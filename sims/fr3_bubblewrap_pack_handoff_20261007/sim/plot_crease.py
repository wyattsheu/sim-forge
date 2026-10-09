#!/usr/bin/env python3
"""plot_crease.py — figures for docs/CREASE_MECHANICS.md from the crease_test.py CSVs (plain python + matplotlib).

  python3 plot_crease.py            # reads sim/logs/crease_*.csv, writes docs/img/*.png

Measured crease moment = fixture torque + gravity torque (both in the opening sense): with the flap moving slowly
that is the moment the crease resists with (inertia and drive damping are a few % of it at 60 deg/s).
"""
import csv, math, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(HERE, "logs")
IMG = os.path.join(os.path.dirname(HERE), "docs", "img")
os.makedirs(IMG, exist_ok=True)
WIDTH = 0.262          # fyp crease length (m)
MY_PER_M = 0.25        # model yield moment per metre
SB = 45.0              # model spring-back (deg)
INK, MUTED, GRID = "#1f2328", "#59636e", "#d0d7de"
C1, C2, C3, C4 = "#2a6fdb", "#d1495b", "#2e9e6b", "#e8a33d"
plt.rcParams.update({"font.size": 11, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 130})


def load(name):
    p = os.path.join(LOGS, name + ".csv")
    if not os.path.isfile(p): print("missing", p); return None
    rows = list(csv.DictReader(open(p)))
    f = lambda k: [float(r[k]) for r in rows]
    return dict(t=f("t_s"), ph=[r["phase"] for r in rows], ang=f("angle_deg"), fix=f("fixture_torque_Nm"),
                g=f("gravity_torque_Nm"), mc=f("crease_moment_Nm"), set=f("plastic_set_deg"), my=f("yield_Nm"))


