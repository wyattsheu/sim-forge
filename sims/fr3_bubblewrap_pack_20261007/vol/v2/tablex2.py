#!/usr/bin/env python3
"""[v2x2] x 片第二輪的表:python3 v2/tablex2.py v2/x/E_final v2/x/F_final ...
判準(全部要過):取杯前杯頂覆蓋 <= 10%、xn / xp 放手後 +10 s 翻片角 < 45°、取杯 OK(從抬起算:杯移動 > 150 mm、離開內腔、抬起後布穿杯 0)、布被帶起(抬起時最大、最終)< 15%。
扶杯期間(抬起前)手 1 下指把布推進 kinematic 杯的瞬間穿杯另列(舊 SUMMARY 的「取杯 OK/NG」把它算進去)。"""
import sys, re, os, glob
F = float
def one(d):
    p = os.path.join(d, "stdout.txt")
    if not os.path.exists(p) or not os.path.exists(os.path.join(d, "elapsed.txt")): return None
    s = open(p, errors="ignore").read(); r = dict(run=d.replace("v2/x/", ""))
    for sd in ("xn", "xp"):
        m = re.findall(r"\[%s\] \[table\] after10:翻片角 ([-\d.]+)°.*?越線 (\d+)%%" % sd, s); r[sd] = (F(m[-1][0]), int(m[-1][1])) if m else None
        m = re.findall(r"\[%s\] \[table\] after2:翻片角 ([-\d.]+)°" % sd, s); r[sd + "2"] = F(m[-1]) if m else None
    m = re.findall(r"\[v2x\] 取杯前 杯頂覆蓋 (\d+)%", s); r["cov"] = int(m[-1]) if m else None
    m = re.findall(r"\[extract2\] SUMMARY mode=\w+ 布被帶起 抬起時最大 ([\d.]+)% .*?最終 ([\d.]+)%", s); r["lift"] = (F(m[-1][0]), F(m[-1][1])) if m else None
    m = re.findall(r"★ t=([\d.]+) \[v2\] 手 2 扶杯 [\d.]+ s 結束 → 抬起", s); tl = F(m[-1]) if m else 1e9
    xl = [(F(t), int(n)) for t, n in re.findall(r"\[extract\] t=([\d.]+) .*?布穿杯 (\d+)", s)]
    r["inm_l"] = max([n for t, n in xl if t >= tl - 1e-6] + [0]); r["inm_h"] = max([n for t, n in xl if t < tl - 1e-6] + [0])
    m = re.findall(r"\[extract\] SUMMARY.*?離開內腔 t=(\S+) \| 最終杯心 世界 \(([-\d.]+),([-\d.]+),([-\d.]+)\)", s)
    mv = None
    m0 = re.findall(r"\[extract\] 開始:杯心 \(([-\d.]+),([-\d.]+),([-\d.]+)\)", s)
    if m and m0: mv = sum((F(a) - F(b)) ** 2 for a, b in zip(m[-1][1:], m0[-1])) ** 0.5
    r["ex"] = "OK" if (m and m[-1][0] != "未離開" and r["inm_l"] == 0 and mv and mv > 150) else "NG"
    r["disp"] = " / ".join("%.0f" % F(x) for x in re.findall(r"\[v2x2\] 手 2 重夾好 → .*?鬆手期間位移 ([\d.]+) mm", s)) or "-"
    r["chk"] = " / ".join("%.0f,%.0f" % (F(a), F(b)) for a, b in re.findall(r"\[v2x2\] 合指前 指-布最小距離\(張開→合 掃掠盒\)−y ([-\d.]+) / \+y ([-\d.]+) mm", s)) or "-"
    xs = [F(t) for t in re.findall(r"\[load\] 從第 \d+ 幀\(t=([\d.]+)", s)]; t0 = xs[0] if xs else 0.0
    L = [(F(t), int(a), int(b)) for t, a, b in re.findall(r"^t=\s*([\d.]+) .*?\| 自穿\s+(\d+) \| 布穿杯\s+\d+ \| 反轉\s+(\d+)", s, re.M) if F(t) >= t0]
    r["pen"] = max([x[1] for x in L] + [0]); r["inv"] = max([x[2] for x in L] + [0])
    r["wall"] = open(os.path.join(d, "elapsed.txt")).read().split()[-1]
    ok = (r["cov"] is not None and r["cov"] <= 10 and all(r[k] and r[k][0] < 45 for k in ("xn", "xp")) and r["ex"] == "OK" and r["lift"] and max(r["lift"]) < 15)
    r["pass"] = "✓" if ok else "✗"
    return r
rows = []
for a in sys.argv[1:]:
    ds = sorted(glob.glob(os.path.join(a, "[0-9]*"))) if not os.path.exists(os.path.join(a, "stdout.txt")) else [a]
    rows += [x for x in map(one, ds) if x]
fa = lambda x: "%.0f° / %d%%" % x if x else "-"
print("| run | xn +2 s / +10 s 翻片角(+10 s 越線) | xp +2 s / +10 s 翻片角(+10 s 越線) | 取杯前 杯頂覆蓋 | 取杯(抬起後) | 布被帶起 抬起最大 / 最終 | 穿杯 抬起後 / 扶杯期間 | 手 2 鬆手期間杯位移 mm | 重夾合指前 指-布 mm(−y,+y) | 自穿 / 反轉 max | 達標 | wall s |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    print("| %s | %s | %s | %s | %s | %s | %d / %d | %s | %s | %d / %d | %s | %s |" % (r["run"],
          "%s / %s" % ("%.0f°" % r["xn2"] if r["xn2"] is not None else "-", fa(r["xn"])), "%s / %s" % ("%.0f°" % r["xp2"] if r["xp2"] is not None else "-", fa(r["xp"])),
          "%d%%" % r["cov"] if r["cov"] is not None else "-", r["ex"], "%.1f%% / %.1f%%" % r["lift"] if r["lift"] else "-", r["inm_l"], r["inm_h"], r["disp"], r["chk"], r["pen"], r["inv"], r["pass"], r["wall"]))
