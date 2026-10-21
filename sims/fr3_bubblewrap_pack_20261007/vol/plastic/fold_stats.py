#!/usr/bin/env python3
"""usage: python3 plastic/fold_stats.py DIR [DIR...]  → (A) 烘焙折痕:關蓋前(放錨前)vs 搬後 / 開蓋後 各片相對杯子位移、覆蓋率、bbox(grep + npz)"""
import re, sys, numpy as np
def g(p, s, k=1, d="-"):
    m = re.search(p, s); return m.group(k) if m else d
print("| 次 | plastic_on_fold | 覆蓋 放錨前 → 搬前 → 搬後 → 開蓋後 | 下降(百分點)| 各片位移 中位/p90 mm(放錨前→開蓋後,相對箱)| 布 bbox 放錨前 → 開蓋後 | 自穿 / 穿杯 全程最大 |")
print("|---|---|---|---|---|---|---|")
for d in sys.argv[1:]:
    s = open(d + "/stdout.txt", errors="ignore").read()
    Z = np.load(d + "/wrap.npz")
    CX = float(g(r"折線 CX=([\d.]+)", s)) / 1e3; CY = float(g(r"CY=([\d.]+) mm", s)) / 1e3
    F = Z["flat"]; c = (F.min(0) + F.max(0)) / 2; dx = np.abs(F[:, 0] - c[0]) - CX; dy = np.abs(F[:, 1] - c[1]) - CY
    lab = np.where(np.maximum(dx, dy) < 0, "base", np.where(dx > dy, np.where(F[:, 0] > c[0], "xp", "xn"), np.where(F[:, 1] > c[1], "yp", "yn")))
    def cov(nm):
        return g(r"\n\s+%s\s+t=.*?杯頂俯視覆蓋 (\d+)%%" % nm, s)
    c0, cb, c1, c2 = cov("closed_pre_release"), cov("before_move"), cov("after_move"), cov("end")
    P0, P1 = Z["snap_closed_pre_release"], Z["snap_end"] if "snap_end" in Z else Z["tet"]
    M0, M1 = Z["snapmug_closed_pre_release"].mean(0), (Z["snapmug_end"] if "snapmug_end" in Z else Z["mug"]).mean(0)
    bx = re.findall(r"\n t=\s*([\d.]+) .*?箱位移 \(([-\d]+),([-\d]+),([-\d]+)\)", s.replace("\nt=", "\n t="))
    B1 = np.array([float(x) for x in bx[-1][1:]]) / 1e3 if bx else np.zeros(3)
    D = np.linalg.norm((P1 - B1) - P0, axis=1) * 1e3                       # 相對箱(箱只平移)
    def kabsch(A, B):                                                        # B 對齊到 A(剛體),回傳對齊後的 B
        ca, cb = A.mean(0), B.mean(0); H = (B - cb).T @ (A - ca); U, S_, Vt = np.linalg.svd(H)
        d_ = np.sign(np.linalg.det(Vt.T @ U.T)); R = Vt.T @ np.diag([1, 1, d_]) @ U.T
        return (B - cb) @ R.T + ca, np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))
    P1k, rot = kabsch(P0, P1); Dk = np.linalg.norm(P1k - P0, axis=1) * 1e3     # 去掉整包剛體運動後的形狀變化
    Dm = np.linalg.norm((P1 - M1) - (P0 - M0), axis=1) * 1e3
    sides = " ".join("%s %.0f/%.0f" % (k, np.median(D[lab == k]), np.percentile(D[lab == k], 90)) for k in ("yn", "yp", "xp", "xn", "base"))
    sides += "(剛體對齊後:" + " ".join("%s %.0f/%.0f" % (k, np.median(Dk[lab == k]), np.percentile(Dk[lab == k], 90)) for k in ("yn", "yp", "xp", "xn")) + ",整包轉 %.1f°)" % rot
    sides += "(相對杯:" + " ".join("%s %.0f" % (k, np.median(Dm[lab == k])) for k in ("yn", "yp", "xp", "xn")) + ";杯相對箱 %.0f mm)" % (np.linalg.norm(M1 - B1 - M0) * 1e3)
    bb = lambda P: "%.0fx%.0fx%.0f" % tuple((P.max(0) - P.min(0)) * 1e3)
    drop = (int(c0) - int(c2)) if c0 != "-" and c2 != "-" else "-"
    print("| %s | %s | %s%% → %s%% → %s%% → %s%% | %s | %s | %s → %s | %s / %s |" % (d, g(r"'--plastic_on_fold', '(\d)'", s, d="0"), c0, cb, c1, c2, drop, sides, bb(P0), bb(P1),
          g(r"全程最大:自穿 (\d+)", s), g(r"全程最大:自穿 \d+.*?布穿杯 (\d+)", s)))
