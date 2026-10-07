#!/usr/bin/env python3
"""peel_traj_v2.py — v2:紙箱再轉 yaw_extra(預設 180°)、左右分工對調、上蓋改「角落夾」或「指尖頂起」、兩段式開蓋、
掀包材弧線半徑 60mm + 終點抬高、IK 時掃 φ 找**無碰撞**解(幾何檢查直接放進 IK 迴圈)。
    /isaac-sim/python.sh peel_traj_v2.py --lid_mode corner|lift [--fx_open 0|1] [--yaw_extra 180] [--no_video]
以下為 v1 說明(仍適用):空箱 + 蓋子(無包材)的手臂乾跑軌跡,kinematic 設關節(set_joint_positions)。
    /isaac-sim/python.sh peel_traj.py [--hand_b right|left] [--no_video]
(a) PPT 第 1 步:右手掀後方上蓋 fyn(世界 +x)、左手按前方上蓋 fyp(世界 −x)。蓋子用 lid_pose 轉,手跟著外緣中點走(剛性夾持)。
(b) 四片蓋全開(180°)後,--hand_b 那隻手:#1 上方 60mm → 下降 → 合指到 4.5mm → 抬 30mm → 沿弧線掀。
IK:Lula(robot_model.py 由場景 USD 產生的 URDF);姿態規則同 reach.py,不行時指尖方向繞開合軸放寬 φ。
碰撞:**幾何檢查**,不是 PhysX 接觸。手臂各剛體的 collision mesh 表面取樣點(每體 ~1500 點)用 numpy FK 擺到世界,
  對紙箱 9 個 Cube(箱底 1 + 牆 4 + 蓋 4)算有號距離(<0 = 穿入);兩臂之間用 KD-tree 量點對點最小距離;桌面 z。
  夾著/壓著的那片蓋 vs 該手的指頭 = 預期接觸,另列。每格也讀回 PhysX 的 link_6 位姿跟 FK 比(確認 set_joint_positions 真的到位)。"""
import os, sys, json, math, argparse, functools, builtins
print = functools.partial(builtins.print, flush=True)
ap = argparse.ArgumentParser()
ap.add_argument("--scene", default="/isaac-sim/test_scripts/manip_fr3/handoff_20261002/scene_final.usd")
ap.add_argument("--yaw_extra", type=float, default=180.0, help="紙箱在 scene_final 的擺法上再繞 z 轉幾度(中心不動)")
ap.add_argument("--lid_mode", default="lift", choices=["corner", "lift", "pinch"])
ap.add_argument("--lid_mid", type=float, default=70.0, help="兩段式:手掀到這個角度就放手,之後蓋子 kinematic 轉到 180")
ap.add_argument("--ajar", type=float, default=12.0, help="lift 模式:蓋子先 kinematic 轉開的角度(手做不到的那一步)")
ap.add_argument("--fx_open", type=int, default=1)
ap.add_argument("--open_deg", type=float, default=180.0, help="(b) 前蓋/下蓋開到的角度;180 = 平躺在鉸鏈高度,>180 = 往外垂、貼外牆")
ap.add_argument("--only", default="all", choices=["all", "a", "b"])
ap.add_argument("--arc_R", type=float, default=60.0)
ap.add_argument("--psi", type=float, default=0.0, help="(b) 允許開合軸繞指尖軸偏離邊法線的最大角度(°);0 = 嚴格照規格")
ap.add_argument("--grasp", type=int, default=1, help="g3 排名第幾個抓取點(1 或 2 有方向資料)")
ap.add_argument("--video_name", default="arm_peel_dry_v2.mp4")
ap.add_argument("--out", default=None)
ap.add_argument("--no_video", action="store_true")
a = ap.parse_args()
from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
import numpy as np
import omni.usd
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Gf, Sdf
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import robot_model as RM
from isaacsim.robot_motion.motion_generation import LulaKinematicsSolver
import lula, trimesh
from scipy.spatial import cKDTree
TAG = "v2_%s_fx%d_g%d_psi%d_o%d" % (a.lid_mode, a.fx_open, a.grasp, a.psi, a.open_deg)
OUT = a.out or os.path.join(HERE, "videos", a.video_name)
os.makedirs(os.path.join(HERE, "videos"), exist_ok=True); os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
LOG = open(os.path.join(HERE, "logs", "peel_traj_%s.log" % TAG), "w")
def P(*s):
    t = " ".join(str(x) for x in s); print(t); LOG.write(t + "\n"); LOG.flush()

omni.usd.get_context().open_stage(a.scene)
for _ in range(10): app.update()
st = omni.usd.get_context().get_stage()
BOX = "/World/Packed/Box"
_rz = next(o for o in UsdGeom.Xformable(st.GetPrimAtPath("/World/Packed")).GetOrderedXformOps() if o.GetOpName() == "xformOp:rotateZ")
_rz.Set(float(_rz.Get()) + a.yaw_extra)
P("★ 擺法:/World/Packed rotateZ = %.0f°(scene_final 90° + %.0f°),中心不動;只改這次的 stage" % (_rz.Get(), a.yaw_extra))
for p in ("/World/Packed/Wrap", "/World/Packed/Mug"):
    st.GetPrimAtPath(p).SetActive(False)
P("包材 / 杯子 deactivate(空箱 + 蓋子)")
if not any(p.IsA(UsdPhysics.Scene) for p in st.Traverse()):
    ps = UsdPhysics.Scene.Define(st, "/physicsScene")
else:
    ps = UsdPhysics.Scene(next(p for p in st.Traverse() if p.IsA(UsdPhysics.Scene)))
ps.CreateGravityMagnitudeAttr().Set(0.0)      # kinematic 乾跑:不要重力把手臂往下拉
for n in ("base", "fxp", "fxn", "fyp", "fyn"):
    UsdPhysics.RigidBodyAPI(st.GetPrimAtPath(BOX + "/" + n)).CreateKinematicEnabledAttr().Set(True)
for n in ("fxp", "fxn", "fyp", "fyn"):     # 蓋子:關掉剛體,改成純 USD xform(每格寫 transform op),渲染一定跟得上
    UsdPhysics.RigidBodyAPI(st.GetPrimAtPath(BOX + "/" + n)).CreateRigidBodyEnabledAttr().Set(False)
for n in ("fxp", "fxn", "fyp", "fyn"):
    UsdPhysics.Joint(st.GetPrimAtPath(BOX + "/crease_" + n)).CreateJointEnabledAttr().Set(False)
P("紙箱底 + 4 蓋 = kinematic,摺痕關節停用(蓋子由 lid_pose 直接擺)、重力 0")

xc = UsdGeom.XformCache()
def Wm(p): return np.array(xc.GetLocalToWorldTransform(st.GetPrimAtPath(p))).T
TB = Wm(BOX)
RJ = json.load(open(os.path.join(HERE, "data", "reach.json")))
meta = json.load(open("/isaac-sim/test_scripts/manip_fr3/handoff_20260929/work/carton.meta.json"))["derived"]

# ── 手臂模型 + IK ─────────────────────────────────────────
ARMS = {}
for side in ("left", "right"):
    m = RM.build(st, side, os.path.join(HERE, "data"))
    sol = LulaKinematicsSolver(robot_description_path=m["desc"], urdf_path=m["urdf"])
    bT = m["base_T"]; q = Gf.Matrix3d(*bT[:3, :3].T.flatten().tolist()).ExtractRotation().GetQuat()
    sol.set_robot_base_pose(bT[:3, 3], np.array([q.GetReal(), *q.GetImaginary()]))
    sol.set_default_position_tolerance(0.001); sol.set_default_orientation_tolerance(0.01)
    sol.bfgs_cspace_limit_biasing = lula.CyclicCoordDescentIkConfig.CSpaceLimitBiasing.ENABLE
    m.update(sol=sol, lo=np.array([l for l, h in m["lims"]]), hi=np.array([h for l, h in m["lims"]]))
    ARMS[side] = m

def quat(R):
    q = Gf.Matrix3d(*R.T.flatten().tolist()).ExtractRotation().GetQuat(); return np.array([q.GetReal(), *q.GetImaginary()])
def rot_axis(k, deg):
    k = np.asarray(k, float) / np.linalg.norm(k); th = math.radians(deg)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K
