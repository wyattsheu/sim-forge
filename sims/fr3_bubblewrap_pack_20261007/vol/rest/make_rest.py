#!/usr/bin/env python3
"""make_rest.py — 解析等距四折 rest shape(純 numpy/scipy,不用模擬器)。

    python3 make_rest.py --gap_mm 10 [--r_T 2] [--align 0|1] [--nz 1] [--arap 300] --out rest_g10.npz

板:sheet x sheet x T,manual 規則格 nxy x nxy x nz(vol_pen.grid_tets,頂點索引 (k*(n+1)+j)*(n+1)+i,與 volcommon 相同),
    底面 z=ZB(=0.001,同探針/ wrap_vol)。杯子 133x107x93(與 wrap_vol 同:杯頂 z=99.1)。
幾何(每一邊各自是 s=|x| 或 |y| 的一維等距剖面,中面等距):
  s<=s1           平貼地面,中面 z = ZB+T/2
  s1..s1+πr/2     圓弧 1(半徑 r,中心 (s1, zm0+r)),轉 90° 立起
  ..s2            側牆,中面在 Xw = s1 + r(預設 Xw = 折線 CX/CY;--align 1 則把 s1 移到最近的格線,Xw 跟著動)
  s2..s2+πr/2     圓弧 2(半徑 r),再轉 90° 蓋到頂面
  之後            頂面,中面 z = zt,往中心走到材料用完(尖端位置 = 等距算出,不夾)
  上下兩層頂點 = 中面 ± T/2 沿局部法線(法線朝杯子;頂面那層朝杯子)。圓弧內外層半徑 r∓T/2 → 彎曲應變 ±T/(2r)。
  頂面層高(中面):x 片 zt = 杯頂 + 2 + T/2(wrap_vol lay 0);yp = x + gap;yn = yp + gap(wrap_vol 在 500mm 板算出 yn lay 2)。
角落(|x|>s1x 且 |y|>s1y):兩個方向都要折,等距不可能(要對角摺痕)。算法:
  (1) 初值 = SIDEPICK(wrap_vol 同一規則):u=|x|-s1x、v=|y|-s1y,u>=v 用 x 剖面(y 不動,= 跟著 x 片立起、
      往 ±y 伸出去的「耳朵」),否則用 y 剖面(x 不動)。對角線兩側不連續。
  (2) 角落頂點(其餘頂點固定在解析位置)做 ARAP(as-rigid-as-possible,相對平板)--arap 次,把對角線的撕裂
      攤到整個角落;這是「先 x 後 y」中唯一能定義成一個連續 rest 的版本,角落不是等距,自檢會分開報。
輸出 npz:fold(rest 點,(V,3))、flat、tets、region(0 中央 1 x 片 2 y 片 3 角落)、side、params。
自檢:(a) 邊長誤差 (b) 體積比 (c) 形變梯度奇異值 σ*=max(σ1,1/σ3)(F: 平板→rest;1/σ3 即前一位
「rest→平板 的最大奇異值」)與彈性能 proxy (d) 層間最小距(rest 時材料距離 > 3 格、空間距離最小)。
"""
import os, sys, argparse, json
import numpy as np
from scipy.spatial import cKDTree
import scipy.sparse as sp
import scipy.sparse.linalg as spl
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from vol_pen import grid_tets, tet_vol, self_pen_count

ap = argparse.ArgumentParser()
ap.add_argument("--sheet_mm", type=float, default=500.0)
ap.add_argument("--thick_mm", type=float, default=4.0)
ap.add_argument("--nxy", type=int, default=35)
ap.add_argument("--nz", type=int, default=1)
ap.add_argument("--gap_mm", type=float, default=10.0)
ap.add_argument("--r_T", type=float, default=2.0, help="圓角半徑 / T")
ap.add_argument("--align", type=int, default=0, help="1 = 圓弧 1 起點對齊格線(Xw 跟著動)")
ap.add_argument("--arap", type=int, default=1000, help="角落 ARAP 迭代數(0 = 只用 SIDEPICK 初值)")
ap.add_argument("--out", default="")
ap.add_argument("--tip_clear_mm", type=float, default=10.0, help="xp/xn 同層,尖端之間至少留這麼多")
ap.add_argument("--init", choices=["sidepick", "blend"], default="sidepick", help="角落 ARAP 初值")
ap.add_argument("--blend_cells", type=float, default=3.0, help="blend 初值:對角線兩側過渡帶寬(格)")
a = ap.parse_args()

