#!/usr/bin/env python3
"""peel_with_cloth.py — dry_with_cloth(v2 (b) 段回放)+ 合指完成時綁定 yn 片頂點、弧線後停 hold 秒再釋放。
    /isaac-sim/python.sh peel_with_cloth.py --young 2e4 [--lift_mm 10] [--pad 16] [--arc_out_mm 0 --arc_up_mm 0] [--tag r1]
改動(相對 dry):
  * 右手關節每格加 Cartesian 偏移(數值 Jacobian 修正,姿態不變):b1 漸入 → b2~b4 = lift_mm·z + out_mm·s_out(#1 邊外向),
    b5 再線性加 arc_out_mm(−x_S,往折線外)+ arc_up_mm(z)。
  * 綁定對象:kinematic 代理方塊 /World/grip_proxy(無碰撞),每格 set_kinematic_targets 到 TCP(指面中點、指尖退 10mm)。
    (Isaac Lab #4628:deformable 直接 attach articulation link 實質不支援 → 不綁 follower_right_gripper_*)
  * b3 最後一格:attach_grip.select_vertices(pad, 只 yn 片上下兩層)→ bind;邊長比 > 2.3 自動 release。
  * b5 結束 → 停 hold 秒 → release → 開指 0.5 s → 再停 post 秒。"""
import os, sys, json, math, argparse, functools, builtins
print = functools.partial(builtins.print, flush=True)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import load_cloth as LC
ap = argparse.ArgumentParser(); LC.add_args(ap)
ap.add_argument("--traj", default=os.path.join(LC.ROOT, "arm", "data", "peel_traj_v2_pinch_fx1_g1_psi15_o260"))
ap.add_argument("--settle", type=float, default=0.5)
ap.add_argument("--lift_mm", type=float, default=10.0)
ap.add_argument("--out_mm", type=float, default=0.0)
ap.add_argument("--pad", type=float, default=16.0)
ap.add_argument("--arc_out_mm", type=float, default=0.0)
ap.add_argument("--arc_up_mm", type=float, default=0.0)
ap.add_argument("--hold", type=float, default=2.0)
ap.add_argument("--post", type=float, default=2.0)
ap.add_argument("--band_mm", type=float, default=None, help="覆寫高度帶:|n|<=band(診斷用,非真夾持)")
ap.add_argument("--gvert", type=int, default=None, help="改抓 yn 自由邊頂點(flat 索引);TCP 終點 = 該點較高層 + 指尖距 10mm + lift_mm")
ap.add_argument("--guard", type=float, default=2.3)
ap.add_argument("--no_video", action="store_true")
a = ap.parse_args()
TAG = "peel_with_cloth" + (("_" + a.tag) if a.tag else "")
from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
import numpy as np, omni.usd
from pxr import Usd, UsdGeom, UsdPhysics, Gf, Vt
LOG = open(os.path.join(HERE, "logs", TAG + ".log"), "w")
def P(*s):
    t = " ".join(str(x) for x in s); print(t); LOG.write(t + "\n"); LOG.flush()
P("args", vars(a))
omni.usd.get_context().open_stage(LC.SCENE)
for _ in range(10): app.update()
st = omni.usd.get_context().get_stage()
C = LC.setup(st, a, P)
sys.path.insert(0, os.path.join(LC.ROOT, "arm")); sys.path.insert(0, os.path.join(LC.VOL, "grip_attach"))
import robot_model as RM, volcommon as VC, attach_grip as AG
SCR = os.environ.get("PEEL_SCRATCH", "/tmp/peel_with_cloth_model"); os.makedirs(SCR, exist_ok=True)
MR = RM.build(st, "right", SCR)
R0 = "/World/stationary_ai"
FING = ["%s/follower_right_gripper_left" % R0, "%s/follower_right_gripper_right" % R0]
xc = UsdGeom.XformCache(); Wm = lambda p: np.array(xc.GetLocalToWorldTransform(st.GetPrimAtPath(p))).T
OBB = {}
for b in FING:
    Wb = Wm(b); pts = []
    for p in Usd.PrimRange(st.GetPrimAtPath(b)):
        if p.IsA(UsdGeom.Mesh) and "/collisions/" in str(p.GetPath()):
            v = np.array(UsdGeom.Mesh(p).GetPointsAttr().Get(), float)
            M = np.linalg.inv(Wb) @ Wm(str(p.GetPath())); pts.append((M @ np.c_[v, np.ones(len(v))].T).T[:, :3])
    pts = np.vstack(pts); OBB[b] = (pts.min(0), pts.max(0))
