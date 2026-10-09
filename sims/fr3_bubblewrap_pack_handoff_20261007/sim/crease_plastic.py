# crease_plastic.py — elastic-plastic crease for the four carton flaps (default lid model since 2026-10-09).
#
# Corrugated / folding-carton creases are not springs. Measured moment-angle curves (Nagasawa et al. 2019,
# Beex & Peerlings 2009, Mentrasti et al. 2013; see docs/CREASE_MECHANICS.md) show:
#   1. a short elastic range, then a yield / peak moment where the creased plies delaminate and bulge,
#   2. a nearly constant (plateau) moment while the fold keeps going,
#   3. on release a large but partial spring-back (folded to 90 deg, a fresh crease comes back to ~45 deg),
#   4. a softer crease on every further fold.
# Here: the USD drive is the elastic part (stiffness k, target = plastic set angle). Every physics step the
# set angle flows when |k * (theta - set)| exceeds the current yield moment My, so the flap stays wherever it
# was folded, minus the elastic spring-back My / k. Yield softens with accumulated plastic rotation (repeat folds).
# Same law as parcel-forge carton_v1 (crease_model.advance), unwrapped angles so folds past 180 deg work (0..270).
#
# Loaded by ui_boot.py / webrtc_boot.py (LID_MODE=plastic, the default; LID_MODE=latch = old open/shut latch).
# By hand in the Script Editor:  p = "/path/to/sim/crease_plastic.py"; exec(compile(open(p).read(), p, "exec"))
# Stop: crease_plastic_stop().  Parameters come from the USD (build_phys_scene.py writes them as custom
# attributes on each crease joint) or from the CREASE_* environment variables below.
import os, math
import numpy as np
import omni.usd
from omni.physx import get_physx_interface
from pxr import UsdPhysics

BOX = "/World/Packed/Box"
LIDS = ("fxp", "fxn", "fyp", "fyn")
# per metre of crease width (overridden per joint by the custom attributes crease:yieldMoment / crease:softening)
MY_PER_M = float(os.environ.get("CREASE_MY_PER_M", "0.25"))        # N*m/m  (Nagasawa 2019: Mp1 0.244 N*m/m)
SOFTENING = float(os.environ.get("CREASE_SOFTENING", "0.15"))      # 1/rad of accumulated plastic rotation (carton_v1)
MIN_YIELD = float(os.environ.get("CREASE_MIN_YIELD", "0.5"))       # floor of the softened yield, fraction of My
VISC_TIME = float(os.environ.get("CREASE_VISC_TIME", "0.02"))      # s, plastic flow time constant (carton_v1)
_C = globals().setdefault("_CREASE_PLASTIC_STATE", {})


def _qmul(a, b):
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2,
                     w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])
def _qc(q): return np.array([q[0], -q[1], -q[2], -q[3]])


def crease_advance(theta, set_, acc, dt, k, my, softening=SOFTENING, min_frac=MIN_YIELD, visc_time=VISC_TIME):
    """One step of the rate-dependent elastic-plastic crease (backward Euler, cannot overshoot the yield
    surface). Angles in rad, k in N*m/rad, my in N*m. Returns (new_set, new_acc, elastic_moment, yield_now)."""
    my_now = my * max(min_frac, math.exp(-softening * acc))
    trial = k * (theta - set_)
    eta = k * visc_time                                    # plastic viscosity N*m*s/rad
    d = math.copysign(max(0.0, abs(trial) - my_now) * dt / (eta + k * dt), trial)
    return set_ + d, acc + abs(d), k * (theta - set_ - d), my_now


