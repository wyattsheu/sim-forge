#!/usr/bin/env python3
"""probe_g3.py — G3 的那一次模擬:把開蓋後的包裹狀態(s2/wrap.npz snap_end)載回來,在 grasp_points.py 排名前兩個
抓取點各放一組 kinematic 平行指面(兩份場景同一個 stage,x 錯開 1m),實際試「下指從布邊外下降 → 沿 −u 插到布下 →
閉合到指面間距 4mm → 抬 60mm → 往 −y(yn 掀開的方向)拉 120mm」。

    /isaac-sim/python.sh probe_g3.py [--ranks 1,2] [--video 0]

場景(箱局部座標):箱底(靜態,頂面 z=3mm)、四面牆(靜態;x 牆內面 ±132 頂 120,y 牆內面 ±112 頂 126.5;開著的蓋在牆外,不建)、
杯子(靜態網格 convexDecomposition,位置 = snapmug_end)、布 = volume deformable(points = snap_end,rest = 平板,速度 0)。
★ 預設 restShapePoints = 開蓋後形狀(--rest snap):rest = 平板時,載入的折疊狀態第 1 步就彈開(實測 max 位移 71mm、自穿 114),
  因為 wrap_vol 裡把它壓住的接觸(杯子凸分解、蓋子、層間)無法 1:1 重建。所以這裡的布「沒有回彈力」,yn 片比真的更服貼。
材料同定案(E 2e3、nu .45、T 4、0.1kg/m²、0.8、manual 35x35x1、cont 2 / rest 0.5、自碰撞、solver 128、dt 1/240)。
指面 20(t)x20(u)x8(n)mm,摩擦 2.0,姿態 = grasp_points.py 的局部框(t 邊切線、u 沿布面外法線、n 布面法線)。
"""
import os, sys, argparse, time, json
import numpy as np

ap = argparse.ArgumentParser()
HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
ap.add_argument("--npz", default=os.path.join(VOL, "soft", "s2", "wrap.npz"))
ap.add_argument("--gp", default=os.path.join(HERE, "data", "grasp_points.json"))
ap.add_argument("--ranks", default="1,2")
ap.add_argument("--video", type=int, default=0, help="錄第幾個場景(0 起算);-1 不錄")
ap.add_argument("--gap_mm", type=float, default=4.0)
ap.add_argument("--ffric", type=float, default=2.0)
ap.add_argument("--young", type=float, default=2e3)
ap.add_argument("--solver", type=int, default=128)
ap.add_argument("--dt", type=float, default=1 / 240.0)
ap.add_argument("--tag", default="g3_sim")
ap.add_argument("--max_depen", type=float, default=-1.0, help=">0:physxDeformableBody:maxDepenetrationVelocity m/s")
ap.add_argument("--ldamp", type=float, default=0.0)
ap.add_argument("--rest", choices=["teleport", "snap", "flat"], default="snap",
                help="teleport(預設):平板建在 0.8m 高、cook 完再用 tensor API 把節點位置設成 snap_end(rest = 平板,自碰撞過濾照平板算);"
                     "snap:restShapePoints = 開蓋後形狀;flat:USD points = snap_end、rest = 平板")
a = ap.parse_args()
LOG = open(os.path.join(HERE, "logs", a.tag + ".log"), "w")
def P(*s):
    m = " ".join(str(x) for x in s); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()

os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from pxr import UsdGeom, UsdPhysics, PhysxSchema, Sdf, Vt, Gf
import omni.usd, trimesh
sys.path.insert(0, HERE)
import gutil as GU
import volcommon as VC
import vol_pen as VP

P("=== G3 sim %s ===" % a.tag); P("args:", vars(a))
OFF = np.array([0.0, 0.200, 0.097])
IX, IY, ZF = 0.132, 0.112, 0.003
T = 0.004; NX = 35; N1 = (NX + 1) ** 2
CX, CY = 0.08463, 0.07150
d = np.load(a.npz)
P0 = d["snap_end"] - OFF; FLAT = d["flat"]; MUG = d["snapmug_end"] - OFF
GP = json.load(open(a.gp)); byv = {r["v"]: r for r in GP["rows"]}
RANKS = [int(x) for x in a.ranks.split(",")]
CANDS = [byv[GP["rank"][k - 1]] for k in RANKS]

