#!/usr/bin/env python3
"""reach.py — 抓取點 #1/#2、四片蓋外緣中點(關/開 90°)、掀的弧線 5 點 → 世界座標 → 左右臂各解 IK(Lula)。
    /isaac-sim/python.sh reach.py [--scene .../scene_final.usd]
IK:isaacsim.robot_motion.motion_generation.LulaKinematicsSolver,URDF/描述檔由 robot_model.py 從場景 USD 關節產生。
姿態(A,題目指定):指尖方向 a = −z,開合軸 c = 邊的水平外法線 u;再繞邊切線 t 俯仰「邊坡度」⇒ a = −n(布面法線)、c = 布面內的外向。
姿態(B,探針模型對照):開合軸 = 布面法線 n(上下夾布厚度)、指尖沿 −(布面外向)插入。
平行夾爪 c 與 −c 等價,兩個都解,取最好。奇異度 = tcp 6x6 Jacobian 最小奇異值 σmin 與 manipulability √det(JJᵀ)。
輸出 data/reach.json(peel_traj.py 讀)、logs/reach.log。"""
import os, sys, json, math, argparse, functools, builtins
print = functools.partial(builtins.print, flush=True)
ap = argparse.ArgumentParser()
ap.add_argument("--scene", default="/isaac-sim/test_scripts/manip_fr3/handoff_20261002/scene_final.usd")
ap.add_argument("--box", default="/World/Packed/Box")
ap.add_argument("--npz", default="/isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/soft/s2/wrap.npz")  # 只讀
ap.add_argument("--place", default=None, help="覆寫紙箱:dx,dy,yaw_deg(相對場景現值,mm/°),做擺放搜尋用")
ap.add_argument("--quiet", action="store_true")
a = ap.parse_args()
from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
import numpy as np
import omni.usd
from pxr import Usd, UsdGeom, Gf
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import robot_model as RM
from isaacsim.robot_motion.motion_generation import LulaKinematicsSolver
os.makedirs(os.path.join(HERE, "data"), exist_ok=True); os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
LOG = open(os.path.join(HERE, "logs", "reach.log" if not a.place else "reach_place.log"), "w")
def P(*s):
    t = " ".join(str(x) for x in s); print(t); LOG.write(t + "\n"); LOG.flush()

omni.usd.get_context().open_stage(a.scene)
st = omni.usd.get_context().get_stage()
xc = UsdGeom.XformCache()
TB = np.array(xc.GetLocalToWorldTransform(st.GetPrimAtPath(a.box))).T     # 箱局部 → 世界
if a.place:
    dx, dy, dyaw = [float(v) for v in a.place.split(",")]
    Rz = np.eye(4); c, s = math.cos(math.radians(dyaw)), math.sin(math.radians(dyaw)); Rz[:2, :2] = [[c, -s], [s, c]]
    ctr = TB[:3, 3].copy(); Tm = np.eye(4); Tm[:3, 3] = ctr + np.array([dx, dy, 0]) * 1e-3
    Ti = np.eye(4); Ti[:3, 3] = -ctr
    TB = Tm @ Rz @ Ti @ TB
P("紙箱 %s 箱局部→世界:原點 %s mm、局部 x 軸 → 世界 %s" % (a.box, (TB[:3, 3] * 1e3).round(1).tolist(), TB[:3, 0].round(3).tolist()))
def W(p_mm):   # 箱局部 mm → 世界 m
    return (TB @ np.r_[np.asarray(p_mm, float) * 1e-3, 1])[:3]
def Wv(v):
    return TB[:3, :3] @ np.asarray(v, float)

