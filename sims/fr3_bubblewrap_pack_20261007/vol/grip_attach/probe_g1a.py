#!/usr/bin/env python3
"""probe_g1a.py — G1a:G1 單片夾持 + 閉合完成時綁定(attach_grip),抬 150 拉 100、停、開始張開那步 RemovePrim。

    /isaac-sim/python.sh probe_g1a.py                                 # 3 pad x 2 層 x 2 間隙 = 12 組同 stage
    /isaac-sim/python.sh probe_g1a.py --only 16,top,4 --video
場景/材料/時間表同 vol/grip/probe_grip.py(指摩擦 2.0、抬 3s),T_OBS 拉到 1.5s 量釋放後 1s。
"""
import os, sys, argparse, time, json
import numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--pads", default="8,16,24"); ap.add_argument("--layers", default="top,both"); ap.add_argument("--gaps", default="4,6")
ap.add_argument("--only", default=""); ap.add_argument("--video", action="store_true"); ap.add_argument("--tag", default="")
ap.add_argument("--ffric", type=float, default=2.0); ap.add_argument("--lift", type=float, default=3.0)
ap.add_argument("--nxy", type=int, default=35); ap.add_argument("--dt", type=float, default=1 / 240.0)
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
if a.only:
    p_, l_, g_ = a.only.split(","); CFG = [(float(p_), l_, float(g_))]
else:
    CFG = [(float(p), l, float(g)) for p in a.pads.split(",") for l in a.layers.split(",") for g in a.gaps.split(",")]
tag = a.tag or ("g1a_" + ("only_%g_%s_%g" % CFG[0] if a.only else "sweep"))
LOG = open(os.path.join(HERE, "logs", tag + ".log"), "w")
def P(*s):
    m = " ".join(str(x) for x in s); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from pxr import UsdGeom, PhysxSchema, Vt
import omni.usd
sys.path[:0] = [HERE, os.path.join(VOL, "grip"), VOL]
import gutil as GU, volcommon as VC, vol_pen as VP, attach_grip as AG

P("=== G1a %s ===" % tag); P("args:", vars(a)); P("組數 %d:%s" % (len(CFG), CFG))
world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane(z_position=-0.4)
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
T = 0.004; S = 0.200; OVH = 0.030; REST = 0.0005
FS = np.array([0.020, 0.020, 0.008]); FH = FS / 2; FX = 0.021; SPC = 0.40; ZB = REST + 1e-4
GU.static_box(st, "/World/table", [0.6, SPC * (len(CFG) - 1) + 0.3, 0.05], [-0.3, SPC * (len(CFG) - 1) / 2, -0.025], 0.5, color=(0.35, 0.25, 0.18))
SC = []
for k, (pad, lay, gap) in enumerate(CFG):
    oy = SPC * k; pth = "/World/s%02d" % k
    VC.build_plate(st, pth + "_plate", S, T, ZB, "manual", nxy=a.nxy, nz=1, youngs=2e3, poisson=0.45, areal=0.1, fric=0.8,
                   cont=0.002, rest=REST, solver=128, self_coll=True, self_filter=2 * REST, cx=OVH - S / 2, cy=oy,
                   P=(P if k == 0 else (lambda *s: None)))
    GU.finger(st, pth + "_fu", FS, [FX, oy, 0.05 + FH[2]], a.ffric, color=(0.9, 0.45, 0.1))
    GU.finger(st, pth + "_fl", FS, [FX, oy, -0.05 - FH[2]], a.ffric, color=(0.9, 0.45, 0.1))
    SC.append(dict(k=k, pad=pad, lay=lay, gap=gap / 1e3, oy=oy, plate=pth + "_plate", fu=pth + "_fu", fl=pth + "_fl"))
