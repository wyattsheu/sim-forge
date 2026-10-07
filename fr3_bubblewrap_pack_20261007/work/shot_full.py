#!/usr/bin/env python3
"""shot_full.py — 完整場景的定裝照(唯讀,不跑物理)。"""
import os, sys
import numpy as np
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import omni.usd
from isaacsim.core.api import World
from isaacsim.sensors.camera import Camera
from pxr import Usd, UsdGeom, UsdLux, Gf
import imageio.v3 as iio
import grip_common as G
P = lambda *s: print(*s, flush=True)

omni.usd.get_context().open_stage(sys.argv[1])
world = World(physics_dt=1/120.0, rendering_dt=1/30.0)
st = omni.usd.get_context().get_stage()
gl = st.GetPrimAtPath("/World/defaultGroundPlane/SphereLight")
if gl.IsValid():
    at = gl.GetAttribute("inputs:intensity")
    if at and at.IsValid(): at.Set(at.Get()/12.0)

cam = Camera(prim_path="/World/shotcam", resolution=(1600, 900), frequency=30)
cam.set_focal_length(6.0)
world.reset(); cam.initialize()
VIEWS = [("等角", [1.05, -1.05, 0.95], [-0.02, 0.0, 0.10]),
         ("俯視", [0.02, -0.02, 1.55], [-0.02, 0.0, 0.08]),
         ("側看兩臂", [1.35, 0.0, 0.55], [-0.02, 0.0, 0.10])]
frames = []
for nm, eye, tgt in VIEWS:
    G.look(cam, eye, tgt)
    G.add_headlight(st, eye, tgt, intensity=900.0, name="sl_" + nm)
    for _ in range(45): world.step(render=True)
    rgb = cam.get_rgba()
    if rgb is not None and rgb.size:
        im = rgb[:, :, :3]
        frames.append(im if im.dtype == np.uint8 else (im*255).astype(np.uint8))
        P("  拍好 %s" % nm)
for i, f in enumerate(frames):
    iio.imwrite("%s_%d.png" % (sys.argv[2], i), f)
P("→ %s_0..%d.png" % (sys.argv[2], len(frames)-1))
sim.close()