world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane(z_position=-0.05)
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
for at, v in [("CreateGpuCollisionStackSizeAttr", 128 * 1024 * 1024), ("CreateGpuFoundLostAggregatePairsCapacityAttr", 8192)]:
    try: getattr(pxs, at)(v)
    except Exception: pass
mm = trimesh.load(os.path.join(VOL, "mug.stl")); MF = np.asarray(mm.faces)
SPC = 1.0
FS = np.array([0.020, 0.020, 0.008]); FH = FS / 2
GAP = a.gap_mm / 1e3
SC = []

def rot2quat(R):
    from scipy.spatial.transform import Rotation
    x, y, z, w = Rotation.from_matrix(R).as_quat()
    return np.array([w, x, y, z])

for k, c in enumerate(CANDS):
    ox = np.array([SPC * k, 0, 0]); pth = "/World/s%d" % k
    GU.static_box(st, pth + "_floor", [0.30, 0.26, 0.02], ox + [0, 0, ZF - 0.01], 0.5, color=(0.62, 0.46, 0.29))
    for nm, sz, ce in [("wxp", [0.003, 0.23, 0.12], [IX + 0.0015, 0, 0.06]), ("wxn", [0.003, 0.23, 0.12], [-IX - 0.0015, 0, 0.06]),
                       ("wyp", [0.27, 0.003, 0.1265], [0, IY + 0.0015, 0.06325]), ("wyn", [0.27, 0.003, 0.1265], [0, -IY - 0.0015, 0.06325])]:
        GU.static_box(st, pth + "_" + nm, sz, ox + ce, 0.5, color=(0.62, 0.46, 0.29))
    g = UsdGeom.Mesh.Define(st, pth + "_mug")
    g.CreatePointsAttr([Gf.Vec3f(*map(float, q)) for q in MUG + ox])
    g.CreateFaceVertexIndicesAttr([int(i) for f in MF for i in f]); g.CreateFaceVertexCountsAttr([3] * len(MF))
    UsdPhysics.CollisionAPI.Apply(g.GetPrim()); UsdPhysics.MeshCollisionAPI.Apply(g.GetPrim()).CreateApproximationAttr("convexDecomposition")
    gc = PhysxSchema.PhysxCollisionAPI.Apply(g.GetPrim()); gc.CreateContactOffsetAttr(0.004); gc.CreateRestOffsetAttr(0.001)
    GU.bind_vis(st, g.GetPrim(), (0.55, 0.62, 0.75), "mug")
    info = VC.build_plate(st, pth + "_sheet", 0.5, T, 0.8 if a.rest == "teleport" else 0.001, "manual", cx=ox[0], nxy=NX, nz=1, youngs=a.young, poisson=0.45, areal=0.1,
                          fric=0.8, cont=0.002, rest=0.0005, solver=a.solver, self_coll=True, self_filter=0.001,
                          P=(P if k == 0 else (lambda *s: None)))
    sp = st.GetPrimAtPath(pth + "_sheet")
    if a.max_depen > 0:
        VC.sa(sp, "physxDeformableBody:maxDepenetrationVelocity", float(a.max_depen), Sdf.ValueTypeNames.Float)
    if a.ldamp > 0:
        VC.sa(sp, "physxDeformableBody:linearDamping", float(a.ldamp), Sdf.ValueTypeNames.Float)
    if a.rest != "teleport":
        UsdGeom.TetMesh(sp).GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in P0 + ox]))
        REST = P0 if a.rest == "snap" else FLAT
        sp.GetAttribute("omniphysics:restShapePoints").Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in REST]))
    p = np.array(c["p"]) / 1e3
    # 局部框(同 grasp_points.py)
    v = c["v"]; i_, j_ = v % (NX + 1), v // (NX + 1)
    vin = v + (NX + 1) if j_ == 0 else (v + 1 if i_ == 0 else v - 1)
    MID = (P0[:N1] + P0[N1:]) / 2
    u = MID[v] - MID[vin]; u /= np.linalg.norm(u)
    tt = np.cross([0, 0, 1.0], u); tt /= np.linalg.norm(tt)
    n = np.cross(tt, u)
    if n[2] < 0:
        tt = -tt; n = np.cross(tt, u)
    R = np.stack([tt, u, n], 1); q = rot2quat(R)
    half = c["thick"] / 2e3
    s = dict(k=k, rank=RANKS[k], c=c, ox=ox, p=p + ox, R=R, q=q, n=n, u=u, half=half, sheet=pth + "_sheet",
             fu=pth + "_fu", fl=pth + "_fl")
    GU.finger(st, s["fu"], FS, s["p"] + [0, 0, 0.3], a.ffric, color=(0.9, 0.45, 0.1))
    GU.finger(st, s["fl"], FS, s["p"] + [0, 0, 0.35], a.ffric, color=(0.9, 0.45, 0.1))
    SC.append(s)
    P("場景 %d:排名 #%d 頂點 %d(%s,flat %s)夾點 %s mm 坡度 %.1f° u=%s n=%s 布厚 %.1fmm 下方空隙(分析)%.1fmm"
      % (k, RANKS[k], v, c["kind"], c["flat"], np.round(np.array(c["p"]), 1), c["slope"], u.round(2), n.round(2), c["thick"], c["gap"]))