# ── 手臂模型 ───────────────────────────────────────────────
ARMS = {}
for side in ("left", "right"):
    m = RM.build(st, side, os.path.join(HERE, "data"))
    sol = LulaKinematicsSolver(robot_description_path=m["desc"], urdf_path=m["urdf"])
    bT = m["base_T"]; q = Gf.Matrix3d(*bT[:3, :3].T.flatten().tolist()).ExtractRotation().GetQuat()
    sol.set_robot_base_pose(bT[:3, 3], np.array([q.GetReal(), *q.GetImaginary()]))
    sol.set_default_position_tolerance(0.001); sol.set_default_orientation_tolerance(0.01)
    import lula; sol.bfgs_cspace_limit_biasing = lula.CyclicCoordDescentIkConfig.CSpaceLimitBiasing.ENABLE
    rng = np.random.default_rng(0 if side == "left" else 1)
    lo = np.array([l for l, h in m["lims"]]); hi = np.array([h for l, h in m["lims"]])
    sol.set_default_cspace_seeds(lo + (hi - lo) * rng.uniform(0.05, 0.95, (40, 6)))
    # FK 自檢:q=0 時 link_6 / ee_tip 與 USD 一致?
    q0 = np.zeros(6)
    fk = RM.fk_np(m, q0)
    l6w = bT @ fk["link_6"]; usd_l6 = RM.world(st, "%s/follower_%s_link_6" % (RM.ROOT, side))
    p_l, R_l = sol.compute_forward_kinematics("ee_tip", q0)
    usd_ee = RM.world(st, "%s/follower_%s_ee_gripper_link" % (RM.ROOT, side))
    P("[%s] Lula 關節 %s;FK 自檢 q=0:numpy link_6 vs USD 差 %.3f mm / %.4f rad;Lula ee_tip vs USD 差 %.3f mm"
      % (side, sol.get_joint_names(), np.linalg.norm(l6w[:3, 3] - usd_l6[:3, 3]) * 1e3,
         np.linalg.norm(l6w[:3, :3] - usd_l6[:3, :3]), np.linalg.norm(p_l - usd_ee[:3, 3]) * 1e3))
    m.update(sol=sol, lo=lo, hi=hi); ARMS[side] = m

def R_from(a_, c_):
    a_ = a_ / np.linalg.norm(a_); c_ = c_ - a_ * (c_ @ a_); c_ /= np.linalg.norm(c_)
    return np.column_stack([a_, c_, np.cross(a_, c_)])
def quat(R):
    q = Gf.Matrix3d(*R.T.flatten().tolist()).ExtractRotation().GetQuat(); return np.array([q.GetReal(), *q.GetImaginary()])

def wrap_lim(q, lo, hi):
    q = np.array(q, float)
    for i in range(len(q)):
        for k in (-1, 1):
            if not (lo[i] - 1e-6 <= q[i] <= hi[i] + 1e-6) and lo[i] - 1e-6 <= q[i] + k * 2 * math.pi <= hi[i] + 1e-6:
                q[i] += k * 2 * math.pi
    return q

def eval_q(side, qs, pos, R):
    m = ARMS[side]
    T = m["base_T"] @ RM.fk_np(m, qs)["tcp"]
    perr = np.linalg.norm(T[:3, 3] - pos) * 1e3
    oerr = math.degrees(math.acos(max(-1, min(1, (np.trace(T[:3, :3].T @ R) - 1) / 2))))
    J = RM.jac_np(m, qs); sv = np.linalg.svd(J, compute_uv=False)
    inlim = bool(np.all(qs >= m["lo"] - 1e-4) and np.all(qs <= m["hi"] + 1e-4))
    marg = float(np.min(np.minimum(qs - m["lo"], m["hi"] - qs)))
    return dict(ok=perr < 2 and oerr < 2 and inlim, q=qs.tolist(), perr=perr, oerr=oerr, smin=float(sv[-1]),
                manip=float(np.sqrt(max(0, np.linalg.det(J @ J.T)))), inlim=inlim, marg_deg=math.degrees(marg))