for p in Usd.PrimRange(st.GetPrimAtPath(R0)):
    if p.HasAPI(UsdPhysics.CollisionAPI) and "follower_" in str(p.GetPath()):
        keep = any(str(p.GetPath()).startswith(f + "/") for f in FING)
        UsdPhysics.CollisionAPI(p).CreateCollisionEnabledAttr().Set(bool(keep))
PROXY = "/World/grip_proxy"
VC.kin_box(st, PROXY, (0.020, 0.020, 0.004), (0, 0, 1.0), collide=False, visible=False)
IF = json.load(open(os.path.join(LC.VOL, "soft", "s2", "iface.json")))
G1 = np.array(IF["grasps"][0]["pos"]["S"]) * 1e-3; V1 = IF["grasps"][0]["v"]
SOUT = np.array(IF["grasps"][0]["edge_out_s"]["S"])
SIDE = np.array(IF["side"] * 2); YN = SIDE == "yn"
XF_NOM = (-71.5 - 20.0) * 1e-3
XF_MEAS = float(np.mean([e["S"][0] for f_ in IF["folds"] if tuple(f_["pair"]) == ("base", "yn") for e in f_["ends"]])) * 1e-3
P("抓取點 #1 v%d S %s mm;yn 頂點 %d;折線 x_S 名義 %.1f / 實測 %.1f mm" % (V1, (G1 * 1e3).round(1).tolist(), YN.sum(), XF_NOM * 1e3, XF_MEAS * 1e3))
Z = np.load(a.traj + ".npz"); J = json.load(open(a.traj + ".json")); FPS = int(Z["fps"])
segs = [s for s in J["segments"] if s["name"].startswith("b") and not s["name"].startswith("b0")]
def fr(t): return int(round(t * FPS))
SEG = {s["name"].split()[0]: (fr(s["t0"]), fr(s["t1"])) for s in segs}
f0 = SEG["b1"][0]; fB3 = SEG["b3"][1] - 1; fB5 = SEG["b5"][1] - 1
G0, GK, MIM = J["gap"]["G0"], J["gap"]["GK"], J["gap"]["mimic"]
gOpen = float(Z["gR"][SEG["b1"][1] - 1])
# 時間表:frame 列表(traj 索引, 事件)
plan = [(f, None) for f in range(f0, fB5 + 1)]
plan += [(fB5, "hold")] * int(round(a.hold * FPS))
plan += [(fB5, "open")] * int(round(0.5 * FPS)) + [(fB5, "post")] * int(round(a.post * FPS))
P("frame %d~%d,b3 末 %d、b5 末 %d;hold %.1fs 後釋放;共 %d 格" % (f0, fB5, fB3, fB5, a.hold, len(plan)))
BASE0 = np.array([0, 0, a.lift_mm]) * 1e-3 + SOUT * a.out_mm * 1e-3
if a.gvert is not None:
    _v = max((a.gvert, a.gvert + 1296), key=lambda v: C["S0"][v, 2]); _te = (MR["base_T"] @ RM.fk_np(MR, Z["qR"][SEG["b2"][1] - 1])["tcp"])[:3, 3]
    BASE0 = C["S0"][_v] + np.array([0, 0, 0.010 + a.lift_mm * 1e-3]) - _te
    P("改抓 v%d S %s mm;原 b2 終點 TCP %s → 偏移 %s mm" % (_v, (C["S0"][_v] * 1e3).round(1).tolist(), (_te * 1e3).round(1).tolist(), (BASE0 * 1e3).round(1).tolist()))
    V1 = _v
