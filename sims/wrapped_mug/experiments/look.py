# -*- coding: utf-8 -*-
"""看現況:播放一段後,從幾個角度算圖,並印出耳朵與包材的實際位置。"""
import os, sys, json, math
from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": True, "width": 1280, "height": 800})
import carb
from pxr import Usd, UsdGeom, Gf
import omni.usd
from isaacsim.core.api import SimulationContext
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import wf_common as wf
st = carb.settings.get_settings()
st.set_bool("/rtx/raytracing/fractionalCutoutOpacity", True)
wf.enable_deformable_runtime()
USD = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out", "wrapped_mug_on_rig.usd")
STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 240
omni.usd.get_context().open_stage(USD)
stage = omni.usd.get_context().get_stage()
sim = SimulationContext(physics_dt=1/120., rendering_dt=1/60., stage_units_in_meters=1.0)
pc = sim.get_physics_context(); pc.enable_gpu_dynamics(True); pc.set_broadphase_type("GPU"); pc.set_solver_type("TGS")
sim.initialize_physics(); sim.play()
for _ in range(STEPS):
    sim.step(render=False)

c = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
def bb(p):
    pr = stage.GetPrimAtPath(p)
    if not (pr and pr.IsValid()): return None
    r = c.ComputeWorldBound(pr).ComputeAlignedRange()
    return [round(v*1000,1) for v in r.GetMin()], [round(v*1000,1) for v in r.GetMax()]
for p in ("/World/Carton/base", "/World/Carton/fxp", "/World/Carton/fxn",
          "/World/Carton/fyp", "/World/Carton/fyn", "/World/mug", "/World/wrap"):
    carb.log_warn(f"[look] {p:26s} {bb(p)}")
# 包材有多少頂點在箱子外
w = UsdGeom.Mesh(stage.GetPrimAtPath("/World/wrap")).GetPointsAttr().Get()
IN = dict(x0=-0.1185, x1=0.0785, y0=-0.0885, y1=0.0885, z0=0.023, z1=0.110)
out_of = [p for p in w if not (IN["x0"]-0.002 <= p[0] <= IN["x1"]+0.002
                               and IN["y0"]-0.002 <= p[1] <= IN["y1"]+0.002
                               and IN["z0"]-0.004 <= p[2] <= IN["z1"]+0.002)]
carb.log_warn(f"[look] wrap verts outside carton interior: {len(out_of)} / {len(w)}")
if out_of:
    carb.log_warn(f"[look]   worst: x[{min(p[0] for p in out_of)*1000:.0f},{max(p[0] for p in out_of)*1000:.0f}] "
                  f"y[{min(p[1] for p in out_of)*1000:.0f},{max(p[1] for p in out_of)*1000:.0f}] "
                  f"z[{min(p[2] for p in out_of)*1000:.0f},{max(p[2] for p in out_of)*1000:.0f}] mm")

import omni.replicator.core as rep
def cam(path, eye, tgt, f=28.0):
    cm = UsdGeom.Camera.Define(stage, path)
    cm.CreateFocalLengthAttr(f); cm.CreateClippingRangeAttr(Gf.Vec2f(0.005, 60.0))
    m = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*tgt), Gf.Vec3d(0,0,1)).GetInverse()
    UsdGeom.Xformable(cm).MakeMatrixXform().Set(m)
    return path
OUT = os.path.join(HERE, "out", "look")
views = {"iso": ((0.30, -0.30, 0.25), (-0.02, 0.0, 0.06), 28.0),
         "top": ((-0.02, 0.0, 0.52), (-0.02, 0.0, 0.05), 30.0),
         "side": ((-0.02, -0.42, 0.10), (-0.02, 0.0, 0.065), 32.0)}
for n,(e,t,f) in views.items():
    rp = rep.create.render_product(cam(f"/World/lookcam_{n}", e, t, f), (1280, 800))
    wr = rep.WriterRegistry.get("BasicWriter"); wr.initialize(output_dir=os.path.join(OUT, n), rgb=True)
    wr.attach([rp]); rep.orchestrator.step(rt_subframes=28); wr.detach(); rp.destroy()
carb.log_warn(f"[look] -> {OUT}")
sim.stop(); simulation_app.close(); os._exit(0)
