#!/usr/bin/env python3
"""probe_peel_surf.py — G2 surface 版:兩片 surface deformable 疊放,只夾上片,抬起後沿圓弧翻 180°(像翻書)。

    /isaac-sim/python.sh probe_peel_surf.py                    # 兩組(無重物 / 0.08kg 方塊壓上片遠端)同 stage 平行
    /isaac-sim/python.sh probe_peel_surf.py --only 0 --video   # 單組 + 錄影

幾何同 vol/grip/probe_peel.py:下片 200x200 x∈[-200,0](+x 邊齊桌緣);上片往 +x 錯開 25mm(x∈[-175,+25])。
差異(surface 必要):
  * 指面 t=0 就合在上片伸出段(G1 surface 實測:bend 4 的懸出段 0.8s 內垂成垂直,不先合就夾不到)。
  * 指面中心 x = 15.5mm(volume 14.5):格距 13.3mm 時上片頂點在 x=25 / 11.7,14.5 會讓 x=25 那排落在指面外 0.5mm,
    改 15.5 讓指面下 2x2 = 4 個頂點(與 G1 surface 相同),離下片邊仍 5.5mm。
  * 上片初始高度 = 下片 + 2 x restOffset + 0.2mm。
時間表:settle 0.8 → (close 1.2,已合)→ hold 0.4 → 抬 20mm(1s)→ 圓弧翻 180°(R = 0.9 x 材料長,4s,
       指面繞 y 轉 −θ)→ 停 1s → 張開(沿指面法線各退 20mm/0.3s)→ 看 1.5s。
重物 0.08kg 50mm 方塊,中心 x = −145mm,t<0.45s kinematic 放到上片上,之後 dynamic。
量測:上片翻面比例(三角形法向 z<0 的比例)、上片夾持端 x、下片位移(質心/最大點)、
      兩片互穿 = 上片邊穿下片面 + 下片邊穿上片面(Moller-Trumbore,work/wrap_sim.py self_pen 同法)、各片自穿。
"""
import os, sys, argparse, time, json
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--only", type=int, default=-1)
ap.add_argument("--video", action="store_true")
ap.add_argument("--gap_mm", type=float, default=2.0)
ap.add_argument("--ffric", type=float, default=2.0)
ap.add_argument("--fx_mm", type=float, default=15.5)
ap.add_argument("--kR", type=float, default=0.9)
ap.add_argument("--lift0", type=float, default=0.020)
ap.add_argument("--t_arc", type=float, default=4.0)
ap.add_argument("--table_fric", type=float, default=0.5)
ap.add_argument("--wmass", type=float, default=0.08)
ap.add_argument("--young", type=float, default=2e4)
ap.add_argument("--bend", type=float, default=4.0)
ap.add_argument("--thick", type=float, default=0.004)
ap.add_argument("--dens", type=float, default=100.0)
ap.add_argument("--fric", type=float, default=0.8)
ap.add_argument("--n", type=int, default=15)
ap.add_argument("--cont", type=float, default=0.005)
ap.add_argument("--rest", type=float, default=0.001)
ap.add_argument("--solver", type=int, default=64)
ap.add_argument("--dt", type=float, default=1 / 120.0)
ap.add_argument("--focal", type=float, default=3.0)
ap.add_argument("--cam", default="0.30,-0.80,0.45,-0.10,0.0,0.07")
ap.add_argument("--tag", default="")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ["logs", "img", "videos", "data"]:
    os.makedirs(os.path.join(HERE, d), exist_ok=True)
CFG = [0, 1] if a.only < 0 else [a.only]
tag = a.tag or ("g2s_" + ("sweep" if a.only < 0 else ("weight" if a.only else "noweight")))
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
from pxr import UsdGeom, UsdPhysics, PhysxSchema, Gf
from omni.physx.scripts import physicsUtils
import omni.usd
sys.path.insert(0, HERE); sys.path.insert(1, os.path.join(os.path.dirname(HERE), "grip"))
import gutil as GU
import volcommon as VC
import sutil as SU

P("=== G2 surface %s ===" % tag); P("args:", vars(a))
world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane(z_position=-0.4)
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

