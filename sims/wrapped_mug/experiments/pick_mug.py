# -*- coding: utf-8 -*-
"""把四顆 NVIDIA 官方馬克杯並排算一張圖,順便報尺寸。"""
import os, sys
from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": True, "width": 1600, "height": 700})
from pxr import Usd, UsdGeom, UsdLux, Gf, Sdf
import omni.usd, carb

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
NAMES = ["SM_Mug_A2", "SM_Mug_B1", "SM_Mug_C1", "SM_Mug_D1"]

omni.usd.get_context().new_stage()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.Xform.Define(stage, "/World")
d = UsdLux.DomeLight.Define(stage, "/World/Dome"); d.CreateIntensityAttr(600.0)
k = UsdLux.DistantLight.Define(stage, "/World/Key"); k.CreateIntensityAttr(1800.0)
UsdGeom.Xformable(k).AddRotateXYZOp().Set(Gf.Vec3f(-40, 0, 25))
g = UsdGeom.Cube.Define(stage, "/World/Floor"); g.CreateSizeAttr(1.0)
gx = UsdGeom.Xformable(g); gx.AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.005)); gx.AddScaleOp().Set(Gf.Vec3f(2.0, 2.0, 0.01))

cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
info = []
for i, n in enumerate(NAMES):
    # 官方資產的 defaultPrim 自帶 translate/rotateXYZ/scale,所以要多包一層乾淨的 Xform
    slot = UsdGeom.Xform.Define(stage, f"/World/slot_{i}")
    UsdGeom.Xformable(slot).AddTranslateOp().Set(Gf.Vec3d(0, (i - 1.5) * 0.17, 0))
    x = UsdGeom.Xform.Define(stage, f"/World/slot_{i}/{n}")
    x.GetPrim().GetReferences().AddReference(os.path.join(ASSETS, n + ".usd"))
    r = cache.ComputeWorldBound(x.GetPrim()).ComputeAlignedRange()
    mn, mx = r.GetMin(), r.GetMax()
    info.append((n, [(mx[j] - mn[j]) * 1000 for j in range(3)], mn[2] * 1000))
    carb.log_warn(f"[pick] {n}: size {(mx[0]-mn[0])*1000:.1f} x {(mx[1]-mn[1])*1000:.1f} x {(mx[2]-mn[2])*1000:.1f} mm, base z={mn[2]*1000:.1f}")

import omni.replicator.core as rep
cam = UsdGeom.Camera.Define(stage, "/World/cam")
cam.CreateFocalLengthAttr(30.0); cam.CreateClippingRangeAttr(Gf.Vec2f(0.01, 50.0))
m = Gf.Matrix4d().SetLookAt(Gf.Vec3d(1.15, 0.0, 0.42), Gf.Vec3d(0.0, 0.0, 0.055), Gf.Vec3d(0, 0, 1)).GetInverse()
UsdGeom.Xformable(cam).MakeMatrixXform().Set(m)
rp = rep.create.render_product("/World/cam", (1600, 700))
w = rep.WriterRegistry.get("BasicWriter"); w.initialize(output_dir=os.path.join(HERE, "out", "mugs"), rgb=True)
w.attach([rp]); rep.orchestrator.step(rt_subframes=32); w.detach()
carb.log_warn("[pick] done")
simulation_app.close(); os._exit(0)