def _setup():
    from isaacsim.core.prims import RigidPrim
    import uuid
    tag = uuid.uuid4().hex[:6]
    st = omni.usd.get_context().get_stage()
    lids = RigidPrim(prim_paths_expr=BOX + "/f[xy][pn]", name="crease_lids_" + tag); lids.initialize()
    base = RigidPrim(prim_paths_expr=BOX + "/base", name="crease_base_" + tag); base.initialize()
    order = [str(p).rsplit("/", 1)[-1] for p in lids.prim_paths]
    _, qL = [np.array(x, float) for x in lids.get_world_poses()]
    _, qB = [np.array(x, float)[0] for x in base.get_world_poses()]
    rel0 = [_qmul(_qc(qB), qL[i]) for i in range(len(order))]
    par = {}
    for n in order:
        j = st.GetPrimAtPath(BOX + "/crease_" + n)
        d = UsdPhysics.DriveAPI.Get(j, "angular")
        k = float(d.GetStiffnessAttr().Get()) * 180.0 / math.pi                  # USD drive is per degree
        a_my = j.GetAttribute("crease:yieldMoment"); a_w = j.GetAttribute("crease:width")
        width = float(a_w.Get()) if a_w and a_w.Get() is not None else 0.25
        my = float(a_my.Get()) if a_my and a_my.Get() is not None else MY_PER_M * width
        par[n] = dict(drive=d, k=k, my=my, width=width,
                      set=math.radians(float(d.GetTargetPositionAttr().Get() or 0.0)), acc=0.0, theta=0.0, last_q=None, sent=None)
    _C.update(lids=lids, base=base, order=order, rel0=rel0, par=par, t=0.0, log=[])
    print("[crease] elastic-plastic creases on", order, " ".join(
        "%s: k %.3f N*m/rad My %.3f N*m (spring-back %.0f deg)" % (n, p["k"], p["my"], math.degrees(p["my"] / p["k"])) for n, p in par.items()))


def _raw_angles():
    _, qL = [np.array(x, float) for x in _C["lids"].get_world_poses()]
    _, qB = [np.array(x, float)[0] for x in _C["base"].get_world_poses()]
    out = []
    for i in range(len(_C["order"])):
        rr = _qmul(_qc(_C["rel0"][i]), _qmul(_qc(qB), qL[i]))
        out.append(2.0 * math.atan2(rr[1], rr[0]))            # about the hinge (lid local X), in (-2pi, 2pi]
    return out


def crease_angles():
    """Continuous (unwrapped) flap angles in degrees, negative = open (0 shut, -90 upright, -180 out, -270 down the wall)."""
    return {n: math.degrees(_C["par"][n]["theta"]) for n in _C.get("order", [])}


def _on_step(dt):
    if "lids" not in _C:
        try: _setup()
        except Exception as e:
            print("[crease] not ready yet:", e); return
    _C["t"] += dt
    for n, raw in zip(_C["order"], _raw_angles()):
        p = _C["par"][n]
        if p["last_q"] is None: p["theta"] = raw
        else:                                                   # unwrap: continuous angle through +-180
            d = (raw - p["last_q"] + math.pi) % (2*math.pi) - math.pi
            p["theta"] += d
        p["last_q"] = raw
        p["set"], p["acc"], p["m_el"], p["my_now"] = crease_advance(p["theta"], p["set"], p["acc"], dt, p["k"], p["my"])
        tgt = math.degrees(p["set"])
        if p["sent"] is None or abs(tgt - p["sent"]) > 0.05:
            p["drive"].GetTargetPositionAttr().Set(tgt); p["sent"] = tgt


def crease_state():
    """{lid: (angle deg, plastic set deg, elastic moment N*m, current yield N*m, accumulated plastic deg)}"""
    return {n: (math.degrees(p["theta"]), math.degrees(p["set"]), p.get("m_el", 0.0), p.get("my_now", p["my"]), math.degrees(p["acc"]))
            for n, p in _C.get("par", {}).items()}


def crease_plastic_stop():
    _C.pop("sub", None)
    for n, p in _C.get("par", {}).items(): p["drive"].GetTargetPositionAttr().Set(0.0)
    _C.clear(); print("[crease] stopped (drive targets back to 0)")


_C.clear()
_C["sub"] = get_physx_interface().subscribe_physics_step_events(_on_step)
print("[crease] physics step attached; flaps keep the angle you fold them to (minus spring-back). Stop: crease_plastic_stop()")