NSEED = 24
PHIS = [0, 10, -10, 20, -20, 30, -30, 45, -45, 60, -60, 75, -75, 90, -90]
def rot_about(R, axis_col, deg):
    k = R[:, axis_col]; th = math.radians(deg); K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return (np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K) @ R
def solve_relaxed(side, pos, Rt, warm=None, nseed=8):
    """放寬:開合軸 c 不變,指尖方向繞 c 轉 φ(手腕俯仰偏離規格);回傳 |φ| 最小的成功解。"""
    global NSEED
    old = NSEED; NSEED = nseed
    try:
        for ph in PHIS:
            r = solve(side, pos, rot_about(Rt, 1, ph), warm)
            if r["ok"]: r["phi"] = ph; return r
        r["phi"] = None; return r
    finally:
        NSEED = old
def solve_pos(side, pos, warm=None):
    m = ARMS[side]; best = None; rng = np.random.default_rng(3)
    for w in [warm] * (warm is not None) + [m["lo"] + (m["hi"] - m["lo"]) * rng.uniform(0.05, 0.95, 6) for _ in range(16)]:
        qs, ok = m["sol"].compute_inverse_kinematics("tcp", pos, None, warm_start=np.asarray(w))
        qs = wrap_lim(qs, m["lo"], m["hi"])
        T = m["base_T"] @ RM.fk_np(m, qs)["tcp"]; perr = np.linalg.norm(T[:3, 3] - pos) * 1e3
        inl = bool(np.all(qs >= m["lo"] - 1e-4) and np.all(qs <= m["hi"] + 1e-4))
        if best is None or (inl and perr < best[0]): best = (perr if inl else 1e9, qs)
    return best[0] < 2, best[0]

def solve(side, pos, Rt, warm=None):
    """Lula CCD+BFGS;多組起點(warm + 24 個隨機),角度可 ±2π 包回限位;取 (成功, σmin) 最好的。"""
    m = ARMS[side]; best = None; rng = np.random.default_rng(7)
    starts = ([warm] if warm is not None else []) + [m["lo"] + (m["hi"] - m["lo"]) * rng.uniform(0.05, 0.95, 6) for _ in range(NSEED)]
    for flip in (1, -1):
        R = Rt.copy()
        if flip < 0: R[:, 1] *= -1; R[:, 2] *= -1          # 繞指尖軸轉 180°(平行夾爪對稱)
        for k, w in enumerate(starts):
            qs, ok = m["sol"].compute_inverse_kinematics("tcp", pos, quat(R), warm_start=np.asarray(w))
            r = eval_q(side, wrap_lim(qs, m["lo"], m["hi"]), pos, R); r.update(flip=flip, lula_ok=bool(ok))
            key = (r["ok"], r["smin"] if r["ok"] else -r["perr"] - r["oerr"] + min(0, r["marg_deg"]))
            if best is None or key > best[0]: best = (key, r)
            if r["ok"] and warm is not None and k == 0: return r          # 弧線:沿用前一點的分支,保持連續
    return best[1]

# ── 目標 ───────────────────────────────────────────────────
targets = []
# 抓取點(箱局部 mm),方向從 vol 的 wrap.npz 量(只讀)
G = {1: dict(v=27, p=(112.9, -6.9, 123.6), slope=33.3, u=(-0.18, 0.98)),
     2: dict(v=11, p=(-84.7, 2.1, 82.0), slope=17.5, u=(0.11, 0.99))}
