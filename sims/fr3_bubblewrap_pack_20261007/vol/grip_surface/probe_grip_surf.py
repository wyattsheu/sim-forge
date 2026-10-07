#!/usr/bin/env python3
"""probe_grip_surf.py — G1 surface 版:kinematic 平行夾爪純摩擦夾持 surface deformable(零厚度膜)板(無 attachment)。

    /isaac-sim/python.sh probe_grip_surf.py                          # 10 組(間隙 10/8/6/4/2 x 摩擦 1/2)同 stage 平行
    /isaac-sim/python.sh probe_grip_surf.py --only 2,2.0 --video     # 單組 + 錄影

幾何與時間表同 vol/grip/probe_grip.py(G1):桌面頂 z=0、邊緣 x=0;板 200x200 平放,+x 邊懸出 30mm;
指面 20x20x8mm 中心 x=21mm、y=板邊中點;settle 0.8 → 量懸出段中面 zc → 合到間距 gap(1.2s)→ hold 0.4
→ 抬 150mm(3s)→ 拉 +x 100mm(2s)→ 停 2s → 張開(各退 20mm/0.3s)→ 看 1.5s。
布:sutil.build_sheet(work/wrap_sim.py 定案:young 2e4 bend 4 thick 4mm dens 100 μ0.8 cont 5mm rest 1mm
    selfCollision solver 64),n=15 格 ⇒ 格距 13.3mm(格點 y=±6.7 ⇒ 指面下 2x2 頂點)。dt 1/120(wrap_sim 同)。
量測:滑動(夾持頂點相對上指)、質心 z、穿指(頂點 + 面取樣點落在指面方塊內;深度 = 到最近面)、
    指面到布的間隙(夾持頂點到上指底面 / 下指頂面)、三角邊長比、張開後黏住/彈飛。
"""
import os, sys, argparse, time, json
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--gaps", default="10,8,6,4,2", help="指面間距 mm")
ap.add_argument("--frics", default="1.0,2.0")
ap.add_argument("--lift", type=float, default=3.0)
ap.add_argument("--only", default="", help="gap,fric 單組")
ap.add_argument("--video", action="store_true")
ap.add_argument("--table_fric", type=float, default=0.5)
ap.add_argument("--young", type=float, default=2e4)
ap.add_argument("--bend", type=float, default=4.0)
ap.add_argument("--thick", type=float, default=0.004)
ap.add_argument("--dens", type=float, default=100.0)
ap.add_argument("--fric", type=float, default=0.8)
ap.add_argument("--n", type=int, default=15)
ap.add_argument("--cont", type=float, default=0.005)
ap.add_argument("--rest", type=float, default=0.001)
ap.add_argument("--fcont", type=float, default=0.001, help="指面 contactOffset")
ap.add_argument("--solver", type=int, default=64)
ap.add_argument("--nosc", action="store_true", help="關 selfCollision")
ap.add_argument("--sleepy", action="store_true")
ap.add_argument("--pre_gap", type=float, default=0.002, help="preclose 起始間距下限(m);gap 比它小的組在 close 段才擠進去")
ap.add_argument("--preclose", type=int, default=1,
                help="1 = 指面 t=0 就已合在平鋪布的懸出段上(間距 gap,中心 z=布初始高度)。"
                     "★ 2026-10-07 實測:bend 4 的布 30mm 懸出段 0.8s 內垂成近乎垂直(邊緣 z -26.5mm、x 最大只剩 3.6mm),"
                     "指面投影內 0 個頂點,照 volume 的時間表根本夾不到 ⇒ 預設先合。0 = 照 volume 時間表(會失敗)")
ap.add_argument("--dt", type=float, default=1 / 120.0)
ap.add_argument("--tag", default="")
ap.add_argument("--dbg_early", action="store_true", help="印 t<0.8 指面投影內(初始)頂點的軌跡")
ap.add_argument("--focal", type=float, default=4.0)
ap.add_argument("--cam", default="0.42,-0.62,0.36,0.0,0.0,0.07")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ["logs", "img", "videos", "data"]:
    os.makedirs(os.path.join(HERE, d), exist_ok=True)
if a.only:
    g_, f_ = [float(x) for x in a.only.split(",")]
    CFG = [(g_, f_)]
