# -*- coding: utf-8 -*-
"""隔離測試:馬克杯單獨掉到地板上,量它停在哪 -> 判定碰撞體到底有沒有效。"""
import os, sys, json
from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": True})
import carb
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Gf, Sdf
import omni.usd
from isaacsim.core.api import SimulationContext
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import wf_common as wf
from params import MUG

wf.enable_deformable_runtime()
omni.usd.get_context().new_stage()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(stage, 1.0); UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.Xform.Define(stage, "/World")
wf.make_physics_scene(stage, steps_per_second=240)
pl = UsdGeom.Plane.Define(stage, "/World/ground"); pl.CreateAxisAttr("Z")
UsdPhysics.CollisionAPI.Apply(pl.GetPrim())

# 對照組:一顆普通方塊,用來判定地板本身有沒有效
cb = UsdGeom.Cube.Define(stage, "/World/ctrl_cube"); cb.CreateSizeAttr(0.06)
cx = UsdGeom.Xformable(cb); cx.AddTranslateOp().Set(Gf.Vec3d(-0.35, 0, 0.25)); cx.AddOrientOp().Set(Gf.Quatf(1,0,0,0))
UsdPhysics.CollisionAPI.Apply(cb.GetPrim()); UsdPhysics.RigidBodyAPI.Apply(cb.GetPrim())
UsdPhysics.MassAPI.Apply(cb.GetPrim()).CreateMassAttr(0.3)

out = {}
VARIANTS = ("sdf", "baked_sdf", "flat_sdf")
for approx in VARIANTS:
    root = f"/World/m_{approx}"
    x = UsdGeom.Xform.Define(stage, root)
    xf = UsdGeom.Xformable(x); tr = xf.AddTranslateOp()
    i = VARIANTS.index(approx)
    tr.Set(Gf.Vec3d(i * 0.3, 0, 0.25))
    xf.AddOrientOp().Set(Gf.Quatf(1, 0, 0, 0))
    UsdPhysics.RigidBodyAPI.Apply(x.GetPrim())
    UsdPhysics.MassAPI.Apply(x.GetPrim()).CreateMassAttr(MUG["mass"])
    m = Gf.Matrix4d(); m.SetRotate(Gf.Rotation(Gf.Vec3d(0, 1, 0), -90.0))
    if approx == "flat_sdf":
        # 讀出資產頂點、把完整變換烘進去,直接掛在剛體底下。中間沒有任何 xform。
        tmp = Usd.Stage.Open(os.path.join(HERE, MUG["source"]))
        allp, allf, off = [], [], 0
        for pr in tmp.Traverse():
            if not pr.IsA(UsdGeom.Mesh):
                continue
            mm = UsdGeom.Mesh(pr)
            lw = UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            T = lw * m
            pts = mm.GetPointsAttr().Get() or []
            allp += [Gf.Vec3f(T.Transform(Gf.Vec3d(*q))) for q in pts]
            fc = mm.GetFaceVertexCountsAttr().Get() or []
            fi = list(mm.GetFaceVertexIndicesAttr().Get() or [])
            k = 0
            for c in fc:
                allf.append([off + fi[k + t] for t in range(c)]); k += c
            off += len(pts)
        fm = UsdGeom.Mesh.Define(stage, root + "/body")
        fm.GetPointsAttr().Set(allp)
        fm.GetFaceVertexCountsAttr().Set([len(f) for f in allf])
        fm.GetFaceVertexIndicesAttr().Set([q for f in allf for q in f])
        fm.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
        UsdPhysics.CollisionAPI.Apply(fm.GetPrim())
        UsdPhysics.MeshCollisionAPI.Apply(fm.GetPrim()).CreateApproximationAttr("sdf")
        PhysxSchema.PhysxSDFMeshCollisionAPI.Apply(fm.GetPrim()).CreateSdfResolutionAttr().Set(256)
        out[approx] = {"meshes": 1, "verts": len(allp)}
        continue
    h = UsdGeom.Xform.Define(stage, root + "/asset")
    UsdGeom.Xformable(h).MakeMatrixXform().Set(m)
    r = UsdGeom.Xform.Define(stage, root + "/asset/ref")
    r.GetPrim().GetReferences().AddReference(os.path.join(HERE, MUG["source"]))
    n = 0
    if approx == "baked_sdf":
        # 把 reference 裡的頂點「烘」到剛體自己的座標系,產生一個獨立的碰撞網格。
        # 這樣碰撞體與算圖網格保證同位,不受 reference 內層 xformOp 影響。
        body_w = UsdGeom.Xformable(x.GetPrim()).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        w2b = body_w.GetInverse()
        allp, allf, off = [], [], 0
        for pr in Usd.PrimRange(r.GetPrim()):
            if not pr.IsA(UsdGeom.Mesh):
                continue
            mm = UsdGeom.Mesh(pr)
            lw = UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            T = lw * w2b
            pts = mm.GetPointsAttr().Get() or []
            allp += [Gf.Vec3f(T.Transform(Gf.Vec3d(*q))) for q in pts]
            fc = mm.GetFaceVertexCountsAttr().Get() or []
            fi = list(mm.GetFaceVertexIndicesAttr().Get() or [])
            k = 0
            for c in fc:
                allf.append([off + fi[k + t] for t in range(c)]); k += c
            off += len(pts)
            n += 1
        cm = UsdGeom.Mesh.Define(stage, root + "/collider")
        cm.GetPointsAttr().Set(allp)
        cm.GetFaceVertexCountsAttr().Set([len(f) for f in allf])
        cm.GetFaceVertexIndicesAttr().Set([q for f in allf for q in f])
        cm.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
        UsdGeom.Imageable(cm.GetPrim()).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
        UsdPhysics.CollisionAPI.Apply(cm.GetPrim())
        UsdPhysics.MeshCollisionAPI.Apply(cm.GetPrim()).CreateApproximationAttr("sdf")
        PhysxSchema.PhysxSDFMeshCollisionAPI.Apply(cm.GetPrim()).CreateSdfResolutionAttr().Set(256)
    else:
        for pr in Usd.PrimRange(r.GetPrim()):
            if pr.IsA(UsdGeom.Mesh):
                UsdPhysics.CollisionAPI.Apply(pr)
                UsdPhysics.MeshCollisionAPI.Apply(pr).CreateApproximationAttr(approx)
                if approx == "sdf":
                    PhysxSchema.PhysxSDFMeshCollisionAPI.Apply(pr).CreateSdfResolutionAttr().Set(256)
                n += 1
    out[approx] = {"meshes": n}

