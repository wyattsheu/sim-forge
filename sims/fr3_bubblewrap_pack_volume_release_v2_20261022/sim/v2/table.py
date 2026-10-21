#!/usr/bin/env python3
"""v2/table.py DIR... → markdown 兩張表(v2 完整流程)。DIR = run3 批次(v2/A → v2/A/1,2,3)或單次(v2/A/1)。
表 1(每次一列):入箱超出 / 膠帶跟隨 / 搬運後覆蓋 / 取出後完整度 / 取杯 / 全程。
表 2(每片一列):夾好指間頂點、掀中最少、放手前 / +10 s 翻片角與越線、他片、杯位移、穿杯、杯頂覆蓋、達標。
資料:<run>/grasp.json(summary[*].ut、rows)、<run>/v2.json(膠帶 / 取出量測)、stdout.txt(驗收、取杯、自穿、wall)。"""
import sys, os, json, re, glob
import numpy as np
def runs(d):
    return sorted(glob.glob(os.path.join(d, "[0-9]*"))) if not os.path.exists(os.path.join(d, "stdout.txt")) and glob.glob(os.path.join(d, "[0-9]*")) else [d]
def f(x, fmt="%.0f"):
    return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else fmt % x
def g(rx, s, k=1, last=True, cast=float):
    m = re.findall(rx, s)
    if not m: return None
    m = m[-1] if last else m[0]
    return cast(m[k - 1] if isinstance(m, tuple) else m)
R = [r for d in sys.argv[1:] for r in runs(d)]
H1 = ["run", "入箱超出 關蓋/搬前/搬後/開蓋(布+杯)", "膠帶點相對杯 搬後 中位/最大 mm", "搬運中 邊長比 max", "搬後 包裹形狀變化(vs 放錨點)中位/p90 mm", "杯頂覆蓋 搬後 / 開蓋後",
      "取出 抬 mm", "取出後 杯頂覆蓋", "放下瞬間 布相對杯 中位/p90 mm", "取出後 布相對杯 中位/p90 mm", "取出後 包裹形狀變化(剛體對齊)中位/p90 mm", "取出後 膠帶點 中位/最大 mm", "取出中 邊長比 max / 穿杯", "取出 達標",
      "掀完 杯頂覆蓋(取杯前)", "取杯", "取杯 布穿杯 / 帶起 抬起/最終", "全程 自穿 max / 穿杯 max", "EXIT", "wall s"]
H2 = ["run", "片", "做法", "夾好 指間頂點", "掀中指間 min", "鉸點 / L mm", "放手前 翻片角 / 越線", "+10s 翻片角", "+10s 越線", "+10s 質心 往外/高",
      "他片 >10mm(10s)", "杯位移 mm 夾好 / 10s", "穿杯 夾取段 / 掀開起", "杯頂覆蓋(10s)", "達標"]