def offset(f, ev):
    base = BASE0
    arc = np.array([-a.arc_out_mm, 0, a.arc_up_mm]) * 1e-3
    if ev is not None: return base + arc
    if f < SEG["b1"][1]: return base * (f - f0) / (SEG["b1"][1] - f0)
    if f < SEG["b5"][0]: return base
    u = (f - SEG["b5"][0]) / max(1, SEG["b5"][1] - 1 - SEG["b5"][0]); return base + arc * min(1, u)
bR = MR["base_T"][:3, :3]
def tcp_w(q): return MR["base_T"] @ RM.fk_np(MR, q)["tcp"]
def corr(q, dpw):
    if np.linalg.norm(dpw) < 1e-7: return np.array(q, float), 0.0
    q = np.array(q, float); T0 = RM.fk_np(MR, q)["tcp"]; pt = T0[:3, 3] + bR.T @ dpw; Rt = T0[:3, :3]
    for _ in range(6):
        T = RM.fk_np(MR, q)["tcp"]; dR = Rt @ T[:3, :3].T
        e = np.r_[pt - T[:3, 3], 0.5 * np.array([dR[2, 1] - dR[1, 2], dR[0, 2] - dR[2, 0], dR[1, 0] - dR[0, 1]])]
        q = q + np.linalg.lstsq(RM.jac_np(MR, q), e, rcond=None)[0]
    return q, float(np.linalg.norm(RM.fk_np(MR, q)["tcp"][:3, 3] - pt) * 1e3)
QR = {}; ierr = 0.0
for f, ev in plan:
    k = (f, ev is not None)
    if k not in QR: QR[k], e_ = corr(Z["qR"][f], offset(f, ev)); ierr = max(ierr, e_)
P("右手偏移 IK 修正最大殘差 %.3f mm" % ierr)

from isaacsim.core.api import World
from isaacsim.core.prims import Articulation, RigidPrim, SingleXFormPrim
world = World(physics_dt=a.dt, rendering_dt=1.0 / FPS, stage_units_in_meters=1.0)
pc_ = world.get_physics_context(); pc_.enable_gpu_dynamics(True); pc_.set_broadphase_type("GPU")
cams = []
if not a.no_video:
    from isaacsim.sensors.camera import Camera
    from isaacsim.core.utils.viewports import set_camera_view
    import imageio
    from PIL import Image, ImageDraw, ImageFont
    for i, (eye, tgt) in enumerate((((-0.55, -0.45, 0.50), (-0.03, -0.08, 0.13)), ((-0.45, 0.30, 0.40), (-0.06, -0.06, 0.12)))):
        c = Camera(prim_path="/World/pc_cam%d" % i, resolution=(960, 540), frequency=FPS); cams.append((c, eye, tgt))
world.reset()
ART = Articulation(prim_paths_expr=R0, name="arms"); ART.initialize()
FR = RigidPrim(prim_paths_expr=FING, name="fing"); FR.initialize()
order = [str(p) for p in FR.prim_paths]
PV = world.physics_sim_view.create_rigid_body_view([PROXY])
dof = list(ART.dof_names)
idx = {s: [dof.index("follower_%s_joint_%d" % (s, k)) for k in range(6)] for s in ("left", "right")}
cidx = {s: (dof.index("follower_%s_left_carriage_joint" % s), dof.index("follower_%s_right_carriage_joint" % s)) for s in ("left", "right")}
for c, eye, tgt in cams:
    c.initialize(); set_camera_view(eye=np.array(eye), target=np.array(tgt), camera_prim_path=c.prim_path)
    cp = UsdGeom.Camera(st.GetPrimAtPath(c.prim_path)); cp.GetFocalLengthAttr().Set(18.0)
    cp.GetHorizontalApertureAttr().Set(20.955); cp.GetVerticalApertureAttr().Set(20.955 * 540 / 960); cp.GetClippingRangeAttr().Set(Gf.Vec2f(0.01, 100.0))
