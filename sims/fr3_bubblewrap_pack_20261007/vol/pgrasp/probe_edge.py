#!/usr/bin/env python3
"""probe_edge.py — [pgrasp] 階段 1:單片「沿整條自由邊」純摩擦夾持探針(不綁定)。

    /isaac-sim/python.sh probe_edge.py --tag sweep                       # 18 組(L x mu x gap)同 stage 平行
    /isaac-sim/python.sh probe_edge.py --only 4 --video --tag v_L150_mu1.5_g3.0   # 單組 + 錄影

幾何(每組一個場景,沿 x 間隔 SPC):300(x)x200(y)x4mm 板,底在 z=0 桌面上;自由邊 y=-100mm(朝 -y),
根部 y>=+80mm 兩排頂點綁到不碰撞的 kinematic 錨(模擬片根被壓住;這是「根部固定」,不是夾爪)。
桌面 y∈[edge+30, +150]:自由邊最後 30mm 懸空,讓下指能滑進布下。
夾爪 = 兩片 kinematic 碰撞體寬指:L(沿邊 x)x D 20(y)x T 6(z),摩擦 mu,cont 1mm / rest 0。
時間表:settle 1.0 → 下指從自由邊外 start_out(前緣)、指頂在布底 -below_mm,沿 +y 水平滑到前緣在邊內 insert_mm(1.0s)
       → 上指從上方 40mm 下降到指間 gap(1.0s)→ 停 hold 0.5s → 沿圓弧(繞片根,R = kR x 夾心到鉸點)掀 theta_max
       → 再沿 +y 外拉 pull_mm(弧 + 拉 = peel_t)→ 停 stay。指頭跟著片轉(R_x(-theta)),布從指出去的方向一直朝鉸點。
量:指間布頂點數、夾住頂點(hold 結束時指間的)相對指面的切向位移 中位/最大、掉布時刻(指間頂點數歸零)、
    邊長比最大、布穿指(頂點落在指盒內)、掀完片自由段越過鉸點比例 / 質心。
"""
import os, sys, argparse, time, json, itertools
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--Ls", default="100,150,200", help="指長 mm(沿邊)")
ap.add_argument("--mus", default="1.0,1.5,2.0", help="指面摩擦")
ap.add_argument("--gaps", default="3.0,2.5", help="合指後指間 mm(= 布厚 4 - 壓縮)")
ap.add_argument("--only", default="", help="逗號分隔的組號(0..17,順序 L→mu→gap);空 = 全部")
ap.add_argument("--video", action="store_true", help="錄第一個場景")
ap.add_argument("--fd_mm", type=float, default=20.0, help="指深(y)")
ap.add_argument("--ft_mm", type=float, default=6.0, help="指厚(z)")
ap.add_argument("--start_out_mm", type=float, default=30.0, help="下指前緣起點在自由邊外")
ap.add_argument("--insert_mm", type=float, default=25.0, help="下指前緣滑到自由邊內")
ap.add_argument("--below_mm", type=float, default=6.0, help="下指指頂在布底(指面足跡內最低)下方")
ap.add_argument("--overhang_mm", type=float, default=30.0, help="自由邊懸空長度(桌緣在邊內)")
ap.add_argument("--kR", type=float, default=0.9)
ap.add_argument("--theta_deg", type=float, default=110.0)
ap.add_argument("--pull_mm", type=float, default=60.0)
ap.add_argument("--peel_t", type=float, default=6.0)
ap.add_argument("--pull_frac", type=float, default=0.25, help="peel_t 中外拉佔的比例")
ap.add_argument("--hold_t", type=float, default=0.5)
ap.add_argument("--stay_t", type=float, default=1.0)
ap.add_argument("--fcont", type=float, default=0.001)
ap.add_argument("--frest", type=float, default=0.0)
ap.add_argument("--table_fric", type=float, default=0.8)
ap.add_argument("--young", type=float, default=2e3)
ap.add_argument("--poisson", type=float, default=0.45)
ap.add_argument("--thick_mm", type=float, default=4.0)
ap.add_argument("--areal", type=float, default=0.1)
ap.add_argument("--fric", type=float, default=0.8)
ap.add_argument("--cell_mm", type=float, default=500 / 35.0, help="網格間距(= wrap_vol sheet 500 / nxy 35)")
ap.add_argument("--cont", type=float, default=0.002)
ap.add_argument("--rest", type=float, default=0.0005)
ap.add_argument("--solver", type=int, default=48)
ap.add_argument("--dt", type=float, default=1 / 120.0)
ap.add_argument("--focal", type=float, default=3.0)
ap.add_argument("--cam", default="-0.62,-0.42,0.30,0.0,0.02,0.05")
ap.add_argument("--tag", default="sweep")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
VOLD = os.path.dirname(HERE)
OUT = os.path.join(HERE, a.tag)
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "probe_edge.log"), "w")
def P(*s):
    m = " ".join(str(x) for x in s); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()

