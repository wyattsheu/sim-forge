#!/usr/bin/env python3
"""ui_path_check.py — 用「跟 UI 一模一樣」的方式按 Play,量箱子會不會陷、蓋子會不會倒。

和 scene_physics_check.py 的差別:那支用 isaacsim.core World(physics_dt=1/120,解算器用 Isaac 預設),
這支只做 open_stage → timeline.play() → app.update(),物理設定完全吃 USD 裡的 PhysicsScene,
所以 UI 會遇到的問題(例如預設 PhysicsScene 太弱、箱子陷進桌面)這裡也會重現。

  cd sim
  /isaac-sim/python.sh ui_path_check.py ../scene_final_ui.usd                    # 路線 A:drive 版
  /isaac-sim/python.sh ui_path_check.py ../scene_final.usd --crease_script       # 路線 B:原檔 + crease_hold_ui.py
  /isaac-sim/python.sh ui_path_check.py ../scene_final.usd                       # 陰性對照:原檔直接 Play
結果印在終端機,也寫到 <out>/ui_path_check.log。
"""
import argparse, os, sys, math
ap = argparse.ArgumentParser()
ap.add_argument("scene")
ap.add_argument("--secs", type=float, default=8.0)
ap.add_argument("--crease_script", action="store_true", help="Play 前先執行 crease_hold_ui.py(= UI 的 Script Editor 路線)")
ap.add_argument("--out", default="ui_check")
a = ap.parse_args()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.abspath(a.scene)
os.makedirs(a.out, exist_ok=True)
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import numpy as np, omni.usd, omni.timeline
from isaacsim.core.prims import RigidPrim
from pxr import UsdPhysics, PhysxSchema
LOG = open(os.path.join(a.out, "ui_path_check.log"), "w")
def P(*s):
    t = " ".join(str(x) for x in s); print(t, flush=True); LOG.write(t + "\n"); LOG.flush()
BOX = "/World/Packed/Box"
omni.usd.get_context().open_stage(SCENE)
for _ in range(30): sim.update()
st = omni.usd.get_context().get_stage()
P("檔案:", SCENE)
sc = [p for p in st.Traverse() if p.IsA(UsdPhysics.Scene)]
P("PhysicsScene:", [str(p.GetPath()) for p in sc] or "無(Play 時 Isaac 自動加預設的:60 Hz / posIter=1 / velIter=0)")
for p in sc:
    if p.HasAPI(PhysxSchema.PhysxSceneAPI):
        api = PhysxSchema.PhysxSceneAPI(p)
        P("  %s Hz / %s / posIter=%s / velIter=%s" % (api.GetTimeStepsPerSecondAttr().Get(), api.GetSolverTypeAttr().Get(),
          api.GetMinPositionIterationCountAttr().Get(), api.GetMinVelocityIterationCountAttr().Get()))
for n in ("fxp", "fxn", "fyp", "fyn"):
    d = UsdPhysics.DriveAPI.Get(st.GetPrimAtPath(BOX + "/crease_" + n), "angular")
    P("crease_%s drive: %s" % (n, "stiffness=%.3g damping=%.3g" % (d.GetStiffnessAttr().Get(), d.GetDampingAttr().Get())
                               if d and d.GetStiffnessAttr() else "無"))
if a.crease_script:
    _p = os.path.join(HERE, "crease_hold_ui.py")
    exec(compile(open(_p).read(), _p, "exec"), globals())
    P("★ 已執行 crease_hold_ui.py(摺痕力矩 + 解算器修正)")
tl = omni.timeline.get_timeline_interface(); tl.play()
for _ in range(5): sim.update()
LIDS = RigidPrim(prim_paths_expr=BOX + "/f[xy][pn]", name="chk_lids"); LIDS.initialize()
BASE = RigidPrim(prim_paths_expr=BOX + "/base", name="chk_base"); BASE.initialize()
order = [str(p).rsplit("/", 1)[-1] for p in LIDS.prim_paths]
def qmul(a_, b_):
    w1, x1, y1, z1 = a_; w2, x2, y2, z2 = b_
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2,
                     w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])
def qconj(q): return np.array([q[0], -q[1], -q[2], -q[3]])
_, q0L = [np.array(x, float) for x in LIDS.get_world_poses()]
p0B, q0B = [np.array(x, float)[0] for x in BASE.get_world_poses()]
REL0 = [qmul(qconj(q0B), q0L[i]) for i in range(len(order))]
def lid_deg():
    _, qL = [np.array(x, float) for x in LIDS.get_world_poses()]
    _, qB = [np.array(x, float)[0] for x in BASE.get_world_poses()]
    out = []
    for i in range(len(order)):
        rr = qmul(qconj(REL0[i]), qmul(qconj(qB), qL[i]))
        if rr[0] < 0: rr = -rr
        out.append(math.degrees(2*math.atan2(rr[1], rr[0])))
    return np.array(out)
mx_lid, mx_dz = np.zeros(len(order)), 0.0
for k in range(int(a.secs*60)):
    sim.update()
    pB = np.array(BASE.get_world_poses()[0], float)[0]; d = (pB - p0B)*1e3; L_ = lid_deg()
    mx_lid = np.maximum(mx_lid, np.abs(L_)); mx_dz = max(mx_dz, abs(d[2]))
    if k % 60 == 0:
        P("t~%4.1fs 蓋角 %s | 箱底位移 (%+.2f, %+.2f, %+.2f) mm" % (k/60.0,
          " ".join("%s=%+6.2f" % (n, v) for n, v in zip(order, L_)), *d))
P("===== 結論 =====")
P("蓋角全程最大 %s" % " ".join("%s=%.2f°" % (n, v) for n, v in zip(order, mx_lid)))
P("箱底 z 位移全程最大 %.2f mm  →  %s" % (mx_dz, "OK" if mx_dz < 1.0 else "★ 箱子陷進桌面/掉落"))
P("蓋子  →  %s" % ("OK" if mx_lid.max() < 5.0 else "★ 蓋子倒下"))
LOG.close(); sim.close()
