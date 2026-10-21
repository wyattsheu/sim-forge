#!/usr/bin/env python3
"""peel_traj_v3.py — 掀包材抓取姿態用 Lula IK 重規劃:夾持軸(開合)沿布面法線、指尖沿自由邊切向,抓在自由邊中段。
    /isaac-sim/python.sh peel_traj_v3.py --flap yn --u 0.3,0.45,0.6 [--arm right]
沿用 peel_traj_v2 的手臂模型 / Lula IK / 幾何碰撞(exec v2 前段;紙箱 yaw 270、四蓋 260°、另一臂停 READY)。
抓點幾何(箱局部 L,來自 vol/soft/s2/iface.npz,= cloth_iface export --snap end --yaw 270):
  n = top−bot(厚度方向,取朝上);t = 自由邊鄰點差(正交化);s = 由第 2 列指向自由邊(水平化)。
  抓取框 R = [t, n, t×n](TCP x = 指尖、y = 開合軸)。φ = 繞開合軸轉、ψ = 繞指尖軸轉(與 v2 同定義)。
段落:b1 到預備點(自由邊外 OUT mm、布面上 60mm)→ b2 垂直下降到布面上 2mm → b2s 水平滑入 IN mm 並降到布中面
  (讓邊進到兩指之間;否則下指會壓布)→ b3 合指 → b4 抬 15mm → b5 繞折線弧線(半徑 0.8×材料長)到 θ_end,
  再直線到牆頂 +40、牆外 → b6 停。每點 IK(warm start + 碰撞檢查)。輸出 npz/json(同 v2 格式)+ 可達表。"""
import os, sys, json, math, argparse
ap = argparse.ArgumentParser()
ap.add_argument("--flap", default="yn", choices=["yn", "yp"])
ap.add_argument("--u", default="0.3,0.45,0.6")
ap.add_argument("--arm", default="right")
ap.add_argument("--out_mm", type=float, default=16.0)
ap.add_argument("--in_mm", type=float, default=24.0)
ap.add_argument("--rfac", type=float, default=0.8)
ap.add_argument("--outs", default="8,16,24")
ap.add_argument("--csd_tol", type=float, default=-1.0, help="下降中指插布容許(mm,負);找不到乾淨解時放寬")
ap.add_argument("--th_end", type=float, default=100.0)
A = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "peel_traj_v2.py")).read()
src = src[:src.index('if a.only != "b":')]
src = src.replace('"peel_traj_%s.log" % TAG', '"peel_traj_v3_%s.log" % "' + A.flap + '"')
sys.argv = ["peel_traj_v2.py", "--lid_mode", "pinch", "--open_deg", "260", "--no_video"]
exec(compile(src, "peel_traj_v2_prefix", "exec"))
import numpy as np
ROOT = os.path.dirname(HERE)
_IF = os.path.join(HERE, "data") if os.path.exists(os.path.join(HERE, "data", "iface.npz")) else os.path.join(ROOT, "vol", "soft", "s2")   # [release] 交付版 iface 放在 data/
D = np.load(os.path.join(_IF, "iface.npz")); IFJ = json.load(open(os.path.join(_IF, "iface.json")))
NX = int(D["NX"]); F2 = D["flat"]
ey = -1 if A.flap == "yn" else 1
fold = next(f for f in IFJ["folds"] if tuple(f["pair"]) == ("base", A.flap))
HY = ey * 71.43e-3; HZ = fold["z_median_L"] * 1e-3
HY_meas = float(np.mean([e["L"][1] for e in fold["ends"]])) * 1e-3
MAT = (250.0 - 71.43) * 1e-3; Rarc = A.rfac * MAT
P("\n=== v3 %s 片;鉸點 L (y %.1f[實測 %.1f], z %.1f) mm;材料長 %.1f mm → 弧半徑 %.1f mm" % (A.flap, HY * 1e3, HY_meas * 1e3, HZ * 1e3, MAT * 1e3, Rarc * 1e3))
def vid(i, j): return j * (NX + 1) + i
jrow = 0 if ey < 0 else NX
add("(a) 略過:上蓋 kinematic 開", 1.0, lids=dict(fyp=180.0, fyn=180.0))
add("b0 四蓋開到 260", 1.2, lids=dict(fxp=260.0, fxn=260.0, fyp=260.0, fyn=260.0))
LB_ = dict(st_["lids"]); H = A.arm; OTH = "left" if H == "right" else "right"; otherH = pts_of(OTH, READY[OTH], 0.0)
qk, gk = ("qR", "gR") if H == "right" else ("qL", "gL")
gOpen, gClose = q_for_gap(21.0), q_for_gap(4.5)
BASESEG = list(SEG)
WALLT = meta["wall_top_y"] if A.flap in ("yn", "yp") else meta["wall_top_x"]
def geom(u):
    i = int(round(u * NX + 1e-9)); v = vid(i, jrow)
    mid, top, bot = D["mid_L"][v] * 1e-3, D["top_L"][v] * 1e-3, D["bot_L"][v] * 1e-3
    n = top - bot; th = np.linalg.norm(n); n /= th
    if n[2] < 0: n = -n
    t = D["mid_L"][vid(min(NX, i + 1), jrow)] - D["mid_L"][vid(max(0, i - 1), jrow)]; t = t - (t @ n) * n; t /= np.linalg.norm(t)
    s = D["mid_L"][v] - D["mid_L"][vid(i, jrow - ey)]; s = s - (s @ n) * n; s /= np.linalg.norm(s)
    sh = s.copy(); sh[2] = 0; sh /= np.linalg.norm(sh)
    return dict(i=i, v=v, mid=mid, n=n, t=t, s=s, sh=sh, th=th)