ALL = list(itertools.product([float(x) for x in a.Ls.split(",")], [float(x) for x in a.mus.split(",")],
                             [float(x) for x in a.gaps.split(",")]))
SEL = [int(x) for x in a.only.split(",")] if a.only else list(range(len(ALL)))

os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from pxr import UsdGeom, PhysxSchema, Vt
import omni.usd
sys.path.insert(0, os.path.join(VOLD, "grip")); sys.path.insert(0, VOLD)
import gutil as GU
import volcommon as VC

P("=== pgrasp probe_edge %s ===" % a.tag); P("args:", vars(a))
P("組:", ["%d:L%.0f_mu%.1f_g%.1f" % (k, *ALL[k]) for k in SEL])
world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane(z_position=-0.4)
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

T = a.thick_mm / 1e3; SX, SY = 0.300, 0.200
NX, NY = int(round(SX * 1e3 / a.cell_mm)), int(round(SY * 1e3 / a.cell_mm))
YE = -SY / 2                                    # 自由邊 y
YROOT = SY / 2 - 0.020                          # y >= 這個的頂點綁錨
FD, FT = a.fd_mm / 1e3, a.ft_mm / 1e3
YF1 = YE + a.insert_mm / 1e3                    # 下指前緣終點
YG = YF1 - FD / 2                               # 夾心 y
YF0 = YE - a.start_out_mm / 1e3                 # 下指前緣起點
SPC = 0.65
ZB = a.rest + 1e-4
kw = dict(nxy=NY, nx=NX, size_y=SY, nz=1, youngs=a.young, poisson=a.poisson, areal=a.areal, fric=a.fric, cont=a.cont,
          rest=a.rest, solver=a.solver, self_coll=True, self_filter=2 * a.rest)
SC = []
for n_, k in enumerate(SEL):
    L, mu, gap = ALL[k]
    ox = SPC * n_; pth = "/World/s%d" % k
    GU.static_box(st, pth + "_table", [SX + 0.06, (SY / 2 + 0.05) - (YE + a.overhang_mm / 1e3), 0.05],
                  [ox, ((SY / 2 + 0.05) + (YE + a.overhang_mm / 1e3)) / 2, -0.025], a.table_fric, color=(0.35, 0.25, 0.18))
    VC.build_plate(st, pth + "_sheet", SX, T, ZB, "manual", cx=ox, cy=0.0, P=(P if n_ == 0 else (lambda *s: None)), **kw)
    FS = np.array([L / 1e3, FD, FT])
    GU.finger(st, pth + "_fu", FS, [ox, YG, 0.08], mu, cont=a.fcont, rest=a.frest, color=(0.9, 0.45, 0.1))
    GU.finger(st, pth + "_fl", FS, [ox, YF0 - FD / 2, -0.03], mu, cont=a.fcont, rest=a.frest, color=(0.9, 0.45, 0.1))
    VC.kin_box(st, pth + "_anc", [0.02, 0.02, 0.02], [ox, SY / 2, 0.01], collide=False, visible=False)
    SC.append(dict(k=k, L=L, mu=mu, gap=gap, ox=ox, sheet=pth + "_sheet", fu=pth + "_fu", fl=pth + "_fl", anc=pth + "_anc",
                   FS=FS, FH=FS / 2, name="L%.0f_mu%.1f_g%.1f" % (L, mu, gap)))
# 根部綁錨(build 後才有頂點)
for s in SC:
    P0 = VC.Mesh(st, s["sheet"]).pts()
    vids = np.where(P0[:, 1] >= YROOT - 1e-6)[0]
    VC.attach_vtx(st, s["sheet"] + "_rootatt", s["sheet"], s["sheet"], s["anc"], vids, P0[vids] - np.array([s["ox"], SY / 2, 0.01]),
                  P=(P if s is SC[0] else (lambda *x: None)))
    s["nroot"] = len(vids)
