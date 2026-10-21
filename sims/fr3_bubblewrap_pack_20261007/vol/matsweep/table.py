#!/usr/bin/env python3
"""usage: python3 matsweep/table.py DIR [DIR...]   材料掃描判讀(grep stdout.txt + wrap.npz 算垂下角)
垂下角 = 箱壁外緣頂角 (y=-113.5, z=130.5 mm,箱局部) → yn 片壁外那段(y<-113.5)質心 的向量,與「垂直向下」的夾角:
0° = 貼著箱壁外側垂直垂下,90° = 水平往外(躺在打開的蓋上),>90° = 往上翹。"""
import re, sys, os, numpy as np
OFF = np.r_[0, 0.2, 0.1]; WALL = -113.5; CORNER = np.r_[WALL, 130.5]
def g(p, s, k=1, d="-"):
    m = re.search(p, s); return m.group(k) if m else d
def droop(Z, t):
    T = Z["traj_t"]
    if not len(T) or t > T[-1] + 0.3: return float("nan"), 0
    i = int(np.argmin(abs(T - t))); F = Z["flat"]; yn = (F[:, 1] - F[:, 1].mean()) < -0.0715
    P = (Z["traj_tet"][i][yn] - OFF) * 1e3; o = P[:, 1] < WALL
    if o.sum() < 3: return float("nan"), int(o.sum())
    v = P[o][:, 1:].mean(0) - CORNER
    return float(np.degrees(np.arctan2(-v[0], -v[1]))), int(o.sum())
def atrel(Z, t):                                                     # 放手瞬間(TR 前一個取樣)yn 片質心 y / 壁外 %
    T = Z["traj_t"]; i = int(np.searchsorted(T, t - 1e-6)) - 1
    if i < 0: return "-"
    F = Z["flat"]; yn = (F[:, 1] - F[:, 1].mean()) < -0.0715; P = (Z["traj_tet"][i][yn] - OFF) * 1e3
    return "%.0f / %.0f%%" % (P[:, 1].mean(), 100 * (P[:, 1] < WALL).mean())
hdr = ["組", "E", "面密度", "四折 bbox", "關蓋後超出 布/杯", "開蓋後超出 布", "包裝段 自穿最大", "包裝段 反轉最大", "包裝段 布穿杯", "開蓋後杯頂覆蓋",
       "yn 綁點", "守衛", "抓取段 邊長比最大", "杯位移最大 mm", "掀完越線(held)", "放手 t", "放手瞬間 質心 y / 壁外",
       "+2s 越線(全片)", "+2s 壁外", "+2s 質心 y", "+2s 垂下角", "+10s 越線(全片)", "+10s 壁外", "+10s 質心 y", "+10s 垂下角", "+10s 布穿杯", "達標", "影片"]
print("| " + " | ".join(hdr) + " |"); print("|" + "---|" * len(hdr))
for d in sys.argv[1:]:
    s = open(os.path.join(d, "stdout.txt"), errors="ignore").read(); nm = os.path.basename(d.rstrip("/"))
    E = g(r"'young': ([\d.e+]+)", s); D = g(r"'areal': ([\d.]+)", s)
    rows = [(float(m[0]), m[1], int(m[2]), int(m[3]), int(m[4]), float(m[5])) for m in
            re.findall(r"\nt=\s*([\d.]+) (.{24}).*?\| 自穿\s+(\d+) \| 布穿杯\s+(\d+) \| 反轉\s+(\d+) \|.*?邊長比 \[[\d.]+,([\d.]+)\]", s)]
    TG0 = float(g(r"open hold 完 ([\d.]+)", s, d="45.9"))
    pk = [r for r in rows if r[0] <= TG0]
    rel = re.findall(r"★ t=([\d.]+) \[yn\] \[plastic\] 放手後 ([\d.]+)s\S\s*越線 (\S+?)%\S全片 (\d+)%\S\s*\| 壁外 (\d+)% \| 質心 y ([-\d.]+) mm \| 自穿 (\d+) \| 布穿杯 (\d+) \| 杯位移 ([\d.]+)", s)
    W = {int(float(r[1])) if float(r[1]) >= 1 else 0: r for r in rel}
    TR = float(W[2][0]) - 2 if 2 in W else float(g(r"★ t=([\d.]+) \[yn\] released", s, d="nan"))
    gr = [r for r in rows if TG0 < r[0] <= (TR if TR == TR else 1e9)]
    guards = re.findall(r"★ t=([\d.]+) \[yn\] 守衛:邊長比最大 ([\d.]+)", s)
    Z = np.load(os.path.join(d, "wrap.npz")) if os.path.exists(os.path.join(d, "wrap.npz")) else None
    def W_(k, j): return W[k][j] if k in W else "-"
    def ang(k):
        if Z is None or TR != TR: return "-"
        a_, n_ = droop(Z, TR + k); return "%.0f°(%d 點)" % (a_, n_) if a_ == a_ else "nan(%d 點)" % n_
    acc = g(r"驗收:[^\n]*", s, 0, "")
    cl = re.search(r"closed \w+\(布 (\d+) 杯 (\d+)\)", acc); en = re.search(r"end \w+\(布 (\d+) 杯 (\d+)\)", acc)
    held = g(r"G\[yn\] t=\s*[\d.]+ yn hold peeled .*?yn 越過折線\s+(\d+%)", s)
    ok = "-"
    if 10 in W:
        cr = W[10][2]; cr = float(W[10][3]) if cr == "nan" else float(cr)
        pkok = (cl and cl.group(1) == "0" and cl.group(2) == "0") and max([r[3] for r in pk] or [0]) == 0
        ok = ("✓" if (cr >= 50 and float(W[10][4]) >= 30) else "✗") + ("" if pkok else "(包裝壞)")
    cols = [nm, E, D, g(r"四折後\(收耳前 t=[\d.]+\)bbox (\S+?);", s),
            "%s/%s" % (cl.group(1), cl.group(2)) if cl else "-", en.group(1) if en else "-",
            str(max([r[2] for r in pk] or [0])) if pk else "-", str(max([r[4] for r in pk] or [0])) if pk else "-", str(max([r[3] for r in pk] or [0])) if pk else "-",
            g(r"\n\s+end\s+t=.*?杯頂俯視覆蓋 (\d+%)", s, d=g(r"開蓋後 3s:.*?杯頂俯視覆蓋 (\d+%)", s)),
            g(r"\[yn\] 綁住 (\d+) 個頂點", s), ("放手 t=%s(%s)" % guards[0]) if guards else "沒觸發",
            "%.2f" % max([r[5] for r in gr]) if gr else "-", g(r"\[yn\] .*?杯位移最大 ([\d.]+) mm", s), held, "%.2f" % TR if TR == TR else "-", atrel(Z, TR) if (Z is not None and TR == TR) else "-",
            "%s%%(%s%%)" % (W_(2, 2), W_(2, 3)), W_(2, 4) + "%", W_(2, 5), ang(2),
            "%s%%(%s%%)" % (W_(10, 2), W_(10, 3)), W_(10, 4) + "%", W_(10, 5), ang(10), W_(10, 7), ok,
            "vol/matsweep/%s/wrap.mp4" % nm + ("" if "EXIT 0" in s else " (未完成)")]
    print("| " + " | ".join(cols) + " |")