S = 0.200; OFS = 0.025
FS = np.array([0.020, 0.020, 0.008]); FH = FS / 2
FX = a.fx_mm / 1e3
SPC = 0.45
ZB = a.rest + 1e-4
ZU = ZB + 2 * a.rest + 0.0002
WS = 0.050
GAP = a.gap_mm / 1e3
SC = []
GU.static_box(st, "/World/table", [0.7, SPC * (len(CFG) - 1) + 0.32, 0.05], [-0.35, SPC * (len(CFG) - 1) / 2, -0.025],
              a.table_fric, color=(0.35, 0.25, 0.18))
kw = dict(young=a.young, bend=a.bend, thick=a.thick, dens=a.dens, fric=a.fric, cont=a.cont, rest=a.rest, solver=a.solver, selfcol=True)
for k, cf in enumerate(CFG):
    oy = SPC * k; pth = "/World/s%d" % k
    lo = SU.build_sheet(st, pth + "_lower", S, a.n, ZB, -S / 2, oy, color=(0.85, 0.85, 0.80), **kw)
    up = SU.build_sheet(st, pth + "_upper", S, a.n, ZU, -S / 2 + OFS, oy, color=(0.25, 0.55, 0.85), **kw)
    GU.finger(st, pth + "_fu", FS, [FX, oy, ZU + GAP / 2 + FH[2]], a.ffric, color=(0.9, 0.45, 0.1))
    GU.finger(st, pth + "_fl", FS, [FX, oy, ZU - GAP / 2 - FH[2]], a.ffric, color=(0.9, 0.45, 0.1))
    s = dict(k=k, weight=bool(cf), oy=oy, lower=pth + "_lower", upper=pth + "_upper", fu=pth + "_fu", fl=pth + "_fl", zc=ZU)
    if cf:
        wp = pth + "_w"
        WX = -S / 2 + OFS - S / 2 + 0.030
        cb = UsdGeom.Cube.Define(st, wp); cb.CreateSizeAttr(1.0)
        xf = UsdGeom.Xformable(cb); xf.AddTranslateOp().Set(Gf.Vec3d(WX, oy, ZU + 0.004 + WS / 2))
        xf.AddOrientOp().Set(Gf.Quatf(1, 0, 0, 0)); xf.AddScaleOp().Set(Gf.Vec3f(WS, WS, WS))
        UsdPhysics.CollisionAPI.Apply(cb.GetPrim()); UsdPhysics.RigidBodyAPI.Apply(cb.GetPrim()).CreateKinematicEnabledAttr(True)
        UsdPhysics.MassAPI.Apply(cb.GetPrim()).CreateMassAttr(float(a.wmass))
        physicsUtils.add_physics_material_to_prim(st, cb.GetPrim(), GU.rigid_mat(st, 0.5))
        pc = PhysxSchema.PhysxCollisionAPI.Apply(cb.GetPrim()); pc.CreateContactOffsetAttr(0.001); pc.CreateRestOffsetAttr(0.0)
        GU.bind_vis(st, cb.GetPrim(), (0.3, 0.3, 0.75), "weight")
        s["w"] = wp; s["wx0"] = np.array([WX, oy]); s["hinge"] = WX + WS / 2
    else:
        s["hinge"] = -S + OFS
    s["L"] = FX - s["hinge"]; s["R"] = a.kR * s["L"]
    SC.append(s)
F = lo["F"]; EDG = SU.tri_edges(F)
P("surface ok=%s/%s;每片 %d 點 %d 三角,格距 %.2fmm;下片 x∈[-200,0] z=%.2fmm;上片 x∈[%.0f,%.0f] z=%.2fmm;指面中心 x=%.1fmm(已合,gap %.1fmm 指摩擦 %.1f);R %s mm;重物 %.3fkg %.0fmm"
  % (lo["ok"], up["ok"], len(lo["V"]), len(F), S / a.n * 1e3, ZB * 1e3, (-S + OFS) * 1e3, OFS * 1e3, ZU * 1e3, FX * 1e3, a.gap_mm, a.ffric,
     [round(s["R"] * 1e3) for s in SC], a.wmass, WS * 1e3))

