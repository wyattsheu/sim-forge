# -*- coding: utf-8 -*-
"""驗收 + 出圖。

驗收(P3 gate):重開烘好的 USD,場上沒有任何抓手或驅動,純播放 N 步。
  * 膜的頂點漂移要夠小 -> 折痕真的是零能量狀態,不靠外力維持
  * 馬克杯要還在膜裡、沒被擠出去

出圖:等角 / 正面 / 俯視三張 PNG。

用法:  /isaac-sim/python.sh verify_render.py [--usd PATH] [--steps 600]
"""
import argparse, json, math, os, sys

from isaacsim import SimulationApp

_ap = argparse.ArgumentParser()
_ap.add_argument("--usd", default=None)
_ap.add_argument("--steps", type=int, default=600)
_ap.add_argument("--no-render", action="store_true")
_ap.add_argument("--prefix", default="/World", help="包裹在場景裡的父路徑,例如 /World/Package")
_ap.add_argument("--wide", action="store_true", help="拉遠相機,拍整個平台")
ARGS = _ap.parse_args()

simulation_app = SimulationApp({"headless": True, "width": 1280, "height": 800})

import carb
from pxr import Usd, UsdGeom, Gf
import omni.usd
from isaacsim.core.api import SimulationContext

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wf_common as wf

OUT = os.path.join(HERE, "out")
USD_IN = ARGS.usd or os.path.join(OUT, "wrapped_mug_in_carton.usd")
SHOTS = os.path.join(OUT, "shots_rig" if ARGS.wide else "shots")
os.makedirs(SHOTS, exist_ok=True)

_LOG = []


def log(msg):
    line = f"[verify] {msg}"
    _LOG.append(line)
    print(line, flush=True)
    carb.log_warn(line)


# RTX Real-Time 預設沒開 fractional cutout opacity,半透明材質會被當成二值 cutout
_rtx = carb.settings.get_settings()
_rtx.set_bool("/rtx/raytracing/fractionalCutoutOpacity", True)
_rtx.set_bool("/rtx/pathtracing/fractionalCutoutOpacity", True)
log(f"runtime: {wf.enable_deformable_runtime()}")
omni.usd.get_context().open_stage(USD_IN)
stage = omni.usd.get_context().get_stage()
log(f"opened {USD_IN}")

wrap = UsdGeom.Mesh(stage.GetPrimAtPath(f"{ARGS.prefix}/wrap"))
mug = stage.GetPrimAtPath(f"{ARGS.prefix}/mug")
before = list(wrap.GetPointsAttr().Get())
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
mug_before = cache.ComputeWorldBound(mug).ComputeAlignedRange().GetMidpoint()

sim = SimulationContext(physics_dt=1.0 / 120.0, rendering_dt=1.0 / 60.0, stage_units_in_meters=1.0)
pcx = sim.get_physics_context()
pcx.enable_gpu_dynamics(True)
pcx.set_broadphase_type("GPU")
pcx.set_solver_type("TGS")
sim.initialize_physics()
sim.play()

trace = []
for k in range(ARGS.steps):
    sim.step(render=False)
    if k % 60 == 59:
        cur = list(wrap.GetPointsAttr().Get())
        d = max(math.dist(tuple(cur[i]), tuple(before[i])) for i in range(len(cur)))
        trace.append(round(d * 1000, 3))

after = list(wrap.GetPointsAttr().Get())
drift = max(math.dist(tuple(after[i]), tuple(before[i])) for i in range(len(after)))
mean_drift = sum(math.dist(tuple(after[i]), tuple(before[i])) for i in range(len(after))) / len(after)
cache2 = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
mug_after = cache2.ComputeWorldBound(mug).ComputeAlignedRange().GetMidpoint()
mug_move = (Gf.Vec3d(mug_after) - Gf.Vec3d(mug_before)).GetLength()

# 杯子有沒有還被膜包著:膜在杯子上方 (z > 杯心) 還有幾個頂點
mug_top_z = mug_after[2]
cover = sum(1 for p in after if p[2] > mug_top_z and abs(p[1]) < 0.05)

# 逃出箱外的頂點:箱內半寬 + 板厚,或低於箱底
_cb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"]).ComputeWorldBound(
    stage.GetPrimAtPath(f"{ARGS.prefix}/Carton/base")).ComputeAlignedRange()
_mn, _mx = _cb.GetMin(), _cb.GetMax()
esc = sum(1 for p in after
          if not (_mn[0] - 0.01 <= p[0] <= _mx[0] + 0.01
                  and _mn[1] - 0.01 <= p[1] <= _mx[1] + 0.01
                  and p[2] >= _mn[2] - 0.008))
