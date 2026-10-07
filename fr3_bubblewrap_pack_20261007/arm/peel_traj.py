#!/usr/bin/env python3
"""peel_traj.py — 空箱 + 蓋子(無包材)的手臂乾跑軌跡,kinematic 設關節(set_joint_positions)。
    /isaac-sim/python.sh peel_traj.py [--hand_b right|left] [--no_video]
(a) PPT 第 1 步:右手掀後方上蓋 fyn(世界 +x)、左手按前方上蓋 fyp(世界 −x)。蓋子用 lid_pose 轉,手跟著外緣中點走(剛性夾持)。
(b) 四片蓋全開(180°)後,--hand_b 那隻手:#1 上方 60mm → 下降 → 合指到 4.5mm → 抬 30mm → 沿弧線掀。
IK:Lula(robot_model.py 由場景 USD 產生的 URDF);姿態規則同 reach.py,不行時指尖方向繞開合軸放寬 φ。
碰撞:**幾何檢查**,不是 PhysX 接觸。手臂各剛體的 collision mesh 表面取樣點(每體 ~1500 點)用 numpy FK 擺到世界,
  對紙箱 9 個 Cube(箱底 1 + 牆 4 + 蓋 4)算有號距離(<0 = 穿入);兩臂之間用 KD-tree 量點對點最小距離;桌面 z。
  夾著/壓著的那片蓋 vs 該手的指頭 = 預期接觸,另列。每格也讀回 PhysX 的 link_6 位姿跟 FK 比(確認 set_joint_positions 真的到位)。"""
import os, sys, json, math, argparse, functools, builtins
print = functools.partial(builtins.print, flush=True)
ap = argparse.ArgumentParser()
ap.add_argument("--scene", default="/isaac-sim/test_scripts/manip_fr3/handoff_20261002/scene_final.usd")
ap.add_argument("--hand_b", default="right")
ap.add_argument("--lid_end", type=float, default=150.0, help="(a) 後方上蓋掀到幾度")
ap.add_argument("--out", default=None)
ap.add_argument("--no_video", action="store_true")
a = ap.parse_args()
from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
import numpy as np
import omni.usd
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Gf, Sdf
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import robot_model as RM
from isaacsim.robot_motion.motion_generation import LulaKinematicsSolver
import lula, trimesh
from scipy.spatial import cKDTree
TAG = "b%s" % a.hand_b
OUT = a.out or os.path.join(HERE, "videos", "arm_peel_dry.mp4" if a.hand_b == "right" else "arm_peel_dry_%s.mp4" % TAG)
os.makedirs(os.path.join(HERE, "videos"), exist_ok=True); os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
LOG = open(os.path.join(HERE, "logs", "peel_traj_%s.log" % TAG), "w")
def P(*s):
    t = " ".join(str(x) for x in s); print(t); LOG.write(t + "\n"); LOG.flush()

omni.usd.get_context().open_stage(a.scene)
for _ in range(10): app.update()
st = omni.usd.get_context().get_stage()
BOX = "/World/Packed/Box"
for p in ("/World/Packed/Wrap", "/World/Packed/Mug"):
    st.GetPrimAtPath(p).SetActive(False)
P("包材 / 杯子 deactivate(空箱 + 蓋子)")
if not any(p.IsA(UsdPhysics.Scene) for p in st.Traverse()):
    ps = UsdPhysics.Scene.Define(st, "/physicsScene")
else:
    ps = UsdPhysics.Scene(next(p for p in st.Traverse() if p.IsA(UsdPhysics.Scene)))
ps.CreateGravityMagnitudeAttr().Set(0.0)      # kinematic 乾跑:不要重力把手臂往下拉
for n in ("base", "fxp", "fxn", "fyp", "fyn"):
    UsdPhysics.RigidBodyAPI(st.GetPrimAtPath(BOX + "/" + n)).CreateKinematicEnabledAttr().Set(True)
for n in ("fxp", "fxn", "fyp", "fyn"):
    UsdPhysics.Joint(st.GetPrimAtPath(BOX + "/crease_" + n)).CreateJointEnabledAttr().Set(False)
P("紙箱底 + 4 蓋 = kinematic,摺痕關節停用(蓋子由 lid_pose 直接擺)、重力 0")

xc = UsdGeom.XformCache()
def Wm(p): return np.array(xc.GetLocalToWorldTransform(st.GetPrimAtPath(p))).T
TB = Wm(BOX)
RJ = json.load(open(os.path.join(HERE, "data", "reach.json")))
meta = json.load(open("/isaac-sim/test_scripts/manip_fr3/handoff_20260929/work/carton.meta.json"))["derived"]

