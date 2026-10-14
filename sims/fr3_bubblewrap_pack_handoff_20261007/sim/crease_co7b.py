# crease_co7b.py — the co7b carton (default lid model since 2026-10-14): the carton the dual-arm carton-opening run
# co7b used (manip_fr3/handoff_20261008/deliver_co7b_20261013/co7b_full_open, co3_arm_open.py).
#
# Same USD as before (scene_final_phys.usd is byte-identical to the co7b package's), different crease physics:
#   * the four crease drives are zeroed (stiffness 0, damping 0)
#   * every physics step the elastoplastic crease of crease_physics.py (ElastoplasticCrease) is applied as a torque
#     about each flap's hinge axis, with the equal and opposite torque on the carton base
#   * crease law CREASE_LAW=soft (default since 2026-10-14 pm): no hardening (H 0), My0 0.12 N*m, k = My0 / 45 deg
#     (spring-back 45 deg, Nagasawa 2019), mild softening with accumulated plastic rotation kappa
#     (yield x max(0.5, exp(-0.03 kappa)), repeated folds get softer as in the literature), c 0.033 as co7b.
#     Picked with gravity included (flap weight torque 0.0094 / 0.0085 N*m upper / lower) so that, quasi-static:
#     fold a closed flap to 90 deg -> rests at 43.5 (literature 43-46); push the pre-opened back / front flap to 165 ->
#     123.4 / 123.6 (co7b's arm run: 122.5-125.1); side flaps sag 3 deg at rest. My0 0.06 with k = My0 / 45 deg let
#     gravity win: side flaps sagged 6.5 deg into the box and 165 rested at 133.
#     CREASE_LAW=co7b = co7b exactly: k 3.2, My0 0.60, H 0.85, c 0.33 (clip 3.0) all x CREASE_SCALE 0.1,
#     rest (k X - My0) / (k + H): 90 -> 63 deg, 165 -> 122 deg, deeper folds get stiffer (opposite of the literature)
#   * flaps pre-opened: front fyp 50 deg, back fyn 60 deg, sides 0 (plastic rest at the same angle)
#   * bubble wrap solverPositionIterationCount 64 -> WRAP_ITERS (8)
# The previous model (USD drive as the elastic part, crease_plastic.py) is archived in sims/carton_plastic_crease_20261009.
#
# Exec it BEFORE Play (the launchers do): the drive / preset / wrap changes are authored on the stopped stage, the
# torques start with the first physics step.  By hand:  p = "/path/to/sim/crease_co7b.py"; exec(compile(open(p).read(), p, "exec"))
# Env: CREASE_LAW (soft | co7b), CREASE_MY0 (0.12), CREASE_SPRINGBACK_DEG (45), CREASE_SOFTENING (0.03), CREASE_MIN_YIELD (0.5), CREASE_SCALE (0.1), CREASE_PRESET ("fyp=50,fyn=60,fxp=0,fxn=0" deg), WRAP_ITERS (8; 0 = keep the scene's 64).
# Stop: co7b_stop().  Angles: co7b_angles() -> {flap: (angle deg, plastic rest deg, torque N*m)}, positive = open.
import os, sys, math
import numpy as np
import omni.usd, omni.timeline
from omni.physx import get_physx_interface
from pxr import Usd, UsdGeom, UsdPhysics

_HERE = os.path.dirname(os.path.abspath(sys._getframe().f_code.co_filename))
if _HERE not in sys.path: sys.path.insert(0, _HERE)
import torch
from crease_physics import ElastoplasticCrease

PK = "/World/Packed"; BOX = PK + "/Box"; BASE = BOX + "/base"
LIDN = ("fxp", "fxn", "fyp", "fyn")
CO7B = dict(k=3.2, my0=0.60, h=0.85, c=0.33, clip=3.0)            # co3_arm_open.py CO
SCALE = float(os.environ.get("CREASE_SCALE", "0.1"))
for _k in ("k", "my0", "h", "c"): CO7B[_k] *= SCALE
LAW = os.environ.get("CREASE_LAW", "soft")
MY0_SOFT = float(os.environ.get("CREASE_MY0", "0.12"))                            # N*m, soft law yield
SPRINGBACK = math.radians(float(os.environ.get("CREASE_SPRINGBACK_DEG", "45")))   # My0 / k  (Nagasawa 2019: 90 -> 43-46 deg)
SOFTENING = float(os.environ.get("CREASE_SOFTENING", "0.03"))                     # 1/rad of accumulated plastic rotation
MIN_YIELD = float(os.environ.get("CREASE_MIN_YIELD", "0.5"))                      # floor of the softened yield, fraction of My0
if LAW == "soft":
    CO7B.update(my0=MY0_SOFT, k=MY0_SOFT / SPRINGBACK, h=0.0)
MGR = dict(fyp=0.00941, fyn=0.00941, fxp=0.00852, fxn=0.00852)   # flap weight torque about the hinge, N*m (carton.meta.json, density 200)
PRESET = dict(fyp=50.0, fyn=60.0, fxp=0.0, fxn=0.0)
for _kv in [x for x in os.environ.get("CREASE_PRESET", "").split(",") if "=" in x]:
    PRESET[_kv.split("=")[0].strip()] = float(_kv.split("=")[1])