VIDEO = None
if a.video:
    c0 = SC[0]
    for p_ in (c0["fu"], c0["fl"]):
        UsdGeom.Imageable(st.GetPrimAtPath(p_)).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    GU.bind_vis(st, st.GetPrimAtPath(c0["lower"]), (0.85, 0.85, 0.80), "lowervis")
    GU.bind_vis(st, st.GetPrimAtPath(c0["upper"]), (0.25, 0.55, 0.85), "uppervis")
    VBU = GU.VisBox(st, "/World/vis_fu", FS, (0.9, 0.45, 0.1)); VBL = GU.VisBox(st, "/World/vis_fl", FS, (0.9, 0.45, 0.1))
    _c = [float(x) for x in a.cam.split(",")]
    EYE = [_c[0], c0["oy"] + _c[1], _c[2]]; TGT = [_c[3], c0["oy"] + _c[4], _c[5]]
    VIDEO = GU.Video(st, os.path.join(HERE, "videos", tag + ".mp4"), EYE, TGT, focal=a.focal,
                     label="G2 SURFACE %s | gap %.0fmm mu %.1f arc R%.0fmm %.0fs | E2e4 bend4 thick4 cont5 rest1 n%d solver%d"
                     % ("weight %.2fkg" % a.wmass if c0["weight"] else "no weight", a.gap_mm, a.ffric, c0["R"] * 1e3, a.t_arc, a.n, a.solver))
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
    s["ml"] = SU.SMesh(st, s["lower"]); s["mu"] = SU.SMesh(st, s["upper"])
    s["fl0"] = s["ml"].pts().copy(); s["fu0"] = s["mu"].pts().copy()
    if "w" in s:
        s["wx"] = SingleXFormPrim(s["w"], name="w%d" % s["k"])
L0 = np.linalg.norm(SC[0]["fl0"][EDG[:, 0]] - SC[0]["fl0"][EDG[:, 1]], axis=1)

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
    oy = s["oy"]; zc = s["zc"]
    du = GAP / 2 + FH[2]; dl = -GAP / 2 - FH[2]
    op = 0.020 * ss((t - t_open0) / T_OPEN)
    du += op; dl -= op
    g0 = np.array([FX, oy, zc + a.lift0 * ss((t - t_lift0) / T_L0)])
    th = np.pi * ss((t - t_arc0) / a.t_arc)
    C = np.array([FX - s["R"], oy, zc + a.lift0])
    g = C + s["R"] * np.array([np.cos(th), 0, np.sin(th)]) if t >= t_arc0 else g0
    R = VC.rot_y(-th); q = VC.quat_y(-th)
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

ME = int(round(0.05 / a.dt)); NSTEP = int(round(T_END / a.dt)); SPF = max(1, int(round(1.0 / (30 * a.dt))))
for s in SC:
    s.update(ts=[], ph=[], slip=[], lo_com=[], lo_dmax=[], lo_zmax=[], pen_ul=[], pen_lu=[], spen=[], lmax=[], tipx=[], flipfrac=[], wpos=[], G=None)
