#!/usr/bin/env python3
"""grasp_points.py — G3:在開蓋後的包裹(vol/soft/s2/wrap.npz)上找最外層 yn 片的抓取點。純 CPU。

    /isaac-sim/python.sh grasp_points.py [--npz ../soft/s2/wrap.npz] [--snap snap_end]

座標:npz 是世界座標,箱子最後位移 OFF = (0, 0.200, 0.097)(OFF_IN (0,0,-3mm) + movebox (0,200,100)mm,見 s2/wrap_vol.log),
      這裡全部換到「箱子局部」:箱底內面 z = 3mm、內腔 |x| <= 132、|y| <= 112;x 牆頂 120、y 牆頂 126.5;鉸鏈 123 / 129.5。
片的歸屬:wrap_vol 的 SIDEPICK(CX 84.63、CY 71.50mm,超出折線多者;角落歸 y)。折序 xp→xn→yp→yn ⇒ yn 最外層。
候選:板的外邊界上、flat y < -CY(超過 yn 折線)的頂點欄(上下兩層取中面)。分 tip(flat y = -250 那排)與 side(x = ±250)。

夾爪模型(題目):手從 +z 下來;兩指上下夾布(閉合軸 ≈ z),指面沿「邊法線」方向伸進布邊(插入方向 = −u,u = 邊的水平外法線)。
  指面 20(沿邊 t)x 20(沿 u:-15 ~ +5mm,布邊在 u=0)x 8(z)mm;上指底面 = 布頂 + 0.5mm,下指頂面 = 布底 − 0.5mm。
  掃掠:上指 = 從 z=160mm 垂直降到夾持高度(在夾持足跡上);下指 = 先在布邊外 u∈[+7,+27] 垂直降到夾持高度,再沿 −u 平移到 u∈[-15,+5]。
判斷
  (a) 被壓住:以夾點為軸、半徑 30mm 的垂直圓柱內,高於布頂、且「不相鄰」(flat 距離 > 45mm)的布頂點數。
  (b) 掃掠撞到:箱壁/開著的蓋(取樣點落在內腔 xy 外且 z < 135mm)、杯子(trimesh contains)、其他層布(取樣點到不相鄰布中面 < T/2 + 0.5mm)。
  指面跟布面局部平面對齊(閉合軸 = 布面法線 n;坡度 = 邊相對水平的仰角,手腕要跟著俯仰)。
  (c) 下方空隙:下指足跡內 5x5 點,從布底沿 −n 射線,打到不相鄰布(中面 − T/2)/ 杯子 / 箱底 的最小距離;要 >= 6mm。
"""
import os, sys, argparse, json
import numpy as np
import trimesh

ap = argparse.ArgumentParser()
HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
ap.add_argument("--npz", default=os.path.join(VOL, "soft", "s2", "wrap.npz"))
ap.add_argument("--snap", default="snap_end")
ap.add_argument("--mug", default=os.path.join(VOL, "mug.stl"))
ap.add_argument("--out", default=os.path.join(HERE, "data", "grasp_points.json"))
a = ap.parse_args()
os.makedirs(os.path.join(HERE, "data"), exist_ok=True); os.makedirs(os.path.join(HERE, "img"), exist_ok=True)

OFF = np.array([0.0, 0.200, 0.097])
IX, IY, ZFLOOR = 0.132, 0.112, 0.003
WTOP_X, WTOP_Y, ZOBST = 0.120, 0.1265, 0.135
CX, CY = 0.08463, 0.07150
T = 0.004; NX = 35; N1 = (NX + 1) ** 2; W = 0.5; DXY = W / NX
FAR = 0.045
d = np.load(a.npz)
Pw = d[a.snap]; FLAT = d["flat"]; MUGW = d["snapmug_" + a.snap.replace("snap_", "")]
P = Pw - OFF; MUG = MUGW - OFF
BOT, TOP = np.arange(N1), np.arange(N1, 2 * N1)
MID = (P[BOT] + P[TOP]) / 2
ZLO = np.minimum(P[BOT, 2], P[TOP, 2]); ZHI = np.maximum(P[BOT, 2], P[TOP, 2]); THK = np.linalg.norm(P[TOP] - P[BOT], axis=1)
F2 = FLAT[BOT, :2]
ii, jj = np.arange(N1) % (NX + 1), np.arange(N1) // (NX + 1)

