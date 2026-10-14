import json, sys, re, os
# usage: python3 peel2/table.py yn|yp DIR...
sd = sys.argv[1]
print("| 組 | 選點 | 重夾 | 綁點 | %s 越線 | 放手後 | 他片 %% | 滑動 中位/最大 mm | 守衛 | 穿杯 | 杯位移 mm | 越過 mm | 鉸點來源 |" % sd)
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for d in sys.argv[2:]:
    log = open(os.path.join(d, "stdout.txt"), errors="replace").read()
    try: g = json.load(open(os.path.join(d, "grasp.json")))
    except Exception: print("|", d, "| 無 grasp.json |"); continue
    s = [x for x in g["summary"] if x["sd"] == sd][0]
    att = re.findall(r"\[%s\] 綁住 (\d+) 個" % sd, log)
    sel = re.findall(r"\[%s\] 選 .*?:v(\d+)(?:\(tip\))?位置 \((-?[\d.]+)" % sd, log)
    rt = re.findall(r"\[%s\] RETRY \d+/\d+:綁 \d+ < \d+ → 上指抬起、換候選 v(\d+)" % sd, log)
    if rt:
        cx = re.findall(r"CAND #\d+ v%s\s+flat x\s+-?\d+ 位置 \(\s*(-?[\d.]+)" % rt[-1], log)
        sel = [(rt[-1], cx[-1] if cx else "?")]
    gd = re.findall(r"\[%s\] 守衛:邊長比最大 ([\d.]+)" % sd, log); ov = re.findall(r"\[%s\] \[peel\] 越過箱壁外緣 ([\d.]+)" % sd, log)
    hs = "state" if re.search(r"\[%s\] \[peel2\] 彎折處偵測 nan" % sd, log) else ("名義" if re.search(r"\[%s\] ★ 彎折處偵測 nan" % sd, log) else "偵測")
    print("| %s | v%s (x %s) | %d | %s | %.0f%% | %.0f%% | %.1f | %.2f/%.2f | %s | %s | %.1f | %s | %s |" % (os.path.basename(d.rstrip("/")), *(sel[0] if sel else ("?", "?")), len(rt), att[-1] if att else "?",
          100*s["cross"], 100*s["cross_rel"], s["oth_pct"], s["slip_med"], s["slip_max"], gd[0] if gd else "無", s["inmug"], s["mug"], ov[0] if ov else "-", hs))
