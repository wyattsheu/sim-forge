#!/usr/bin/env python3
"""patch_scene.py — bring the delivered scene_final_phys.usd up to the build_phys_scene.py fixes that matter for the
co7b carton, without a full rebuild (a rebuild also makes the carton an articulation and rewrites limits / drives,
which the co7b arm paths were not run against).

  source ../../../tools/usdenv.sh && $PY patch_scene.py [../scene_final_phys.usd]      # pxr only, no Isaac, no GPU

1. wall pads (20 mm outside the four walls) and lid pads (20 mm on the outer face of fyp / fyn): invisible colliders
   that collide with the bubble wrap only, so wrap vertices cannot cross the 3 mm cardboard in one physics step.
   Shake test before: up to 87 wrap vertices through the side walls. Same code as build_phys_scene.py.
2. flap inertia from geometry (the authored 0.006 kg*m^2 is removed) and joint armature 0.006 -> 2e-4:
   the flaps were ~180x heavier to rotate than a real 15-17 g flap.
3. floor pad mass 0.24 kg -> 1e-6: the carton base weighed 0.352 kg, two thirds of it an invisible pad.
Idempotent: a second run changes nothing.
"""
import os, sys
import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Sdf, Gf

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "scene_final_phys.usd"))
PK = "/World/Packed"; BOX = PK + "/Box"; BASE = BOX + "/base"; WRAP = PK + "/Wrap"
LIDS = ("fxp", "fxn", "fyp", "fyn")
T_PAD, FLOOR_PAD, ARMATURE = 0.02, 0.02, 2e-4

st = Usd.Stage.Open(SCENE)
done = []

# 1. pads
if not st.GetPrimAtPath(BASE + "/pad_wxp"):
    rbc = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render", "guide", "proxy"])
    def rel(prim, anc):
        r = rbc.ComputeRelativeBound(prim, anc).ComputeAlignedRange(); return np.array(r.GetMin()), np.array(r.GetMax())
    basep = st.GetPrimAtPath(BASE)
    blo, bhi = rel(st.GetPrimAtPath(BASE + "/bottom"), basep)
    cav = (blo + bhi) / 2
    pads = []
    def add_pad(parent, name, lo, hi):
        c = UsdGeom.Cube.Define(st, parent + "/" + name); c.CreateSizeAttr(1.0)
        c.AddTranslateOp().Set(Gf.Vec3d(*map(float, (lo + hi) / 2))); c.AddScaleOp().Set(Gf.Vec3f(*map(float, hi - lo)))
        c.CreatePurposeAttr(UsdGeom.Tokens.guide)
        UsdPhysics.CollisionAPI.Apply(c.GetPrim())
        q = PhysxSchema.PhysxCollisionAPI.Apply(c.GetPrim()); q.CreateContactOffsetAttr(0.001); q.CreateRestOffsetAttr(0.0)
        UsdPhysics.MassAPI.Apply(c.GetPrim()).CreateMassAttr(1e-6)
        pads.append(c.GetPath())
    for w in ("wxp", "wxn", "wyp", "wyn"):
        lo, hi = rel(st.GetPrimAtPath(BASE + "/" + w), basep)
        ax = int(np.argmin((hi - lo)[:2])); o = 1 - ax
        out = 1.0 if (lo[ax] + hi[ax]) / 2 > cav[ax] else -1.0
        plo, phi = lo.copy(), hi.copy()
        if out > 0: plo[ax], phi[ax] = hi[ax], hi[ax] + T_PAD
        else:       plo[ax], phi[ax] = lo[ax] - T_PAD, lo[ax]
        plo[o] -= T_PAD; phi[o] += T_PAD
        plo[2] = blo[2] - FLOOR_PAD
        add_pad(BASE, "pad_" + w, plo, phi)
    for n in ("fyp", "fyn"):                       # outer (upper) flaps only: a pad on fxp / fxn overlaps fyp / fyn
        lp = st.GetPrimAtPath(BOX + "/" + n)
        lo, hi = rel(st.GetPrimAtPath(BOX + "/" + n + "/geo"), lp)
        ax = int(np.argmin(hi - lo))
        Tl = np.array(UsdGeom.Xformable(lp).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), float).T
        Tb = np.array(UsdGeom.Xformable(basep).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), float).T
        cl = np.linalg.inv(Tl[:3, :3]) @ ((Tb[:3, :3] @ cav + Tb[:3, 3]) - Tl[:3, 3])
        out = 1.0 if (lo[ax] + hi[ax]) / 2 > cl[ax] else -1.0
        plo, phi = lo.copy(), hi.copy()
        if out > 0: plo[ax], phi[ax] = hi[ax], hi[ax] + T_PAD
        else:       plo[ax], phi[ax] = lo[ax] - T_PAD, lo[ax]
        add_pad(BOX + "/" + n, "pad_outer", plo, phi)
    # wrap-only: filter the pads against an "everything except wrap and pads" group, and every pad against every flap
    gp = UsdPhysics.CollisionGroup.Define(st, PK + "/cg_pads")
    gp.GetCollidersCollectionAPI().CreateIncludesRel().SetTargets(pads)
    go = UsdPhysics.CollisionGroup.Define(st, PK + "/cg_not_wrap")
    oc = go.GetCollidersCollectionAPI()
    oc.CreateIncludesRel().SetTargets([q.GetPath() for q in st.GetPseudoRoot().GetChildren()])
    oc.CreateExcludesRel().SetTargets([Sdf.Path(WRAP)] + pads)
    gp.CreateFilteredGroupsRel().SetTargets([go.GetPath()])
    lidb = [Sdf.Path(BOX + "/" + n) for n in LIDS]
    for pp in pads:
        own = str(pp).split("/")[-2]
        UsdPhysics.FilteredPairsAPI.Apply(st.GetPrimAtPath(pp)).CreateFilteredPairsRel().SetTargets(
            [b for b in lidb if b.name != own] + ([Sdf.Path(BASE)] if own != "base" else []))
    done.append("pads %s" % [str(p) for p in pads])

# 2. flap inertia from geometry + armature
for n in LIDS:
    lp = st.GetPrimAtPath(BOX + "/" + n)
    for at in ("physics:diagonalInertia", "physics:principalAxes"):
        if lp.GetAttribute(at).IsAuthored(): lp.RemoveProperty(at); done.append("%s %s removed" % (n, at))
    arm = PhysxSchema.PhysxJointAPI.Apply(st.GetPrimAtPath(BOX + "/crease_" + n)).CreateArmatureAttr()
    if abs((arm.Get() or 0) - ARMATURE) > 1e-9: arm.Set(ARMATURE); done.append("%s armature %g" % (n, ARMATURE))

# 3. floor pad mass
pm = UsdPhysics.MassAPI.Apply(st.GetPrimAtPath(BASE + "/pad_collider")).CreateMassAttr()
if pm.Get() != 1e-6: pm.Set(1e-6); done.append("floor pad mass 1e-6 kg")

if done:
    st.GetRootLayer().Save()
print("patched %s:" % SCENE if done else "already patched: %s" % SCENE)
for d in done: print("  -", d)