T = a.thick_mm / 1e3; S = a.sheet_mm / 1e3; n = a.nxy; h = S / n
ZB = 0.001; ZM0 = ZB + T / 2
CX, CY = 0.08465, 0.0715                  # wrap_vol 折線(杯子 133x107 + margin 12 + wall 6)
MUG = np.array([0.133, 0.107, 0.093])
REST_OFF = 0.0005
MUGBOT = REST_OFF + T + 0.002              # wrap_vol:PLATE_TOP0 + 2mm
MUGTOP = MUGBOT + MUG[2]
r = a.r_T * T
P = print

def snap_grid(v):
    k = np.round((v + S / 2) / h); return k * h - S / 2

def side_params(C, zt):
    s1 = C - r
    if a.align:
        s1 = snap_grid(s1)
    Xw = s1 + r
    L1 = np.pi * r / 2
    s2 = s1 + L1 + (zt - r - ZM0 - r)
    assert s2 >= s1 + L1, "側牆長度 < 0(r 太大)"
    s3 = s2 + L1
    tip = Xw - r - (S / 2 - s3)
    return dict(C=C, s1=s1, Xw=Xw, s2=s2, s3=s3, zt=zt, tip=tip)

def profile(s, p):
    """s:材料座標(>=0,往外)。回傳 along(往外為正)、z、法線 (n_along, n_z)(朝杯子)。"""
    s = np.asarray(s, float)
    al = np.empty_like(s); z = np.empty_like(s); na = np.empty_like(s); nzz = np.empty_like(s)
    s1, s2, s3, Xw, zt = p["s1"], p["s2"], p["s3"], p["Xw"], p["zt"]
    L1 = np.pi * r / 2
    m = s <= s1
    al[m], z[m], na[m], nzz[m] = s[m], ZM0, 0, 1
    m = (s > s1) & (s <= s1 + L1)
    ph = (s[m] - s1) / r
    al[m], z[m], na[m], nzz[m] = s1 + r * np.sin(ph), ZM0 + r - r * np.cos(ph), -np.sin(ph), np.cos(ph)
    m = (s > s1 + L1) & (s <= s2)
    al[m], z[m], na[m], nzz[m] = Xw, ZM0 + r + (s[m] - s1 - L1), -1, 0
    m = (s > s2) & (s <= s3)
    ps = (s[m] - s2) / r
    al[m], z[m], na[m], nzz[m] = Xw - r + r * np.cos(ps), zt - r + r * np.sin(ps), -np.cos(ps), -np.sin(ps)
    m = s > s3
    al[m], z[m], na[m], nzz[m] = Xw - r - (s[m] - s3), zt, 0, -1
    return al, z, na, nzz

ZX = MUGTOP + 0.002 + T / 2
G = a.gap_mm / 1e3
ap2 = a.tip_clear_mm / 1e3
def _lift(C, z0):
    """同層兩片(xp/xn)尖端要留 tip_clear:尖端 along < tip_clear/2 就把頂面加高(用掉材料,尖端外移)。"""
    z = z0
    while side_params(C, z)["tip"] < ap2 / 2:
        z += 0.0005
    return z
ZX = _lift(CX, ZX)
SIDES = dict(xp=side_params(CX, ZX), xn=side_params(CX, ZX), yp=side_params(CY, ZX + G), yn=side_params(CY, ZX + 2 * G))
# yp/yn 是否重疊:不重疊就同層(只是報告;仍照 wrap_vol 500 板 yn lay 2)
P("板 %.0fmm n%d nz%d h=%.2fmm T=%.0f r=%.1fmm(%.2fT)align=%d gap=%.0fmm;杯底 %.1f 杯頂 %.1f mm"
  % (S * 1e3, n, a.nz, h * 1e3, T * 1e3, r * 1e3, a.r_T, a.align, a.gap_mm, MUGBOT * 1e3, MUGTOP * 1e3))
for k, p in SIDES.items():
    P("  %s:折線 %.2f → 弧1起點 s1=%.2f(格線? %s)牆中面 %.2f;頂面中面 z=%.1f;弧2 s2=%.1f;尖端 along=%+.1f mm"
      % (k, p["C"] * 1e3, p["s1"] * 1e3, abs(snap_grid(p["s1"]) - p["s1"]) < 1e-9, p["Xw"] * 1e3, p["zt"] * 1e3,
         p["s2"] * 1e3, p["tip"] * 1e3))