VID = None
if a.video >= 0:
    s0 = SC[a.video]
    vis = GU.vis_mesh(st, "/World/vis_sheet", P0 + s0["ox"], NX, NX, (0.25, 0.55, 0.85))
    UsdGeom.Imageable(st.GetPrimAtPath(s0["sheet"])).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    for p_ in (s0["fu"], s0["fl"]):
        UsdGeom.Imageable(st.GetPrimAtPath(p_)).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    VBU = GU.VisBox(st, "/World/vis_fu", FS, (0.9, 0.45, 0.1)); VBL = GU.VisBox(st, "/World/vis_fl", FS, (0.9, 0.45, 0.1))
    EYE = list(s0["ox"] + [0.05, -0.55, 0.50]); TGT = list(s0["p"] * [1, 1, 0] + [0, 0, 0.09])
    VID = GU.Video(st, os.path.join(HERE, "videos", a.tag + "_rank%d.mp4" % s0["rank"]), EYE, TGT, focal=2.6,
                   label="G3 opened package, grasp rank #%d (v%d) | kinematic fingers gap %.0fmm mu %.1f | walls+floor static, mug static"
                   % (s0["rank"], s0["c"]["v"], a.gap_mm, a.ffric))
world.reset()
if VID is not None:
    VID.init(); VID.look(EYE, TGT)
for _ in range(2):
    sim.update()
FPATHS = [s["fu"] for s in SC] + [s["fl"] for s in SC]
FV = world.physics_sim_view.create_rigid_body_view(FPATHS)
_pi = {p_: i for i, p_ in enumerate(FPATHS)}
ORD = np.array([_pi[p_] for p_ in FV.prim_paths]); FIDX = np.arange(FV.count, dtype=np.int32)
TETS = VC.Mesh(st, SC[0]["sheet"]).tets()
V0 = VP.tet_vol(P0 if a.rest == "snap" else FLAT, TETS)
P("rest 模式 %s" % a.rest)
EDG = GU.edges(TETS); L0 = np.linalg.norm(FLAT[EDG[:, 0]] - FLAT[EDG[:, 1]], axis=1)
F2 = FLAT[:N1, :2]
def side(fx, fy):
    sx = max(0.0, abs(fx) - CX); sy = max(0.0, abs(fy) - CY)
    return ("yp" if fy > 0 else "yn") if sy >= sx else ("xp" if fx > 0 else "xn")