else:
    CFG = [(g, f) for g in map(float, a.gaps.split(",")) for f in map(float, a.frics.split(","))]
tag = a.tag or ("g1s_" + ("only_%g_%g" % CFG[0] if a.only else "sweep"))
LOG = open(os.path.join(HERE, "logs", tag + ".log"), "w")
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
sys.path.insert(0, HERE); sys.path.insert(1, os.path.join(os.path.dirname(HERE), "grip"))
import gutil as GU          # vol/grip/gutil.py(唯讀引用)
import volcommon as VC
import sutil as SU

P("=== G1 surface %s ===" % tag); P("args:", vars(a)); P("組數 %d:%s" % (len(CFG), CFG))
world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane(z_position=-0.4)
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

S = 0.200; OVH = 0.030
FS = np.array([0.020, 0.020, 0.008]); FH = FS / 2
FX = 0.021
SPC = 0.40
ZB = a.rest + 1e-4
SC = []
GU.static_box(st, "/World/table", [0.6, SPC * (len(CFG) - 1) + 0.3, 0.05], [-0.3, SPC * (len(CFG) - 1) / 2, -0.025], a.table_fric, color=(0.35, 0.25, 0.18))
for k, (gap, fr) in enumerate(CFG):
    oy = SPC * k; pth = "/World/s%02d" % k
    info = SU.build_sheet(st, pth + "_sheet", S, a.n, ZB, OVH - S / 2, oy, young=a.young, bend=a.bend, thick=a.thick,
                          dens=a.dens, fric=a.fric, cont=a.cont, rest=a.rest, solver=a.solver, selfcol=not a.nosc, sleepy=a.sleepy)
    g0 = max(gap / 1e3, a.pre_gap)          # 起始間距:< pre_gap 的組先停在 pre_gap,close 段(0.8~2.0s)再擠到 gap
    zu0, zl0 = (ZB + g0 / 2 + FH[2], ZB - g0 / 2 - FH[2]) if a.preclose else (0.05 + FH[2], -0.05 - FH[2])
    GU.finger(st, pth + "_fu", FS, [FX, oy, zu0], fr, cont=a.fcont, color=(0.9, 0.45, 0.1))
    GU.finger(st, pth + "_fl", FS, [FX, oy, zl0], fr, cont=a.fcont, color=(0.9, 0.45, 0.1))
    SC.append(dict(k=k, gap=gap / 1e3, fr=fr, lift=a.lift, oy=oy, sheet=pth + "_sheet", fu=pth + "_fu", fl=pth + "_fl"))
F = info["F"]; EDG = SU.tri_edges(F); B = SU.bary_samples(4)
P("surface deformable ok=%s;每片 %d 點 %d 三角 %d 邊,格距 %.2fmm;板底 z=%.2fmm;指面 cont %.1fmm rest 0;布 cont %.1f rest %.1f thick %.1fmm"
  % (info["ok"], len(info["V"]), len(F), len(EDG), S / a.n * 1e3, ZB * 1e3, a.fcont * 1e3, a.cont * 1e3, a.rest * 1e3, a.thick * 1e3))

VIDEO = None
if a.video:
    c0 = SC[0]
    for _f in (c0["fu"], c0["fl"]):
        UsdGeom.Imageable(st.GetPrimAtPath(_f)).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    GU.bind_vis(st, st.GetPrimAtPath(c0["sheet"]), (0.25, 0.55, 0.85), "sheetvis")
    VBU = GU.VisBox(st, "/World/vis_fu", FS, (0.9, 0.45, 0.1)); VBL = GU.VisBox(st, "/World/vis_fl", FS, (0.9, 0.45, 0.1))
    _c = [float(x) for x in a.cam.split(",")]
    EYE = [_c[0], c0["oy"] + _c[1], _c[2]]; TGT = [_c[3], c0["oy"] + _c[4], _c[5]]
    VIDEO = GU.Video(st, os.path.join(HERE, "videos", tag + ".mp4"), EYE, TGT, focal=a.focal,
                     label="G1 SURFACE gap %.1fmm finger mu %.1f lift 3s | E2e4 bend4 thick4 cont5 rest1 n%d(%.1fmm) solver%d dt1/%d"
                     % (c0["gap"] * 1e3, c0["fr"], a.n, S / a.n * 1e3, a.solver, round(1 / a.dt)))