# ── 網格 ──
FLAT, TETS = grid_tets(n, n, a.nz, h, h, T / a.nz, [-S / 2, -S / 2, ZB])
x, y = FLAT[:, 0], FLAT[:, 1]
d = (FLAT[:, 2] - ZM0) / T                 # -0.5..0.5(層:沿法線的偏移)
s1x, s1y = SIDES["xp"]["s1"], SIDES["yp"]["s1"]
REG = np.zeros(len(FLAT), int)
inx = np.abs(x) > s1x + 1e-9; iny = np.abs(y) > s1y + 1e-9
REG[inx & ~iny] = 1; REG[~inx & iny] = 2; REG[inx & iny] = 3

def apply_x(idx):
    out = np.zeros((len(idx), 3))
    for sg, nm in ((1, "xp"), (-1, "xn")):
        m = np.sign(x[idx]) == sg
        al, z, na, nzz = profile(np.abs(x[idx][m]), SIDES[nm])
        out[m, 0] = sg * (al + na * d[idx][m] * T); out[m, 1] = y[idx][m]; out[m, 2] = z + nzz * d[idx][m] * T
    return out

def apply_y(idx):
    out = np.zeros((len(idx), 3))
    for sg, nm in ((1, "yp"), (-1, "yn")):
        m = np.sign(y[idx]) == sg
        al, z, na, nzz = profile(np.abs(y[idx][m]), SIDES[nm])
        out[m, 1] = sg * (al + na * d[idx][m] * T); out[m, 0] = x[idx][m]; out[m, 2] = z + nzz * d[idx][m] * T
    return out

R = FLAT.copy()
i1 = np.where(REG == 1)[0]; R[i1] = apply_x(i1)
i2 = np.where(REG == 2)[0]; R[i2] = apply_y(i2)
i3 = np.where(REG == 3)[0]
u = np.abs(x[i3]) - s1x; v = np.abs(y[i3]) - s1y
ax_ = u >= v
R[i3[ax_]] = apply_x(i3[ax_]); R[i3[~ax_]] = apply_y(i3[~ax_])
R_sidepick = R.copy()
if a.init == "blend":
    # 連續初值:w = smoothstep((u-v)/帶寬),位置 = w*x剖面 + (1-w)*y剖面(對角線上各一半)
    t_ = np.clip(0.5 + (u - v) / (2 * a.blend_cells * h), 0, 1); w = t_ * t_ * (3 - 2 * t_)
    R[i3] = w[:, None] * apply_x(i3) + (1 - w[:, None]) * apply_y(i3)

# ── 角落 ARAP ──
def tet_B(X, Tt):
    Dm = np.stack([X[Tt[:, i]] - X[Tt[:, 0]] for i in (1, 2, 3)], 2)
    Di = np.linalg.inv(Dm)
    B = np.zeros((len(Tt), 4, 3)); B[:, 1:, :] = Di; B[:, 0, :] = -Di.sum(1)
    return B, np.abs(np.linalg.det(Dm)) / 6

def defgrad(X, Y, Tt):
    Dm = np.stack([X[Tt[:, i]] - X[Tt[:, 0]] for i in (1, 2, 3)], 2)
    Ds = np.stack([Y[Tt[:, i]] - Y[Tt[:, 0]] for i in (1, 2, 3)], 2)
    return Ds @ np.linalg.inv(Dm)

if a.arap > 0:
    free = np.zeros(len(FLAT), bool); free[i3] = True
    B, V0 = tet_B(FLAT, TETS)
    tsel = np.where(free[TETS].any(1))[0]
    Tt, Bt, Vt = TETS[tsel], B[tsel], V0[tsel]
    rows, cols, vals = [], [], []
    K = np.einsum("tai,tbi->tab", Bt, Bt) * Vt[:, None, None]
    for a_ in range(4):
        for b_ in range(4):
            rows.append(Tt[:, a_]); cols.append(Tt[:, b_]); vals.append(K[:, a_, b_])
    L = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(len(FLAT),) * 2)
    fi = np.where(free)[0]; ci = np.where(~free)[0]
    Lff = L[fi][:, fi].tocsc(); Lfc = L[fi][:, ci]
    solve = spl.factorized(Lff)
    for it in range(a.arap):
        F = np.einsum("tai,tak->tki", Bt, R[Tt])          # F[k,i] = sum_a X[a,k] B[a,i]
        U, _, Wt = np.linalg.svd(F)
        D = np.ones((len(F), 3)); D[:, 2] = np.sign(np.linalg.det(U @ Wt))
        Rot = (U * D[:, None, :]) @ Wt
        rhs = np.zeros((len(FLAT), 3))
        contrib = np.einsum("tai,tki->tak", Bt, Rot) * Vt[:, None, None]
        for a_ in range(4):
            np.add.at(rhs, Tt[:, a_], contrib[:, a_, :])
        R[fi] = np.stack([solve(rhs[fi, k] - Lfc @ R[ci, k]) for k in range(3)], 1)
    P("角落 ARAP:%d 個角落頂點自由、其餘固定,%d 次迭代" % (len(fi), a.arap))

