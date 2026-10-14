#!/usr/bin/env python3
"""crease_test.py — fold one flap like a crease bending tester and record the moment-angle curve.

The carton base is clamped (kinematic), a stiff PD "fixture" torque turns the flap about its hinge at a constant
angular speed to the tracking angle, holds, then lets go and records where the flap comes to rest (spring-back).
This is the protocol of Nagasawa et al. (2019): fold to 90 deg, hold, release, read the release angle.

  cd sim
  python.sh crease_test.py ../scene_final_phys.usd --lid fyp --track 90            # fold to 90, release
  python.sh crease_test.py ../scene_final_phys.usd --lid fyp --track 270           # fold down the outside of the wall
  python.sh crease_test.py ../scene_final_phys.usd --lid fyp --track 90 --cycles 3 # repeated folds (softening)
  ... --model latch|spring   (old flap models, for comparison)   --video out.mp4 --label "..."

Writes <out>.csv (t, phase, angle, reference, fixture torque, gravity torque, crease model moment, plastic set,
yield) and <out>.txt (summary). Angles: 0 shut, positive = open (90 upright, 180 out like a shelf, 270 down the wall).
"""
import argparse, os, sys, math, json
ap = argparse.ArgumentParser()
ap.add_argument("scene")
ap.add_argument("--lid", default="fyp")
ap.add_argument("--track", type=float, default=90.0, help="tracking (maximum) fold angle, deg")
ap.add_argument("--omega", type=float, default=60.0, help="fold speed deg/s (Nagasawa 2019 used 0.2 rps = 72 deg/s)")
ap.add_argument("--hold", type=float, default=1.0, help="s held at the tracking angle")
ap.add_argument("--release", type=float, default=3.0, help="s free after release")
ap.add_argument("--cycles", type=int, default=1)
ap.add_argument("--model", default="plastic", choices=["plastic", "latch", "spring"])
ap.add_argument("--empty", action="store_true", help="remove wrap + mug: the bare crease, like a bending tester")
ap.add_argument("--kp", type=float, default=1.5, help="fixture N*m/rad")
ap.add_argument("--kd", type=float, default=0.03, help="fixture N*m*s/rad")
ap.add_argument("--out", default="", help="output prefix (default logs/crease_<lid>_<track>_<model>)")
ap.add_argument("--video", default="")
ap.add_argument("--label", default="")
ap.add_argument("--res", default="1280x720")
a = ap.parse_args()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
W_, H_ = [int(v) for v in a.res.split("x")]
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True, "width": W_, "height": H_})
import carb, numpy as np, omni.usd, omni.timeline, omni.kit.app
import omni.physx.bindings._physx as pxb
_s = carb.settings.get_settings()
if hasattr(pxb, "SETTING_ENABLE_DEFORMABLE_BETA"): _s.set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
_s.set_bool("/physics/updateToUsd", True)
omni.kit.app.get_app().get_extension_manager().set_extension_enabled_immediate("omni.physx.tensors", True)
import omni.physics.tensors as tensors
from omni.physx import get_physx_interface
from pxr import Usd, UsdGeom, UsdPhysics, Gf

OUT = a.out or os.path.join(HERE, "logs", "crease_%s_%d_%s%s%s" % (a.lid, int(a.track), a.model, "_x%d" % a.cycles if a.cycles > 1 else "", "_empty" if a.empty else ""))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
LOG = open(OUT + ".txt", "w")
def P(*s):
    t = " ".join(str(x) for x in s); print(t, flush=True); LOG.write(t + "\n"); LOG.flush()

BOX = "/World/Packed/Box"; BASE = BOX + "/base"; LID = BOX + "/" + a.lid
ctx = omni.usd.get_context(); ctx.open_stage(os.path.abspath(a.scene))
for _ in range(30): sim.update()
st = ctx.get_stage()
# clamp the carton (tester jaw): a fixed joint base -> world (articulation links cannot be kinematic)
_fj = UsdPhysics.FixedJoint.Define(st, "/World/crease_test_clamp"); _fj.CreateBody1Rel().SetTargets([BASE])
_tb = np.array(UsdGeom.Xformable(st.GetPrimAtPath(BASE)).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), float)
_fj.CreateLocalPos0Attr(Gf.Vec3f(*map(float, _tb[3, :3]))); _fj.CreateLocalPos1Attr(Gf.Vec3f(0, 0, 0))
_q = Gf.Matrix4d(*_tb.flatten()).ExtractRotationQuat(); _fj.CreateLocalRot0Attr(Gf.Quatf(_q)); _fj.CreateLocalRot1Attr(Gf.Quatf(1, 0, 0, 0))
if a.empty:
    for _p in ("/World/Packed/Wrap", "/World/Packed/Mug"): st.GetPrimAtPath(_p).SetActive(False)