def side(fx, fy):
    sx = max(0.0, abs(fx) - CX); sy = max(0.0, abs(fy) - CY)
    return ("yp" if fy > 0 else "yn") if sy >= sx else ("xp" if fx > 0 else "xn")
SIDE = np.array([side(*f) if (abs(f[0]) > CX or abs(f[1]) > CY) else "base" for f in F2])

# 中面三角網格(36x36 欄)
QF = []
for j in range(NX):
    for i in range(NX):
        v = j * (NX + 1) + i
        QF += [(v, v + 1, v + NX + 2), (v, v + NX + 2, v + NX + 1)]
QF = np.array(QF)
mug_mesh = trimesh.load(a.mug)
assert len(mug_mesh.vertices) == len(MUG), (len(mug_mesh.vertices), len(MUG))
MUGM = trimesh.Trimesh(MUG, np.asarray(mug_mesh.faces), process=False)

# 候選:外邊界、flat y < -CY
bnd = (ii == 0) | (ii == NX) | (jj == 0) | (jj == NX)
cand = np.where(bnd & (F2[:, 1] < -CY + 1e-9))[0]

def inward(v):
    i, j = ii[v], jj[v]
    if j == 0:
        return v + (NX + 1), "tip"
    return (v + 1 if i == 0 else v - 1), "side"

def samples_box(c, R, lo, hi, step=0.002):
    """局部框(t,u,z)的軸對齊盒 [lo,hi] 均勻取樣 → 世界(箱局部)座標。R 欄 = t,u,z。"""
    ax = [np.arange(lo[k], hi[k] + 1e-9, step) if hi[k] - lo[k] > step else np.array([(lo[k] + hi[k]) / 2]) for k in range(3)]
    g = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
    return c + g @ R.T

