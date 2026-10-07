#!/usr/bin/env python3
"""probe_peel.py — G2:兩片疊板只夾上片,往上掀並沿圓弧翻 180°(像翻書),看下片會不會被帶走。

    /isaac-sim/python.sh probe_peel.py                     # 兩組(無重物 / 0.08kg 方塊壓上片遠端)同 stage 平行
    /isaac-sim/python.sh probe_peel.py --only 1 --video    # 單組 + 錄影(0 = 無重物、1 = 有重物)

幾何(每組一個場景,沿 y 間隔 SPC):桌面頂 z=0、+x 邊在 x=0。下片 200x200 x∈[-200,0](+x 邊齊桌緣);
上片 200x200 往 +x 錯開 25mm(x∈[-175,+25]),伸出桌緣與下片 25mm 當抓取邊。
指面 20x20x8mm,中心 x = 14.5mm(覆蓋 4.5~24.5mm,離下片邊 4.5mm),y = 0。
時間表:settle → 量伸出段中面高 zc → 上下指合到指面間距 gap → hold → 抬 LIFT0(1s)
       → 沿圓弧翻 180°(半徑 R、T_ARC 秒;指面跟著繞 y 轉 −θ,讓布從指面出去的方向一直朝圓心)
       → 停 1s → 張開(沿指面法線各退 20mm,0.3s)→ 看 1.5s
重物:0.08kg、40x40x40mm 動態方塊,放在上片遠端(中心 x = −145mm),摩擦 0.5。
判準(題目):下片位移 < 10mm、互穿 0、上片被完整掀開(翻過去的那一端 x 越過中線)。
"""
import os, sys, argparse, time, json
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--only", type=int, default=-1)
ap.add_argument("--video", action="store_true")
ap.add_argument("--gap_mm", type=float, default=4.0)
ap.add_argument("--ffric", type=float, default=2.0, help="指面摩擦")
ap.add_argument("--kR", type=float, default=0.9, help="圓弧半徑 = kR x(夾心到鉸點的材料長);鉸點 = 上片遠端(無重物)或重物 +x 緣(有重物)")
ap.add_argument("--lift0", type=float, default=0.020, help="翻之前先垂直抬 m")
ap.add_argument("--t_arc", type=float, default=4.0)
ap.add_argument("--table_fric", type=float, default=0.5)
ap.add_argument("--wmass", type=float, default=0.08)
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
ap.add_argument("--focal", type=float, default=3.0)
ap.add_argument("--cam", default="0.30,-0.80,0.45,-0.10,0.0,0.07")
ap.add_argument("--tag", default="")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ["logs", "img", "videos", "data"]:
    os.makedirs(os.path.join(HERE, d), exist_ok=True)
CFG = [0, 1] if a.only < 0 else [a.only]
tag = a.tag or ("g2_" + ("sweep" if a.only < 0 else ("weight" if a.only else "noweight")))
LOG = open(os.path.join(HERE, "logs", tag + ".log"), "w")
def P(*s):
    m = " ".join(str(x) for x in s); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()

os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from isaacsim.core.prims import SingleXFormPrim
from pxr import UsdGeom, UsdPhysics, PhysxSchema, Sdf, Vt, Gf
import omni.usd
sys.path.insert(0, HERE)
import gutil as GU
import volcommon as VC
import vol_pen as VP

P("=== G2 %s ===" % tag); P("args:", vars(a))
world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane(z_position=-0.4)
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

T = a.thick_mm / 1e3; S = 0.200; OFS = 0.025
FS = np.array([0.020, 0.020, 0.008]); FH = FS / 2
FX = 0.0145
SPC = 0.45
ZB = a.rest + 1e-4
ZU = ZB + T + 2 * a.rest + 0.0004
WS = 0.050
GAP = a.gap_mm / 1e3
SC = []
GU.static_box(st, "/World/table", [0.7, SPC * (len(CFG) - 1) + 0.32, 0.05], [-0.35, SPC * (len(CFG) - 1) / 2, -0.025],
              a.table_fric, color=(0.35, 0.25, 0.18))
