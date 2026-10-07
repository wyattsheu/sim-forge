#!/usr/bin/env python3
"""layer_gap.py — 量「布疊在杯子上方時，層與層之間實際隔多遠」(純 CPU,只吃 npz)。

    python3 layer_gap.py a.npz [b.npz ...] [--grid_mm 5] [--shrink_mm 15]
    python3 layer_gap.py --selftest        # 合成兩張平行布(dz=3mm),必須量出 2 層 / 3.0mm

做法:在杯子 xy bbox 內縮 shrink_mm 的範圍內,每 grid_mm 取一個 (x,y);對布的每個三角形
(規則網格重建,每格兩個三角形)做 xy 投影點在三角形內測試,重心插值出交點 z。
同一 (x,y) 有幾個 z 就是幾層。只算杯頂上方的層(z > 局部杯頂 − BELOW_TOL),
杯子底下墊在地上的那層另計、不算進疊層。局部杯頂 = 該 xy 半徑 MUG_R 內杯子頂點最大 z
(沒有頂點就取 xy 最近 10 個頂點的最大 z)。
同一層被相鄰三角形重複命中(點剛好落在共用邊/頂點上)時,以「兩三角形共用頂點」判為重複並合併。
"""
import argparse
import sys
import numpy as np

BELOW_TOL = 0.010   # m;z 低於局部杯頂超過這個量的層視為「杯子下方」(墊底那層),不計入疊層
MUG_R = 0.006       # m;局部杯頂的 xy 搜尋半徑
EPS = 1e-9          # 重心座標容差


def grid_tris(n):
    """n 個頂點的方形規則網格 -> (T,3) 三角形索引。索引 k: i=k%r, j=k//r。"""
    r = int(round(np.sqrt(n)))
    if r * r != n:
        raise ValueError("頂點數 %d 不是完全平方,這支只吃方形規則網格" % n)
    i, j = np.meshgrid(np.arange(r - 1), np.arange(r - 1), indexing="xy")
    a = (j * r + i).ravel()
    b, c, d = a + 1, a + r, a + r + 1
    return np.concatenate([np.stack([a, b, d], 1), np.stack([a, d, c], 1)])


