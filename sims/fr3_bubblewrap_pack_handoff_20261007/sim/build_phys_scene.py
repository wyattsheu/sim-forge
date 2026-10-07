#!/usr/bin/env python3
"""build_phys_scene.py — scene_final_ui.usd -> scene_final_phys.usd
Wrap = live surface deformable (rest shape = wrapped shape), Mug = dynamic rigid body
with convex-frustum body + handle-sphere colliders. Everything else unchanged except the
PhysicsScene GPU settings needed by deformables (documented in ATTEMPTS.md).

  cd sim && /isaac-sim/python.sh build_phys_scene.py            # -> ../scene_final_phys.usd(預設參數 = 交付版)
  /isaac-sim/python.sh build_phys_scene.py --out /tmp/x.usd --no_bake

Two-stage pre-settle (forge.py recipe) through the UI path (open_stage -> timeline.play ->
app.update), then settled points are written into points + restShapePoints (velocities 0)
and the mug pose is baked — both expressed relative to the carton base so a small base drift
during the settle doesn't offset the package.
"""
import argparse, os, sys, math, json
HERE = os.path.dirname(os.path.abspath(__file__))
H = os.path.dirname(HERE)                       # 交付包根目錄(sim/ 的上一層)
ap = argparse.ArgumentParser()
ap.add_argument("--scene", default=H + "/scene_final_ui.usd")
ap.add_argument("--mugstl", default=H + "/sim/mug.stl")
ap.add_argument("--out", default=os.path.join(H, "scene_final_phys.usd"))
ap.add_argument("--log", default=os.path.join(H, "logs", "build_phys.log"))
ap.add_argument("--no_bake", action="store_true")
ap.add_argument("--settle1", type=float, default=2.0, help="s, mug kinematic")
ap.add_argument("--settle2", type=float, default=4.0, help="s, mug dynamic")
# wrap material (DEMO run_demo.sh: --young 2e4 --bend 4 --thick 0.004; wrap_sim FRIC 0.8 DENS 100)
ap.add_argument("--young", type=float, default=2e4)
ap.add_argument("--poisson", type=float, default=0.45)
ap.add_argument("--thick", type=float, default=0.004)
ap.add_argument("--bend", type=float, default=4.0)
ap.add_argument("--fric", type=float, default=0.8)
ap.add_argument("--dens", type=float, default=100.0)
ap.add_argument("--edamp", type=float, default=0.85)
ap.add_argument("--bdamp", type=float, default=0.85)
ap.add_argument("--ldamp", type=float, default=0.6)
ap.add_argument("--solver", type=int, default=64)
ap.add_argument("--cont", type=float, default=0.005)
ap.add_argument("--rest", type=float, default=0.001)
ap.add_argument("--selfcol", type=int, default=1)
ap.add_argument("--sleepy", type=int, default=1, help="wrap_sim DEMO sleep params: settlingDamping 10 / settlingThreshold 0.1 / sleepThreshold 0.05")
ap.add_argument("--pair_freq", type=int, default=2)
ap.add_argument("--col_mult", type=int, default=2)
# mug
ap.add_argument("--mug_mass", type=float, default=0.32)
ap.add_argument("--mug_fric", type=float, default=0.9)
ap.add_argument("--mug_ldamp", type=float, default=0.12)
ap.add_argument("--mug_adamp", type=float, default=0.6)
ap.add_argument("--mug_cont", type=float, default=0.004)
ap.add_argument("--mug_rest", type=float, default=0.0)
# carton floor pad (wrap_sim --base_collider_pad), filtered against the table colliders
ap.add_argument("--pad", type=float, default=0.02, help="m; 0 = no pad")
# carton feel in the UI (2026-10-07): weaker lid spring so a mouse can open lids (+ lid_latch.py keeps them open),
# damped base so force-mode mouse grab doesn't overshoot when lifting
ap.add_argument("--lid_stiff", type=float, default=0.012, help="N*m/deg; scene_final_ui.usd has 0.056 (mouse only reached 15 deg)")
ap.add_argument("--lid_damp", type=float, default=0.003)
ap.add_argument("--base_damp", default="2,2", help="carton base linear,angular damping; '' = keep")
a = ap.parse_args()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
os.makedirs(os.path.dirname(a.log), exist_ok=True)

