#!/usr/bin/env python3
"""probe_grip.py — G1:kinematic 平行夾爪純摩擦夾持 volume 薄板(無 attachment)。

    /isaac-sim/python.sh probe_grip.py                         # 18 組(間隙 x 摩擦 x 抬升速度)同一個 stage 平行跑
    /isaac-sim/python.sh probe_grip.py --only 4,1.0,3 --video  # 單組 + 錄影

每組一個場景(沿 y 間隔 SPC):桌面 = 靜態方塊,頂面 z=0、邊緣 x=0(場景局部);
板 200x200xT 平放,+x 邊懸出桌緣 30mm。兩片 kinematic 指面 20x20x8mm(x,y,z),
指面中心 x = 桌緣 + 21mm(覆蓋 x 11~31mm,板邊在 30mm),y = 板邊中點。
時間表:settle → 量懸出段中面高 zc → 上下指從 ±50mm 合到「指面間距 = gap」(以 zc 為中心)→ hold
       → 抬 150mm(T_LIFT,smoothstep)→ 往 +x 拉 100mm(2s)→ 停 2s → 張開(各退 20mm,0.3s)→ 看 1.5s
材料(定案):E 2e3、nu 0.45、T 4mm、0.1kg/m²、板摩擦 0.8、manual 35x35x1、cont 2mm / rest 0.5mm、
           自碰撞開 filter 2x rest、solver 128、dt 1/240。指面 cont 1mm rest 0;桌面摩擦 --table_fric。
"""
import os, sys, argparse, time, json
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--gaps", default="4,3,2", help="指面間距 mm")
ap.add_argument("--frics", default="0.5,1.0,2.0")
ap.add_argument("--lifts", default="3,1", help="抬升秒數")
ap.add_argument("--only", default="", help="gap,fric,lift 單組")
ap.add_argument("--video", action="store_true")
ap.add_argument("--table_fric", type=float, default=0.5)
ap.add_argument("--young", type=float, default=2e3)
ap.add_argument("--poisson", type=float, default=0.45)
ap.add_argument("--thick_mm", type=float, default=4.0)
ap.add_argument("--areal", type=float, default=0.1)
ap.add_argument("--fric", type=float, default=0.8)
ap.add_argument("--nxy", type=int, default=35)
ap.add_argument("--cont", type=float, default=0.002)
ap.add_argument("--rest", type=float, default=0.0005)
ap.add_argument("--solver", type=int, default=128)
ap.add_argument("--dt", type=float, default=1 / 240.0)
ap.add_argument("--tag", default="")
ap.add_argument("--focal", type=float, default=4.0)
ap.add_argument("--cam", default="0.42,-0.62,0.36,0.0,0.0,0.07", help="eye xyz, target xyz(場景局部)")
ap.add_argument("--t_end", type=float, default=0.0, help="除錯:只跑到這個時間")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ["logs", "img", "videos", "data"]:
    os.makedirs(os.path.join(HERE, d), exist_ok=True)
if a.only:
    g_, f_, l_ = [float(x) for x in a.only.split(",")]
    CFG = [(g_, f_, l_)]
else:
    CFG = [(g, f, l) for g in map(float, a.gaps.split(",")) for f in map(float, a.frics.split(","))
           for l in map(float, a.lifts.split(","))]
tag = a.tag or ("g1_" + ("only_%g_%g_%g" % CFG[0] if a.only else "sweep"))
LOG = open(os.path.join(HERE, "logs", tag + ".log"), "w")
def P(*s):
    m = " ".join(str(x) for x in s); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()

os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from pxr import UsdGeom, PhysxSchema, Sdf, Vt, Gf
import omni.usd
sys.path.insert(0, HERE)
import gutil as GU
import volcommon as VC
import vol_pen as VP

P("=== G1 %s ===" % tag); P("args:", vars(a)); P("組數 %d:%s" % (len(CFG), CFG))
world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane(z_position=-0.4)
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