def hits_at(S, T, P):
    """P: (K,2) 取樣點。回傳 list,每個取樣點一個 [(z, tri_idx), ...](已去掉重複命中)。"""
    A, B, C = S[T[:, 0]], S[T[:, 1]], S[T[:, 2]]            # (T,3)
    e1, e2 = (B - A)[:, :2], (C - A)[:, :2]
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]           # xy 投影面積*2
    ok = np.abs(det) > 1e-12                                  # 垂直於 xy 的退化三角形跳過
    out = []
    for p in P:
        q = p[None, :] - A[:, :2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = (q[:, 0] * e2[:, 1] - q[:, 1] * e2[:, 0]) / det
            v = (e1[:, 0] * q[:, 1] - e1[:, 1] * q[:, 0]) / det
        inside = ok & (u >= -EPS) & (v >= -EPS) & (u + v <= 1 + EPS)
        idx = np.nonzero(inside)[0]
        z = A[idx, 2] + u[idx] * (B[idx, 2] - A[idx, 2]) + v[idx] * (C[idx, 2] - A[idx, 2])
        # 去重:共用頂點的兩個三角形同時命中 -> 同一層(點落在共用邊/頂點上)
        keep = []
        for k in np.argsort(z):
            tv = set(T[idx[k]])
            if any(tv & set(T[idx[m]]) for m in keep):
                continue
            keep.append(k)
        out.append(sorted((float(z[k]), int(idx[k])) for k in keep))
    return out


def local_mug_top(M, P):
    tops = np.empty(len(P))
    for n, p in enumerate(P):
        d2 = ((M[:, :2] - p) ** 2).sum(1)
        m = d2 < MUG_R ** 2
        tops[n] = M[m, 2].max() if m.any() else M[np.argpartition(d2, 10)[:10], 2].max()
    return tops


def pct(a):
    a = np.asarray(a)
    return (np.median(a), np.percentile(a, 5), np.percentile(a, 95)) if len(a) else (np.nan,) * 3


def measure(S, M, grid_mm=5.0, shrink_mm=15.0):
    T = grid_tris(len(S))
    lo, hi = M[:, :2].min(0) + shrink_mm / 1000, M[:, :2].max(0) - shrink_mm / 1000
    xs = np.arange(lo[0], hi[0] + 1e-9, grid_mm / 1000)
    ys = np.arange(lo[1], hi[1] + 1e-9, grid_mm / 1000)
    P = np.array([(x, y) for y in ys for x in xs])
    H = hits_at(S, T, P)
    top = local_mug_top(M, P)
    nabove, nbelow, gaps, first, thick = [], [], {}, [], []
    for h, t in zip(H, top):
        z = np.array([zz for zz, _ in h])
        za = z[z > t - BELOW_TOL]
        nabove.append(len(za)); nbelow.append(len(z) - len(za))
        if len(za):
            first.append(za[0] - t); thick.append(za[-1] - t)
        for k in range(len(za) - 1):
            gaps.setdefault(k, []).append(za[k + 1] - za[k])
    return dict(n=len(P), nx=len(xs), ny=len(ys), lo=lo, hi=hi,
                nabove=np.array(nabove), nbelow=np.array(nbelow), gaps=gaps,
                first=np.array(first), thick=np.array(thick), top=top)


def report(name, R):
    na = R["nabove"]
    print("\n=== %s" % name)
    print("  取樣格 x[%.1f,%.1f] y[%.1f,%.1f] mm, %dx%d=%d 點; 局部杯頂 z 中位 %.1f mm [%.1f, %.1f]"
          % (*(1000 * np.r_[R["lo"][0], R["hi"][0], R["lo"][1], R["hi"][1]]), R["nx"], R["ny"], R["n"],
             *(1000 * np.r_[np.median(R["top"]), R["top"].min(), R["top"].max()])))
    u, c = np.unique(na, return_counts=True)
    print("  杯頂上方層數分佈: " + ", ".join("%d層:%d" % (a, b) for a, b in zip(u, c))
          + "   (中位 %.1f 層)" % np.median(na))
    ub, cb = np.unique(R["nbelow"], return_counts=True)
    print("  (杯頂下方 >%.0fmm 的層,如墊底布,不計入: " % (BELOW_TOL * 1000)
          + ", ".join("%d層:%d" % (a, b) for a, b in zip(ub, cb)) + ")")
    if len(R["first"]):
        print("  第1層 − 杯頂        : 中位 %6.2f  p5 %6.2f  p95 %6.2f mm  (n=%d)" % (*(1000 * np.r_[pct(R["first"])]), len(R["first"])))
    for k in sorted(R["gaps"]):
        g = R["gaps"][k]
        print("  第%d↔%d層 層間距      : 中位 %6.2f  p5 %6.2f  p95 %6.2f mm  (n=%d)" % (k + 1, k + 2, *(1000 * np.r_[pct(g)]), len(g)))
    allg = np.concatenate([R["gaps"][k] for k in R["gaps"]]) if R["gaps"] else np.array([])
    gmed = 1000 * np.median(allg) if len(allg) else np.nan
    if len(allg):
        print("  全部相鄰層間距      : 中位 %6.2f  p5 %6.2f  p95 %6.2f mm  (n=%d)" % (*(1000 * np.r_[pct(allg)]), len(allg)))
    tmed = 1000 * np.median(R["thick"]) if len(R["thick"]) else np.nan
    if len(R["thick"]):
        print("  布最高點 − 杯頂(疊層總厚): 中位 %6.2f  p5 %6.2f  p95 %6.2f mm" % tuple(1000 * np.r_[pct(R["thick"])]))
    if not len(allg):
        print("  判讀: 沒有任何取樣點有 ≥2 層,量不到層間距(先確認布真的疊在杯頂)")
    elif gmed > 2.0:
        print("  判讀: 層間有空隙 ≈ %.1f mm,不是貼合" % gmed)
    else:
        print("  判讀: 層間已貼合 (中位層間距 %.2f mm)" % gmed)
    return (np.median(na), gmed, tmed)


def selftest():
    r, W = 35, 0.586
    i, j = np.arange(r * r) % r, np.arange(r * r) // r
    base = np.c_[-W / 2 + i * W / (r - 1), -W / 2 + j * W / (r - 1), np.zeros(r * r)]
    # 杯子:xy ±50mm 的一片頂點,頂在 z=0.100
    g = np.linspace(-0.05, 0.05, 41)
    X, Y = np.meshgrid(g, g)
    M = np.c_[X.ravel(), Y.ravel(), np.full(X.size, 0.100)]
    ok = True
    for nm, S in (("兩張平行布 z=101/104mm", np.r_[base + [0, 0, 0.101], base + [0, 0, 0.104]]),
                  ("兩張平行布 xy 錯開半格 + 輕微傾斜",
                   np.r_[base + [0, 0, 0.101], base + [0.0043, 0.0043, 0.104]])):
        # 兩張布併成一個 npz 不是單一方格網,所以分別三角化後合併
        T1 = grid_tris(r * r)
        T = np.r_[T1, T1 + r * r]
        if "傾斜" in nm:
            S = S.copy(); S[:, 2] += 0.02 * S[:, 0]; M2 = M.copy(); M2[:, 2] += 0.02 * M2[:, 0]
        else:
            M2 = M
        P = np.array([(x, y) for y in np.arange(-0.035, 0.0351, 0.005) for x in np.arange(-0.035, 0.0351, 0.005)])
        H = hits_at(S, T, P)
        nl = np.array([len(h) for h in H])
        gp = np.array([h[1][0] - h[0][0] for h in H if len(h) == 2])
        top = local_mug_top(M2, P)
        th = np.array([h[-1][0] for h in H]) - top
        good = (nl == 2).all() and np.allclose(gp, 0.003, atol=1e-6) and np.allclose(th, 0.004, atol=2e-4)
        ok &= good
        print("[selftest] %-30s 層數分佈 %s  間距中位 %.3f mm  總厚中位 %.3f mm  -> %s"
              % (nm, dict(zip(*[a.tolist() for a in np.unique(nl, return_counts=True)])),
                 1000 * np.median(gp), 1000 * np.median(th), "PASS" if good else "FAIL"))
    # 端到端:走 measure() 路徑 (單張 35x35 布,z 折成兩層不方便,改測單層 1 層 / 總厚 1mm)
    R = measure(base + [0, 0, 0.101], M)
    good = (R["nabove"] == 1).all() and np.allclose(R["thick"], 0.001, atol=1e-6)
    ok &= good
    print("[selftest] %-30s 層數全為 1: %s  總厚中位 %.3f mm  -> %s"
          % ("measure() 單層端到端", (R["nabove"] == 1).all(), 1000 * np.median(R["thick"]), "PASS" if good else "FAIL"))
    print("[selftest] %s" % ("ALL PASS" if ok else "有失敗"))
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--grid_mm", type=float, default=5.0)
    ap.add_argument("--shrink_mm", type=float, default=15.0)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if not a.files:
        sys.exit(__doc__)
    print("grid %.1f mm, shrink %.1f mm, 杯頂下方容差 %.0f mm" % (a.grid_mm, a.shrink_mm, BELOW_TOL * 1000))
    rows = []
    for f in a.files:
        d = np.load(f)
        try:
            R = measure(d["sheet"].astype(float), d["mug"].astype(float), a.grid_mm, a.shrink_mm)
        except ValueError as e:
            print("\n=== %s: %s" % (f, e)); continue
        rows.append((f,) + report(f, R))
    if rows:
        w = max(len(r[0]) for r in rows)
        print("\n%-*s | 層數中位 | 層間距中位(mm) | 疊層總厚(mm)" % (w, "檔名"))
        print("-" * (w + 45))
        for f, n, g, t in rows:
            print("%-*s | %8.1f | %14.2f | %12.2f" % (w, f, n, g, t))


if __name__ == "__main__":
    main()
