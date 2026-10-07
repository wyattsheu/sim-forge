#!/usr/bin/env python3
"""把彈塑性摺痕接到場景裡的四個摺痕關節,並驗證蓋子撐得住。

  /isaac-sim/python.sh run_crease.py --scene out/scene_mug.usd --steps 400
  /isaac-sim/python.sh run_crease.py --scene out/scene_mug.usd --steps 400 --no_crease   # 陰性對照

★ USD 只帶被動關節(±185°、無 drive)。彈塑性是**每個物理步**外加的關節力矩,
  沒有這支腳本,蓋子就會自己垂下來 —— --no_crease 就是拿來證明這件事的。
"""
import argparse, math
ap = argparse.ArgumentParser()
ap.add_argument("--scene", required=True)
ap.add_argument("--steps", type=int, default=400)
ap.add_argument("--no_crease", action="store_true", help="陰性對照:不施加摺痕力矩")
ap.add_argument("--drop", type=float, default=0.0, help="診斷:把杯子抬高這麼多公尺再放開")
ap.add_argument("--k", type=float, default=3.2); ap.add_argument("--my0", type=float, default=0.60)
ap.add_argument("--hh", type=float, default=0.85); ap.add_argument("--c", type=float, default=0.33)
ap.add_argument("--clip", type=float, default=3.0)
a = ap.parse_args()

from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import numpy as np, torch
from isaacsim.core.api import World
from isaacsim.core.prims import RigidPrim
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Gf
import omni.usd
from crease_physics import ElastoplasticCrease
P = lambda *x: print(*x, flush=True)

omni.usd.get_context().open_stage(a.scene)
world = World(stage_units_in_meters=1.0)
st = omni.usd.get_context().get_stage()
ps = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene")) \
     if st.GetPrimAtPath("/physicsScene") else None
if ps is None:                                    # ★ 原場景沒有 PhysicsScene
    sc = UsdPhysics.Scene.Define(st, "/physicsScene")
    ps = PhysxSchema.PhysxSceneAPI.Apply(sc.GetPrim())
ps.CreateEnableGPUDynamicsAttr(True); ps.CreateBroadphaseTypeAttr("GPU")
ps.CreateGpuFoundLostAggregatePairsCapacityAttr(8192)      # 手臂形狀多, 預設不夠(PhysX 會警告)
sc = UsdPhysics.Scene(st.GetPrimAtPath("/physicsScene"))
sc.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1)); sc.CreateGravityMagnitudeAttr(9.81)
P("重力: dir=%s mag=%s" % (sc.GetGravityDirectionAttr().Get(), sc.GetGravityMagnitudeAttr().Get()))
P("場景裡的 PhysicsScene:", [str(p.GetPath()) for p in st.Traverse() if p.GetTypeName()=="PhysicsScene"])

FL = ["fyp", "fyn", "fxp", "fxn"]
AX = {"fyp": np.array([1.0,0,0]), "fyn": np.array([1.0,0,0]),
      "fxp": np.array([0,1.0,0]), "fxn": np.array([0,1.0,0])}
VIEW = RigidPrim(prim_paths_expr="/World/Carton/f(yp|yn|xp|xn)")
MUG  = RigidPrim(prim_paths_expr="/World/Mug")
world.reset(); VIEW.initialize(); MUG.initialize()
ORDER = [p.rsplit("/",1)[-1] for p in VIEW.prim_paths]
P("蓋子順序:", ORDER)

def basis(nm):
    p = st.GetPrimAtPath("/World/Carton/" + nm)
    m = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    R = np.array([[m[i][j] for j in range(3)] for i in range(3)])
    return R[1] / np.linalg.norm(R[1])          # 局部 Y 軸在世界座標

Y0 = {f: basis(f) for f in ORDER}
prev = {f: 0.0 for f in ORDER}; turn = {f: 0.0 for f in ORDER}
def ang(nm):
    y0, yv, ax = Y0[nm], basis(nm), AX[nm]
    raw = math.degrees(math.atan2(float(np.dot(np.cross(y0, yv), ax)), float(np.dot(y0, yv))))
    d = raw - prev[nm]
    if d > 180: turn[nm] -= 360
    elif d < -180: turn[nm] += 360
    prev[nm] = raw
    return raw + turn[nm]

