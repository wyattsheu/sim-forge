import json, sys, re, os, numpy as np
print("| 組 | 選點 | 綁點 | yn 越線 | 放手後 | 他片 % | 滑動 中位/最大 mm | 守衛 | 穿杯 | 杯位移 mm | 越過 mm |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for d in sys.argv[1:]:
    log = open(os.path.join(d, "stdout.txt"), errors="replace").read()
    try: g = json.load(open(os.path.join(d, "grasp.json")))
    except Exception: print("|", d, "| 無 grasp.json |"); continue
    s = [x for x in g["summary"] if x["sd"] == "yn"][0]
    att = re.findall(r"\[yn\] 綁住 (\d+) 個", log); sel = re.findall(r"\[yn\] 選 .*?:v(\d+)(?:\(tip\))?位置 \((-?[\d.]+)", log)
    gd = re.findall(r"\[yn\] 守衛:邊長比最大 ([\d.]+)", log); ov = re.findall(r"\[yn\] \[peel\] 越過箱壁外緣 ([\d.]+)", log)
    print("| %s | v%s (x %s) | %s | %.0f%% | %.0f%% | %.1f | %.2f/%.2f | %s | %s | %.1f | %s |" % (os.path.basename(d.rstrip("/")), *(sel[0] if sel else ("?","?")), att[-1] if att else "?",
          100*s["cross"], 100*s["cross_rel"], s["oth_pct"], s["slip_med"], s["slip_max"], gd[0] if gd else "無", s["inmug"], s["mug"], ov[0] if ov else "-"))