T = a.thick_mm / 1e3; S = 0.200; OVH = 0.030
FS = np.array([0.020, 0.020, 0.008]); FH = FS / 2
FX = 0.021                     # 指面中心 x(相對桌緣)
SPC = 0.40
ZB = a.rest + 1e-4
SC = []
GU.static_box(st, "/World/table", [0.6, SPC * (len(CFG) - 1) + 0.3, 0.05], [-0.3, SPC * (len(CFG) - 1) / 2, -0.025], a.table_fric, color=(0.35, 0.25, 0.18))
for k, (gap, fr, lift) in enumerate(CFG):
    oy = SPC * k
    pth = "/World/s%02d" % k
    info = VC.build_plate(st, pth + "_plate", S, T, ZB, "manual", nxy=a.nxy, nz=1, youngs=a.young, poisson=a.poisson,
                          areal=a.areal, fric=a.fric, cont=a.cont, rest=a.rest, solver=a.solver, self_coll=True,
                          self_filter=2 * a.rest, cx=OVH - S / 2, cy=oy, P=(P if k == 0 else (lambda *s: None)))
    fu = GU.finger(st, pth + "_fu", FS, [FX, oy, 0.05 + FH[2]], fr, color=(0.9, 0.45, 0.1))
    fl = GU.finger(st, pth + "_fl", FS, [FX, oy, -0.05 - FH[2]], fr, color=(0.9, 0.45, 0.1))
    SC.append(dict(k=k, gap=gap / 1e3, fr=fr, lift=lift, oy=oy, path=pth, plate=pth + "_plate",
                   fu=pth + "_fu", fl=pth + "_fl"))
P("場景 %d 個;板 %.0fx%.0fx%.0fmm 底 z=%.2fmm,+x 邊懸出 %.0fmm;指面 %s mm 中心 x=%.0fmm;桌面摩擦 %.2f"
  % (len(SC), S * 1e3, S * 1e3, T * 1e3, ZB * 1e3, OVH * 1e3, FS * 1e3, FX * 1e3, a.table_fric))

VIS = None
if a.video:
    c0 = SC[0]
    VIS = GU.vis_mesh(st, "/World/plate_vis", np.zeros(((a.nxy + 1) ** 2 * 2, 3)), a.nxy, a.nxy, (0.25, 0.55, 0.85))
    UsdGeom.Imageable(st.GetPrimAtPath(c0["plate"])).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    for _f in (c0["fu"], c0["fl"]):
        UsdGeom.Imageable(st.GetPrimAtPath(_f)).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    VBU = GU.VisBox(st, "/World/vis_fu", FS, (0.9, 0.45, 0.1)); VBL = GU.VisBox(st, "/World/vis_fl", FS, (0.9, 0.45, 0.1))
    _c = [float(x) for x in a.cam.split(",")]
    EYE = [_c[0], c0["oy"] + _c[1], _c[2]]; TGT = [_c[3], c0["oy"] + _c[4], _c[5]]
    VID = GU.Video(st, os.path.join(HERE, "videos", tag + ".mp4"), EYE, TGT, focal=a.focal,
                   label="G1 gap %.0fmm  finger mu %.1f  lift %.0fs | E2e3 nu.45 T4 0.1kg/m2 mu.8 n35 solver128 dt1/240"
                   % (c0["gap"] * 1e3, c0["fr"], c0["lift"]))
world.reset()
if VIS is not None:
    VID.init(); VID.look(EYE, TGT); P("cam pose after look:", VID.cam.get_world_pose(camera_axes="world"), "EYE", EYE, "TGT", TGT)
for _ in range(2):
    sim.update()
FPATHS = [s["fu"] for s in SC] + [s["fl"] for s in SC]
FV = world.physics_sim_view.create_rigid_body_view(FPATHS)
_pi = {p: i for i, p in enumerate(FPATHS)}
ORD = np.array([_pi[p] for p in FV.prim_paths]); FIDX = np.arange(FV.count, dtype=np.int32)
for s in SC:
    s["mesh"] = VC.Mesh(st, s["plate"])
    s["flat"] = s["mesh"].pts().copy()
TETS = SC[0]["mesh"].tets()
V0 = VP.tet_vol(SC[0]["flat"], TETS)
EDG = GU.edges(TETS)
L0 = np.linalg.norm(SC[0]["flat"][EDG[:, 0]] - SC[0]["flat"][EDG[:, 1]], axis=1)
N1 = (a.nxy + 1) ** 2
P("每板 %d 點 %d tets;dxy %.2fmm" % (len(SC[0]["flat"]), len(TETS), S / a.nxy * 1e3))