def wrap_lim(q, lo, hi):
    q = np.array(q, float)
    for i in range(len(q)):
        for k in (-1, 1):
            if not (lo[i] <= q[i] <= hi[i]) and lo[i] <= q[i] + k * 2 * math.pi <= hi[i]: q[i] += k * 2 * math.pi
    return q
def fk_tcp(side, q):
    m = ARMS[side]; return m["base_T"] @ RM.fk_np(m, q)["tcp"]
def check(side, q, pos, R):
    m = ARMS[side]; T = fk_tcp(side, q)
    pe = np.linalg.norm(T[:3, 3] - pos) * 1e3
    oe = math.degrees(math.acos(max(-1, min(1, (np.trace(T[:3, :3].T @ R) - 1) / 2))))
    inl = bool(np.all(q >= m["lo"] - 1e-4) and np.all(q <= m["hi"] + 1e-4))
    return pe < 1.5 and oe < 1.5 and inl, pe, oe
PHIS = [0, 5, -5, 10, -10, 15, -15, 20, -20, 30, -30, 45, -45, 60, -60, 75, -75, 90, -90]
def ik(side, pos, R, q_prev, phi_prev=0.0, maxjump=25.0, nseed=12):
    """φ 依離 phi_prev 遠近排序;先用 q_prev 起點,再試隨機起點;要求跟前一點的關節跳動 < maxjump°。"""
    m = ARMS[side]; rng = np.random.default_rng(11)
    order = sorted(PHIS, key=lambda p: (abs(p - phi_prev), abs(p)))
    for ph in order:
        Rp = rot_axis(R[:, 1], ph) @ R
        away = np.array([0, 1.0, 0]) if side == "left" else np.array([0, -1.0, 0])
        flips = sorted((1, -1), key=lambda f_: -(f_ * Rp[:, 2] @ away))       # 腕上相機(tool +z 側)朝自己的基座,不朝另一臂
        for flip in flips:
            Rf = Rp.copy()
            if flip < 0: Rf[:, 1] *= -1; Rf[:, 2] *= -1
            starts = [q_prev] + [m["lo"] + (m["hi"] - m["lo"]) * rng.uniform(0.05, 0.95, 6) for _ in range(nseed if q_prev is None else 4)]
            for w in starts:
                if w is None: continue
                qs, ok = m["sol"].compute_inverse_kinematics("tcp", pos, quat(Rf), warm_start=np.asarray(w))
                qs = wrap_lim(qs, m["lo"], m["hi"])
                good, pe, oe = check(side, qs, pos, Rf)
                if good and (q_prev is None or np.max(np.abs(qs - q_prev)) < math.radians(maxjump)):
                    return qs, ph
    return None, None
def cart(side, poses, q0, phi0):
    qs, phis = [], []; q, ph = q0, phi0
    for i, (p_, R_) in enumerate(poses):
        qn, phn = ik(side, p_, R_, q, ph)
        if qn is None:
            return qs, phis, i
        qs.append(qn); phis.append(phn); q, ph = qn, phn
    return qs, phis, None
def lerp_q(q0, q1, n):
    return [q0 + (q1 - q0) * (0.5 - 0.5 * math.cos(math.pi * k / (n - 1))) for k in range(n)]

# ── 夾爪:指面間距 vs carriage 關節 ─────────────────────────
JALL = {}
for p in st.Traverse():
    if p.IsA(UsdPhysics.Joint) and "/joints/" in str(p.GetPath()):
        j = UsdPhysics.Joint(p); b0 = j.GetBody0Rel().GetTargets(); b1 = j.GetBody1Rel().GetTargets()
        if b0 and b1:
            JALL[str(b1[0])] = dict(name=p.GetName(), b0=str(b0[0]), T0=RM.T_of(j.GetLocalPos0Attr().Get(), j.GetLocalRot0Attr().Get()),
                                   T1=RM.T_of(j.GetLocalPos1Attr().Get(), j.GetLocalRot1Attr().Get()), prim=p)
R0 = RM.ROOT
def body_fk(side, q6, qc_l, qc_r):
    """各剛體世界 4x4。carriage = link_6·T0·Trans(axis·q)·T1⁻¹;其餘 fixed 子體一路往下接。"""
    m = ARMS[side]; fk = RM.fk_np(m, q6); out = {}
    for k in range(1, 7): out["%s/follower_%s_link_%d" % (R0, side, k)] = m["base_T"] @ fk["link_%d" % k]
    js = m["js"]
    for nm, qq in (("left_carriage_joint", qc_l), ("right_carriage_joint", qc_r)):
        J = js[nm]; Tr = np.eye(4); Tr[:3, 3] = np.array(J["axis"], float) * qq
        out[J["b1"]] = out[J["b0"]] @ J["T0"] @ Tr @ np.linalg.inv(J["T1"])
    changed = True
    while changed:
        changed = False
        for b1, J in JALL.items():
            if b1 not in out and J["b0"] in out and ("follower_%s_" % side) in b1 and J["prim"].IsA(UsdPhysics.FixedJoint):
                out[b1] = out[J["b0"]] @ J["T0"] @ np.linalg.inv(J["T1"]); changed = True
    return out
