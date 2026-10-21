#!/usr/bin/env python3
"""cloth_iface.py — wrap.npz → 手臂端介面 JSON(arm/INTERFACE.md §2 六項)。純 CPU(numpy + trimesh)。

  cloth_iface.py export <wrap.npz> [--snap end] [--yaw 270] [--off 0,0.200,0.097] [--top 5] -o iface.json
      另寫 iface.npz(同名):mid/top/bot 的 L/V/S 三座標(mm)、flat、side、mug_L
  cloth_iface.py check iface.json
  cloth_iface.py --selftest
座標:L 箱局部(mm);V = L + OFF;S = T + Rz(yaw)·L,T = (−20,0,20) mm(方向只乘 Rz)。
"""
import sys, os, json, argparse
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
NX_DEF, CX_DEF, CY_DEF = 35, 0.08463, 0.07150
OFF_DEF = (0.0, 0.200, 0.097)
BOX = dict(IX=0.132, IY=0.112, ZFLOOR=0.003, ZOBST=0.135)
T_S = np.array([-20.0, 0.0, 20.0])
SIDES = ["base", "xp", "xn", "yp", "yn"]
# INTERFACE.md §3 常數(手抄)
GRIP_LIMITS = dict(
    spec_pose="指尖朝 -z 並繞邊切線俯仰『邊坡度』;開合軸 = 布邊外向 s",
    descend_grip_lift=dict(phi_deg=0, psi_deg=0),
    arc_phi_deg=dict(nominal=[0, 35], allowed=[-45, 45]),
    arc_psi_deg=dict(nominal=[-15, 0], allowed=[-15, 15]),
    finger_open_mm=21.0, finger_close_mm=4.5, carriage_q_open_mm=10.5, carriage_q_close_mm=2.2,
    finger_gap_formula="0.1 mm + 2*q",
    descend=dict(dist_mm=60, time_s=1.5, speed_mm_s=40, preapproach="抓點正上方 60 mm"),
    close_time_s=0.5, lift=dict(dist_mm=30, time_s=1.0, dir="vertical"),
    arc=dict(hinge_L_mm=[None, -71.5, 106], r_from_mm=80, r_to_mm=60, R_mm=60, theta_deg=[36, 100],
             final_lift_L_z_mm=168.5, total_s=4.5, n_pts=67),
    tcp_back_mm=10, collision=dict(arm_vs_carton_pen_mm=0.5, arm_arm_min_mm=10),
    finger_box_mm=[36, 70, 60], min_wall_clear_mm=30)

def rz(yaw):
    c, s = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])

class Frames:
    def __init__(s, off_m, yaw): s.off = np.asarray(off_m) * 1e3; s.R = rz(yaw); s.yaw = yaw
    def pt(s, L):
        L = np.asarray(L, float); return dict(L=r1(L), V=r1(L + s.off), S=r1(T_S + L @ s.R.T))
    def vec(s, d):
        d = np.asarray(d, float); return dict(L=r4(d), V=r4(d), S=r4(d @ s.R.T))

def r1(a): return np.round(np.asarray(a, float), 2).tolist()
def r4(a): return np.round(np.asarray(a, float), 4).tolist()

# ---------- 分片 / 折線(只用平板索引) ----------
def side_of(F2, CX, CY):
    out = []
    for fx, fy in F2:
        if abs(fx) <= CX and abs(fy) <= CY: out.append("base"); continue
        sx = max(0.0, abs(fx) - CX); sy = max(0.0, abs(fy) - CY)
        out.append(("yp" if fy > 0 else "yn") if sy >= sx else ("xp" if fx > 0 else "xn"))
    return np.array(out)

def grid_edges(NX):
    E = []
    for j in range(NX + 1):
        for i in range(NX + 1):
            v = j * (NX + 1) + i
            if i < NX: E.append((v, v + 1))
            if j < NX: E.append((v, v + NX + 1))
    return np.array(E)

