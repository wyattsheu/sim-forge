#!/usr/bin/env python3
"""[v2x] x 片 + 取杯段的表:python3 v2/tablex.py v2/x/A_fast [v2/x/B_fast ...]
每次一列:yp 放手後 10 s(續跑時在 x 片開始那一刻量)、xn / xp 做法與結果、取杯前杯頂覆蓋、取杯、布被帶起、穿杯、牆鐘。
判準:取杯前杯頂覆蓋 <= 10%、取杯 OK、布被帶起(抬起時最大、最終)< 15%。"""
import sys, re, os, glob
F = lambda x: float(x)
def one(d):
    p = os.path.join(d, "stdout.txt")
    if not os.path.exists(p): return None
    s = open(p, errors="ignore").read(); r = dict(run=d)
    m = re.findall(r"\[yp\] \[table\] after10:翻片角 ([-\d.]+)°.*?越線 (\d+)%", s); r["yp10"] = "%.0f° / %s%%" % (F(m[-1][0]), m[-1][1]) if m else "-"
    for sd in ("xn", "xp"):
        x = {}
        m = re.search(r"\[%s\] \[v2x\] 拆膠帶 [\d.]+ s 後越線 (\d+)%% → (\S+);鉸點 v\d+ x ([-\d.]+).*?材料長 L ([\d.]+) mm" % sd, s)
        if m: x.update(how=m.group(2), cr=m.group(1), L=m.group(4))
        else:
            m = re.search(r"\[%s\] \[v2\] 拆膠帶 [\d.]+ s 後(只開一部分|已自己攤開)\(越線 (\d+)%%" % sd, s) or re.search(r"\[%s\] \[v2\] 拆膠帶 [\d.]+ s 後越線 (\d+)%%" % sd, s)
            if m and m.lastindex == 2: x.update(how="斜靠沒夾" if m.group(1) == "只開一部分" else "自己攤開", cr=m.group(2))
            elif m: x.update(how="寬指夾翻", cr=m.group(1))
        m = re.findall(r"\[%s\] \[table\] after10:翻片角 ([-\d.]+)°" % sd, s); x["a10"] = "%.0f°" % F(m[-1]) if m else "-"
        m = re.findall(r"\[%s\] \[v2\] \S+ released:越線 (\d+)%% \| 他片 >10mm ([\d.]+)%% \| 杯位移 ([\d.]+) mm \| 穿杯 (\d+) \| 自穿 (\d+) \| 杯頂覆蓋 (\d+)%%" % sd, s)
        if m: x.update(crE=m[-1][0], cov=m[-1][5], oth=m[-1][1])
        else:
            m = re.findall(r"\[%s\] released\n.*?越過折線\s+(\d+)%%" % sd, s); x["crE"] = m[-1] if m else "-"
        r[sd] = x
    m = re.findall(r"\[v2x\] 取杯前 杯頂覆蓋 (\d+)%", s); r["cov"] = int(m[-1]) if m else None; r["covs"] = ""
    if r["cov"] is None:                                                       # 舊 log 沒有這行 → 用 xp 片結束時的杯頂覆蓋(標 *)
        m = re.findall(r"\[xp\] \[v2\] \S+ released:.*?杯頂覆蓋 (\d+)%", s) or re.findall(r"杯頂俯視覆蓋 (\d+)%", s)
        if m: r["cov"] = int(m[-1]); r["covs"] = "*"
    m = re.findall(r"\[extract\] SUMMARY.*取杯 (OK|NG)", s); r["ex"] = m[-1] if m else "-"
    m = re.findall(r"\[extract2\] SUMMARY mode=\w+ 布被帶起 抬起時最大 ([\d.]+)% .*?最終 ([\d.]+)%", s); r["lift"] = (F(m[-1][0]), F(m[-1][1])) if m else None
    m = re.findall(r"布穿杯最大 (\d+)", s); r["inm"] = m[-1] if m else "-"
    xs = [F(t) for t in re.findall(r"\[load\] 從第 \d+ 幀\(t=([\d.]+)", s)]; t0 = xs[0] if xs else 0.0
    pens = [int(a) for t, a in re.findall(r"^t=\s*([\d.]+) .*?\| 自穿\s+(\d+)", s, re.M) if F(t) >= t0]; r["pen"] = max(pens) if pens else "-"
    m = re.findall(r"^EXIT (-?\d+)", s, re.M); r["exit"] = m[-1] if m else "-"
    e = os.path.join(d, "elapsed.txt"); r["wall"] = open(e).read().split()[-1] if os.path.exists(e) else "-"
    ok = r["cov"] is not None and r["cov"] <= 10 and r["ex"] == "OK" and r["lift"] is not None and max(r["lift"]) < 15.0
    r["pass"] = "✓" if ok else "✗"
    return r
rows = []
for a in sys.argv[1:]:
    ds = sorted(glob.glob(os.path.join(a, "[0-9]*"))) if not os.path.exists(os.path.join(a, "stdout.txt")) else [a]
    rows += [x for x in map(one, ds) if x]
print("| run | yp +10s 翻片角 / 越線 | xn 做法 | xn 拆膠帶後越線 → 片結束越線 | xn +10s 翻片角 | xp 做法 | xp 拆膠帶後越線 → 片結束越線 | xp +10s 翻片角 | 取杯前 杯頂覆蓋 | 取杯 | 布被帶起 抬起最大 / 最終 | 取杯 布穿杯 | 續跑段 自穿 max | 達標 | EXIT | wall s |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    c = []
    for sd in ("xn", "xp"):
        x = r[sd]; c += [x.get("how", "-"), "%s%% → %s%%" % (x.get("cr", "-"), x.get("crE", "-")), x.get("a10", "-")]
    print("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (r["run"], r["yp10"], *c, "%d%%%s" % (r["cov"], r["covs"]) if r["cov"] is not None else "-", r["ex"],
          "%.1f%% / %.1f%%" % r["lift"] if r["lift"] else "-", r["inm"], r["pen"], r["pass"], r["exit"], r["wall"]))
