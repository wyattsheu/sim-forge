# -*- coding: utf-8 -*-
"""基準測試:原始 stationary_ai 場景,不加任何東西,純播放,看紙箱穩不穩。"""
import os, sys, json
from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": True})
import carb
from pxr import Usd, UsdGeom
import omni.usd
from isaacsim.core.api import SimulationContext
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import wf_common as wf
RIG = os.path.join(os.path.dirname(HERE), "stationary_ai_carton_scene_flat.usd")
wf.enable_deformable_runtime()
omni.usd.get_context().open_stage(RIG)
stage = omni.usd.get_context().get_stage()
c = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
def bb(p):
    r = c.ComputeWorldBound(stage.GetPrimAtPath(p)).ComputeAlignedRange()
    return [round(v*1000,1) for v in r.GetMin()], [round(v*1000,1) for v in r.GetMax()]
before = {p: bb(p) for p in ("/World/Carton/base", "/World/Carton/fxp", "/World/Carton/fyp",
                             "/World/stationary_ai/tabletop_link")}
sim = SimulationContext(physics_dt=1/120., rendering_dt=1/60., stage_units_in_meters=1.0)
pc = sim.get_physics_context(); pc.enable_gpu_dynamics(True); pc.set_broadphase_type("GPU"); pc.set_solver_type("TGS")
sim.initialize_physics(); sim.play()
traj = []
for k in range(360):
    sim.step(render=False)
    if k % 60 == 59:
        c2 = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
        r = c2.ComputeWorldBound(stage.GetPrimAtPath("/World/Carton/base")).ComputeAlignedRange()
        traj.append(round(r.GetMin()[2]*1000, 1))
c3 = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
def bb3(p):
    r = c3.ComputeWorldBound(stage.GetPrimAtPath(p)).ComputeAlignedRange()
    return [round(v*1000,1) for v in r.GetMin()], [round(v*1000,1) for v in r.GetMax()]
after = {p: bb3(p) for p in before}
for p in before:
    carb.log_warn(f"[base] {p:44s} before {before[p]}  ->  after {after[p]}")
carb.log_warn(f"[base] carton base min-z trajectory (每 0.5s): {traj}")
json.dump({"before": before, "after": after, "traj_min_z_mm": traj},
          open(os.path.join(HERE, "out", "rig_baseline.json"), "w"), indent=2)
sim.stop(); simulation_app.close(); os._exit(0)
