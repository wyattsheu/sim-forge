# -*- coding: utf-8 -*-
"""P0-b: 三條懸臂膜條同場比較,一次分清楚折痕到底能不能用。

同樣的幾何、同樣的材質、同樣的錨點,只差靜止組態的設法:

  C  control        restShapePoints = 平的, flatDefault            -> 只有重力下垂
  A  explicit       restAdjTriPairs = 全部橫邊, restBendAngles=45  -> 若有效會捲起來
  B  restShape      restShapePoints = V 形折疊, restShapeDefault   -> 若有效會折起來

判讀:
  C 幾乎不下垂        -> 連彎曲自由度都沒動,材質參數或 solver 設定有問題
  A 跟 C 沒差         -> restBendAngles / restAdjTriPairs 未實作
  B 跟 C 沒差         -> restShapeDefault 未實作
  A 或 B 明顯不同於 C -> 那條路可用

用法:  /isaac-sim/python.sh p0b_crease_matrix.py
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

NX, NY = 10, 2
LX, LY = 0.20, 0.04
FOLD_DEG = 45.0
STEPS, DT = 900, 1.0 / 240.0
YOUNGS, POISSON = 5.0e4, 0.45
THICKNESS, BEND_STIFF = 0.004, 1.15e3
LIN_DAMP, ELAS_DAMP, BEND_DAMP = 0.40, 0.30, 0.30
SOLVER_ITER, MASS = 64, 0.0012
ANCHOR = 0.05
Z0 = 0.6

_LOG = []


def log(msg):
    line = f"[p0b] {msg}"
    _LOG.append(line)
    print(line, flush=True)
    carb.log_warn(line)


log(f"runtime: {wf.enable_deformable_runtime()}")
omni.usd.get_context().new_stage()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.Xform.Define(stage, "/World")
UsdGeom.Scope.Define(stage, "/World/attach")
wf.make_physics_scene(stage, steps_per_second=int(round(1.0 / DT)))
mat = wf.make_film_material(stage, "/World/filmMat", YOUNGS, POISSON, THICKNESS,
                            BEND_STIFF, 0.7, ELAS_DAMP, BEND_DAMP)

row = NX + 1


def cross_edges(tris, pts):
    """沿 Y 方向的橫邊(折線候選),依 x 由小到大排序。"""
    out = [(tp, e) for tp, e in wf.interior_edge_pairs(tris)
           if abs(pts[e[0]][0] - pts[e[1]][0]) < 1e-9]
    out.sort(key=lambda pe: pts[pe[1][0]][0])
    return out


def fold_rest_points(pts, fold_x, deg):
    """把平面點集繞 x = fold_x 這條線折起 deg 度(等距,不拉伸)。"""
    out = []
    a = math.radians(deg)
    for p in pts:
        if p[0] <= fold_x:
            out.append(Gf.Vec3f(p[0], p[1], p[2]))
        else:
            d = p[0] - fold_x
            out.append(Gf.Vec3f(fold_x + d * math.cos(a), p[1], p[2] + d * math.sin(a)))
    return out


cases = {}
for k, (name, y_off) in enumerate({"C_control": 0.0, "A_explicit": 0.10, "B_restShape": 0.20}.items()):
    pts, tris = wf.grid_mesh(NX, NY, LX, LY, z=Z0, origin=(0.0, y_off))
    path = f"/World/{name}"
    mesh, ok, coll = wf.make_surface_deformable(stage, path, pts, tris, mat, MASS,
                                                solver_iter=SOLVER_ITER, lin_damp=LIN_DAMP)
    prim = mesh.GetPrim()
    ce = cross_edges(tris, pts)

    if name == "A_explicit":
        wf.set_attr(prim, "omniphysics:restBendAnglesDefault", "flatDefault")
        wf.set_attr(prim, "omniphysics:restAdjTriPairs",
                    Vt.Vec2iArray([Gf.Vec2i(int(tp[0]), int(tp[1])) for tp, _ in ce]))
        wf.set_attr(prim, "omniphysics:restBendAngles",
                    Vt.FloatArray([FOLD_DEG] * len(ce)))
    elif name == "B_restShape":
        rest = fold_rest_points(pts, LX * 0.5, FOLD_DEG)
        wf.set_attr(prim, "omniphysics:restShapePoints", Vt.Vec3fArray(rest))
        wf.set_attr(prim, "omniphysics:restBendAnglesDefault", "restShapeDefault")

    anchor_path = f"/World/anchor_{name}"
    ac = UsdGeom.Cube.Define(stage, anchor_path)
    ac.CreateSizeAttr(ANCHOR)
    UsdGeom.Xformable(ac).AddTranslateOp().Set(Gf.Vec3d(0.0, y_off + LY / 2.0, Z0))
    UsdPhysics.CollisionAPI.Apply(ac.GetPrim())
    UsdPhysics.RigidBodyAPI.Apply(ac.GetPrim()).CreateKinematicEnabledAttr(True)
    sel = wf.verts_in_box(stage, path, anchor_path, pad=0.002)
    a_ok, n_vtx = wf.attach_verts_to_xform(stage, f"/World/attach/{name}", path, anchor_path,
                                           sel, filter_elements=wf.tris_touching(tris, sel))
    wf.refresh_film_offsets(coll, 0.005, 0.001)

    cases[name] = dict(mesh=mesh, pts=pts, tris=tris, cross=ce, n_vtx=n_vtx)
    log(f"{name}: verts={len(pts)} tris={len(tris)} cross_edges={len(ce)} attached={n_vtx}")

sim = SimulationContext(physics_dt=DT, rendering_dt=DT, stage_units_in_meters=1.0)
pcx = sim.get_physics_context()
pcx.enable_gpu_dynamics(True)
pcx.set_broadphase_type("GPU")
pcx.set_solver_type("TGS")
sim.initialize_physics()
sim.play()
for _ in range(STEPS):
    sim.step(render=False)

summary = {}
for name, c in cases.items():
    after = list(c["mesh"].GetPointsAttr().Get())
    pts, tris = c["pts"], c["tris"]
    angs = [wf.dihedral_deg(after, tris, tp, e) for tp, e in c["cross"]]
    tip_drop = max(pts[i][2] - after[i][2] for i in range(len(pts)))
    total_turn = sum(abs(a) for a in angs)
    summary[name] = {
        "attached_vertices": c["n_vtx"],
        "tip_drop_m": round(tip_drop, 5),
        "cross_dihedrals_deg": [round(a, 2) for a in angs],
        "mean_abs_deg": round(sum(abs(a) for a in angs) / len(angs), 3),
        "total_turn_deg": round(total_turn, 2),
    }
    log(f"{name}: tip_drop={tip_drop:.4f} mean|dihedral|={summary[name]['mean_abs_deg']:.2f} "
        f"total_turn={total_turn:.1f}")

ctrl = summary["C_control"]["total_turn_deg"]
verdict = {
    "bending_dof_live": summary["C_control"]["tip_drop_m"] > 0.005,
    "explicit_rest_bend_angles_works": summary["A_explicit"]["total_turn_deg"] > max(2.0 * ctrl, 30.0),
    "rest_shape_default_works": summary["B_restShape"]["total_turn_deg"] > max(2.0 * ctrl, 30.0),
}
log(f"VERDICT {verdict}")

out = {"isaac_version": open("/isaac-sim/VERSION").read().strip(),
       "fold_deg": FOLD_DEG, "steps": STEPS, "cases": summary,
       "verdict": verdict, "log": _LOG}
with open(os.path.join(OUT, "p0b_result.json"), "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)

sim.stop()
simulation_app.close()
os._exit(0)
