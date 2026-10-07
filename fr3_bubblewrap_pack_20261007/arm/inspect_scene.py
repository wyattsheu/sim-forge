#!/usr/bin/env python3
"""inspect_scene.py — 盤點雙臂場景(手臂/夾爪/紙箱/桌面),並對照 scene_final.usd 的紙箱擺放。
    /isaac-sim/python.sh inspect_scene.py
輸出 data/scene_inventory.json(reach.py / peel_traj.py 讀這個)。純 USD 讀取(不開物理)。"""
import os, json, math, functools, builtins
print = functools.partial(builtins.print, flush=True)
from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics, Gf

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = "/isaac-sim/test_scripts/mission0921/stationary_ai_carton_scene_flat.usd"
FINAL = "/isaac-sim/test_scripts/manip_fr3/handoff_20261002/scene_final.usd"
os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
st = Usd.Stage.Open(SCENE)
XC = UsdGeom.XformCache()
BB = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
def M(p):  # world 4x4 (row-vector convention → transpose to column)
    return np.array(XC.GetLocalToWorldTransform(st.GetPrimAtPath(p))).T
def pose_str(T):
    t = T[:3, 3] * 1e3
    R = T[:3, :3] / np.linalg.norm(T[:3, :3], axis=0)
    yaw = math.degrees(math.atan2(R[1, 0], R[0, 0]))
    return "(%.1f, %.1f, %.1f) mm yaw %.1f°" % (*t, yaw), t.tolist(), R.tolist()
def bbox(p, stage_bb=BB):
    r = stage_bb.ComputeWorldBound(st.GetPrimAtPath(p)).ComputeAlignedRange()
    return (np.array(r.GetMin()) * 1e3).round(1).tolist(), (np.array(r.GetMax()) * 1e3).round(1).tolist()

out = {"scene": SCENE, "arms": {}, "joints": []}
R = "/World/stationary_ai"
# joints
for p in st.Traverse():
    if not p.IsA(UsdPhysics.Joint): continue
    j = UsdPhysics.Joint(p)
    b0 = [str(x) for x in j.GetBody0Rel().GetTargets()]; b1 = [str(x) for x in j.GetBody1Rel().GetTargets()]
    d = {"path": str(p.GetPath()), "name": p.GetName(), "type": p.GetTypeName(),
         "body0": b0[0] if b0 else None, "body1": b1[0] if b1 else None,
         "lp0": list(j.GetLocalPos0Attr().Get() or (0, 0, 0)), "lr0": [j.GetLocalRot0Attr().Get().GetReal(), *j.GetLocalRot0Attr().Get().GetImaginary()],
         "lp1": list(j.GetLocalPos1Attr().Get() or (0, 0, 0)), "lr1": [j.GetLocalRot1Attr().Get().GetReal(), *j.GetLocalRot1Attr().Get().GetImaginary()]}
    if p.IsA(UsdPhysics.RevoluteJoint) or p.IsA(UsdPhysics.PrismaticJoint):
        jj = UsdPhysics.RevoluteJoint(p) if p.IsA(UsdPhysics.RevoluteJoint) else UsdPhysics.PrismaticJoint(p)
        d.update(axis=jj.GetAxisAttr().Get(), lo=jj.GetLowerLimitAttr().Get(), hi=jj.GetUpperLimitAttr().Get())
        for kind in ("angular", "linear"):
            dr = UsdPhysics.DriveAPI.Get(p, kind)
            if dr and dr.GetStiffnessAttr().Get() is not None:
                d["drive"] = dict(kind=kind, k=dr.GetStiffnessAttr().Get(), c=dr.GetDampingAttr().Get(), fmax=dr.GetMaxForceAttr().Get())
        mim = [a for a in p.GetAppliedSchemas() if "Mimic" in a]
        if mim: d["mimic"] = mim
    out["joints"].append(d)

print("=== 場景:", SCENE)
print("=== 關節(可動)")
for d in out["joints"]:
    if "axis" in d:
        u = "°" if "Revolute" in d["type"] else "m"
        print("  %-42s %-22s %s→%s 軸 %s 限制 [%s, %s]%s %s" % (d["name"], d["type"], os.path.basename(d["body0"] or "-"),
              os.path.basename(d["body1"] or "-"), d["axis"], d["lo"], d["hi"], u, d.get("drive", "") ))
