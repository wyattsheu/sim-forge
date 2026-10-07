#!/usr/bin/env python3
"""verify_phys_scene.py — UI-path check (open_stage -> timeline.play -> app.update; physics
settings only from USD) of the physical-wrap scene.  Numbers, no images.

  /isaac-sim/python.sh verify_phys_scene.py SCENE --test A|B|Bm|C [--log out.txt]

A  rest 8 s, nothing touched
B  carry: carton base servoed (velocity set every physics step, body stays dynamic, like a
   stiff hand) along smoothstep --move (default +0.10 m x / +0.10 m z) over 3 s, hold 2 s
Bm carry by PhysX mouse interaction (update_interaction MOUSE_DRAG_*), ray from the side onto
   the carton wall, ray origin moved by --move over 3 s, hold 2 s (forceGrab=1, pickingForce 100)
C  lid-vs-wrap: 3 N downward force on the free half of lower lid fxn for 3 s, then release 2 s
"""
import argparse, os, sys, math
ap = argparse.ArgumentParser()
ap.add_argument("scene")
ap.add_argument("--test", default="A")
ap.add_argument("--log", default="")
ap.add_argument("--secs", type=float, default=8.0)
ap.add_argument("--force", type=float, default=3.0)
ap.add_argument("--warm", type=float, default=1.0, help="B/C: rest before acting (s)")
ap.add_argument("--move", default="0.10,0,0.10", help="B/Bm: carry vector x,y,z (m). ±y runs into the arms' grippers (69 mm away), so default moves in +x")
ap.add_argument("--force_grab", type=int, default=1, help="Bm: 1 = /physics/forceGrab=True (the setting that actually drags; joint mode moves ~1 cm)")
ap.add_argument("--picking_force", type=float, default=70.0, help="Bm: /physics/pickingForce (launcher default 70; 100 flips the carton when lifting by a wall)")
ap.add_argument("--grab_z", type=float, default=0.06, help="Bm: grab height above the carton floor (m) on the +x wall")
ap.add_argument("--base_damping", default="", help="override carton base linear,angular damping before Play, e.g. 2,2")
a = ap.parse_args()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True, "extra_args": ["--/persistent/physics/enableDeformableBeta=true"]})
import carb, omni.physx.bindings._physx as pxb
_s = carb.settings.get_settings()
_s.set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
_s.set_bool("/physics/updateToUsd", True)
_s.set_bool("/physics/updateVelocitiesToUsd", True)
import numpy as np, omni.usd, omni.timeline
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Gf
from omni.physx import get_physx_interface
import omni.physics.tensors as tensors

LOGP = a.log or os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs",
                             "verify_%s_%s.txt" % (os.path.basename(a.scene).replace(".usd", ""), a.test))
os.makedirs(os.path.dirname(LOGP), exist_ok=True)
LOG = open(LOGP, "w")
def P(*s):
    t = " ".join(str(x) for x in s); print(t, flush=True); LOG.write(t + "\n"); LOG.flush()
PK = "/World/Packed"; BOX = PK + "/Box"; BASE = BOX + "/base"; WRAP = PK + "/Wrap"; MUG = PK + "/Mug"
LIDN = ["fxp", "fxn", "fyp", "fyn"]
ctx = omni.usd.get_context(); ctx.open_stage(os.path.abspath(a.scene))
for _ in range(30): sim.update()
st = ctx.get_stage()
P("scene", a.scene, "test", a.test, "beta", _s.get("/persistent/physics/enableDeformableBeta"))
wp = st.GetPrimAtPath(WRAP); mp = st.GetPrimAtPath(MUG)
LIVE_W = wp.HasAPI("OmniPhysicsDeformableBodyAPI") if hasattr(wp, "HasAPI") else False
LIVE_W = "OmniPhysicsDeformableBodyAPI" in wp.GetAppliedSchemas()
LIVE_M = mp.HasAPI(UsdPhysics.RigidBodyAPI)
P("wrap deformable:", LIVE_W, " mug rigid:", LIVE_M)
for n in LIDN:
    d = UsdPhysics.DriveAPI.Get(st.GetPrimAtPath(BOX + "/crease_" + n), "angular")
    P("crease_%s drive stiffness %s damping %s target %s maxForce %s" % (n, d.GetStiffnessAttr().Get(), d.GetDampingAttr().Get(),
      d.GetTargetPositionAttr().Get(), d.GetMaxForceAttr().Get()))