YH = float(np.unique(np.round(VC.Mesh(st, SC[0]["sheet"]).pts()[:, 1], 6))[np.unique(np.round(VC.Mesh(st, SC[0]["sheet"]).pts()[:, 1], 6)) >= YROOT - 1e-6].min())
P("板 %.0fx%.0fx%.0fmm 網格 %dx%dx1(間距 %.2fx%.2fmm);根部綁 %d 點(y>=%.1f,鉸點 y=%.1f);桌緣 y=%.1f(懸空 %.0fmm)"
  % (SX * 1e3, SY * 1e3, T * 1e3, NX, NY, SX / NX * 1e3, SY / NY * 1e3, SC[0]["nroot"], YROOT * 1e3, YH * 1e3,
     (YE + a.overhang_mm / 1e3) * 1e3, a.overhang_mm))
P("指 D %.0f T %.0f;下指前緣 %.0f → %.0f mm(邊 %.0f),夾心 y %.1f;cont %.1fmm rest %.1fmm"
  % (a.fd_mm, a.ft_mm, YF0 * 1e3, YF1 * 1e3, YE * 1e3, YG * 1e3, a.fcont * 1e3, a.frest * 1e3))

VIS = None
if a.video:
    s0 = SC[0]
    for p_ in (s0["sheet"], s0["fu"], s0["fl"]):
        UsdGeom.Imageable(st.GetPrimAtPath(p_)).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    VIS = GU.vis_mesh(st, "/World/vis_sheet", np.zeros(((NX + 1) * (NY + 1) * 2, 3)), NX, NY, (0.25, 0.55, 0.85))
    VBU = GU.VisBox(st, "/World/vis_fu", s0["FS"], (0.9, 0.45, 0.1)); VBL = GU.VisBox(st, "/World/vis_fl", s0["FS"], (0.9, 0.35, 0.05))
    _c = [float(x) for x in a.cam.split(",")]
    EYE = [s0["ox"] + _c[0], _c[1], _c[2]]; TGT = [s0["ox"] + _c[3], _c[4], _c[5]]
    VID = GU.Video(st, os.path.join(OUT, "probe_edge.mp4"), EYE, TGT, focal=a.focal,
                   label="pgrasp edge  L%.0f D%.0f T%.0f mm  mu %.1f  gap %.1f  | 300x200x4 E2e3 0.1kg/m2 | dt 1/%.0f solver %d | friction only (no attach)"
                   % (s0["L"], a.fd_mm, a.ft_mm, s0["mu"], s0["gap"], 1 / a.dt, a.solver))
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
    s["m"] = VC.Mesh(st, s["sheet"]); s["P0"] = s["m"].pts().copy()
TETS = SC[0]["m"].tets()
V0 = VC.tet_vol(SC[0]["P0"], TETS)
EDG = GU.edges(TETS)
L0 = np.linalg.norm(SC[0]["P0"][EDG[:, 0]] - SC[0]["P0"][EDG[:, 1]], axis=1)
N1 = (NX + 1) * (NY + 1)
FREE = np.where(SC[0]["P0"][:, 1] < YH - 1e-6)[0]          # 自由段(鉸點外)

T_SET = 1.0; T_SL = 1.0; T_CL = 1.0
t_sl0 = T_SET; t_cl0 = t_sl0 + T_SL; t_hold = t_cl0 + T_CL; t_peel = t_hold + a.hold_t
t_arc1 = t_peel + a.peel_t * (1 - a.pull_frac); t_pull1 = t_peel + a.peel_t; T_END = t_pull1 + a.stay_t
THM = np.radians(a.theta_deg)
ss = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.), 1.))
def phase(t):
    for nm, tt in [("settle", t_sl0), ("slide", t_cl0), ("close", t_hold), ("hold", t_peel), ("arc", t_arc1), ("pull", t_pull1)]:
        if t < tt:
            return nm
    return "stay"

def rot_x(al):
    c, s_ = np.cos(al), np.sin(al)
    return np.array([[1, 0, 0], [0, c, -s_], [0, s_, c]])