world.reset()
if VIDEO is not None:
    VIDEO.init(); VIDEO.look(EYE, TGT)
for _ in range(2):
    sim.update()
FPATHS = [s["fu"] for s in SC] + [s["fl"] for s in SC]
FV = world.physics_sim_view.create_rigid_body_view(FPATHS)
_pi = {p: i for i, p in enumerate(FPATHS)}
ORD = np.array([_pi[p] for p in FV.prim_paths]); FIDX = np.arange(FV.count, dtype=np.int32)
for s in SC:
    s["mesh"] = SU.SMesh(st, s["sheet"]); s["flat"] = s["mesh"].pts().copy()
L0 = np.linalg.norm(SC[0]["flat"][EDG[:, 0]] - SC[0]["flat"][EDG[:, 1]], axis=1)

T_SET = 0.8; T_CL = 1.2; T_HOLD = 0.4; T_PULL = 2.0; T_STAY = 2.0; T_OPEN = 0.3; T_OBS = 1.5
LIFT_H = 0.150; PULL_D = 0.100
ss = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.), 1.))
def tl(s):
    t1 = T_SET + T_CL; t2 = t1 + T_HOLD; t3 = t2 + s["lift"]; t4 = t3 + T_PULL; t5 = t4 + T_STAY; t6 = t5 + T_OPEN
    return dict(close0=T_SET, closed=t1, lift0=t2, lift1=t3, pull1=t4, open0=t5, open1=t6, end=t6 + T_OBS)
for s in SC:
    s["tl"] = tl(s); s["zc"] = ZB if a.preclose else None
T_END = max(s["tl"]["end"] for s in SC)

def phase(s, t):
    q = s["tl"]
    for nm, k in [("settle", "close0"), ("close", "closed"), ("hold", "lift0"), ("lift", "lift1"), ("pull", "pull1"),
                  ("stay", "open0"), ("open", "open1")]:
        if t < q[k]:
            return nm
    return "observe"

def finger_c(s, t):
    q = s["tl"]; oy = s["oy"]
    if s["zc"] is None:
        return np.array([FX, oy, 0.05 + FH[2]]), np.array([FX, oy, -0.05 - FH[2]])
    zc = s["zc"]; g = s["gap"]
    hu0, hl0 = 0.05 + FH[2], -0.05 - FH[2]
    hu1, hl1 = zc + g / 2 + FH[2], zc - g / 2 - FH[2]
    if a.preclose:
        g0 = max(g, a.pre_gap); gg = g0 + (g - g0) * ss((t - q["close0"]) / T_CL)
        zu = zc + gg / 2 + FH[2]; zl = zc - gg / 2 - FH[2]
    else:
        u = ss((t - q["close0"]) / T_CL)
        zu = hu0 + (hu1 - hu0) * u; zl = hl0 + (hl1 - hl0) * u
    dz = LIFT_H * ss((t - q["lift0"]) / s["lift"])
    dx = PULL_D * ss((t - q["lift1"]) / T_PULL)
    op = 0.020 * ss((t - q["open0"]) / T_OPEN)
    return np.array([FX + dx, oy, zu + dz + op]), np.array([FX + dx, oy, zl + dz - op])

def drive(t):
    D = np.zeros((len(FPATHS), 7), np.float32); D[:, 6] = 1.0
    n = len(SC)
    for i, s in enumerate(SC):
        cu, cl = finger_c(s, t)
        D[i, :3] = cu; D[n + i, :3] = cl
    FV.set_kinematic_targets(D[ORD], FIDX)

def foot(Pp, c):
    return (np.abs(Pp[:, 0] - c[0]) < FH[0]) & (np.abs(Pp[:, 1] - c[1]) < FH[1])

ME = int(round(0.05 / a.dt)); NSTEP = int(round(T_END / a.dt)); SPF = max(1, int(round(1.0 / (30 * a.dt))))
for s in SC:
    s.update(ts=[], slip_med=[], slip_max=[], com=[], pen_n=[], pen_d=[], spen_n=[], spen_d=[], lmax=[], cl_u=[], cl_l=[], ph=[], G=None)