T_SET = 0.8; T_CL = 1.2; T_HOLD = 0.4; T_PULL = 2.0; T_STAY = 2.0; T_OPEN = 0.3; T_OBS = 1.5
LIFT_H = 0.150; PULL_D = 0.100
ss = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.), 1.))
def tl(s):
    t1 = T_SET + T_CL; t2 = t1 + T_HOLD; t3 = t2 + s["lift"]; t4 = t3 + T_PULL; t5 = t4 + T_STAY; t6 = t5 + T_OPEN
    return dict(close0=T_SET, closed=t1, lift0=t2, lift1=t3, pull1=t4, open0=t5, open1=t6, end=t6 + T_OBS)
for s in SC:
    s["tl"] = tl(s); s["zc"] = None
T_END = max(s["tl"]["end"] for s in SC)
if a.t_end > 0:
    T_END = a.t_end

def phase(s, t):
    q = s["tl"]
    for nm, k in [("settle", "close0"), ("close", "closed"), ("hold", "lift0"), ("lift", "lift1"), ("pull", "pull1"),
                  ("stay", "open0"), ("open", "open1")]:
        if t < q[k]:
            return nm
    return "observe"

def finger_c(s, t):
    """回傳 (上指中心, 下指中心)。"""
    q = s["tl"]; oy = s["oy"]
    if s["zc"] is None:
        return np.array([FX, oy, 0.05 + FH[2]]), np.array([FX, oy, -0.05 - FH[2]])
    zc = s["zc"]; g = s["gap"]
    hu0, hl0 = 0.05 + FH[2], -0.05 - FH[2]
    hu1, hl1 = zc + g / 2 + FH[2], zc - g / 2 - FH[2]
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

def foot(Pp, c, shrink=0.0):
    return (np.abs(Pp[:, 0] - c[0]) < FH[0] - shrink) & (np.abs(Pp[:, 1] - c[1]) < FH[1] - shrink)

ME = int(round(0.05 / a.dt))
NSTEP = int(round(T_END / a.dt))
SPF = int(round(1.0 / (30 * a.dt)))
for s in SC:
    s.update(ts=[], slip_med=[], slip_p90=[], com=[], far=[], pen_n=[], pen_d=[], inv=[], volr=[], lmax=[], lmin=[],
             gz=[], fz=[], ph=[], G=None)
t0w = time.time(); nan = False
P("時間表(秒):settle %.1f → close %.1f → hold %.1f → lift 150mm %s → pull 100mm %.1f → stay %.1f → open %.1f → obs %.1f;總長 %.2f"
  % (T_SET, T_CL, T_HOLD, "/".join("%g" % l for l in sorted(set(s["lift"] for s in SC))), T_PULL, T_STAY, T_OPEN, T_OBS, T_END))
