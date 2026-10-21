#!/usr/bin/env python3
"""usage: python3 plastic/spread_stats.py DIR [DIR...]  → (A2) 撐開 rest 烘焙 vs 對照:覆蓋率鏈、各片形狀變化(剛體對齊)、自穿 全程最大/結束、穿杯、反轉、烘焙 log。
(fold_stats.py 的精簡 + 自穿/反轉/spread 欄)"""
import re, sys, numpy as np
def g(p, s, k=1, d="-"):
    m = re.search(p, s); return m.group(k) if m else d
def kabsch(A, B):
    ca, cb = A.mean(0), B.mean(0); H = (B - cb).T @ (A - ca); U, S_, Vt = np.linalg.svd(H)
    d_ = np.sign(np.linalg.det(Vt.T @ U.T)); R = Vt.T @ np.diag([1, 1, d_]) @ U.T
    return (B - cb) @ R.T + ca
print("| 次 | 烘焙 | 覆蓋 放錨前 → 搬前 → 搬後 → 開蓋後 | 下降 | 形狀變化(剛體對齊)中位/p90 mm yn yp xp xn | 布 bbox 放錨前 → 結束 | 自穿 烘焙前 / 全程最大 / 結束 | 穿杯 最大 | 反轉 最大 | spread log |")
print("|---|---|---|---|---|---|---|---|---|---|")
for d in sys.argv[1:]:
    try:
        s = open(d + "/stdout.txt", errors="ignore").read(); Z = np.load(d + "/wrap.npz")
    except Exception as e:
        print("| %s | 讀不到 (%s) |" % (d, e)); continue
    CX = float(g(r"折線 CX=([\d.]+)", s)) / 1e3; CY = float(g(r"CY=([\d.]+) mm", s)) / 1e3
    F = Z["flat"]; c = (F.min(0) + F.max(0)) / 2; dx = np.abs(F[:, 0] - c[0]) - CX; dy = np.abs(F[:, 1] - c[1]) - CY
    lab = np.where(np.maximum(dx, dy) < 0, "base", np.where(dx > dy, np.where(F[:, 0] > c[0], "xp", "xn"), np.where(F[:, 1] > c[1], "yp", "yn")))
    cov = lambda nm: g(r"\n\s+%s\s+t=.*?杯頂俯視覆蓋 (\d+)%%" % nm, s)
    c0, cb, c1, c2 = cov("closed_pre_release"), cov("before_move"), cov("after_move"), cov("end")
    P0 = Z["snap_closed_pre_release"]; P1 = Z["snap_end"] if "snap_end" in Z else Z["tet"]
    Dk = np.linalg.norm(kabsch(P0, P1) - P0, axis=1) * 1e3
    sides = " ".join("%.0f/%.0f" % (np.median(Dk[lab == k]), np.percentile(Dk[lab == k], 90)) for k in ("yn", "yp", "xp", "xn"))
    bb = lambda P: "%.0fx%.0fx%.0f" % tuple((P.max(0) - P.min(0)) * 1e3)
    drop = (int(c0) - int(c2)) if c0 != "-" and c2 != "-" else "-"
    rows = re.findall(r"\nt=\s*([\d.]+) .*?\| 自穿\s+(\d+) \| 布穿杯\s+(\d+) \| 反轉\s+(\d+)", s)
    tb = float(g(r"★ t=([\d.]+) \[plastic\]", s, d="nan"))
    sp = [int(r[1]) for r in rows]; pre = [int(r[1]) for r in rows if float(r[0]) < tb] if tb == tb else sp
    endpen = g(r"\n\s+final\s+t=.*?自穿 (\d+)", s)
    spl = g(r"\[spread\] rest 撐開 (.*?)、解", s)
    print("| %s | %s | %s → %s → %s → %s%% | %s | %s | %s → %s | %s / %s / %s | %s | %s | %s |" % (
        d, ("d=" + g(r"'--plastic_spread_mm', '([\d.]+)'", s, d="0")) if "'--plastic_on_fold', '1'" in s else "否", c0, cb, c1, c2, drop, sides,
        bb(P0), bb(P1), max(pre) if pre else "-", max(sp) if sp else "-", endpen, max(int(r[2]) for r in rows) if rows else "-",
        max(int(r[3]) for r in rows) if rows else "-", spl))