kw = dict(nxy=a.nxy, nz=1, youngs=a.young, poisson=a.poisson, areal=a.areal, fric=a.fric, cont=a.cont, rest=a.rest,
          solver=a.solver, self_coll=True, self_filter=2 * a.rest)
for k, cf in enumerate(CFG):
    oy = SPC * k; pth = "/World/s%d" % k
    lo = VC.build_plate(st, pth + "_lower", S, T, ZB, "manual", cx=-S / 2, cy=oy, P=(P if k == 0 else (lambda *s: None)), **kw)
    up = VC.build_plate(st, pth + "_upper", S, T, ZU, "manual", cx=-S / 2 + OFS, cy=oy, P=(lambda *s: None), **kw)
    GU.finger(st, pth + "_fu", FS, [FX, oy, 0.05 + FH[2]], a.ffric, color=(0.9, 0.45, 0.1))
    GU.finger(st, pth + "_fl", FS, [FX, oy, -0.05 - FH[2]], a.ffric, color=(0.9, 0.45, 0.1))
    s = dict(k=k, weight=bool(cf), oy=oy, lower=pth + "_lower", upper=pth + "_upper", fu=pth + "_fu", fl=pth + "_fl")
    if cf:
        wp = pth + "_w"
        WX = -S / 2 + OFS - S / 2 + 0.030           # 上片遠端往內 30mm
        cb = UsdGeom.Cube.Define(st, wp); cb.CreateSizeAttr(1.0)
        xf = UsdGeom.Xformable(cb); xf.AddTranslateOp().Set(Gf.Vec3d(WX, oy, ZU + T + 0.003 + WS / 2))
        xf.AddOrientOp().Set(Gf.Quatf(1, 0, 0, 0)); xf.AddScaleOp().Set(Gf.Vec3f(WS, WS, WS))
        UsdPhysics.CollisionAPI.Apply(cb.GetPrim()); UsdPhysics.RigidBodyAPI.Apply(cb.GetPrim()).CreateKinematicEnabledAttr(True)
        UsdPhysics.MassAPI.Apply(cb.GetPrim()).CreateMassAttr(float(a.wmass))
        from omni.physx.scripts import physicsUtils
        physicsUtils.add_physics_material_to_prim(st, cb.GetPrim(), GU.rigid_mat(st, 0.5))
        pc = PhysxSchema.PhysxCollisionAPI.Apply(cb.GetPrim()); pc.CreateContactOffsetAttr(0.001); pc.CreateRestOffsetAttr(0.0)
        GU.bind_vis(st, cb.GetPrim(), (0.3, 0.3, 0.75), "weight")
        s["w"] = wp; s["wx0"] = np.array([WX, oy]); s["hinge"] = WX + WS / 2
    else:
        s["hinge"] = -S + OFS
    s["L"] = FX - s["hinge"]; s["R"] = a.kR * s["L"]
    SC.append(s)
P("場景 %d 個;下片 x∈[-200,0] 底 %.2fmm;上片 x∈[%.0f,%.0f] 底 %.2fmm;指面中心 x=%.1fmm;gap %.1fmm 指摩擦 %.1f;kR %.2f(R:%s mm)先抬 %.0fmm 翻 %.1fs;桌面摩擦 %.2f;重物 %.3fkg %.0fmm 方塊 @x=%s"
  % (len(SC), ZB * 1e3, (-S + OFS) * 1e3, OFS * 1e3, ZU * 1e3, FX * 1e3, a.gap_mm, a.ffric, a.kR, [round(s["R"] * 1e3) for s in SC], a.lift0 * 1e3, a.t_arc,
     a.table_fric, a.wmass, WS * 1e3, [round(s["wx0"][0] * 1e3, 1) for s in SC if "w" in s]))