def qmat(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
def r2q(R):
    q = Gf.Matrix3d(*R.T.flatten().tolist()).ExtractRotation().GetQuat(); return np.array([q.GetReal(), *q.GetImaginary()])
GAX = None
def grip_frame(qr):
    """TCP 位置 + R(第 3 軸 = 兩指連線方向)。"""
    global GAX
    T = tcp_w(qr); Rt = T[:3, :3]
    if GAX is None:
        pos = np.array(FR.get_world_poses()[0], float); d = pos[1] - pos[0]
        GAX = int(np.argmax(np.abs(Rt.T @ d))); P("夾持軸 = TCP 第 %d 軸(兩指連線投影 %s)" % (GAX, np.round(Rt.T @ d / np.linalg.norm(d), 3).tolist()))
    o = [i for i in range(3) if i != GAX]; Rf = np.column_stack([Rt[:, o[0]], Rt[:, o[1]], Rt[:, GAX]])
    if np.linalg.det(Rf) < 0: Rf[:, 0] *= -1
    return T[:3, 3], Rf
def set_proxy(c, R):
    q = r2q(R); D = np.array([[*c, q[1], q[2], q[3], q[0]]], np.float32)
    PV.set_kinematic_targets(D, np.arange(1, dtype=np.int32))
def apply(f, ev):
    Jq = np.array(ART.get_joint_positions(), float)[0]
    qr = QR[(f, ev is not None)]
    Jq[idx["left"]] = Z["qL"][f]; Jq[idx["right"]] = qr
    gr = Z["gR"][f]
    if ev == "open" or ev == "post": gr = gOpen if ev == "post" else gr + (gOpen - gr) * apply.k / max(1, int(0.5 * FPS)); apply.k += ev == "open"
    for s, g in (("left", Z["gL"][f]), ("right", gr)):
        Jq[cidx[s][0]] = g; Jq[cidx[s][1]] = MIM * g
    ART.set_joint_positions(Jq[None]); ART.set_joint_position_targets(Jq[None]); ART.set_joint_velocities(np.zeros_like(Jq)[None])
    c, R = grip_frame(qr); set_proxy(c, R); return c, R, gr
apply.k = 0
def finger_sd(Pc):
    pos, qs = [np.array(v, float) for v in FR.get_world_poses()]; best = np.full(len(Pc), 9.9)
    for j, b in enumerate(order):
        R = qmat(qs[j]); lo, hi = OBB[b]; c = (lo + hi) / 2; h = (hi - lo) / 2
        l = (Pc - pos[j]) @ R - c; d = np.abs(l) - h
        sd = np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(d.max(1), 0); best = np.minimum(best, sd)
    return best
T_ = C["TETS"]; EDG = np.unique(np.sort(np.vstack([T_[:, [i, j]] for i, j in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))]), 1), axis=0)
L0 = np.linalg.norm(C["S0"][EDG[:, 0]] - C["S0"][EDG[:, 1]], axis=1)
def rel(sc):
    """釋放 = attachmentEnabled False(不 RemovePrim;r2 RemovePrim 後程序無訊息結束)。"""
    ch = st.GetPrimAtPath(sc + "/vtx_xform_attachment")
    if ch: ch.GetAttribute("omniphysics:attachmentEnabled").Set(False)
def eratio(Pc): return float((np.linalg.norm(Pc[EDG[:, 0]] - Pc[EDG[:, 1]], axis=1) / L0).max())
apply(f0, None)
for _ in range(int(round(a.settle * FPS))): world.step(render=bool(cams))
_F = np.vstack([T_[:, [0, 2, 1]], T_[:, [0, 1, 3]], T_[:, [1, 2, 3]], T_[:, [0, 3, 2]]])
_k = np.sort(_F, 1); _u, _inv, _c = np.unique(_k, axis=0, return_inverse=True, return_counts=True); SF = _F[_c[_inv.ravel()] == 1]
VIS = UsdGeom.Mesh.Define(st, "/World/cloth_vis"); VIS.CreateFaceVertexIndicesAttr([int(i) for i in SF.ravel()]); VIS.CreateFaceVertexCountsAttr([3] * len(SF))
VIS.CreateDoubleSidedAttr(True); VIS.CreateDisplayColorAttr([Gf.Vec3f(0.2, 0.7, 0.95)])
def upd_vis(Pc): VIS.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in Pc]))
Pb = C["PLATE"].pts(); upd_vis(Pb)
YNIN = YN & (Pb[:, 0] > XF_MEAS)       # 起始在折線內側的 yn 頂點(分母)
def cross(Pc, xf): return 100.0 * float((Pc[YNIN, 0] < xf).sum()) / max(1, YNIN.sum())
r = C["measure"](Pb); P("settle 後:位移 %.2f mm 反轉 %d 互穿 %d 穿杯 %d;yn 分母 %d" % (r["disp"], r["inv"], r["pen"], r["inmug"], YNIN.sum()))
MX = SingleXFormPrim("/World/cloth_mug", name="mugx"); mug_p0 = np.array(MX.get_world_pose()[0])
wr = None
if cams:
    try: FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 17)
    except Exception: FONT = None
    wr = imageio.get_writer(os.path.join(HERE, "videos", TAG + ".mp4"), fps=FPS, codec="libx264", quality=8, pixelformat="yuv420p")
