#!/usr/bin/env python3
"""make_figs.py — composite figures for the crease slides (run from docs/slides/).

Inputs: figs/nagasawa_fig{4,8,10}.png (cropped from the paper PDF with acm-pptx figure.py, see outline notes),
figs/ours_fig10_frames.png (frames of videos/crease_fold90.mp4), ../img/ours_fig8_style.png, ../img/flap_fbd_slide.png.
Paper and simulation are kept in SEPARATE panels, never drawn on one axis.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

INK, MUTED, RED, BLUE = "#1f2328", "#59636e", "#C00000", "#2a6fdb"
REF = "Nagasawa, Kaneko & Adachi, JAMDSM 13(1), 2019"


def side_by_side(left, right, ltitle, rtitle, out, ratio=(1, 1), size=(16, 5.6)):
    fig, ax = plt.subplots(1, 2, figsize=size, gridspec_kw={"width_ratios": ratio})
    for a, img, t, c in ((ax[0], left, ltitle, RED), (ax[1], right, rtitle, BLUE)):
        a.imshow(mpimg.imread(img)); a.axis("off"); a.set_title(t, fontsize=18, color=c, loc="left", weight="bold")
    fig.tight_layout(); fig.savefig(out, dpi=200, bbox_inches="tight"); plt.close(fig)


def stacked(top, bottom, ttitle, btitle, out, size=(14, 8.0)):
    fig, ax = plt.subplots(2, 1, figsize=size)
    for a, img, t, c in ((ax[0], top, ttitle, RED), (ax[1], bottom, btitle, BLUE)):
        a.imshow(mpimg.imread(img)); a.axis("off"); a.set_title(t, fontsize=18, color=c, loc="left", weight="bold")
    fig.tight_layout(); fig.savefig(out, dpi=200, bbox_inches="tight"); plt.close(fig)


def model_card(out):
    """free-body diagram + the crease law typeset (matplotlib mathtext)"""
    fig = plt.figure(figsize=(16, 7.2))
    a = fig.add_axes([0.0, 0.0, 0.36, 1.0]); a.imshow(mpimg.imread("../img/flap_fbd_slide.png")); a.axis("off")
    t = fig.add_axes([0.38, 0.0, 0.62, 1.0]); t.axis("off")
    rows = [
        (r"$M_c = k\,(\theta-\theta_p),\qquad |M_c|\leq M_y(\kappa)$", "elastic crease moment, capped at yield"),
        (r"$\dot{\theta}_p \neq 0 \;\;\mathrm{only\ if}\;\; |k(\theta-\theta_p)| > M_y$", "plastic set grows: the fold stays"),
        (r"$M_y(\kappa) = M_{y0}\,\max\!\left(0.5,\; e^{-s\kappa}\right),\quad \kappa=\sum|\Delta\theta_p|$", "every fold softens the crease"),
        (r"$\Delta\theta_{\mathrm{spring\!-\!back}} = M_y\,/\,k$", "release returns this much"),
        (r"$F\,L = M_c(\theta) + m g\,\frac{L}{2}\cos\theta$", "pull needed at the flap edge"),
    ]
    y = 0.93
    for eq, txt in rows:
        t.text(0.0, y, eq, fontsize=27, color=INK, va="top")
        t.text(0.02, y - 0.10, txt, fontsize=17, color=MUTED, va="top")
        y -= 0.19
    fig.savefig(out, dpi=200, bbox_inches="tight"); plt.close(fig)


def mechanics_summary(out):
    """eight properties of a carton crease, each a tiny schematic + formula + 'in our model?'"""
    import numpy as np
    cards = [
        ("1  Elastic bending", r"$M = k\,\theta$", "small folds spring back fully", True,
         lambda a: a.plot([0, 1], [0, 1], color=INK, lw=3)),
        ("2  Yield / peak", r"$M \leq M_y$" + "\n" + r"$M_{p1}\approx0.24\ \mathrm{N\cdot m/m}$", "plies delaminate, crease gives", True,
         lambda a: a.plot([0, .3, .45, 1], [0, .9, 1, .95], color=INK, lw=3)),
        ("3  Plastic plateau", r"$M \approx M_{90}$" + "\n" + r"for $20^\circ$–$90^\circ$", "fold keeps going at ~const. moment", True,
         lambda a: a.plot([0, .25, 1], [0, .9, .82], color=INK, lw=3)),
        ("4  Spring-back", r"$\Delta\theta = M_y/k \approx 45^\circ$", "90° fold rests at ~45°", True,
         lambda a: (a.plot([0, .3, 1], [0, .9, .9], color=INK, lw=3), a.plot([1, .5], [.9, 0], color=RED, lw=3))),
        ("5  Softening on refold", r"$M_y \propto e^{-s\kappa}$", "2nd fold is easier", True,
         lambda a: (a.plot([0, .3, 1], [0, 1, 1], color=INK, lw=3), a.plot([.4, .62, 1], [0, .8, .8], color=BLUE, lw=3))),
        ("6  Flap weight", r"$m g\,\frac{L}{2}\cos\theta$", "closes < 90°, opens > 90°", True,
         lambda a: a.plot(np.linspace(0, 1, 50), np.cos(np.linspace(0, np.pi, 50)) * .45 + .5, color=INK, lw=3)),
        ("7  Rate dependence", r"$M_{p1}=0.244$" + "\n" + r"$\;+\,0.013\ln(\omega/0.2)$", "faster fold, slightly stiffer (~5%/e-fold)", False,
         lambda a: a.plot(np.linspace(.05, 1, 50), np.log(np.linspace(.05, 1, 50)) * .12 + .8, color=INK, lw=3)),
        ("8  Relaxation / creep", r"$M(t)=a_0\,(1-p_1\ln t)$", "held fold slowly lets go", False,
         lambda a: a.plot(np.linspace(.05, 1, 50), 1 - .25 * np.log(np.linspace(.05, 1, 50) * 20) / np.log(20), color=INK, lw=3)),
    ]
    fig = plt.figure(figsize=(17, 8.2))
    for i, (title, eq, txt, ok, draw) in enumerate(cards):
        r, c = divmod(i, 4)
        x0, y0 = 0.01 + c * 0.25, 0.52 - r * 0.50
        ax = fig.add_axes([x0 + 0.005, y0 + 0.20, 0.09, 0.19])
        draw(ax); ax.set_xticks([]); ax.set_yticks([]); ax.set_xlim(-.05, 1.05); ax.set_ylim(-.1, 1.15)
        for sp in ("top", "right"): ax.spines[sp].set_visible(False)
        fig.text(x0, y0 + 0.43, title, fontsize=17, weight="bold", color=INK)
        fig.text(x0 + 0.105, y0 + 0.33, eq, fontsize=17, color=INK, va="center")
        fig.text(x0, y0 + 0.13, txt, fontsize=14, color=MUTED)
        fig.text(x0, y0 + 0.06, "modelled ✓" if ok else "not modelled", fontsize=15, weight="bold",
                 color="#2e9e6b" if ok else RED)
    fig.savefig(out, dpi=200, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    side_by_side("figs/nagasawa_fig8.png", "../img/ours_fig8_style.png",
                 "Paper — Fig. 8 (0.3 mm paperboard, 72°/s)", "Ours — simulated fyp crease (60°/s)",
                 "figs/cmp_fig8.png", ratio=(1.0, 1.15))
    stacked("figs/nagasawa_fig10.png", "figs/ours_fig10_frames.png",
            "Paper — Fig. 10: fold to 89.9°, release → 46.0° → 42.7° (0.42 s)",
            "Ours — fold to 88.8°, release → 39.1° (0.2 s) → settles 45.3°", "figs/cmp_fig10.png")
    model_card("figs/model_eq.png")
    mechanics_summary("figs/mechanics_summary.png")
    print("ok")
