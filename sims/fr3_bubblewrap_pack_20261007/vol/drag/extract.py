import json, sys, re, os
for d in sys.argv[1:]:
    try: g = json.load(open(os.path.join(d, "grasp.json")))
    except Exception as e: print(d, "no grasp.json", e); continue
    log = open(os.path.join(d, "stdout.txt"), errors="replace").read()
    print("==", d)
    for s in g["summary"]:
        sd = s["sd"]; rows = [r for r in g["rows"] if r["sd"] == sd]
        def at(t):
            c = min(rows, key=lambda r: abs(r["t"] - t)); return c
        rg = at(s["TP0"]); rh = at(s["events"]["held"])
        n_att = re.findall(r"\[%s\] 綁住 (\d+) 個" % sd, log) or re.findall(r"\[%s\] 綁到上指 (\d+)" % sd, log)
        mask = re.findall(r"\[%s\] 綁定遮罩.*" % sd, log); lift = re.findall(r"\[%s\] 先沿.*" % sd, log)
        # measure line nearest held
        th = s["events"]["held"]
        ml = [l for l in log.splitlines() if re.match(r"t= *%.2f " % th, l) or re.match(r"t= *%.1f\d " % th, l)]
        print(" %s 綁點 %s | 越線 held %.0f%% 放手後 %.0f%% | 滑動 中位 %.2f 最大 %.2f | 他片 夾好時 %.1f%% held %.1f%% 總結 %.1f%% 最大 %.0f mm | side 夾好 %s → held %s | 杯 %.1f | pen %s inmug %s inv %s | PASS %s ok %s"
              % (sd, n_att, s["cross"]*100, s["cross_rel"]*100, s["slip_med"], s["slip_max"], rg.get("oth_pct", float("nan")), rh.get("oth_pct", float("nan")), s["oth_pct"], s["oth_max"],
                 rg.get("oth_side"), rh.get("oth_side"), s["mug"], s["pen"], s["inmug"], s["inv"], s["PASS"], {k: v for k, v in s["ok"].items() if not v}))
        for m in mask + lift: print("   ", m.strip())
        for l in ml[:1]: print("   ", l.strip()[:200])
    print(" ", (re.findall(r"⇒ (PASS|FAIL).*", log) or ["no verdict"])[-1][:160], "| EXIT", re.findall(r"EXIT (\d+)", log))