j = st.GetPrimAtPath(BOX + "/crease_" + a.lid)
drv = UsdPhysics.DriveAPI.Get(j, "angular")
P("scene", a.scene, "lid", a.lid, "model", a.model, "track", a.track, "omega", a.omega, "cycles", a.cycles)
P("drive k %.4f N*m/rad, c %.5f N*m*s/rad; limits %s..%s; crease:yieldMoment %s" % (
    drv.GetStiffnessAttr().Get()*180/math.pi, drv.GetDampingAttr().Get()*180/math.pi,
    UsdPhysics.RevoluteJoint(j).GetLowerLimitAttr().Get(), UsdPhysics.RevoluteJoint(j).GetUpperLimitAttr().Get(),
    j.GetAttribute("crease:yieldMoment").Get() if j.GetAttribute("crease:yieldMoment") else None))
if a.model == "plastic":
    p = os.path.join(HERE, "crease_plastic.py"); exec(compile(open(p).read(), p, "exec"), globals())
elif a.model == "latch":
    p = os.path.join(HERE, "lid_latch.py"); exec(compile(open(p).read(), p, "exec"), globals())

def xfw(path):
    return np.array(UsdGeom.Xformable(st.GetPrimAtPath(path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), float).T
TB = xfw(BASE); TL0 = xfw(LID)
HINGE = TL0[:3, 3].copy()                       # lid origin = hinge point (make_carton_P: lid xform at the hinge)
AX = TL0[:3, :3] @ np.array([1.0, 0, 0])        # hinge axis (lid local X); opening = negative rotation about AX

# camera: look along the hinge axis so the fold is seen in profile
REC = None
if a.video:
    import imageio, omni.replicator.core as rep
    from PIL import Image, ImageDraw, ImageFont
    cav = TB[:3, 3] + np.array([0, 0, 0.07])
    side = np.cross(AX, [0, 0, 1.0]); side /= np.linalg.norm(side)
    if np.dot(side, HINGE - cav) < 0: side = -side          # 'side' points out of the box through this hinge
    tgt = HINGE + side*0.06 - np.array([0, 0, 0.02])
    eye = tgt + AX*0.75 + side*0.12 + np.array([0, 0, 0.10])
    cam = rep.create.camera(focal_length=18.0, clipping_range=(0.01, 100.0), position=tuple(map(float, eye)), look_at=tuple(map(float, tgt)))
    rp = rep.create.render_product(cam, (W_, H_)); rgb = rep.AnnotatorRegistry.get_annotator("rgb"); rgb.attach([rp])
    try: F1 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30); F2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except Exception: F1 = F2 = ImageFont.load_default()
    REC = imageio.get_writer(a.video, fps=30, codec="libx264", quality=8, pixelformat="yuv420p")

tl = omni.timeline.get_timeline_interface(); tl.play(); sim.update()
sv = tensors.create_simulation_view("numpy", stage_id=ctx.get_stage_id()); sv.set_subspace_roots("/")
RV = sv.create_rigid_body_view([LID])
MASS = float(np.array(RV.get_masses(), float).ravel()[0])
COMS = np.array(RV.get_coms(), float).reshape(-1, 7)[0, :3]       # body-frame centre of mass
P("lid mass %.4f kg, com (body) %s mm" % (MASS, np.round(COMS*1e3, 1)))
def qmat(q):
    x, y, z, w = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
R0 = TL0[:3, :3]
S = dict(t=0.0, theta=0.0, last=None, phase="settle", ref=0.0, tau=0.0, cyc=0, t_phase=0.0, rows=[], rel=[])
T_SETTLE = 0.5
def lid_state():
    tr = np.array(RV.get_transforms(), float)[0]
    Rl = qmat(tr[3:7]); Rr = R0.T @ Rl                      # rotation relative to the authored (shut) pose
    raw = math.atan2(Rr[2, 1], Rr[1, 1])                   # about local X
    w = float(np.array(RV.get_velocities(), float)[0, 3:] @ AX)
    return raw, w, Rl, tr[:3]

