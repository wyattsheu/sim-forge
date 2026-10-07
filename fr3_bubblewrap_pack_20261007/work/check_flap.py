#!/usr/bin/env python3
"""check_flap.py — 包材有沒有穿過紙箱的蓋子/底板。用每一片的實際世界 bbox 判,不用名目平面。"""
import os, sys
import numpy as np
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
from pxr import Usd, UsdGeom, Gf
P = lambda *s: print(*s, flush=True)
st = Usd.Stage.Open(sys.argv[1])
bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])

def wb(path):
    p = st.GetPrimAtPath(path)
    if not p.IsValid(): return None
    r = bb.ComputeWorldBound(p).ComputeAlignedRange()
    lo, hi = np.array(r.GetMin()), np.array(r.GetMax())
    return (lo*1e3, hi*1e3) if np.all(np.isfinite(lo)) else None

SPp = st.GetPrimAtPath("/World/Packed/Wrap")
SP = np.array(UsdGeom.Mesh(SPp).GetPointsAttr().Get())
w = Gf.Matrix4d(UsdGeom.Xformable(SPp).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
SP = np.array([[*w.Transform(Gf.Vec3d(float(a), float(b), float(c)))] for a, b, c in SP])*1e3
P("包材 %d 頂點,世界 bbox x %.0f~%.0f y %.0f~%.0f z %.0f~%.0f mm"
  % (len(SP), SP[:,0].min(), SP[:,0].max(), SP[:,1].min(), SP[:,1].max(), SP[:,2].min(), SP[:,2].max()))
P("")
for nm in ("base", "fxp", "fxn", "fyp", "fyn", "wxp", "wxn", "wyp", "wyn"):
    r = wb("/World/Packed/Box/" + nm)
    if r is None: continue
    lo, hi = r
    inside = ((SP[:,0] > lo[0]) & (SP[:,0] < hi[0]) &
              (SP[:,1] > lo[1]) & (SP[:,1] < hi[1]) &
              (SP[:,2] > lo[2]) & (SP[:,2] < hi[2]))
    tag = {"base":"箱底","fxp":"下層蓋 +x","fxn":"下層蓋 -x","fyp":"上層蓋 +y","fyn":"上層蓋 -y"}.get(nm, "牆 "+nm)
    P("%-12s bbox x %7.1f~%7.1f y %7.1f~%7.1f z %7.1f~%7.1f | 包材落在它體積內的頂點 **%d**"
      % (tag, lo[0], hi[0], lo[1], hi[1], lo[2], hi[2], int(inside.sum())))
    if inside.sum():
        q = SP[inside]
        P("              → 那些點 x %.0f~%.0f y %.0f~%.0f z %.0f~%.0f"
          % (q[:,0].min(), q[:,0].max(), q[:,1].min(), q[:,1].max(), q[:,2].min(), q[:,2].max()))
sim.close()