def fpose(s, t):
    """(上指中心, 下指中心, R 指→世界, 四元數 wxyz, θ, 夾心)。"""
    ox = s["ox"]; FH = s["FH"]
    if s.get("zl") is None:
        return np.array([ox, YG, 0.08]), np.array([ox, YF0 - FD / 2, -0.03]), np.eye(3), np.array([1., 0, 0, 0]), 0.0, None
    zl = s["zl"]; gap = s["gap"] / 1e3                       # zl = 下指指頂
    gc0 = np.array([ox, YG, zl + gap / 2])
    if t < t_peel:
        yl = (YF0 + (YF1 - YF0) * ss((t - t_sl0) / T_SL)) - FD / 2
        cl = np.array([ox, yl, zl - FH[2]])
        zu = zl + gap + FH[2] + 0.040 * (1 - ss((t - t_cl0) / T_CL))
        return np.array([ox, YG, zu]), cl, np.eye(3), np.array([1., 0, 0, 0]), 0.0, gc0
    th = THM * ss((t - t_peel) / (t_arc1 - t_peel))
    C = np.array([ox, YG + s["R"], gc0[2]])
    g = C + s["R"] * np.array([0, -np.cos(th), np.sin(th)])
    g = g + np.array([0, a.pull_mm / 1e3 * ss((t - t_arc1) / (t_pull1 - t_arc1)), 0])
    R = rot_x(-th); q = np.array([np.cos(-th / 2), np.sin(-th / 2), 0, 0])
    n = R @ np.array([0, 0, 1.0]); h = gap / 2 + FH[2]
    return g + n * h, g - n * h, R, q, th, g

def drive(t):
    D = np.zeros((len(FPATHS), 7), np.float32); n = len(SC)
    for i, s in enumerate(SC):
        cu, cl, R, q, _, _ = fpose(s, t)
        for j, c in ((i, cu), (n + i, cl)):
            D[j, :3] = c; D[j, 3:6] = q[1:]; D[j, 6] = q[0]
    FV.set_kinematic_targets(D[ORD], FIDX)

ME = int(round(0.05 / a.dt)); NSTEP = int(round(T_END / a.dt)); SPF = max(1, int(round(1.0 / (30 * a.dt))))
for s in SC:
    s.update(ts=[], ph=[], nb=[], ng=[], slip_med=[], slip_max=[], lmax=[], pen_n=[], pen_d=[], inv=[], past=[], comy=[], comz=[], G=None,
             drop_t=None, R=None)
P("時間表:settle %.1f 滑入→%.2f 合指→%.2f 停→%.2f 弧(θ %.0f°)→%.2f 外拉 %.0fmm→%.2f 停→%.2f"
  % (T_SET, t_cl0, t_hold, t_peel, a.theta_deg, t_arc1, a.pull_mm, t_pull1, T_END))