VIS = None
if a.video:
    c0 = SC[0]
    VIS = dict(lower=GU.vis_mesh(st, "/World/vis_lower", np.zeros(((a.nxy + 1) ** 2 * 2, 3)), a.nxy, a.nxy, (0.85, 0.85, 0.80)),
               upper=GU.vis_mesh(st, "/World/vis_upper", np.zeros(((a.nxy + 1) ** 2 * 2, 3)), a.nxy, a.nxy, (0.25, 0.55, 0.85)))
    for p_ in (c0["lower"], c0["upper"], c0["fu"], c0["fl"]):
        UsdGeom.Imageable(st.GetPrimAtPath(p_)).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    VBU = GU.VisBox(st, "/World/vis_fu", FS, (0.9, 0.45, 0.1)); VBL = GU.VisBox(st, "/World/vis_fl", FS, (0.9, 0.45, 0.1))
    _c = [float(x) for x in a.cam.split(",")]
    EYE = [_c[0], c0["oy"] + _c[1], _c[2]]; TGT = [_c[3], c0["oy"] + _c[4], _c[5]]
    VID = GU.Video(st, os.path.join(HERE, "videos", tag + ".mp4"), EYE, TGT, focal=a.focal,
                   label="G2 %s | gap %.0fmm finger mu %.1f arc R%.0fmm %.0fs | E2e3 nu.45 T4 0.1kg/m2 mu.8 n35 solver128 dt1/240"
                   % ("weight %.2fkg on far end" % a.wmass if c0["weight"] else "no weight", a.gap_mm, a.ffric, c0["R"] * 1e3, a.t_arc))
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
    s["ml"] = VC.Mesh(st, s["lower"]); s["mu"] = VC.Mesh(st, s["upper"])
    s["fl0"] = s["ml"].pts().copy(); s["fu0"] = s["mu"].pts().copy()
    if "w" in s:
        s["wx"] = SingleXFormPrim(s["w"], name="w%d" % s["k"])
TETS = SC[0]["ml"].tets()
V0 = VP.tet_vol(SC[0]["fl0"], TETS)
EDG = GU.edges(TETS)
L0 = np.linalg.norm(SC[0]["fl0"][EDG[:, 0]] - SC[0]["fl0"][EDG[:, 1]], axis=1)
N1 = (a.nxy + 1) ** 2
BOT, TOP = np.arange(N1), np.arange(N1, 2 * N1)

T_SET = 0.8; T_CL = 1.2; T_HOLD = 0.4; T_L0 = 1.0; T_STAY = 1.0; T_OPEN = 0.3; T_OBS = 1.5
t_close0 = T_SET; t_closed = T_SET + T_CL; t_lift0 = t_closed + T_HOLD; t_arc0 = t_lift0 + T_L0
t_arc1 = t_arc0 + a.t_arc; t_open0 = t_arc1 + T_STAY; t_open1 = t_open0 + T_OPEN; T_END = t_open1 + T_OBS
ss = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.), 1.))
def phase(t):
    for nm, tt in [("settle", t_close0), ("close", t_closed), ("hold", t_lift0), ("lift", t_arc0), ("arc", t_arc1),
                   ("stay", t_open0), ("open", t_open1)]:
        if t < tt:
            return nm
    return "observe"

def fpose(s, t):
    """回傳 (上指中心, 下指中心, 旋轉矩陣 R(指→世界), 四元數 wxyz, θ)。"""
    oy = s["oy"]
    if s.get("zc") is None:
        return np.array([FX, oy, 0.05 + FH[2]]), np.array([FX, oy, -0.05 - FH[2]]), np.eye(3), np.array([1., 0, 0, 0]), 0.0
    zc = s["zc"]
    hu0, hl0 = 0.05 + FH[2], -0.05 - FH[2]
    hu1, hl1 = GAP / 2 + FH[2], -GAP / 2 - FH[2]           # 相對夾持中心
    u = ss((t - t_close0) / T_CL)
    du = (hu0 + (zc + hu1 - hu0) * u) - zc
    dl = (hl0 + (zc + hl1 - hl0) * u) - zc
    op = 0.020 * ss((t - t_open0) / T_OPEN)
    du += op; dl -= op
    g0 = np.array([FX, oy, zc + a.lift0 * ss((t - t_lift0) / T_L0)])
    th = np.pi * ss((t - t_arc0) / a.t_arc)
    C = np.array([FX - s["R"], oy, zc + a.lift0])
    g = C + s["R"] * np.array([np.cos(th), 0, np.sin(th)]) if t >= t_arc0 else g0
    al = -th
    R = VC.rot_y(al); q = VC.quat_y(al)
    n = R @ np.array([0, 0, 1.0])
    return g + n * du, g + n * dl, R, q, th

