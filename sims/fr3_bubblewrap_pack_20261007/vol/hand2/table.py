#!/usr/bin/env python3
"""python3 hand2/table.py yn hand2/P1 hand2/A1 ...  → markdown 表(grep stdout.txt)"""
import re, sys
sd = sys.argv[1]
print("| 組 | 模式 | 綁點(手1) | 壓板/方塊 (x,y,z) mm | 接觸/綁 | %s 越線 放手前/+0.5/+2/抬起+2 s %% | 質心 y mm | 壁外 %% | 他片 %% | 穿杯 | 達標 |" % sd)
print("|---|---|---|---|---|---|---|---|---|---|---|")
for d in sys.argv[2:]:
    s = open(d + "/stdout.txt").read(); nm = d.rstrip("/").split("/")[-1]
    m = re.search(r"\[hand2\] SUMMARY %s mode=(\w+) pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\) n=(\d+) 越線 pre/0.5/2/lift\+2 = ([-\d.na]+)/([-\d.na]+)/([-\d.na]+)/([-\d.na]+)%% 質心y = ([-\d.na]+)/([-\d.na]+)/([-\d.na]+)/([-\d.na]+) 壁外 = ([-\d.na]+)/([-\d.na]+)/([-\d.na]+)/([-\d.na]+)%%" % sd, s)
    a = re.search(r"\[%s\] ATTACH 綁 (\d+) 點" % sd, s)
    o = re.search(r"\[%s\] 夾到.*?他片 >10mm \d+\(([\d.]+)%%\)" % sd, s)
    p = re.search(r"\[%s\] 夾到.*?穿杯 (\d+)" % sd, s)
    if not m: print("| %s | – | %s | 未完成 |||||||" % (nm, a.group(1) if a else "-")); continue
    g = m.groups(); x = [float(v) for v in g[5:9]]
    ok = x[1] >= 50 and x[2] >= 50 and x[3] >= 50 and o and float(o.group(1)) < 20 and p and p.group(1) == "0"
    print("| %s | %s | %s | (%s,%s,%s) | %s | %s | %s | %s | %s | %s | %s |" % (nm, g[0], a.group(1) if a else "-", g[1], g[2], g[3], g[4],
          "/".join(g[5:9]), "/".join(g[9:13]), "/".join(g[13:17]), o.group(1) if o else "-", p.group(1) if p else "-", "✓" if ok else "✗"))
