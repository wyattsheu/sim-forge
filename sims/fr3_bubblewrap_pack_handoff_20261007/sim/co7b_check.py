#!/usr/bin/env python3
"""co7b_check.py — does the co7b carton behave like the co7b run?  Numbers, no images.

  /isaac-sim/python.sh co7b_check.py [SCENE] [--push 165] [--order fyn,fyp,fxp,fxn] [--log out.txt]

Loads crease_co7b.py the way the launchers do (before Play), lets the scene settle, then opens the flaps one by one in
the PPT order (back, front, right, left): a torque about the flap's hinge (P-control on a reference ramping at --rate deg/s, reaction on the carton base so
only the crease is measured) pushes it to --push deg, holds 1 s, releases, waits 3 s.
Checks (co7b K1 / K3): rest angle within 3 deg of (k X - My0) / (k + H) with X = the angle actually reached;
carton base moved < 10 mm; wrap verts through the side walls; flaps keep their preset while settling.
Env WRAP_ITERS / CREASE_SCALE / CREASE_PRESET are passed through to crease_co7b.py.
"""
import argparse, os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("scene", nargs="?", default=os.path.join(HERE, "..", "scene_final_phys.usd"))
ap.add_argument("--push", type=float, default=165.0)
ap.add_argument("--order", default="fyn,fyp,fxp,fxn")
ap.add_argument("--settle", type=float, default=2.0)
ap.add_argument("--rate", type=float, default=30.0, help="deg/s the push reference moves at")
ap.add_argument("--log", default="")
a = ap.parse_args()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True, "extra_args": ["--/persistent/physics/enableDeformableBeta=true"]})
import carb, omni.physx.bindings._physx as pxb
_s = carb.settings.get_settings()
if hasattr(pxb, "SETTING_ENABLE_DEFORMABLE_BETA"): _s.set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
_s.set_bool("/physics/updateToUsd", True)
import numpy as np, omni.usd, omni.timeline, omni.kit.app
from pxr import Usd, UsdGeom
from omni.physx import get_physx_interface
omni.kit.app.get_app().get_extension_manager().set_extension_enabled_immediate("omni.physx.tensors", True)

LOGP = a.log or os.path.join(HERE, "logs", "co7b_check.txt"); os.makedirs(os.path.dirname(LOGP), exist_ok=True)
LOG = open(LOGP, "w")
def P(*s):
    t = " ".join(str(x) for x in s); print(t, flush=True); LOG.write(t + "\n"); LOG.flush()
ctx = omni.usd.get_context(); ctx.open_stage(os.path.abspath(a.scene))
for _ in range(30): sim.update()
st = ctx.get_stage()
_p = os.path.join(HERE, "crease_co7b.py"); exec(compile(open(_p).read(), _p, "exec"), globals())
P("scene", os.path.abspath(a.scene)); P("crease", CO7B, "preset", PRESET, "wrap iterations",
  st.GetPrimAtPath(PK + "/Wrap").GetAttribute("physxDeformableBody:solverPositionIterationCount").Get())

def xfw(path): return np.array(UsdGeom.Xformable(st.GetPrimAtPath(path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), float).T
PKW = xfw(PK); WRAP = st.GetPrimAtPath(PK + "/Wrap")
def wrap_base(TB):
    p = np.array(UsdGeom.Mesh(WRAP).GetPointsAttr().Get(), float); w = (PKW[:3, :3] @ p.T).T + PKW[:3, 3]
    return (np.linalg.inv(TB)[:3, :3] @ w.T).T + np.linalg.inv(TB)[:3, 3]
def through_wall(pb): return int(np.sum(((np.abs(pb[:, 0]) > 0.136) | (np.abs(pb[:, 1]) > 0.116)) & (pb[:, 2] < 0.134)))
TB0 = xfw(BASE)

tl = omni.timeline.get_timeline_interface(); tl.play()
S = dict(t=0.0, lid=None, tgt=0.0, ref=0.0, on=False, peak=0.0)
def base_T():
    pB, qB = [np.array(x, float)[0] for x in _K["base"].get_world_poses()]
    T = np.eye(4); w, x, y, z = qB
    T[:3, :3] = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
    T[:3, 3] = pB; return T
def push_step(dt):
    S["t"] += dt
    if not S["on"] or "lids" not in _K: return
    i = _K["order"].index(S["lid"]); A = co7b_angles()[S["lid"]][0]; S["peak"] = max(S["peak"], A)
    _, qL = [np.array(x, float) for x in _K["lids"].get_world_poses()]
    ax = _qrot(qL[i], np.array([1.0, 0, 0]))
    S["ref"] = min(S["tgt"], S["ref"] + a.rate*dt)                         # reference angle ramps at --rate deg/s (an arm, not a kick)
    T = float(np.clip(0.03 + 3.0*math.radians(S["ref"] - A), 0.0, 0.6))   # N*m, opening = rotation about -x
    tau = np.zeros((len(_K["order"]), 3)); tau[i] = -ax*T
    _K["lids"].apply_forces_and_torques_at_pos(torques=tau, is_global=True)
    _K["base"].apply_forces_and_torques_at_pos(torques=-tau.sum(0, keepdims=True), is_global=True)
_sub2 = get_physx_interface().subscribe_physics_step_events(push_step)
def run(sec):
    t1 = S["t"] + sec; mx = 0.0; tw = 0
    while S["t"] < t1:
        sim.update()
        if "base" in _K:
            TB = base_T(); mx = max(mx, np.linalg.norm(TB[:3, 3] - TB0[:3, 3])*1e3); tw = max(tw, through_wall(wrap_base(TB)))
    return mx, tw
def angles(): return {n: v[0] for n, v in co7b_angles().items()}

run(0.2); A0 = angles()
mx, tw = run(a.settle); A1 = angles()
P("settle %.1f s: angles %s -> %s (deg, open +); base moved max %.1f mm; wrap through walls max %d"
  % (a.settle, {n: round(v, 1) for n, v in A0.items()}, {n: round(v, 1) for n, v in A1.items()}, mx, tw))
ok_all = True; MX = mx; TW = tw
for n in a.order.split(","):
    before = angles(); S.update(lid=n, tgt=a.push, ref=before[n], on=True, peak=0.0)
    t0 = S["t"]
    while S["t"] - t0 < 10.0 and angles()[n] < a.push - 0.5:
        m_, t_ = run(0.1); MX = max(MX, m_); TW = max(TW, t_)
    reach_t = S["t"] - t0
    m_, t_ = run(1.0); MX = max(MX, m_); TW = max(TW, t_)
    S["on"] = False; X = S["peak"]
    m_, t_ = run(3.0); MX = max(MX, m_); TW = max(TW, t_)
    after = angles(); R = after[n]; pred = rest_after(X)
    others = {m: round(after[m] - before[m], 1) for m in after if m != n}
    ok = abs(R - pred) < 3.0
    ok_all &= ok
    P("%s: pushed to %.1f deg in %.1f s, released -> rest %.1f deg, formula %.1f (diff %+.1f) %s | other flaps changed %s"
      % (n, X, reach_t, R, pred, R - pred, "OK" if ok else "FAIL", others))
TBn = base_T()
P("===== base moved max %.1f mm (co7b K3 < 10) | wrap through side walls max %d | rest-angle check %s ====="
  % (MX, TW, "PASS" if ok_all else "FAIL"))
P("final angles", {n: round(v, 1) for n, v in angles().items()}, "base now %.1f mm from start" % (np.linalg.norm(TBn[:3, 3] - TB0[:3, 3])*1e3))
tl.stop(); LOG.close(); sim.close()