def fold_lines(M, F2, SIDE, NX):
    """M: 中面 (N1,3) mm。各相鄰片對的交界 = 跨片網格邊的中點;端點取沿交界方向(flat 主軸)兩極。"""
    E = grid_edges(NX); out = []
    a, b = SIDE[E[:, 0]], SIDE[E[:, 1]]
    pairs = sorted({tuple(sorted(p)) for p in zip(a[a != b], b[a != b])})
    for p in pairs:
        sel = E[((a == p[0]) & (b == p[1])) | ((a == p[1]) & (b == p[0]))]
        fm = (F2[sel[:, 0]] + F2[sel[:, 1]]) / 2; mm = (M[sel[:, 0]] + M[sel[:, 1]]) / 2
        c = fm.mean(0); _, _, vt = np.linalg.svd(fm - c); t = (fm - c) @ vt[0]
        i0, i1 = int(np.argmin(t)), int(np.argmax(t))
        out.append(dict(pair=list(p), n_edges=int(len(sel)), flat_ends=[fm[i0], fm[i1]], ends=[mm[i0], mm[i1]],
                        z_median=float(np.median(mm[:, 2])), z_min=float(mm[:, 2].min()), z_max=float(mm[:, 2].max())))
    return out

# ---------- 幾何 ----------
def plane_fit(M, F2, v, rad_flat):
    nb = np.where(np.linalg.norm(F2 - F2[v], axis=1) <= rad_flat)[0]
    P = M[nb]; c = P.mean(0); _, sv, vt = np.linalg.svd(P - c); n = vt[2]
    if n[2] < 0: n = -n
    res = (P - c) @ n
    return n, float(np.sqrt((res ** 2).mean())), float(np.abs(res).max()), int(len(nb))

def mug_info(mug, mugrest, faces_n):
    """mugrest:杯子自身框(原點中心)。Kabsch 求 R,杯口 = rest 中 z 端無中心頂點的一側,杯耳 = rest 中最外徑頂點方向。"""
    if mugrest.shape != mug.shape: return None
    a = mugrest - mugrest.mean(0); b = mug - mug.mean(0)
    U, _, Vt = np.linalg.svd(a.T @ b); D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))]); R = (U @ D @ Vt).T
    r = np.hypot(a[:, 0], a[:, 1]); zl, zh = a[:, 2].min(), a[:, 2].max()
    ctr_lo = ((a[:, 2] < zl + 0.002) & (r < 0.01)).sum(); ctr_hi = ((a[:, 2] > zh - 0.002) & (r < 0.01)).sum()
    mouth = np.array([0, 0, 1.0 if ctr_hi < ctr_lo else -1.0])
    far = a[r > 0.95 * r.max()]; h = far[:, :2].mean(0); h = np.array([h[0], h[1], 0]); h /= np.linalg.norm(h) + 1e-12
    return dict(R=R, mouth=R @ mouth, handle=R @ h, ambiguous=bool(ctr_hi == ctr_lo))