t0w = time.time()
for step in range(1, NSTEP + 1):
    t = step * a.dt
    for s in SC:
        if s.get("zl") is None and t >= T_SET - 0.1:
            Pp = s["m"].pts()
            m = (np.abs(Pp[:, 0] - s["ox"]) < s["FH"][0]) & (Pp[:, 1] < YF1 + 1e-6)
            zb = float(Pp[m, 2].min())
            s["zl"] = zb - a.below_mm / 1e3
            s["R"] = a.kR * (YH - YG)
            P("  [%s] t=%.2f 邊區(指長內、y<前緣終點)%d 點 z %.2f~%.2f mm(邊頂點 z min %.2f)→ 下指頂 z %.2f;弧半徑 %.0fmm"
              % (s["name"], t, int(m.sum()), Pp[m, 2].min() * 1e3, Pp[m, 2].max() * 1e3, Pp[np.abs(s["P0"][:, 1] - YE) < 2e-3, 2].min() * 1e3,
                 s["zl"] * 1e3, s["R"] * 1e3))
    drive(t)
    rend = VIS is not None and step % SPF == 0
    world.step(render=rend)
    if rend:
        s0 = SC[0]
        VIS.Set(Vt.Vec3fArray.FromNumpy(s0["m"].pts().astype(np.float32)))
        cu, cl, R, q, th, _ = fpose(s0, t)
        VBU.set(cu, q); VBL.set(cl, q)
        nb_ = s0["nb"][-1] if s0["nb"] else 0
        VID.frame(t, "%-6s theta %3.0f deg | between fingers %3d vtx | slip med %4.1f mm" % (phase(t), np.degrees(th), nb_,
                  (s0["slip_med"][-1] * 1e3 if s0["slip_med"] and np.isfinite(s0["slip_med"][-1]) else 0.0)))
    if step % ME or t < t_hold - 1e-9:
        continue
    for s in SC:
        Pp = s["m"].pts()
        if not np.isfinite(Pp).all():
            if s.get("nan") is None:
                P("★ NaN %s t=%.2f" % (s["name"], t)); s["nan"] = t
            continue
        cu, cl, R, q, th, gc = fpose(s, t)
        Lc = (Pp - gc) @ R
        FH = s["FH"]; gh = s["gap"] / 2e3
        inxy = (np.abs(Lc[:, 0]) < FH[0]) & (np.abs(Lc[:, 1]) < FH[1])
        btw = inxy & (np.abs(Lc[:, 2]) < gh + 0.0015)
        if s["G"] is None and t >= t_peel - 1e-9:
            s["G"] = np.where(btw)[0]; s["rel0"] = Lc[s["G"]].copy()
            P("  [%s] t=%.2f 掀前指間頂點 %d(頂面 %d 底面 %d)" % (s["name"], t, len(s["G"]), int((s["G"] >= N1).sum()), int((s["G"] < N1).sum())))
        if s["G"] is not None and len(s["G"]):
            d = np.linalg.norm(Lc[s["G"], :2] - s["rel0"][:, :2], axis=1)
            smed, smax = float(np.median(d)), float(d.max())
            s["dxy"] = np.median(Lc[s["G"], :2] - s["rel0"][:, :2], axis=0)      # 滑動方向(局部 x = 沿邊、y = 往鉸點)
            ng = int(btw[s["G"]].sum())
        else:
            smed = smax = np.nan; ng = 0
        # 穿指:頂點落在上 / 下指盒內(指盒中心在 ±(gap/2 + FT/2))的深度
        pd = 0.0; pn = 0
        for sgn in (1, -1):
            c = np.array([0, 0, sgn * (gh + FH[2])])
            mm, dd = GU.in_box(Lc, c, FH)
            if mm.any():
                pn += int(mm.sum()); pd = max(pd, float(dd[mm].max()))
        lr = float((np.linalg.norm(Pp[EDG[:, 0]] - Pp[EDG[:, 1]], axis=1) / L0).max())
        inv = VC.inverted(Pp, TETS, V0)[0]
        F = Pp[FREE]
        s["ts"].append(t); s["ph"].append(phase(t)); s["nb"].append(int(btw.sum())); s["ng"].append(ng)
        s["slip_med"].append(smed); s["slip_max"].append(smax); s["lmax"].append(lr); s["pen_n"].append(pn); s["pen_d"].append(pd)
        s["inv"].append(inv); s["past"].append(float((F[:, 1] > YH).mean())); s["comy"].append(float(F[:, 1].mean())); s["comz"].append(float(F[:, 2].mean()))
        if t >= t_peel and s["drop_t"] is None and int(btw.sum()) == 0:
            s["drop_t"] = t; P("  ★ [%s] t=%.2f 掉布(指間 0 頂點)θ=%.0f°" % (s["name"], t, np.degrees(th)))
        if step % (ME * 10) == 0 or len(SC) == 1:
            P("  [%s] t=%5.2f %-6s θ=%5.1f° | 指間 %3d(夾住集 %3d/%d)| 滑動 中位 %5.2f 最大 %6.2f mm | 穿指 %d 點 %.2fmm | 邊長比 %.3f 反轉 %d | 自由段過鉸 %3.0f%% 質心 y %.0f z %.0f mm"
              % (s["name"], t, phase(t), np.degrees(th), s["nb"][-1], ng, len(s["G"]) if s["G"] is not None else 0, smed * 1e3, smax * 1e3,
                 pn, pd * 1e3, lr, inv, 100 * s["past"][-1], s["comy"][-1] * 1e3, s["comz"][-1] * 1e3))
    if step % (ME * 40) == 0:
        P("  -- t=%.2f wall %.0fs" % (t, time.time() - t0w))
wall = time.time() - t0w
if VIS is not None:
    VID.close(); P("影片 → %s(%d 幀)" % (VID.path, VID.n))