P("時間表(秒):settle %.1f → close %.1f → hold %.1f → lift 150mm %.0f → pull 100mm %.1f → stay %.1f → open %.1f → obs %.1f;總長 %.2f"
  % (T_SET, T_CL, T_HOLD, a.lift, T_PULL, T_STAY, T_OPEN, T_OBS, T_END))
t0w = time.time()
for step in range(1, NSTEP + 1):
    t = step * a.dt
    if a.preclose and abs(t - T_SET) < a.dt / 2:
        for s in SC:
            if s["k"] == 0 or a.only:
                Pp = s["mesh"].pts(); fu, fl = finger_c(s, t); m = foot(Pp, fu)
                P("  [s%02d] t=%.2f(preclose)指面投影內 %d 點 z %s mm;上指底 %.2f 下指頂 %.2f;板邊頂點 z min %.2f x max %.2f"
                  % (s["k"], t, int(m.sum()), (Pp[m, 2] * 1e3).round(2).tolist(), (fu[2] - FH[2]) * 1e3, (fl[2] + FH[2]) * 1e3,
                     Pp[:, 2].min() * 1e3, Pp[:, 0].max() * 1e3))
    for s in SC:
        if s["zc"] is None and t >= T_SET:
            Pp = s["mesh"].pts(); fu, _ = finger_c(s, t)
            m = foot(Pp, fu)
            if not m.any():
                P("  DEBUG s%02d n=%d bbox %s ~ %s fu %s flat0 %s" % (s["k"], len(Pp), Pp.min(0).round(4), Pp.max(0).round(4), fu.round(4), s["flat"][:3].round(4)))
                sim.close(); sys.exit(1)
            s["zc"] = float(Pp[m, 2].mean())
            if s["k"] == 0 or a.only:
                P("  [s%02d] t=%.2f 懸出段(指面投影內 %d 點)z %.2f~%.2f mm,zc=%.2f;板邊頂點 z min %.2f;整片 z %.2f~%.2f"
                  % (s["k"], t, int(m.sum()), Pp[m, 2].min() * 1e3, Pp[m, 2].max() * 1e3, s["zc"] * 1e3,
                     Pp[Pp[:, 0] > Pp[:, 0].max() - 1e-4, 2].min() * 1e3, Pp[:, 2].min() * 1e3, Pp[:, 2].max() * 1e3))
    drive(t)
    rend = VIDEO is not None and step % SPF == 0
    world.step(render=rend)
    if rend:
        s0 = SC[0]; _cu, _cl = finger_c(s0, t); VBU.set(_cu); VBL.set(_cl)
        VIDEO.frame(t, "%s  gap %.1fmm mu %.1f  SURFACE" % (phase(s0, t), s0["gap"] * 1e3, s0["fr"]))
    if a.dbg_early and t < 0.8 and step % 3 == 0:
        s0 = SC[0]; Pp = s0["mesh"].pts(); fu, fl = finger_c(s0, t)
        if "G0" not in s0:
            s0["G0"] = np.where(foot(s0["flat"], fu))[0]
        P("  dbg t=%.3f G0 %s xz %s | fu z %.2f fl z %.2f | FV pos %s" % (t, s0["G0"].tolist(), (Pp[s0["G0"]][:, [0, 2]] * 1e3).round(1).tolist(),
          fu[2] * 1e3, fl[2] * 1e3, (FV.get_transforms()[:, :3] * 1e3).round(1).tolist()))
    if step % ME:
        continue
    for s in SC:
        Pp = s["mesh"].pts()
        if not np.isfinite(Pp).all():
            if not s.get("nan"):
                P("★ NaN s%02d t=%.2f" % (s["k"], t))
            s["nan"] = t; continue
        cu, cl = finger_c(s, t); ph = phase(s, t)
        if s["G"] is None and t >= s["tl"]["lift0"] - 1e-9:
            G = np.where(foot(Pp, cu) & (Pp[:, 2] > cl[2]) & (Pp[:, 2] < cu[2]))[0]
            s["G"] = G; s["rel0"] = Pp[G] - cu
            P("  [s%02d] 夾持頂點 %d 個:%s;z %s mm(上指底 %.2f 下指頂 %.2f)"
              % (s["k"], len(G), G.tolist(), (Pp[G, 2] * 1e3).round(2).tolist(), (cu[2] - FH[2]) * 1e3, (cl[2] + FH[2]) * 1e3))
        if s["G"] is not None and len(s["G"]):
            dd = np.linalg.norm(Pp[s["G"]] - cu - s["rel0"], axis=1)
            s["slip_med"].append(float(np.median(dd))); s["slip_max"].append(float(dd.max()))
            s["cl_u"].append(float(np.median((cu[2] - FH[2]) - Pp[s["G"], 2]))); s["cl_l"].append(float(np.median(Pp[s["G"], 2] - (cl[2] + FH[2]))))
        else:
            s["slip_med"].append(np.nan); s["slip_max"].append(np.nan); s["cl_u"].append(np.nan); s["cl_l"].append(np.nan)
        mu_, du = GU.in_box(Pp, cu, FH); ml_, dl = GU.in_box(Pp, cl, FH)
        npn = int(mu_.sum() + ml_.sum()); dmax = max(du[mu_].max() if mu_.any() else 0.0, dl[ml_].max() if ml_.any() else 0.0)
        Q = SU.surf_samples(Pp, F, B)
        qu, qdu = GU.in_box(Q, cu, FH); ql, qdl = GU.in_box(Q, cl, FH)
        nsp = int(qu.sum() + ql.sum()); sdmax = max(qdu[qu].max() if qu.any() else 0.0, qdl[ql].max() if ql.any() else 0.0)
        Lr = np.linalg.norm(Pp[EDG[:, 0]] - Pp[EDG[:, 1]], axis=1) / L0
        s["ts"].append(t); s["com"].append(Pp.mean(0)); s["ph"].append(ph)
        s["pen_n"].append(npn); s["pen_d"].append(float(dmax)); s["spen_n"].append(nsp); s["spen_d"].append(float(sdmax))
        s["lmax"].append(float(Lr.max())); s["Plast"] = Pp
        if "stick" not in s and t >= s["tl"]["open1"] + 0.1 - 1e-9:
            _nu = GU.in_box(Pp, cu, FH + 0.002)[0]; _nl = GU.in_box(Pp, cl, FH + 0.002)[0]
            s["stick"] = int((_nu | _nl).sum())
        if a.only or (step % (ME * 10) == 0 and s["k"] == 0):
            P("  [s%02d] t=%5.2f %-7s 上指 (%.1f,%.1f) | 滑動 中位 %.2f 最大 %.2f mm | 指-布間隙 上 %.2f 下 %.2f mm | 質心 z %.1f | 穿指 頂點 %d 深 %.2f / 面取樣 %d 深 %.2fmm | 邊長比 max %.3f"
              % (s["k"], t, ph, cu[0] * 1e3, cu[2] * 1e3, s["slip_med"][-1] * 1e3, s["slip_max"][-1] * 1e3, s["cl_u"][-1] * 1e3,
                 s["cl_l"][-1] * 1e3, s["com"][-1][2] * 1e3, npn, dmax * 1e3, nsp, sdmax * 1e3, Lr.max()))
    if step % (ME * 40) == 0:
        P("  ... t=%.2f wall %.0fs" % (t, time.time() - t0w))
