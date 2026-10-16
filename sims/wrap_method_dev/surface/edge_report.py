#!/usr/bin/env python3
"""edge_report.py — 把 wrap.npz 的布**逐邊**量出來。

    python3 edge_report.py out_w2/wrap.npz [out_w1/wrap.npz ...]

為什麼要這支:2026-09-29,W2 的 bbox 是 230x554x139,我據此判定「y 折失敗」並
去改第二段的錨點,改了兩輪都更糟。逐邊一量才發現 ±y 邊其實折到 y≈0(完美),
554 是**±x 邊**撐的 —— x 邊是沿 y 方向 586mm 的長條,折 x 不會縮短它。
整片的 bbox 對「哪條邊沒折好」完全沒有鑑別力。要判斷折疊,用這支,不要看 bbox。
"""
import numpy as np, sys
if len(sys.argv) < 2: sys.exit(__doc__)
W = 0.586                                  # 布邊長,跟 wrap_sim 的 NEED_SQ 一致
for f in sys.argv[1:]:
    S = np.load(f)["sheet"]
    n = len(S); r = int(round(np.sqrt(n)))
    if r*r != n:
        print("%s: 頂點數 %d 不是完全平方,這支只吃方形規則網格" % (f, n)); continue
    i, j = np.arange(n) % r, np.arange(n) // r
    fx, fy = -W/2 + i*W/(r-1), -W/2 + j*W/(r-1)
    lim = W/2 - 1e-6
    print("\n%s  res=%d  整片 bbox %s mm" % (f, r, (1000*(S.max(0)-S.min(0))).round(0)))
    for nm, m in (("+x", fx > lim), ("-x", fx < -lim), ("+y", fy > lim), ("-y", fy < -lim)):
        P = S[m]
        print("  %s 邊 n=%3d  x[%7.1f,%7.1f]  y[%7.1f,%7.1f]  z[%6.1f,%6.1f]"
              % (nm, m.sum(), *(1000*np.r_[P[:, 0].min(), P[:, 0].max(),
                                           P[:, 1].min(), P[:, 1].max(),
                                           P[:, 2].min(), P[:, 2].max()])))
    print("  判讀:折好的邊應該收到中線附近(該軸 |值| 小)且抬到杯高;"
          "沒折的邊會停在 ±293。另一軸的跨距不代表沒折 —— 那是邊本身的長度。")