P("時間表:settle %.1f close→%.2f hold→%.2f 抬→%.2f 弧→%.2f 停→%.2f 開→%.2f 觀察→%.2f" % (T_SET, t_closed, t_lift0, t_arc0, t_arc1, t_open0, t_open1, T_END))
XMID = -S / 2
EDGE_U = np.where(np.abs(SC[0]["fu0"][:, 0] - SC[0]["fu0"][:, 0].max()) < 1e-6)[0]
t0w = time.time()
for step in range(1, NSTEP + 1):
    t = step * a.dt
    for s in SC:
        if "w" in s and not s.get("wdyn"):
            zt = ZU + 0.004 + WS / 2 - 0.0027 * ss(t / 0.4)
            s["wx"].set_world_pose(position=np.array([s["wx0"][0], s["oy"], zt]), orientation=np.array([1., 0, 0, 0]))
            if t >= 0.45:
                st.GetPrimAtPath(s["w"]).GetAttribute("physics:kinematicEnabled").Set(False); s["wdyn"] = True
                P("  [s%d] t=%.2f 重物轉 dynamic(底面 %.2fmm,上片 z %.2fmm)" % (s["k"], t, (zt - WS / 2) * 1e3, ZU * 1e3))
    drive(t)
    rend = VIDEO is not None and step % SPF == 0
    world.step(render=rend)
    if rend:
        s0 = SC[0]; cu, cl, R, q, th = fpose(s0, t)
        VBU.set(cu, q); VBL.set(cl, q)
        VIDEO.frame(t, "%s  theta %.0f deg  %s  SURFACE" % (phase(t), np.degrees(th), "weight" if s0["weight"] else "no weight"))
    if step % ME:
        continue
    for s in SC:
        Pl = s["ml"].pts(); Pu = s["mu"].pts()
        if not (np.isfinite(Pl).all() and np.isfinite(Pu).all()):
            if not s.get("nan"):
                P("★ NaN s%d t=%.2f" % (s["k"], t))
            s["nan"] = t; continue
        cu, cl, R, q, th = fpose(s, t); gc = (cu + cl) / 2
        if s["G"] is None and t >= t_lift0 - 1e-9:
            L = loc(Pu, gc, R)
            G = np.where((np.abs(L[:, 0]) < FH[0]) & (np.abs(L[:, 1]) < FH[1]) & (np.abs(L[:, 2]) < GAP / 2 + 0.002))[0]
            s["G"] = G; s["rel0"] = loc(Pu[G], gc, R)
            P("  [s%d] 夾住上片頂點 %d 個 %s;局部 z %s mm" % (s["k"], len(G), G.tolist(), (s["rel0"][:, 2] * 1e3).round(2).tolist()))
        sl = float(np.median(np.linalg.norm(loc(Pu[s["G"]], gc, R) - s["rel0"], axis=1))) if s["G"] is not None and len(s["G"]) else np.nan
        dl = Pl - s["fl0"]
        p_ul = SU.edge_tri_cross(Pu, EDG, Pl, F); p_lu = SU.edge_tri_cross(Pl, EDG, Pu, F)
        sp = SU.self_cross(Pu, EDG, F) + SU.self_cross(Pl, EDG, F)
        lr = max((np.linalg.norm(Pu[EDG[:, 0]] - Pu[EDG[:, 1]], axis=1) / L0).max(), (np.linalg.norm(Pl[EDG[:, 0]] - Pl[EDG[:, 1]], axis=1) / L0).max())
        ff = float((SU.tri_normals(Pu, F)[:, 2] < 0).mean())
        s["ts"].append(t); s["ph"].append(phase(t)); s["slip"].append(sl)
        s["lo_com"].append(np.linalg.norm(dl.mean(0))); s["lo_dmax"].append(np.linalg.norm(dl, axis=1).max()); s["lo_zmax"].append(Pl[:, 2].max())
        s["pen_ul"].append(p_ul); s["pen_lu"].append(p_lu); s["spen"].append(sp); s["lmax"].append(lr)
        s["tipx"].append((Pu[EDGE_U, 0].min(), Pu[EDGE_U, 0].max())); s["flipfrac"].append(ff)
        if "w" in s:
            wp = np.array(s["wx"].get_world_pose()[0]); s["wpos"].append(wp)
        s["Pu"] = Pu; s["Pl"] = Pl
        if step % (ME * 5) == 0 or a.only >= 0 and step % (ME * 2) == 0:
            P("  [s%d] t=%5.2f %-7s θ=%5.1f° 夾心 (%.0f,%.0f) | 滑動 %.2fmm | 下片 質心位移 %.2f 最大點 %.2f 最高 z %.2f mm | 互穿 上邊穿下面 %d 下邊穿上面 %d 自穿 %d | 邊長比 %.3f | 上片夾持端 x %.0f~%.0f 翻面 %.0f%%%s"
              % (s["k"], t, phase(t), np.degrees(th), gc[0] * 1e3, gc[2] * 1e3, sl * 1e3, s["lo_com"][-1] * 1e3, s["lo_dmax"][-1] * 1e3,
                 s["lo_zmax"][-1] * 1e3, p_ul, p_lu, sp, lr, s["tipx"][-1][0] * 1e3, s["tipx"][-1][1] * 1e3, 100 * ff,
                 (" | 重物 (%.0f,%.0f) mm" % (wp[0] * 1e3, wp[2] * 1e3)) if "w" in s else ""))
wall = time.time() - t0w
if VIDEO is not None:
    VIDEO.close(); P("影片 → %s(%d 幀)" % (VIDEO.path, VIDEO.n))

