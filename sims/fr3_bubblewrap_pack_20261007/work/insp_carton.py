#!/usr/bin/env python3
"""insp_carton.py — 讀紙箱 USD 的結構(摺線關節怎麼驅動)。唯讀,不改任何東西。"""
import os, sys
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
from pxr import Usd, UsdPhysics, UsdGeom, Gf
P = lambda *s: print(*s, flush=True)
st = Usd.Stage.Open(sys.argv[1])
P("=== prim ===")
for p in st.Traverse():
    t = str(p.GetTypeName())
    if t in ("PhysicsRevoluteJoint", "Mesh", "Xform", "Scope"):
        extra = ""
        if t == "PhysicsRevoluteJoint":
            j = UsdPhysics.RevoluteJoint(p)
            b0 = j.GetBody0Rel().GetTargets(); b1 = j.GetBody1Rel().GetTargets()
            extra = " axis=%s low=%s high=%s body0=%s body1=%s" % (
                j.GetAxisAttr().Get(), j.GetLowerLimitAttr().Get(), j.GetUpperLimitAttr().Get(),
                b0[0].name if b0 else "-", b1[0].name if b1 else "-")
            extra += " | drive=%s" % [a.GetName() for a in p.GetAttributes() if "drive" in a.GetName()]
        if t == "Mesh":
            b = UsdGeom.Mesh(p).GetPointsAttr().Get()
            if b:
                import numpy as np
                B = np.array(b); e = B.max(0) - B.min(0)
                extra = " bbox %.0f x %.0f x %.0f mm" % tuple(e*1e3)
        P("%-46s %-24s%s" % (p.GetPath(), t, extra))
P("\n=== 每片蓋的姿態(要驅動蓋子就得知道現在在哪)===")
for nm in ("fxp", "fxn", "fyp", "fyn"):
    pr = st.GetPrimAtPath("/Box/" + nm)
    if not pr.IsValid(): continue
    w = Gf.Matrix4d(UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
    import numpy as np
    bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
    r = bb.ComputeWorldBound(pr).ComputeAlignedRange()
    lo, hi = np.array(r.GetMin()), np.array(r.GetMax())
    P("%-5s 世界 bbox  x %7.1f~%7.1f  y %7.1f~%7.1f  z %7.1f~%7.1f mm"
      % (nm, lo[0]*1e3, hi[0]*1e3, lo[1]*1e3, hi[1]*1e3, lo[2]*1e3, hi[2]*1e3))
    P("      厚度方向 = %s;平躺(開)厚度應該很薄,豎起(關)會很高"
      % ("z 最薄" if (hi[2]-lo[2]) < min(hi[0]-lo[0], hi[1]-lo[1]) else "非 z"))
    rot = w.ExtractRotation()
    P("      local->world 旋轉 %s,平移 %s"
      % (rot.GetAxis(), tuple(round(float(x)*1e3, 1) for x in w.ExtractTranslation())))
    P("      旋轉角 %.1f deg" % rot.GetAngle())
for nm in ("crease_fxp", "crease_fxn", "crease_fyp", "crease_fyn"):
    j = UsdPhysics.RevoluteJoint(st.GetPrimAtPath("/Box/" + nm))
    if not j: continue
    P("%-12s localPos0=%s localRot0=%s" % (nm, j.GetLocalPos0Attr().Get(), j.GetLocalRot0Attr().Get()))
    P("%-12s localPos1=%s localRot1=%s" % ("", j.GetLocalPos1Attr().Get(), j.GetLocalRot1Attr().Get()))
sim.close()