# ── 自檢 ──
def _mx(v):
    return float(v.max()) if len(v) else 0.0

def check(Rr, tag):
    used = np.zeros(len(Rr), bool); used[TETS.ravel()] = True
    EDG = np.unique(np.sort(np.concatenate([TETS[:, [i, j]] for i in range(4) for j in range(i + 1, 4)]), axis=1), axis=0)
    L0 = np.linalg.norm(FLAT[EDG[:, 0]] - FLAT[EDG[:, 1]], axis=1)
    L1 = np.linalg.norm(Rr[EDG[:, 0]] - Rr[EDG[:, 1]], axis=1)
    err = np.abs(L1 / L0 - 1)
    # 圓弧帶:任一端點的材料座標在某一邊的弧 1 或弧 2 內(±半格)
    def in_arc(idx):
        res = np.zeros(len(idx), bool)
        for nm, p in SIDES.items():
            s = np.abs(FLAT[idx, 0 if nm[0] == "x" else 1])
            for lo in (p["s1"], p["s2"]):
                res |= (s > lo - 1e-9) & (s < lo + np.pi * r / 2 + 1e-9)
        return res
    earc = in_arc(EDG[:, 0]) | in_arc(EDG[:, 1])
    ecor = (REG[EDG[:, 0]] == 3) | (REG[EDG[:, 1]] == 3)
    flat_e = ~earc & ~ecor; arc_e = earc & ~ecor
    V0 = tet_vol(FLAT, TETS); V1 = tet_vol(Rr, TETS); vr = V1 / V0
    F = defgrad(FLAT, Rr, TETS); sv = np.linalg.svd(F, compute_uv=False)
    sig = np.maximum(sv[:, 0], 1 / np.maximum(sv[:, 2], 1e-9))
    tcor = (REG[TETS] == 3).any(1)
    # 彈性能 proxy:rest 為參考,F' = rest→平板,ψ = Σ(σ'-1)^2,權重 rest 體積
    psi = (((1 / np.maximum(sv, 1e-9)) - 1) ** 2).sum(1) * np.abs(V1)
    # 層間:材料距離 > 3 格的頂點對,空間最小距離
    ui = np.where(used)[0]
    tr = cKDTree(Rr[ui]); pr = ui[tr.query_pairs(0.03, output_type="ndarray")]
    md = np.linalg.norm(FLAT[pr[:, 0], :2] - FLAT[pr[:, 1], :2], axis=1)
    pr = pr[md > 3 * h]
    dd = np.linalg.norm(Rr[pr[:, 0]] - Rr[pr[:, 1]], axis=1)
    pc = (REG[pr[:, 0]] == 3) | (REG[pr[:, 1]] == 3)
    top = (Rr[pr[:, 0], 2] > MUGTOP) & (Rr[pr[:, 1], 2] > MUGTOP) & ~pc
    dmin_all = dd.min() if len(dd) else np.inf
    dmin_nc = dd[~pc].min() if (~pc).any() else np.inf
    dmin_top = dd[top].min() if top.any() else np.inf
    # 穿杯(杯子當 box)
    lo = np.array([-MUG[0] / 2, -MUG[1] / 2, MUGBOT]); hi = np.array([MUG[0] / 2, MUG[1] / 2, MUGTOP])
    in_cup = int(((Rr[ui] > lo) & (Rr[ui] < hi)).all(1).sum())
    npen, _ = self_pen_count(Rr, TETS, FLAT, far=3 * h, idx=ui)
    out = dict(tag=tag,
               edge_flat=float(err[flat_e].max()), edge_arc=float(err[arc_e].max()) if arc_e.any() else 0.0,
               edge_corner=_mx(err[ecor]), edge_nc_n_over5=int((err[~ecor] > 0.05).sum()),
               vol_min=float(vr.min()), vol_max=float(vr.max()), n_negvol=int((V1 <= 0).sum()),
               vol_minmax_nc=float(vr[~tcor].min() / vr[~tcor].max()), vol_minmax_all=float(vr.min() / vr.max()),
               sig_nc=float(sig[~tcor].max()), sig_cor=_mx(sig[tcor]),
               n_sig14_nc=int((sig[~tcor] > 1.4).sum()), n_sig14_cor=int((sig[tcor] > 1.4).sum()),
               n_str50=int((sv[:, 2] < 1 / 1.5).sum() + (sv[:, 0] > 1.5).sum()),
               energy=float(psi.sum()), energy_nc=float(psi[~tcor].sum()),
               dmin_all=float(dmin_all), dmin_nc=float(dmin_nc), dmin_top=float(dmin_top),
               in_cup=in_cup, self_pen=npen)
    P("\n[%s]" % tag)
    P(" (a) 邊長誤差 max:平面段 %.2f%% | 圓弧段 %.1f%%(理論彎曲應變 ±T/2r=%.1f%%)| 角落 %.1f%% | 非角落 >5%% 的邊 %d 條"
      % (out["edge_flat"] * 100, out["edge_arc"] * 100, T / 2 / r * 100, out["edge_corner"] * 100, out["edge_nc_n_over5"]))
    P(" (b) 體積比 V_rest/V_flat ∈ [%.3f, %.3f];<=0 的 %d 個;min/max 非角落 %.3f 全部 %.3f"
      % (out["vol_min"], out["vol_max"], out["n_negvol"], out["vol_minmax_nc"], out["vol_minmax_all"]))
    P(" (c) σ*=max(σ1,1/σ3):非角落 max %.3f(>1.4 有 %d)| 角落 max %.3f(>1.4 有 %d)| 伸縮>50%% 的 tet %d | 能量 proxy %.3e(非角落 %.3e)"
      % (out["sig_nc"], out["n_sig14_nc"], out["sig_cor"], out["n_sig14_cor"], out["n_str50"], out["energy"], out["energy_nc"]))
    P(" (d) 不相鄰頂點最小距:全部 %.2f | 非角落 %.2f | 頂面層間 %.2f mm(要求 >= gap-T = %.1f)| 杯內頂點 %d | 自互穿 %d"
      % (dmin_all * 1e3, dmin_nc * 1e3, dmin_top * 1e3, a.gap_mm - a.thick_mm, in_cup, npen))
    return out