rows = []
for v in cand:
    vin, kind = inward(v)
    p = MID[v]
    u3 = MID[v] - MID[vin]; slope = np.degrees(np.arctan2(u3[2], np.linalg.norm(u3[:2])))
    uh = np.array([u3[0], u3[1], 0.0]); uh /= np.linalg.norm(uh)
    # 局部框:u = 沿布面的外法線(含坡度),t = 邊切線,n = 布面法線(朝上)— 指面貼著布面,閉合軸 = n
    u = u3 / np.linalg.norm(u3)
    tt = np.cross([0, 0, 1.0], u); tt /= np.linalg.norm(tt)
    n = np.cross(u, tt); n = n if n[2] > 0 else -n
    R = np.stack([tt, u, n], 1)
    half = THK[v] / 2
    fd = np.linalg.norm(F2 - F2[v], axis=1)
    other = fd > FAR
    zlo, zhi = ZLO[v], ZHI[v]
    # (a) 上方圓柱
    hr = np.linalg.norm(MID[:, :2] - p[:2], axis=1)
    above = other & (hr < 0.030) & (ZHI > zhi + 0.0005)
    na = int(above.sum())
    fo = other[QF].all(1)
    om = trimesh.Trimesh(MID, QF[fo], process=False) if fo.any() else None
    # (c) 下方空隙:下指足跡 5x5 點,從布底沿 −n 射線
    O = samples_box(p, R, [-0.010, -0.015, -half - 1e-4], [0.010, 0.005, -half - 1e-4], step=0.005)
    D = np.tile(-n, (len(O), 1))
    dist = np.full(len(O), np.inf)
    if -n[2] < -1e-6:      # 箱底平面
        dist = np.minimum(dist, (O[:, 2] - ZFLOOR) / n[2])
    for mesh, off in ((om, T / 2), (MUGM, 0.0)):
        if mesh is None or not len(mesh.faces):
            continue
        loc, ir, _ = mesh.ray.intersects_location(O, D, multiple_hits=False)
        for q, r_ in zip(loc, ir):
            dist[r_] = min(dist[r_], np.linalg.norm(q - O[r_]) - off)
    gap = float(dist.min())
    # (b) 掃掠:指面在終點姿態(貼布面)+ 往世界 +z 拉成柱(上指);下指 = 布邊外垂直柱 + 沿 −u 平移的板
    def column(B):
        return np.vstack([B + [0, 0, dz] for dz in np.arange(0, max(0.0, ZOBST + 0.025 - B[:, 2].min()) + 1e-9, 0.003)])
    fu = column(samples_box(p, R, [-0.010, -0.015, half + 0.0005], [0.010, 0.005, half + 0.0085], step=0.003))
    flc = column(samples_box(p, R, [-0.010, 0.007, -half - 0.0085], [0.010, 0.027, -half - 0.0005], step=0.003))
    fls = samples_box(p, R, [-0.010, -0.015, -half - 0.0085], [0.010, 0.027, -half - 0.0005], step=0.003)
    S_ = np.vstack([fu, flc, fls])
    outside = (np.abs(S_[:, 0]) > IX) | (np.abs(S_[:, 1]) > IY)
    n_wall = int((outside & (S_[:, 2] < ZOBST)).sum())
    n_floor = int((S_[:, 2] < ZFLOOR).sum())
    n_mug = int(MUGM.contains(S_).sum())
    n_cloth = 0
    if om is not None and len(om.faces):
        _, dd, _ = trimesh.proximity.closest_point(om, S_)
        n_cloth = int((dd < T / 2 + 0.0005).sum())
    # 到牆的水平距離(夾點)
    dwall = min(IX - abs(p[0]), IY - abs(p[1]))
    rows.append(dict(v=int(v), kind=kind, side=str(SIDE[v]), flat=[float(x) * 1e3 for x in F2[v]], p=[float(x) * 1e3 for x in p],
                     zlo=zlo * 1e3, zhi=zhi * 1e3, thick=float(THK[v]) * 1e3, u=[float(x) for x in uh[:2]], slope=float(slope),
                     a_above=na, gap=gap * 1e3, b_wall=n_wall, b_floor=n_floor, b_mug=n_mug, b_cloth=n_cloth, dwall=dwall * 1e3,
                     open_mm=float(THK[v]) * 1e3 + 2 * 0.5 + 2 * 8.0))
for r in rows:
    r["ok_a"] = r["a_above"] == 0; r["ok_b"] = (r["b_wall"] + r["b_mug"] + r["b_cloth"] + r["b_floor"]) == 0; r["ok_c"] = r["gap"] >= 6.0
    r["ok"] = r["ok_a"] and r["ok_b"] and r["ok_c"]
rank = sorted(rows, key=lambda r: (-int(r["ok"]), -(int(r["ok_a"]) + int(r["ok_b"])), -r["gap"], -r["dwall"]))
json.dump(dict(rows=rows, rank=[r["v"] for r in rank]), open(a.out, "w"), indent=1)
print("快照 %s;箱局部座標(mm)。候選(yn 片外邊界,flat y < -CY)%d 個:tip %d、side %d"
      % (a.snap, len(rows), sum(r["kind"] == "tip" for r in rows), sum(r["kind"] == "side" for r in rows)))
print("滿足 (a) %d / (b) %d / (c) %d / 全部 %d" % (sum(r["ok_a"] for r in rows), sum(r["ok_b"] for r in rows),
                                              sum(r["ok_c"] for r in rows), sum(r["ok"] for r in rows)))
gaps = np.array([r["gap"] for r in rows])
print("下方空隙 mm:min %.1f 中位 %.1f max %.1f;>=6mm 的 %d 個;>=3mm 的 %d 個" % (gaps.min(), np.median(gaps), gaps.max(),
                                                                         int((gaps >= 6).sum()), int((gaps >= 3).sum())))