wall = time.time() - t0w
if VIDEO is not None:
    VIDEO.close(); P("影片 → %s(%d 幀)" % (VIDEO.path, VIDEO.n))

P("\n===== 判讀 G1 surface =====")
P("判準:夾持期間滑動(中位)< 5mm、穿指深度 < 1mm(頂點與面取樣都算)、邊長比最大 < 1.5")
rows = []
for s in SC:
    ts = np.array(s["ts"]); q = s["tl"]
    grip = (ts >= q["lift0"]) & (ts < q["open0"])
    sm = np.array(s["slip_med"]); sx = np.array(s["slip_max"]); com = np.array(s["com"])
    ms = float(np.nanmax(sm[grip])) if grip.any() else np.nan
    mx = float(np.nanmax(sx[grip])) if grip.any() else np.nan
    pn = int(np.max(np.array(s["pen_n"])[grip])); pd = float(np.max(np.array(s["pen_d"])[grip]))
    spn = int(np.max(np.array(s["spen_n"])[grip])); spd = float(np.max(np.array(s["spen_d"])[grip]))
    lmax = float(np.max(np.array(s["lmax"])[grip]))
    st_ = (ts >= q["pull1"]) & (ts < q["open0"])
    com_z_stay = float(com[st_, 2].mean()); com_z0 = float(com[0, 2])
    clu = float(np.nanmedian(np.array(s["cl_u"])[st_])); cll = float(np.nanmedian(np.array(s["cl_l"])[st_]))
    ob = (ts >= q["open1"]) & (ts <= q["open1"] + 0.3); i_open = np.searchsorted(ts, q["open0"])
    com_ob = com[ob]
    drop = float(com[i_open - 1, 2] - com_ob[-1, 2])
    vmax = float(np.max(np.linalg.norm(np.diff(com_ob[:, :2], axis=0), axis=1)) / 0.05) if len(com_ob) > 1 else np.nan
    vz = float(np.max(np.diff(com[ts >= q["open0"], 2])) / 0.05) if (ts >= q["open0"]).sum() > 1 else np.nan
    carried = com_z_stay - com_z0 > 0.030
    ok = carried and ms < 0.005 and max(pd, spd) < 0.001 and lmax < 1.5 and not s.get("nan")
    ok_nolen = carried and ms < 0.005 and max(pd, spd) < 0.001 and not s.get("nan")
    r = dict(k=s["k"], gap=s["gap"] * 1e3, fr=s["fr"], nG=len(s["G"]) if s["G"] is not None else 0, slip=ms * 1e3, slip_max=mx * 1e3,
             com_z0=com_z0 * 1e3, com_z_stay=com_z_stay * 1e3, carried=bool(carried), pen_n=pn, pen_d=pd * 1e3, spen_n=spn, spen_d=spd * 1e3,
             clear_u=clu * 1e3, clear_l=cll * 1e3, lmax=lmax, drop_after_open=drop * 1e3, stick=s.get("stick", -1), vcom_after_open=vmax,
             vz_up_after_open=vz, ok=bool(ok), ok_nolen=bool(ok_nolen), nan=s.get("nan"))
    rows.append(r)
    P("  s%02d gap %.1f mu %.1f | 夾持頂點 %d | 滑動 中位 %.2f / 最大 %.2f mm | 停時 質心 z %.1f(初 %.1f)帶起 %s | 指-布間隙 上 %.2f 下 %.2f mm | 穿指 頂點 %d 深 %.2fmm / 面取樣 %d 深 %.2fmm | 邊長比最大 %.3f | 張開後 質心掉 %.1fmm 指旁 2mm 內 %d 點 水平速度 %.3f m/s 上衝 %.3f m/s ⇒ %s(不看邊長比 %s)"
      % (r["k"], r["gap"], r["fr"], r["nG"], r["slip"], r["slip_max"], r["com_z_stay"], r["com_z0"], "是" if carried else "否",
         r["clear_u"], r["clear_l"], pn, r["pen_d"], spn, r["spen_d"], lmax, r["drop_after_open"], r["stick"], vmax, vz,
         "PASS" if ok else "FAIL", "PASS" if ok_nolen else "FAIL"))
json.dump(rows, open(os.path.join(HERE, "data", tag + ".json"), "w"), indent=1, default=float)
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(14, 5))
    for s in SC:
        ls = "-" if s["fr"] >= 2 else "--"
        ax[0].plot(s["ts"], np.array(s["slip_med"]) * 1e3, ls, lw=1, label="g%.0f mu%.1f" % (s["gap"] * 1e3, s["fr"]))
        ax[1].plot(s["ts"], np.array(s["com"])[:, 2] * 1e3, ls, lw=1)
    ax[0].axhline(5, color="k", lw=.6); ax[0].set_ylabel("slip median mm"); ax[0].set_ylim(0, 60); ax[0].legend(fontsize=7, ncol=2)
    ax[1].set_ylabel("sheet COM z mm")
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "img", tag + "_slip.png"), dpi=90); plt.close(fig)
except Exception as e:
    P("plot 失敗", e)
P("wall %.1fs / sim %.2fs | 顯存 %s" % (wall, T_END, VC.gpu_mem_mib()))
LOG.close()
sim.close()
