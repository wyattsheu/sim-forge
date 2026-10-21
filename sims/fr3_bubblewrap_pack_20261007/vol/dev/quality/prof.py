#!/usr/bin/env python3
# usage: prof.py progfile   每 10 s 取樣的「epoch ... t= X」→ 各段 wall 與 wall/sim
import re, sys
S = []
for ln in open(sys.argv[1]):
    m = re.match(r"(\d+) .*?t=\s*([\d.]+)", ln)
    if m: S.append((int(m.group(1)), float(m.group(2))))
t0 = int(open(sys.argv[1]).readline().split()[0])
segs = [("啟動→四折+收耳 0~17.5", 0, 17.5), ("入箱/關蓋/搬/開蓋 17.5~46.5", 17.5, 46.5), ("yn 規劃停頓 46.53", 46.5, 46.6),
        ("yn 抓/掀/手2 46.6~82", 46.6, 82.0), ("yp 規劃停頓 82.03", 82.0, 82.1), ("yp+取杯 82.1~129.6", 82.1, 129.6)]
def wall_at(ts):   # 第一個 sim t > ts 的取樣時刻
    for w, t in S:
        if t > ts: return w
    return S[-1][0] + 10
prev = t0
for nm, a, b in segs:
    w = wall_at(b) if b < 129 else S[-1][0] + 10
    print("%-28s wall %4d s  sim %5.1f s  倍率 %s" % (nm, w - prev, b - a, ("%.1f" % ((w - prev) / (b - a))) if b - a > 1 else "-"))
    prev = w
