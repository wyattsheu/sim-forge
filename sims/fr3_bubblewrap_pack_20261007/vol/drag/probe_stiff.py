#!/usr/bin/env python3
"""probe_stiff.py — 驗 PhysX 107.3 volume deformable 的 VtxXformAttachment 吃不吃有限 stiffness。
骨架 = grip_attach/probe_g1a.py(pad 24 / both / gap 4 固定),四組同 stage 掃 stiff ∈ {inf,80,20,5},
每 0.1 s 記綁點相對上指框的伸長(= wrap_vol 的「滑動」欄)。
    /isaac-sim/python.sh drag/probe_stiff.py --stiffs inf,80,20,5 --damp -1
"""
import os, sys, argparse, time, json
import numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--stiffs", default="inf,80,20,5"); ap.add_argument("--damp", type=float, default=-1.0)
ap.add_argument("--pad", type=float, default=24.0); ap.add_argument("--gap", type=float, default=4.0)
ap.add_argument("--ffric", type=float, default=2.0); ap.add_argument("--lift", type=float, default=2.0)
ap.add_argument("--nxy", type=int, default=35); ap.add_argument("--dt", type=float, default=1 / 240.0)
ap.add_argument("--out", default="stiff_probe")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
OUT = os.path.join(HERE, a.out); os.makedirs(OUT, exist_ok=True)
CFG = [float(x) for x in a.stiffs.split(",")]
LOG = open(os.path.join(OUT, "probe.log"), "w")
def P(*s):
    m = " ".join(str(x) for x in s); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from pxr import UsdGeom, PhysxSchema
import omni.usd
sys.path[:0] = [os.path.join(VOL, "grip_attach"), os.path.join(VOL, "grip"), VOL]
import gutil as GU, volcommon as VC, vol_pen as VP, attach_grip as AG
P("=== probe_stiff ==="); P("args:", vars(a)); P("stiffs:", CFG)
world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane(z_position=-0.4)
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
T = 0.004; S = 0.200; OVH = 0.030; REST = 0.0005
FS = np.array([0.020, 0.020, 0.008]); FH = FS / 2; FX = 0.021; SPC = 0.40; ZB = REST + 1e-4
GU.static_box(st, "/World/table", [0.6, SPC * (len(CFG) - 1) + 0.3, 0.05], [-0.3, SPC * (len(CFG) - 1) / 2, -0.025], 0.5)
SC = []
for k, stf in enumerate(CFG):
    oy = SPC * k; pth = "/World/s%02d" % k
    VC.build_plate(st, pth + "_plate", S, T, ZB, "manual", nxy=a.nxy, nz=1, youngs=2e3, poisson=0.45, areal=0.1, fric=0.8,
                   cont=0.002, rest=REST, solver=128, self_coll=True, self_filter=2 * REST, cx=OVH - S / 2, cy=oy,
                   P=(P if k == 0 else (lambda *s: None)))
    GU.finger(st, pth + "_fu", FS, [FX, oy, 0.05 + FH[2]], a.ffric)
    GU.finger(st, pth + "_fl", FS, [FX, oy, -0.05 - FH[2]], a.ffric)
    SC.append(dict(k=k, stiff=stf, oy=oy, plate=pth + "_plate", fu=pth + "_fu", fl=pth + "_fl", gap=a.gap / 1e3))
world.reset()
for _ in range(2):
    sim.update()
FPATHS = [s["fu"] for s in SC] + [s["fl"] for s in SC]
FV = world.physics_sim_view.create_rigid_body_view(FPATHS)
_pi = {p: i for i, p in enumerate(FPATHS)}
ORD = np.array([_pi[p] for p in FV.prim_paths]); FIDX = np.arange(FV.count, dtype=np.int32)
for s in SC:
    s["mesh"] = VC.Mesh(st, s["plate"]); s["flat"] = s["mesh"].pts().copy()
NV = len(SC[0]["flat"]); M_VTX = 0.1 * S * S / NV
P("頂點數 %d 每頂點質量 %.2e kg" % (NV, M_VTX))
T_SET = 0.8; T_CL = 1.2; T_HOLD = 0.4; T_PULL = 1.5; T_STAY = 1.0
t_closed = T_SET + T_CL; t_lift0 = t_closed + T_HOLD; t_lift1 = t_lift0 + a.lift; t_pull1 = t_lift1 + T_PULL; T_END = t_pull1 + T_STAY
ss = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.), 1.))
def phase(t):
    for nm, tt in [("settle", T_SET), ("close", t_closed), ("hold", t_lift0), ("lift", t_lift1), ("pull", t_pull1)]:
        if t < tt: return nm
    return "stay"
def finger_c(s, t):
    oy = s["oy"]
    if s.get("zc") is None:
        return np.array([FX, oy, 0.05 + FH[2]]), np.array([FX, oy, -0.05 - FH[2]])
    zc = s["zc"]; g = s["gap"]; hu0, hl0 = 0.05 + FH[2], -0.05 - FH[2]
    hu1, hl1 = zc + g / 2 + FH[2], zc - g / 2 - FH[2]
    u = ss((t - T_SET) / T_CL); zu = hu0 + (hu1 - hu0) * u; zl = hl0 + (hl1 - hl0) * u
    dz = 0.100 * ss((t - t_lift0) / a.lift); dx = 0.100 * ss((t - t_lift1) / T_PULL)
    return np.array([FX + dx, oy, zu + dz]), np.array([FX + dx, oy, zl + dz])