# 剛體的 collision mesh 取樣點(body 座標)
PTS = {}
for side in ("left", "right"):
    for b in body_fk(side, np.zeros(6), 0, 0):
        Wb = Wm(b); pts = []
        for p in Usd.PrimRange(st.GetPrimAtPath(b)):
            if p.IsA(UsdGeom.Mesh) and "/collisions/" in str(p.GetPath()):
                mm = UsdGeom.Mesh(p); v = np.array(mm.GetPointsAttr().Get(), float)
                fc = np.array(mm.GetFaceVertexCountsAttr().Get()); fi = np.array(mm.GetFaceVertexIndicesAttr().Get())
                if np.all(fc == 3):
                    tm = trimesh.Trimesh(v, fi.reshape(-1, 3), process=False)
                    sp, _ = trimesh.sample.sample_surface(tm, 1500, seed=0); v = np.vstack([sp, v[::max(1, len(v) // 300)]])
                M = np.linalg.inv(Wb) @ Wm(str(p.GetPath()))
                pts.append((M @ np.c_[v, np.ones(len(v))].T).T[:, :3])
        if pts: PTS[b] = np.vstack(pts)
P("碰撞取樣:%d 個剛體,共 %d 點" % (len(PTS), sum(len(v) for v in PTS.values())))
def finger_gap(side, qc_l, qc_r):
    """兩指 collision 點在 tcp 座標的開合軸(y)上的內面距離;只看指尖往回 25mm 的指面區。"""
    B = body_fk(side, np.zeros(6), qc_l, qc_r); Tt = ARMS[side]["base_T"] @ RM.fk_np(ARMS[side], np.zeros(6))["ee_tip"]
    ys = {}
    for f in ("gripper_left", "gripper_right"):
        b = "%s/follower_%s_%s" % (R0, side, f); w = (B[b] @ np.c_[PTS[b], np.ones(len(PTS[b]))].T).T[:, :3]
        l = (np.linalg.inv(Tt) @ np.c_[w, np.ones(len(w))].T).T[:, :3]
        l = l[(l[:, 0] > -0.025) & (l[:, 0] < 0.001)]
        ys[f] = l[:, 1]
    A, Bf = ("gripper_left", "gripper_right") if ys["gripper_left"].mean() > ys["gripper_right"].mean() else ("gripper_right", "gripper_left")
    return (ys[A].min() - ys[Bf].max()) * 1e3, (ys[A].min() + ys[Bf].max()) / 2 * 1e3
for sgn in (1, -1):
    g0, c0 = finger_gap("right", 0, 0); g1, c1 = finger_gap("right", 0.02, sgn * 0.02)
    P("夾爪測試:carriage_left=20mm、right=%+dmm → 指面間距 %.1f → %.1f mm,中心偏移 %.1f mm" % (sgn * 20, g0, g1, c1 - c0))
gA = finger_gap("right", 0.02, 0.02); gB = finger_gap("right", 0.02, -0.02)
MIM = 1.0 if abs(gA[1] - finger_gap("right", 0, 0)[1]) < abs(gB[1] - finger_gap("right", 0, 0)[1]) else -1.0
G0 = finger_gap("right", 0, 0)[0]; GK = (finger_gap("right", 0.02, MIM * 0.02)[0] - G0) / 0.02
GMAX = finger_gap("right", 0.044, MIM * 0.044)[0]
P("★ 夾爪:right_carriage = %+.0f × left_carriage(對稱);指面間距 = %.1f mm + %.2f × q(m);q=0 → %.1f mm、q=44mm(上限)→ %.1f mm" % (MIM, G0, GK, G0, GMAX))
def q_for_gap(gmm): return max(0.0, min(0.044, (gmm - G0) / GK))

# ── 紙箱 OBB ──────────────────────────────────────────────
OBB = []
BBC = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
for body in ("base", "fxp", "fxn", "fyp", "fyn"):
    for p in Usd.PrimRange(st.GetPrimAtPath(BOX + "/" + body)):
        if p.IsA(UsdGeom.Cube):
            rg = BBC.ComputeUntransformedBound(p).GetRange()
            M = Wm(str(p.GetPath())); mn, mx = np.array(rg.GetMin()), np.array(rg.GetMax())
            ctr = M @ np.r_[(mn + mx) / 2, 1]; ax = M[:3, :3] * ((mx - mn) / 2)
            hl = np.linalg.norm(ax, axis=0); U = ax / hl
            OBB.append(dict(name=body + ("/" + p.GetName() if body == "base" else ""), body=body, c0=ctr[:3], U0=U, h=hl))
P("紙箱 Cube:%s" % ", ".join("%s %.0fx%.0fx%.0f" % (o["name"], *(2e3 * o["h"])) for o in OBB))
LID = {}
for nm, L in RJ["lids"].items():
    LID[nm] = dict(hw=(TB @ np.r_[L["h"], 1])[:3], aw=TB[:3, :3] @ np.array(L["ax"]), sgn=L["sgn"], mid=np.array(L["mid"]))
def lid_T(nm, deg):
    L = LID[nm]; T = np.eye(4); R = rot_axis(L["aw"], L["sgn"] * deg)
    T[:3, :3] = R; T[:3, 3] = L["hw"] - R @ L["hw"]; return T
def lid_edge(nm, deg):
    return (lid_T(nm, deg) @ TB @ np.r_[LID[nm]["mid"], 1])[:3]
def sdist(pts, o, T):
    c = (T @ np.r_[o["c0"], 1])[:3]; U = T[:3, :3] @ o["U0"]
    l = (pts - c) @ U; d = np.abs(l) - o["h"]
    out = np.linalg.norm(np.maximum(d, 0), axis=1); inside = np.minimum(d.max(1), 0)
    return out + inside
TABLE_Z = 0.020


TABLE_Z = 0.020
# ── 單臂碰撞(給 IK 迴圈用)───────────────────────────────
PLAN_TOL = -0.3      # 規劃時:穿入 ≤ 0.3mm 才接受(驗收門檻 0.5mm,留餘裕)
ARM_MIN = 12.0       # 規劃時兩臂 ≥ 12mm(驗收 10mm)
def arm_world(side, q6, g):
    B = body_fk(side, np.asarray(q6), g, MIM * g); W = {}
    for b, T in B.items():
        if b in PTS: W[b] = (T @ np.c_[PTS[b], np.ones(len(PTS[b]))].T).T[:, :3]
    return W
def arm_clear(side, q6, g, lids):
    W = arm_world(side, q6, g); allp = np.vstack(list(W.values()))
    best = ((allp[:, 2].min() - TABLE_Z) * 1e3, "table", "")
    for o in OBB:
        T = lid_T(o["body"], lids[o["body"]]) if o["body"] != "base" else np.eye(4)
        for b, pts in W.items():
            d = sdist(pts, o, T).min() * 1e3
            if d < best[0]: best = (d, o["name"], b.rsplit("follower_", 1)[-1])
    return best, allp
DIAG = [None]
PSIS = [0.0]
def ik_cf(side, pos, R, q_prev, phi_prev, g, lids, phis, other=None, maxjump=25.0, nseed=10, psis=None):
    """φ(繞開合軸)依離 phi_prev 近排序;每個候選解都做幾何碰撞檢查(紙箱/桌面;other=(points) 時再加兩臂距離)。"""
    m = ARMS[side]; rng = np.random.default_rng(5)
    tree = cKDTree(other) if other is not None else None
    away = np.array([0, 1.0, 0]) if side == "left" else np.array([0, -1.0, 0])
    cand = [(ph, ps) for ps in (psis or [0.0]) for ph in sorted(phis, key=lambda p: (abs(p - phi_prev), abs(p)))]
    for ph, ps in cand:
        R1 = rot_axis(R[:, 0], ps) @ R                     # ψ:繞指尖軸
        Rp = rot_axis(R1[:, 1], ph) @ R1
        for flip in sorted((1, -1), key=lambda f_: -(f_ * Rp[:, 2] @ away)):
            Rf = Rp.copy()
            if flip < 0: Rf[:, 1] *= -1; Rf[:, 2] *= -1
            starts = ([q_prev] if q_prev is not None else []) + [m["lo"] + (m["hi"] - m["lo"]) * rng.uniform(0.05, 0.95, 6) for _ in range(nseed if q_prev is None else 3)]
            for w in starts:
                qs, ok = m["sol"].compute_inverse_kinematics("tcp", pos, quat(Rf), warm_start=np.asarray(w))
                qs = wrap_lim(qs, m["lo"], m["hi"])
                good, pe, oe = check(side, qs, pos, Rf)
                if not good or (q_prev is not None and maxjump and np.max(np.abs(qs - q_prev)) > math.radians(maxjump)): continue
                if isinstance(lids, list):      # 多個蓋子狀態都要過(例如蓋子會掀過來的路徑)
                    rr = [arm_clear(side, qs, g, l_) for l_ in lids]; (d, nm, bn), allp = min(rr, key=lambda r_: r_[0][0])
                else:
                    (d, nm, bn), allp = arm_clear(side, qs, g, lids)
                if d < PLAN_TOL:
                    if DIAG[0] is None or d > DIAG[0][0]: DIAG[0] = (d, nm, bn, ph, ps)
                    continue
                if tree is not None and tree.query(allp, k=1)[0].min() * 1e3 < ARM_MIN: continue
                LASTPSI[0] = ps
                return qs, ph
    return None, None
LASTPSI = [0.0]; USEDPSI = set()
def cart_cf(side, poses, q0, phi0, g, lids_seq, phis, label, other_seq=None, psis=None):
    qs, phs = [], []; q, ph = q0, phi0; USEDPSI.clear()
    for i, (p_, R_) in enumerate(poses):
        lids = lids_seq[i] if (isinstance(lids_seq, list) and len(lids_seq) == len(poses)) else lids_seq
        oth = other_seq[i] if isinstance(other_seq, list) else other_seq
        DIAG[0] = None
        qn, phn = ik_cf(side, p_, R_, q, ph, g, lids, phis, oth, psis=psis); USEDPSI.add(LASTPSI[0])
        if qn is None:
            P("  ✗ %s(%s):第 %d/%d 點找不到無碰撞 IK(tcp 世界 %s mm);IK 有解但最好的仍穿入 %s" % (label, side, i, len(poses), (p_ * 1e3).round(1).tolist(),
              "%.1fmm(%s↔%s,φ%d ψ%d)" % DIAG[0] if DIAG[0] else "—(IK 本身無解)"))
            return qs, phs, i
        qs.append(qn); phs.append(phn); q, ph = qn, phn
    P("  %s(%s):%d 點全解,φ 用到 %s、ψ 用到 %s" % (label, side, len(qs), sorted(set(int(p) for p in phs)), sorted(int(x) for x in USEDPSI)))
    return qs, phs, None
def pts_of(side, q, g): return np.vstack(list(arm_world(side, q, g).values()))

# ── 軌跡 ──────────────────────────────────────────────────
FPS = 30
SEG = []
HOME = np.zeros(6)
lids0 = dict(fxp=0.0, fxn=0.0, fyp=0.0, fyn=0.0)
st_ = dict(qL=HOME.copy(), qR=HOME.copy(), gL=0.0, gR=0.0, lids=dict(lids0))
def add(name, secs, qL=None, qR=None, gL=None, gR=None, lids=None, contact=None):
    n = max(2, int(round(secs * FPS)))
    def seq(v, cur):
        if v is None: return [cur.copy() if hasattr(cur, "copy") else cur] * n
        if isinstance(v, list) and not v: return [cur.copy() if hasattr(cur, "copy") else cur] * n
        if isinstance(v, list): return v if len(v) == n else [v[min(len(v) - 1, int(k * len(v) / n))] for k in range(n)]
        return lerp_q(np.atleast_1d(cur).astype(float), np.atleast_1d(v).astype(float), n) if hasattr(v, "__len__") else \
            [cur + (v - cur) * (0.5 - 0.5 * math.cos(math.pi * k / (n - 1))) for k in range(n)]
    s = dict(name=name, n=n, qL=seq(qL, st_["qL"]), qR=seq(qR, st_["qR"]), gL=seq(gL, st_["gL"]), gR=seq(gR, st_["gR"]), contact=contact or {})
    if lids is None: s["lids"] = [dict(st_["lids"])] * n
    elif isinstance(lids, list): s["lids"] = [lids[min(len(lids) - 1, int(k * len(lids) / n))] for k in range(n)]
    else:
        s["lids"] = [{k: st_["lids"][k] + (lids.get(k, st_["lids"][k]) - st_["lids"][k]) * (0.5 - 0.5 * math.cos(math.pi * i / (n - 1))) for k in lids0} for i in range(n)]
    SEG.append(s); st_.update(qL=np.array(s["qL"][-1]), qR=np.array(s["qR"][-1]), gL=float(s["gL"][-1]), gR=float(s["gR"][-1]), lids=dict(s["lids"][-1]))
    return s
FAIL = []
OPEN_GAP = 21.0; CLOSE_GAP = 4.5
gOpen, gClose = q_for_gap(OPEN_GAP), q_for_gap(CLOSE_GAP)
PH_ALL = list(range(-90, 91, 10))
PH_WRAP = [0, 10, -10, 15, -15, 20, -20, 25, -25, 30, -30, 35, -35, 40, -40, 45, -45]
# 世界方向:哪片上蓋在後方(+x)
def lid_center_x(nm): return (TB @ np.r_[LID[nm]["mid"] * 0 + (np.array(RJ["lids"][nm]["h"])), 1])[0]
BACK = max(("fyp", "fyn"), key=lid_center_x); FRONT = "fyn" if BACK == "fyp" else "fyp"
P("★ 上蓋:後方(+x)= %s、前方(−x)= %s" % (BACK, FRONT))
PEEL, PRESS = "left", "right"          # 對調後:左手掀後方、右手按前方;(b) 右手掀包材 #1
READY = {}
for side, sy in (("left", 1), ("right", -1)):
    Rr_ = np.column_stack([[0, 0, -1.0], [1.0, 0, 0], [0, -1.0, 0]])
    qr_, _p = ik(side, np.array([-0.02, sy * 0.25, 0.33]), Rr_, None)
    READY[side] = qr_ if qr_ is not None else HOME
add("a0 home→READY", 1.5, qL=READY["left"], qR=READY["right"])

if a.only != "b":
    P("\n=== (a) %s 手掀後方上蓋 %s(%s)、%s 手壓前方上蓋 %s" % (PEEL, BACK, a.lid_mode, PRESS, FRONT))
    LB = RJ["lids"][BACK]; LF = RJ["lids"][FRONT]
    hB = np.array(LB["h"]); axB = np.array(LB["ax"]); midB = np.array(LB["mid"])
    # 角落點:外緣上、離「靠 PEEL 手那個角」50mm(箱局部 x = ±(131−50))
    sgn_peel = 1.0 if (TB[:3, :3] @ np.array([1.0, 0, 0]))[1] * (1 if PEEL == "left" else -1) > 0 else -1.0
    corner_loc = midB.copy(); corner_loc[0] = sgn_peel * (meta["flap_half_width_upper"] - 0.050)
    cw0 = (TB @ np.r_[corner_loc, 1])[:3]
    en_w = TB[:3, :3] @ ((midB - hB) - axB * ((midB - hB) @ axB)); en_w[2] = 0; en_w /= np.linalg.norm(en_w)     # 鉸鏈→外緣(水平)
    ax_w = LID[BACK]["aw"]
    P("  掀蓋點(外緣、離角 50mm):箱局部 %s → 世界 %s mm" % ((corner_loc * 1e3).round(1).tolist(), (cw0 * 1e3).round(1).tolist()))
    # 壓的手:前方上蓋板面中段、靠 PRESS 手那側 90mm、離鉸鏈 55mm;指尖距板面 +0.3mm
    hF = np.array(LF["h"]); inF = (np.array(LF["mid"]) - hF); inF[2] = 0; inF /= np.linalg.norm(inF)
    sgn_press = 1.0 if (TB[:3, :3] @ np.array([1.0, 0, 0]))[1] * (1 if PRESS == "left" else -1) > 0 else -1.0
    press_loc = hF + inF * 0.055 + np.array([sgn_press * 0.09, 0, 0]); press_loc[2] = LF["mid"][2] + 0.0015 + 0.0003
    pw = (TB @ np.r_[press_loc, 1])[:3]
    Rp0 = np.column_stack([[0, 0, -1.0], [1.0, 0, 0], [0, -1.0, 0]])
    PSI_PRESS = [90, -90, 75, -75, 60, -60, 45, -45, 30, -30, 0]     # 繞指軸轉:優先讓夾爪滑軌(寬 186mm)沿 y,不要橫在後蓋掀起的路上
    tipP = pw + np.array([0, 0, RM.TCP_BACK])
    L0 = dict(lids0)
    LPR = [dict(lids0, **{BACK: float(d_)}) for d_ in np.linspace(0, a.lid_mid, 7)]    # 壓的手要讓開「後蓋 0→lid_mid 整段」
    qPpre, phP = ik_cf(PRESS, tipP + np.array([0, 0, 0.06]), Rp0, READY[PRESS], 0, 0.0, LPR, PH_ALL, maxjump=None, psis=PSI_PRESS)
    Rp0 = rot_axis(Rp0[:, 0], LASTPSI[0]) @ Rp0; P("  壓的手:指軸轉 ψ=%d°(滑軌方向 %s)" % (LASTPSI[0], (Rp0[:, 1]).round(2).tolist()))
    dnP = [(tipP + np.array([0, 0, 0.06 * (1 - u)]), Rp0) for u in np.linspace(0, 1, 25)]
    qsP, phsP, fP = cart_cf(PRESS, dnP, qPpre, phP, 0.0, LPR, PH_ALL, "a2 壓的手下降到 %s 板面" % FRONT) if qPpre is not None else ([], [], 0)
    P("  壓點 世界 %s mm" % ((pw * 1e3).round(1).tolist()))
    if qPpre is None or fP is not None: FAIL.append("(a) 壓的手到不了")
    qk = lambda s_: "qL" if s_ == "left" else "qR"; gk = lambda s_: "gL" if s_ == "left" else "gR"

    def lidT_loc(deg):   # 世界 4x4:後蓋從 0° 轉到 deg
        return lid_T(BACK, deg)
    if a.lid_mode == "corner":
        # 外緣角落「跨邊夾」:指尖朝 −z,開合軸 = 邊法線(水平),tcp 在外緣上;蓋子 0°
        Rc = np.column_stack([[0, 0, -1.0], en_w, np.cross([0, 0, -1.0], en_w)])
        gC = q_for_gap(10.0)
        otherP = pts_of(PRESS, qsP[-1], 0.0) if qsP else None
        qpre, ph0 = ik_cf(PEEL, cw0 + np.array([0, 0, 0.06]), Rc, READY[PEEL], 0, gC, L0, PH_ALL, otherP, maxjump=None)
        lift_ok = False
        if qpre is None: FAIL.append("(a) corner:預備點找不到無碰撞 IK")
        else:
            dn = [(cw0 + np.array([0, 0, 0.06 * (1 - u)]), Rc) for u in np.linspace(0, 1, 30)]
            qsD, phD, f_ = cart_cf(PEEL, dn, qpre, ph0, gC, L0, PH_ALL, "a3 corner:跨邊下降", otherP)
            if f_ is not None: FAIL.append("(a) corner:下降到外緣角落時無碰撞解中斷於 %d/30(跨邊夾一定會壓到/插進板子)" % f_)
            start_q, start_ph, start_deg, T_grip = (qsD[-1], phD[-1], 0.0, None) if qsD else (qpre, ph0, 0.0, None)
            add("a1 到預備點", 2.5, **{qk(PEEL): qpre, gk(PEEL): gC, qk(PRESS): qPpre})
            add("a2 壓的手下降 / 掀的手跨邊下降", 1.5, **{qk(PRESS): qsP, qk(PEEL): qsD if qsD else [qpre]})
            lift_ok = f_ is None
    elif a.lid_mode == "pinch":
        # 角落「捏板厚」:蓋子先 kinematic 開到 ajar°(手做不到這步),指尖沿板面朝鉸鏈方向伸進外緣角落,
        # 開合軸 = 板面法線(上下指夾板厚),開 21mm → 合 4.5mm,剛性帶著蓋子轉
        otherP = pts_of(PRESS, qsP[-1], 0.0) if qsP else None
        LA = dict(lids0, **{BACK: a.ajar}); TA = lidT_loc(a.ajar)
        cwA = (TA @ np.r_[cw0, 1])[:3]; nA = TA[:3, :3] @ np.array([0, 0, 1.0]); enA = TA[:3, :3] @ en_w
        gC = gOpen; best = None; BESTREJ = [None]
        for ins in (0.010, 0.015, 0.006):
            tcp = cwA - enA * ins + nA * 0.0          # tcp 在板中面
            Rb0 = np.column_stack([-enA, nA, np.cross(-enA, nA)])
            for phs in sorted(PH_ALL, key=abs):
                Rb = rot_axis(Rb0[:, 1], phs) @ Rb0
                tcp_ = cwA - Rb[:, 0] * (-ins) * 0 - enA * ins
                DIAG[0] = None
                q_, ph_ = ik_cf(PEEL, tcp_, Rb, None, 0, gC, LA, [0], otherP, maxjump=None, nseed=16)
                if q_ is None:
                    if DIAG[0] is not None and (BESTREJ[0] is None or DIAG[0][0] > BESTREJ[0][0]): BESTREJ[0] = DIAG[0] + (phs, ins)
                    continue
                dvH = -Rb[:, 0]
                for dv in (dvH, (dvH + np.array([0, 0, 1.0])) / np.linalg.norm(dvH + np.array([0, 0, 1.0]))):
                    appr = [(tcp_ + dv * 0.04 * (1 - u), Rb) for u in np.linspace(0, 1, 25)]
                    qs0, _p0 = ik_cf(PEEL, appr[0][0], Rb, q_, 0, gC, LA, [0, 10, -10], otherP, maxjump=None)
                    if qs0 is None: continue
                    qpre, ph0 = ik_cf(PEEL, appr[0][0] + np.array([0, 0, 0.05]), Rb, qs0, _p0, gC, LA, [0, 10, -10, 20, -20], otherP, maxjump=None)
                    if qpre is None: continue
                    upd = [(appr[0][0] + np.array([0, 0, 0.05 * (1 - u)]), Rb) for u in np.linspace(0, 1, 15)]
                    qsU0, phU0, fU0 = cart_cf(PEEL, upd, qpre, ph0, gC, LA, [0, 10, -10, 20, -20], "a3 pinch:下降到進場起點", otherP)
                    if fU0 is not None: continue
                    qsD, phD, f_ = cart_cf(PEEL, appr, qsU0[-1], phU0[-1], gC, LA, [0, 10, -10, 20, -20], "a3 pinch:沿板面伸進外緣角落", otherP)
                    if f_ is None: best = (ins, phs); qsD = qsU0 + qsD; break
                if best: break
            if best: break
        lift_ok = best is not None
        if not lift_ok:
            FAIL.append("(a) pinch:找不到可無碰撞進場的捏法(碰撞中最好的:%s)" % (BESTREJ[0],)); qpre = READY[PEEL]; qsD = []
        else:
            P("  pinch:蓋子先 kinematic 開到 %.0f°;指尖伸進外緣 %.0fmm、指軸繞板法線 %d°" % (a.ajar, best[0] * 1e3, best[1]))
        add("a1 到預備點(壓的手 / 掀的手)", 2.5, **{qk(PRESS): qPpre, qk(PEEL): qpre if qpre is not None else READY[PEEL], gk(PEEL): gC})
        add("a2 壓的手下降壓住 %s" % FRONT, 1.2, **{qk(PRESS): qsP})
        add("a2b 後蓋 kinematic 開到 %.0f°(非手動)" % a.ajar, 0.8, lids={BACK: a.ajar})
        add("a3 指頭沿板面伸進外緣角落(開 21mm)", 1.5, **{qk(PEEL): qsD if qsD else [qpre]})
        if lift_ok:
            add("a3b 合指到 5.0mm(夾板厚 3mm)", 0.5, **{gk(PEEL): q_for_gap(5.0)}); gC = q_for_gap(5.0)
        start_q, start_ph, start_deg = (qsD[-1], phD[-1], a.ajar) if qsD else (None, 0, a.ajar)
    else:
        # 指尖頂起:蓋子先 kinematic 轉開 ajar°(手做不到),指尖(合指)伸到外緣角落下方 → 跟著蓋子頂到 lid_mid
        gC = 0.0
        otherP = pts_of(PRESS, qsP[-1], 0.0) if qsP else None
        LA = dict(lids0, **{BACK: a.ajar})
        TA = lidT_loc(a.ajar)
        cwA = (TA @ np.r_[cw0, 1])[:3]
        nA = TA[:3, :3] @ np.array([0, 0, 1.0]); enA = TA[:3, :3] @ en_w     # 板面法線(向上)、鉸鏈→外緣
        best = None; tried = 0; BESTREJ = [None]
        def own_clear(q):
            W = arm_world(PEEL, q, gC); o = next(o for o in OBB if o["body"] == BACK)
            return min(sdist(W[b], o, lidT_loc(a.ajar)).min() for b in W if ("gripper_" in b or "carriage_" in b)) * 1e3
        for gap in [0.0015 + x * 1e-3 for x in (4, 8, 12, 16, 20, 25, 30, 35)]:   # 指軸在板底下(要量真正的指面離板距離)
            for ins in (0.004, 0.008, 0.012):                  # 指尖伸進外緣內
                tip = cwA - nA * gap - enA * ins
                for base_a in (-enA, np.array([0, 0, -1.0])):
                    Rb0 = np.column_stack([base_a / np.linalg.norm(base_a), ax_w, np.cross(base_a / np.linalg.norm(base_a), ax_w)])
                    for phs in PH_ALL:
                        Rb = rot_axis(Rb0[:, 1], phs) @ Rb0
                        tcp = tip - Rb[:, 0] * RM.TCP_BACK
                        DIAG[0] = None
                        q_, ph_ = ik_cf(PEEL, tcp, Rb, None, 0, gC, LA, [0], otherP, maxjump=None, nseed=16)
                        if q_ is not None and own_clear(q_) > 6.0: continue          # 指頭離板底 > 6mm 就不算「頂」
                        if q_ is None:
                            if DIAG[0] is not None and (BESTREJ[0] is None or DIAG[0][0] > BESTREJ[0][0]): BESTREJ[0] = DIAG[0] + (phs, gap, ins)
                            continue
                        tried += 1
                        # 進場:試三個退出方向(沿指軸反向 / 水平往外緣外 / 正上方),起點離 40mm,再往上 50mm 當預備點
                        enH = enA.copy(); enH[2] = 0; enH /= np.linalg.norm(enH)
                        for dv in (-Rb[:, 0], enH, np.array([0, 0, 1.0]), (enH + np.array([0, 0, 1.0])) / math.sqrt(2)):
                            appr = [(tcp + dv * 0.04 * (1 - u), Rb) for u in np.linspace(0, 1, 25)]
                            qs0, _p0 = ik_cf(PEEL, appr[0][0], Rb, q_, 0, gC, LA, [0, 10, -10, 20, -20], otherP, maxjump=None)
                            if qs0 is None: continue
                            qpre, ph0 = ik_cf(PEEL, appr[0][0] + np.array([0, 0, 0.05]), Rb, qs0, _p0, gC, LA, [0, 10, -10, 20, -20], otherP, maxjump=None)
                            if qpre is None: continue
                            upd = [(appr[0][0] + np.array([0, 0, 0.05 * (1 - u)]), Rb) for u in np.linspace(0, 1, 15)]
                            qsU0, phU0, fU0 = cart_cf(PEEL, upd, qpre, ph0, gC, LA, [0, 10, -10, 20, -20], "a3 lift:下降到進場起點", otherP)
                            if fU0 is not None: continue
                            qsD, phD, f_ = cart_cf(PEEL, appr, qsU0[-1], phU0[-1], gC, LA, [0, 10, -10, 20, -20], "a3 lift:指尖伸進外緣下方", otherP)
                            if f_ is None:
                                best = (gap, ins, phs); qsD = qsU0 + qsD; break
                        if best: break
                    if best: break
                if best: break
            if best: break
        lift_ok = best is not None
        if not lift_ok:
            FAIL.append("(a) lift:外緣角落下方找不到可無碰撞進場的指尖姿態(可 IK 且無碰撞的姿態 %d 個;有 IK 解但碰撞中最好的:%s)" % (tried, BESTREJ[0])); qpre = READY[PEEL]; qsD = []
        else:
            P("  lift:蓋子先 kinematic 開到 %.0f°;指軸在板底下 %.1fmm、伸入外緣 %.0fmm、指軸繞邊切線 %d°;指頭離板底 %.1fmm"
              % (a.ajar, (best[0] - 0.0015) * 1e3, best[1] * 1e3, best[2], own_clear(qsD[-1])))
        add("a1 到預備點(壓的手 / 掀的手)", 2.5, **{qk(PRESS): qPpre, qk(PEEL): qpre if qpre is not None else READY[PEEL]})
        add("a2 壓的手下降壓住 %s" % FRONT, 1.2, **{qk(PRESS): qsP})
        add("a2b 後蓋 kinematic 開到 %.0f°(非手動)" % a.ajar, 0.8, lids={BACK: a.ajar})
        add("a3 指尖伸到外緣下方", 1.5, **{qk(PEEL): qsD if qsD else [qpre]})
        start_q, start_ph, start_deg = (qsD[-1], phD[-1], a.ajar) if qsD else (None, 0, a.ajar)
    if lift_ok:
        # 手跟著蓋子轉到 lid_mid(剛性)
        T0w = lidT_loc(start_deg)
        Tt0 = fk_tcp(PEEL, start_q)
        degs = np.linspace(start_deg, a.lid_mid, 40)
        path = []; lseq = []
        for d in degs:
            Tr = lidT_loc(d) @ np.linalg.inv(T0w)
            path.append((Tr[:3, :3] @ Tt0[:3, 3] + Tr[:3, 3], Tr[:3, :3] @ Tt0[:3, :3])); lseq.append(dict(L0, **{BACK: float(d)}))
        if a.lid_mode == "corner": add("a3 合指", 0.5, **{gk(PEEL): q_for_gap(CLOSE_GAP)}); gC = q_for_gap(CLOSE_GAP)
        qsL, phL, fL = cart_cf(PEEL, path, start_q, start_ph, gC, lseq, [0, 5, -5, 10, -10, 15, -15, 20, -20], "a4 掀 %s %.0f→%.0f°" % (BACK, start_deg, a.lid_mid), otherP)
        nL = len(qsL); reached = degs[nL - 1] if nL else start_deg
        if fL is not None: FAIL.append("(a) 後蓋只掀到 %.0f°" % reached)
        if nL:
            add("a4 掀 %s → %.0f°(壓的手壓住 %s)" % (BACK, reached, FRONT), 3.0 * nL / len(degs), **{qk(PEEL): qsL}, lids=lseq[:nL])
            # 放手:沿 +外緣方向退 30mm,再往上 60mm
            Tl = fk_tcp(PEEL, qsL[-1]); Tr = lidT_loc(reached) @ np.linalg.inv(T0w); enR = Tr[:3, :3] @ enA if a.lid_mode in ("lift", "pinch") else Tr[:3, :3] @ en_w
            L_r = dict(L0, **{BACK: float(reached)})
            if a.lid_mode in ("corner", "pinch"): add("a5 開指", 0.4, **{gk(PEEL): q_for_gap(10.0) if a.lid_mode == "corner" else gOpen})
            back = [(Tl[:3, 3] + enR * 0.03 * u, Tl[:3, :3]) for u in np.linspace(0, 1, 20)]     # 只沿外緣外向退 30mm,之後關節內插回 READY(也有碰撞檢查)
            qsB, phB, fB = cart_cf(PEEL, back, qsL[-1], phL[-1], {"lift": gC, "pinch": gOpen, "corner": q_for_gap(10.0)}[a.lid_mode], L_r, PH_ALL, "a5 掀的手退開", otherP)
            if fB is not None: FAIL.append("(a) 退開中斷")
            if qsB: add("a5 掀的手退開(放手,兩段式)", 1.0, **{qk(PEEL): qsB})
    add("a6 兩手回 READY", 2.0, qL=READY["left"], qR=READY["right"], gL=0.0, gR=0.0)
    add("a7 後蓋 kinematic 續轉到 180°(兩段式第二段)", 1.0, lids={BACK: 180.0})

else:
    add("(a) 略過:上蓋直接 kinematic 開到 180°", 1.0, lids=dict(fyp=180.0, fyn=180.0))
    FRONT = FRONT
if a.only != "a":
    P("\n=== (b) 開其餘的蓋 → 右手掀抓取點 #1(fx_open=%d)" % a.fx_open)
    add("b0 前蓋 %s 開到 %.0f°" % (FRONT, a.open_deg), 1.0, lids={FRONT: a.open_deg, BACK: a.open_deg})
    if a.fx_open: add("b0 下蓋 fx 開到 %.0f°" % a.open_deg, 1.2, lids=dict(fxp=a.open_deg, fxn=a.open_deg))
    LB_ = dict(st_["lids"])
    H = "right"; otherH = pts_of("left", READY["left"], 0.0)
    g1 = RJ["grasp"][str(a.grasp)]; so = np.array(g1["so"]); av = np.array(g1["a"])
    Rg_loc = np.column_stack([av, so, np.cross(av, so)]); Rg = TB[:3, :3] @ Rg_loc
    pg = (TB @ np.r_[np.array(g1["p"]) * 1e-3, 1])[:3]
    PSB = sorted(set([0.0] + [float(x) for x in np.arange(5, a.psi + 0.1, 5)] + [-float(x) for x in np.arange(5, a.psi + 0.1, 5)]), key=abs)
    P("  #%d 世界 %s mm;ψ 允許 ±%.0f°" % (a.grasp, (pg * 1e3).round(1).tolist(), a.psi))
    qpre, phpre = ik_cf(H, pg + np.array([0, 0, 0.06]), Rg, READY[H], 0, gOpen, LB_, PH_WRAP, otherH, maxjump=None, psis=PSB)
    if qpre is None: FAIL.append("(b) 預備點無碰撞 IK 失敗")
    else:
        add("b1 右手到 #1 上方 60mm、開指 21mm", 2.5, qR=qpre, gR=gOpen)
        dn = [(pg + np.array([0, 0, 0.06 * (1 - u)]), Rg) for u in np.linspace(0, 1, 40)]
        qsD, phD, f4 = cart_cf(H, dn, qpre, phpre, gOpen, LB_, PH_WRAP, "b2 下降到 #1", otherH, psis=PSB)
        if f4 is not None: FAIL.append("(b) 下降中斷")
        add("b2 下降到 #1", 1.5, qR=qsD)
        add("b3 合指到 4.5mm", 0.5, gR=gClose)
        HY, HZ = -71.5e-3, 106e-3; Rarc = a.arc_R * 1e-3
        gp = np.array(g1["p"]) * 1e-3
        up = [(pg + np.array([0, 0, 0.03 * u]), Rg) for u in np.linspace(0, 1, 15)]
        qsU, phU, f5 = cart_cf(H, up, qsD[-1] if qsD else qpre, phD[-1] if phD else phpre, gClose, LB_, PH_WRAP, "b4 抬 30mm", otherH, psis=PSB)
        add("b4 抬 30mm", 1.0, qR=qsU)
        gl = gp + np.array([0, 0, 0.03]); th0 = math.atan2(gl[2] - HZ, gl[1] - HY); r0 = math.hypot(gl[1] - HY, gl[2] - HZ)
        # 半徑由 r0 縮到 Rarc(沿徑向往鉸點收 → 布只會鬆不會拉),再沿 R=60 弧走到 θ_end,最後垂直抬到 z ≥ 牆頂 + 40
        TH_END = math.radians(100.0); Z_END = meta["wall_top_y"] + 0.040 + 0.002
        pts = []
        for u in np.linspace(0, 1, 12)[1:]:
            r = r0 + (Rarc - r0) * u; pts.append((np.array([gl[0], HY + r * math.cos(th0), HZ + r * math.sin(th0)]), 0.0))
        for t in np.linspace(th0, TH_END, 50)[1:]:
            pts.append((np.array([gl[0], HY + Rarc * math.cos(t), HZ + Rarc * math.sin(t)]), t - th0))
        zl = pts[-1][0][2]
        for z in np.linspace(zl, max(zl, Z_END), 8)[1:]:
            pts.append((np.array([gl[0], pts[-1][0][1], z]), TH_END - th0))
        arcP = [((TB @ np.r_[p_, 1])[:3], TB[:3, :3] @ rot_axis([1, 0, 0], math.degrees(dt)) @ Rg_loc) for p_, dt in pts]
        P("  弧線:鉸點 (y %.1f, z %.1f) mm 局部;收半徑 %.0f→%.0f mm;θ %.0f→%.0f°;終點局部 %s mm(牆頂 %.1f + 40)"
          % (HY * 1e3, HZ * 1e3, r0 * 1e3, Rarc * 1e3, math.degrees(th0), math.degrees(TH_END), (pts[-1][0] * 1e3).round(1).tolist(), meta["wall_top_y"] * 1e3))
        qsC, phC, f6 = cart_cf(H, arcP, qsU[-1] if qsU else (qsD[-1] if qsD else qpre), phU[-1] if phU else 0, gClose, LB_, PH_WRAP, "b5 收半徑 + 弧線 + 抬高", otherH, psis=PSB)
        if f6 is not None: FAIL.append("(b) 弧線中斷於 %d/%d" % (f6, len(arcP)))
        if qsC: add("b5 收半徑 + 沿 R60 弧線掀 + 抬高", 4.5 * len(qsC) / len(arcP), qR=qsC)
        add("b6 停", 0.7)

# ── 碰撞(幾何)────────────────────────────────────────────
P("\n=== 碰撞檢查(幾何:手臂 collision mesh 取樣點 vs 紙箱 Cube 有號距離;兩臂點對點;桌面)")
PT = {}
def frame_check(qL, qR, gL, gR, lids, contact):
    res = {}; W = {}
    for side, q6, g in (("left", qL, gL), ("right", qR, gR)):
        B = body_fk(side, np.asarray(q6), g, MIM * g); W[side] = {}
        for b, T in B.items():
            if b in PTS: W[side][b] = (T @ np.c_[PTS[b], np.ones(len(PTS[b]))].T).T[:, :3]
    for side in ("left", "right"):
        allp = np.vstack(list(W[side].values()))
        res["table_" + side] = (allp[:, 2].min() - TABLE_Z) * 1e3
        for o in OBB:
            T = lid_T(o["body"], lids[o["body"]]) if o["body"] != "base" else np.eye(4)
            for b, pts in W[side].items():
                dv = sdist(pts, o, T); jmin = int(np.argmin(dv)); d = dv[jmin] * 1e3
                fing = ("gripper_" in b or "carriage_" in b)
                key = "box_" + side          # v2:不再排除任何接觸,全部算
                if key not in res or d < res[key][0]: res[key] = (d, o["name"], b.rsplit("/", 1)[-1]); PT[key] = (pts[jmin] * 1e3).round(0).tolist()
    nl = [b for b in W["left"] for _ in range(len(W["left"][b]))]; nr = [b for b in W["right"] for _ in range(len(W["right"][b]))]
    pl = np.vstack(list(W["left"].values())); pr = np.vstack(list(W["right"].values()))
    dd, ii = cKDTree(pl).query(pr, k=1); j = int(np.argmin(dd))
    res["arm_arm"] = (dd[j] * 1e3, nl[ii[j]].rsplit("follower_", 1)[1], nr[j].rsplit("follower_", 1)[1])
    return res
def nearest_pair(qL, qR, gL, gR):
    W = {}
    for side, q6, g in (("left", qL, gL), ("right", qR, gR)):
        B = body_fk(side, np.asarray(q6), g, MIM * g)
        for b, T in B.items():
            if b in PTS: W[b] = (T @ np.c_[PTS[b], np.ones(len(PTS[b]))].T).T[:, :3]
    best = None
    for bl in [b for b in W if "follower_left_" in b]:
        tr = cKDTree(W[bl])
        for br in [b for b in W if "follower_right_" in b]:
            d = tr.query(W[br], k=1)[0].min() * 1e3
            if best is None or d < best[0]: best = (d, bl, br)
    return best, {b: (W[b].min(0) * 1e3).round(0).tolist() + (W[b].max(0) * 1e3).round(0).tolist() for b in W}
_np, _bb = nearest_pair(SEG[0]["qL"][0], SEG[0]["qR"][0], SEG[0]["gL"][0], SEG[0]["gR"][0])
P("  home 兩臂最近:%.1f mm %s ↔ %s" % _np)
for b, v in _bb.items(): P("    bbox %s %s" % (b.rsplit("/", 1)[-1], v))
T_ALL = []; t = 0.0
summary = []
for s in SEG:
    worst = {}
    for i in range(s["n"]):
        r = frame_check(s["qL"][i], s["qR"][i], s["gL"][i], s["gR"][i], s["lids"][i], s["contact"])
        T_ALL.append(r)
        for k, v in r.items():
            vv = v[0] if isinstance(v, tuple) else v
            if k not in worst or vv < (worst[k][0] if isinstance(worst[k], tuple) else worst[k]): worst[k] = v
    dur = s["n"] / FPS
    f = lambda k: ("%.1f(%s↔%s)" % worst[k] if isinstance(worst.get(k), tuple) else ("%.1f" % worst[k] if k in worst else "-"))
    col = [k for k in ("box_left", "box_right", "arm_arm", "table_left", "table_right") if k in worst and (worst[k][0] if isinstance(worst[k], tuple) else worst[k]) < (10.0 if k == "arm_arm" else -0.5)]
    P("  [%5.1f–%5.1fs] %-34s 左↔箱 %s | 右↔箱 %s | 兩臂 %s | 桌 L%.0f R%.0f | 預期接觸 L %s R %s %s"
      % (t, t + dur, s["name"], f("box_left"), f("box_right"), ("%.1f(%s↔%s)" % worst["arm_arm"]), worst["table_left"], worst["table_right"],
         f("intended_left"), f("intended_right"), "★ 穿入:" + ",".join(col) if col else "OK"))
    if col: P("      最深點(世界 mm):" + "; ".join("%s %s" % (k, PT.get(k)) for k in col if k in PT))
    summary.append(dict(name=s["name"], t0=t, t1=t + dur, worst={k: v for k, v in worst.items()}, collide=col)); t += dur
P("  (數字 = 最小有號距離 mm,負 = 穿入;驗收:穿入 > 0.5mm 或兩臂 < 10mm 或桌面 < 0 = 碰撞)")
P("★ 總結:%s" % ("全程無碰撞" if not any(sg["collide"] for sg in summary) else "有碰撞段:" + ", ".join(sg["name"] for sg in summary if sg["collide"])))
for f_ in FAIL: P("  ⚠ " + f_)
json.dump(dict(segments=summary, fail=FAIL, gap=dict(G0=G0, GK=GK, mimic=MIM)), open(os.path.join(HERE, "data", "peel_traj_%s.json" % TAG), "w"), indent=1, default=lambda o: float(o) if hasattr(o, "__float__") else str(o))
np.savez(os.path.join(HERE, "data", "peel_traj_%s.npz" % TAG), qL=np.array([q for s in SEG for q in s["qL"]]), qR=np.array([q for s in SEG for q in s["qR"]]),
         gL=np.array([g for s in SEG for g in s["gL"]]), gR=np.array([g for s in SEG for g in s["gR"]]),
         lids=np.array([[l[k] for k in ("fxp", "fxn", "fyp", "fyn")] for s in SEG for l in s["lids"]]), fps=FPS)

# ── 播放:set_joint_positions + 錄影 ──────────────────────
from isaacsim.core.api import World
from isaacsim.core.prims import Articulation, RigidPrim
for p in Usd.PrimRange(st.GetPrimAtPath(R0)):
    if p.HasAPI(UsdPhysics.CollisionAPI) and "follower_" in str(p.GetPath()):
        UsdPhysics.CollisionAPI(p).CreateCollisionEnabledAttr().Set(False)
P("播放時手臂 collision 關掉(碰撞只用上面的幾何檢查;避免 PhysX 把 teleport 的手臂推開)")
world = World(physics_dt=1 / 120.0, rendering_dt=1 / FPS, stage_units_in_meters=1.0)
cams = []
if not a.no_video:
    from isaacsim.sensors.camera import Camera
    from isaacsim.core.utils.viewports import set_camera_view
    import imageio
    from PIL import Image, ImageDraw, ImageFont
    for i, (eye, tgt) in enumerate((((-0.95, 0.0, 0.62), (0.0, 0.0, 0.16)), ((0.55, -0.55, 0.75), (0.0, 0.05, 0.12)))):
        c = Camera(prim_path="/World/dry_cam%d" % i, resolution=(960, 540), frequency=FPS); cams.append((c, eye, tgt))
world.reset()
ART = Articulation(prim_paths_expr="/World/stationary_ai", name="arms"); ART.initialize()
L6 = RigidPrim(prim_paths_expr=R0 + "/follower_*_link_6", name="l6"); L6.initialize()
lid_order = ["fxp", "fxn", "fyp", "fyn"]; l6_order = [str(p).split("follower_")[1].split("_")[0] for p in L6.prim_paths]
dof = list(ART.dof_names)
P("\nArticulation DOF %d:%s" % (len(dof), dof))
idx = {side: [dof.index("follower_%s_joint_%d" % (side, k)) for k in range(6)] for side in ("left", "right")}
cidx = {side: (dof.index("follower_%s_left_carriage_joint" % side), dof.index("follower_%s_right_carriage_joint" % side)) for side in ("left", "right")}
LT0, LOP, PAR = {}, {}, {}
for nm in lid_order:
    pr = st.GetPrimAtPath(BOX + "/" + nm); LT0[nm] = Wm(BOX + "/" + nm)
    PAR[nm] = np.array(UsdGeom.Xformable(pr.GetParent()).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T
    xf = UsdGeom.Xformable(pr); xf.ClearXformOpOrder(); LOP[nm] = xf.AddTransformOp()
    LOP[nm].Set(Gf.Matrix4d(*(np.linalg.inv(PAR[nm]) @ LT0[nm]).T.flatten().tolist()))
for c, eye, tgt in cams:
    c.initialize(); set_camera_view(eye=np.array(eye), target=np.array(tgt), camera_prim_path=c.prim_path)
    cp = UsdGeom.Camera(st.GetPrimAtPath(c.prim_path)); cp.GetFocalLengthAttr().Set(18.0 if c.prim_path.endswith("0") else 20.0)
    cp.GetHorizontalApertureAttr().Set(20.955); cp.GetVerticalApertureAttr().Set(20.955 * 540 / 960); cp.GetClippingRangeAttr().Set(Gf.Vec2f(0.01, 100.0))
EN = {"a0": "a0 home -> READY", "a1": "a1 to pre-poses", "a2": "a2 R presses front lid", "a2b": "a2b back lid kinematic ajar (not by hand)",
      "a3": "a3 L fingers slide onto back-lid corner edge", "a3b": "a3b L pinch 5mm", "a4": "a4 L lifts back lid (R holds front)",
      "a5": "a5 L release / retreat", "a6": "a6 both to READY", "a7": "a7 back lid continues kinematic to 180",
      "b0": "b0 lids open (kinematic)", "b1": "b1 R to 60mm above grasp #1", "b2": "b2 R descend to #1", "b3": "b3 R close to 4.5mm",
      "b4": "b4 R lift 30mm", "b5": "b5 R radius-in + R60 peel arc + raise", "b6": "b6 hold"}
try: FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 17)
except Exception: FONT = None
wr = imageio.get_writer(OUT, fps=FPS, codec="libx264", quality=8, pixelformat="yuv420p") if cams else None
def apply(qL, qR, gL, gR, lids):
    J = np.array(ART.get_joint_positions(), float)[0]
    J[idx["left"]] = qL; J[idx["right"]] = qR
    J[cidx["left"][0]] = gL; J[cidx["left"][1]] = MIM * gL; J[cidx["right"][0]] = gR; J[cidx["right"][1]] = MIM * gR
    ART.set_joint_positions(J[None]); ART.set_joint_position_targets(J[None]); ART.set_joint_velocities(np.zeros_like(J)[None])
    for nm in lid_order:
        T = np.linalg.inv(PAR[nm]) @ lid_T(nm, lids[nm]) @ LT0[nm]
        LOP[nm].Set(Gf.Matrix4d(*T.T.flatten().tolist()))
# 暖機
s0 = SEG[0]; apply(s0["qL"][0], s0["qR"][0], s0["gL"][0], s0["gR"][0], s0["lids"][0])
for _ in range(15): world.step(render=bool(cams))
k = 0; t = 0.0; maxdev = 0.0; maxjerr = 0.0
for si, s in enumerate(SEG):
    sdev = 0.0
    for i in range(s["n"]):
        apply(s["qL"][i], s["qR"][i], s["gL"][i], s["gR"][i], s["lids"][i])
        world.step(render=bool(cams))
        Jr = np.array(ART.get_joint_positions(), float)[0]
        maxjerr = max(maxjerr, np.abs(Jr[idx["left"]] - s["qL"][i]).max(), np.abs(Jr[idx["right"]] - s["qR"][i]).max())
        p6, q6 = [np.array(x, float) for x in L6.get_world_poses()]
        for j, side in enumerate(l6_order):
            fk = ARMS[side]["base_T"] @ RM.fk_np(ARMS[side], s["qL"][i] if side == "left" else s["qR"][i])["link_6"]
            maxdev = max(maxdev, np.linalg.norm(fk[:3, 3] - p6[j]) * 1e3); sdev = max(sdev, np.linalg.norm(fk[:3, 3] - p6[j]) * 1e3)
        if cams:
            ims = []
            for c, _e, _t in cams:
                rgb = c.get_rgba()
                ims.append(np.asarray(rgb)[:, :, :3] if rgb is not None and rgb.size else np.zeros((540, 960, 3), np.uint8))
            im = Image.fromarray(np.concatenate(ims, 1)); d = ImageDraw.Draw(im)
            r = T_ALL[k]
            txt = "t=%5.2fs  %s\nbox clearance L %.0f / R %.0f mm   arm-arm %.0f mm   gripL %.1f gripR %.1f mm" % (
                t, EN.get(s["name"].split()[0], s["name"].split()[0]), r["box_left"][0], r["box_right"][0], r["arm_arm"][0],
                G0 + GK * s["gL"][i], G0 + GK * s["gR"][i])
            d.rectangle([0, 0, 760, 44], fill=(0, 0, 0)); d.text((6, 3), txt, fill=(255, 255, 255), font=FONT)
            if wr: wr.append_data(np.asarray(im))
        k += 1; t += 1 / FPS
    if sdev > 1.0: P("  播放 %s:link_6 讀回偏差 %.1f mm" % (s["name"], sdev))
if wr: wr.close()
P("播放 %d 格(%.1f s);PhysX 讀回 vs 指令:關節最大差 %.3f°、link_6 位置 vs numpy FK 最大差 %.2f mm" % (k, t, math.degrees(maxjerr), maxdev))
if cams: P("影片 → %s" % OUT)
app.close()
