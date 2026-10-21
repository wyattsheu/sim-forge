"""robot_model.py — 從場景 USD 的 PhysX 關節直接產生每隻手臂的 URDF + Lula robot description(yaml)。
場景裡的手臂是 stationary_ai 的 6 軸 follower_{left,right}(不是 FR3;Isaac 內建 policy_configs 沒有這款),
所以不用 Franka 近似,改從 USD 關節框架(localPos/Rot0/1、axis、limit)精確轉 URDF。
需要在 SimulationApp 啟動之後 import(用到 pxr)。"""
import os, math
import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics, Gf

ROOT = "/World/stationary_ai"
ARM_JOINTS = ["joint_%d" % i for i in range(6)]
TCP_BACK = 0.010   # TCP = 指尖(ee_gripper_link)往手腕退 10mm:布邊夾在指面 10mm 處

def q2R(w, x, y, z):
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
def T_of(p, q):
    T = np.eye(4); T[:3, :3] = q2R(q.GetReal(), *q.GetImaginary()); T[:3, 3] = np.array(p); return T
def rpy(R):
    sy = -R[2, 0]; p = math.asin(max(-1, min(1, sy)))
    if abs(math.cos(p)) > 1e-9:
        r = math.atan2(R[2, 1], R[2, 2]); y = math.atan2(R[1, 0], R[0, 0])
    else:
        r = math.atan2(-R[1, 2], R[1, 1]); y = 0.0
    return r, p, y
def world(st, path, xc=None):
    xc = xc or UsdGeom.XformCache()
    return np.array(xc.GetLocalToWorldTransform(st.GetPrimAtPath(path))).T

def arm_joints(st, side):
    js = {}
    for nm in ARM_JOINTS + ["left_carriage_joint", "right_carriage_joint"]:
        p = st.GetPrimAtPath("%s/joints/follower_%s_%s" % (ROOT, side, nm))
        j = UsdPhysics.Joint(p)
        jj = UsdPhysics.RevoluteJoint(p) if p.IsA(UsdPhysics.RevoluteJoint) else UsdPhysics.PrismaticJoint(p)
        js[nm] = dict(prim=p, b0=str(j.GetBody0Rel().GetTargets()[0]), b1=str(j.GetBody1Rel().GetTargets()[0]),
                      T0=T_of(j.GetLocalPos0Attr().Get(), j.GetLocalRot0Attr().Get()),
                      T1=T_of(j.GetLocalPos1Attr().Get(), j.GetLocalRot1Attr().Get()),
                      axis={"X": [1, 0, 0], "Y": [0, 1, 0], "Z": [0, 0, 1]}[jj.GetAxisAttr().Get()],
                      lo=jj.GetLowerLimitAttr().Get(), hi=jj.GetUpperLimitAttr().Get(),
                      rev=p.IsA(UsdPhysics.RevoluteJoint))
    return js