P("\n===== 判讀 pgrasp probe_edge =====")
P("判準:掀開全程(peel 起到 stay 結束)不掉布(指間頂點 > 0)且 夾住集滑動中位 < 5mm")
rows = []
for s in SC:
    ts = np.array(s["ts"]); pe = ts >= t_peel - 1e-9; ar = (ts >= t_peel - 1e-9) & (ts < t_arc1 + 1e-9)
    nb = np.array(s["nb"]); sm = np.array(s["slip_med"]); sx = np.array(s["slip_max"])
    i_arc = int(np.searchsorted(ts, t_arc1 - 1e-9)); i_pull = int(np.searchsorted(ts, t_pull1 - 1e-9))
    G = s["G"] if s["G"] is not None else []
    r = dict(k=s["k"], name=s["name"], L=s["L"], mu=s["mu"], gap=s["gap"], nG=len(G),
             nb_hold=int(nb[ts < t_peel - 1e-9].max()) if (ts < t_peel - 1e-9).any() else -1,
             nb_min=int(nb[pe].min()), nb_arc_end=int(nb[i_arc]), nb_end=int(nb[-1]),
             slip_med_arc=float(sm[i_arc]) * 1e3, slip_med_end=float(sm[-1]) * 1e3, slip_med_max=float(np.nanmax(sm[pe])) * 1e3,
             slip_max_max=float(np.nanmax(sx[pe])) * 1e3, drop_t=s["drop_t"],
             drop_th=(float(np.degrees(THM * ss((s["drop_t"] - t_peel) / (t_arc1 - t_peel)))) if s["drop_t"] else None),
             lmax=float(np.max(s["lmax"])), pen_n=int(np.max(s["pen_n"])), pen_d=float(np.max(s["pen_d"])) * 1e3,
             inv=int(np.max(s["inv"])), past_arc=float(s["past"][i_arc]), past_end=float(s["past"][-1]),
             comy_end=float(s["comy"][-1]) * 1e3, comz_end=float(s["comz"][-1]) * 1e3, nan=s.get("nan"))
    r["slip_dx"], r["slip_dy"] = [float(x) * 1e3 for x in s.get("dxy", [np.nan, np.nan])]
    r["ok"] = bool(r["drop_t"] is None and r["nb_min"] > 0 and r["slip_med_end"] < 5 and not r["nan"])
    rows.append(r)
    P("ROW %2d %-16s | 掀前指間 %3d | 掀中指間 min %3d 弧末 %3d 結束 %3d | 滑動中位 弧末 %6.2f 結束 %6.2f 最大 %6.2f | 滑動最大 %7.2f mm | 掉布 %s | 邊長比 %.3f | 穿指 %d 點 %.2fmm | 反轉 %d | 過鉸 弧末 %3.0f%% 結束 %3.0f%% 質心 y %.0f z %.0f | %s"
      % (r["k"], r["name"], r["nG"], r["nb_min"], r["nb_arc_end"], r["nb_end"], r["slip_med_arc"], r["slip_med_end"], r["slip_med_max"],
         r["slip_max_max"], ("t=%.2f θ=%.0f°" % (r["drop_t"], r["drop_th"])) if r["drop_t"] else "無", r["lmax"], r["pen_n"], r["pen_d"],
         r["inv"], 100 * r["past_arc"], 100 * r["past_end"], r["comy_end"], r["comz_end"], "PASS" if r["ok"] else "FAIL"))
    P("SLIPDIR %2d %-16s 結束時夾住集位移中位 局部 x(沿邊)%.2f y(+ = 往鉸點)%.2f mm" % (r["k"], r["name"], r["slip_dx"], r["slip_dy"]))
    VC.snap(os.path.join(OUT, "end_%s.png" % s["name"]), s["m"].pts() - np.array([s["ox"], 0, 0]), "%s end" % s["name"])
json.dump(dict(args=vars(a), rows=rows, series={s["name"]: dict(t=s["ts"], nb=s["nb"], slip_med=s["slip_med"], slip_max=s["slip_max"], lmax=s["lmax"])
                                                for s in SC}), open(os.path.join(OUT, "probe_edge.json"), "w"), indent=1, default=float)
P("wall %.1fs / sim %.2fs | 顯存 %s" % (wall, T_END, VC.gpu_mem_mib()))
LOG.close()
sim.close()
