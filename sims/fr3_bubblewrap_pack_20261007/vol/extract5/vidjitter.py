#!/usr/bin/env python3
"""影片顫抖指標:對 wrap.mp4 某時段抽幀(30 fps),在 ROI 內的布像素(低彩度、亮)上算
  d1 = 相鄰幀像素差 RMS(灰階 0-255)       — 含緩慢漂移
  d2 = 二階差分 f[t+1]-2f[t]+f[t-1] 的 RMS  — 扣掉漂移,只留抖動(對應 jitter.py 的 hf)
  chg = 相鄰幀 |差| > 8 的布像素比例 %
usage: vidjitter.py VIDEO  [--seg NAME:T0:T1:x0,y0,x1,y1 ...]
"""
import argparse, subprocess, numpy as np
SEGS = ["closed:27.0:29.0:0,40,1280,655",          # 關蓋後靜置(布看不到 → 編碼雜訊底)
        "open_hold:43.0:46.0:480,70,920,320",      # 掀開停留
        "yp_hold:113.5:116.5:380,30,1180,450"]     # yp 放手後、取杯前停留(兩手仍綁著)
ap = argparse.ArgumentParser(); ap.add_argument("video"); ap.add_argument("--seg", nargs="*", default=SEGS)
a = ap.parse_args()
W, H = 1280, 720
for s in a.seg:
    name, t0, t1, roi = s.split(":"); t0, t1 = float(t0), float(t1)
    x0, y0, x1, y1 = map(int, roi.split(","))
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", "%.3f" % t0, "-i", a.video, "-t", "%.3f" % (t1 - t0),
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    F = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)[:, y0:y1, x0:x1].astype(np.float32)
    # 擋掉右上角時間字幕
    if y0 < 36: F[:, :36 - y0, max(0, 848 - x0):] = np.nan
    g = F.mean(-1)
    chroma = F.max(-1) - F.min(-1)
    cloth = (chroma < 18) & (F[..., 2] >= F[..., 0] - 3) & (g > 60)
    m = cloth[:-1] | cloth[1:]
    d = np.diff(g, axis=0)
    d1 = np.sqrt(np.nanmean(d[m] ** 2))
    chg = 100 * np.nanmean(np.abs(d[m]) > 8)
    m2 = m[:-1] & m[1:]
    dd = g[2:] - 2 * g[1:-1] + g[:-2]
    d2 = np.sqrt(np.nanmean(dd[m2] ** 2))
    print("%-10s %6.2f-%6.2f s  幀 %3d  布像素 %6d  d1 %.3f  d2 %.3f  chg>8 %.3f%%" % (name, t0, t1, len(g), int(cloth.mean(0).sum()), d1, d2, chg))