# ★ 力矩方向不要用推的 —— 開跑前先施一個小力矩量出每片蓋子的正負號。
#   手推那版符號反了, 摺痕變成「驅動」而不是「阻止」, 蓋子直接甩到 ±185 度的極限。
# ★ 先記錄「建檔時」的姿態 —— 校準/靜置會動到東西, 記在後面等於什麼都沒量(踩過)
if a.drop > 0:                       # ★ 決定性診斷:物理到底有沒有在跑
    pos, quat = MUG.get_world_poses()
    pos = np.asarray(pos).copy(); pos[0][2] += a.drop
    MUG.set_world_poses(positions=pos, orientations=np.asarray(quat))
    z_hi = float(MUG.get_world_poses()[0][0][2]); P("[落下測試] 抬到 z=%.4f" % z_hi)
    for i in range(120):
        world.step(render=False)
        if i in (5, 20, 60, 119):
            P("   step %3d  z=%.4f  v_z=%+.4f" % (i, float(MUG.get_world_poses()[0][0][2]),
                                                  float(np.asarray(MUG.get_linear_velocities())[0][2])))
    P("[落下測試] 落差 %.1f mm(抬了 %.1f mm)" % ((z_hi-float(MUG.get_world_poses()[0][0][2]))*1e3, a.drop*1e3))
A_BUILD = {f: ang(f) for f in ORDER}
Z_BUILD = float(MUG.get_world_poses()[0][0][2])
SGN = {f: 1.0 for f in ORDER}
for i, f in ([] if a.no_crease else list(enumerate(ORDER))):
    b4 = ang(f); TT = np.zeros((len(ORDER), 3), dtype=np.float32); TT[i] = AX[f] * 0.5
    for _ in range(10):
        VIEW.apply_forces_and_torques_at_pos(torques=TT.copy(), is_global=True); world.step(render=False)
    SGN[f] = 1.0 if (ang(f) - b4) > 0 else -1.0
    TT[:] = 0.0
    for _ in range(40): world.step(render=False)          # 讓它靜下來
if a.no_crease:
    for _ in range(4*50): world.step(render=False)          # 對照組跑同樣步數才可比
P("力矩符號校準:", SGN)
P("靜置漂移:蓋子 %s  杯 z %+.1f mm"
  % ({f: round(ang(f)-A_BUILD[f],1) for f in ORDER}, (float(MUG.get_world_poses()[0][0][2])-Z_BUILD)*1e3))
crease = ElastoplasticCrease(len(ORDER), "cpu", k=a.k, my0=a.my0, h=a.hh, c=a.c, clip=a.clip)
# ★ 蓋子是「已經被折開」的 → rest 初始化成目前角度, 否則彈性會把它拉回 0
for i,_ in enumerate(ORDER): crease.rest[i] = 0.0
A0 = {f: ang(f) for f in ORDER}
P("初始角度:", {f: round(A0[f],1) for f in ORDER})
mz0 = float(MUG.get_world_poses()[0][0][2])
T = np.zeros((len(ORDER), 3), dtype=np.float32)

for s in range(a.steps):
    q  = torch.tensor([math.radians(ang(f) - A0[f]) for f in ORDER], dtype=torch.float32)
    w  = np.asarray(VIEW.get_angular_velocities())
    qd = torch.tensor([float(np.dot(w[i], AX[f])) for i,f in enumerate(ORDER)], dtype=torch.float32)
    tau = crease.step(q, qd)
    T[:] = 0.0
    if not a.no_crease:
        for i,f in enumerate(ORDER): T[i] = AX[f] * float(tau[i]) * SGN[f]
        VIEW.apply_forces_and_torques_at_pos(torques=T.copy(), is_global=True)
    world.step(render=False)
    if s in (1, 5, 20):
        v = np.asarray(MUG.get_linear_velocities())[0]
        P("  [診斷] step %d 杯速度 z = %+.4f m/s" % (s, v[2]))
    if s % 100 == 0:
        P("  step %3d  角度變化 %s  杯 z %.4f" %
          (s, {f: round(ang(f)-A0[f],1) for f in ORDER}, float(MUG.get_world_poses()[0][0][2])))

d = {f: ang(f)-A0[f] for f in ORDER}
mz = float(MUG.get_world_poses()[0][0][2])
P("=== 結果 (%s) ===" % ("無摺痕/陰性對照" if a.no_crease else "有摺痕"))
P("  蓋子角度變化 (deg):", {f: round(v,1) for f,v in d.items()}, " 最大 %.1f"%max(abs(v) for v in d.values()))
P("  杯 z %.4f → %.4f  (位移 %.1f mm)" % (mz0, mz, (mz-mz0)*1000))
P("  質量讀回 %.4f kg" % float(UsdPhysics.MassAPI(st.GetPrimAtPath("/World/Mug")).GetMassAttr().Get()))
ok = max(abs(v) for v in d.values()) < 5.0
P("  判定:%s" % ("✅ 蓋子撐住(<5°)" if ok else "❌ 蓋子動了 %.1f°" % max(abs(v) for v in d.values())))
sim.close()