# ── 手臂模型 + IK ─────────────────────────────────────────
ARMS = {}
for side in ("left", "right"):
    m = RM.build(st, side, os.path.join(HERE, "data"))
    sol = LulaKinematicsSolver(robot_description_path=m["desc"], urdf_path=m["urdf"])
    bT = m["base_T"]; q = Gf.Matrix3d(*bT[:3, :3].T.flatten().tolist()).ExtractRotation().GetQuat()
    sol.set_robot_base_pose(bT[:3, 3], np.array([q.GetReal(), *q.GetImaginary()]))
    sol.set_default_position_tolerance(0.001); sol.set_default_orientation_tolerance(0.01)
    sol.bfgs_cspace_limit_biasing = lula.CyclicCoordDescentIkConfig.CSpaceLimitBiasing.ENABLE
    m.update(sol=sol, lo=np.array([l for l, h in m["lims"]]), hi=np.array([h for l, h in m["lims"]]))
    ARMS[side] = m

def quat(R):
    q = Gf.Matrix3d(*R.T.flatten().tolist()).ExtractRotation().GetQuat(); return np.array([q.GetReal(), *q.GetImaginary()])
def rot_axis(k, deg):
    k = np.asarray(k, float) / np.linalg.norm(k); th = math.radians(deg)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K
def wrap_lim(q, lo, hi):
    q = np.array(q, float)
    for i in range(len(q)):
        for k in (-1, 1):
            if not (lo[i] <= q[i] <= hi[i]) and lo[i] <= q[i] + k * 2 * math.pi <= hi[i]: q[i] += k * 2 * math.pi
    return q
def fk_tcp(side, q):
    m = ARMS[side]; return m["base_T"] @ RM.fk_np(m, q)["tcp"]
def check(side, q, pos, R):
    m = ARMS[side]; T = fk_tcp(side, q)
    pe = np.linalg.norm(T[:3, 3] - pos) * 1e3
    oe = math.degrees(math.acos(max(-1, min(1, (np.trace(T[:3, :3].T @ R) - 1) / 2))))
    inl = bool(np.all(q >= m["lo"] - 1e-4) and np.all(q <= m["hi"] + 1e-4))
    return pe < 1.5 and oe < 1.5 and inl, pe, oe
PHIS = [0, 5, -5, 10, -10, 15, -15, 20, -20, 30, -30, 45, -45, 60, -60, 75, -75, 90, -90]
def ik(side, pos, R, q_prev, phi_prev=0.0, maxjump=25.0, nseed=12):
    """φ 依離 phi_prev 遠近排序;先用 q_prev 起點,再試隨機起點;要求跟前一點的關節跳動 < maxjump°。"""
    m = ARMS[side]; rng = np.random.default_rng(11)
    order = sorted(PHIS, key=lambda p: (abs(p - phi_prev), abs(p)))
    for ph in order:
        Rp = rot_axis(R[:, 1], ph) @ R
        for flip in (1, -1):
            Rf = Rp.copy()
            if flip < 0: Rf[:, 1] *= -1; Rf[:, 2] *= -1
            starts = [q_prev] + [m["lo"] + (m["hi"] - m["lo"]) * rng.uniform(0.05, 0.95, 6) for _ in range(nseed if q_prev is None else 4)]
            for w in starts:
                if w is None: continue
                qs, ok = m["sol"].compute_inverse_kinematics("tcp", pos, quat(Rf), warm_start=np.asarray(w))
                qs = wrap_lim(qs, m["lo"], m["hi"])
                good, pe, oe = check(side, qs, pos, Rf)
                if good and (q_prev is None or np.max(np.abs(qs - q_prev)) < math.radians(maxjump)):
                    return qs, ph
    return None, None
def cart(side, poses, q0, phi0):
    qs, phis = [], []; q, ph = q0, phi0
    for i, (p_, R_) in enumerate(poses):
        qn, phn = ik(side, p_, R_, q, ph)
        if qn is None:
            return qs, phis, i
        qs.append(qn); phis.append(phn); q, ph = qn, phn
    return qs, phis, None
def lerp_q(q0, q1, n):
    return [q0 + (q1 - q0) * (0.5 - 0.5 * math.cos(math.pi * k / (n - 1))) for k in range(n)]

# ── 夾爪:指面間距 vs carriage 關節 ─────────────────────────
JALL = {}
for p in st.Traverse():
    if p.IsA(UsdPhysics.Joint) and "/joints/" in str(p.GetPath()):
        j = UsdPhysics.Joint(p); b0 = j.GetBody0Rel().GetTargets(); b1 = j.GetBody1Rel().GetTargets()
        if b0 and b1:
            JALL[str(b1[0])] = dict(name=p.GetName(), b0=str(b0[0]), T0=RM.T_of(j.GetLocalPos0Attr().Get(), j.GetLocalRot0Attr().Get()),
                                   T1=RM.T_of(j.GetLocalPos1Attr().Get(), j.GetLocalRot1Attr().Get()), prim=p)
