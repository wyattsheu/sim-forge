#!/usr/bin/env python3
"""compose_yield.py — yield_run.py 的輸出 -> 一眼看得懂的降伏影片(由 compose_stair_orig.py 改來)
   compose_yield.py <outdir> <name> <out.mp4> [--frames 600] [--split 0.30,0.10,0.60]

跟 compose_stair_orig.py 的差別:
  * 時間軸重排:REST+PRESS+HOLD / RELEASE / SETTLE 三段各自重取樣到固定影格數(預設 30/10/60%)。
    原版是「每個擷取到的影格輸出一幀」,所以影格比例 = 擷取比例(加壓佔 ~95%)。
  * 不放 S1 SETTLE / calib(方向校正會把蓋子推來推去,跟這個實驗無關)。
  * 右上改成「角度 vs 模擬時間」(看得出走平),右下保留力矩–角度遲滯迴圈。
  * 中文字型:容器沒有 CJK 字型 -> 用 fonts/NotoSansTC.ttf;三行字「壓到 X°」「放開」「停在 Y°(起點 Z°)」
    在對應時間出現並保留到片尾。所有數字從 <name>_result.json / <name>_steps.csv 讀。
"""
import os, sys, json, csv, argparse
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.gridspec import GridSpec
import imageio.v2 as imageio

ap = argparse.ArgumentParser()
ap.add_argument("outdir"); ap.add_argument("name"); ap.add_argument("mp4")
ap.add_argument("--frames", type=int, default=600)
ap.add_argument("--split", default="0.30,0.10,0.60")
ap.add_argument("--crop", default="330,130,930,560", help="x0,y0,x1,y1:3D 畫面裁到紙箱附近(原圖紙箱只佔一小塊)")
a = ap.parse_args()
P = lambda *x: print(*x, flush=True)

FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "NotoSansTC.ttf")
fm.fontManager.addfont(FONT)
plt.rcParams["font.family"] = fm.FontProperties(fname=FONT).get_name()
plt.rcParams["axes.unicode_minus"] = False

D, N = a.outdir, a.name
M = json.load(open(os.path.join(D, N + "_frames.json")))
R = json.load(open(os.path.join(D, N + "_result.json")))
KEY = R["key"]; DT = R["physics_dt"]; YD = R["yield_deg"]
rows = list(csv.DictReader(open(os.path.join(D, N + "_steps.csv"))))
SO = np.array([float(r["sopen_" + KEY]) for r in rows])
TAU = np.array([float(r["tau_" + KEY]) for r in rows])
Z, X, Y = R["Z"][KEY], R["X_release"][KEY], R["Y"][KEY]
seg = R["segments"]
press_ph = [k for k in seg if k.startswith("PRESS")][0]
t0s = seg["REST"]["step0"]; rel_s = seg["RELEASE"]["step0"]; end_s = seg["SETTLE"]["step1"]
hold_s = seg["HOLD"]["step0"]
tsim = lambda s: (s - t0s) * DT

# 「停在 Y」出現的時間:之後角度一直留在 Y±0.5° 以內的第一步(量出來的,不是寫死)
inband = np.abs(SO[rel_s:end_s] - Y) < 0.5
bad = np.where(~inband)[0]
stop_s = rel_s + (int(bad[-1]) + 1 if len(bad) else 0)
P("Z %.3f  X %.3f  Y %.3f | 放開 t=%.2fs  進入 Y±0.5° 並留住 t=%.2fs  結束 t=%.2fs"
  % (Z, X, Y, tsim(rel_s), tsim(stop_s), tsim(end_s)))

# ---- 三段影格重取樣
fr = M["frames"]
blocks = [[i for i, f in enumerate(fr) if f["phase"] in ("REST", press_ph, "HOLD")],
          [i for i, f in enumerate(fr) if f["phase"] == "RELEASE"],
          [i for i, f in enumerate(fr) if f["phase"] == "SETTLE"]]