verdict = "PASS" if (mean_drift < 0.005 and drift < 0.025 and mug_move < 0.010
                     and cover > 20 and esc == 0) else "REVIEW"
log(f"wrap max drift {drift*1000:.2f} mm (mean {mean_drift*1000:.2f}), "
    f"mug moved {mug_move*1000:.2f} mm, cover verts {cover}, escaped {esc} -> {verdict}")
log(f"drift trace (mm, per 0.5 s): {trace}")

cache3 = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
geo = {}
for p_ in [f"{ARGS.prefix}/Carton/base", f"{ARGS.prefix}/mug",
           f"{ARGS.prefix}/mug/handle", f"{ARGS.prefix}/wrap"]:
    pr = stage.GetPrimAtPath(p_)
    if pr and pr.IsValid():
        r = cache3.ComputeWorldBound(pr).ComputeAlignedRange()
        geo[p_] = [[round(v * 1000, 1) for v in r.GetMin()], [round(v * 1000, 1) for v in r.GetMax()]]
        log(f"bbox {p_:24s} min={geo[p_][0]} max={geo[p_][1]} (mm)")

# 取 x 最接近 0 的那一排膜頂點,印出 (y,z) 剖面 —— 直接看包覆形狀對不對
xs = sorted({round(p[0], 4) for p in after})
x_mid = min(xs, key=lambda v: abs(v))
prof = sorted([(round(p[1] * 1000, 1), round(p[2] * 1000, 1)) for p in after if abs(p[0] - x_mid) < 2e-4])
log(f"wrap cross-section at x={x_mid*1000:.1f} mm, {len(prof)} pts:")
log("  " + " ".join(f"({y:+.0f},{z:.0f})" for y, z in prof[::3]))

shots = []
if not ARGS.no_render:
    try:
        import omni.replicator.core as rep

        def place_cam(path, eye, target, focal=24.0):
            cam = UsdGeom.Camera.Define(stage, path)
            cam.CreateFocalLengthAttr(focal)
            cam.CreateFocusDistanceAttr(float((Gf.Vec3d(*target) - Gf.Vec3d(*eye)).GetLength()))
            cam.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
            m = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1)).GetInverse()
            UsdGeom.Xformable(cam).MakeMatrixXform().Set(m)
            return path

        if ARGS.wide:
            views = {
                "rig_iso": ((1.05, -1.05, 0.85), (-0.02, 0.0, 0.10)),
                "rig_front": ((1.15, 0.0, 0.42), (-0.02, 0.0, 0.10)),
                "rig_top": ((0.0, 0.0, 1.55), (-0.02, 0.0, 0.05)),
                "closeup": ((0.24, -0.24, 0.30), (-0.02, 0.0, 0.09)),
            }
        else:
            views = {
                "iso": ((0.46, -0.42, 0.34), (0.0, 0.0, 0.05)),
                "front": ((0.0, -0.52, 0.12), (0.0, 0.0, 0.055)),
                "top": ((0.02, 0.0, 0.62), (0.0, 0.0, 0.03)),
                "closeup": ((0.19, -0.19, 0.19), (0.0, 0.0, 0.075)),
            }
        for name, (pos, look) in views.items():
            cam_path = place_cam(f"/World/cams/{name}", pos, look,
                                 focal=35.0 if name == "closeup" else 24.0)
            rp = rep.create.render_product(cam_path, (1280, 800))
            w = rep.WriterRegistry.get("BasicWriter")
            d = os.path.join(SHOTS, name)
            w.initialize(output_dir=d, rgb=True)
            w.attach([rp])
            rep.orchestrator.step(rt_subframes=24)
            w.detach()
            rp.destroy()
            shots.append(d)
        log(f"rendered {len(shots)} views -> {SHOTS}")
    except Exception as e:
        log(f"render failed: {e}")

report = {
    "usd": USD_IN,
    "steps": ARGS.steps,
    "wrap_max_drift_mm": round(drift * 1000, 3),
    "wrap_mean_drift_mm": round(mean_drift * 1000, 3),
    "drift_trace_mm": trace,
    "mug_center_move_mm": round(mug_move * 1000, 3),
    "verts_above_mug_center": cover,
    "escaped_verts": esc,
    "verdict": verdict,
    "shots": shots,
    "bboxes_mm": geo,
    "wrap_cross_section_mm": prof,
    "log": _LOG,
}
with open(os.path.join(OUT, "verify_report.json"), "w") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

sim.stop()
simulation_app.close()
os._exit(0)
