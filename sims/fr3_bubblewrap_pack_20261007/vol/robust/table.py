import json, sys, re, os
print("| 組 | 選點 | 重夾 | 綁點 | 夾前覆蓋 | yn 越線 | 放手後 | 他片 % | 滑動 中位/最大 mm | 穿杯 | 杯位移 mm |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for d in sys.argv[1:]:
    log = open(os.path.join(d, "stdout.txt"), errors="replace").read()
    try: g = json.load(open(os.path.join(d, "grasp.json")))
    except Exception: print("|", d, "| 無 grasp.json |"); continue
    s = [x for x in g["summary"] if x["sd"] == "yn"][0]
    att = re.findall(r"\[yn\] 綁住 (\d+) 個", log); cov = re.findall(r"\[yn\] 翻面量測集.*杯頂俯視覆蓋 (\d+)%", log)
    ret = re.findall(r"\[yn\] RETRY", log); sel = re.findall(r"\[yn\] 選 .*?:v(\d+)", log)
    fx = re.findall(r"CAND #1 v\d+ +flat x +(-?\d+)", log)
    print("| %s | v%s (x %s) | %d | %s | %s%% | %.0f%% | %.0f%% | %.1f | %.2f/%.2f | %s | %.1f |" % (os.path.basename(d.rstrip("/")), sel[0] if sel else "?", fx[0] if fx else "-", len(ret), att[-1] if att else "?", cov[0] if cov else "?",
          100*s["cross"], 100*s["cross_rel"], s["oth_pct"], s["slip_med"], s["slip_max"], s["inmug"], s["mug"]))