from isaacsim import SimulationApp
sim = SimulationApp({"headless": True, "extra_args": ["--/persistent/physics/enableDeformableBeta=true"]})
import carb, omni.physx.bindings._physx as pxb
_s = carb.settings.get_settings()
_s.set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)          # exactly as wrap_sim.py
_s.set_bool("/physics/updateToUsd", True)
_s.set_bool("/physics/updateVelocitiesToUsd", True)
import numpy as np, trimesh, omni.usd, omni.timeline
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, PhysxSchema, Gf, Sdf, Vt
from omni.physx.scripts import deformableUtils

LOG = open(a.log, "w")
def P(*s):
    t = " ".join(str(x) for x in s); print(t, flush=True); LOG.write(t + "\n"); LOG.flush()
P("args", vars(a))
P("beta flag:", _s.get("/persistent/physics/enableDeformableBeta"), "updateToUsd:", _s.get("/physics/updateToUsd"))

def sa(prim, n, v, tn=None):
    at = prim.GetAttribute(n)
    if not at or not at.IsValid():
        if tn is None:
            P("  !! missing attr", prim.GetPath(), n); return
        at = prim.CreateAttribute(n, tn)
    at.Set(v)

PK = "/World/Packed"; WRAP = PK + "/Wrap"; MUG = PK + "/Mug"; BASE = PK + "/Box/base"

# ───────────────────────────── author ─────────────────────────────
st = Usd.Stage.Open(a.scene)
layer = st.GetRootLayer()

# -- PhysicsScene: deformables need GPU dynamics/broadphase (schema defaults are already GPU,
#    authored explicitly) + wrap_sim.py GPU capacities. Solver/Hz/iterations untouched.
ps = st.GetPrimAtPath("/physicsScene")
px = PhysxSchema.PhysxSceneAPI(ps)
px.CreateEnableGPUDynamicsAttr(True); px.CreateBroadphaseTypeAttr("GPU")
px.CreateGpuMaxDeformableSurfaceContactsAttr(4 * 1048576)
px.CreateGpuCollisionStackSizeAttr(128 * 1024 * 1024)
# timeline: endTimeCode 0 stops Play immediately in the UI (FINDINGS #12) -> long timeline
st.SetTimeCodesPerSecond(60.0); st.SetStartTimeCode(0.0); st.SetEndTimeCode(1000000.0)