VIS = None
if a.video:
    c0 = SC[0]
    VIS = GU.vis_mesh(st, "/World/plate_vis", np.zeros(((a.nxy + 1) ** 2 * 2, 3)), a.nxy, a.nxy, (0.25, 0.55, 0.85))
    for _p in (c0["plate"], c0["fu"], c0["fl"]):
        UsdGeom.Imageable(st.GetPrimAtPath(_p)).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    VBU = GU.VisBox(st, "/World/vis_fu", FS, (0.9, 0.45, 0.1)); VBL = GU.VisBox(st, "/World/vis_fl", FS, (0.9, 0.45, 0.1))
    EYE = [0.42, c0["oy"] - 0.62, 0.36]; TGT = [0.0, c0["oy"], 0.07]
    VID = GU.Video(st, os.path.join(HERE, "videos", tag + ".mp4"), EYE, TGT, focal=4.0,
                   label="G1a attach-grip pad %.0fmm layer %s gap %.0fmm mu %.1f | E2e3 T4 n35 solver128 dt1/240" % (c0["pad"], c0["lay"], c0["gap"] * 1e3, a.ffric))
world.reset()
if VIS is not None:
    VID.init(); VID.look(EYE, TGT)
for _ in range(2):
    sim.update()
FPATHS = [s["fu"] for s in SC] + [s["fl"] for s in SC]
FV = world.physics_sim_view.create_rigid_body_view(FPATHS)
_pi = {p: i for i, p in enumerate(FPATHS)}
ORD = np.array([_pi[p] for p in FV.prim_paths]); FIDX = np.arange(FV.count, dtype=np.int32)
for s in SC:
    s["mesh"] = VC.Mesh(st, s["plate"]); s["flat"] = s["mesh"].pts().copy()
TETS = SC[0]["mesh"].tets(); V0 = VP.tet_vol(SC[0]["flat"], TETS); EDG = GU.edges(TETS)
L0 = np.linalg.norm(SC[0]["flat"][EDG[:, 0]] - SC[0]["flat"][EDG[:, 1]], axis=1)
N1 = (a.nxy + 1) ** 2
TOPM = np.zeros(2 * N1, bool); TOPM[N1:] = True

T_SET = 0.8; T_CL = 1.2; T_HOLD = 0.4; T_PULL = 2.0; T_STAY = 2.0; T_OPEN = 0.3; T_OBS = 1.5
t_closed = T_SET + T_CL; t_lift0 = t_closed + T_HOLD; t_lift1 = t_lift0 + a.lift; t_pull1 = t_lift1 + T_PULL
t_open0 = t_pull1 + T_STAY; t_open1 = t_open0 + T_OPEN; T_END = t_open1 + T_OBS
ss = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.), 1.))
def phase(t):
    for nm, tt in [("settle", T_SET), ("close", t_closed), ("hold", t_lift0), ("lift", t_lift1), ("pull", t_pull1), ("stay", t_open0), ("open", t_open1)]:
        if t < tt:
            return nm
    return "observe"
def finger_c(s, t):
    oy = s["oy"]
    if s.get("zc") is None:
        return np.array([FX, oy, 0.05 + FH[2]]), np.array([FX, oy, -0.05 - FH[2]])
    zc = s["zc"]; g = s["gap"]; hu0, hl0 = 0.05 + FH[2], -0.05 - FH[2]
    hu1, hl1 = zc + g / 2 + FH[2], zc - g / 2 - FH[2]
    u = ss((t - T_SET) / T_CL); zu = hu0 + (hu1 - hu0) * u; zl = hl0 + (hl1 - hl0) * u
    dz = 0.150 * ss((t - t_lift0) / a.lift); dx = 0.100 * ss((t - t_lift1) / T_PULL); op = 0.020 * ss((t - t_open0) / T_OPEN)
    return np.array([FX + dx, oy, zu + dz + op]), np.array([FX + dx, oy, zl + dz - op])
def drive(t):
    D = np.zeros((len(FPATHS), 7), np.float32); D[:, 6] = 1.0; n = len(SC)
    for i, s in enumerate(SC):
        cu, cl = finger_c(s, t); D[i, :3] = cu; D[n + i, :3] = cl
    FV.set_kinematic_targets(D[ORD], FIDX)
def foot(Pp, c):
    return (np.abs(Pp[:, 0] - c[0]) < FH[0]) & (np.abs(Pp[:, 1] - c[1]) < FH[1])