def drive(t):
    D = np.zeros((len(FPATHS), 7), np.float32)
    n = len(SC)
    for i, s in enumerate(SC):
        cu, cl, R, q, _ = fpose(s, t)
        for j, c in ((i, cu), (n + i, cl)):
            D[j, :3] = c; D[j, 3:6] = q[1:]; D[j, 6] = q[0]
    FV.set_kinematic_targets(D[ORD], FIDX)

def loc(Pp, c, R):
    return (Pp - c) @ R

ME = int(round(0.05 / a.dt)); NSTEP = int(round(T_END / a.dt)); SPF = int(round(1.0 / (30 * a.dt)))
for s in SC:
    s.update(ts=[], ph=[], slip=[], lo_com=[], lo_dmax=[], lo_zmax=[], pen=[], spen=[], inv=[], lmax=[], tipx=[], flipfrac=[],
             wpos=[], fx=[], G=None)
P("時間表:settle %.1f close→%.2f hold→%.2f 抬→%.2f 弧→%.2f 停→%.2f 開→%.2f 觀察→%.2f" % (T_SET, t_closed, t_lift0, t_arc0, t_arc1, t_open0, t_open1, T_END))
XMID = -S / 2                       # 下片中線 x
EDGE_U = np.where(np.abs(SC[0]["fu0"][:, 0] - SC[0]["fu0"][:, 0].max()) < 1e-6)[0]   # 上片 +x 邊(被夾那端)
P("上片 +x 邊頂點 %d 個;中線(下片中心)x = %.0f mm" % (len(EDGE_U), XMID * 1e3))
t0w = time.time()
for step in range(1, NSTEP + 1):
    t = step * a.dt
    for s in SC:
        if s.get("zc") is None and t >= T_SET:
            Pu = s["mu"].pts(); cu, _, _, _, _ = fpose(s, t)
            m = (np.abs(Pu[:, 0] - FX) < FH[0]) & (np.abs(Pu[:, 1] - s["oy"]) < FH[1])
            s["zc"] = float(Pu[m, 2].mean())
            Pl = s["ml"].pts()
            P("  [s%d] t=%.2f 上片伸出段(指面投影內 %d 點)z %.2f~%.2f 中面 zc=%.2f mm;下片 z %.2f~%.2f;上片邊緣頂點 z min %.2f"
              % (s["k"], t, int(m.sum()), Pu[m, 2].min() * 1e3, Pu[m, 2].max() * 1e3, s["zc"] * 1e3, Pl[:, 2].min() * 1e3,
                 Pl[:, 2].max() * 1e3, Pu[EDGE_U, 2].min() * 1e3))
    for s in SC:
        if "w" in s and not s.get("wdyn"):
            zt = ZU + T + 0.003 + WS / 2 - 0.0028 * ss(t / 0.4)
            s["wx"].set_world_pose(position=np.array([s["wx0"][0], s["oy"], zt]), orientation=np.array([1., 0, 0, 0]))
            if t >= 0.45:
                st.GetPrimAtPath(s["w"]).GetAttribute("physics:kinematicEnabled").Set(False); s["wdyn"] = True
                P("  [s%d] t=%.2f 重物轉 dynamic(底面 %.2fmm,上片頂 %.2fmm)" % (s["k"], t, (zt - WS / 2) * 1e3, (ZU + T) * 1e3))
    drive(t)
    rend = VIS is not None and step % SPF == 0
    world.step(render=rend)
    if rend:
        s0 = SC[0]
        VIS["lower"].Set(Vt.Vec3fArray.FromNumpy(s0["ml"].pts().astype(np.float32)))
        VIS["upper"].Set(Vt.Vec3fArray.FromNumpy(s0["mu"].pts().astype(np.float32)))
        cu, cl, R, q, th = fpose(s0, t)
        VBU.set(cu, q); VBL.set(cl, q)
        VID.frame(t, "%s  theta %.0f deg  %s" % (phase(t), np.degrees(th), "weight" if s0["weight"] else "no weight"))
    if step % ME:
        continue
    for s in SC:
        Pl = s["ml"].pts(); Pu = s["mu"].pts()
        if not (np.isfinite(Pl).all() and np.isfinite(Pu).all()):
            P("★ NaN s%d t=%.2f" % (s["k"], t)); s["nan"] = t; continue
        cu, cl, R, q, th = fpose(s, t)
        gc = (cu + cl) / 2
        if s["G"] is None and t >= t_lift0 - 1e-9:
            L = loc(Pu, gc, R)
            G = np.where((np.abs(L[:, 0]) < FH[0]) & (np.abs(L[:, 1]) < FH[1]) & (np.abs(L[:, 2]) < GAP / 2 + 0.002))[0]
            s["G"] = G; s["rel0"] = loc(Pu[G], gc, R)
            P("  [s%d] 夾住上片頂點 %d(頂面 %d 底面 %d)" % (s["k"], len(G), int((G >= N1).sum()), int((G < N1).sum())))
        sl = float(np.median(np.linalg.norm(loc(Pu[s["G"]], gc, R) - s["rel0"], axis=1))) if s["G"] is not None and len(s["G"]) else np.nan
        dl = Pl - s["fl0"]
        npen1, _ = VP.pen_count(Pu, np.arange(len(Pu)), Pl, TETS)
        npen2, _ = VP.pen_count(Pl, np.arange(len(Pl)), Pu, TETS)
        sp_u, _ = VP.self_pen_count(Pu, TETS, s["fu0"]); sp_l, _ = VP.self_pen_count(Pl, TETS, s["fl0"])
        inv = VC.inverted(Pu, TETS, V0)[0] + VC.inverted(Pl, TETS, V0)[0]
        lr = max((np.linalg.norm(Pu[EDG[:, 0]] - Pu[EDG[:, 1]], axis=1) / L0).max(), (np.linalg.norm(Pl[EDG[:, 0]] - Pl[EDG[:, 1]], axis=1) / L0).max())
        ff = float((Pu[TOP, 2] < Pu[BOT, 2]).mean())        # 上片翻面比例(原頂面跑到原底面下面)
        s["ts"].append(t); s["ph"].append(phase(t)); s["slip"].append(sl)
        s["lo_com"].append(np.linalg.norm(dl.mean(0))); s["lo_dmax"].append(np.linalg.norm(dl, axis=1).max()); s["lo_zmax"].append(Pl[:, 2].max())
        s["pen"].append(npen1 + npen2); s["spen"].append(sp_u + sp_l); s["inv"].append(inv); s["lmax"].append(lr)
        s["tipx"].append((Pu[EDGE_U, 0].min(), Pu[EDGE_U, 0].max())); s["flipfrac"].append(ff); s["fx"].append(gc.copy())
        if "w" in s:
            wp = np.array(s["wx"].get_world_pose()[0]); s["wpos"].append(wp)
        s["Pu"] = Pu; s["Pl"] = Pl
        if step % (ME * 5) == 0 or a.only >= 0:
            P("  [s%d] t=%5.2f %-7s θ=%5.1f° 夾心 (%.0f,%.0f) | 滑動 %.2fmm | 下片 質心位移 %.2f 最大點位移 %.2f 最高 z %.2f mm | 上下片互穿 %d 自穿 %d | 反轉 %d 邊長比 %.3f | 上片夾持端 x %.0f~%.0f 翻面 %.0f%%%s"
              % (s["k"], t, phase(t), np.degrees(th), gc[0] * 1e3, gc[2] * 1e3, sl * 1e3, s["lo_com"][-1] * 1e3, s["lo_dmax"][-1] * 1e3,
                 s["lo_zmax"][-1] * 1e3, npen1 + npen2, sp_u + sp_l, inv, lr, s["tipx"][-1][0] * 1e3, s["tipx"][-1][1] * 1e3, 100 * ff,
                 (" | 重物 (%.0f,%.0f) mm" % ((wp[0]) * 1e3, wp[2] * 1e3)) if "w" in s else ""))