try:
    d = np.load(a.npz); OFF = np.array([0.0, 0.200, 0.097]); NX = 35; N1 = (NX + 1) ** 2
    Pn = (d["snap_end"] - OFF) * 1e3; MID = (Pn[:N1] + Pn[N1:]) / 2
    for k, g in G.items():
        v = g["v"]; so = MID[v] - MID[v + NX + 1]; so /= np.linalg.norm(so)
        i0, j0 = v % (NX + 1), v // (NX + 1)
        nb = [jj * (NX + 1) + ii for jj in range(j0, j0 + 3) for ii in range(max(0, i0 - 2), min(NX, i0 + 2) + 1)]
        Q = MID[nb] - MID[nb].mean(0); n = np.linalg.svd(Q)[2][-1]       # 局部平面擬合(~30mm 內 15 點)的法線
        n = n if n[2] > 0 else -n
        so = so - n * (so @ n); so /= np.linalg.norm(so)                 # 外向投影到擬合平面
        tt = np.cross(n, so)
        g.update(so=so, t=tt, n=n, p_npz=MID[v])
        P("抓取點 #%d:npz 中面 %s mm(log %s);布面外向 s=%s(仰角 %.1f°,log 坡度 %.1f°);擬合法線 n=%s(平面殘差 rms %.1f mm)"
          % (k, MID[v].round(1).tolist(), g["p"], so.round(2).tolist(), math.degrees(math.asin(so[2])), g["slope"], n.round(2).tolist(), float(np.sqrt(np.mean((Q @ n) ** 2)))))
except Exception as e:
    P("⚠ 讀 npz 失敗 %s,用 log 的 u + 坡度(假設往外上升)" % e)
    for k, g in G.items():
        u = np.r_[g["u"], 0]; u /= np.linalg.norm(u); th = math.radians(g["slope"])
        so = math.cos(th) * u + math.sin(th) * np.array([0, 0, 1.0]); tt = np.cross([0, 0, 1.0], u)
        g.update(so=so, t=tt, n=np.cross(tt, so))
for k, g in G.items():
    pw = W(g["p"])
    # A:c = 布邊外向(含坡度 = log 的仰角);a = 在含 c 的鉛直面內、垂直 c、朝下(= −z 俯仰坡度)
    so = g["so"]; av = -(np.array([0, 0, 1.0]) - so[2] * so); av /= np.linalg.norm(av); g["a"] = av
    targets.append(dict(name="grasp#%d A" % k, pos=pw, R=R_from(Wv(av), Wv(so)), group="grasp"))
    targets.append(dict(name="grasp#%d B(探針)" % k, pos=pw, R=R_from(Wv(-so), Wv(-av)), group="grasp_B"))
    targets.append(dict(name="grasp#%d 上方 60mm" % k, pos=pw + np.array([0, 0, 0.06]), R=R_from(Wv(av), Wv(so)), group="pre"))

# 蓋子:從 USD 量蓋板網格,外緣中點 = 離鉸鏈軸最遠那排頂點的中點
meta = json.load(open("/isaac-sim/test_scripts/manip_fr3/handoff_20260929/work/carton.meta.json"))["derived"]
IX, IY, HLO, HUP = meta["wall_inner_x"], meta["wall_inner_y"], meta["lower_hinge_z"], meta["upper_hinge_z"]
LIDS = [("fxp", (IX, 0, HLO), (0, 1, 0)), ("fxn", (-IX, 0, HLO), (0, -1, 0)),
        ("fyp", (0, IY, HUP), (-1, 0, 0)), ("fyn", (0, -IY, HUP), (1, 0, 0))]
TBinv = np.linalg.inv(TB)
def rod(v, h, ax, deg):
    ax = np.asarray(ax, float); th = math.radians(deg); r = np.asarray(v, float) - h
    return h + r * math.cos(th) + np.cross(ax, r) * math.sin(th) + ax * (ax @ r) * (1 - math.cos(th))