ME = int(round(0.05 / a.dt)); NSTEP = int(round(T_END / a.dt)); SPF = int(round(1.0 / (30 * a.dt)))
for s in SC:
    s.update(ts=[], slip=[], com=[], penf=[], spen=[], lmax=[], ph=[], G=None, AV=None)
P("時間表:close→%.2f(綁定)hold→%.2f lift→%.2f pull→%.2f stay→%.2f(釋放+張開)open→%.2f obs→%.2f" % (t_closed, t_lift0, t_lift1, t_pull1, t_open0, t_open1, T_END))
t0w = time.time()
for step in range(1, NSTEP + 1):
    t = step * a.dt
    for s in SC:
        if s.get("zc") is None and t >= T_SET:
            Pp = s["mesh"].pts(); m = foot(Pp, finger_c(s, t)[0]); s["zc"] = float(Pp[m, 2].mean())
        if s["AV"] is None and t >= t_closed - 1e-9:
            Pp = s["mesh"].pts(); cu, cl = finger_c(s, t)
            fp = AG.finger_pose((cu + cl) / 2, None, s["gap"], FH[:2])
            AV = AG.select_vertices(Pp, fp, s["pad"], TOPM if s["lay"] == "top" else None)
            s["scope"] = AG.bind(st, AV, s["fu"], Pp, s["plate"], cu, None, scope="/World/gatt_%02d" % s["k"])
            s["AV"] = AV; s["n_top"] = int((AV >= N1).sum()); s["n_bot"] = int((AV < N1).sum())
            P("  [s%02d] t=%.2f 綁定 %d 點(上層 %d 下層 %d)pad %.0f %s gap %.0f" % (s["k"], t, len(AV), s["n_top"], s["n_bot"], s["pad"], s["lay"], s["gap"] * 1e3))
        if not s.get("rel") and t >= t_open0 - 1e-9:
            AG.release(st, s.get("scope")); s["rel"] = True; s["com_rel"] = s["mesh"].pts().mean(0)
    drive(t)
    rend = VIS is not None and step % SPF == 0
    world.step(render=rend)
    if rend:
        s0 = SC[0]; VIS.Set(Vt.Vec3fArray.FromNumpy(s0["mesh"].pts().astype(np.float32)))
        _cu, _cl = finger_c(s0, t); VBU.set(_cu); VBL.set(_cl)
        VID.frame(t, "%s  pad %.0f %s gap %.0f  bound %s" % (phase(t), s0["pad"], s0["lay"], s0["gap"] * 1e3,
                                                         "-" if s0["AV"] is None else ("released" if s0.get("rel") else len(s0["AV"]))))
    if step % ME:
        continue
    for s in SC:
        Pp = s["mesh"].pts()
        if not np.isfinite(Pp).all():
            if not s.get("nan"):
                P("★ NaN s%02d t=%.2f" % (s["k"], t))
            s["nan"] = t; continue
        cu, cl = finger_c(s, t)
        if s["G"] is None and t >= t_lift0 - 1e-9:
            s["G"] = np.where(foot(Pp, cu) & (Pp[:, 2] > cl[2]) & (Pp[:, 2] < cu[2]))[0]; s["rel0"] = Pp[s["G"]] - cu
        sl = float(np.median(np.linalg.norm(Pp[s["G"]] - cu - s["rel0"], axis=1))) if s["G"] is not None and len(s["G"]) else np.nan
        mu_, du = GU.in_box(Pp, cu, FH); ml_, dl = GU.in_box(Pp, cl, FH)
        penf = int((mu_ & (du > 0.0005)).sum() + (ml_ & (dl > 0.0005)).sum())
        spen = VP.self_pen_count(Pp, TETS, s["flat"])[0] if step % (ME * 4) == 0 else (s["spen"][-1] if s["spen"] else 0)
        Lr = np.linalg.norm(Pp[EDG[:, 0]] - Pp[EDG[:, 1]], axis=1) / L0
        s["ts"].append(t); s["slip"].append(sl); s["com"].append(Pp.mean(0)); s["penf"].append(penf); s["spen"].append(spen)
        s["lmax"].append(float(Lr.max())); s["ph"].append(phase(t))
        if "stick" not in s and t >= t_open0 + 1.0 - 1e-9:
            s["stick"] = int((GU.in_box(Pp, cu, FH + 0.002)[0] | GU.in_box(Pp, cl, FH + 0.002)[0]).sum())
        if a.only or (step % (ME * 10) == 0 and s["k"] == 0):
            P("  [s%02d] t=%5.2f %-7s 滑動 %.2fmm 質心 z %.1f 穿指 %d 自穿 %d 邊長比 %.3f" % (s["k"], t, phase(t), sl * 1e3, s["com"][-1][2] * 1e3, penf, spen, Lr.max()))
    if step % (ME * 20) == 0:
        P("  ... t=%.2f wall %.0fs" % (t, time.time() - t0w))