SIDE = np.array([side(*f) if (abs(f[0]) > CX or abs(f[1]) > CY) else "base" for f in F2])
SIDE2 = np.concatenate([SIDE, SIDE])
if a.rest == "teleport":
    import omni.physics.tensors as tensors, warp as wp
    world.step(render=False)
    _sv = tensors.create_simulation_view("warp"); _sv.set_subspace_roots("/")
    DV = _sv.create_volume_deformable_body_view("/World/s*_sheet")
    P("  deformable view count %d nodes %d" % (DV.count, DV.max_simulation_nodes_per_body))
    _pp = DV.get_simulation_nodal_positions().numpy().reshape(DV.count, DV.max_simulation_nodes_per_body, 3)
    _dp = {p_: i for i, p_ in enumerate(DV.prim_paths)}
    D = np.zeros_like(_pp, dtype=np.float32)
    for s in SC:
        i = _dp[s["sheet"]]
        chk = np.abs(_pp[i] - (FLAT + [s["ox"][0], 0, 0.8 - 0.001])).max()   # 已走 1 步(重力)
        P("  [s%d] tensor view:%d 個節點;與平板建板位置的差 max %.3fmm(順序檢查)" % (s["k"], DV.max_simulation_nodes_per_body, chk * 1e3))
        D[i] = P0 + s["ox"]
    _ix = wp.array(np.arange(DV.count, dtype=np.int32), dtype=wp.int32, device="cuda:0")
    DV.set_simulation_nodal_positions(wp.array(D, dtype=wp.float32, device="cuda:0"), _ix)
    DV.set_simulation_nodal_velocities(wp.array(np.zeros_like(D), dtype=wp.float32, device="cuda:0"), _ix)
    world.step(render=False)
for s in SC:
    s["m"] = VC.Mesh(st, s["sheet"])
    P0s = s["m"].pts()
    P("  [s%d] reset 後布點與 snap_end 的差 max %.2fmm;自穿 %d;反轉 %d" % (s["k"], np.abs(P0s - (P0 + s["ox"])).max() * 1e3,
      VP.self_pen_count(P0s, TETS, FLAT)[0], VC.inverted(P0s, TETS, V0)[0]))

# 時間表
T_SET, T_DN, T_IN, T_CL, T_HO, T_UP, T_PULL, T_STAY = 1.0, 1.0, 1.0, 0.8, 0.3, 2.0, 2.0, 1.0
t1 = T_SET; t2 = t1 + T_DN; t3 = t2 + T_IN; t4 = t3 + T_CL; t5 = t4 + T_HO; t6 = t5 + T_UP; t7 = t6 + T_PULL; T_END = t7 + T_STAY
ss = lambda x: (lambda v: v * v * (3 - 2 * v))(min(max(x, 0.), 1.))
def phase(t):
    for nm, tt_ in [("settle", t1), ("descend", t2), ("insert", t3), ("close", t4), ("hold", t5), ("lift", t6), ("pull -y", t7)]:
        if t < tt_:
            return nm
    return "stay"
def fpose(s, t):
    p, R, n, u, h = s["p"], s["R"], s["n"], s["u"], s["half"]
    cu_f = p + R @ [0, -0.005, GAP / 2 + FH[2]]; cl_f = p + R @ [0, -0.005, -GAP / 2 - FH[2]]
    cu_pre = p + R @ [0, -0.005, h + 0.0005 + FH[2] + 0.012]
    cl_pre = p + R @ [0, 0.017, -h - 0.0005 - FH[2] - 0.002]
    cl_hi = cl_pre + [0, 0, 0.10]; cu_hi = cu_pre + [0, 0, 0.10]
    if t < t1:
        cu, cl = cu_hi, cl_hi
    elif t < t2:
        w = ss((t - t1) / T_DN); cu = cu_hi + (cu_pre - cu_hi) * w; cl = cl_hi + (cl_pre - cl_hi) * w
    elif t < t3:
        w = ss((t - t2) / T_IN); cu = cu_pre; cl = cl_pre + (p + R @ [0, -0.005, -h - 0.0005 - FH[2] - 0.002] - cl_pre) * w
    else:
        cl0 = p + R @ [0, -0.005, -h - 0.0005 - FH[2] - 0.002]
        w = ss((t - t3) / T_CL); cu = cu_pre + (cu_f - cu_pre) * w; cl = cl0 + (cl_f - cl0) * w
    dz = 0.06 * ss((t - t5) / T_UP); dy = -0.12 * ss((t - t6) / T_PULL)
    sh = np.array([0, dy, dz])
    return cu + sh, cl + sh
def drive(t):
    D = np.zeros((len(FPATHS), 7), np.float32); n_ = len(SC)
    for i, s in enumerate(SC):
        cu, cl = fpose(s, t)
        for j, c_ in ((i, cu), (n_ + i, cl)):
            D[j, :3] = c_; D[j, 3:6] = s["q"][1:]; D[j, 6] = s["q"][0]
    FV.set_kinematic_targets(D[ORD], FIDX)