def segname(f, ev):
    if ev: return ev
    for n, (s0, s1) in SEG.items():
        if s0 <= f < s1: return n
    return "b5"
BASE = np.zeros(len(Pb)); scope = None; VB = np.zeros(0, int); LOCB = None
M = dict(pen_b2=0.0, v1push=0.0, other_pct=0.0, mug=0.0, er_max=0.0, slip=0.0, nbind=0, guard=None, yn_nom=0.0, yn_meas=0.0)
KEY = {}; rows = []
for k, (f, ev) in enumerate(plan):
    c, R, gr = apply(f, ev); world.step(render=bool(cams))
    Pc = C["PLATE"].pts(); upd_vis(Pc); sn = segname(f, ev); sd = finger_sd(Pc)
    disp = np.linalg.norm(Pc - Pb, axis=1)
    if sn == "b1": BASE = np.maximum(BASE, disp)
    if sn in ("b2", "b3") and f < SEG["b3"][1] and (sn == "b2" or f < fB3):
        M["pen_b2"] = max(M["pen_b2"], -sd.min() * 1e3); M["v1push"] = max(M["v1push"], disp[V1] * 1e3)
    oth = 100.0 * float(((disp - BASE) > 0.010)[~YN].sum()) / (~YN).sum()
    M["other_pct"] = max(M["other_pct"], oth); mugd = np.linalg.norm(np.array(MX.get_world_pose()[0]) - mug_p0) * 1e3; M["mug"] = max(M["mug"], mugd)
    er = eratio(Pc); M["er_max"] = max(M["er_max"], er)
    yn1, yn2 = cross(Pc, XF_NOM), cross(Pc, XF_MEAS)
    slip = float(np.linalg.norm(Pc[VB] - (c + LOCB @ R.T), axis=1).max() * 1e3) if scope else 0.0
    if scope: M["slip"] = max(M["slip"], slip)
    if f == fB3 and ev is None and scope is None and not KEY.get("bind"):
        fp = AG.finger_pose(c, R, (G0 + GK * gr) * 1e-3, (0.010, 0.010))
        VB = AG.select_vertices(Pc, fp, a.pad, YN, band_tol=(AG.BAND_TOL if a.band_mm is None else a.band_mm * 1e-3 - fp["gap"] / 2))
        Lc = (Pc - c) @ R; near = YN & (np.abs(Lc[:, 0]) < 0.026) & (np.abs(Lc[:, 1]) < 0.026)
        P("t=%.2f 綁定候選:yn 足跡內(不限高度帶)%d 點,|n| 範圍 %s mm;選中 %d(上層 %d / 下層 %d);gap %.2f mm" % (
            f / FPS, near.sum(), np.round([Lc[near, 2].min() * 1e3, Lc[near, 2].max() * 1e3], 1).tolist() if near.any() else "-",
            len(VB), int((VB < 1296).sum()), int((VB >= 1296).sum()), G0 + GK * gr))
        scope = AG.bind(st, VB, PROXY, points=Pc, body_path="/World/cloth", finger_pos=c, finger_R=R, scope="/World/gatt_peel", P=P)
        LOCB = (Pc[VB] - c) @ R; M["nbind"] = len(VB); KEY["bind"] = dict(t=f / FPS, **C["measure"](Pc))
    if scope and er > a.guard:
        rel(scope); scope = None; M["guard"] = dict(t=round(f / FPS, 2), er=er, seg=sn); P("★ 守衛:邊長比 %.2f > %.1f,t=%.2f %s 自動 release" % (er, a.guard, f / FPS, sn))
    if ev == "hold" and plan[k + 1][1] != "hold":
        M["yn_nom"], M["yn_meas"] = yn1, yn2; KEY["pre_release"] = dict(t=f / FPS, yn_nom=yn1, yn_meas=yn2, slip=M["slip"], **C["measure"](Pc))
        P("t=%.2f 釋放前:yn 越線 名義 %.1f%% / 實測 %.1f%%,滑動 max %.2f mm,邊長比 max %.2f" % (f / FPS, yn1, yn2, M["slip"], M["er_max"]))
        if scope: rel(scope); scope = None; P("  release")
    if f == fB5 and ev is None: KEY["b5_end"] = dict(t=f / FPS, yn_nom=yn1, yn_meas=yn2, **C["measure"](Pc))
    if k % (FPS // 2) == 0 or k == len(plan) - 1:
        rows.append(dict(t=round(k / FPS, 2), seg=sn, dmin=float(sd.min() * 1e3), oth=oth, er=er, yn=yn2, slip=slip))
        P("k=%4d %-4s 指布最小 %7.2f mm | 他片(扣 b1 基線)>10mm %.1f%% | yn 越線 %.1f/%.1f%% | 邊長比 %.2f | 滑動 %.2f | #1 位移 %.1f | 杯 %.2f"
          % (k, sn, sd.min() * 1e3, oth, yn1, yn2, er, slip, disp[V1] * 1e3, mugd))
    if wr:
        ims = []
        for cc, _e, _t in cams:
            rgb = cc.get_rgba(); ims.append(np.asarray(rgb)[:, :, :3] if rgb is not None and rgb.size else np.zeros((540, 960, 3), np.uint8))
        im = Image.fromarray(np.concatenate(ims, 1)); dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, 1300, 44], fill=(0, 0, 0))
        dr.text((6, 3), "t=%5.2fs %-4s %s bound %d  yn crossed %.0f%%  other>10mm %.1f%%  edge ratio %.2f  slip %.1f mm"
                % (k / FPS, sn, "ATTACHED" if scope else "free", len(VB) if scope else 0, yn2, oth, er, slip), fill=(255, 255, 255), font=FONT)
        wr.append_data(np.asarray(im))