sp = [float(x) for x in a.split.split(",")]
cnt = [int(round(a.frames * s)) for s in sp]; cnt[-1] = a.frames - sum(cnt[:-1])
pick = []
for b, c in zip(blocks, cnt):
    idx = np.linspace(0, len(b) - 1, c).round().astype(int)
    pick += [b[j] for j in idx]
P("raw 影格 REST+PRESS+HOLD %d / RELEASE %d / SETTLE %d -> 輸出 %s"
  % (len(blocks[0]), len(blocks[1]), len(blocks[2]), cnt))
BLK_T = [(tsim(fr[b[0]]["step"]), tsim(fr[b[-1]]["step"])) for b in blocks]

# raw 影片整支讀進來(幾百~一千多幀,1180x800,記憶體可接受)
need = set(pick)
rd = imageio.get_reader(os.path.join(D, N + "_raw.mp4"))
IMG = {i: im for i, im in enumerate(rd) if i in need}
rd.close()

wr = imageio.get_writer(a.mp4, fps=30, quality=8, macro_block_size=1,
                        ffmpeg_params=["-pix_fmt", "yuv420p"])
GREEN, RED, BLUE, GREY, YEL, ORG = "#66bb6a", "#ef5350", "#4fc3f7", "#90a4ae", "#ffeb3b", "#ffa726"
tt_all = tsim(np.arange(len(SO)))
lo = max(t0s, 0)
ymin = min(SO[lo:end_s].min(), Z) - 2.0; ymax = max(SO[lo:end_s].max(), YD + Z) + 3.0
xmin_t, xmax_t = 0.0, tsim(end_s)

