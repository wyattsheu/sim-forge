# -*- coding: utf-8 -*-
"""只算圖不跑物理:把膜換成不透明紅色,確認它在畫面上的位置與覆蓋範圍。"""
import os, sys
from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": True, "width": 1280, "height": 800})
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf
import omni.usd, carb

HERE = os.path.dirname(os.path.abspath(__file__))
USD = os.path.join(HERE, "out", "wrapped_mug_in_carton.usd")
# RTX Real-Time 預設沒開 fractional cutout opacity,半透明材質會被當成二值 cutout
_rtx = carb.settings.get_settings()
_rtx.set_bool("/rtx/raytracing/fractionalCutoutOpacity", True)
_rtx.set_bool("/rtx/pathtracing/fractionalCutoutOpacity", True)
omni.usd.get_context().open_stage(USD)
stage = omni.usd.get_context().get_stage()

sh = stage.GetPrimAtPath("/World/Looks/BubbleFilm/Shader")
s = UsdShade.Shader(sh)
s.GetInput("diffuse_color_constant").Set(Gf.Vec3f(0.90, 0.10, 0.10))
# 保留作者設定的半透明,只換顏色 -> 看半透明到底有沒有生效

# 燈光調暗,避免過曝看不出材質

carb.log_warn("[probe] film -> red, opacity as authored")

import omni.replicator.core as rep
def cam(path, eye, target, focal=24.0):
    c = UsdGeom.Camera.Define(stage, path)
    c.CreateFocalLengthAttr(focal); c.CreateClippingRangeAttr(Gf.Vec2f(0.01, 50.0))
    m = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0,0,1)).GetInverse()
    UsdGeom.Xformable(c).MakeMatrixXform().Set(m)
    return path
out = os.path.join(HERE, "out", "probe")
for name, (eye, tgt, f) in {
    "top":  ((0.02, 0.0, 0.55), (0.0, 0.0, 0.03), 24.0),
    "iso":  ((0.34, -0.30, 0.26), (0.0, 0.0, 0.05), 24.0),
}.items():
    rp = rep.create.render_product(cam(f"/World/probecams/{name}", eye, tgt, f), (1280, 800))
    w = rep.WriterRegistry.get("BasicWriter")
    w.initialize(output_dir=os.path.join(out, name), rgb=True)
    w.attach([rp]); rep.orchestrator.step(rt_subframes=32); w.detach(); rp.destroy()
carb.log_warn(f"[probe] done -> {out}")
simulation_app.close(); os._exit(0)