print("=== 各手臂")
for side in ("left", "right"):
    base = "%s/follower_%s_base_link" % (R, side)
    s, t, Rm = pose_str(M(base))
    ee = "%s/follower_%s_ee_gripper_link" % (R, side)
    es, et, eR = pose_str(M(ee))
    gl, gr = "%s/follower_%s_gripper_left" % (R, side), "%s/follower_%s_gripper_right" % (R, side)
    bl, br = bbox(gl), bbox(gr)
    ee_prim = st.GetPrimAtPath(ee)
    out["arms"][side] = dict(base=base, base_pos_mm=t, base_R=Rm, ee=ee, ee_pos_mm=et, ee_R=eR,
                             finger_left_bbox=bl, finger_right_bbox=br,
                             ee_schemas=list(ee_prim.GetAppliedSchemas()))
    print("  %s 基座 %s  ee 連桿 %s" % (side, s, es))
    print("     ee R(世界) 欄=x,y,z:", np.round(np.array(eR), 3).tolist(), " ee schemas", list(ee_prim.GetAppliedSchemas()))
    print("     指 L bbox", bl, " 指 R bbox", br)
    for k in range(1, 7):
        lk = "%s/follower_%s_link_%d" % (R, side, k)
        print("     link_%d 原點 %s" % (k, pose_str(M(lk))[0]))
    print("     carriage_left %s / carriage_right %s" % (pose_str(M("%s/follower_%s_carriage_left" % (R, side)))[0],
                                                      pose_str(M("%s/follower_%s_carriage_right" % (R, side)))[0]))
# fixed joints that hold the ee link?
for d in out["joints"]:
    if d["body1"] and "ee_gripper" in d["body1"]: print("  ee 由", d["name"], "固定在", d["body0"])
# table
tb = bbox(R + "/tabletop_link")
print("=== 桌面 tabletop_link bbox", tb, " ⇒ 桌面 z = %.1f mm" % tb[1][2]); out["table_bbox"] = tb
# carton
c = "/World/Carton"
cs, ct, cR = pose_str(M(c)); cb = bbox(c)
print("=== 紙箱 /World/Carton xform %s  bbox %s  尺寸 %.0f x %.0f x %.0f mm" % (cs, cb, *(np.array(cb[1]) - np.array(cb[0]))))
for ch in ("base", "fxp", "fxn", "fyp", "fyn"):
    print("     %s bbox %s" % (ch, bbox(c + "/" + ch)))
for d in out["joints"]:
    if d["name"].startswith("crease"):
        print("     %s 限制 [%s, %s] lp0 %s" % (d["name"], d["lo"], d["hi"], np.round(np.array(d["lp0"]) * 1e3, 1).tolist()))
out["carton_scene"] = dict(pos_mm=ct, R=cR, bbox=cb)

# scene_final 對照
sf = Usd.Stage.Open(FINAL)
xc2 = UsdGeom.XformCache(); bb2 = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
P = "/World/Packed"
T2 = np.array(xc2.GetLocalToWorldTransform(sf.GetPrimAtPath(P))).T
s2 = pose_str(T2)
bx = bb2.ComputeWorldBound(sf.GetPrimAtPath(P + "/Box")).ComputeAlignedRange()
bmin, bmax = np.array(bx.GetMin()) * 1e3, np.array(bx.GetMax()) * 1e3
print("=== scene_final.usd /World/Packed %s  Box bbox %s ~ %s (尺寸 %.0f x %.0f x %.0f)" % (s2[0], bmin.round(1).tolist(), bmax.round(1).tolist(), *(bmax - bmin)))
for ch in ("crease_fxp", "crease_fyn"):
    pp = sf.GetPrimAtPath(P + "/Box/" + ch)
    if pp.IsValid():
        j = UsdPhysics.Joint(pp); b0 = str(j.GetBody0Rel().GetTargets()[0])
        Tb = np.array(xc2.GetLocalToWorldTransform(sf.GetPrimAtPath(b0))).T
        hw = Tb @ np.r_[np.array(j.GetLocalPos0Attr().Get()), 1]
        print("     %s 鉸鏈點 世界 %s mm" % (ch, (hw[:3] * 1e3).round(1).tolist()))
# compare with carton.usd local (meta): long 270 side along local x
out["carton_final"] = dict(pos_mm=s2[1], R=s2[2], bbox=[bmin.tolist(), bmax.tolist()])
same_ctr = np.allclose(((bmin + bmax) / 2)[:2], ((np.array(cb[0]) + np.array(cb[1])) / 2)[:2], atol=2)
print("=== 對照:中心 xy 一致 %s;原 /World/Carton 長邊沿 %s,scene_final 長邊沿 %s" % (
    same_ctr, "x" if (cb[1][0] - cb[0][0]) > (cb[1][1] - cb[0][1]) else "y", "x" if (bmax - bmin)[0] > (bmax - bmin)[1] else "y"))
json.dump(out, open(os.path.join(HERE, "data", "scene_inventory.json"), "w"), indent=1, default=str)
app.close()