# ---------- export ----------
def export(a):
    import trimesh, grasp_plan as GP
    d = np.load(a.npz)
    key = "snap_" + a.snap if "snap_" + a.snap in d.files else a.snap
    off = np.array([float(x) for x in a.off.split(",")]); fr = Frames(off, a.yaw)
    P = d[key] - off; N1 = P.shape[0] // 2; NX = int(round(np.sqrt(N1))) - 1
    FLAT = d["flat"]; F2 = FLAT[:N1, :2]
    topfirst = FLAT[0, 2] > FLAT[N1, 2]
    TOP, BOT = (P[:N1], P[N1:]) if topfirst else (P[N1:], P[:N1])
    M = (P[:N1] + P[N1:]) / 2
    mk = "snapmug_" + a.snap if "snapmug_" + a.snap in d.files else "mug"
    MUG = d[mk] - off
    mf = trimesh.load(os.path.join(HERE, "mug.stl")).faces
    S = GP.setup(FLAT, NX, a.cx, a.cy, mf)
    SIDE = S["SIDE"]; assert (SIDE == side_of(F2, a.cx, a.cy)).all()
    Mmm = M * 1e3
    # 1
    snap_t = None
    meta = dict(src=os.path.abspath(a.npz), snap_key=key, snap_t=snap_t, NX=NX, N_vert=int(N1), N_tet_nodes=int(P.shape[0]),
                CX_mm=a.cx * 1e3, CY_mm=a.cy * 1e3, OFF_m=off.tolist(), yaw_deg=a.yaw, units="mm",
                OFF_source="CLI --off(npz 無此欄)", top_layer="first" if topfirst else "second",
                frames="L=箱局部; V=L+OFF; S=T+Rz(yaw)L, T=(-20,0,20)")
    # 2
    counts = {s: int((SIDE == s).sum()) for s in SIDES}
    folds = fold_lines(Mmm, F2 * 1e3, SIDE, NX)
    fold_js = []
    for f in folds:
        fold_js.append(dict(pair=f["pair"], n_edges=f["n_edges"], flat_ends_mm=r1(f["flat_ends"]),
                            ends=[fr.pt(e) for e in f["ends"]], z_median_L=round(f["z_median"], 2),
                            z_range_L=[round(f["z_min"], 2), round(f["z_max"], 2)]))
    bends = {}
    for sd in ("yn", "yp"):
        h = GP.hinge(P, sd)
        bends[sd] = dict(y_L=round(h[3] * 1e3, 2), z_L=round(h[4] * 1e3, 2), n_cols=h[5],
                         note="片從側面轉向杯頂的實際彎折處(grasp_plan.hinge 各欄中位)")
    # 3
    rows = []
    for sd in ("yn", "yp"):
        rows += GP.rank(P, MUG, sd, BOX)
    rows.sort(key=lambda r: (-int(r["ok"]), -(int(r["ok_a"]) + int(r["ok_b"])), -r["gap"], -r["dwall"]))
    grasps = []
    for k, r in enumerate(rows[:a.top]):
        v = r["v"]; R, slope = GP.frame(P, v)
        n, rms, rmax, nn = plane_fit(Mmm, F2 * 1e3, v, a.fit_r)
        n2, rms2, rmax2, nn2 = plane_fit(Mmm, F2 * 1e3, v, a.fit_r * 2)
        grasps.append(dict(rank=k + 1, v=v, side=r["side"], kind=r["kind"], pos=fr.pt(r["p"]),
                           edge_tangent=fr.vec(R[:, 0]), edge_out_s=fr.vec(R[:, 1]), edge_slope_deg=round(slope, 2),
                           frame_normal=fr.vec(R[:, 2]),
                           fit_normal=fr.vec(n), fit=dict(r_flat_mm=a.fit_r, n_pts=nn, rms_mm=round(rms, 3), max_mm=round(rmax, 3)),
                           fit_normal_wide=fr.vec(n2), fit_wide=dict(r_flat_mm=a.fit_r * 2, n_pts=nn2, rms_mm=round(rms2, 3), max_mm=round(rmax2, 3)),
                           thick_mm=round(r["thick"], 2), gap_below_mm=round(r["gap"], 2), dwall_mm=round(r["dwall"], 2),
                           approach=fr.vec([0, 0, -1.0]), preapproach=fr.pt(np.asarray(r["p"]) + [0, 0, 60]),
                           opening_mm=dict(approach=21.0, close=4.5, need_min=round(r["thick"] + 2 * 3.0, 2)),
                           checks=dict(a_pressed=r["a"], b_sweep=list(r["b"]), ok_a=r["ok_a"], ok_b=r["ok_b"], ok_c=r["ok_c"], ok=r["ok"]),
                           warn=(["dwall<30mm(指寬會碰牆/蓋)"] if r["dwall"] < 30 else [])))
    # 4
    mi = mug_info(MUG, d["mugrest"], None) if "mugrest" in d.files else None
    Mm = MUG * 1e3; lo, hi = Mm.min(0), Mm.max(0)
    mug_js = dict(key=mk, bbox_min=fr.pt(lo), bbox_max=fr.pt(hi), center=fr.pt((lo + hi) / 2), centroid=fr.pt(Mm.mean(0)),
                  bbox_S_note="bbox_min/max 的 S 只是兩角點轉換,非 S 軸對齊 bbox")
    if mi:
        mug_js.update(mouth_dir=fr.vec(mi["mouth"]), handle_dir=fr.vec(mi["handle"]), R_rest_to_L=r4(mi["R"]),
                      mouth_ambiguous=mi["ambiguous"], note="杯口/杯耳由 mugrest(杯自身框)推,Kabsch 對齊")
    # 5,6
    lids = dict(convention="lid_pose: 0=關, +=開(deg)", fxp=None, fxn=None, fyp=None, fyn=None,
                status="npz 無蓋角欄位 → null(見 todo)")
    traj = dict(status="npz 只有 traj_t/traj_tet/traj_mug,無 tcp 位置/夾指姿態 → null", t=None, tcp_L=None, quat_L=None,
                traj_t_range=[float(d["traj_t"][0]), float(d["traj_t"][-1])] if "traj_t" in d.files and len(d["traj_t"]) else None)
    todo = ["OFF(實際 OFF_IN+MOVE)", "NX/CX/CY", "snap 時間(snap_t_<name>)", "lid_deg_<snap>(fxp,fxn,fyp,fyn)",
            "grip_t / grip_tcp (T,3) / grip_quat (T,4) / grip_open (T,)", "top/bot 層索引(TOP,BOT)"]
    out = dict(meta=meta, side_counts=counts, side=SIDE.tolist(), folds=fold_js, bends=bends,
               grasps=grasps, mug=mug_js, lids=lids, grip_traj=traj, grip_limits=GRIP_LIMITS,
               box=dict(IX_mm=132, IY_mm=112, ZFLOOR_mm=3, ZOBST_mm=135), todo_wrap_vol=todo)
    json.dump(out, open(a.o, "w"), indent=1, ensure_ascii=False)
    def tri(X): X = X * 1e3; return X, X + off * 1e3, T_S + X @ fr.R.T
    z = {}
    for nm, X in (("mid", M), ("top", TOP), ("bot", BOT)):
        z[nm + "_L"], z[nm + "_V"], z[nm + "_S"] = tri(X)
    np.savez_compressed(os.path.splitext(a.o)[0] + ".npz", flat=F2 * 1e3, side=SIDE, NX=NX, mug_L=Mm, **z)
    summary(out)

