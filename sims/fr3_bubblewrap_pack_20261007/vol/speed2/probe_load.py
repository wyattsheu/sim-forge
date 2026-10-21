#!/usr/bin/env python3
"""probe_load.py — 怎麼把 volume deformable 的 sim 節點設成任意狀態(續跑用)。小板 200x200x4、自碰撞 on。
  --mode usd     : reset 後寫 USD points(往上 50 mm + 彎)→ 看 USD 有沒有繼續更新 / 掉下來
  --mode tensor  : physics tensors volume deformable view set_simulation_nodal_positions
"""
import os, sys, argparse, numpy as np
ap = argparse.ArgumentParser(); ap.add_argument("--mode", default="tensor"); ap.add_argument("--front", default="numpy"); a = ap.parse_args()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from pxr import UsdGeom, PhysxSchema, Vt
import omni.usd
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
import volcommon as VC
world = World(physics_dt=1/120, rendering_dt=1/120); world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage(); UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene")); pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
VC.build_plate(st, "/World/plate", 0.2, 0.004, 0.001, "manual", nxy=10, nz=1, youngs=2e3, solver=32, self_coll=True, self_filter=0.001)
M = VC.Mesh(st, "/World/plate"); F = M.pts().copy()
world.reset()
for _ in range(3): sim.update()
TGT = F.copy(); TGT[:, 2] += 0.05 + 0.2 * (TGT[:, 0] - F[:, 0].min()) ** 2      # 抬高 50 mm、x 方向彎
def rep(tag):
    p = M.pts(); print("%-28s USD z min %.4f max %.4f | max|P-TGT| %.4f" % (tag, p[:, 2].min(), p[:, 2].max(), np.abs(p - TGT).max()), flush=True)
rep("after reset")
if a.mode == "usd":
    M.pa.Set(Vt.Vec3fArray.FromNumpy(TGT.astype(np.float32)))
    rep("after USD write")
else:
    import omni.physics.tensors as T
    for nm, sv in (("world.physics_sim_view", world.physics_sim_view), ("tensors.%s" % a.front, None)):
        if sv is None:
            sv = T.create_simulation_view(a.front); sv.set_subspace_roots("/")
        try:
            v = sv.create_volume_deformable_body_view("/World/plate")
            print(nm, "count", v.count, "max_sim_nodes", v.max_simulation_nodes_per_body, "max_col_nodes", v.max_collision_nodes_per_body, flush=True)
            if v.max_simulation_nodes_per_body:
                x = v.get_simulation_nodal_positions(); xn = x.numpy() if hasattr(x, "numpy") else np.asarray(x)
                print("  sim nodes shape", xn.shape, "vs USD", F.shape, "max diff to USD", np.abs(xn.reshape(-1, 3)[:len(F)] - M.pts()).max(), flush=True)
                idx = np.arange(v.count, dtype=np.uint32)
                v.set_simulation_nodal_positions(TGT.astype(np.float32).reshape(1, -1, 3), idx)
                v.set_simulation_nodal_velocities(np.zeros((1, len(F), 3), np.float32), idx)
                print("  set ok", flush=True); break
        except Exception as e:
            print(nm, "ERR", e, flush=True)
for k in range(30):
    world.step(render=False)
    if k in (0, 1, 5, 29): rep("step %d" % (k + 1))
sim.close()