def W(pL): return (TB @ np.r_[pL, 1])[:3]
CLW = np.vstack([np.array([W(p_ * 1e-3) for p_ in D[k]]) for k in ("top_L", "bot_L")])
FB = ["%s/follower_%s_gripper_%s" % (R0, A.arm, f_) for f_ in ("left", "right")]
FOBB = {b: (PTS[b].min(0), PTS[b].max(0)) for b in FB}
def cloth_sd(q, g):
    """布頂點(兩層)對兩指 OBB 的最小有號距離 mm(<0 = 指頭插進布)。"""
    B = body_fk(H, np.asarray(q), g, MIM * g); best = 9e9
    for b in FB:
        T = B[b]; l = (CLW - T[:3, 3]) @ T[:3, :3]; lo, hi = FOBB[b]; c = (lo + hi) / 2; h = (hi - lo) / 2
        d = np.abs(l - c) - h; sd = np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(d.max(1), 0); best = min(best, sd.min() * 1e3)
    return best
def sig(q): return float(np.linalg.svd(RM.jac_np(ARMS[H], q), compute_uv=False).min())
PHI_S = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45]; PSI_S = [0, -10, 10, -20, 20, -30, 30]
TABLE = []; RES = {}
for u in [float(x) for x in A.u.split(",")]:
    g = geom(u); surf = g["mid"] + g["n"] * g["th"] / 2
    RES[u] = None
    P("\n--- u=%.2f v%d:中面 L %s mm,n %s,t %s,厚 %.1f mm" % (u, g["v"], (g["mid"] * 1e3).round(1).tolist(), g["n"].round(2).tolist(), g["t"].round(2).tolist(), g["th"] * 1e3))
    cands = []
    for om, tsg in [(float(o_), -1) for o_ in A.outs.split(",")]:
        pD = surf + g["sh"] * om * 1e-3 + np.array([0, 0, 0.002])         # 下降終點:邊外 om mm、布面上 2mm
        pIn = g["mid"] - g["sh"] * 8e-3                                      # 滑入終點:布中面、邊進指內 8 mm
        tt = tsg * g["t"]; Rl = np.column_stack([tt, g["n"], np.cross(tt, g["n"])]); Rw = TB[:3, :3] @ Rl
        for ph in PHI_S:
            for ps in PSI_S:
                DIAG[0] = None
                q, _ = ik_cf(H, W(pD), Rw, READY[H], ph, gOpen, LB_, [ph], otherH, maxjump=None, psis=[float(ps)])
                if q is None:
                    TABLE.append(dict(u=u, out=om, tsg=tsg, phi=ph, psi=ps, ok=False, sigma=None, clr=(DIAG[0][0] if DIAG[0] else None), why=("碰撞 %.1fmm %s↔%s" % DIAG[0][:3]) if DIAG[0] else "IK 無解"))
                    continue
                (d, nm, bn), _p = arm_clear(H, q, gOpen, LB_); sg = sig(q); cs = cloth_sd(q, gOpen)
                TABLE.append(dict(u=u, out=om, tsg=tsg, phi=ph, psi=ps, ok=True, sigma=sg, clr=d, csd=cs, why="%s↔%s" % (nm, bn)))
                cands.append((cs < -1.0, -min(cs, 5) - min(d, 30) / 30 - sg, tsg, ph, ps, q, Rl, om, pD, pIn))
    nok = sum(1 for r in TABLE if r["u"] == u and r["ok"])
    P("  可達(下降終點)%d / %d 組;其中指不插布(≥−1mm)%d" % (nok, len(A.outs.split(",")) * len(PHI_S) * len(PSI_S), sum(1 for c_ in cands if not c_[0])))
    cands.sort(key=lambda c: (c[0], c[1]))
    for c_ in cands[:20]:
        _, _, tsg, ph, ps, q0, Rl, om, pD, pIn = c_
        Rw = TB[:3, :3] @ Rl; PHN = sorted(set([ph] + [max(0, ph - 5), min(45, ph + 5)] + [ph - 10, ph + 10]), key=lambda x: abs(x - ph))
        PSN = [float(ps)]
        pre = W(pD + np.array([0, 0, 0.058]))
        qpre, phpre = ik_cf(H, pre, Rw, READY[H], ph, gOpen, LB_, PHN, otherH, maxjump=None, psis=PSN)
        if qpre is None: P("  ✗ t%+d φ%d ψ%d 預備點無解" % (tsg, ph, ps)); continue
        dn = [(W(pD + np.array([0, 0, 0.058 * (1 - k)])), Rw) for k in np.linspace(0, 1, 30)]
        qsD, phD, f2 = cart_cf(H, dn, qpre, phpre, gOpen, LB_, PHN, "b2 下降", otherH, psis=PSN)
        if f2 is not None: continue
        dsd = min(cloth_sd(q_, gOpen) for q_ in qsD)
        if dsd < A.csd_tol: P("  ✗ out%d φ%d ψ%d 下降中指插布 %.1f mm" % (om, ph, ps, dsd)); continue
        sl = [(W(pD + (pIn - pD) * k), Rw) for k in np.linspace(0, 1, 16)[1:]]
        qsS, phS, f2s = cart_cf(H, sl, qsD[-1], phD[-1], gOpen, LB_, PHN, "b2s 滑入", otherH, psis=PSN)
        if f2s is not None: continue
        upP = [(W(pIn + np.array([0, 0, 0.015 * k])), Rw) for k in np.linspace(0, 1, 10)[1:]]
        qsU, phU, f4 = cart_cf(H, upP, qsS[-1], phS[-1], gClose, LB_, PHN, "b4 抬 15", otherH, psis=PSN)
        if f4 is not None: continue
        gl = pIn + np.array([0, 0, 0.015]); th0 = math.atan2(gl[2] - HZ, ey * (gl[1] - HY) * -1); r0 = math.hypot(gl[1] - HY, gl[2] - HZ)
        # 角度 θ 從「箱內側水平」量起(yn:−y 為外,內側 = +y);弧線往外翻 → θ 增加
        def ptL(r, th): return np.array([gl[0], HY - ey * r * math.cos(th), HZ + r * math.sin(th)])
        TE = math.radians(A.th_end); arcL = []
        for k in np.linspace(0, 1, 40)[1:]:
            th = th0 + (TE - th0) * k; r = r0 + (Rarc - r0) * min(1, k * 1.5); arcL.append((ptL(r, th), th - th0))
        pE = np.array([gl[0], ey * (0.112 + 0.020), WALLT + 0.040 + 0.002]); pl = arcL[-1][0]
        for k in np.linspace(0, 1, 12)[1:]: arcL.append((pl + (pE - pl) * k, TE - th0))
        rotax = np.array([-ey * 1.0, 0, 0])     # yn:繞 +x;yp:繞 −x
        arcP = [(W(p_), TB[:3, :3] @ rot_axis(rotax, math.degrees(dt)) @ Rl) for p_, dt in arcL]
        qsC, phC, f5 = cart_cf(H, arcP, qsU[-1], phU[-1], gClose, LB_, PHN + [ph + 15, ph + 20, ph - 15, ph - 20], "b5 弧線", otherH, psis=PSN)
        RES[u] = dict(out=om, dsd=dsd, tsg=tsg, phi=ph, psi=ps, qpre=qpre, qsD=qsD, qsS=qsS, qsU=qsU, qsC=qsC, arc_fail=f5, narc=len(arcP), g=g, th0=math.degrees(th0), r0=r0,
                      end_L=(arcL[(len(qsC) - 1) if qsC else 0][0] * 1e3).round(1).tolist(), sig=min(sig(q) for q in qsD + qsS + qsU + qsC))
        P("  ★ 選 out%d 下降指布最小 %.1fmm t%+d φ%d ψ%d:" % (om, dsd, tsg, ph, ps) + "弧線 %d/%d 點(θ0 %.0f°、r0 %.0f mm),最小 σ %.3f" % (len(qsC), len(arcP), math.degrees(th0), r0 * 1e3, RES[u]["sig"]))
        if f5 is None: break