# -- Wrap: surface deformable
wm = UsdGeom.Mesh(st.GetPrimAtPath(WRAP)); wp = wm.GetPrim()
W0 = np.array(wm.GetPointsAttr().Get(), float)
tris = np.array(wm.GetFaceVertexIndicesAttr().Get(), int).reshape(-1, 3)
phm = UsdShade.Material.Define(st, PK + "/wrapPhys"); pp = phm.GetPrim()
pp.ApplyAPI("OmniPhysicsBaseMaterialAPI")
sa(pp, "omniphysics:dynamicFriction", a.fric); sa(pp, "omniphysics:density", a.dens)
pp.ApplyAPI("OmniPhysicsDeformableMaterialAPI")
sa(pp, "omniphysics:youngsModulus", a.young); sa(pp, "omniphysics:poissonsRatio", a.poisson)
pp.ApplyAPI("OmniPhysicsSurfaceDeformableMaterialAPI")
sa(pp, "omniphysics:surfaceThickness", a.thick); sa(pp, "omniphysics:surfaceBendStiffness", a.bend)
pp.ApplyAPI("PhysxSurfaceDeformableMaterialAPI")
sa(pp, "physxDeformableMaterial:elasticityDamping", a.edamp)
sa(pp, "physxDeformableMaterial:bendDamping", a.bdamp)
ok = deformableUtils.set_physics_surface_deformable_body(st, wp.GetPath())
P("set_physics_surface_deformable_body:", ok)
wp.ApplyAPI("PhysxSurfaceDeformableBodyAPI")
sa(wp, "omniphysics:restShapePoints", Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in W0]))
sa(wp, "omniphysics:restBendAnglesDefault", "restShapeDefault", Sdf.ValueTypeNames.Token)
sa(wp, "physxDeformableBody:selfCollision", bool(a.selfcol))
sa(wp, "physxDeformableBody:solverPositionIterationCount", int(a.solver))
sa(wp, "physxDeformableBody:linearDamping", float(a.ldamp))
sa(wp, "physxDeformableBody:maxDepenetrationVelocity", 0.5)
sa(wp, "physxDeformableBody:collisionPairUpdateFrequency", int(a.pair_freq))
sa(wp, "physxDeformableBody:collisionIterationMultiplier", int(a.col_mult))
if a.sleepy:
    sa(wp, "physxDeformableBody:settlingDamping", 10.0, Sdf.ValueTypeNames.Float)
    sa(wp, "physxDeformableBody:settlingThreshold", 0.10, Sdf.ValueTypeNames.Float)
    sa(wp, "physxDeformableBody:sleepThreshold", 0.05, Sdf.ValueTypeNames.Float)
if a.selfcol:
    # self-collision filter pose = flat 400 mm sheet (res 34), FINDINGS #9
    n = 34; L = 0.4
    flat = [Gf.Vec3f(-L/2 + i*L/n, -L/2 + j*L/n, 0.0) for j in range(n+1) for i in range(n+1)]
    wp.ApplyAPI("OmniPhysicsDeformablePoseAPI", "filter")
    sa(wp, "deformablePose:filter:omniphysics:purposes", Vt.TokenArray(["selfCollisionFilterPose"]), Sdf.ValueTypeNames.TokenArray)
    sa(wp, "deformablePose:filter:omniphysics:points", Vt.Vec3fArray(flat), Sdf.ValueTypeNames.Point3fArray)
pc = PhysxSchema.PhysxCollisionAPI.Apply(wp)
pc.CreateRestOffsetAttr().Set(a.rest); pc.CreateContactOffsetAttr().Set(a.cont)
wm.CreateVelocitiesAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0, 0, 0)] * len(W0)))
UsdShade.MaterialBindingAPI.Apply(wp).Bind(phm, UsdShade.Tokens.weakerThanDescendants, "physics")
area = 0.0
for t_ in tris:
    area += 0.5*np.linalg.norm(np.cross(W0[t_[1]]-W0[t_[0]], W0[t_[2]]-W0[t_[0]]))
P("wrap: %d verts %d tris, area %.4f m2 -> mass ~ %.1f g (density x thickness x area)"
  % (len(W0), len(tris), area, a.dens*a.thick*area*1e3))

# -- Mug: Mesh -> Xform rigid body + /visual mesh + colliders
MW = np.array(UsdGeom.Mesh(st.GetPrimAtPath(MUG)).GetPointsAttr().Get(), float)
tm = trimesh.load(a.mugstl); V = np.asarray(tm.vertices) * 1e-3
A_, B_ = V - V.mean(0), MW - MW.mean(0)
U, S_, Vt_ = np.linalg.svd(A_.T @ B_)
D = np.diag([1, 1, np.sign(np.linalg.det(Vt_.T @ U.T))]); R = Vt_.T @ D @ U.T
# mug local frame: stl frame shifted so origin = body axis at z = 0 (stl: axis = +z)
Vm = V * 1e3
cy = (Vm[:, 1].min() + Vm[:, 1].max()) / 2
xs = []
for zz in np.arange(3, 105, 4):
    s = np.abs(Vm[:, 2] - zz) < 1.5
    if s.sum() > 10:
        xs.append(Vm[s, 0].min() + (Vm[s, 1].max() - Vm[s, 1].min()) / 2)