LIDINFO = {}
BBC = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
PRIMTYPES = set()
for nm, h, ax in LIDS:
    pts = []
    for p in Usd.PrimRange(st.GetPrimAtPath(a.box + "/" + nm)):
        if p.IsA(UsdGeom.Gprim):
            M = np.array(xc.GetLocalToWorldTransform(p)).T
            if p.IsA(UsdGeom.Mesh):
                v = np.array(UsdGeom.Mesh(p).GetPointsAttr().Get(), float)
            else:   # Cube 等:未變換 bbox 的 8 角
                rg = BBC.ComputeUntransformedBound(p).GetRange(); mn, mx = np.array(rg.GetMin()), np.array(rg.GetMax())
                v = np.array([[x, y, z] for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])])
            vw = (M @ np.c_[v, np.ones(len(v))].T).T
            if a.place:  # 場景值 → 位移後
                T0 = np.array(xc.GetLocalToWorldTransform(st.GetPrimAtPath(a.box))).T
                vw = (TB @ np.linalg.inv(T0) @ vw.T).T
            pts.append((TBinv @ vw.T).T[:, :3])
    pts = np.vstack(pts); h = np.array(h); ax = np.array(ax, float)
    r = pts - h; dist = np.linalg.norm(r - np.outer(r @ ax, ax), axis=1)
    edge = pts[dist > dist.max() - 0.002]; along = edge @ ax
    mid = edge.mean(0); mid = mid - ax * ((mid - h) @ ax)    # 外緣那排頂點的中心,沿鉸鏈方向投影到寬度中點
    ctr = pts.mean(0)
    sgn = 1.0 if rod(ctr, h, ax, 90)[2] >= rod(ctr, h, ax, -90)[2] else -1.0
    LIDINFO[nm] = dict(h=h, ax=ax, sgn=sgn, mid=mid, L=float(dist.max()))
    for deg in (0, 90):
        pl = rod(mid, h, ax, sgn * deg)
        # 夾法:指尖朝 −z;開合軸 = 蓋板在該點的法線(蓋板繞軸轉後)的水平分量;關著時(蓋平躺)開合軸取邊法線(水平、垂直於鉸鏈)
        rr = pl - h; rr -= ax * (rr @ ax); en = rr / np.linalg.norm(rr)       # 從鉸鏈指向外緣
        if deg == 0: c_ = np.array([en[0], en[1], 0.0])
        else: c_ = np.cross(ax, en); c_[2] = 0
        targets.append(dict(name="lid %s %s" % (nm, "關" if deg == 0 else "開90°"), pos=W(pl * 1e3), R=R_from(Wv([0, 0, -1.0]), Wv(c_)), group="lid",
                            local_mm=(pl * 1e3).round(1).tolist()))
    P("蓋 %s:鉸鏈 %s mm,外緣中點(關)%s mm,板長 %.1f mm,開方向 sgn %+d" % (nm, (h * 1e3).round(1).tolist(), (mid * 1e3).round(1).tolist(), dist.max() * 1e3, sgn))

# 掀的弧線(抓取點 #1):繞 yn 折線(箱局部沿 x、y=−71.5、z=106)轉;先抬 30mm,半徑 = 抬後到鉸點距離(≤ 0.9×材料長 178.5)
HY, HZ, LMAT = -71.5, 106.0, 250.0 - 71.5
ARC = {}
for k in (1, 2):
    g = G[k]; gp = np.array(g["p"]) + np.array([0, 0, 30.0])
    th0 = math.atan2(gp[2] - HZ, gp[1] - HY); R = math.hypot(gp[1] - HY, gp[2] - HZ)
    # 終點:翻到折線外側,但要高過 yn 牆頂(126.5)+ 30mm(y < −112 時)
    ths = np.linspace(th0, math.radians(175), 400)
    ok = [(HY + R * math.cos(t) > -112 + 10) or (HZ + R * math.sin(t) > 126.5 + 30) for t in ths]
    th1 = ths[np.argmin(ok)] if not all(ok) else ths[-1]
    pts = []
    for f in np.linspace(0, 1, 5):
        t = th0 + (th1 - th0) * f
        pl = np.array([gp[0], HY + R * math.cos(t), HZ + R * math.sin(t)])
        dth = t - th0
        Rx = np.array([[1, 0, 0], [0, math.cos(dth), -math.sin(dth)], [0, math.sin(dth), math.cos(dth)]])
        Rl = Rx @ R_from(g["a"], g["so"])
        pts.append(dict(local=pl.round(1).tolist(), deg=math.degrees(t)))
        targets.append(dict(name="arc#%d %.0f%% (%.0f°)" % (k, f * 100, math.degrees(t)), pos=W(pl), R=TB[:3, :3] @ Rl, group="arc%d" % k, local_mm=pl.round(1).tolist()))
    ARC[k] = dict(R_mm=R, th0=math.degrees(th0), th1=math.degrees(th1), Rmax=0.9 * LMAT, pts=pts, lift=30.0)
    P("弧線 #%d:鉸點 (x, %.1f, %.1f) mm、半徑 %.1f mm(上限 0.9×%.1f = %.1f)、θ %.0f° → %.0f°"
      % (k, HY, HZ, R, LMAT, 0.9 * LMAT, math.degrees(th0), math.degrees(th1)))