def drive(t):
    D = np.zeros((len(FPATHS), 7), np.float32); D[:, 6] = 1.0; n = len(SC)
    for i, s in enumerate(SC):
        cu, cl = finger_c(s, t); D[i, :3] = cu; D[n + i, :3] = cl
    FV.set_kinematic_targets(D[ORD], FIDX)
def foot(Pp, c):
    return (np.abs(Pp[:, 0] - c[0]) < FH[0]) & (np.abs(Pp[:, 1] - c[1]) < FH[1])
ME = int(round(0.1 / a.dt)); NSTEP = int(round(T_END / a.dt))
for s in SC:
    s.update(ts=[], ext_med=[], ext_max=[], ph=[], AV=None)
t0w = time.time()
for step in range(1, NSTEP + 1):
    t = step * a.dt
    for s in SC:
        if s.get("zc") is None and t >= T_SET:
            Pp = s["mesh"].pts(); m = foot(Pp, finger_c(s, t)[0]); s["zc"] = float(Pp[m, 2].mean())
        if s["AV"] is None and t >= t_closed - 1e-9:
            Pp = s["mesh"].pts(); cu, cl = finger_c(s, t)
            fp = AG.finger_pose((cu + cl) / 2, None, s["gap"], FH[:2])
            AV = AG.select_vertices(Pp, fp, a.pad, None)
            stf = s["stiff"]; dmp = a.damp if a.damp >= 0 else (0.0 if not np.isfinite(stf) else 2 * np.sqrt(stf * M_VTX))
            VC.attach_vtx(st, "/World/gatt_%02d" % s["k"], s["plate"], s["plate"], s["fu"], AV, Pp[AV] - cu, P=P, stiff=stf, damp=dmp)
            s["AV"] = AV; s["loc0"] = Pp[AV] - cu; s["dmp"] = dmp
            P("  [s%02d stiff=%s damp=%.4g] t=%.2f 綁定 %d 點" % (s["k"], stf, dmp, t, len(AV)))
    drive(t)
    world.step(render=False)
    if step % ME: continue
    for s in SC:
        Pp = s["mesh"].pts()
        if not np.isfinite(Pp).all():
            P("★ NaN s%02d t=%.2f" % (s["k"], t)); s["nan"] = t; continue
        cu, cl = finger_c(s, t)
        if s["AV"] is not None:
            d = np.linalg.norm(Pp[s["AV"]] - cu - s["loc0"], axis=1) * 1e3
            s["ts"].append(t); s["ext_med"].append(float(np.median(d))); s["ext_max"].append(float(d.max())); s["ph"].append(phase(t))
    if step % (ME * 5) == 0:
        P("  t=%5.2f %-6s | " % (t, phase(t)) + " | ".join("k=%s 伸長 中位 %.2f 最大 %.2f mm" % (s["stiff"], s["ext_med"][-1], s["ext_max"][-1]) for s in SC if s["ts"]) + " | wall %.0fs" % (time.time() - t0w))
P("\n===== 判讀 =====")
rows = []
for s in SC:
    ts = np.array(s["ts"]); em = np.array(s["ext_med"]); ex = np.array(s["ext_max"]); ph = np.array(s["ph"])
    lift = ph == "lift"; pull = ph == "pull"; stay = ph == "stay"
    r = dict(stiff=s["stiff"], damp=s["dmp"], n=len(s["AV"]), lift_med=float(em[lift].max()), lift_max=float(ex[lift].max()),
             pull_med=float(em[pull].max()), pull_max=float(ex[pull].max()), stay_med=float(em[stay].mean()), nan=s.get("nan"))
    rows.append(r)
    P("  stiff=%-5s damp=%.4g 綁 %d | 伸長 lift 中位/最大 %.2f/%.2f | pull %.2f/%.2f | stay 中位 %.2f mm %s"
      % (r["stiff"], r["damp"], r["n"], r["lift_med"], r["lift_max"], r["pull_med"], r["pull_max"], r["stay_med"], "NaN!" if r["nan"] else ""))
fin = [r["stay_med"] for r in rows if np.isfinite(r["stiff"])]
inf_ = [r["stay_med"] for r in rows if not np.isfinite(r["stiff"])]
mono = all(fin[i] <= fin[i + 1] + 0.05 for i in range(len(fin) - 1)) if len(fin) > 1 else True  # stiffs 排序由硬到軟
sup = bool(fin) and max(fin) > 0.5 and (not inf_ or inf_[0] < 0.3)
P("PhysX 吃有限 stiffness:%s(有限組 stay 伸長 %s;inf 組 %s;隨 k 變軟單調 %s)" % ("YES" if sup else "NO", ["%.2f" % x for x in fin], ["%.2f" % x for x in inf_], mono))
json.dump(rows, open(os.path.join(OUT, "probe.json"), "w"), indent=1, default=float)
P("wall %.1fs" % (time.time() - t0w)); LOG.close(); sim.close()