cx = float(np.median(xs))
C = np.array([cx, cy, 0.0]) * 1e-3
VL = V - C                                  # local points (m)
t = MW.mean(0) - R @ V.mean(0) + R @ C      # MW = R @ VL + t
res = np.abs((R @ VL.T).T + t - MW).max()
P("mug: R=%s t=%s mm  fit resid %.2e mm" % (np.round(R, 3).tolist(), np.round(t*1e3, 2).tolist(), res*1e3))
r_ax = np.hypot(VL[:, 0], VL[:, 1]); z_ = VL[:, 2]
def prof(z0, w=2.0e-3):
    s = (np.abs(z_ - z0) < w)
    return float(np.max(r_ax[s][r_ax[s] < np.percentile(r_ax[s], 60) + 0.004])) if s.sum() else 0.0
zmax = float(z_.max())
# body radius profile from the -y half (handle is at +x), robust
def rprof(z0, w=2.0e-3):
    s = (np.abs(z_ - z0) < w) & (VL[:, 0] < 0.02)
    return float(r_ax[s].max())
zc = [0.0, 0.012, 0.030, 0.055, zmax]
rc = [rprof(max(min(z0, zmax - 0.0015), 0.0015)) for z0 in zc]
P("mug body profile z(mm)->r(mm):", [(round(z0*1e3, 1), round(r*1e3, 2)) for z0, r in zip(zc, rc)])
handle = (r_ax > np.interp(z_, zc, rc) + 0.0015)
HP = VL[handle]
P("mug handle verts %d, x %.1f..%.1f y %.1f..%.1f z %.1f..%.1f mm" % (len(HP), *(np.array(
    [HP[:, 0].min(), HP[:, 0].max(), HP[:, 1].min(), HP[:, 1].max(), HP[:, 2].min(), HP[:, 2].max()])*1e3)))

Sdf.CopySpec(layer, Sdf.Path(MUG), layer, Sdf.Path(PK + "/_MugTmp"))
st.RemovePrim(MUG)
mx = UsdGeom.Xform.Define(st, MUG); mp = mx.GetPrim()
Sdf.CopySpec(layer, Sdf.Path(PK + "/_MugTmp"), layer, Sdf.Path(MUG + "/visual"))
st.RemovePrim(PK + "/_MugTmp")
vis = UsdGeom.Mesh(st.GetPrimAtPath(MUG + "/visual"))
vis.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in VL]))
vis.CreateExtentAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, VL.min(0))), Gf.Vec3f(*map(float, VL.max(0)))]))
_Mc = np.eye(4); _Mc[:3, :3] = R; _Mc[:3, 3] = t          # column convention
M = Gf.Matrix4d(*[float(x) for x in _Mc.T.flatten()])   # USD row-vector convention: p_parent = p_local * M
mx.AddTransformOp().Set(M)
mphm = UsdShade.Material.Define(st, PK + "/mugPhys")
_m = UsdPhysics.MaterialAPI.Apply(mphm.GetPrim())
_m.CreateStaticFrictionAttr(a.mug_fric); _m.CreateDynamicFrictionAttr(a.mug_fric); _m.CreateRestitutionAttr(0.05)

def coll(prim, cont, rest):
    UsdPhysics.CollisionAPI.Apply(prim)
    c = PhysxSchema.PhysxCollisionAPI.Apply(prim)
    c.CreateContactOffsetAttr().Set(cont); c.CreateRestOffsetAttr().Set(rest)
    UsdGeom.Imageable(prim).CreatePurposeAttr().Set(UsdGeom.Tokens.guide)
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(mphm, UsdShade.Tokens.weakerThanDescendants, "physics")