sim = SimulationContext(physics_dt=1/240., rendering_dt=1/240., stage_units_in_meters=1.0)
pc = sim.get_physics_context(); pc.enable_gpu_dynamics(True); pc.set_broadphase_type("GPU"); pc.set_solver_type("TGS")
sim.initialize_physics(); sim.play()
for _ in range(700):
    sim.step(render=False)

cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
rc = cache.ComputeWorldBound(stage.GetPrimAtPath("/World/ctrl_cube")).ComputeAlignedRange()
out["ctrl_cube"] = {"min_z_mm": round(rc.GetMin()[2]*1000,2), "max_z_mm": round(rc.GetMax()[2]*1000,2)}
carb.log_warn(f"[drop] ctrl_cube            rest min_z={rc.GetMin()[2]*1000:+7.2f} mm  (應該 ~0)")
for approx in out:
    r = cache.ComputeWorldBound(stage.GetPrimAtPath(f"/World/m_{approx}")).ComputeAlignedRange()
    mn, mx = r.GetMin(), r.GetMax()
    out[approx].update(min_z_mm=round(mn[2]*1000, 2), max_z_mm=round(mx[2]*1000, 2),
                       z_span_mm=round((mx[2]-mn[2])*1000, 2))
    xfc = UsdGeom.Xformable(stage.GetPrimAtPath(f"/World/m_{approx}"))
    M = xfc.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    out[approx]["world_translate_mm"] = [round(v*1000,2) for v in M.ExtractTranslation()]
    carb.log_warn(f"[drop] {approx:20s} rest min_z={mn[2]*1000:+7.2f} mm  span={(mx[2]-mn[2])*1000:.1f} mm")
print(json.dumps(out, indent=2), flush=True)
json.dump(out, open(os.path.join(HERE, "out", "drop_test.json"), "w"), indent=2)
sim.stop(); simulation_app.close(); os._exit(0)