for step in range(1, NSTEP + 1):
    t = step * a.dt
    for s in SC:
        if s["zc"] is None and t >= T_SET:
            Pp = s["mesh"].pts()
            fu, _ = finger_c(s, t)
            m = foot(Pp, fu)
            s["zc"] = float(Pp[m, 2].mean())
            s["zc_rng"] = (float(Pp[m, 2].min()), float(Pp[m, 2].max()))
            if s["k"] == 0 or a.only:
                P("  [s%02d] t=%.2f 懸出段(指面投影內 %d 點)z %.2f~%.2f mm,中面 zc=%.2f;板邊(x 最大)頂點 z min %.2f"
                  % (s["k"], t, int(m.sum()), s["zc_rng"][0] * 1e3, s["zc_rng"][1] * 1e3, s["zc"] * 1e3,
                     Pp[np.argmax(Pp[:, 0]), 2] * 1e3))
    drive(t)
    rend = VIS is not None and step % SPF == 0
    world.step(render=rend)
    if rend:
        s0 = SC[0]; Pp = s0["mesh"].pts()
        VIS.Set(Vt.Vec3fArray.FromNumpy((Pp).astype(np.float32)))
        _cu, _cl = finger_c(s0, t); VBU.set(_cu); VBL.set(_cl)
        _im = VID.frame(t, "%s  gap %.1fmm mu %.1f" % (phase(s0, t), s0["gap"] * 1e3, s0["fr"]))
        if a.t_end > 0 and step % (SPF * 15) == 0:
            _pts = np.array([[0.021, 0, 0.0], [-0.3, 0, 0], [0, -0.15, 0], [0, 0.15, 0], [-0.6, -0.15, 0]])
            P("  cam", VID.cam.get_world_pose(camera_axes="world"), "proj", VID.cam.get_image_coords_from_world_points(_pts).round(0).tolist(),
              "plate mean", Pp.mean(0).round(3), "VIS mean", np.array(VIS.Get()).mean(0).round(3))
        if a.t_end > 0 and _im is not None:
            from PIL import Image; Image.fromarray(_im).save(os.path.join(HERE, "img", tag + "_frame.png"))
    if step % ME:
        continue
    for s in SC:
        Pp = s["mesh"].pts()
        if not np.isfinite(Pp).all():
            P("★ NaN s%02d t=%.2f" % (s["k"], t)); nan = True; s["nan"] = t
            continue
        cu, cl = finger_c(s, t)
        ph = phase(s, t)
        if s["G"] is None and t >= s["tl"]["lift0"] - 1e-9:
            G = np.where(foot(Pp, cu) & (Pp[:, 2] > cl[2]) & (Pp[:, 2] < cu[2]))[0]
            s["G"] = G; s["rel0"] = Pp[G] - cu
            s["n_top"] = int((G >= N1).sum()); s["n_bot"] = int((G < N1).sum())
        if s["G"] is not None and len(s["G"]):
            dd = np.linalg.norm(Pp[s["G"]] - cu - s["rel0"], axis=1)
            s["slip_med"].append(float(np.median(dd))); s["slip_p90"].append(float(np.percentile(dd, 90)))
        else:
            s["slip_med"].append(np.nan); s["slip_p90"].append(np.nan)
        mu_, du = GU.in_box(Pp, cu, FH); ml_, dl = GU.in_box(Pp, cl, FH)
        npn = int(mu_.sum() + ml_.sum())
        dmax = max(du[mu_].max() if mu_.any() else 0.0, dl[ml_].max() if ml_.any() else 0.0)
        ninv, v = VC.inverted(Pp, TETS, V0)
        Lr = np.linalg.norm(Pp[EDG[:, 0]] - Pp[EDG[:, 1]], axis=1) / L0
        _em = (Pp[EDG[:, 0]] + Pp[EDG[:, 1]]) / 2
        _ng = (np.abs(_em[:, 0] - cu[0]) < FH[0] + 0.008) & (np.abs(_em[:, 1] - cu[1]) < FH[1] + 0.008) & \
              (_em[:, 2] > cl[2] - FH[2] - 0.008) & (_em[:, 2] < cu[2] + FH[2] + 0.008)
        _nA = (np.abs(_em[:, 0] - cu[0]) < FH[0]) & (np.abs(_em[:, 1] - cu[1]) < FH[1]) & \
              (_em[:, 2] > cl[2] + FH[2] - 0.001) & (_em[:, 2] < cu[2] - FH[2] + 0.001)
        s.setdefault("lA", []).append(float(Lr[_nA].max()) if _nA.any() else 1.0)
        _nB = _ng & ~_nA
        s.setdefault("lB", []).append(float(Lr[_nB].max()) if _nB.any() else 1.0)
        _iB = np.argmax(np.where(_nB, Lr, 0)); s.setdefault("lB_at", []).append((_em[_iB] - cu).copy())
        s.setdefault("lg", []).append(float(Lr[_ng].max()) if _ng.any() else 1.0)
        s.setdefault("lo", []).append(float(Lr[~_ng].max()))
        _io = np.argmax(np.where(_ng, 0, Lr))
        s.setdefault("lo_at", []).append((_em[_io] - cu).copy())
        far = s["flat"][:, 0] < s["flat"][:, 0].min() + 1e-6
        s["ts"].append(t); s["com"].append(Pp.mean(0)); s["far"].append(float(Pp[far, 2].max()))
        s["pen_n"].append(npn); s["pen_d"].append(float(dmax)); s["inv"].append(ninv); s["volr"].append(float(v.sum() / V0.sum()))
        s["lmax"].append(float(Lr.max())); s["lmin"].append(float(Lr.min())); s["fz"].append(cu.copy()); s["ph"].append(ph)
        s["gz"].append(float(Pp[s["G"], 2].mean()) if s["G"] is not None and len(s["G"]) else np.nan)
        s["Plast"] = Pp
        if "stick" not in s and t >= s["tl"]["open1"] + 0.1 - 1e-9:
            _nu = GU.in_box(Pp, cu, FH + 0.002)[0]; _nl = GU.in_box(Pp, cl, FH + 0.002)[0]
            s["stick"] = int((_nu | _nl).sum())
        if a.only or step % (ME * 10) == 0 and s["k"] in (0,):
            P("  [s%02d] t=%5.2f %-7s 上指 (%.1f,%.1f) | 滑動 中位 %.2f p90 %.2f mm | 質心 z %.1f 遠端 z %.1f | 穿指 %d 深 %.2fmm | 反轉 %d 體積比 %.4f 邊長比 [%.3f,%.3f]"
              % (s["k"], t, ph, cu[0] * 1e3, cu[2] * 1e3, s["slip_med"][-1] * 1e3, s["slip_p90"][-1] * 1e3,
                 s["com"][-1][2] * 1e3, s["far"][-1] * 1e3, npn, dmax * 1e3, ninv, s["volr"][-1], Lr.min(), Lr.max()))
    if step % (ME * 20) == 0:
        P("  ... t=%.2f wall %.0fs" % (t, time.time() - t0w))
