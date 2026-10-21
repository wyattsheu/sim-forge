#!/usr/bin/env python3
# usage: python3 quality/table.py extract4/X1 ... quality/F1 ...   從 stdout.txt grep 判準
import re, sys, os
def g(pat, s, grp=1, d="-"):
    m = re.search(pat, s); return m.group(grp) if m else d
rows = []
for d in sys.argv[1:]:
    s = open(os.path.join(d, "stdout.txt")).read()
    conc = ""
    if os.path.exists(os.path.join(d, "conc.txt")):
        c = [int(x) - 1 for x in re.findall(r"others (\d+)", open(os.path.join(d, "conc.txt")).read())]
        if c: conc = "%.1f/%d" % (sum(c) / len(c), max(c))
    wall = float(g(r"wall ([\d.]+)s", s, d="nan")); tend = max([float(x) for x in re.findall(r"結束 t=\s*([\d.]+)", s)] or [float("nan")])
    q = g(r"quality: (\w+) \| dt 1/(\d+) solver (\d+)", s, 0, "off")
    dt = g(r"dt 1/(\d+)", g(r"quality: [^\n]*", s, 0, ""), d="240"); sol = g(r"solver (\d+)", g(r"quality: [^\n]*", s, 0, ""), d="128")
    yn_b = g(r"\[yn\] 綁住 (\d+) 個頂點", s); yp_b = g(r"\[yp\] 綁住 (\d+) 個頂點", s)
    h2 = re.search(r"\[hand2\] SUMMARY .*? n=(\d+) 越線 pre/0.5/2/lift\+2 = [\d/]*?(\d+)%", s)
    ex = g(r"\[extract\] SUMMARY[^\n]*", s, 0, "")
    guards = re.findall(r"守衛[^\n]*", s)
    gtxt = "沒觸發" if not any(("放手" in x or "放" in x) for x in guards) else "; ".join(x[:60] for x in guards[:2])
    rows.append(dict(
        run=d, q="%s dt1/%s s%s" % (q.split()[1] if q != "off" else "off", dt, sol), wall="%.0f" % wall, sim="%.2f" % tend, ratio="%.2f" % (wall / tend), conc=conc,
        fold=g(r"四折後\(收耳前 t=[\d.]+\)bbox (\S+?);", s), tuck=g(r"收耳後/入箱前 bbox (\S+)", s), closed=g(r"關蓋後 bbox (\S+)", s),
        acc=" ".join("%s%s" % (k, ",".join(x)) for k, *x in re.findall(r"(pre_in|closed|bm|am|end) \w+\(布 (\d+) 杯 (\d+)\)", g(r"驗收:[^\n]*", s, 0, ""))),
        maxpen=g(r"全程最大 自穿 (\d+)", s), mugpen=g(r"全程最大 自穿 \d+ 布穿杯 (\d+)", s), inv=g(r"反轉 (\d+) 邊長比 \[", s), edge=g(r"邊長比 (\[[\d.,]+\]) 體積比", s),
        yn=yn_b, h2n=h2.group(1) if h2 else "-", yn_l2=(h2.group(2) + "%") if h2 else "-",
        yn_end=g(r"yn 越線 (\d+%)", ex), yp=yp_b, yp_117=g(r"G\[yp\] t=117.25 .*?yp 越過折線\s+(\d+%)", s), yp_end=g(r"yp 越線 (\d+%)", ex),
        guard=gtxt, out_t=g(r"t=([\d.]+) \[extract2\] 離箱", s), expen=g(r"布穿杯最大 (\d+)", ex),
        lift=g(r"\[extract2\] SUMMARY[^\n]*?抬起時最大 ([\d.]+%)", s) + " / " + g(r"\[extract2\] SUMMARY[^\n]*?離箱 ([\d.]+%)", s) + " / " + g(r"\[extract2\] SUMMARY[^\n]*?落地 ([\d.]+%)", s),
        cup=g(r"最終杯心 世界 \S+ 箱局部 (\([\d.,\-]+\))", ex), inbox=g(r"布在箱內 ([\d.]+%)", s), exit=g(r"EXIT (\d+)", s)))
cols = list(rows[0].keys())
print("| " + " | ".join(cols) + " |"); print("|" + "---|" * len(cols))
for r in rows: print("| " + " | ".join(str(r[c]) for c in cols) + " |")