R0 = RM.ROOT
def body_fk(side, q6, qc_l, qc_r):
    """各剛體世界 4x4。carriage = link_6·T0·Trans(axis·q)·T1⁻¹;其餘 fixed 子體一路往下接。"""
    m = ARMS[side]; fk = RM.fk_np(m, q6); out = {}
    for k in range(1, 7): out["%s/follower_%s_link_%d" % (R0, side, k)] = m["base_T"] @ fk["link_%d" % k]
    js = m["js"]
    for nm, qq in (("left_carriage_joint", qc_l), ("right_carriage_joint", qc_r)):
        J = js[nm]; Tr = np.eye(4); Tr[:3, 3] = np.array(J["axis"], float) * qq
        out[J["b1"]] = out[J["b0"]] @ J["T0"] @ Tr @ np.linalg.inv(J["T1"])
    changed = True
    while changed:
        changed = False
        for b1, J in JALL.items():
            if b1 not in out and J["b0"] in out and ("follower_%s_" % side) in b1 and J["prim"].IsA(UsdPhysics.FixedJoint):
                out[b1] = out[J["b0"]] @ J["T0"] @ np.linalg.inv(J["T1"]); changed = True
    return out
# 剛體的 collision mesh 取樣點(body 座標)
PTS = {}
for side in ("left", "right"):
    for b in body_fk(side, np.zeros(6), 0, 0):
        Wb = Wm(b); pts = []
        for p in Usd.PrimRange(st.GetPrimAtPath(b)):
            if p.IsA(UsdGeom.Mesh) and "/collisions/" in str(p.GetPath()):
                mm = UsdGeom.Mesh(p); v = np.array(mm.GetPointsAttr().Get(), float)
                fc = np.array(mm.GetFaceVertexCountsAttr().Get()); fi = np.array(mm.GetFaceVertexIndicesAttr().Get())
                if np.all(fc == 3):
                    tm = trimesh.Trimesh(v, fi.reshape(-1, 3), process=False)
                    sp, _ = trimesh.sample.sample_surface(tm, 1500, seed=0); v = np.vstack([sp, v[::max(1, len(v) // 300)]])
                M = np.linalg.inv(Wb) @ Wm(str(p.GetPath()))
                pts.append((M @ np.c_[v, np.ones(len(v))].T).T[:, :3])
        if pts: PTS[b] = np.vstack(pts)
P("碰撞取樣:%d 個剛體,共 %d 點" % (len(PTS), sum(len(v) for v in PTS.values())))
def finger_gap(side, qc_l, qc_r):
    """兩指 collision 點在 tcp 座標的開合軸(y)上的內面距離;只看指尖往回 25mm 的指面區。"""
    B = body_fk(side, np.zeros(6), qc_l, qc_r); Tt = ARMS[side]["base_T"] @ RM.fk_np(ARMS[side], np.zeros(6))["ee_tip"]
    ys = {}
    for f in ("gripper_left", "gripper_right"):
        b = "%s/follower_%s_%s" % (R0, side, f); w = (B[b] @ np.c_[PTS[b], np.ones(len(PTS[b]))].T).T[:, :3]
        l = (np.linalg.inv(Tt) @ np.c_[w, np.ones(len(w))].T).T[:, :3]
        l = l[(l[:, 0] > -0.025) & (l[:, 0] < 0.001)]
        ys[f] = l[:, 1]
    A, Bf = ("gripper_left", "gripper_right") if ys["gripper_left"].mean() > ys["gripper_right"].mean() else ("gripper_right", "gripper_left")
    return (ys[A].min() - ys[Bf].max()) * 1e3, (ys[A].min() + ys[Bf].max()) / 2 * 1e3
for sgn in (1, -1):
    g0, c0 = finger_gap("right", 0, 0); g1, c1 = finger_gap("right", 0.02, sgn * 0.02)
    P("夾爪測試:carriage_left=20mm、right=%+dmm → 指面間距 %.1f → %.1f mm,中心偏移 %.1f mm" % (sgn * 20, g0, g1, c1 - c0))
gA = finger_gap("right", 0.02, 0.02); gB = finger_gap("right", 0.02, -0.02)
MIM = 1.0 if abs(gA[1] - finger_gap("right", 0, 0)[1]) < abs(gB[1] - finger_gap("right", 0, 0)[1]) else -1.0
G0 = finger_gap("right", 0, 0)[0]; GK = (finger_gap("right", 0.02, MIM * 0.02)[0] - G0) / 0.02
GMAX = finger_gap("right", 0.044, MIM * 0.044)[0]
P("★ 夾爪:right_carriage = %+.0f × left_carriage(對稱);指面間距 = %.1f mm + %.2f × q(m);q=0 → %.1f mm、q=44mm(上限)→ %.1f mm" % (MIM, G0, GK, G0, GMAX))
def q_for_gap(gmm): return max(0.0, min(0.044, (gmm - G0) / GK))

# ── 紙箱 OBB ──────────────────────────────────────────────
OBB = []
BBC = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
for body in ("base", "fxp", "fxn", "fyp", "fyn"):
    for p in Usd.PrimRange(st.GetPrimAtPath(BOX + "/" + body)):
        if p.IsA(UsdGeom.Cube):
            rg = BBC.ComputeUntransformedBound(p).GetRange()
            M = Wm(str(p.GetPath())); mn, mx = np.array(rg.GetMin()), np.array(rg.GetMax())
            ctr = M @ np.r_[(mn + mx) / 2, 1]; ax = M[:3, :3] * ((mx - mn) / 2)
            hl = np.linalg.norm(ax, axis=0); U = ax / hl
            OBB.append(dict(name=body + ("/" + p.GetName() if body == "base" else ""), body=body, c0=ctr[:3], U0=U, h=hl))
P("紙箱 Cube:%s" % ", ".join("%s %.0fx%.0fx%.0f" % (o["name"], *(2e3 * o["h"])) for o in OBB))
LID = {}
for nm, L in RJ["lids"].items():
    LID[nm] = dict(hw=(TB @ np.r_[L["h"], 1])[:3], aw=TB[:3, :3] @ np.array(L["ax"]), sgn=L["sgn"], mid=np.array(L["mid"]))
def lid_T(nm, deg):
    L = LID[nm]; T = np.eye(4); R = rot_axis(L["aw"], L["sgn"] * deg)
    T[:3, :3] = R; T[:3, 3] = L["hw"] - R @ L["hw"]; return T
def lid_edge(nm, deg):
    return (lid_T(nm, deg) @ TB @ np.r_[LID[nm]["mid"], 1])[:3]
def sdist(pts, o, T):
    c = (T @ np.r_[o["c0"], 1])[:3]; U = T[:3, :3] @ o["U0"]
    l = (pts - c) @ U; d = np.abs(l) - o["h"]
    out = np.linalg.norm(np.maximum(d, 0), axis=1); inside = np.minimum(d.max(1), 0)
    return out + inside
TABLE_Z = 0.020

# ── 軌跡 ──────────────────────────────────────────────────
FPS = 30
SEG = []        # dict(name, n, qL[n], gL[n], qR[n], gR[n], lids[n]{nm:deg}, contact{side:lid})
HOME = np.zeros(6)
lids0 = dict(fxp=0.0, fxn=0.0, fyp=0.0, fyn=0.0)
st_ = dict(qL=HOME.copy(), qR=HOME.copy(), gL=0.0, gR=0.0, lids=dict(lids0))
def add(name, secs, qL=None, qR=None, gL=None, gR=None, lids=None, contact=None):
    n = max(2, int(round(secs * FPS)))
    def seq(v, cur):
        if v is None: return [cur.copy() if hasattr(cur, "copy") else cur] * n
        if isinstance(v, list): return v if len(v) == n else [v[min(len(v) - 1, int(k * len(v) / n))] for k in range(n)]
        return lerp_q(np.atleast_1d(cur).astype(float), np.atleast_1d(v).astype(float), n) if hasattr(v, "__len__") else \
            [cur + (v - cur) * (0.5 - 0.5 * math.cos(math.pi * k / (n - 1))) for k in range(n)]
    s = dict(name=name, n=n, qL=seq(qL, st_["qL"]), qR=seq(qR, st_["qR"]), gL=seq(gL, st_["gL"]), gR=seq(gR, st_["gR"]),
             contact=contact or {})
    if lids is None: s["lids"] = [dict(st_["lids"])] * n
    elif isinstance(lids, list): s["lids"] = [lids[min(len(lids) - 1, int(k * len(lids) / n))] for k in range(n)]
    else:
        s["lids"] = [{k: st_["lids"][k] + (lids.get(k, st_["lids"][k]) - st_["lids"][k]) * (0.5 - 0.5 * math.cos(math.pi * i / (n - 1))) for k in lids0} for i in range(n)]
    SEG.append(s); st_.update(qL=np.array(s["qL"][-1]), qR=np.array(s["qR"][-1]), gL=float(s["gL"][-1]), gR=float(s["gR"][-1]), lids=dict(s["lids"][-1]))
    return s
def cart_seg(side, poses, q0, phi0, label):
    qs, phis, fail = cart(side, poses, q0, phi0)
    if fail is not None:
        P("  ✗ %s:%s 第 %d/%d 點 IK 失敗(位置 %s mm),之後停在上一點" % (label, side, fail, len(poses), (poses[fail][0] * 1e3).round(1).tolist()))
        if not qs: qs, phis = [q0], [phi0]
    P("  %s(%s):%d 點,φ %s" % (label, side, len(qs), sorted(set(int(p) for p in phis))))
    return qs, phis, fail
def Rspec_lid(nm):
    # 指尖朝 −z、開合軸 = 邊的水平法線(從鉸鏈指向外緣)
    e = lid_edge(nm, 0); h = LID[nm]["hw"]; ax = LID[nm]["aw"]; r = e - h; r -= ax * (r @ ax); c = np.array([r[0], r[1], 0]); c /= np.linalg.norm(c)
    a_ = np.array([0, 0, -1.0]); return np.column_stack([a_, c, np.cross(a_, c)])
FAIL = []
OPEN_GAP = 21.0; CLOSE_GAP = 4.5
gOpen, gClose, gShut = q_for_gap(OPEN_GAP), q_for_gap(CLOSE_GAP), 0.0
P("指寬:開 %.1f mm ⇒ q %.1f mm;合 %.1f mm ⇒ q %.1f mm" % (OPEN_GAP, gOpen * 1e3, CLOSE_GAP, gClose * 1e3))

P("\n=== (a) 右手掀後方上蓋 fyn(世界 +x)、左手按前方上蓋 fyp(世界 −x)")
# 右手:外緣中點(剛性夾持跟著蓋轉)
eR = lid_edge("fyn", 0); RR0 = Rspec_lid("fyn")
qpre, phR = ik("right", eR + np.array([0, 0, 0.06]), RR0, None)
P("  右手 fyn 外緣中點 世界 %s mm;預備點 IK %s φ%s" % ((eR * 1e3).round(1).tolist(), qpre is not None, phR))
# 左手:按 fyp 板面(箱局部 x=+90 → 世界 y=+90 靠左臂那側;x=+60 時兩臂最近 0.2mm、離鉸鏈 55mm 處),合指、指尖剛好碰到蓋頂
Lf = RJ["lids"]["fyp"]; th_ = meta["board_thickness"]
press_loc = np.array(Lf["h"]) + np.array([0.09, -0.055, 0]); press_loc[2] = Lf["mid"][2] + 0.0015
pw = (TB @ np.r_[press_loc, 1])[:3]
RL0 = np.column_stack([[0, 0, -1.0], [1.0, 0, 0], np.cross([0, 0, -1.0], [1.0, 0, 0])])
tipL = pw + np.array([0, 0, RM.TCP_BACK])        # tcp 在指尖上方 10mm ⇒ 指尖 = 板面
qLpre, phL = ik("left", tipL + np.array([0, 0, 0.06]), RL0, None)
P("  左手按壓點 世界 %s mm;預備點 IK %s φ%s" % ((pw * 1e3).round(1).tolist(), qLpre is not None, phL))
if qpre is None or qLpre is None: FAIL.append("(a) 預備點 IK 失敗")
else:
    add("a1 到預備點", 2.5, qL=qLpre, qR=qpre, gL=gShut, gR=q_for_gap(10.0))
    dn = [(eR + np.array([0, 0, 0.06 * (1 - u)]), RR0) for u in np.linspace(0, 1, 30)]
    qsR, _, f1 = cart_seg("right", dn, qpre, phR, "a2 下降到外緣")
    dnL = [(tipL + np.array([0, 0, 0.06 * (1 - u)]), RL0) for u in np.linspace(0, 1, 30)]
    qsL, _, f2 = cart_seg("left", dnL, qLpre, phL, "a2 下降按壓")
    add("a2 右下降到外緣 / 左下降按壓", 1.5, qL=qsL, qR=qsR, contact=dict(left="fyp", right="fyn"))
    add("a3 右合指 %.1fmm" % CLOSE_GAP, 0.5, gR=gClose, contact=dict(left="fyp", right="fyn"))
    degs = np.linspace(0, a.lid_end, 60)
    arcR = []
    for d in degs:
        T = lid_T("fyn", d); arcR.append((T[:3, :3] @ eR + T[:3, 3], T[:3, :3] @ RR0))
    qsA, phA, f3 = cart_seg("right", arcR, qsR[-1], _[-1] if _ else phR, "a4 蓋 fyn 0→%.0f°" % a.lid_end)
    reached = degs[len(qsA) - 1] if qsA else 0
    if f3 is not None: FAIL.append("(a) fyn 只掀到 %.0f°" % reached)
    nA = len(qsA)
    add("a4 掀 fyn 0→%.0f°(左手壓住 fyp)" % reached, 4.0 * nA / len(degs), qR=qsA,
        lids=[dict(st_["lids"], fyn=float(d)) for d in degs[:nA]], contact=dict(left="fyp", right="fyn"))
    # 放開、退
    TR = fk_tcp("right", qsA[-1]); back = [(TR[:3, 3] + np.array([0, 0, 0.05 * u]), TR[:3, :3]) for u in np.linspace(0, 1, 20)]
    add("a5 右開指", 0.4, gR=q_for_gap(10.0))
    qsB, _, _f = cart_seg("right", back, qsA[-1], phA[-1], "a5 右開指後往上 50mm")
    up = [(tipL + np.array([0, 0, 0.06 * u]), RL0) for u in np.linspace(0, 1, 20)]
    qsU, _, _f = cart_seg("left", up, qsL[-1], 0, "a5 左抬 60mm")
    add("a5 右退 / 左抬", 1.0, qL=qsU, qR=qsB)
    add("a6 回 home", 2.0, qL=HOME, qR=HOME, gL=0.0, gR=0.0)

P("\n=== (b) 開四片蓋 → %s 手掀抓取點 #1" % a.hand_b)
add("b0 上蓋 fy 開到 180°", 1.2, lids=dict(fyp=180.0, fyn=180.0))
add("b0 下蓋 fx 開到 180°", 1.2, lids=dict(fxp=180.0, fxn=180.0))
H = a.hand_b
g1 = RJ["grasp"]["1"]
so = np.array(g1["so"]); av = np.array(g1["a"])
Rg_loc = np.column_stack([av, so, np.cross(av, so)])
Rg = TB[:3, :3] @ Rg_loc
pg = (TB @ np.r_[np.array(g1["p"]) * 1e-3, 1])[:3]
qpre, phpre = ik(H, pg + np.array([0, 0, 0.06]), Rg, None)
P("  抓取點 #1 世界 %s mm;預備點(上方 60mm)IK %s φ%s" % ((pg * 1e3).round(1).tolist(), qpre is not None, phpre))
if qpre is None: FAIL.append("(b) 預備點 IK 失敗")
else:
    qk = "qR" if H == "right" else "qL"; gk = "gR" if H == "right" else "gL"
    add("b1 到 #1 上方 60mm、開指 %.0fmm" % OPEN_GAP, 2.5, **{qk: qpre, gk: gOpen})
    dn = [(pg + np.array([0, 0, 0.06 * (1 - u)]), Rg) for u in np.linspace(0, 1, 40)]
    qsD, phD, f4 = cart_seg(H, dn, qpre, phpre, "b2 下降到 #1")
    if f4 is not None: FAIL.append("(b) 下降 IK 失敗")
    add("b2 下降到 #1", 1.5, **{qk: qsD})
    add("b3 合指到 %.1fmm" % CLOSE_GAP, 0.5, **{gk: gClose})
    up = [(pg + np.array([0, 0, 0.03 * u]), Rg) for u in np.linspace(0, 1, 15)]
    qsU, phU, f5 = cart_seg(H, up, qsD[-1], phD[-1], "b4 抬 30mm")
    add("b4 抬 30mm", 1.0, **{qk: qsU})
    arc = RJ["arc"]["1"]; HY, HZ = -71.5e-3, 106e-3
    gp = np.array(g1["p"]) * 1e-3 + np.array([0, 0, 0.03]); Rr = arc["R_mm"] * 1e-3
    th0, th1 = math.radians(arc["th0"]), math.radians(arc["th1"])
    arcP = []
    for t in np.linspace(th0, th1, 60):
        pl = np.array([gp[0], HY + Rr * math.cos(t), HZ + Rr * math.sin(t)])
        Rx = rot_axis([1, 0, 0], math.degrees(t - th0))
        arcP.append(((TB @ np.r_[pl, 1])[:3], TB[:3, :3] @ Rx @ Rg_loc))
    qsC, phC, f6 = cart_seg(H, arcP, qsU[-1], phU[-1], "b5 弧線 θ %.0f→%.0f°(半徑 %.0fmm)" % (arc["th0"], arc["th1"], arc["R_mm"]))
    if f6 is not None: FAIL.append("(b) 弧線只走到 %d/%d 點" % (f6, len(arcP)))
    add("b5 沿弧線掀", 4.0 * len(qsC) / len(arcP), **{qk: qsC})
    add("b6 停", 0.7)

# ── 碰撞(幾何)────────────────────────────────────────────
P("\n=== 碰撞檢查(幾何:手臂 collision mesh 取樣點 vs 紙箱 Cube 有號距離;兩臂點對點;桌面)")
def frame_check(qL, qR, gL, gR, lids, contact):
    res = {}; W = {}
    for side, q6, g in (("left", qL, gL), ("right", qR, gR)):
        B = body_fk(side, np.asarray(q6), g, MIM * g); W[side] = {}
        for b, T in B.items():
            if b in PTS: W[side][b] = (T @ np.c_[PTS[b], np.ones(len(PTS[b]))].T).T[:, :3]
    for side in ("left", "right"):
        allp = np.vstack(list(W[side].values()))
        res["table_" + side] = (allp[:, 2].min() - TABLE_Z) * 1e3
        for o in OBB:
            T = lid_T(o["body"], lids[o["body"]]) if o["body"] != "base" else np.eye(4)
            for b, pts in W[side].items():
                d = sdist(pts, o, T).min() * 1e3
                fing = ("gripper_" in b or "carriage_" in b)
                key = ("intended" if (fing and contact.get(side) == o["body"]) else "box") + "_" + side
                if key not in res or d < res[key][0]: res[key] = (d, o["name"], b.rsplit("/", 1)[-1])
    pl = np.vstack(list(W["left"].values())); pr = np.vstack(list(W["right"].values()))
    dd, _ = cKDTree(pl).query(pr, k=1); res["arm_arm"] = dd.min() * 1e3
    return res
def nearest_pair(qL, qR, gL, gR):
    W = {}
    for side, q6, g in (("left", qL, gL), ("right", qR, gR)):
        B = body_fk(side, np.asarray(q6), g, MIM * g)
        for b, T in B.items():
            if b in PTS: W[b] = (T @ np.c_[PTS[b], np.ones(len(PTS[b]))].T).T[:, :3]
    best = None
    for bl in [b for b in W if "follower_left_" in b]:
        tr = cKDTree(W[bl])
        for br in [b for b in W if "follower_right_" in b]:
            d = tr.query(W[br], k=1)[0].min() * 1e3
            if best is None or d < best[0]: best = (d, bl, br)
    return best, {b: (W[b].min(0) * 1e3).round(0).tolist() + (W[b].max(0) * 1e3).round(0).tolist() for b in W}
_np, _bb = nearest_pair(SEG[0]["qL"][0], SEG[0]["qR"][0], SEG[0]["gL"][0], SEG[0]["gR"][0])
P("  home 兩臂最近:%.1f mm %s ↔ %s" % _np)
for b, v in _bb.items(): P("    bbox %s %s" % (b.rsplit("/", 1)[-1], v))
T_ALL = []; t = 0.0
summary = []
for s in SEG:
    worst = {}
    for i in range(s["n"]):
        r = frame_check(s["qL"][i], s["qR"][i], s["gL"][i], s["gR"][i], s["lids"][i], s["contact"])
        T_ALL.append(r)
        for k, v in r.items():
            vv = v[0] if isinstance(v, tuple) else v
            if k not in worst or vv < (worst[k][0] if isinstance(worst[k], tuple) else worst[k]): worst[k] = v
    dur = s["n"] / FPS
    f = lambda k: ("%.1f(%s↔%s)" % worst[k] if isinstance(worst.get(k), tuple) else ("%.1f" % worst[k] if k in worst else "-"))
    col = [k for k in ("box_left", "box_right", "arm_arm", "table_left", "table_right") if k in worst and (worst[k][0] if isinstance(worst[k], tuple) else worst[k]) < 0]
    P("  [%5.1f–%5.1fs] %-34s 左↔箱 %s | 右↔箱 %s | 兩臂 %s | 桌 L%.0f R%.0f | 預期接觸 L %s R %s %s"
      % (t, t + dur, s["name"], f("box_left"), f("box_right"), f("arm_arm"), worst["table_left"], worst["table_right"],
         f("intended_left"), f("intended_right"), "★ 穿入:" + ",".join(col) if col else "OK"))
    summary.append(dict(name=s["name"], t0=t, t1=t + dur, worst={k: v for k, v in worst.items()}, collide=col)); t += dur
P("  (數字 = 最小有號距離 mm,負 = 穿入;括號 = 紙箱部位↔手臂剛體)")
for f_ in FAIL: P("  ⚠ " + f_)
json.dump(dict(segments=summary, fail=FAIL, gap=dict(G0=G0, GK=GK, mimic=MIM)), open(os.path.join(HERE, "data", "peel_traj_%s.json" % TAG), "w"), indent=1, default=lambda o: float(o) if hasattr(o, "__float__") else str(o))
np.savez(os.path.join(HERE, "data", "peel_traj_%s.npz" % TAG), qL=np.array([q for s in SEG for q in s["qL"]]), qR=np.array([q for s in SEG for q in s["qR"]]),
         gL=np.array([g for s in SEG for g in s["gL"]]), gR=np.array([g for s in SEG for g in s["gR"]]),
         lids=np.array([[l[k] for k in ("fxp", "fxn", "fyp", "fyn")] for s in SEG for l in s["lids"]]), fps=FPS)

# ── 播放:set_joint_positions + 錄影 ──────────────────────
from isaacsim.core.api import World
from isaacsim.core.prims import Articulation, RigidPrim
world = World(physics_dt=1 / 120.0, rendering_dt=1 / FPS, stage_units_in_meters=1.0)
cams = []
if not a.no_video:
    from isaacsim.sensors.camera import Camera
    from isaacsim.core.utils.viewports import set_camera_view
    import imageio
    from PIL import Image, ImageDraw, ImageFont
    for i, (eye, tgt) in enumerate((((-0.95, 0.0, 0.62), (0.0, 0.0, 0.16)), ((0.55, -0.55, 0.75), (0.0, 0.05, 0.12)))):
        c = Camera(prim_path="/World/dry_cam%d" % i, resolution=(960, 540), frequency=FPS); cams.append((c, eye, tgt))
world.reset()
ART = Articulation(prim_paths_expr="/World/stationary_ai", name="arms"); ART.initialize()
LR = RigidPrim(prim_paths_expr=BOX + "/f[xy][pn]", name="lids"); LR.initialize()
L6 = RigidPrim(prim_paths_expr=R0 + "/follower_*_link_6", name="l6"); L6.initialize()
lid_order = [str(p).rsplit("/", 1)[-1] for p in LR.prim_paths]; l6_order = [str(p).split("follower_")[1].split("_")[0] for p in L6.prim_paths]
dof = list(ART.dof_names)
P("\nArticulation DOF %d:%s" % (len(dof), dof))
idx = {side: [dof.index("follower_%s_joint_%d" % (side, k)) for k in range(6)] for side in ("left", "right")}
cidx = {side: (dof.index("follower_%s_left_carriage_joint" % side), dof.index("follower_%s_right_carriage_joint" % side)) for side in ("left", "right")}
LT0 = {}
pL0, qL0 = [np.array(x, float) for x in LR.get_world_poses()]
for i, nm in enumerate(lid_order):
    T = np.eye(4); w, x, y, z = qL0[i]; T[:3, :3] = RM.q2R(w, x, y, z); T[:3, 3] = pL0[i]; LT0[nm] = T
for c, eye, tgt in cams:
    c.initialize(); set_camera_view(eye=np.array(eye), target=np.array(tgt), camera_prim_path=c.prim_path)
    cp = UsdGeom.Camera(st.GetPrimAtPath(c.prim_path)); cp.GetFocalLengthAttr().Set(18.0 if c.prim_path.endswith("0") else 20.0)
    cp.GetHorizontalApertureAttr().Set(20.955); cp.GetVerticalApertureAttr().Set(20.955 * 540 / 960); cp.GetClippingRangeAttr().Set(Gf.Vec2f(0.01, 100.0))
try: FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 17)
except Exception: FONT = None
wr = imageio.get_writer(OUT, fps=FPS, codec="libx264", quality=8, pixelformat="yuv420p") if cams else None
def apply(qL, qR, gL, gR, lids):
    J = np.array(ART.get_joint_positions(), float)[0]
    J[idx["left"]] = qL; J[idx["right"]] = qR
    J[cidx["left"][0]] = gL; J[cidx["left"][1]] = MIM * gL; J[cidx["right"][0]] = gR; J[cidx["right"][1]] = MIM * gR
    ART.set_joint_positions(J[None]); ART.set_joint_position_targets(J[None]); ART.set_joint_velocities(np.zeros_like(J)[None])
    ps_, qs_ = [], []
    for nm in lid_order:
        T = lid_T(nm, lids[nm]) @ LT0[nm]; q = Gf.Matrix3d(*T[:3, :3].T.flatten().tolist()).ExtractRotation().GetQuat()
        ps_.append(T[:3, 3]); qs_.append([q.GetReal(), *q.GetImaginary()])
    LR.set_world_poses(positions=np.array(ps_), orientations=np.array(qs_))
# 暖機
s0 = SEG[0]; apply(s0["qL"][0], s0["qR"][0], s0["gL"][0], s0["gR"][0], s0["lids"][0])
for _ in range(15): world.step(render=bool(cams))
k = 0; t = 0.0; maxdev = 0.0; maxjerr = 0.0
for si, s in enumerate(SEG):
    for i in range(s["n"]):
        apply(s["qL"][i], s["qR"][i], s["gL"][i], s["gR"][i], s["lids"][i])
        world.step(render=bool(cams))
        Jr = np.array(ART.get_joint_positions(), float)[0]
        maxjerr = max(maxjerr, np.abs(Jr[idx["left"]] - s["qL"][i]).max(), np.abs(Jr[idx["right"]] - s["qR"][i]).max())
        p6, q6 = [np.array(x, float) for x in L6.get_world_poses()]
        for j, side in enumerate(l6_order):
            fk = ARMS[side]["base_T"] @ RM.fk_np(ARMS[side], s["qL"][i] if side == "left" else s["qR"][i])["link_6"]
            maxdev = max(maxdev, np.linalg.norm(fk[:3, 3] - p6[j]) * 1e3)
        if cams:
            ims = []
            for c, _e, _t in cams:
                rgb = c.get_rgba()
                ims.append(np.asarray(rgb)[:, :, :3] if rgb is not None and rgb.size else np.zeros((540, 960, 3), np.uint8))
            im = Image.fromarray(np.concatenate(ims, 1)); d = ImageDraw.Draw(im)
            r = T_ALL[k]
            txt = "t=%5.2fs  %s\nbox clearance L %.0f / R %.0f mm   arm-arm %.0f mm   gripR %.1f mm" % (
                t, s["name"].encode("ascii", "ignore").decode() or s["name"][:2], r["box_left"][0], r["box_right"][0], r["arm_arm"],
                G0 + GK * s["gR"][i])
            d.rectangle([0, 0, 760, 44], fill=(0, 0, 0)); d.text((6, 3), txt, fill=(255, 255, 255), font=FONT)
            if wr: wr.append_data(np.asarray(im))
        k += 1; t += 1 / FPS
if wr: wr.close()
P("播放 %d 格(%.1f s);PhysX 讀回 vs 指令:關節最大差 %.3f°、link_6 位置 vs numpy FK 最大差 %.2f mm" % (k, t, math.degrees(maxjerr), maxdev))
if cams: P("影片 → %s" % OUT)
app.close()