def on_step(dt):
    S["t"] += dt; S["t_phase"] += dt
    raw, w, Rl, pos = lid_state()
    if S["last"] is None: S["theta"] = raw
    else: S["theta"] += (raw - S["last"] + math.pi) % (2*math.pi) - math.pi
    S["last"] = raw
    open_deg = -math.degrees(S["theta"])                    # positive = open
    ph = S["phase"]; trk = a.track
    if ph == "settle" and S["t_phase"] > T_SETTLE:
        S["phase"], S["t_phase"], S["start"] = "fold", 0.0, max(0.0, open_deg); S["ref"] = S["start"]
    elif ph == "fold":
        S["ref"] = min(trk, S.get("start", 0.0) + a.omega * S["t_phase"])          # refold starts where the flap rests
        if S["ref"] >= trk: S["phase"], S["t_phase"] = "hold", 0.0
    elif ph == "hold" and S["t_phase"] >= a.hold: S["phase"], S["t_phase"] = "release", 0.0
    elif ph == "release" and S["t_phase"] >= a.release:
        S["rel"].append(open_deg); S["cyc"] += 1
        S["phase"], S["t_phase"] = ("fold", 0.0) if S["cyc"] < a.cycles else ("done", 0.0)
        S["start"] = max(0.0, open_deg); S["ref"] = S["start"]
    if S["phase"] in ("fold", "hold"):
        e = math.radians(S["ref"]) - (-S["theta"]); ed = 0.0 - (-w) if S["phase"] == "hold" else math.radians(a.omega if S["ref"] < trk else 0) - (-w)
        tau_open = a.kp*e + a.kd*ed                          # positive = opening torque
    else:
        tau_open = 0.0
    S["tau"] = tau_open
    if tau_open != 0.0:
        Tq = np.zeros((1, 3), np.float32); Tq[0] = -AX*tau_open                 # opening is -AX
        F = np.zeros((1, 3), np.float32); Pp = np.array([pos], np.float32)
        RV.apply_forces_and_torques_at_position(F, Tq, Pp, np.array([0], dtype=np.int32), True)
    # gravity torque about the hinge, in the opening sense
    com_w = pos + Rl @ COMS
    tg = float(np.cross(com_w - HINGE, np.array([0, 0, -9.81*MASS])) @ (-AX))
    cs = crease_state().get(a.lid) if a.model == "plastic" and "crease_state" in globals() else None
    S["rows"].append((S["t"], S["phase"], open_deg, S["ref"] if S["phase"] in ("fold", "hold") else float("nan"), tau_open, tg,
                      -cs[2] if cs else float("nan"), -cs[1] if cs else float("nan"), cs[3] if cs else float("nan")))
sub = get_physx_interface().subscribe_physics_step_events(on_step)

k = 0
while S["phase"] != "done" and S["t"] < 60:
    sim.update(); k += 1
    if REC is not None and k % 2 == 0:
        img = rgb.get_data()
        if img is not None and np.asarray(img).size:
            r = S["rows"][-1] if S["rows"] else None
            im = Image.fromarray(np.asarray(img)[:, :, :3].copy()); d = ImageDraw.Draw(im)
            d.rectangle([0, 0, W_, 112], fill=(0, 0, 0))
            d.text((16, 8), a.label or "crease test %s (%s)" % (a.lid, a.model), font=F1, fill=(255, 255, 255))
            if r:
                d.text((16, 44), "%-7s  angle %6.1f deg   fixture %+.3f N*m   gravity %+.3f N*m" % (r[1], r[2], r[4], r[5]), font=F2, fill=(255, 220, 120))
                if not math.isnan(r[6]):
                    d.text((16, 76), "crease moment %+.3f N*m (yield %.3f)   plastic set %.1f deg" % (r[6], r[8], r[7]), font=F2, fill=(150, 220, 255))
            REC.append_data(np.asarray(im))
sub = None
if REC is not None: REC.close(); P("video ->", os.path.abspath(a.video))

import csv
with open(OUT + ".csv", "w", newline="") as f:
    wr = csv.writer(f); wr.writerow(["t_s", "phase", "angle_deg", "ref_deg", "fixture_torque_Nm", "gravity_torque_Nm", "crease_moment_Nm", "plastic_set_deg", "yield_Nm"])
    for r in S["rows"]: wr.writerow([("%.5g" % v) if isinstance(v, float) else v for v in r])
rows = S["rows"]
fold = [r for r in rows if r[1] == "fold"]
P("===== RESULT %s %s track %.0f deg, %d cycle(s) =====" % (a.lid, a.model, a.track, a.cycles))
if fold:
    P("max angle reached %.1f deg (tracking %.0f); max fixture torque during fold %.4f N*m" % (max(r[2] for r in rows), a.track, max(r[4] for r in fold)))
for i, ang in enumerate(S["rel"]):
    P("cycle %d: rest angle %.1f deg after %.1f s free  -> spring-back %.1f deg" % (i+1, ang, a.release, a.track - ang))
LOG.close(); tl.stop(); sim.close()
