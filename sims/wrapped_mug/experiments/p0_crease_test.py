# -*- coding: utf-8 -*-
"""P0 go/no-go: restBendAngles 到底有沒有被 solver 讀?

一條膜條左端釘在 kinematic 錨點上,其餘懸空受重力下垂。
只把正中央那一對相鄰三角形的靜止二面角設成 TARGET_DEG,其餘留 flatDefault。

  NO_ANCHOR : 綁定沒抓到頂點 -> 測試本身無效,先修綁定
  NO_SIM    : 頂點完全沒位移 -> 模擬沒跑或讀不回來
  FAIL      : 有下垂,但中央邊角度跟其他邊沒兩樣 -> restBendAngles 被忽略
  PASS      : 有下垂,且中央邊明顯尖折 -> 折痕可用

用法:  /isaac-sim/python.sh p0_crease_test.py
"""
import json, math, os, sys

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": True})

import carb
from pxr import UsdGeom, UsdPhysics, Gf, Sdf, Vt
import omni.usd
from isaacsim.core.api import SimulationContext

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wf_common as wf

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

N_CELLS, STRIP_L, STRIP_W = 8, 0.24, 0.036
TARGET_DEG = 90.0
STEPS, DT = 600, 1.0 / 240.0
YOUNGS, POISSON = 5.0e4, 0.45
THICKNESS, BEND_STIFF = 0.004, 1.15e3
LIN_DAMP, ELAS_DAMP, BEND_DAMP = 0.60, 0.30, 0.30
SOLVER_ITER, MASS = 64, 0.002
ANCHOR = 0.05

_LOG = []


def log(msg):
    line = f"[p0] {msg}"
    _LOG.append(line)
    print(line, flush=True)
    carb.log_warn(line)


log(f"runtime settings: {wf.enable_deformable_runtime()}")

omni.usd.get_context().new_stage()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.Xform.Define(stage, "/World")
wf.make_physics_scene(stage, steps_per_second=int(round(1.0 / DT)))

mat = wf.make_film_material(stage, "/World/filmMat", YOUNGS, POISSON, THICKNESS,
                            BEND_STIFF, 0.7, ELAS_DAMP, BEND_DAMP)

# 膜條:1 格寬,沿 X 切 N_CELLS 格。放在 z = 0.5 的空中。
pts, tris = wf.grid_mesh(N_CELLS, 1, STRIP_L, STRIP_W, z=0.5, origin=(0.0, -STRIP_W / 2.0))
mesh, ok, coll = wf.make_surface_deformable(
    stage, "/World/strip", pts, tris, mat, MASS,
    solver_iter=SOLVER_ITER, lin_damp=LIN_DAMP)
log(f"surface deformable applied={ok}  verts={len(pts)} tris={len(tris)}")

# 左端錨點:x=0 那一排頂點落在方塊內
anchor = UsdGeom.Cube.Define(stage, "/World/anchor")
anchor.CreateSizeAttr(ANCHOR)
UsdGeom.Xformable(anchor).AddTranslateOp().Set(Gf.Vec3d(0, 0, 0.5))
UsdPhysics.CollisionAPI.Apply(anchor.GetPrim())
UsdPhysics.RigidBodyAPI.Apply(anchor.GetPrim()).CreateKinematicEnabledAttr(True)
UsdGeom.Scope.Define(stage, "/World/attach")

sel = wf.verts_in_box(stage, "/World/strip", "/World/anchor", pad=0.004)
a_ok, n_vtx = wf.attach_verts_to_xform(stage, "/World/attach/anchor", "/World/strip",
                                       "/World/anchor", sel,
                                       filter_elements=wf.tris_touching(tris, sel))
log(f"attachment ok={a_ok} attached_vertices={n_vtx} idx={sel}")
wf.refresh_film_offsets(coll, 0.005, 0.001)

# 折線:只設正中央那一條橫邊
pairs = wf.interior_edge_pairs(tris)
row = N_CELLS + 1
# 橫邊 = 兩端點在同一個 x 欄(index 差剛好 row)
cross = [(tp, e) for tp, e in pairs if abs(e[1] - e[0]) == row]
cross.sort(key=lambda pe: pts[pe[1][0]][0])
mid_idx = len(cross) // 2
hinge_pair, hinge_edge = cross[mid_idx]

prim = mesh.GetPrim()
wf.set_attr(prim, "omniphysics:restBendAnglesDefault", "flatDefault")
wf.set_attr(prim, "omniphysics:restAdjTriPairs", Vt.Vec2iArray([Gf.Vec2i(*hinge_pair)]))
wf.set_attr(prim, "omniphysics:restBendAngles", Vt.FloatArray([TARGET_DEG]))
log(f"cross edges={len(cross)} hinge pair={hinge_pair} edge={hinge_edge} x={pts[hinge_edge[0]][0]:.3f}")
log(f"authored pairs={prim.GetAttribute('omniphysics:restAdjTriPairs').Get()} "
    f"angles={prim.GetAttribute('omniphysics:restBendAngles').Get()}")

sim = SimulationContext(physics_dt=DT, rendering_dt=DT, stage_units_in_meters=1.0)
pcx = sim.get_physics_context()
pcx.enable_gpu_dynamics(True)
pcx.set_broadphase_type("GPU")
pcx.set_solver_type("TGS")
sim.initialize_physics()
sim.play()
for _ in range(STEPS):
    sim.step(render=False)

after = list(mesh.GetPointsAttr().Get())
disp = max(math.dist(tuple(after[i]), tuple(pts[i])) for i in range(len(pts)))
anchor_disp = max(math.dist(tuple(after[i]), tuple(pts[i])) for i in (0, row))

angles = {}
for tp, e in cross:
    angles[round(pts[e[0]][0], 4)] = wf.dihedral_deg(after, tris, tp, e)
hx = round(pts[hinge_edge[0]][0], 4)
hinge_deg = angles[hx]
others = [abs(v) for k, v in angles.items() if k != hx]
mean_other = sum(others) / len(others) if others else 0.0
max_other = max(others) if others else 0.0

if n_vtx == 0:
    verdict = "NO_ANCHOR"
elif disp < 1e-4:
    verdict = "NO_SIM"
elif abs(hinge_deg) > 30.0 and abs(hinge_deg) > 2.0 * max(max_other, 1e-6):
    verdict = "PASS"
else:
    verdict = "FAIL"

result = {
    "isaac_version": open("/isaac-sim/VERSION").read().strip(),
    "surface_deformable_applied": bool(ok),
    "attachment_ok": bool(a_ok),
    "attached_vertex_count": n_vtx,
    "target_rest_bend_deg": TARGET_DEG,
    "max_vertex_displacement_m": round(disp, 6),
    "anchored_vertex_displacement_m": round(anchor_disp, 6),
    "hinge_x_m": hx,
    "hinge_dihedral_deg": round(hinge_deg, 3),
    "cross_edge_dihedrals_deg": {str(k): round(v, 3) for k, v in sorted(angles.items())},
    "mean_abs_other_deg": round(mean_other, 3),
    "max_abs_other_deg": round(max_other, 3),
    "steps": STEPS,
    "verdict": verdict,
}
log(f"attached={n_vtx} anchor_disp={anchor_disp:.5f} disp={disp:.5f} "
    f"hinge={hinge_deg:.2f} max_other={max_other:.2f} -> {verdict}")
result["log"] = _LOG
with open(os.path.join(OUT, "p0_result.json"), "w") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

sim.stop()
simulation_app.close()
os._exit(0 if verdict == "PASS" else 2)