WRAP_ITERS = int(os.environ.get("WRAP_ITERS", "8"))


class SofteningCrease(ElastoplasticCrease):
    """ElastoplasticCrease (same step, same tau) whose yield softens with the accumulated plastic rotation acc:
    My_cur = (My0 + H |rest|) * max(MIN_YIELD, exp(-SOFTENING acc)). SOFTENING 0 = ElastoplasticCrease exactly."""
    def __init__(self, num_envs, device, softening=SOFTENING, min_frac=MIN_YIELD, **kw):
        super().__init__(num_envs, device, **kw)
        self.softening, self.min_frac = float(softening), float(min_frac)
        self.acc = torch.zeros(num_envs, device=device)

    def reset(self, env_ids, ajar_rad):
        super().reset(env_ids, ajar_rad); self.acc[env_ids] = 0.0

    def yield_now(self):
        return (self.my0 + self.h * self.rest.abs()) * torch.clamp(torch.exp(-self.softening * self.acc), min=self.min_frac)

    def step(self, q, qd):
        e = q - self.rest
        my_cur = self.yield_now()
        mr = self.k * e
        mel = torch.clamp(mr, -my_cur, my_cur)
        d = (mr - mel) / self.k
        self.rest = self.rest + d
        self.acc = self.acc + d.abs()
        tau = torch.clamp(-mel - self.c * qd, -self.clip, self.clip)
        return torch.nan_to_num(tau, nan=0.0)
_K = globals().setdefault("_CO7B_STATE", {})


