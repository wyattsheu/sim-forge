#!/usr/bin/env python3
"""usage: python3 extract6/table.py extract6/X1 extract4/X2 ...   → EXTRACT3 v4 欄位的 markdown 表(全用 grep 取數)"""
import re, sys
def g(pat, s, k=1, d="-"):
    m = re.search(pat, s); return m.group(k) if m else d
print("| 次 | yn 綁 / 手2 n | yn 越線 lift+2 → 結束(壁外)| yp 綁 | yp 越線 取杯前(117.25)→ 結束 | 守衛 | 出箱 t | 穿杯最大 | 布被帶起 抬起 / 離箱 / 落地 | 最終杯心 箱局部 mm | 布在箱內 |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for d in sys.argv[1:]:
    s = open(d + "/stdout.txt", errors="ignore").read()
    yn = g(r"\[yn\] 綁住 (\d+) 個頂點", s); yp = g(r"\[yp\] 綁住 (\d+) 個頂點", s)
    h2 = re.search(r"\[hand2\] SUMMARY yn mode=\w+ pos=\S+ n=(\d+) 越線 pre/0.5/2/lift\+2 = [\w.]+/[\w.]+/[\w.]+/([\w.]+)%.*?壁外 = \S+?/\S+?/\S+?/(\d+)%", s)
    ynend = g(r"yn 越線 (\w+)% 壁外", s); ynwo = g(r"yn 越線 \w+% 壁外 (\d+)%", s); ypend = g(r"yp 越線 (\d+)% 壁外", s)
    yp117 = g(r"G\[yp\] t=117.25 .*?yp 越過折線\s+(\d+)%", s)
    gd = re.findall(r"★ t=([\d.]+) \[(\w+)\] 守衛", s); gs = re.findall(r"\[guard_yp\] t=([\d.]+) \[(\w+)\]", s)
    guard = ("放 " + ",".join("%s@%s" % (b, a) for a, b in gd)) if gd else ("先不放 %d 次" % len(gs) if gs else "都沒觸發")
    ex = re.search(r"\[extract2\] SUMMARY mode=\w+ 布被帶起 抬起時最大 ([\d.]+)% \| 離箱 (\S+) \| 落地 (\S+) \|.*?最終杯心 箱局部 \(([^)]*)\).*?布在箱內 ([\d.]+)%", s)
    print("| %s | %s / %s | %s%% → %s%%(%s → %s%%)| %s | %s%% → %s%% | %s | %s | %s | %s | %s | %s |" % (
        d, yn, h2.group(1) if h2 else "-", h2.group(2) if h2 else "-", ynend, h2.group(3) if h2 else "-", ynwo, yp, yp117, ypend, guard,
        g(r"離開內腔 t=([\d.]+|未離開)", s), g(r"布穿杯最大 (\d+)", s),
        "%s / %s / %s" % (ex.group(1) + "%", ex.group(2), ex.group(3)) if ex else "-", "(%s)" % ex.group(4) if ex else "-",
        ex.group(5) + "%" if ex else "-"))
