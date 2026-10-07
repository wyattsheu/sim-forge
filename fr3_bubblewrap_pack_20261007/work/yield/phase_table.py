#!/usr/bin/env python3
"""phase_table.py <xxx_frames.json> — 印出各階段:影格數 / 佔比 / 影片秒數(30fps) / 步數範圍 / sim 秒數(240Hz)"""
import json, sys, collections
m = json.load(open(sys.argv[1]))
fr = m["frames"]; n = len(fr)
print("tune %s  yield_deg %.2f  frames %d  video %.1fs@30fps  last_step %s"
      % (m["tune"], m["yield_deg"], n, n / 30, fr[-1]["step"] if fr else None))
c = collections.OrderedDict()
for f in fr:
    c.setdefault(f["phase"], [0, None, None]); c[f["phase"]][0] += 1
    if c[f["phase"]][1] is None: c[f["phase"]][1] = f["step"]
    c[f["phase"]][2] = f["step"]
print("%-40s %7s %7s %9s %15s %9s" % ("phase", "frames", "share", "video_s", "steps", "sim_s"))
for k, (v, s0, s1) in c.items():
    print("%-40s %7d %6.1f%% %8.1fs %7d-%7d %8.1fs" % (k, v, 100 * v / n, v / 30, s0, s1, (s1 - s0) / 240))