CROSS = ~((np.abs(FLAT[TETS].mean(1)[:, 0]) > s1x) & (np.abs(FLAT[TETS].mean(1)[:, 1]) > s1y))   # 十字形:去掉角落格
res = {}
res["sidepick"] = check(R_sidepick, "SIDEPICK 初值(角落不連續)")
if a.arap > 0:
    res["final"] = check(R, "最終(角落 ARAP)")
if a.align:
    _T0 = TETS; TETS = TETS[CROSS]
    res["cross"] = check(R, "十字形(去掉角落格 %d tets,剩 %d)" % ((~CROSS).sum(), CROSS.sum()))
    TETS = _T0
# 對照:wrap_vol 快照(500 板 fold_end)、單折探針
def ref(npz, kf, kr):
    z = np.load(npz); Tt = z["tets"]; F = defgrad(z[kr], z[kf], Tt); sv = np.linalg.svd(F, compute_uv=False)
    V1 = np.abs(tet_vol(z[kf], Tt))
    return float(np.maximum(sv[:, 0], 1 / sv[:, 2]).max()), float(((((1 / sv) - 1) ** 2).sum(1) * V1).sum())
try:
    sn = ref(os.path.join(HERE, "..", "out_v500", "wrap.npz"), "fold_end_tet", "flat")
    s1_ = ref(os.path.join(HERE, "..", "logs", "fold_manual_E2e4.npz"), "fold", "rest")
    P("\n對照:wrap_vol 快照 σ* %.2f 能量 %.3e | 單折探針 σ* %.2f 能量 %.3e | 本 rest 能量 / 單折 = %.1f,/ 快照 = %.2f"
      % (sn[0], sn[1], s1_[0], s1_[1], res[list(res)[-1]]["energy"] / s1_[1], res[list(res)[-1]]["energy"] / sn[1]))
    res["ref"] = dict(snapshot=sn, single=s1_)
except Exception as e:
    P("對照讀不到:", e)
if a.out:
    np.savez(a.out, fold=R, flat=FLAT, tets=TETS, region=REG, sidepick=R_sidepick, cross_keep=CROSS,
             params=json.dumps(dict(vars(a), sides=SIDES, MUGTOP=MUGTOP, MUGBOT=MUGBOT, r=r, ZB=ZB)),
             check=json.dumps(res))
    P("存 %s" % a.out)
