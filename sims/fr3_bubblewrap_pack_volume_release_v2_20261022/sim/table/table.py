#!/usr/bin/env python3
"""table/table.py DIR... → markdown 表(桌面掀開)。DIR 可以是 run3 的批次(table/B → table/B/1,2,3)或單次(table/B/1)。
資料:<run>/grasp.json 的 summary[*].ut(pre / after0.5 / after2 / after10)+ stdout.txt(綁點、指間、守衛、wall)。"""
import sys, os, json, re, glob
import numpy as np
def runs(d):
    return sorted(glob.glob(os.path.join(d, "[0-9]*"))) if not os.path.exists(os.path.join(d, "grasp.json")) and glob.glob(os.path.join(d, "[0-9]*")) else [d]
def f(x, fmt="%.0f"):
    return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else fmt % x
H = ["run", "片", "夾法", "綁點 / 指間", "掀中指間 min", "守衛", "鉸點 y / L mm", "放手前 翻片角 / 越線", "+2s 翻片角", "+2s 越線", "+2s 質心 往外/高",
     "+10s 翻片角", "+10s 越線", "+10s 質心 往外/高", "+10s 主片在鉸線外", "他片 >10mm(10s)", "杯位移 mm 夾好時 / 10s", "穿杯 max 夾取段 / 掀開起", "杯頂覆蓋(10s)", "達標", "wall s"]
print("| " + " | ".join(H) + " |"); print("|" + "---|" * len(H))
for d in sys.argv[1:]:
    for r in runs(d):
        so = open(os.path.join(r, "stdout.txt"), errors="ignore").read() if os.path.exists(os.path.join(r, "stdout.txt")) else ""
        if not os.path.exists(os.path.join(r, "grasp.json")):
            print("| %s | 沒跑完 |" % r + " |" * (len(H) - 2)); continue
        J = json.load(open(os.path.join(r, "grasp.json")))
        wide = "--pick_mode wide" in so.split("\n")[0]
        el = open(os.path.join(r, "elapsed.txt")).read().split()[-1] if os.path.exists(os.path.join(r, "elapsed.txt")) else "-"
        for s in J["summary"]:
            sd = s["sd"]; u = s.get("ut") or {}
            natt = re.findall(r"\[%s\] 綁住 (\d+) 個頂點" % sd, so); ngr = re.findall(r"\[%s\] 夾好:指面之間.*?布頂點 (\d+) 個" % sd, so)
            rows = [q for q in J["rows"] if q["sd"] == sd and s.get("TP0") and s["TP0"] - 1e-6 <= q["t"] <= s["events"].get("held", 1e9)]
            nmin = min([q["ngrip"] for q in rows]) if rows else None
            gd = re.findall(r"t=([\d.]+) \[%s\] 守衛:" % sd, so)
            mg = [q["mug_d"] for q in J["rows"] if q["sd"] == sd and s.get("TP0") and q["t"] <= s["TP0"] - 0.9]
            _t1 = (s.get("TP0") or 1e9) - 0.9
            inm = "%d / %d" % (max([q["inmug"] for q in J["rows"] if q["sd"] == sd and q["t"] < _t1] + [0]), max([q["inmug"] for q in J["rows"] if q["sd"] == sd and q["t"] >= _t1] + [0]))
            pre, a2, a10 = u.get("pre", {}), u.get("after2", {}), u.get("after10", {})
            ok = a10 and a10["ang"] < 45 and a10["cross"] >= 80
            print("| " + " | ".join([r, sd, "寬指 純摩擦" if wide else "綁定", "%s / %s" % (natt[-1] if natt else "-", ngr[-1] if ngr else "-"),
                  f(nmin, "%d") if wide else "(綁定)", ("觸發 t=" + gd[0]) if gd else "沒觸發",
                  "%s / %s" % (f(u.get("hy", np.nan) * 1e3, "%.1f"), f(u.get("L", np.nan) * 1e3, "%.1f")),
                  "%s° / %s%%" % (f(pre.get("ang")), f(pre.get("cross"))),
                  f(a2.get("ang"), "%.0f°"), f(a2.get("cross"), "%.0f%%"), "%s / %s" % (f(a2.get("oc")), f(a2.get("zc"))),
                  f(a10.get("ang"), "%.0f°"), f(a10.get("cross"), "%.0f%%"), "%s / %s" % (f(a10.get("oc")), f(a10.get("zc"))), f(a10.get("out"), "%.0f%%"),
                  f(a10.get("oth"), "%.1f%%"), "%s / %s" % (f(mg[-1] if mg else None, "%.1f"), f(a10.get("mug"), "%.1f")), inm, f(a10.get("cov"), "%.0f%%"),
                  "✓" if ok else "✗", el]) + " |")
