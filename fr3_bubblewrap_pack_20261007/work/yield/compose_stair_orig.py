#!/usr/bin/env python3
"""compose_stair.py — 把 3D 影格 + 摺線遲滯迴圈 + 即時數值 + 階段名稱合成一支影片。
   compose_stair.py <outdir> [name=stair] [every=1]

★ 影片就是協議在執行(使用者 2026-07-30):看完影片 = 跑完一次檢查。
  三層:過程(階段名稱) / 物理(力矩-角度遲滯迴圈,標降伏點) / 數值(角度+力矩+邊緣推力)
  版面沿用既有的 compose_*.py:matplotlib GridSpec,3D 放左、曲線放右,每幀重畫。
"""
import os, sys, json, csv
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import imageio.v2 as imageio

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK TC","Noto Sans CJK JP","DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUT  = sys.argv[1]
NAME = sys.argv[2] if len(sys.argv) > 2 else "stair"
EVERY= int(sys.argv[3]) if len(sys.argv) > 3 else 1
P = lambda *a: print(*a, flush=True)

M = json.load(open(os.path.join(OUT, NAME + "_frames.json")))
FL = M["flaps"]; YD = M["yield_deg"]; LA = M["lever_arm"]; FCAP = M["force_cap_N"]
rows = list(csv.DictReader(open(os.path.join(OUT, NAME + "_steps.csv"))))
P("讀到 %d 幀中繼資料 / %d 步時序" % (len(M["frames"]), len(rows)))

# 時序抽成陣列(遲滯迴圈用):以 fyp 為主角,沒有就用第一片
KEY = "fyp" if "fyp" in FL else FL[0]
SO  = np.array([float(r["sopen_"+KEY]) for r in rows])
TAU = np.array([float(r["tau_"+KEY])  for r in rows])
PSH = np.array([float(r["push_"+KEY]) for r in rows])
LK  = LA["upper"] if KEY in ("fyp","fyn") else LA["lower"]

rd = imageio.get_reader(os.path.join(OUT, NAME + "_raw.mp4"))
wr = imageio.get_writer(os.path.join(OUT, NAME + "_composed.mp4"),
                        fps=30, quality=7, macro_block_size=1)

GREEN, RED, BLUE, GREY = "#2e7d32", "#c62828", "#1565c0", "#78909c"
n_written = 0
for i, img in enumerate(rd):
    if i % EVERY: continue
    if i >= len(M["frames"]): break
    fm = M["frames"][i]; upto = max(2, min(fm["step"], len(SO)))

    fig = plt.figure(figsize=(15.0, 8.0), facecolor="#0c0e12")
    gs = GridSpec(2, 2, width_ratios=[1.35, 1.0], height_ratios=[1.25, 1.0],
                  wspace=0.16, hspace=0.22)

    # ---- 左:3D 畫面 + 階段名稱
    ax = fig.add_subplot(gs[:, 0]); ax.axis("off"); ax.imshow(img)
    # 容器沒有中文字型 → 中文會變方框。抽出 ASCII 部分(數字/度數)保證可讀
    _ph = fm["phase"]
    _asc = "".join(ch if ord(ch) < 128 else " " for ch in _ph).strip()
    ax.set_title(_asc if _asc else _ph, color="w", fontsize=14, fontweight="bold", pad=8)

    # ---- 右上:摺線力矩-角度 遲滯迴圈
    a1 = fig.add_subplot(gs[0, 1]); a1.set_facecolor("#12151b")
    a1.plot(SO[:upto], TAU[:upto], lw=1.1, color="#4fc3f7")
    a1.plot(SO[upto-1], TAU[upto-1], "o", ms=8, color="#ffeb3b")
    a1.axvline(YD, color=RED, ls="--", lw=1.4)
    a1.text(YD, a1.get_ylim()[1], " yield %.1f deg" % YD, color=RED, fontsize=9, va="top")
    a1.axvline(0, color=GREY, lw=0.8); a1.axhline(0, color=GREY, lw=0.8)
    a1.axvline(180, color=GREEN, ls=":", lw=1.2)
    a1.text(180, a1.get_ylim()[0], "180 deg full open", color=GREEN, fontsize=9, ha="right", va="bottom")
    a1.set_xlabel("open angle (deg)", color="w", fontsize=10)
    a1.set_ylabel("crease moment (N*m)", color="w", fontsize=10)
    a1.set_title("crease hysteresis - %s" % KEY, color="w", fontsize=12)
    a1.set_xlim(-15, 195)
    a1.tick_params(colors="w", labelsize=8); a1.grid(alpha=.18)

    # ---- 右下:即時數值
    a2 = fig.add_subplot(gs[1, 1]); a2.axis("off"); a2.set_facecolor("#12151b")
    y = 0.96
    a2.text(0, y, "LIVE", color="w", fontsize=12, fontweight="bold", va="top"); y -= 0.16
    for f in FL:
        so = fm["sopen"][f]; pu = fm["push"][f]; ti = fm["tilt"][f]
        col = GREEN if abs(so) < 1.0 else ("#ffeb3b" if so < 175 else GREEN)
        a2.text(0, y, "%-4s open %+7.2f  tilt %+6.2f deg" % (f, so, ti),
                color=col, fontsize=11, family="monospace", va="top"); y -= 0.115
        a2.text(0.06, y, "  push %6.3f N*m = edge %5.1f N%s"
                % (pu, abs(pu)/(LA["upper"] if f in ("fyp","fyn") else LA["lower"]),
                   "  AT CAP" if abs(pu)/(LA["upper"] if f in ("fyp","fyn") else LA["lower"]) >= FCAP-0.5 else ""),
                color="#b0bec5", fontsize=9.5, family="monospace", va="top"); y -= 0.135
    a2.text(0, y-0.02, "force cap %.0f N (tau cap up %.2f / low %.2f N*m)"
            % (FCAP, FCAP*LA["upper"], FCAP*LA["lower"]),
            color=GREY, fontsize=9, va="top")
    a2.text(0, y-0.14, "tune %s  yield My0/k = %.2f deg" % (M["tune"], YD),
            color=GREY, fontsize=9, va="top")

    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
    wr.append_data(buf); plt.close(fig); n_written += 1
    if n_written % 200 == 0: P("  合成 %d 幀..." % n_written)

wr.close()
P("WROTE %s_composed.mp4  幀數 %d" % (NAME, n_written))