def summary(o):
    print("snap", o["meta"]["snap_key"], "N", o["meta"]["N_vert"], "counts", o["side_counts"])
    for g in o["grasps"][:3]:
        print("  #%d v%d %s L%s S%s slope %.1f gap %.1f fit rms %.2f/max %.2f (wide %.2f) ok %s" % (
            g["rank"], g["v"], g["side"], g["pos"]["L"], g["pos"]["S"], g["edge_slope_deg"], g["gap_below_mm"],
            g["fit"]["rms_mm"], g["fit"]["max_mm"], g["fit_wide"]["rms_mm"], g["checks"]["ok"]))
    for f in o["folds"]:
        print("  fold %-9s L %s → %s z_med %.1f" % ("-".join(f["pair"]), f["ends"][0]["L"], f["ends"][1]["L"], f["z_median_L"]))
    print("  bends", o["bends"])

# ---------- check ----------
def check(path):
    o = json.load(open(path)); z = np.load(os.path.splitext(path)[0] + ".npz"); M = z["mid_L"]
    b = o["box"]; R = rz(o["meta"]["yaw_deg"]); off = np.array(o["meta"]["OFF_m"]) * 1e3; fails = []
    for g in o["grasps"]:
        p = np.array(g["pos"]["L"])
        if not (abs(p[0]) <= b["IX_mm"] and abs(p[1]) <= b["IY_mm"] and p[2] >= b["ZFLOOR_mm"]): fails.append("grasp v%d 出內腔" % g["v"])
        for k in ("edge_tangent", "edge_out_s", "frame_normal", "fit_normal"):
            for fk in "LVS":
                if abs(np.linalg.norm(g[k][fk]) - 1) > 1e-3: fails.append("v%d %s.%s 非單位" % (g["v"], k, fk))
        if np.abs(np.array(g["pos"]["V"]) - (p + off)).max() > 0.05 or np.abs(np.array(g["pos"]["S"]) - (T_S + R @ p)).max() > 0.05:
            fails.append("v%d 座標轉換不一致" % g["v"])
    if sum(o["side_counts"].values()) != o["meta"]["N_vert"] or len(o["side"]) != o["meta"]["N_vert"]: fails.append("片頂點數加總 != N")
    dmax = 0
    for f in o["folds"]:
        for e in f["ends"]:
            dd = np.linalg.norm(M - np.array(e["L"]), axis=1).min(); dmax = max(dmax, dd)
            if dd >= 10: fails.append("fold %s 端點離布 %.1f mm" % (f["pair"], dd))
    print("check %s: grasps %d, folds %d, fold 端點最大離布 %.2f mm → %s" % (path, len(o["grasps"]), len(o["folds"]), dmax, "PASS" if not fails else "FAIL"))
    for x in fails: print("  ", x)
    return not fails