def _qmul(a, b):
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2, w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])
def _qc(q): return np.array([q[0], -q[1], -q[2], -q[3]])
def _qrot(q, v): return _qmul(_qmul(q, np.r_[0.0, v]), _qc(q))[1:]
def _qworld(st, path):
    q = UsdGeom.Xformable(st.GetPrimAtPath(path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default()).ExtractRotationQuat()
    return np.array([q.GetReal(), *q.GetImaginary()])


def rest_after(x_deg, my_now=None):
    """Where a flap pushed to x_deg comes to rest after release (past yield). my_now: the yield at release
    (softening law; default = unsoftened My0, i.e. a fresh crease)."""
    x = math.radians(x_deg)
    if my_now is not None: return math.degrees(x - my_now / CO7B["k"])
    return math.degrees((CO7B["k"]*x - CO7B["my0"]) / (CO7B["k"] + CO7B["h"]))


def rest_with_gravity(p_deg, n):
    """Rest angle (deg, open +) of flap n released with plastic set p_deg: theta = p - (m g r / k) cos(theta)."""
    p = math.radians(p_deg); g = MGR[n] / CO7B["k"]; th = p
    for _ in range(100): th = p - g * math.cos(th)
    return math.degrees(th)


def predict_rest(x_deg, n, from_deg=None):
    """Quasi-static: push flap n from its plastic set from_deg (default its preset) to x_deg, release. Softening and
    gravity included; co7b law: hardening, gravity included."""
    p0 = math.radians(PRESET.get(n, 0.0) if from_deg is None else from_deg); X = math.radians(x_deg); p = p0
    for _ in range(200):
        my = CO7B["my0"] + CO7B["h"] * p
        if LAW == "soft": my = CO7B["my0"] * max(MIN_YIELD, math.exp(-SOFTENING * max(0.0, p - p0)))
        q = max(p, X - my / CO7B["k"])
        if abs(q - p) < 1e-10: break
        p = q
    return rest_with_gravity(math.degrees(p), n)


def co7b_yield(n):
    """Current yield moment of flap n (N*m), softening included."""
    i = _K["order"].index(n); return float(_K["cr"].yield_now()[i]) if LAW == "soft" else None


def _prepare():
    """On the stopped stage: closed-pose reference, drives off, presets, wrap iterations."""
    from pxr import Gf
    st = omni.usd.get_context().get_stage()
    if omni.timeline.get_timeline_interface().is_playing():
        print("[co7b] WARNING: loaded while playing -- presets / wrap iterations need Stop, then exec again")
    qB = _qworld(st, BASE)
    _K["rel0"] = {n: _qmul(_qc(qB), _qworld(st, BOX + "/" + n)) for n in LIDN}     # closed flap vs base
    for n in LIDN:
        d = UsdPhysics.DriveAPI.Get(st.GetPrimAtPath(BOX + "/crease_" + n), "angular")
        if d: d.GetStiffnessAttr().Set(0.0); d.GetDampingAttr().Set(0.0)
        if not PRESET.get(n): continue
        ops = UsdGeom.Xformable(st.GetPrimAtPath(BOX + "/" + n)).GetOrderedXformOps()
        rx = [o for o in ops if o.GetOpType() == UsdGeom.XformOp.TypeRotateX]
        if rx: rx[0].Set(float(rx[0].Get()) - PRESET[n])
        else:
            ori = [o for o in ops if o.GetOpType() == UsdGeom.XformOp.TypeOrient][0]; q = ori.Get()
            ori.Set(type(q)(Gf.Quatd(q) * Gf.Rotation(Gf.Vec3d(1, 0, 0), -PRESET[n]).GetQuat()))
    w = st.GetPrimAtPath(PK + "/Wrap").GetAttribute("physxDeformableBody:solverPositionIterationCount")
    if WRAP_ITERS and w: w.Set(WRAP_ITERS)
    print("[co7b] crease law %s: k %.4f N*m/rad My0 %.3f N*m H %.3f c %.3f clip %.1f%s; preset %s; wrap iterations %s; "
          "expected (quasi-static, gravity): closed fold 90 -> %.1f, back / front / side pushed to 165 -> %.1f / %.1f / %.1f deg"
          % (LAW, CO7B["k"], CO7B["my0"], CO7B["h"], CO7B["c"], CO7B["clip"],
             " softening %.2f/rad floor %.2f" % (SOFTENING, MIN_YIELD) if LAW == "soft" else " (x%.2f)" % SCALE,
             PRESET, w.Get() if w else "-", predict_rest(90, "fyp", 0.0), predict_rest(165, "fyn"), predict_rest(165, "fyp"), predict_rest(165, "fxp")))


def _setup():
    from isaacsim.core.prims import RigidPrim
    import uuid
    tag = uuid.uuid4().hex[:6]
    lids = RigidPrim(prim_paths_expr=BOX + "/f[xy][pn]", name="co7b_lids_" + tag); lids.initialize()
    base = RigidPrim(prim_paths_expr=BASE, name="co7b_base_" + tag); base.initialize()
    order = [str(p).rsplit("/", 1)[-1] for p in lids.prim_paths]
    cr = SofteningCrease(len(order), "cpu", **CO7B) if LAW == "soft" else ElastoplasticCrease(len(order), "cpu", **CO7B)
    cr.reset(torch.arange(len(order)), torch.tensor([math.radians(PRESET.get(n, 0.0)) for n in order], dtype=torch.float32))
    _K.update(lids=lids, base=base, order=order, cr=cr, last=[None]*len(order), tq=np.zeros(len(order)), ang=np.zeros(len(order)))


def _lid_state():
    _, qL = [np.array(x, float) for x in _K["lids"].get_world_poses()]
    _, qB = [np.array(x, float)[0] for x in _K["base"].get_world_poses()]
    wL = np.array(_K["lids"].get_angular_velocities(), float); wB = np.array(_K["base"].get_angular_velocities(), float)[0]
    ang, rate, axes = [], [], []
    for i, n in enumerate(_K["order"]):
        ax = _qrot(qL[i], np.array([1.0, 0, 0])); rr = _qmul(_qc(_K["rel0"][n]), _qmul(_qc(qB), qL[i]))
        if rr[0] < 0: rr = -rr
        a = 2*math.atan2(rr[1], rr[0])
        if _K["last"][i] is not None: a = _K["last"][i] + (a - _K["last"][i] + math.pi) % (2*math.pi) - math.pi   # continuous past 180
        _K["last"][i] = a
        ang.append(a); rate.append(float(np.dot(wL[i] - wB, ax))); axes.append(ax)
    return np.array(ang), np.array(rate), axes


def _on_step(dt):
    if "lids" not in _K:
        try: _setup(); _K.pop("waiting", None)
        except Exception as e:
            if not _K.get("waiting"): print("[co7b] not ready yet:", e)
            _K["waiting"] = True; return
    try: ang, rate, axes = _lid_state()
    except Exception as e:                                      # stage reloaded / Stop+Play: the tensor view is invalidated
        if not _K.get("lost"): print("[co7b] physics view lost (%s); re-attaching on the next step" % e)
        for k in ("lids", "base", "order", "cr", "last"): _K.pop(k, None)
        _K["lost"] = True; return
    _K.pop("lost", None)
    tq = _K["cr"].step(torch.tensor(ang, dtype=torch.float32), torch.tensor(rate, dtype=torch.float32)).numpy()
    tau = np.stack([axes[i]*float(tq[i]) for i in range(len(axes))])
    _K["lids"].apply_forces_and_torques_at_pos(torques=tau, is_global=True)
    _K["base"].apply_forces_and_torques_at_pos(torques=-tau.sum(0, keepdims=True), is_global=True)
    _K["ang"], _K["tq"] = ang, tq


def co7b_angles():
    """{flap: (angle deg, plastic rest deg, torque N*m)}, positive = open (opening is the negative joint direction)."""
    if "cr" not in _K: return {}
    rest = _K["cr"].rest.numpy()
    return {n: (-math.degrees(_K["ang"][i]), -math.degrees(rest[i]), -float(_K["tq"][i])) for i, n in enumerate(_K["order"])}


def co7b_stop():
    _K.pop("sub", None); _K.clear(); print("[co7b] stopped (drives stay at 0; reopen the scene to restore them)")


_K.clear()
_prepare()
_K["sub"] = get_physx_interface().subscribe_physics_step_events(_on_step)
print("[co7b] physics step attached. Stop: co7b_stop()")
