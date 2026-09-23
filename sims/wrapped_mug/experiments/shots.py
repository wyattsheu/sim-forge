# -*- coding: utf-8 -*-
"""出 README 用的截圖。播放一段讓物理落定後再算圖。"""
import os, sys
from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": True, "width": 1440, "height": 900})
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

USD, OUT, STEPS = sys.argv[1], sys.argv[2], int(sys.argv[3])
VIEWS = eval(sys.argv[4])
omni.usd.get_context().open_stage(USD)
stage = omni.usd.get_context().get_stage()
sim = SimulationContext(physics_dt=1/120., rendering_dt=1/60., stage_units_in_meters=1.0)
pc = sim.get_physics_context(); pc.enable_gpu_dynamics(True); pc.set_broadphase_type("GPU"); pc.set_solver_type("TGS")
sim.initialize_physics(); sim.play()
for _ in range(STEPS):
    sim.step(render=False)

import omni.replicator.core as rep
os.makedirs(OUT, exist_ok=True)
for name, (eye, tgt, f) in VIEWS.items():
    c = UsdGeom.Camera.Define(stage, f"/World/shotcam_{name}")
    c.CreateFocalLengthAttr(f); c.CreateClippingRangeAttr(Gf.Vec2f(0.005, 80.0))
    m = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*tgt), Gf.Vec3d(0,0,1)).GetInverse()
    UsdGeom.Xformable(c).MakeMatrixXform().Set(m)
    rp = rep.create.render_product(f"/World/shotcam_{name}", (1440, 900))
    w = rep.WriterRegistry.get("BasicWriter"); w.initialize(output_dir=os.path.join(OUT, name), rgb=True)
    w.attach([rp]); rep.orchestrator.step(rt_subframes=36); w.detach(); rp.destroy()
    carb.log_warn(f"[shots] {name}")
sim.stop(); simulation_app.close(); os._exit(0)