# ---------- selftest ----------
def selftest():
    NX = 35; W = 0.5; x = np.linspace(-W / 2, W / 2, NX + 1)
    F2 = np.array([(xi, yj) for yj in x for xi in x]); CX, CY = 0.08463, 0.0715
    SIDE = side_of(F2, CX, CY); ok = True
    # 已知歸屬:手算幾點
    def idx(i, j): return j * (NX + 1) + i
    exp = {idx(17, 17): "base", idx(35, 17): "xp", idx(0, 17): "xn", idx(17, 35): "yp", idx(17, 0): "yn",
           idx(35, 35): "yp", idx(0, 0): "yn"}   # 角:sy>=sx 歸 y(與 grasp_plan 一致)
    for v, s in exp.items():
        if SIDE[v] != s: print("  side v%d %s != %s" % (v, SIDE[v], s)); ok = False
    import grasp_plan as GP
    GP.setup(np.c_[np.vstack([F2, F2]), np.r_[np.full(len(F2), .001), np.full(len(F2), .005)]], NX, CX, CY, np.zeros((0, 3), int))
    if not (GP.S["SIDE"] == SIDE).all(): print("  與 grasp_plan.setup 分片不一致"); ok = False
    # 摺成盒:平板 → 3D(base z=0,側片沿折線立起 90°)
    M = np.c_[F2, np.zeros(len(F2))] * 1e3
    for k, (s, ax, sg, C) in enumerate((("xp", 0, 1, CX), ("xn", 0, -1, CX), ("yp", 1, 1, CY), ("yn", 1, -1, CY))):
        m = SIDE == s; d = sg * F2[m, ax] - C
        M[m, ax] = sg * C * 1e3; M[m, 2] = d * 1e3
    fl = fold_lines(M, F2 * 1e3, SIDE, NX)
    pairs = {tuple(f["pair"]) for f in fl}
    want = {("base", "xn"), ("base", "xp"), ("base", "yn"), ("base", "yp"), ("xn", "yn"), ("xn", "yp"), ("xp", "yn"), ("xp", "yp")}
    if pairs != want: print("  fold pairs", pairs); ok = False
    for f in fl:
        if "base" in f["pair"]:
            s = [p for p in f["pair"] if p != "base"][0]; ax = 0 if s[0] == "x" else 1; C = (CX if ax == 0 else CY) * 1e3
            e = np.array(f["ends"]); dx = abs(abs(e[:, ax]) - C).max()
            # 折線在 base/flap 網格邊中點:z 應 < 半格,|coord| 偏 C 半格內
            h = (x[1] - x[0]) * 1e3 / 2
            good = dx <= h + 1e-6 and abs(f["z_median"]) <= h + 1e-6
            print("  fold base-%s ends %s z_med %.2f %s" % (s, np.round(e, 1).tolist(), f["z_median"], "OK" if good else "BAD")); ok &= good
    cnt = {s: int((SIDE == s).sum()) for s in SIDES}
    print("  counts", cnt, "sum", sum(cnt.values()))
    ok &= sum(cnt.values()) == len(F2) and cnt["xp"] == cnt["xn"] and cnt["yp"] == cnt["yn"]
    n, rms, _, _ = plane_fit(M, F2 * 1e3, idx(17, 17), 30)
    ok &= abs(n[2] - 1) < 1e-9 and rms < 1e-9
    print("selftest", "PASS" if ok else "FAIL"); return ok

if __name__ == "__main__":
    if "--selftest" in sys.argv: sys.exit(0 if selftest() else 1)
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd")
    e = sp.add_parser("export"); e.add_argument("npz"); e.add_argument("--snap", default="end"); e.add_argument("--yaw", type=float, default=270)
    e.add_argument("--off", default=",".join(map(str, OFF_DEF))); e.add_argument("--top", type=int, default=5)
    e.add_argument("--cx", type=float, default=CX_DEF); e.add_argument("--cy", type=float, default=CY_DEF)
    e.add_argument("--fit_r", type=float, default=20.0, help="法線擬合 flat 半徑 mm"); e.add_argument("-o", default="iface.json")
    c = sp.add_parser("check"); c.add_argument("json")
    a = ap.parse_args()
    if a.cmd == "export": export(a)
    elif a.cmd == "check": sys.exit(0 if check(a.json) else 1)
    else: ap.print_help()