for k, fi in enumerate(pick):
    f = fr[fi]; s = min(f["step"], len(SO) - 1); t = tsim(s)
    blk = 0 if k < cnt[0] else (1 if k < cnt[0] + cnt[1] else 2)
    fig = plt.figure(figsize=(15.0, 8.0), facecolor="#0c0e12")
    gs = GridSpec(2, 2, width_ratios=[1.35, 1.0], height_ratios=[1.0, 1.0], wspace=0.14, hspace=0.30,
                  left=0.01, right=0.98, top=0.93, bottom=0.10)

    # ---- 左:3D + 三行字
    cx0, cy0, cx1, cy1 = [int(v) for v in a.crop.split(",")]
    ax = fig.add_subplot(gs[:, 0]); ax.axis("off"); ax.imshow(IMG[fi][cy0:cy1, cx0:cx1])
    live = SO[s]
    ax.text(0.02, 0.98, "蓋子 %s 開啟角  %+.1f°" % (KEY, live), transform=ax.transAxes,
            color="w", fontsize=20, fontweight="bold", va="top",
            bbox=dict(fc="#000000a0", ec="none", pad=6))
    lines = []
    if s >= hold_s:   lines.append(("① 壓到 %.1f°" % X, ORG))
    elif s >= seg[press_ph]["step0"]: lines.append(("加壓中…", ORG))
    if s >= rel_s:    lines.append(("② 放開", BLUE))
    if s >= stop_s:   lines.append(("③ 停在 %.1f°(起點 %.1f°)" % (Y, Z), GREEN))
    for j, (txt, col) in enumerate(lines):
        ax.text(0.02, 0.86 - j * 0.085, txt, transform=ax.transAxes, color=col, fontsize=24,
                fontweight="bold", va="top", bbox=dict(fc="#000000b0", ec="none", pad=5))

    # ---- 右上:角度 vs 時間
    a1 = fig.add_subplot(gs[0, 1]); a1.set_facecolor("#12151b")
    a1.plot(tt_all[lo:end_s], SO[lo:end_s], color="#455a64", lw=1.0)
    a1.plot(tt_all[lo:s + 1], SO[lo:s + 1], color=BLUE, lw=2.0)
    a1.plot(t, live, "o", ms=9, color=YEL)
    for (b0, b1), col in zip(BLK_T, ("#ffa72622", "#4fc3f722", "#66bb6a22")):
        a1.axvspan(b0, b1, color=col, lw=0)
    a1.axhline(Z, color=GREY, ls=":", lw=1.2); a1.text(xmax_t, Z, "起點 %.1f° " % Z, color=GREY,
                                                     fontsize=10, ha="right", va="bottom")
    a1.axhline(Z + YD, color=RED, ls="--", lw=1.2)
    a1.text(0.2, Z + YD, " 降伏角 %.1f°" % YD, color=RED, fontsize=10, va="bottom")
    if s >= hold_s:
        a1.axhline(X, color=ORG, ls="-.", lw=1.0)
        a1.text(0.2, X, " 壓到 %.1f°" % X, color=ORG, fontsize=10, va="bottom")
    if s >= stop_s:
        a1.axhline(Y, color=GREEN, ls="-", lw=1.2)
        a1.text(xmax_t, Y, "停在 %.1f° " % Y, color=GREEN, fontsize=10, ha="right", va="top")
    a1.set_xlim(xmin_t, xmax_t); a1.set_ylim(ymin, ymax)
    a1.set_xlabel("模擬時間 (s)", color="w", fontsize=10); a1.set_ylabel("開啟角 (°)", color="w", fontsize=10)
    a1.set_title("角度 – 時間(橘=加壓  藍=放開  綠=靜置)", color="w", fontsize=12)
    a1.tick_params(colors="w", labelsize=9); a1.grid(alpha=.18)

    # ---- 右下:力矩–角度
    a2 = fig.add_subplot(gs[1, 1]); a2.set_facecolor("#12151b")
    a2.plot(SO[lo:end_s], TAU[lo:end_s], color="#455a64", lw=0.8)
    a2.plot(SO[lo:s + 1], TAU[lo:s + 1], color=BLUE, lw=1.4)
    a2.plot(live, TAU[s], "o", ms=8, color=YEL)
    a2.axvline(Z + YD, color=RED, ls="--", lw=1.2)
    a2.axvline(Z, color=GREY, lw=0.8); a2.axhline(0, color=GREY, lw=0.8)
    a2.set_xlim(ymin, ymax)
    a2.set_xlabel("開啟角 (°)", color="w", fontsize=10); a2.set_ylabel("摺線力矩 (N·m)", color="w", fontsize=10)
    a2.set_title("摺線力矩 – 角度(紅虛線 = 降伏角)", color="w", fontsize=12)
    a2.tick_params(colors="w", labelsize=9); a2.grid(alpha=.18)

    # ---- 底部時間條:三段 + 游標
    fig.text(0.01, 0.955, "紙箱蓋降伏測試  tune %s  降伏角 My0/k = %.2f°  目標 %.1f°(%.2f × 降伏角)"
             % (R["tune"], YD, R["target_deg"], R["target_over_yield"]), color="w", fontsize=14,
             fontweight="bold")
    bx = fig.add_axes([0.01, 0.025, 0.97, 0.035]); bx.axis("off"); bx.set_xlim(0, 1); bx.set_ylim(0, 1)
    x0 = 0.0
    for c, lab, col in zip(cnt, ("加壓(含起點、保持)", "放開", "回彈與靜置"), (ORG, BLUE, GREEN)):
        w = c / a.frames
        bx.add_patch(plt.Rectangle((x0, 0), w, 1, color=col, alpha=0.35))
        bx.text(x0 + w / 2, 0.5, lab, color="w", fontsize=10, ha="center", va="center"); x0 += w
    bx.axvline((k + 0.5) / a.frames, color=YEL, lw=3)

    fig.canvas.draw()
    wr.append_data(np.asarray(fig.canvas.buffer_rgba())[:, :, :3]); plt.close(fig)
    if (k + 1) % 100 == 0: P("  合成 %d/%d" % (k + 1, a.frames))
wr.close()
json.dump(dict(frames=a.frames, counts=cnt, video_s=[c / 30 for c in cnt], share=[c / a.frames for c in cnt],
               sim_block_s=BLK_T, raw_frames=[len(b) for b in blocks], stop_t=tsim(stop_s),
               release_t=tsim(rel_s), hold_t=tsim(hold_s)),
          open(os.path.join(D, N + "_compose.json"), "w"), indent=1, ensure_ascii=False)
P("WROTE %s  幀數 %d" % (a.mp4, a.frames))