P("\n=== 表 1 可達性(下降終點;每抓點列最好 6 組)")
P("抓點 | out | φ | ψ | σ | 箱/臂最小距離 mm | 指布 mm")
for u in RES:
    rows = sorted([r for r in TABLE if r["u"] == u and r["ok"]], key=lambda r: (r["csd"] < -1, -(min(r["csd"], 5) + min(r["clr"], 30) / 30 + r["sigma"])))
    for r in rows[:6]: P("u%.2f | %d | %d | %d | %.3f | %.1f(%s) | %.1f" % (u, r["out"], r["phi"], r["psi"], r["sigma"], r["clr"], r["why"], r["csd"]))
    if not rows:
        bad = [r for r in TABLE if r["u"] == u]; P("u%.2f | 無解;原因統計 %s" % (u, {k: sum(1 for r in bad if r["why"].startswith(k)) for k in ("IK", "碰撞")}))
OUTS = {}
for u, R_ in RES.items():
    if R_ is None: continue
    del SEG[len(BASESEG):]; st_.update(qL=np.array(SEG[-1]["qL"][-1]), qR=np.array(SEG[-1]["qR"][-1]), gL=float(SEG[-1]["gL"][-1]), gR=float(SEG[-1]["gR"][-1]), lids=dict(SEG[-1]["lids"][-1]))
    kw = lambda q, g_: {qk: q, gk: g_}
    add("b1 到預備點(邊外、布面上 60mm)、開指", 2.5, **kw(R_["qpre"], gOpen))
    add("b2 垂直下降到布面上 2mm + 滑入", 2.0, **kw(R_["qsD"] + R_["qsS"], None))
    add("b3 合指到 4.5mm", 0.5, **kw(None, gClose))
    add("b4 抬 15mm", 0.6, **kw(R_["qsU"], None))
    if R_["qsC"]: add("b5 弧線 + 抬到牆頂+40 牆外", 4.5 * len(R_["qsC"]) / R_["narc"], **kw(R_["qsC"], None))
    add("b6 停", 0.7)
    summ = []; t = 0.0
    for s in SEG: summ.append(dict(name=s["name"], t0=t, t1=t + s["n"] / FPS)); t += s["n"] / FPS
    tag = "peel_traj_v3_%s_u%02d" % (A.flap, int(round(u * 100)))
    g = R_["g"]
    json.dump(dict(out_mm=R_["out"], descent_cloth_sd=R_["dsd"], segments=summ, gap=dict(G0=G0, GK=GK, mimic=MIM), flap=A.flap, arm=H, u=u, grasp_v=int(g["v"]), phi=R_["phi"], psi=R_["psi"], tsg=R_["tsg"],
                   sigma_min=R_["sig"], arc_fail=R_["arc_fail"], narc=R_["narc"], end_L=R_["end_L"], hinge_L=[HY, HZ], Rarc=Rarc, n_L=g["n"].tolist(), t_L=g["t"].tolist()),
              open(os.path.join(HERE, "data", tag + ".json"), "w"), indent=1, default=float)
    np.savez(os.path.join(HERE, "data", tag + ".npz"), qL=np.array([q for s in SEG for q in s["qL"]]), qR=np.array([q for s in SEG for q in s["qR"]]),
             gL=np.array([x for s in SEG for x in s["gL"]]), gR=np.array([x for s in SEG for x in s["gR"]]),
             lids=np.array([[l[k] for k in ("fxp", "fxn", "fyp", "fyn")] for s in SEG for l in s["lids"]]), fps=FPS)
    P("寫 %s(%d 格)" % (tag, sum(s["n"] for s in SEG)))
json.dump(TABLE, open(os.path.join(HERE, "data", "peel_traj_v3_%s_reach.json" % A.flap), "w"), indent=0, default=float)
app.close()