wall = time.time() - t0w
if VIS is not None:
    VID.close(); P("影片 → %s(%d 幀)" % (VID.path, VID.n))

if a.t_end > 0:
    sim.close(); sys.exit(0)
# ── 判讀 ──
P("\n===== 判讀 G1 =====")
P("判準:全程滑動 < 5mm、穿夾爪深度 < 1mm、反轉 0、邊長比最大 < 1.5")
rows = []
for s in SC:
    ts = np.array(s["ts"]); ph = np.array(s["ph"])
    q = s["tl"]
    grip = (ts >= q["lift0"]) & (ts < q["open0"])           # 夾持期間(抬、拉、停)
    sm = np.array(s["slip_med"]); sp = np.array(s["slip_p90"])
    com = np.array(s["com"]); gz = np.array(s["gz"]); fz = np.array(s["fz"])
    ms = np.nanmax(sm[grip]) if grip.any() else np.nan
    mp_ = np.nanmax(sp[grip]) if grip.any() else np.nan
    pn = int(np.max(np.array(s["pen_n"])[grip])); pd = float(np.max(np.array(s["pen_d"])[grip]))
    inv = int(np.max(s["inv"])); lmax = float(np.max(np.array(s["lmax"])[grip])); vr = (float(np.min(s["volr"])), float(np.max(s["volr"])))
    st_ = (ts >= q["pull1"]) & (ts < q["open0"])            # 停的那 2s
    com_z_stay = float(com[st_, 2].mean()) if st_.any() else np.nan
    gz_stay = float(np.nanmean(gz[st_])) if st_.any() else np.nan
    fz_stay = float(fz[st_, 2].mean() - s["gap"] / 2 - FH[2]) if st_.any() else np.nan   # 上下指之間中面 z
    far_max = float(np.max(np.array(s["far"])[grip]))
    lg = float(np.max(np.array(s["lg"])[grip])); lo_ = np.array(s["lo"]); io = np.argmax(np.where(grip, lo_, 0))
    lo_max = float(lo_[io]); lo_at = s["lo_at"][io] * 1e3
    lA = float(np.max(np.array(s["lA"])[grip])); lB_ = np.array(s["lB"]); iB = np.argmax(np.where(grip, lB_, 0))
    lB = float(lB_[iB]); lB_at = s["lB_at"][iB] * 1e3
    # 張開後:open1 之後 0.3s 內,質心水平位移 / 指旁殘留
    ob = (ts >= q["open1"]) & (ts <= q["open1"] + 0.3)
    i_open = np.searchsorted(ts, q["open0"])
    if ob.any():
        com_ob = com[ob]
        drop = float(com[i_open - 1, 2] - com_ob[-1, 2])
        stick = s.get("stick", -1)        # 張開完 0.1s 時,指面方塊外擴 2mm 內的布頂點數(黏住)
        vmax = float(np.max(np.linalg.norm(np.diff(com_ob[:, :2], axis=0), axis=1)) / 0.05) if len(com_ob) > 1 else np.nan
    else:
        drop = stick = vmax = np.nan
    ok = (ms < 0.005) and (pd < 0.001) and inv == 0 and lmax < 1.5 and not s.get("nan")
    ok_g = (ms < 0.005) and (pd < 0.001) and inv == 0 and lg < 1.5 and not s.get("nan")
    r = dict(k=s["k"], gap=s["gap"] * 1e3, fr=s["fr"], lift=s["lift"], slip=ms * 1e3, slip90=mp_ * 1e3, nG=len(s["G"]) if s["G"] is not None else 0,
             nG_top=s.get("n_top"), nG_bot=s.get("n_bot"),
             zc=s["zc"] * 1e3, com_z0=float(com[0, 2]) * 1e3, com_z_stay=com_z_stay * 1e3, gz_stay=gz_stay * 1e3, fz_stay=fz_stay * 1e3,
             far_max=far_max * 1e3, pen_n=pn, pen_d=pd * 1e3, inv=inv, lmax=lmax, volr=vr, drop_after_open=drop * 1e3,
             stick=stick, vcom_after_open=vmax, ok=bool(ok), nan=s.get("nan"),
             lmax_grip=lg, lmax_between=lA, lmax_bend=lB, lmax_bend_at=list(lB_at), lmax_else=lo_max, lmax_else_at=list(lo_at), ok_grip=bool(ok_g))
    rows.append(r)
    P("  s%02d gap %.0f mu %.1f lift %.0fs | 夾持頂點 %d(頂面 %s 底面 %s)| 最大滑動 中位 %.2f / p90 %.2f mm | 停時 質心 z %.1f(初 %.1f)夾點 z %.1f 指中 z %.1f | 遠端 z 最高 %.1f | 穿指 %d 點 深 %.2fmm | 反轉 %d 邊長比最大 %.3f(夾持區 %.3f = 指面之間 %.3f / 指緣外 8mm 內 %.3f @ (%.0f,%.0f,%.0f);其他 %.3f @ 相對上指 (%.0f,%.0f,%.0f)mm)體積比 %.4f~%.4f | 張開後 質心掉 %.1fmm、指旁 2mm 內 %d 點、0.3s 內質心水平速度最大 %.3f m/s ⇒ %s(只看夾持區邊長比 %s)"
      % (r["k"], r["gap"], r["fr"], r["lift"], r["nG"], r["nG_top"], r["nG_bot"], r["slip"], r["slip90"], r["com_z_stay"], r["com_z0"],
         r["gz_stay"], r["fz_stay"], r["far_max"], pn, r["pen_d"], inv, lmax, lg, lA, lB, *lB_at, lo_max, *lo_at, vr[0], vr[1], r["drop_after_open"], stick,
         r["vcom_after_open"], "PASS" if ok else "FAIL", "PASS" if ok_g else "FAIL"))
