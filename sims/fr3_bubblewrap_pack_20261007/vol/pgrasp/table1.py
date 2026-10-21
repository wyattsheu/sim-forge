#!/usr/bin/env python3
"""usage: python3 pgrasp/table1.py pgrasp/sweep [pgrasp/d40 ...]   階段 1 表(讀 probe_edge.json)"""
import json, sys, os
hdr = ["run", "組", "L mm", "μ", "指間 mm", "掀前指間頂點", "掀中指間 min / 結束", "滑動中位 弧末 / 結束 mm", "滑動最大 mm", "滑動方向 沿邊 / 往鉸點 mm",
       "掉布", "邊長比最大", "布穿指 點 / 深 mm", "自由段過鉸 結束", "達標(不掉 + 中位<5)"]
print("| " + " | ".join(hdr) + " |"); print("|" + "---|" * len(hdr))
for d in sys.argv[1:]:
    J = json.load(open(os.path.join(d, "probe_edge.json")))
    a = J["args"]; tag = os.path.basename(d.rstrip("/"))
    ex = []
    if a.get("fd_mm", 20) != 20: ex.append("D%.0f" % a["fd_mm"])
    if a.get("overhang_mm", 30) != 30: ex.append("懸空%.0f" % a["overhang_mm"])
    if a.get("kR", 0.9) != 0.9: ex.append("kR%.1f" % a["kR"])
    if a.get("fric", 0.8) != 0.8: ex.append("布μ%.1f" % a["fric"])
    if abs(a.get("dt", 1 / 120) - 1 / 120) > 1e-6: ex.append("dt1/%.0f s%d" % (1 / a["dt"], a["solver"]))
    for r in J["rows"]:
        print("| " + " | ".join([tag + ("(" + ",".join(ex) + ")" if ex else ""), r["name"], "%.0f" % r["L"], "%.1f" % r["mu"], "%.1f" % r["gap"], str(r["nG"]),
              "%d / %d" % (r["nb_min"], r["nb_end"]), "%.1f / %.1f" % (r["slip_med_arc"], r["slip_med_end"]), "%.1f" % r["slip_max_max"],
              ("%.1f / %.1f" % (r["slip_dx"], r["slip_dy"])) if "slip_dx" in r else "-",
              ("t=%.2f θ=%.0f°" % (r["drop_t"], r["drop_th"])) if r["drop_t"] else "無", "%.2f" % r["lmax"], "%d / %.1f" % (r["pen_n"], r["pen_d"]),
              "%.0f%%" % (100 * r["past_end"]), "✓" if r["ok"] else "✗"]) + " |")
