#!/usr/bin/env python3
"""speed2/table3.py NAME [NAME2 ...]  → markdown:每個指標 3 次值 + 平均 [範圍](NAME/1..N/stdout.txt,全用 grep)。
多個 NAME 時每個 NAME 一段(續跑 vs 整鏈對照用)。"""
import re, sys, os, glob
import numpy as np
def g(pat, s, k=1):
    m = re.search(pat, s); return m.group(k) if m else None
def f(x):
    try: return float(x)
    except Exception: return None
def metrics(s, d):
    r = {}
    for sd in ("yn", "yp"):
        r[sd + " 綁點"] = f(g(r"\[%s\] 綁住 (\d+) 個頂點" % sd, s))
        m = re.search(r"\[%s\] ATTACH 綁 \S+ 點 \| 越線 名義 (\w+)%% / 實測彎折 \w+%%.*?→ 放手後 名義 (\w+)%%" % sd, s)
        r[sd + " 越線 %"] = f(m.group(1)) if m else None; r[sd + " 放手後 %"] = f(m.group(2)) if m else None
        m = re.search(r"\[%s\] 夾到 .*? 他片 >10mm \d+\(([\d.]+)%%\).*?杯位移最大 ([\d.]+) mm .*?穿杯 (\d+)" % sd, s)
        r[sd + " 他片 %"] = f(m.group(1)) if m else None
        if sd == "yn": r["yn 杯位移 mm"] = f(m.group(2)) if m else None
        r[sd + " 穿杯"] = f(m.group(3)) if m else None
    h2 = re.search(r"\[hand2\] SUMMARY yn mode=\w+ pos=\S+ n=(\d+) 越線 pre/0.5/2/lift\+2 = [\w.]+/[\w.]+/[\w.]+/([\w.]+)%", s)
    r["手2 綁點"] = f(h2.group(1)) if h2 else None; r["yn lift+2 越線 %"] = f(h2.group(2)) if h2 else None
    gd = re.findall(r"★ t=([\d.]+) \[(\w+)\] 守衛", s)
    r["守衛"] = ",".join("%s@%s" % (b, a) for a, b in gd) if gd else "沒觸發"
    r["全程 布穿杯"] = f(g(r"全程最大 自穿 \d+ 布穿杯 (\d+)", s))
    r["全程 自穿"] = f(g(r"全程最大 自穿 (\d+)", s))
    ex = re.search(r"\[extract2\] SUMMARY mode=\w+ 布被帶起 抬起時最大 ([\d.]+)% \| 離箱 ([\d.]+)% \| 落地 ([\d.]+)%", s)
    r["取杯 布穿杯"] = f(g(r"\[extract\] SUMMARY .*?布穿杯最大 (\d+)", s))
    r["布被帶起 抬起 %"] = f(ex.group(1)) if ex else None; r["布被帶起 落地 %"] = f(ex.group(3)) if ex else None
    m = re.search(r"wall ([\d.]+)s / sim ([\d.]+)s = ([\d.]+)", s)
    r["迴圈 wall s"] = f(m.group(1)) if m else None; r["sim 結束 t"] = f(m.group(2)) if m else None
    lo = f(g(r"\[load\] 從第 \d+ 幀\(t=([\d.]+)", s))
    r["sim 段長 s"] = (r["sim 結束 t"] - (lo or 0.0)) if r["sim 結束 t"] is not None else None
    r["wall/sim(迴圈)"] = r["迴圈 wall s"] / r["sim 段長 s"] if r["迴圈 wall s"] and r["sim 段長 s"] else None
    el = os.path.join(d, "elapsed.txt")
    r["總牆鐘 s(含啟動)"] = f(open(el).read().split()[1]) if os.path.exists(el) else None
    r["規劃停頓 s(yn/yp rank)"] = "/".join(re.findall(r"算了 ([\d.]+)s", s)) or None
    r["EXIT"] = g(r"EXIT (\d+)", s)
    return r
def fmt(v):
    if v is None: return "-"
    if isinstance(v, str): return v
    if v != v: return "nan"
    return ("%.0f" % v) if abs(v - round(v)) < 1e-9 or abs(v) >= 100 else ("%.2f" % v if abs(v) < 10 else "%.1f" % v)
for name in sys.argv[1:]:
    runs = sorted([d for d in glob.glob(os.path.join(name, "*")) if os.path.isdir(d) and os.path.exists(os.path.join(d, "stdout.txt"))])
    R = [metrics(open(os.path.join(d, "stdout.txt"), errors="ignore").read(), d) for d in runs]
    if not R: continue
    cmd = open(os.path.join(runs[0], "stdout.txt"), errors="ignore").readline().strip()
    print("### %s(%d 次)\n\n`%s`\n" % (name, len(R), cmd[:600]))
    print("| 指標 | " + " | ".join(os.path.basename(d) for d in runs) + " | 平均 [範圍] |"); print("|---" * (len(R) + 2) + "|")
    for k in R[0]:
        vs = [r.get(k) for r in R]; nums = [v for v in vs if isinstance(v, float) and v == v]
        agg = ("%s [%s, %s]" % (fmt(float(np.mean(nums))), fmt(min(nums)), fmt(max(nums)))) if nums and len(nums) == len(vs) else "-"
        print("| %s | %s | %s |" % (k, " | ".join(fmt(v) for v in vs), agg))
    print()