wall = time.time() - t0w
if VIS is not None:
    VID.close(); P("影片 → %s(%d 幀)" % (VID.path, VID.n))

P("\n===== 判讀 G2 =====")
P("判準:下片位移 < 10mm、互穿 0、上片被完整掀開(夾持端 x 越過中線 %.0fmm)" % (XMID * 1e3))
rows = []
for s in SC:
    ts = np.array(s["ts"])
    grip = (ts >= t_lift0) & (ts < t_open0)
    i_arc1 = int(np.searchsorted(ts, t_arc1 - 1e-9)); i_end = len(ts) - 1
    lo_com = np.array(s["lo_com"]); lo_dmax = np.array(s["lo_dmax"]); pen = np.array(s["pen"]); spen = np.array(s["spen"])
    tip = np.array(s["tipx"])
    r = dict(k=s["k"], weight=s["weight"], slip_max=float(np.nanmax(np.array(s["slip"])[grip])) * 1e3,
             lo_com_max=float(lo_com.max()) * 1e3, lo_com_end=float(lo_com[-1]) * 1e3, lo_dmax_max=float(lo_dmax.max()) * 1e3,
             lo_zmax=float(np.max(s["lo_zmax"])) * 1e3, pen_max=int(pen.max()), pen_t=float(ts[np.argmax(pen)]), spen_max=int(spen.max()),
             inv=int(np.max(s["inv"])), lmax=float(np.max(s["lmax"])),
             tip_arc_end=[float(x) * 1e3 for x in tip[i_arc1]], tip_end=[float(x) * 1e3 for x in tip[i_end]],
             flip_arc_end=float(s["flipfrac"][i_arc1]), flip_end=float(s["flipfrac"][i_end]), nan=s.get("nan"))
    if "w" in s:
        W = np.array(s["wpos"]); r["w_disp_max"] = float(np.linalg.norm(W[:, :2] - W[0, :2], axis=1).max()) * 1e3
        r["w_z"] = [float(W[:, 2].min()) * 1e3, float(W[:, 2].max()) * 1e3]
    opened = r["tip_end"][1] < XMID * 1e3 and r["tip_arc_end"][1] < XMID * 1e3
    r["opened"] = bool(opened)
    r["ok"] = bool(r["lo_dmax_max"] < 10 and r["pen_max"] == 0 and opened and not s.get("nan"))
    rows.append(r)
    P("  s%d %s | 夾持滑動最大 %.2fmm | 下片 質心位移 最大 %.2f(結束 %.2f)最大點位移 %.2f mm 最高 z %.2f mm | 上下片互穿最多 %d(t=%.2f)自穿最多 %d | 反轉 %d 邊長比 %.3f | 上片夾持端 x:翻完 %.0f~%.0f / 結束 %.0f~%.0f mm;翻面比例 翻完 %.0f%% 結束 %.0f%%%s ⇒ 掀開 %s;%s"
      % (s["k"], "有重物" if s["weight"] else "無重物", r["slip_max"], r["lo_com_max"], r["lo_com_end"], r["lo_dmax_max"], r["lo_zmax"],
         r["pen_max"], r["pen_t"], r["spen_max"], r["inv"], r["lmax"], *r["tip_arc_end"], *r["tip_end"], 100 * r["flip_arc_end"],
         100 * r["flip_end"], (" | 重物水平位移最大 %.1fmm z %.1f~%.1f" % (r["w_disp_max"], *r["w_z"])) if "w" in s else "",
         "是" if opened else "否", "PASS" if r["ok"] else "FAIL"))
    VC.snap(os.path.join(HERE, "img", tag + "_s%d_end.png" % s["k"]), np.vstack([s["Pl"], s["Pu"]]), tag + " s%d end" % s["k"],
            groups=[(np.arange(len(s["Pl"])), "tab:gray", "lower"), (len(s["Pl"]) + np.arange(len(s["Pu"])), "tab:blue", "upper")],
            xlim=(-420, 80), zlim=(-10, 220))
json.dump(rows, open(os.path.join(HERE, "data", tag + ".json"), "w"), indent=1, default=float)
P("wall %.1fs / sim %.2fs | 顯存 %s" % (wall, T_END, VC.gpu_mem_mib()))
LOG.close()
sim.close()