print("\n全部候選(依排名):")
print(" # | v    | kind | 歸屬 | flat(x,y)      | 位置 x,y,z(mm)          | 厚 | 坡度° | 外法線 u      | (a)上方他層 | (c)下方空隙 | (b)牆/底/杯/布 | 離牆 | 判定")
for k, r in enumerate(rank):
    print("%2d | %4d | %-4s | %-4s | (%5.0f,%5.0f) | (%6.1f,%6.1f,%6.1f) | %4.1f | %5.1f | (%5.2f,%5.2f) | %3d | %6.1f | %d/%d/%d/%d | %5.1f | %s"
          % (k + 1, r["v"], r["kind"], r["side"], *r["flat"], *r["p"], r["thick"], r["slope"], *r["u"], r["a_above"], r["gap"],
             r["b_wall"], r["b_floor"], r["b_mug"], r["b_cloth"], r["dwall"], "OK" if r["ok"] else
             "NG(" + ",".join(x for x, f in (("a", r["ok_a"]), ("b", r["ok_b"]), ("c", r["ok_c"])) if not f) + ")"))

# 圖
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(16, 7), gridspec_kw=dict(width_ratios=[1.25, 1]))
ax[0].add_patch(plt.Rectangle((-IX * 1e3, -IY * 1e3), 2 * IX * 1e3, 2 * IY * 1e3, fill=False, lw=2, ec="saddlebrown"))
hull = trimesh.convex.convex_hull(MUG[:, :2] if False else np.c_[MUG[:, :2], np.zeros(len(MUG))]) if False else None
from scipy.spatial import ConvexHull
mh = ConvexHull(MUG[:, :2]); ax[0].fill(*(MUG[mh.vertices, :2] * 1e3).T, color="lightsteelblue", alpha=.5, label="mug (top proj.)")
cols = dict(xp="tab:green", xn="tab:olive", yp="tab:purple", yn="tab:red", base="lightgray")
for sd, c in cols.items():
    m = SIDE == sd
    sc = ax[0].scatter(MID[m, 0] * 1e3, MID[m, 1] * 1e3, s=6 + 0 * MID[m, 2], c=c, label=sd, alpha=.6)
cp = np.array([r["p"] for r in rows]); cg = np.array([r["gap"] for r in rows])
im = ax[0].scatter(cp[:, 0], cp[:, 1], c=np.clip(cg, 0, 12), cmap="viridis", s=40, marker="s", edgecolors="k", lw=.5, vmin=0, vmax=12)
plt.colorbar(im, ax=ax[0], label="gap below (mm), candidates")
for k, r in enumerate(rank[:5]):
    x, y = r["p"][0], r["p"][1]
    ax[0].annotate("#%d" % (k + 1), (x, y), xytext=(x + 12, y + 12), fontsize=11, color="k", weight="bold",
                   arrowprops=dict(arrowstyle="-", lw=.5))
    ax[0].arrow(x + 25 * r["u"][0], y + 25 * r["u"][1], -20 * r["u"][0], -20 * r["u"][1], head_width=4, color="k", lw=1)
ax[0].set_aspect("equal"); ax[0].set_xlabel("x mm (box local)"); ax[0].set_ylabel("y mm"); ax[0].legend(fontsize=7, loc="upper right")
ax[0].set_title("%s: sheet mid-surface by flap; yn free-edge candidates (squares, color = gap below); arrows = finger insertion" % a.snap, fontsize=9)
# 右:候選的布底 z 與下方障礙 z(沿 tip 邊 x 排序)
for kind, mk in (("tip", "o"), ("side", "^")):
    rr = [r for r in rows if r["kind"] == kind]
    xs = [r["p"][0] if kind == "tip" else r["p"][1] for r in rr]
    ax[1].plot(xs, [r["gap"] for r in rr], mk + "-", label="gap below, %s (x for tip / y for side)" % kind)
    ax[1].plot(xs, [r["zhi"] for r in rr], mk + ":", alpha=.5, label="sheet top z, %s" % kind)
ax[1].axhline(6, color="r", lw=.8, label="6 mm needed")
ax[1].set_xlabel("position along edge (mm)"); ax[1].set_ylabel("mm"); ax[1].legend(fontsize=7); ax[1].grid(alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(HERE, "img", "g3_grasp_points.png"), dpi=90); plt.close(fig)
print("\n圖 → %s" % os.path.join(HERE, "img", "g3_grasp_points.png"))