def build(st, side, outdir):
    """寫 {side}.urdf / {side}_desc.yaml;回傳 dict(base_T, tcp_in_l6, joint limits(rad))。"""
    js = arm_joints(st, side)
    xc = UsdGeom.XformCache()
    base = "%s/follower_%s_base_link" % (ROOT, side)
    l6 = "%s/follower_%s_link_6" % (ROOT, side)
    ee = "%s/follower_%s_ee_gripper_link" % (ROOT, side)
    T_l6_ee = np.linalg.inv(world(st, l6, xc)) @ world(st, ee, xc)
    T_l6_tcp = T_l6_ee.copy(); T_l6_tcp[:3, 3] -= TCP_BACK * T_l6_ee[:3, 0]   # ee x = 指尖方向
    L = ['<?xml version="1.0"?>', '<robot name="follower_%s">' % side, '  <link name="base_link"/>']
    def org(T):
        r, p, y = rpy(T[:3, :3]); return '<origin xyz="%.9f %.9f %.9f" rpy="%.9f %.9f %.9f"/>' % (*T[:3, 3], r, p, y)
    prev = "base_link"
    lims = []
    for k, nm in enumerate(ARM_JOINTS):
        J = js[nm]
        jf, ln = "j%d_frame" % k, "link_%d" % (k + 1)
        lo, hi = math.radians(J["lo"]), math.radians(J["hi"])
        lims.append((lo, hi))
        L += ['  <link name="%s"/>' % jf, '  <link name="%s"/>' % ln,
              '  <joint name="%s" type="revolute"><parent link="%s"/><child link="%s"/>%s<axis xyz="%d %d %d"/>'
              '<limit lower="%.6f" upper="%.6f" effort="100" velocity="3"/></joint>' % (nm, prev, jf, org(J["T0"]), *J["axis"], lo, hi),
              '  <joint name="%s_fix" type="fixed"><parent link="%s"/><child link="%s"/>%s</joint>' % (nm, jf, ln, org(np.linalg.inv(J["T1"])))]
        prev = ln
    L += ['  <link name="tcp"/>', '  <link name="ee_tip"/>',
          '  <joint name="tcp_fix" type="fixed"><parent link="link_6"/><child link="tcp"/>%s</joint>' % org(T_l6_tcp),
          '  <joint name="tip_fix" type="fixed"><parent link="link_6"/><child link="ee_tip"/>%s</joint>' % org(T_l6_ee),
          '</robot>']
    up = os.path.join(outdir, "%s.urdf" % side); open(up, "w").write("\n".join(L) + "\n")
    mid = [0.5 * (a + b) for a, b in lims]
    Y = ["api_version: 1.0", "cspace:"] + ["  - %s" % n for n in ARM_JOINTS] + \
        ["root_link: base_link", "default_q: [%s]" % ", ".join("%.4f" % m for m in mid),
         "acceleration_limits: [%s]" % ", ".join(["10.0"] * 6), "jerk_limits: [%s]" % ", ".join(["10000.0"] * 6),
         "cspace_to_urdf_rules: []", "composite_task_spaces: []"]
    yp = os.path.join(outdir, "%s_desc.yaml" % side); open(yp, "w").write("\n".join(Y) + "\n")
    return dict(urdf=up, desc=yp, base_T=world(st, base, xc), T_l6_tcp=T_l6_tcp, T_l6_ee=T_l6_ee,
                lims=lims, js=js)

def fk_np(model, q):
    """numpy FK(與 URDF 同一套數字),回傳 base 座標系下各 link 4x4 與 tcp。"""
    js = model["js"]; T = np.eye(4); out = {}
    for k, nm in enumerate(ARM_JOINTS):
        J = js[nm]; a = np.array(J["axis"], float)
        c, s = math.cos(q[k]), math.sin(q[k]); K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
        Rk = np.eye(4); Rk[:3, :3] = np.eye(3) + s * K + (1 - c) * K @ K
        T = T @ J["T0"] @ Rk @ np.linalg.inv(J["T1"])
        out["link_%d" % (k + 1)] = T.copy()
    out["tcp"] = T @ model["T_l6_tcp"]; out["ee_tip"] = T @ model["T_l6_ee"]
    return out

def jac_np(model, q, eps=1e-6):
    """數值幾何 Jacobian(6x6,base 座標;上 3 列線速度、下 3 列角速度)於 tcp。"""
    T0 = fk_np(model, q)["tcp"]; J = np.zeros((6, 6))
    for i in range(6):
        dq = np.array(q, float); dq[i] += eps
        T1 = fk_np(model, dq)["tcp"]
        J[:3, i] = (T1[:3, 3] - T0[:3, 3]) / eps
        dR = T1[:3, :3] @ T0[:3, :3].T
        J[3:, i] = np.array([dR[2, 1] - dR[1, 2], dR[0, 2] - dR[2, 0], dR[1, 0] - dR[0, 1]]) / (2 * eps)
    return J