ME = int(round(0.05 / a.dt)); NSTEP = int(round(T_END / a.dt)); SPF = int(round(1.0 / (30 * a.dt)))
for s in SC:
    s.update(ts=[], log=[], G=None)
P("時間表:settle→%.1f 下降→%.1f 下指插入→%.1f 閉合→%.1f hold→%.1f 抬 60mm→%.1f 往 −y 拉 120mm→%.1f 停→%.1f" % (t1, t2, t3, t4, t5, t6, t7, T_END))
t0w = time.time()
for step in range(1, NSTEP + 1):
    t = step * a.dt
    for s in SC:
        if not s.get("refit") and t >= t1 - 1e-9:      # settle 完:用布邊「現在」的位置重定夾點與局部框(等同有視覺回授)
            Pp = s["m"].pts(); v = s["c"]["v"]; i_, j_ = v % (NX + 1), v // (NX + 1)
            vin = v + (NX + 1) if j_ == 0 else (v + 1 if i_ == 0 else v - 1)
            M_ = (Pp[:N1] + Pp[N1:]) / 2
            u = M_[v] - M_[vin]; u /= np.linalg.norm(u)
            tt = np.cross([0, 0, 1.0], u); tt /= np.linalg.norm(tt); nn = np.cross(tt, u)
            if nn[2] < 0:
                tt = -tt; nn = np.cross(tt, u)
            R = np.stack([tt, u, nn], 1)
            P("  [s%d] t=%.2f settle 後重定夾點:%s → %s mm(移 %.1fmm);坡度 %.1f° → %.1f°"
              % (s["k"], t, np.round((s["p"] - s["ox"]) * 1e3, 1), np.round((M_[v] - s["ox"]) * 1e3, 1),
                 np.linalg.norm(M_[v] - s["p"]) * 1e3, s["c"]["slope"], np.degrees(np.arcsin(np.clip(u[2], -1, 1)))))
            s.update(p=M_[v], R=R, q=rot2quat(R), n=nn, u=u, refit=True)
    drive(t)
    rend = VID is not None and step % SPF == 0
    world.step(render=rend)
    if rend:
        s0 = SC[a.video]; Pp = s0["m"].pts()
        vis.Set(Vt.Vec3fArray.FromNumpy(Pp.astype(np.float32)))
        cu, cl = fpose(s0, t); VBU.set(cu, s0["q"]); VBL.set(cl, s0["q"])
        VID.frame(t, phase(t))
    if step % ME:
        continue
    for s in SC:
        Pp = s["m"].pts()
        if not np.isfinite(Pp).all():
            P("★ NaN s%d t=%.2f" % (s["k"], t)); s["nan"] = t; continue
        cu, cl = fpose(s, t); gc = (cu + cl) / 2; R = s["R"]
        Lu = (Pp - cu) @ R; Ll = (Pp - cl) @ R
        inU = (np.abs(Lu) < FH).all(1); inL = (np.abs(Ll) < FH).all(1)
        depth = max(((FH - np.abs(Lu[inU])).min(1).max() if inU.any() else 0.0), ((FH - np.abs(Ll[inL])).min(1).max() if inL.any() else 0.0))
        if s["G"] is None and t >= t5 - 1e-9:
            Lg = (Pp - gc) @ R
            G = np.where((np.abs(Lg[:, 0]) < FH[0]) & (np.abs(Lg[:, 1]) < FH[1]) & (np.abs(Lg[:, 2]) < GAP / 2 + 0.003))[0]
            s["G"] = G; s["rel0"] = Lg[G]
            P("  [s%d] t=%.2f 閉合後夾住頂點 %d(歸屬 %s)" % (s["k"], t, len(G), dict(zip(*np.unique(SIDE2[G], return_counts=True)))))
        sl = float(np.median(np.linalg.norm((Pp[s["G"]] - gc) @ R - s["rel0"], axis=1))) if s["G"] is not None and len(s["G"]) else np.nan
        dP = np.linalg.norm(Pp - (P0 + s["ox"]), axis=1)
        yn = SIDE2 == "yn"
        r = dict(t=t, ph=phase(t), slip=sl, pen_n=int(inU.sum() + inL.sum()), pen_d=float(depth),
                 yn_med=float(np.median(dP[yn])), yn_f20=float((dP[yn] > 0.02).mean()), oth_max=float(dP[~yn].max()),
                 oth_n10=int((dP[~yn] > 0.010).sum()),
                 spen=VP.self_pen_count(Pp, TETS, FLAT)[0], inv=VC.inverted(Pp, TETS, V0)[0],
                 lr=float((np.linalg.norm(Pp[EDG[:, 0]] - Pp[EDG[:, 1]], axis=1) / L0).max()))
        vv = s["c"]["v"]; mv = (Pp[vv] + Pp[vv + N1]) / 2
        r["v_loc"] = ((mv - gc) @ R).tolist()
        s["log"].append(r); s["Plast"] = Pp
        if step % (ME * 4) == 0:
            P("  [s%d] t=%5.2f %-8s 夾持滑動 %s | 指面內布頂點 %d 最深 %.2fmm | yn 片位移中位 %.1fmm、>20mm 比例 %.0f%% | 其他片 最大位移 %.1fmm、>10mm 頂點 %d | 自穿 %d 反轉 %d 邊長比 %.3f | 夾點頂點在指框 (t,u,n) %s mm"
              % (s["k"], t, r["ph"], ("%.2fmm" % (sl * 1e3)) if np.isfinite(sl) else "-", r["pen_n"], r["pen_d"] * 1e3, r["yn_med"] * 1e3,
                 100 * r["yn_f20"], r["oth_max"] * 1e3, r["oth_n10"], r["spen"], r["inv"], r["lr"], np.round(np.array(r["v_loc"]) * 1e3, 1)))