def smooth(y, n=9):
    out = []
    for i in range(len(y)):
        w = y[max(0, i - n // 2): i + n // 2 + 1]; out.append(sum(w) / len(w))
    return out


def measured(d):
    """crease moment per metre (N*m/m) during the fixture-driven part (fold + hold)"""
    t0 = next((d["t"][i] for i, p in enumerate(d["ph"]) if p == "fold"), 0.0)
    idx = [i for i, p in enumerate(d["ph"]) if p in ("fold", "hold") and d["t"][i] > t0 + 0.08]
    a = [d["ang"][i] for i in idx]
    m = smooth([(d["fix"][i] + d["g"][i]) / WIDTH for i in idx])
    return a, m


# 1. literature-shaped schematic vs the model law
def fig_schematic():
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    th = [i * 0.5 for i in range(0, 181)]
    # schematic of measured paperboard (Nagasawa 2019 Fig. 8 shape): elastic < ~20 deg, peak Mp1, plateau to 90
    lit = []
    for t in th:
        if t <= 18: m = 0.244 * (t / 18) ** 0.8
        elif t <= 30: m = 0.244 - (0.244 - 0.215) * (t - 18) / 12
        else: m = 0.215
        lit.append(m)
    ax.plot(th, lit, color=MUTED, lw=2, ls="--", label="paperboard, measured shape (Nagasawa 2019, schematic)")
    # model: elastic-perfectly-plastic, k = My / spring-back
    k = MY_PER_M / math.radians(SB)
    mod = [min(k * math.radians(t), MY_PER_M) for t in th]
    ax.plot(th, mod, color=C1, lw=2.5, label="model loading: k = My / spring-back, plateau My")
    # unloading from 90
    un = [(t, max(0.0, MY_PER_M - k * math.radians(90 - t))) for t in th if 90 - SB <= t <= 90]
    ax.plot([u[0] for u in un], [u[1] for u in un], color=C2, lw=2.5, label="model unloading from 90 deg")
    ax.annotate("spring-back %.0f deg\n(lit.: 90 deg fold releases\nto 43-46 deg)" % SB, xy=(45, 0.0), xytext=(8, 0.07),
                arrowprops=dict(arrowstyle="->", color=INK), color=INK, fontsize=10)
    ax.annotate("yield / plateau My = %.2f N*m/m\n(lit. Mp1 0.244, M90 0.215)" % MY_PER_M, xy=(70, MY_PER_M), xytext=(48, 0.29),
                arrowprops=dict(arrowstyle="->", color=INK), color=INK, fontsize=10)
    ax.set_xlim(0, 90); ax.set_ylim(0, 0.34)
    ax.set_xlabel("fold angle (deg)"); ax.set_ylabel("crease moment per width (N*m/m)")
    ax.set_title("Crease moment vs fold angle: literature shape and the model", color=INK, loc="left")
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(IMG, "crease_model_vs_literature.png")); plt.close(fig)


# 2. simulated fold to 90 and to 270 (empty carton)
def fig_sim():
    d90, d270 = load("crease_fyp_90_plastic_empty"), load("crease_fyp_270_plastic_empty")
    if not d90: return
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    a, m = measured(d90)
    ax[0].plot(a, m, color=C1, lw=2, label="simulated: fixture + gravity")
    t0 = next((d90["t"][i] for i, p in enumerate(d90["ph"]) if p == "fold"), 0.0)
    mc = [d90["mc"][i] / WIDTH for i, p in enumerate(d90["ph"]) if p in ("fold", "hold") and d90["t"][i] > t0 + 0.08]
    ax[0].plot(a, mc, color=C3, lw=1.5, ls="--", label="crease law k(theta - set)")
    ax[0].axhline(MY_PER_M, color=MUTED, lw=1, ls=":")
    rel = [d90["ang"][i] for i, p in enumerate(d90["ph"]) if p == "release"]
    ax[0].axvline(rel[-1], color=C2, lw=1.5)
    ax[0].text(rel[-1] + 1, 0.02, "rests at %.1f deg\nafter release" % rel[-1], color=C2, fontsize=10)
    ax[0].set_title("Fold to 90 deg (fyp, empty carton)", loc="left", color=INK)
    ax[0].set_xlabel("fold angle (deg)"); ax[0].set_ylabel("crease moment per width (N*m/m)")
    ax[0].legend(frameon=False, fontsize=9, loc="lower right"); ax[0].set_ylim(-0.05, 0.42)
    if d270:
        a, m = measured(d270)
        ax[1].plot(a, m, color=C1, lw=2, label="fixture + gravity")
        t0 = next((d270["t"][i] for i, p in enumerate(d270["ph"]) if p == "fold"), 0.0)
        g = [d270["g"][i] / WIDTH for i, p in enumerate(d270["ph"]) if p in ("fold", "hold") and d270["t"][i] > t0 + 0.08]
        ax[1].plot(a, g, color=C4, lw=1.5, label="gravity (opening sense)")
        ax[1].axvline(90, color=GRID, lw=1); ax[1].axvline(180, color=GRID, lw=1)
        rel = [d270["ang"][i] for i, p in enumerate(d270["ph"]) if p == "release"]
        ax[1].axvline(rel[-1], color=C2, lw=1.5); ax[1].text(rel[-1] - 62, 0.36, "rests at %.0f deg" % rel[-1], color=C2, fontsize=10)
        ax[1].text(92, -0.04, "past 90 deg the flap's\nweight helps opening", color=C4, fontsize=9)
        ax[1].text(200, 0.30, "flap reaches the\nwall at ≈261 deg →", color=INK, fontsize=9)
        ax[1].set_title("Fold to 270 deg (down the outside of the wall)", loc="left", color=INK)
        ax[1].set_xlabel("fold angle (deg)"); ax[1].legend(frameon=False, fontsize=9, loc="upper left"); ax[1].set_ylim(-0.08, 0.42)
    fig.tight_layout(); fig.savefig(os.path.join(IMG, "crease_sim_fold.png")); plt.close(fig)


# 3. repeated folds (softening) and the old models
def fig_cycles_old():
    dc = load("crease_fyp_90_plastic_x3_empty")
    old, spr = load("crease_fyp_90_oldlatch_empty"), load("crease_fyp_90_spring_empty")
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    if dc:
        cyc, prev = [], None
        for i, p in enumerate(dc["ph"]):
            if p == "fold" and prev not in ("fold", "hold"): cyc.append([])
            if p in ("fold", "hold"): cyc[-1].append(i)
            prev = p
        cyc = [c[10:] for c in cyc]                           # skip the fixture start transient
        for n, idx in enumerate(cyc):
            a = [dc["ang"][i] for i in idx]; m = smooth([(dc["fix"][i] + dc["g"][i]) / WIDTH for i in idx])
            ax[0].plot(a, m, lw=2, color=[C1, C3, C4][n % 3], label="fold %d (from %.0f deg)" % (n + 1, a[0]))
        ax[0].text(52, 0.105, "re-fold: elastic up to the previous\nfold, then yields at a softer M_y", color=MUTED, fontsize=9)
        ax[0].set_title("Repeated folds to 90 deg: the crease softens", loc="left", color=INK)
        ax[0].set_xlabel("fold angle (deg)"); ax[0].set_ylabel("crease moment per width (N*m/m)"); ax[0].legend(frameon=False, fontsize=9)
    for d, lab, c in ((old, "before: stiff spring 0.69 N*m/rad + latch, inertia x180", C2), (spr, "spring only, carton_v1 stiffness", C4),
                      (load("crease_fyp_90_plastic_empty"), "now: elastic-plastic crease", C1)):
        if d:
            a, m = measured(d); m = smooth(m, 41); ax[1].plot(a, m, lw=2, color=c, label=lab)
    ax[1].text(-4, -2.75, "old latch flips the target to 170 deg at 25 deg:\nthe flap drives itself open, the fixture has to hold it back", color=C2, fontsize=9)
    ax[1].set_title("Same 90 deg fold, three flap models", loc="left", color=INK); ax[1].set_ylabel("moment per width (N*m/m)")
    ax[1].set_xlabel("fold angle (deg)"); ax[1].legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout(); fig.savefig(os.path.join(IMG, "crease_cycles_and_old_models.png")); plt.close(fig)


# 4. free-body diagram + the four flap positions (drawn, no data)
def fig_fbd():
    from matplotlib.patches import Rectangle, FancyArrowPatch, Arc
    fig = plt.figure(figsize=(12, 7.6))
    ax = fig.add_axes([0.02, 0.40, 0.46, 0.56]); ax.set_aspect("equal"); ax.axis("off")
    hx, hy, L, th = 0.0, 0.0, 1.0, 55.0
    ax.add_patch(Rectangle((hx - 0.08, hy - 1.0), 0.08, 1.0, fc="#d9c3a0", ec="#8a6d3b"))
    ax.text(hx - 0.55, -0.6, "carton wall", color=MUTED)
    ax.plot([hx - 0.08, hx - 1.0], [hy, hy], ls="--", color="#bbbbbb"); ax.text(-1.0, 0.04, "shut (0 deg)", color=MUTED, fontsize=10)
    a_ = math.radians(180 - th); fx, fy = hx + L*math.cos(a_), hy + L*math.sin(a_)
    ax.plot([hx, fx], [hy, fy], color="#b08850", lw=9, solid_capstyle="round")
    ax.plot(hx, hy, "o", color=INK, ms=9); ax.text(hx + 0.06, hy + 0.02, "crease (hinge)", color=INK, fontsize=10)
    ax.add_patch(Arc((hx, hy), 0.6, 0.6, theta1=180 - th, theta2=180, color=C1, lw=2)); ax.text(-0.42, 0.13, "θ", color=C1, fontsize=15)
    cx, cy = (hx + fx)/2, (hy + fy)/2
    ax.plot(cx, cy, "o", color=C4, ms=7)
    ax.add_patch(FancyArrowPatch((cx, cy), (cx, cy - 0.45), arrowstyle="-|>", mutation_scale=18, color=C4, lw=2.5))
    ax.text(cx - 0.62, cy - 0.20, "m g  (at L/2)", color="#b07a12", fontsize=11)
    nx, ny = math.sin(a_), -math.cos(a_)                       # perpendicular, opening side (clockwise here)
    ax.add_patch(FancyArrowPatch((fx, fy), (fx + 0.38*nx, fy + 0.38*ny), arrowstyle="-|>", mutation_scale=18, color=C2, lw=2.5))
    ax.text(fx + 0.40*nx + 0.03, fy + 0.40*ny + 0.02, "F  (gripper / mouse)", color=C2, fontsize=11)
    ax.add_patch(FancyArrowPatch((hx + 0.3*math.cos(math.radians(105)), 0.3*math.sin(math.radians(105))),
                                 (hx + 0.3*math.cos(math.radians(150)), 0.3*math.sin(math.radians(150))),
                                 connectionstyle="arc3,rad=0.35", arrowstyle="-|>", mutation_scale=16, color=C3, lw=2.5))
    ax.text(-0.95, -0.28, "M_c  crease moment\n(pulls back towards shut)", color=C3, fontsize=11)
    ax.text((hx+fx)/2 - 0.35, (hy+fy)/2 + 0.12, "L", color=MUTED, fontsize=12)
    ax.set_xlim(-1.15, 0.75); ax.set_ylim(-1.05, 1.15)
    ax.set_title("A. Forces on one flap (side view)", loc="left", color=INK, fontsize=13)
    tx = fig.add_axes([0.50, 0.40, 0.48, 0.56]); tx.axis("off")
    lines = [("Moment balance about the crease (slow fold)", True),
             ("F · L  =  M_c(θ)  +  m g (L/2) cos θ", True), ("", False),
             ("M_c = k (θ − θ_p)       elastic, while |M_c| < M_y", False),
             ("θ_p flows so that |M_c| = M_y      plastic fold", False),
             ("M_y softens with accumulated plastic rotation", False),
             ("after release the flap returns by M_y / k = 45 deg", False), ("", False),
             ("Upper flap fyp: L = 111 mm, width 262 mm, m = 17.4 g", False),
             ("M_y = 0.25 N·m/m × 0.262 m = 0.066 N·m", False),
             ("m g L/2 = 0.0094 N·m  (≈ 14 % of M_y)", False),
             ("k = M_y / 45 deg = 0.083 N·m/rad", False),
             ("→ edge force to start the fold ≈ (0.066 + 0.009) / 0.111 ≈ 0.68 N", False),
             ("→ past 90 deg cos θ < 0: the flap's weight helps opening", False)]
    for i, (t, b) in enumerate(lines):
        tx.text(0.0, 0.96 - i*0.072, t, fontsize=12, color=INK, weight="bold" if b else "normal", transform=tx.transAxes)
    bx = fig.add_axes([0.02, 0.02, 0.96, 0.33]); bx.set_aspect("equal"); bx.axis("off")
    bx.set_title("B. Flap positions and what the weight does", loc="left", color=INK, fontsize=13)
    cases = [(0, "0 deg shut", "weight presses it shut"), (90, "90 deg upright", "weight: no moment"),
             (180, "180 deg out like a shelf", "weight pulls it down = opening sense"), (261, "≈ 261 deg down the wall", "weight holds it there")]
    for i, (th, t1, t2) in enumerate(cases):
        ox = i * 3.0
        bx.add_patch(Rectangle((ox - 0.08, -1.0), 0.08, 1.0, fc="#d9c3a0", ec="#8a6d3b"))
        bx.add_patch(Rectangle((ox - 1.0, -1.0), 1.0, 0.06, fc="#d9c3a0", ec="#8a6d3b"))
        a_ = math.radians(180 - th); fx, fy = ox + 0.9*math.cos(a_), 0.9*math.sin(a_)
        if th > 250: fx, fy = ox + 0.06, -0.9
        bx.plot([ox, fx], [0, fy], color="#b08850", lw=7, solid_capstyle="round"); bx.plot(ox, 0, "o", color=INK, ms=7)
        cx, cy = (ox + fx)/2, fy/2
        if th == 90: cx += 0.12
        bx.add_patch(FancyArrowPatch((cx, cy), (cx, cy - 0.35), arrowstyle="-|>", mutation_scale=14, color=C4, lw=2))
        bx.text(ox - 0.9, -1.35, t1, fontsize=11, color=INK, weight="bold"); bx.text(ox - 0.9, -1.6, t2, fontsize=10, color=MUTED)
    bx.set_xlim(-1.2, 10.4); bx.set_ylim(-1.75, 1.05)
    fig.savefig(os.path.join(IMG, "flap_free_body.png")); plt.close(fig)


fig_fbd(); fig_schematic(); fig_sim(); fig_cycles_old()
print("figures ->", IMG)
