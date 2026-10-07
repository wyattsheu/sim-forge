#!/usr/bin/env python3
"""insp_scene.py — 手臂場景的方位。唯讀。"""
import os, sys
import numpy as np
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
from pxr import Usd, UsdGeom, Gf
P = lambda *s: print(*s, flush=True)
st = Usd.Stage.Open(sys.argv[1])
bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])

P("=== /World 底下的頂層 prim ===")
w = st.GetPrimAtPath("/World")
for p in (w.GetChildren() if w.IsValid() else st.GetPseudoRoot().GetChildren()):
    t = str(p.GetTypeName())
    try:
        r = bb.ComputeWorldBound(p).ComputeAlignedRange()
        lo, hi = np.array(r.GetMin()), np.array(r.GetMax())
        if not np.all(np.isfinite(lo)):
            P("  %-34s %-12s (無 bbox)" % (p.GetPath(), t)); continue
        c = (lo+hi)/2
        P("  %-34s %-12s 中心 (%7.1f, %7.1f, %7.1f) 尺寸 %6.1f x %6.1f x %6.1f mm"
          % (p.GetPath(), t, *(c*1e3), *((hi-lo)*1e3)))
    except Exception as e:
        P("  %-34s %-12s ✗ %s" % (p.GetPath(), t, str(e)[:40]))

P("\n=== 找手臂 / 桌子 ===")
for p in st.Traverse():
    n = p.GetName().lower()
    if any(k in n for k in ("fr3", "franka", "panda", "robot", "arm", "table", "desk", "link0", "base_link")):
        try:
            r = bb.ComputeWorldBound(p).ComputeAlignedRange()
            lo, hi = np.array(r.GetMin()), np.array(r.GetMax())
            if not np.all(np.isfinite(lo)): continue
            c = (lo+hi)/2
            P("  %-46s 中心 (%7.1f, %7.1f, %7.1f) 尺寸 %6.1f x %6.1f x %6.1f"
              % (str(p.GetPath())[:46], *(c*1e3), *((hi-lo)*1e3)))
        except Exception:
            pass
sim.close()
