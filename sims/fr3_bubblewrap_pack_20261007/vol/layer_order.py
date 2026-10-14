#!/usr/bin/env python3
"""層序分析:某片(yn/yp)有哪些頂點被其他片壓住/壓在別片上。
用法: python3 vol/layer_order.py <npz> [--snap end] [--r 12] [--dz 2] ; python3 vol/layer_order.py --selftest
volume npz: 'tet'(2N 點,上下兩層)取中面;surface npz: 'sheet'(N 點)。片歸屬同 cloth_iface.side_of。"""
import sys, argparse, numpy as np
CX_DEF, CY_DEF, NX_DEF = 0.08463, 0.07150, 35

def side_of(F2, CX, CY):
    out = []
    for fx, fy in F2:
        if abs(fx) <= CX and abs(fy) <= CY: out.append("base"); continue
        sx = max(0., abs(fx) - CX); sy = max(0., abs(fy) - CY)
        out.append(("yp" if fy > 0 else "yn") if sy >= sx else ("xp" if fx > 0 else "xn"))
    return np.array(out)

def load(path, snap="end", nx=NX_DEF):
    d = np.load(path)
    n = len(d["sheet"]) if "sheet" in d.files else len(d["tet"]) // 2; nx = int(round(n ** .5)) - 1
    ax = (np.arange(nx + 1) / nx - .5) * 0.5
    F2 = np.array([(x, y) for y in ax for x in ax])      # 頂點 j*(nx+1)+i, i->x, j->y
    if "sheet" in d.files: P = d["sheet"] * 1e3
    else:
        k = "snap_" + snap if "snap_" + snap in d.files else snap
        T = d[k]; P = (T[:n] + T[n:]) / 2 * 1e3
        if "flat" in d.files: F2 = d["flat"][:n, :2]
    return P, F2, nx

def analyze(P, side, sd, r=12., dz=2.):
    """回傳 (被壓布林, 壓住者名, 壓在誰上(名集合 per vertex))"""
    idx = np.where(side == sd)[0]; others = np.where((side != sd) & (side != "base"))[0]
    over = np.zeros(len(idx), bool); who = [""] * len(idx); under = [""] * len(idx)
    for a, v in enumerate(idx):
        d = np.hypot(*(P[others, :2] - P[v, :2]).T); m = d < r
        up = others[m & (P[others, 2] > P[v, 2] + dz)]; dn = others[m & (P[others, 2] < P[v, 2] - dz)]
        if len(up):
            nm, c = np.unique(side[up], return_counts=True); who[a] = nm[c.argmax()]; over[a] = True
        if len(dn):
            nm, c = np.unique(side[dn], return_counts=True); under[a] = nm[c.argmax()]
    return idx, over, who, under

def report(P, F2, sd, edge_y, nx=NX_DEF, r=12., dz=2., CX=CX_DEF, CY=CY_DEF):
    side = side_of(F2, CX, CY)
    idx, over, who, under = analyze(P, side, sd, r, dz)
    pos = {v: a for a, v in enumerate(idx)}
    edge = [j * (nx + 1) + i for j in [0 if edge_y < 0 else nx] for i in range(nx + 1)]
    es = [(who[pos[v]] if over[pos[v]] else ".") if v in pos else "-" for v in edge]
    inn = [v for v in edge if v in pos]
    third = lambda lo, hi: sum(over[pos[v]] for k, v in enumerate(edge) if v in pos and lo <= k / nx < hi + (k == nx))
    seg = [third(0, 1/3), third(1/3, 2/3), third(2/3, 1)]
    cnt = {s: sum(1 for a in range(len(idx)) if over[a] and who[a] == s) for s in ("xp", "xn", "yp", "yn")}
    ucnt = {s: sum(1 for u in under if u == s) for s in ("xp", "xn", "yp", "yn", "base")}
    return dict(edge=" ".join(es), seg=[int(x) for x in seg], nedge=len(inn), pct=100 * over.mean(), who=cnt, under_pct=100 * np.mean([u != "" for u in under]), under=ucnt, n=len(idx))

def run(path, snap="end", r=12., dz=2.):
    P, F2, nx = load(path, snap); out = {}
    for sd, ey in (("yn", -1), ("yp", 1)):
        out[sd] = report(P, F2, sd, ey, nx=nx, r=r, dz=dz)
    return out

def show(path, o):
    print(path)
    for sd in o:
        x = o[sd]; print(f" {sd}: 自由邊 {x['edge']}\n    邊被壓 左/中/右={x['seg']}  整片被壓 {x['pct']:.0f}%  壓住者={ {k:v for k,v in x['who'].items() if v} }  壓在誰上 {x['under_pct']:.0f}% {{k:v for k,v in x['under'].items() if v}}".replace("{k:v for k,v in x['under'].items() if v}", str({k: v for k, v in x['under'].items() if v})))

def selftest():
    nx = 35; ax = (np.arange(nx + 1) / nx - .5) * .5
    F2 = np.array([(x, y) for y in ax for x in ax]); side = side_of(F2, CX_DEF, CY_DEF)
    P = np.c_[F2 * 1e3, np.zeros(len(F2))]
    P[side == "yn", 2] = 10.                 # yn 全在上
    i, over, who, under = analyze(P, side, "yn", 30.)
    assert not over.any(), "yn 在上時不該被壓"
    P[side == "yn", 2] = 0.; P[side == "xp", 2] = 10.   # xp 抬高壓 yn 角落
    i, over, who, under = analyze(P, side, "yn", 30.)
    assert over.any() and set(w for w in who if w) == {"xp"}, (over.sum(), set(who))
    P[side == "xp", 2] = 1.                   # 差 <2mm 不算
    assert not analyze(P, side, "yn", 30.)[1].any()
    print("selftest OK")

if __name__ == "__main__":
    if "--selftest" in sys.argv: selftest(); sys.exit()
    ap = argparse.ArgumentParser(); ap.add_argument("npz"); ap.add_argument("--snap", default="end")
    ap.add_argument("--r", type=float, default=12.); ap.add_argument("--dz", type=float, default=2.)
    a = ap.parse_args(); show(a.npz, run(a.npz, a.snap, a.r, a.dz))