T1, T2 = [], []
for r in R:
    so = open(os.path.join(r, "stdout.txt"), errors="ignore").read() if os.path.exists(os.path.join(r, "stdout.txt")) else ""
    el = open(os.path.join(r, "elapsed.txt")).read().split()[-1] if os.path.exists(os.path.join(r, "elapsed.txt")) else "-"
    ex = g(r"EXIT (-?\d+)", so, cast=int)
    V = json.load(open(os.path.join(r, "v2.json"))) if os.path.exists(os.path.join(r, "v2.json")) else {}
    J = json.load(open(os.path.join(r, "grasp.json"))) if os.path.exists(os.path.join(r, "grasp.json")) else {"summary": [], "rows": []}
    vd = dict((k, int(b) + int(c)) for k, _, b, c in re.findall(r"(\w+) (PASS|WARN|FAIL)\(布 (\d+) 杯 (\d+)\)", so))
    am, op, tk = V.get("after_move", {}), V.get("opened", {}), V.get("tk_done", {})
    lift = g(r"→ 抬 (\d+) mm\(要求", so)
    tkok = bool(tk) and tk.get("cov", 0) >= 0.90 and tk.get("sh_med", 99) < 15     # 判準:杯頂覆蓋 >= 90% 且 包裹形狀變化(剛體對齊)中位 < 15 mm
    xs = g(r"\[extract\] SUMMARY .*?布穿杯最大 (\d+) .*?取杯 (OK|NG)", so, k=2, cast=str)
    xinm = g(r"\[extract\] SUMMARY .*?布穿杯最大 (\d+)", so, cast=int)
    xl = re.findall(r"\[extract2\] SUMMARY mode=\w+ 布被帶起 抬起時最大 ([\d.]+)% .*?最終 ([\d.]+)%", so)
    pen = g(r"全程最大:自穿 (\d+)", so, cast=int); inm = g(r"全程最大:自穿 \d+.*?布穿杯 (\d+)", so, cast=int)
    covs = []
    for s in J["summary"]:
        u = s.get("ut") or {}
        if u.get("after10"): covs.append((s["S0"], u["after10"].get("cov")))
    for sd in ("xn", "xp"):
        c = g(r"\[%s\] \[v2\] (?:自己攤開|斜靠沒夾) released:.*?杯頂覆蓋 (\d+)%%" % sd, so)
        s0 = g(r"t=([\d.]+) \[%s\] \[v2\] 開始掀" % sd, so)
        if c is not None and s0 is not None: covs.append((s0, c))
    covlast = sorted(covs)[-1][1] if covs else None
    T1.append([r, "%s/%s/%s/%s" % tuple(f(vd.get(k), "%d") for k in ("closed", "bm", "am", "end")),
               "%s / %s" % (f(am.get("tape_med"), "%.2f"), f(am.get("tape_max"), "%.2f")), f(am.get("lrmax"), "%.3f"), "%s / %s" % (f(am.get("sh_med"), "%.1f"), f(am.get("sh_p90"), "%.1f")),
               "%s / %s" % (f(100 * am["cov"] if am else None, "%.0f%%"), f(100 * op["cov"] if op else None, "%.0f%%")),
               f(lift, "%.0f"), f(100 * tk["cov"] if tk else None, "%.0f%%"), "%s / %s" % (f(V.get("tk_place", {}).get("cl_med"), "%.1f"), f(V.get("tk_place", {}).get("cl_p90"), "%.1f")), "%s / %s" % (f(tk.get("cl_med"), "%.1f"), f(tk.get("cl_p90"), "%.1f")), "%s / %s" % (f(tk.get("sh_med"), "%.1f"), f(tk.get("sh_p90"), "%.1f")),
               "%s / %s" % (f(tk.get("tape_med"), "%.2f"), f(tk.get("tape_max"), "%.2f")), "%s / %s" % (f(tk.get("lrmax"), "%.3f"), f(tk.get("inmug"), "%d")),
               "✓" if tkok else "✗", f(covlast, "%.0f%%"), xs or "-", "%s / %s" % (f(xinm, "%d"), ("%s%% / %s%%" % xl[-1]) if xl else "-"),
               "%s / %s" % (f(pen, "%d"), f(inm, "%d")), f(ex, "%d"), el])
    T2r = []
    for s in J["summary"]:
        sd = s["sd"]; u = s.get("ut") or {}
        ngr = re.findall(r"\[%s\] 夾好:指面之間.*?布頂點 (\d+) 個" % sd, so)
        rows = [q for q in J["rows"] if q["sd"] == sd and s.get("TP0") and s["TP0"] - 1e-6 <= q["t"] <= s["events"].get("held", 1e9)]
        nmin = min([q["ngrip"] for q in rows]) if rows else None
        mg = [q["mug_d"] for q in J["rows"] if q["sd"] == sd and s.get("TP0") and q["t"] <= s["TP0"] - 0.9]
        _t1 = (s.get("TP0") or 1e9) - 0.9
        im = "%d / %d" % (max([q["inmug"] for q in J["rows"] if q["sd"] == sd and q["t"] < _t1] + [0]), max([q["inmug"] for q in J["rows"] if q["sd"] == sd and q["t"] >= _t1] + [0]))
        pre, a10 = u.get("pre", {}), u.get("after10", {})
        ok = bool(a10) and a10["ang"] < 45 and a10["cross"] >= 80
        T2r.append((s["S0"], [r, sd, "寬指 純摩擦", ngr[-1] if ngr else "-", f(nmin, "%d"), "%s / %s" % (f(u.get("hy", np.nan) * 1e3, "%.1f"), f(u.get("L", np.nan) * 1e3, "%.1f")),
                   "%s° / %s%%" % (f(pre.get("ang")), f(pre.get("cross"))), f(a10.get("ang"), "%.0f°"), f(a10.get("cross"), "%.0f%%"),
                   "%s / %s" % (f(a10.get("oc")), f(a10.get("zc"))), f(a10.get("oth"), "%.1f%%"), "%s / %s" % (f(mg[-1] if mg else None, "%.1f"), f(a10.get("mug"), "%.1f")),
                   im, f(a10.get("cov"), "%.0f%%"), "✓" if ok else "✗"]))
    for sd in ("xn", "xp"):                                                   # 拆膠帶後自己攤開 / 斜靠在杯側(沒夾)
        m = re.findall(r"\[%s\] \[v2\] (自己攤開|斜靠沒夾) (\S+):越線 (\d+)%% \| 他片 >10mm ([\d.]+)%% \| 杯位移 ([\d.]+) mm \| 穿杯 (\d+) \| 自穿 \d+ \| 杯頂覆蓋 (\d+)%%" % sd, so)
        if m:
            q = m[-1][1:]; s0 = g(r"t=([\d.]+) \[%s\] \[v2\] 開始掀" % sd, so) or 0
            T2r.append((s0, [r, sd, "拆膠帶後" + ("自己攤開" if m[-1][0] == "自己攤開" else "斜靠在杯側") + "(沒夾)", "-", "-", "-", "-", "-", q[1] + "%", "-", q[2] + "%", "- / " + q[3], "- / " + q[4], q[5] + "%",
                              "✓(自己攤開)" if int(q[1]) >= 80 else "部分(沒夾)"]))
    T2 += [x[1] for x in sorted(T2r, key=lambda x: x[0])]
for H, T in ((H1, T1), (H2, T2)):
    print("| " + " | ".join(H) + " |"); print("|" + "---|" * len(H))
    for row in T: print("| " + " | ".join(str(x) for x in row) + " |")
    print()