# ── 解 ────────────────────────────────────────────────────
P("\n%-22s | %-24s | %-38s | %-38s | 建議" % ("目標", "世界 mm", "左臂 IK(ok/誤差/σmin/限位餘裕)", "右臂 IK"))
res = []
warm = {"left": None, "right": None}
for T in targets:
    row = dict(name=T["name"], group=T["group"], pos_mm=(T["pos"] * 1e3).round(1).tolist(), R=T["R"].tolist(), local_mm=T.get("local_mm"))
    for side in ("left", "right"):
        w = warm[side] if T["group"].startswith("arc") else None
        r = solve(side, T["pos"], T["R"], w)
        r["phi"] = 0 if r["ok"] else None
        if not r["ok"] and T["group"] != "grasp_B":
            r2 = solve_relaxed(side, T["pos"], T["R"], w)
            if r2["ok"]: r = r2
        r["pos_reach"] = solve_pos(side, T["pos"], w)[0] if not r["ok"] else True
        if T["group"].startswith("arc") and r["ok"]: warm[side] = np.array(r["q"])
        row[side] = r
    L, Rr = row["left"], row["right"]
    cand = [s for s in ("left", "right") if row[s]["ok"]]
    row["best"] = max(cand, key=lambda s: (row[s]["phi"] == 0, -abs(row[s]["phi"]), row[s]["smin"])) if cand else None
    def f(r):
        if r["ok"]:
            return "OK%s σ%.3f √det%.4f 餘%.0f°" % ("" if r["phi"] == 0 else "(φ%+d°)" % r["phi"], r["smin"], r["manip"], r["marg_deg"])
        return "NG(差%.0fmm/%.1f°;只要位置:%s)" % (r["perr"], r["oerr"], "可" if r["pos_reach"] else "不可")
    P("%-22s | %-24s | %-40s | %-40s | %s" % (T["name"], row["pos_mm"], f(L), f(Rr), {"left": "左", "right": "右", None: "兩臂都不行"}[row["best"]]))
    res.append(row)
json.dump(dict(scene=a.scene, TB=TB.tolist(), rows=res, arc=ARC, lids={k: {kk: (vv.tolist() if hasattr(vv, "tolist") else vv) for kk, vv in v.items()} for k, v in LIDINFO.items()},
               grasp={k: {kk: (vv.tolist() if hasattr(vv, "tolist") else vv) for kk, vv in g.items()} for k, g in G.items()}),
          open(os.path.join(HERE, "data", "reach.json" if not a.place else "reach_place.json"), "w"), indent=1,
          default=lambda o: o.tolist() if hasattr(o, "tolist") else (bool(o) if isinstance(o, np.bool_) else float(o)))
P("\n註:φ = 指尖方向繞開合軸偏離規格姿態的角度(0 = 完全照規格);σ = tcp 6x6 Jacobian 最小奇異值(位置 m、角度 rad 混合單位);√det = manipulability;餘 = 離最近關節限位")
app.close()
