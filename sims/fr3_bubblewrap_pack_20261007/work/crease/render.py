#!/usr/bin/env python3
"""render.py — 把探針錄的頂點(rec/*.npz)畫成 mp4(純 CPU,matplotlib + ffmpeg)。
    python3 crease/render.py rec/a.npz [rec/b.npz ...] [--out videos/x.mp4] [--every 1]
多個 npz → 並排(同一時間軸),方便「對照 vs 改寫」比較。左:斜視 3D 面;下:x-z 側視(全部頂點投影)。"""
import argparse, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter
ap = argparse.ArgumentParser()
ap.add_argument("npz", nargs="+")
ap.add_argument("--out", required=True)
ap.add_argument("--every", type=int, default=1)
ap.add_argument("--elev", type=float, default=22)
ap.add_argument("--azim", type=float, default=-60)
a = ap.parse_args()
D = [np.load(f, allow_pickle=True) for f in a.npz]
n = len(D)
allp = np.concatenate([d["P"].reshape(-1, 3) for d in D])
lo, hi = allp.min(0), allp.max(0); c = (lo + hi) / 2; r = (hi - lo).max() / 2 + 0.005
fig = plt.figure(figsize=(4.2 * n, 6.4), dpi=110)
ax3 = [fig.add_subplot(2, n, k + 1, projection="3d") for k in range(n)]
ax2 = [fig.add_subplot(2, n, n + k + 1) for k in range(n)]
T = min(len(d["t"]) for d in D)
w = FFMpegWriter(fps=30 // a.every if a.every <= 30 else 1, codec="libx264", extra_args=["-pix_fmt", "yuv420p"])
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
with w.saving(fig, a.out, dpi=110):
    for f in range(0, T, a.every):
        for k, d in enumerate(D):
            p = d["P"][f]; t = d["t"][f]; tri = d["tris"]
            ev = [str(nm) for te, nm in zip(d["ev"], d["evn"]) if te <= t + 1e-6]
            A = ax3[k]; A.cla()
            A.plot_trisurf(p[:, 0], p[:, 1], p[:, 2], triangles=tri, color=(0.95, 0.6, 0.2), edgecolor=(0.3, 0.2, 0.1, 0.25), linewidth=0.2, shade=True)
            A.set_xlim(c[0] - r, c[0] + r); A.set_ylim(c[1] - r, c[1] + r); A.set_zlim(max(c[2] - r, lo[2] - 0.002), max(c[2] - r, lo[2] - 0.002) + 2 * r)
            A.view_init(a.elev, a.azim); A.set_box_aspect((1, 1, 1))
            A.set_title("%s\nt=%.2fs  %s" % (str(d["title"]), t, ev[-1] if ev else ""), fontsize=8)
            B = ax2[k]; B.cla()
            B.plot(p[:, 0] * 1e3, p[:, 2] * 1e3, ".", ms=1.2, color=(0.8, 0.4, 0.1))
            B.set_xlim((c[0] - r) * 1e3, (c[0] + r) * 1e3); B.set_ylim((lo[2] - 0.003) * 1e3, (lo[2] - 0.003 + 2 * r) * 1e3)
            B.set_aspect("equal"); B.set_xlabel("x mm"); B.set_ylabel("z mm"); B.grid(alpha=0.3)
            B.set_title("side view (x-z)", fontsize=8)
        fig.tight_layout(); w.grab_frame()
print("wrote", a.out, T // a.every, "frames")