# body = stacked convex frusta (each 2 rings x 32 = 64 verts -> GPU convex limit), outer profile
NR = 32
for k in range(len(zc) - 1):
    z0, z1, r0, r1 = zc[k], zc[k+1], rc[k], rc[k+1]
    ring = lambda z, r: [(r*math.cos(2*math.pi*i/NR), r*math.sin(2*math.pi*i/NR), z) for i in range(NR)]
    pts = ring(z0, r0) + ring(z1, r1)
    fv = []
    for i in range(NR):
        i2 = (i + 1) % NR
        fv += [i, i2, NR + i2, i, NR + i2, NR + i]
    for i in range(1, NR - 1):
        fv += [0, i + 1, i, NR, NR + i, NR + i + 1]
    cm = UsdGeom.Mesh.Define(st, MUG + "/col_body_%d" % k)
    cm.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*p) for p in pts]))
    cm.GetFaceVertexCountsAttr().Set([3] * (len(fv)//3)); cm.GetFaceVertexIndicesAttr().Set(fv)
    coll(cm.GetPrim(), a.mug_cont, a.mug_rest)
    UsdPhysics.MeshCollisionAPI.Apply(cm.GetPrim()).CreateApproximationAttr("convexHull")
# handle = sphere chain (forge.py): angular bins around handle centre in the x-z plane
nb = 0
if len(HP):
    xc0 = (HP[:, 0].min() + HP[:, 0].max()) / 2; zc0 = (HP[:, 2].min() + HP[:, 2].max()) / 2
    tube = max(min((HP[:, 1].max() - HP[:, 1].min()) / 2, 0.010), 0.0035)
    ang = np.arctan2(HP[:, 2] - zc0, HP[:, 0] - xc0)
    NB = 16
    b = ((ang + np.pi) / (2*np.pi) * NB).astype(int) % NB
    for bi in range(NB):
        q = HP[b == bi]
        if len(q) < 5: continue
        c = q.mean(0); c[1] = (HP[:, 1].min() + HP[:, 1].max()) / 2
        sp = UsdGeom.Sphere.Define(st, MUG + "/col_handle_%02d" % bi)
        sp.CreateRadiusAttr(float(tube)); UsdGeom.Xformable(sp).AddTranslateOp().Set(Gf.Vec3d(*map(float, c)))
        coll(sp.GetPrim(), a.mug_cont, a.mug_rest); nb += 1
    P("mug handle: %d spheres r=%.1f mm" % (nb, tube*1e3))
UsdPhysics.RigidBodyAPI.Apply(mp)
UsdPhysics.MassAPI.Apply(mp).CreateMassAttr(a.mug_mass)
UsdPhysics.MassAPI(mp).CreateCenterOfMassAttr(Gf.Vec3f(0.0, 0.0, float(zmax*0.45)))   # on axis
prb = PhysxSchema.PhysxRigidBodyAPI.Apply(mp)
prb.CreateLinearDampingAttr(a.mug_ldamp); prb.CreateAngularDampingAttr(a.mug_adamp)
prb.CreateSleepThresholdAttr(0.0005); prb.CreateMaxDepenetrationVelocityAttr(0.4)

# -- optional carton floor pad, filtered against the table so it doesn't lift the carton
if a.pad > 0:
    # 碰撞 mesh 的 purpose 常是 guide/proxy,不含在 default/render 裡會算成空 bbox → 2026-10-07 之前這裡漏掉桌面,pad 被卡死
    bc = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render", "guide", "proxy"])
    rb = bc.ComputeWorldBound(st.GetPrimAtPath(BASE + "/bottom")).ComputeAlignedRange()
    pad = UsdGeom.Cube.Define(st, BASE + "/pad_collider"); pad.CreateSizeAttr(1.0)
    pad.AddTranslateOp().Set(Gf.Vec3d(0, 0, -a.pad/2)); pad.AddScaleOp().Set(Gf.Vec3f(0.267, 0.227, a.pad))
    UsdPhysics.CollisionAPI.Apply(pad.GetPrim()); pad.CreatePurposeAttr(UsdGeom.Tokens.guide)
    pc2 = PhysxSchema.PhysxCollisionAPI.Apply(pad.GetPrim()); pc2.CreateContactOffsetAttr(0.001); pc2.CreateRestOffsetAttr(0.0)
    # find every collider (outside /World/Packed) that intersects the pad volume
    lo, hi = np.array(rb.GetMin()), np.array(rb.GetMax())
    plo, phi = lo - np.array([0.003, 0.003, a.pad + 0.003]), np.array([hi[0]+0.003, hi[1]+0.003, lo[2] + 0.0005])
    tgt = []
    for p in st.Traverse():
        if p.HasAPI(UsdPhysics.CollisionAPI) and not str(p.GetPath()).startswith(PK):
            r = bc.ComputeWorldBound(p).ComputeAlignedRange()
            if r.IsEmpty(): continue
            l2, h2 = np.array(r.GetMin()), np.array(r.GetMax())
            if np.all(l2 <= phi) and np.all(h2 >= plo):
                q = p                                   # 過濾整個剛體(例如 tabletop_link),不只單一碰撞 mesh
                while q and not q.HasAPI(UsdPhysics.RigidBodyAPI) and q.GetParent() and q.GetParent().GetPath() != Sdf.Path.absoluteRootPath:
                    q = q.GetParent()
                if q.GetPath() not in tgt: tgt.append(q.GetPath())
    assert tgt, "pad 下面找不到任何碰撞體?桌面碰撞 mesh 應該要被找到"
    UsdPhysics.FilteredPairsAPI.Apply(pad.GetPrim()).CreateFilteredPairsRel().SetTargets(tgt)
    P("pad %.0f mm under base, filtered vs %s" % (a.pad*1e3, [str(x) for x in tgt]))

for _n in ("fxp", "fxn", "fyp", "fyn"):
    _d = UsdPhysics.DriveAPI.Get(st.GetPrimAtPath(PK + "/Box/crease_" + _n), "angular")
    _d.GetStiffnessAttr().Set(a.lid_stiff); _d.GetDampingAttr().Set(a.lid_damp)
P("lid drives: stiffness %g N*m/deg damping %g" % (a.lid_stiff, a.lid_damp))
if a.base_damp:
    _ld, _ad = [float(v) for v in a.base_damp.split(",")]
    _bp = PhysxSchema.PhysxRigidBodyAPI.Apply(st.GetPrimAtPath(BASE))
    _bp.CreateLinearDampingAttr().Set(_ld); _bp.CreateAngularDampingAttr().Set(_ad)
    P("base damping: linear %g angular %g" % (_ld, _ad))
PRE = a.out if a.no_bake else a.out.replace(".usd", "_prebake.usd")
layer.Export(PRE)
P("authored ->", PRE)
if a.no_bake:
    LOG.close(); sim.close(); sys.exit(0)

# ───────────────────────────── pre-settle (UI path) ─────────────────────────────
ctx = omni.usd.get_context()
ctx.open_stage(PRE)
for _ in range(30): sim.update()
s2 = ctx.get_stage()
def wmat(path):
    return np.array(UsdGeom.Xformable(s2.GetPrimAtPath(path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), float).T  # column conv
def wrap_pts(): return np.array(UsdGeom.Mesh(s2.GetPrimAtPath(WRAP)).GetPointsAttr().Get(), float)
s2.GetPrimAtPath(MUG).GetAttribute("physics:kinematicEnabled").Set(True)
PK_W = wmat(PK); B0 = wmat(BASE)
tl = omni.timeline.get_timeline_interface(); tl.play()
def run(secs, tag):
    t0 = tl.get_current_time(); prev = wrap_pts(); k = 0; last = 0
    while tl.get_current_time() - t0 < secs:
        sim.update(); k += 1
        if k % 15 == 0:
            cur = wrap_pts(); dt = tl.get_current_time() - last; last = tl.get_current_time()
            v = np.linalg.norm(cur - prev, axis=1).max() / max(dt, 1e-6)
            P("  %s t=%.2f maxv %.4f m/s  nan=%s  base dz %.2f mm" % (tag, tl.get_current_time(), v,
              bool(np.isnan(cur).any()), (wmat(BASE)[2, 3] - B0[2, 3])*1e3)); prev = cur
    return k
n1 = run(a.settle1, "ph1(mug kin)")
s2.GetPrimAtPath(MUG).GetAttribute("physics:kinematicEnabled").Set(False)
n2 = run(a.settle2, "ph2(mug dyn)")
Wf = wrap_pts(); Bf = wmat(BASE); Mf = wmat(MUG)
tl.stop()
for _ in range(5): sim.update()
P("settle: %d + %d updates, sim time %.2f s" % (n1, n2, a.settle1 + a.settle2))
# express settled state relative to base, then put it back on the authored base pose
corr = B0 @ np.linalg.inv(Bf)                       # world -> world
Pinv = np.linalg.inv(PK_W)
Wh = np.c_[Wf, np.ones(len(Wf))]
Wn = (Pinv @ corr @ PK_W @ Wh.T).T[:, :3]           # wrap points are in Packed-local frame
Mn = Pinv @ corr @ Mf                               # mug local (parent = Packed)
d = np.linalg.norm(Wn - W0, axis=1)
M0c = np.eye(4); M0c[:3, :3] = R; M0c[:3, 3] = t
dR = Mn[:3, :3] @ M0c[:3, :3].T
P("bake: mug translation (Packed frame) (%.2f, %.2f, %.2f) mm, rotation %.2f deg; mug lowest z %.1f mm (floor top 3.0)"
  % (*((Mn[:3, 3]-t)*1e3), math.degrees(math.acos(max(-1, min(1, (np.trace(dR)-1)/2)))),
     ((Mn[:3, :3] @ VL.T).T + Mn[:3, 3])[:, 2].min()*1e3))
P("bake: wrap z range %.1f..%.1f mm (authored %.1f..%.1f); verts below floor top-1mm: %d"
  % (Wn[:, 2].min()*1e3, Wn[:, 2].max()*1e3, W0[:, 2].min()*1e3, W0[:, 2].max()*1e3, int((Wn[:, 2] < 0.002).sum())))
P("bake: base drift during settle (%.2f, %.2f, %.2f) mm; wrap disp vs authored max %.2f mean %.2f mm; mug disp %.2f mm"
  % (*((Bf[:3, 3] - B0[:3, 3])*1e3), d.max()*1e3, d.mean()*1e3,
     np.linalg.norm(Mn[:3, 3] - np.r_[t])*1e3))
ctx.close_stage()
fs = Usd.Stage.Open(PRE)
fw = UsdGeom.Mesh(fs.GetPrimAtPath(WRAP)); fp = fw.GetPrim()
WV = Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in Wn])
fw.GetPointsAttr().Set(WV); fp.GetAttribute("omniphysics:restShapePoints").Set(WV)
fw.GetVelocitiesAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0, 0, 0)] * len(Wn)))
fw.GetExtentAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, Wn.min(0))), Gf.Vec3f(*map(float, Wn.max(0)))]))
Mrow = Gf.Matrix4d(*[float(x) for x in Mn.T.flatten()])
xf = UsdGeom.Xformable(fs.GetPrimAtPath(MUG)); xf.ClearXformOpOrder()
for op in list(fs.GetPrimAtPath(MUG).GetAuthoredPropertyNames()):
    if op.startswith("xformOp:"): fs.GetPrimAtPath(MUG).RemoveProperty(op)
xf.AddTransformOp().Set(Mrow)
fs.GetPrimAtPath(MUG).GetAttribute("physics:kinematicEnabled").Set(False)
fs.GetRootLayer().Export(a.out)
P("baked ->", a.out)
LOG.close(); sim.close()