def xfw(path):
    return np.array(UsdGeom.Xformable(st.GetPrimAtPath(path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), float).T
PKW = xfw(PK)                       # static parent of Wrap (and Mug)
def wrap_world():
    p = np.array(UsdGeom.Mesh(wp).GetPointsAttr().Get(), float)
    return (PKW[:3, :3] @ p.T).T + PKW[:3, 3]
if LIVE_M:
    MUGLOC = np.array(UsdGeom.Mesh(st.GetPrimAtPath(MUG + "/visual")).GetPointsAttr().Get(), float)[::8]
else:
    MUGLOC = np.array(UsdGeom.Mesh(mp).GetPointsAttr().Get(), float)[::8]
def mug_world():
    T = xfw(MUG) if LIVE_M else PKW
    return (T[:3, :3] @ MUGLOC.T).T + T[:3, 3]
# lid geometry (lid local): x ±0.1095(lower)/±0.131(upper), y [-2*sy, 0], z [0, 0.003]
LIDGEO = {}
for n in LIDN:
    g = st.GetPrimAtPath(BOX + "/" + n + "/geo")
    sc = g.GetAttribute("xformOp:scale").Get()
    LIDGEO[n] = (float(sc[0]), 2*float(sc[1]))

paths = [BASE] + [BOX + "/" + n for n in LIDN] + ([MUG] if LIVE_M else [])
T0 = [xfw(p_) for p_ in paths]       # authored (pre-Play) poses = reference
W0w = wrap_world(); M0w = mug_world()
if a.base_damping:
    ld, ad = [float(v) for v in a.base_damping.split(",")]
    _bp = PhysxSchema.PhysxRigidBodyAPI.Apply(st.GetPrimAtPath(BOX + "/base"))
    _bp.CreateLinearDampingAttr().Set(ld); _bp.CreateAngularDampingAttr().Set(ad)
    P("base damping override: linear %.2f angular %.2f" % (ld, ad))
tl = omni.timeline.get_timeline_interface()
tl.play(); sim.update()
sv = tensors.create_simulation_view("numpy"); sv.set_subspace_roots("/")
RV = sv.create_rigid_body_view(paths)
P("rigid view count", RV.count, RV.prim_paths if hasattr(RV, "prim_paths") else "")
IDX = np.arange(RV.count, dtype=np.int32)

def qmat(q):  # xyzw
    x, y, z, w = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
def poses():
    tr = np.array(RV.get_transforms(), float)
    out = []
    for r in tr:
        T = np.eye(4); T[:3, :3] = qmat(r[3:7]); T[:3, 3] = r[:3]; out.append(T)
    return out
def inv(T): return np.linalg.inv(T)
def apply(T, p): return (T[:3, :3] @ p.T).T + T[:3, 3]
TB0 = T0[0]
_T1 = poses(); P("first-update base jump (mm)", np.round((_T1[0][:3, 3]-TB0[:3, 3])*1e3, 2))
REL0 = [inv(TB0) @ T0[1+i] for i in range(4)]
def lid_angles(T):
    out = []
    for i in range(4):
        Rr = (inv(REL0[i]) @ inv(T[0]) @ T[1+i])[:3, :3]
        out.append(math.degrees(math.atan2(Rr[2, 1], Rr[1, 1])))
    return np.array(out)
W0b = apply(inv(TB0), W0w); M0b = apply(inv(TB0), M0w)
CAV = dict(x=0.132, y=0.112, zlo=0.003, zhi=0.134)
def outside(pb, tol):
    return int(np.sum((np.abs(pb[:, 0]) > CAV["x"] + tol) | (np.abs(pb[:, 1]) > CAV["y"] + tol) |
                      (pb[:, 2] < CAV["zlo"] - tol) | (pb[:, 2] > CAV["zhi"] + tol)))
P("start: wrap outside cavity (tol 0/1/2 mm): %d/%d/%d of %d ; mug(1/8 verts) %d/%d/%d of %d"
  % (outside(W0b, 0), outside(W0b, .001), outside(W0b, .002), len(W0b), outside(M0b, 0), outside(M0b, .001), outside(M0b, .002), len(M0b)))
P("start: base world pos (mm)", np.round(TB0[:3, 3]*1e3, 2), " wrap z range (base frame) %.1f..%.1f mm" % (W0b[:, 2].min()*1e3, W0b[:, 2].max()*1e3))

# lid-fxn geometric angles (lid frame at start): angle at which the closing lid reaches a point
def hit_angle(pw, n):
    Tl = T0[1 + LIDN.index(n)]; q = apply(inv(Tl), pw)
    hx, L = LIDGEO[n]
    r = np.hypot(q[:, 1], q[:, 2])
    sel = (np.abs(q[:, 0]) < hx) & (r < L) & (q[:, 1] < 0)
    if not sel.any(): return None, 0
    ang = np.degrees(np.arctan2(-q[sel, 2], -q[sel, 1]))
    return float(ang.min()), int((ang < 0).sum())
for n in ("fxn", "fxp"):
    aw, pw_ = hit_angle(W0w, n); am, pm_ = hit_angle(M0w, n)
    P("lid %s: wrap first contact at %+.2f deg (%d verts already above underside); mug first contact at %+.2f deg"
      % (n, aw if aw is not None else float("nan"), pw_, am if am is not None else float("nan")))

# ---------------------------------------------------------------- actions
state = dict(t=0.0, act=None)
def smooth(u): u = min(max(u, 0.0), 1.0); return u*u*(3 - 2*u)
MOVE = np.array([float(v) for v in a.move.split(",")]); TMOVE = 3.0; THOLD = 2.0
def on_step(dt):
    state["t"] += dt
    t = state["t"]
    if a.test == "B" and t >= a.warm:
        u = (t - a.warm) / TMOVE
        s = smooth(u)
        ds = (6*u*(1-u))/TMOVE if 0 <= u <= 1 else 0.0
        tr = np.array(RV.get_transforms(), float)
        p = tr[0, :3]; q = tr[0, 3:7]
        pd = TB0[:3, 3] + MOVE*s; vd = MOVE*ds
        v = vd + 20.0*(pd - p)
        # rotation error q * q0^-1 -> axis angle
        Rerr = qmat(q) @ TB0[:3, :3].T
        ang = math.acos(max(-1.0, min(1.0, (np.trace(Rerr) - 1)/2)))
        w = np.zeros(3)
        if ang > 1e-6:
            ax = np.array([Rerr[2, 1]-Rerr[1, 2], Rerr[0, 2]-Rerr[2, 0], Rerr[1, 0]-Rerr[0, 1]])/(2*math.sin(ang))
            w = -20.0*ang*ax
        vel = np.array(RV.get_velocities(), float)
        vel[0, :3] = v; vel[0, 3:] = w
        RV.set_velocities(vel.astype(np.float32), np.array([0], dtype=np.int32))
    if a.test == "C" and a.warm <= t < a.warm + 3.0:
        i = 1 + LIDN.index("fxn")
        tr = np.array(RV.get_transforms(), float)
        Tl = np.eye(4); Tl[:3, :3] = qmat(tr[i, 3:7]); Tl[:3, 3] = tr[i, :3]
        pt = apply(Tl, np.array([[0.0, -0.085, 0.003]]))[0]           # 85 mm out from the hinge, top face
        F = np.zeros((RV.count, 3), np.float32); Tq = np.zeros((RV.count, 3), np.float32); Pp = np.zeros((RV.count, 3), np.float32)
        F[i] = [0, 0, -a.force]; Pp[i] = pt
        RV.apply_forces_and_torques_at_position(F, Tq, Pp, np.array([i], dtype=np.int32), True)
sub = get_physx_interface().subscribe_physics_step_events(on_step)

# mouse drag (Bm)
drag = dict(on=False)
if a.test == "Bm":
    _s.set_bool("/physics/mouseInteractionEnabled", True); _s.set_bool("/physics/mouseGrab", True)
    _s.set_bool("/physics/forceGrab", a.force_grab == 1); _s.set_float("/physics/pickingForce", a.picking_force)
    from omni.physx.bindings._physx import PhysicsInteractionEvent as PIE
    # ray from +x side onto the carton wall facing +x (world x = 95 mm), 40 mm below the rim
    O0 = np.array([0.6, TB0[1, 3], TB0[2, 3] + a.grab_z]); DIR = carb.Float3(-1.0, 0.0, 0.0)

total = a.secs if a.test == "A" else (a.warm + TMOVE + THOLD if a.test in ("B", "Bm") else a.warm + 5.0)
mxlid = np.zeros(4); mx_dz = 0.0; nan_seen = False; k = 0; last_print = -1
lid_c = []
while state["t"] < total:
    t = state["t"]
    if a.test == "Bm":
        if not drag["on"] and t >= a.warm:
            get_physx_interface().update_interaction(carb.Float3(*O0), DIR, PIE.MOUSE_DRAG_BEGAN); drag["on"] = True
        elif drag["on"]:
            s = smooth((t - a.warm)/TMOVE)
            get_physx_interface().update_interaction(carb.Float3(*(O0 + MOVE*s)), DIR, PIE.MOUSE_DRAG_CHANGED)
    sim.update(); k += 1
    T = poses(); TB = T[0]
    Ww = wrap_world(); Mw = mug_world()
    if np.isnan(Ww).any() or np.isnan(TB).any(): nan_seen = True
    L_ = lid_angles(T); mxlid = np.maximum(mxlid, np.abs(L_))
    mx_dz = max(mx_dz, abs(TB[2, 3] - TB0[2, 3]))
    if a.test == "C": lid_c.append((state["t"], L_[1]))
    if int(state["t"]*2) != last_print or state["t"] >= total:
        last_print = int(state["t"]*2)
        Wb = apply(inv(TB), Ww); Mb = apply(inv(TB), Mw)
        dw = np.linalg.norm(Wb - W0b, axis=1); dm = np.linalg.norm(Mb - M0b, axis=1)
        P("t=%5.2f base d(%+6.1f,%+6.1f,%+6.1f)mm | rel-to-carton: wrap max %6.1f mean %5.1f cen(%+5.1f,%+5.1f,%+5.1f) mug mean %5.1f mm | out(1mm) wrap %4d mug %4d | lids %s | nan %s"
          % (state["t"], *((TB[:3, 3]-TB0[:3, 3])*1e3), dw.max()*1e3, dw.mean()*1e3, *((Wb.mean(0)-W0b.mean(0))*1e3),
             dm.mean()*1e3, outside(Wb, .001), outside(Mb, .001), " ".join("%s=%+5.1f" % (n, v) for n, v in zip(LIDN, L_)), nan_seen))
if a.test == "Bm" and drag["on"]:
    get_physx_interface().update_interaction(carb.Float3(*(O0 + MOVE)), DIR, PIE.MOUSE_DRAG_ENDED)
T = poses(); TB = T[0]
Wb = apply(inv(TB), wrap_world()); Mb = apply(inv(TB), mug_world())
dw = np.linalg.norm(Wb - W0b, axis=1); dm = np.linalg.norm(Mb - M0b, axis=1)
P("===== RESULT %s (%s) after %.2f s sim, %d updates =====" % (a.test, os.path.basename(a.scene), state["t"], k))
P("base displacement (mm) (%.2f, %.2f, %.2f); max |dz| %.2f mm; base tilt %.2f deg"
  % (*((TB[:3, 3]-TB0[:3, 3])*1e3), mx_dz*1e3, math.degrees(math.acos(max(-1, min(1, (np.trace(TB[:3, :3] @ TB0[:3, :3].T)-1)/2))))))
P("wrap rel. carton: max %.2f mean %.2f mm, centroid shift (%.2f, %.2f, %.2f) mm" % (dw.max()*1e3, dw.mean()*1e3, *((Wb.mean(0)-W0b.mean(0))*1e3)))
P("mug  rel. carton: mean vertex disp %.2f mm, centroid shift (%.2f, %.2f, %.2f) mm" % (dm.mean()*1e3, *((Mb.mean(0)-M0b.mean(0))*1e3)))
P("outside cavity (tol 0/1/2 mm): wrap %d/%d/%d of %d ; mug %d/%d/%d of %d" % (outside(Wb, 0), outside(Wb, .001), outside(Wb, .002), len(Wb),
  outside(Mb, 0), outside(Mb, .001), outside(Mb, .002), len(Mb)))
P("wrap z range (carton frame) %.1f..%.1f mm; NaN seen %s" % (Wb[:, 2].min()*1e3, Wb[:, 2].max()*1e3, nan_seen))
P("lid angles now %s ; max |angle| %s" % (" ".join("%s=%+.2f" % (n, v) for n, v in zip(LIDN, lid_angles(T))),
  " ".join("%s=%.2f" % (n, v) for n, v in zip(LIDN, mxlid))))
if a.test == "C":
    arr = np.array(lid_c)
    push = arr[(arr[:, 0] > a.warm) & (arr[:, 0] < a.warm + 3.0)]
    P("C: fxn angle max during push %+.2f deg, at end of push %+.2f deg, after release %+.2f deg"
      % (push[:, 1].max(), push[-1, 1], arr[-1, 1]))
    Tl = T[1 + LIDN.index("fxn")]; q = apply(inv(Tl), wrap_world()); hx, Ll = LIDGEO["fxn"]
    fp = (np.abs(q[:, 0]) < hx) & (q[:, 1] < 0) & (q[:, 1] > -Ll)
    P("C: wrap verts under lid footprint %d; above lid underside (passed into/through lid) %d; above lid top %d; max penetration %.2f mm"
      % (fp.sum(), int((fp & (q[:, 2] > 0)).sum()), int((fp & (q[:, 2] > 0.003)).sum()), max(0.0, q[fp, 2].max()*1e3) if fp.any() else 0))
sub = None
tl.stop(); LOG.close(); sim.close()