P("\n===== 判讀 G2 surface =====")
P("判準:下片最大點位移 < 10mm、互穿 0、上片被完整掀開(夾持端 x 越過中線 %.0fmm)" % (XMID * 1e3))
rows = []
for s in SC:
    ts = np.array(s["ts"]); grip = (ts >= t_lift0) & (ts < t_open0)
    i_arc1 = int(np.searchsorted(ts, t_arc1 - 1e-9)); i_end = len(ts) - 1
    lo_com = np.array(s["lo_com"]); lo_dmax = np.array(s["lo_dmax"]); pen = np.array(s["pen_ul"]) + np.array(s["pen_lu"]); spen = np.array(s["spen"])
    tip = np.array(s["tipx"])
    r = dict(k=s["k"], weight=s["weight"], slip_max=float(np.nanmax(np.array(s["slip"])[grip])) * 1e3,
             lo_com_max=float(lo_com.max()) * 1e3, lo_com_end=float(lo_com[-1]) * 1e3, lo_dmax_max=float(lo_dmax.max()) * 1e3,
             lo_zmax=float(np.max(s["lo_zmax"])) * 1e3, pen_max=int(pen.max()), pen_t=float(ts[np.argmax(pen)]),
             pen_ul_max=int(np.max(s["pen_ul"])), pen_lu_max=int(np.max(s["pen_lu"])), pen_frames=int((pen > 0).sum()), n_frames=len(pen),
             spen_max=int(spen.max()), lmax=float(np.max(s["lmax"])),
             tip_arc_end=[float(x) * 1e3 for x in tip[i_arc1]], tip_end=[float(x) * 1e3 for x in tip[i_end]],
             flip_arc_end=float(s["flipfrac"][i_arc1]), flip_end=float(s["flipfrac"][i_end]), nan=s.get("nan"))
    if "w" in s:
        W = np.array(s["wpos"]); r["w_disp_max"] = float(np.linalg.norm(W[:, :2] - W[0, :2], axis=1).max()) * 1e3
        r["w_z"] = [float(W[:, 2].min()) * 1e3, float(W[:, 2].max()) * 1e3]
    opened = r["tip_end"][1] < XMID * 1e3 and r["tip_arc_end"][1] < XMID * 1e3
    r["opened"] = bool(opened)
    r["ok"] = bool(r["lo_dmax_max"] < 10 and r["pen_max"] == 0 and opened and not s.get("nan"))
    rows.append(r)
    P("  s%d %s | 夾持滑動最大 %.2fmm | 下片 質心位移 最大 %.2f(結束 %.2f)最大點位移 %.2f mm 最高 z %.2f mm | 兩片互穿最多 %d(上邊穿下面 %d / 下邊穿上面 %d,t=%.2f,%d/%d 格有)自穿最多 %d | 邊長比 %.3f | 上片夾持端 x:翻完 %.0f~%.0f / 結束 %.0f~%.0f mm;翻面比例 翻完 %.0f%% 結束 %.0f%%%s ⇒ 掀開 %s;%s"
      % (s["k"], "有重物" if s["weight"] else "無重物", r["slip_max"], r["lo_com_max"], r["lo_com_end"], r["lo_dmax_max"], r["lo_zmax"],
         r["pen_max"], r["pen_ul_max"], r["pen_lu_max"], r["pen_t"], r["pen_frames"], r["n_frames"], r["spen_max"], r["lmax"],
         *r["tip_arc_end"], *r["tip_end"], 100 * r["flip_arc_end"], 100 * r["flip_end"],
         (" | 重物水平位移最大 %.1fmm z %.1f~%.1f" % (r["w_disp_max"], *r["w_z"])) if "w" in s else "",
         "是" if opened else "否", "PASS" if r["ok"] else "FAIL"))
    VC.snap(os.path.join(HERE, "img", tag + "_s%d_end.png" % s["k"]), np.vstack([s["Pl"], s["Pu"]]), tag + " s%d end" % s["k"],
            groups=[(np.arange(len(s["Pl"])), "tab:gray", "lower"), (len(s["Pl"]) + np.arange(len(s["Pu"])), "tab:blue", "upper")],
            xlim=(-420, 80), zlim=(-30, 220))
json.dump(rows, open(os.path.join(HERE, "data", tag + ".json"), "w"), indent=1, default=float)
P("wall %.1fs / sim %.2fs | 顯存 %s" % (wall, T_END, VC.gpu_mem_mib()))
LOG.close()
sim.close()