if wr: wr.close()
Pc = C["PLATE"].pts(); KEY["end"] = dict(yn_nom=cross(Pc, XF_NOM), yn_meas=cross(Pc, XF_MEAS), **C["measure"](Pc))
P("\n=== 總結 %s" % TAG)
P("下降穿入(合指前)%.2f mm | #1 被推 %.1f mm | 綁 %d | 滑動 %.2f mm | yn 越線 名義 %.1f%% / 實測 %.1f%% | 他片 %.1f%% | 杯 %.2f mm | 邊長比 %.2f | 守衛 %s"
  % (M["pen_b2"], M["v1push"], M["nbind"], M["slip"], M["yn_nom"], M["yn_meas"], M["other_pct"], M["mug"], M["er_max"], M["guard"]))
for kk, v in KEY.items(): P("  %-11s %s" % (kk, {x: (round(y, 2) if isinstance(y, float) else y) for x, y in v.items() if x not in ("bb",)}))
ok = M["nbind"] >= 6 and M["yn_meas"] >= 80 and M["other_pct"] < 5 and M["mug"] < 5 and KEY["end"]["inmug"] == 0 and KEY["end"]["yn_meas"] >= 60
P("★ 判定 %s" % ("PASS" if ok else "FAIL"))
json.dump(dict(args=vars(a), M=M, KEY=KEY, rows=rows, ok=ok), open(os.path.join(HERE, "logs", TAG + ".json"), "w"), indent=1, default=str)
app.close()
