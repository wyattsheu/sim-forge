#!/usr/bin/env python3
"""usage: python3 pgrasp/table2.py DIR [DIR...]   階段 2 表(grep stdout.txt + wrap.npz)。DIR 可以是 matsweep/E2e3_d0.1(綁定版對照)"""
import re, sys, os, numpy as np
OFF = np.r_[0, 0.2, 0.1]; WALL = -113.5
def g(p, s, k=1, d="-"):
    m = re.search(p, s); return m.group(k) if m else d
def atrel(d, t):
    f = os.path.join(d, "wrap.npz")
    if not os.path.exists(f) or t != t: return "-"
    Z = np.load(f); T = Z["traj_t"]; i = int(np.searchsorted(T, t - 1e-6)) - 1
    if i < 0: return "-"
    F = Z["flat"]; yn = (F[:, 1] - F[:, 1].mean()) < -0.0715; P = (Z["traj_tet"][i][yn] - OFF) * 1e3
    return "%.0f / %.0f%%" % (P[:, 1].mean(), 100 * (P[:, 1] < WALL).mean())
hdr = ["run", "夾法", "夾好 指間頂點(外擴2.5mm)", "掀中指間 max", "掉布 t(段)", "滑動中位 掉前最大 mm", "抓取段 邊長比最大", "布穿指 上/下 mm",
       "他片 >10mm(held)", "杯位移 mm", "越線 peel 2/3 → held", "越壁到位 質心 y", "放手 t", "放手瞬間 質心 y / 壁外", "+10s 越線(全片)", "+10s 壁外", "+10s 質心 y", "達標"]
print("| " + " | ".join(hdr) + " |"); print("|" + "---|" * len(hdr))
for d in sys.argv[1:]:
    s = open(os.path.join(d, "stdout.txt"), errors="ignore").read(); nm = d.rstrip("/").replace("pgrasp/", "")
    wide = "--pick_mode wide" in s
    how = ("寬指 %s×%s 指間 %.1f" % (g(r"--wide_mm (\S+)", s), g(r"--wide_depth_mm (\S+)", s, d="20"), 4 - float(g(r"--wide_squeeze_mm (\S+)", s, d="1")))) if wide else "綁定(20mm 指)"
    grip = g(r"★ t=[\d.]+ \[yn\] 夾好:.*?的布頂點 (\d+) 個", s); m25 = g(r"\[yn\] 參考:足跡外擴 2.5mm、離指面 <=2.5mm 的布頂點 (\d+) 個", s)
    att = g(r"\[yn\] 綁住 (\d+) 個頂點", s)
    G = re.findall(r"G\[yn\] t=\s*([\d.]+) yn (.{22}) .*?\| 夾到\s+(\d+) \| 滑動 中位 (\S+) 最大 (\S+) \| yn 越過折線\s+(\d+)%.*?他片 >10mm\s+\d+\(([\d.]+)%\).*?\| 杯位移 ([\d.]+)", s)
    TG = float(g(r"★ t=([\d.]+) \[yn\] 夾好", s, d="nan"))
    pe = [r for r in G if float(r[0]) > TG and not r[1].startswith("release")]
    drop = next((r for r in pe if r[2] == "0"), None)
    pre = [r for r in pe if drop is None or float(r[0]) < float(drop[0])]
    sm = [float(r[3]) for r in pre if r[3] != "-"]
    TR = float(g(r"★ t=([\d.]+) \[yn\] \[plastic\] 放手後 0.5s", s, d="nan")) - 0.5
    rows = [(float(m[0]), float(m[1])) for m in re.findall(r"\nt=\s*([\d.]+) .*?邊長比 \[[\d.]+,([\d.]+)\]", s)]
    lr = max([r[1] for r in rows if TG - 10 <= r[0] <= (TR if TR == TR else 1e9)] or [float("nan")])
    jaw = g(r"\[jaw3\] SUMMARY[^:]*:(.*)", s).strip()
    up = g(r"up (-?[\d.]+)", jaw); lo = g(r"lo (-?[\d.]+)", jaw)
    held = next((r for r in G if r[1].startswith("hold peeled")), None)
    p23 = g(r"★ t=[\d.]+ \[yn\] peel_2_3\n\s+G\[yn\].*?yn 越過折線\s+(\d+)%", s)
    W = {k: re.search(r"\[yn\] \[plastic\] 放手後 %ss:越線 (\S+?)%%\S全片 (\d+)%%\S\s*\| 壁外 (\d+)%% \| 質心 y ([-\d.]+)" % k, s) for k in ("0.5", "2", "10")}
    w10 = W["10"]
    ok = "-"
    if w10:
        ok = "✓" if (float(w10.group(1)) >= 50 and float(w10.group(3)) >= 30) else "✗"
    cols = [nm, how, ("%s(%s)" % (grip, m25)) + ((" / 綁 %s" % att) if att != "-" else ""), str(max([int(r[2]) for r in pe] or [0])),
            ("%.2f(%s)" % (float(drop[0]), drop[1].strip())) if drop else "無", ("%.1f" % max(sm)) if sm else "-", "%.2f" % lr,
            "%s / %s" % (up, lo), (held[6] + "%") if held else "-", max([r[7] for r in pe], key=float) if pe else "-",
            "%s%% → %s%%" % (p23, held[5] if held else "-"), g(r"\[peel3\] t=[\d.]+ \[yn\] 越壁到位:.*?質心 y=([-\d.]+)", s), "%.2f" % TR if TR == TR else "-", atrel(d, TR),
            ("%s%%(%s%%)" % (w10.group(1), w10.group(2))) if w10 else "-", (w10.group(3) + "%") if w10 else "-", w10.group(4) if w10 else "-", ok]
    print("| " + " | ".join(cols) + " |")