if VIS is not None:
    VID.close(); P("影片 → %s(%d 幀)" % (VID.path, VID.n))
P("\n===== 判讀 G1a =====")
P("判準:滑動 < 1mm、邊長比 < 2.0、互穿 0(穿指深 >0.5mm 點 + 自穿)、釋放後 1s 質心速度 < 0.1 m/s")
rows = []
for s in SC:
    ts = np.array(s["ts"]); com = np.array(s["com"])
    grip = (ts >= t_lift0) & (ts < t_open0)
    ms = float(np.nanmax(np.array(s["slip"])[grip])); lm = float(np.max(np.array(s["lmax"])[grip]))
    pf = int(np.max(np.array(s["penf"])[grip])); sp = int(np.max(s["spen"]))
    i1 = int(np.searchsorted(ts, t_open0 + 1.0 - 1e-9)); i1 = min(i1, len(ts) - 1)
    v1 = float(np.linalg.norm(com[i1] - com[i1 - 1]) / (ts[i1] - ts[i1 - 1]))
    after = ts >= t_open0
    vmax = float(np.max(np.linalg.norm(np.diff(com[after], axis=0), axis=1) / 0.05))
    d1 = com[i1] - s["com_rel"]
    stick = s.get("stick", -1)
    vh = float(np.max(np.linalg.norm(np.diff(com[after][:, :2], axis=0), axis=1) / 0.05))
    fate = "黏住" if stick > 5 else ("彈飛" if vh > 0.5 else ("掉落(落桌下 %.0fmm)" % (-d1[2] * 1e3) if d1[2] < -0.1 else "掉落(回桌面)"))
    ok = ms < 0.001 and lm < 2.0 and pf == 0 and sp == 0 and v1 < 0.1 and not s.get("nan") and stick <= 5
    r = dict(k=s["k"], pad=s["pad"], lay=s["lay"], gap=s["gap"] * 1e3, n=len(s["AV"]), n_top=s["n_top"], n_bot=s["n_bot"], slip=ms * 1e3,
             lmax=lm, penf=pf, spen=sp, v1=v1, vmax=vmax, vh=vh, d1=(d1 * 1e3).tolist(), stick=stick, fate=fate, ok=bool(ok), nan=s.get("nan"),
             com_z_stay=float(com[(ts >= t_pull1) & (ts < t_open0), 2].mean() * 1e3))
    rows.append(r)
    P("  s%02d pad %2.0f %-4s gap %.0f | 綁 %3d(上 %d 下 %d)| 滑動 %.2fmm | 邊長比 %.3f | 穿指 %d 自穿 %d | 停時質心 z %.1f | 釋放後1s 質心速度 %.3f m/s 位移 (%.0f,%.0f,%.0f)mm 最大速度 %.2f(水平 %.2f)釋放後1s 指旁2mm內 %d → %s ⇒ %s"
      % (r["k"], r["pad"], r["lay"], r["gap"], r["n"], r["n_top"], r["n_bot"], r["slip"], lm, pf, sp, r["com_z_stay"], v1, *r["d1"], vmax, vh, stick, fate, "PASS" if ok else "FAIL"))
json.dump(rows, open(os.path.join(HERE, "data", tag + ".json"), "w"), indent=1, default=float)
P("wall %.1fs" % (time.time() - t0w))
LOG.close(); sim.close()
