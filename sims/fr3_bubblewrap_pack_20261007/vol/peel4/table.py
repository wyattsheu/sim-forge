import json, sys, re, os, numpy as np
# usage: python3 peel4/table.py yn|yp DIR...   質心/貼蓋用箱局部座標(world − 箱位移 0,200,100;壁外緣 |y|=113.5、開蓋頂 z=129.5)
sd = sys.argv[1]; sg = -1 if sd == "yn" else 1; OFF = np.r_[0, 0.2, 0.1]
print("| 組 | 選點 | 重夾 | 綁點 | %s 越線 | 放手後 | 他片 %% | 滑動 中位/最大 mm | 守衛 | 穿杯 | 杯位移 mm | 越壁 mm | 往下 z 中心 | 凍結 | 質心 y/z 掀完→放手+2s | 貼蓋點 放手前→+2s |" % sd)
print("|" + "---|" * 16)
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
    lay = re.findall(r"\[%s\] \[peel4\] 往下貼蓋.*?z ([\d.]+) → ([\d.]+)" % sd, log)
    fz = re.findall(r"\[peel4\] t=[\d.]+ \[%s\] 往下 w=([\d.]+).*?凍結" % sd, log)
    cen = "-"; lid = "-"
    try:
        z = np.load(os.path.join(d, "wrap.npz")); F = z["flat"]; Fy = (F[:, 1] - F[:, 1].mean()) * 1e3; m = sg * Fy > 71.5
        T = z["traj_t"]; X = z["traj_tet"]
        tp = float(re.search(r"★ t=([\d.]+) \[%s\] peeled" % sd, log).group(1)); th = float(re.search(r"★ t=([\d.]+) \[%s\] held" % sd, log).group(1))
        Q = lambda t: (X[np.argmin(abs(T - t))][m] - OFF) * 1e3
        c = lambda P: "%.0f/%.0f" % (P[:, 1].mean(), P[:, 2].mean())
        nl = lambda P: int(((sg * P[:, 1] > 116.5) & (P[:, 2] < 141.5)).sum())
        cen = "%s → %s" % (c(Q(tp)), c(Q(th + 2))); lid = "%d → %d" % (nl(Q(th)), nl(Q(th + 2)))
    except Exception as e: cen = "err %s" % e
    print("| %s | v%s (x %s) | %d | %s | %.0f%% | %.0f%% | %.1f | %.2f/%.2f | %s | %s | %.1f | %s | %s | %s | %s | %s |" % (os.path.basename(d.rstrip("/")), *(sel[0] if sel else ("?", "?")), len(rt), att[-1] if att else "?",
          100*s["cross"], 100*s["cross_rel"], s["oth_pct"], s["slip_med"], s["slip_max"], gd[0] if gd else "無", s["inmug"], s["mug"], ov[0] if ov else "-",
          ("%s→%s" % lay[0]) if lay else "-", ("w=" + fz[0]) if fz else "無", cen, lid))