json.dump(rows, open(os.path.join(HERE, "data", tag + ".json"), "w"), indent=1, default=float)
np.savez_compressed(os.path.join(HERE, "data", tag + ".npz"),
                    **{"s%02d_%s" % (s["k"], k): np.array(s[k]) for s in SC for k in ["ts", "slip_med", "slip_p90", "com", "far", "pen_n", "pen_d", "lmax", "gz"]})
# 圖:滑動 vs 時間
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(14, 5))
    for s in SC:
        ls = "-" if s["lift"] >= 2 else "--"
        ax[0].plot(s["ts"], np.array(s["slip_med"]) * 1e3, ls, lw=1, label="g%.0f mu%.1f L%.0f" % (s["gap"] * 1e3, s["fr"], s["lift"]))
        ax[1].plot(s["ts"], np.array(s["com"])[:, 2] * 1e3, ls, lw=1)
    ax[0].axhline(5, color="k", lw=.6); ax[0].set_ylabel("slip median mm"); ax[0].set_xlabel("t s"); ax[0].set_ylim(0, 60)
    ax[1].set_ylabel("plate COM z mm"); ax[1].set_xlabel("t s")
    ax[0].legend(fontsize=6, ncol=2); fig.tight_layout(); fig.savefig(os.path.join(HERE, "img", tag + "_slip.png"), dpi=90)
    plt.close(fig)
    s0 = SC[0]
    VC.snap(os.path.join(HERE, "img", tag + "_s00_end.png"), s0["Plast"], tag + " s00 end", xlim=(-200, 160), zlim=(-20, 200))
except Exception as e:
    P("plot 失敗", e)
P("wall %.1fs / sim %.2fs | 顯存 %s" % (wall, T_END, VC.gpu_mem_mib()))
LOG.close()
sim.close()
