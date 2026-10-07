#!/usr/bin/env python3
"""orbit_video.py — 場景環繞影片(只渲染、不建 World、不跑物理)。

  /isaac-sim/python.sh orbit_video.py scene_final.usd out.mp4 [--secs 12] [--fps 30]

shot_full.py 會先建 World(物理)再拍,在完整場景上會 segfault;
這支只開 stage + replicator render product,沒有物理初始化。
鏡頭繞 /World/Packed(找不到就繞 /World/Carton)轉一圈,最後停在近拍俯視。
"""
import argparse, math, os
ap = argparse.ArgumentParser()
ap.add_argument("scene"); ap.add_argument("out")
ap.add_argument("--secs", type=float, default=12.0)
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--res", default="1280x720")
ap.add_argument("--radius", type=float, default=1.35, help="繞圈半徑(m)")
ap.add_argument("--height", type=float, default=0.75, help="鏡頭高度(m)")
a = ap.parse_args()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
W, H = [int(v) for v in a.res.split("x")]

from isaacsim import SimulationApp
sim = SimulationApp({"headless": True, "width": W, "height": H})
import numpy as np, imageio
import omni.usd, omni.replicator.core as rep
from pxr import Usd, UsdGeom, Gf
P = lambda *s: print(*s, flush=True)

omni.usd.get_context().open_stage(os.path.abspath(a.scene))
for _ in range(60): sim.update()                       # 等材質 / 雲端 MDL 載入
st = omni.usd.get_context().get_stage()
tgt = next(p for p in ("/World/Packed", "/World/Carton") if st.GetPrimAtPath(p).IsValid())
r = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]) \
    .ComputeWorldBound(st.GetPrimAtPath(tgt)).ComputeAlignedRange()
C = (r.GetMin() + r.GetMax()) / 2
P("鏡頭目標 %s 中心 (%.0f, %.0f, %.0f) mm" % (tgt, C[0]*1e3, C[1]*1e3, C[2]*1e3))

cam = rep.create.camera(focal_length=18.0, clipping_range=(0.01, 100.0))
rp = rep.create.render_product(cam, (W, H))
rgb = rep.AnnotatorRegistry.get_annotator("rgb"); rgb.attach([rp])
rep.orchestrator.set_capture_on_play(False)

def look(eye, at):
    with cam:
        rep.modify.pose(position=tuple(float(v) for v in eye), look_at=tuple(float(v) for v in at))

n = int(a.secs * a.fps)
n_orbit = int(n * 0.75)
wr = imageio.get_writer(a.out, fps=a.fps, codec="libx264", quality=8, pixelformat="yuv420p")
for i in range(n):
    if i < n_orbit:                                    # 從手臂正面(-x)起繞一圈
        th = math.pi + 2*math.pi * i / n_orbit
        eye = (C[0] + a.radius*math.cos(th), C[1] + a.radius*math.sin(th), a.height)
    else:                                              # 收尾:推近俯視看箱內
        u = (i - n_orbit) / max(1, n - n_orbit - 1); u = u*u*(3 - 2*u)
        e0 = np.array([C[0] - a.radius, C[1], a.height]); e1 = np.array([C[0] - 0.30, C[1], C[2] + 0.55])
        eye = e0 + (e1 - e0)*u
    look(eye, C)
    rep.orchestrator.step(rt_subframes=4 if i else 32, pause_timeline=True)
    img = rgb.get_data()
    if img is None or img.size == 0: continue
    wr.append_data(np.asarray(img)[:, :, :3])
    if i % 60 == 0: P("  frame %d / %d" % (i, n))
wr.close()
P("→ %s" % os.path.abspath(a.out))
sim.close()