wall = time.time() - t0w
if VID is not None:
    VID.close(); P("影片 → %s(%d 幀)" % (VID.path, VID.n))
P("\n===== 判讀 G3 sim =====")
out = []
for s in SC:
    L = s["log"]; ts = np.array([r["t"] for r in L])
    def mx(key, a_, b_):
        m = (ts >= a_) & (ts < b_)
        return max(r[key] for r, mm_ in zip(L, m) if mm_) if m.any() else np.nan
    ins = dict(pen_n=mx("pen_n", t2, t3), pen_d=mx("pen_d", t2, t3) * 1e3, oth=mx("oth_max", t1, t3) * 1e3)
    grip = (ts >= t5)
    slip = np.nanmax([r["slip"] for r, g in zip(L, grip) if g]) * 1e3
    e = L[-1]
    res = dict(rank=s["rank"], v=s["c"]["v"], insert=ins, slip_max=slip, pen_grip=mx("pen_d", t5, T_END) * 1e3,
               yn_med_end=e["yn_med"] * 1e3, yn_f20_end=e["yn_f20"], oth_max_end=e["oth_max"] * 1e3, oth_n10_end=e["oth_n10"],
               spen_max=max(r["spen"] for r in L), inv_max=max(r["inv"] for r in L), lr_max=max(r["lr"] for r in L), nG=len(s["G"]) if s["G"] is not None else 0)
    out.append(res)
    P("  排名 #%d v%d:下降+插入期間 指面內布頂點最多 %d 最深 %.2fmm、其他片被推最大 %.1fmm | 夾住 %d 點,抬+拉 滑動最大 %.2fmm,夾持時穿指最深 %.2fmm | 結束:yn 片位移中位 %.1fmm、>20mm 比例 %.0f%%;其他片 最大位移 %.1fmm、>10mm 頂點 %d | 全程 自穿最多 %d 反轉 %d 邊長比 %.3f"
      % (res["rank"], res["v"], ins["pen_n"], ins["pen_d"], ins["oth"], res["nG"], slip, res["pen_grip"], res["yn_med_end"], 100 * res["yn_f20_end"],
         res["oth_max_end"], res["oth_n10_end"], res["spen_max"], res["inv_max"], res["lr_max"]))
json.dump(out, open(os.path.join(HERE, "data", a.tag + ".json"), "w"), indent=1, default=float)
P("wall %.1fs / sim %.2fs | 顯存 %s" % (wall, T_END, VC.gpu_mem_mib()))
LOG.close()
sim.close()
