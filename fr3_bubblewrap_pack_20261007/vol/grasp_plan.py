#!/usr/bin/env python3
"""grasp_plan.py — wrap_vol --grasp 1 用的純 CPU 函式(numpy + trimesh;可離線對 npz 測)。
從 grip/grasp_points.py 搬來三項檢查,改成「即時」:輸入目前的 sim 頂點(箱局部座標)。

  setup(FLAT, NX, CX, CY, mug_faces)      建索引(片歸屬、中面三角形)
  rank(Pl, MUGl, sd, box)                 片 sd(yn/yp)外邊界候選 → 依 (a)(b)(c) 排名(同 grasp_points.py)
  frame(Pl, v)                            夾點局部框 R=[t,u,n](t 邊切線、u 沿布面外法線、n 布面法線朝上)
  gap_below(Pl, MUGl, v, R, box)          下指足跡 5x5 點沿 −n 到他層/杯/箱底的最小距離
  hinge(Pl, sd)                           片 sd 頂部折線 (y_h, z_h):每欄從折線往尖端走,第一段變水平處
  matlen(Pl, v, sd, yh, zh)               夾點欄到鉸點的材料長度(flat 距離)
box = dict(IX, IY, ZFLOOR, ZOBST);全部 m。
(a) 被壓住:夾點半徑 30mm 垂直圓柱內,高於布頂、flat 距離 > 45mm 的布頂點數 = 0
(b) 掃掠:上指從 ZOBST+25mm 垂直降;下指在布邊外 u∈[+7,+27] 垂直降,再沿 −u 平移到 u∈[-15,+5];
    撞 箱壁(內腔外且 z<ZOBST)/箱底/杯(contains)/他層(到不相鄰中面 < T/2+0.5mm)= 0
(c) 下方空隙 >= 6mm
"""
import numpy as np
import trimesh

T = 0.004; FAR = 0.045
S = {}

def setup(FLAT, NX, CX, CY, mug_faces, thick=0.004):
    global T
    T = thick
    N1 = (NX + 1) ** 2
    F2 = FLAT[:N1, :2]
    def side(fx, fy):
        sx = max(0.0, abs(fx) - CX); sy = max(0.0, abs(fy) - CY)
        return ("yp" if fy > 0 else "yn") if sy >= sx else ("xp" if fx > 0 else "xn")
    SIDE = np.array([side(*f) if (abs(f[0]) > CX or abs(f[1]) > CY) else "base" for f in F2])
    QF = []
    for j in range(NX):
        for i in range(NX):
            v = j * (NX + 1) + i
            QF += [(v, v + 1, v + NX + 2), (v, v + NX + 2, v + NX + 1)]
    S.update(NX=NX, N1=N1, F2=F2, SIDE=SIDE, SIDE2=np.concatenate([SIDE, SIDE]), QF=np.array(QF), CX=CX, CY=CY,
             ii=np.arange(N1) % (NX + 1), jj=np.arange(N1) // (NX + 1), MF=np.asarray(mug_faces))
    return S

def mid(Pl):
    N1 = S["N1"]; return (Pl[:N1] + Pl[N1:]) / 2

def inward(v):
    NX = S["NX"]; i, j = S["ii"][v], S["jj"][v]
    if j == 0: return v + (NX + 1), "tip"
    if j == NX: return v - (NX + 1), "tip"
    return (v + 1 if i == 0 else v - 1), "side"

def frame(Pl, v):
    M = mid(Pl); vin, _ = inward(v)
    u3 = M[v] - M[vin]; u = u3 / np.linalg.norm(u3)
    tt = np.cross([0, 0, 1.0], u); tt /= np.linalg.norm(tt)
    n = np.cross(tt, u)                      # 右手系 [t,u,n](det +1)
    if n[2] < 0:
        tt = -tt; n = np.cross(tt, u)
    slope = float(np.degrees(np.arctan2(u3[2], np.linalg.norm(u3[:2]))))
    return np.stack([tt, u, n], 1), slope

def samples_box(c, R, lo, hi, step=0.002):
    ax = [np.arange(lo[k], hi[k] + 1e-9, step) if hi[k] - lo[k] > step else np.array([(lo[k] + hi[k]) / 2]) for k in range(3)]
    g = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
    return c + g @ R.T

def _other_mesh(Pl, v):
    M = mid(Pl); fd = np.linalg.norm(S["F2"] - S["F2"][v], axis=1); other = fd > FAR
    fo = other[S["QF"]].all(1)
    return (trimesh.Trimesh(M, S["QF"][fo], process=False) if fo.any() else None), other

def gap_below(Pl, MUGl, v, R, box, om=None, mugm=None):
    N1 = S["N1"]; M = mid(Pl); p = M[v]; n = R[:, 2]
    half = np.linalg.norm(Pl[v + N1] - Pl[v]) / 2
    if om is None: om, _ = _other_mesh(Pl, v)
    if mugm is None: mugm = trimesh.Trimesh(MUGl, S["MF"], process=False)
    O = samples_box(p, R, [-0.010, -0.015, -half - 1e-4], [0.010, 0.005, -half - 1e-4], step=0.005)
    D = np.tile(-n, (len(O), 1)); dist = np.full(len(O), np.inf)
    if -n[2] < -1e-6:
        dist = np.minimum(dist, (O[:, 2] - box["ZFLOOR"]) / n[2])
    for mesh, off in ((om, T / 2), (mugm, 0.0)):
        if mesh is None or not len(mesh.faces): continue
        loc, ir, _ = mesh.ray.intersects_location(O, D, multiple_hits=False)
        for q, r_ in zip(loc, ir):
            dist[r_] = min(dist[r_], np.linalg.norm(q - O[r_]) - off)
    return float(dist.min())

def rank(Pl, MUGl, sd, box):
    N1, F2, ii, jj, NX = S["N1"], S["F2"], S["ii"], S["jj"], S["NX"]
    sg = -1.0 if sd == "yn" else 1.0
    M = mid(Pl); ZLO = np.minimum(Pl[:N1, 2], Pl[N1:, 2]); ZHI = np.maximum(Pl[:N1, 2], Pl[N1:, 2])
    THK = np.linalg.norm(Pl[N1:] - Pl[:N1], axis=1)
    bnd = (ii == 0) | (ii == NX) | (jj == 0) | (jj == NX)
    cand = np.where(bnd & (sg * F2[:, 1] > S["CY"] - 1e-9))[0]
    mugm = trimesh.Trimesh(MUGl, S["MF"], process=False)
    IX, IY, ZF, ZO = box["IX"], box["IY"], box["ZFLOOR"], box["ZOBST"]
    rows = []
    for v in cand:
        _, kind = inward(v)
        R, slope = frame(Pl, v); tt, u, n = R[:, 0], R[:, 1], R[:, 2]
        p = M[v]; half = THK[v] / 2
        om, other = _other_mesh(Pl, v)
        hr = np.linalg.norm(M[:, :2] - p[:2], axis=1)
        na = int((other & (hr < 0.030) & (ZHI > ZHI[v] + 0.0005)).sum())
        gap = gap_below(Pl, MUGl, v, R, box, om, mugm)
        def column(B):
            return np.vstack([B + [0, 0, dz] for dz in np.arange(0, max(0.0, ZO + 0.025 - B[:, 2].min()) + 1e-9, 0.003)])
        fu = column(samples_box(p, R, [-0.010, -0.015, half + 0.0005], [0.010, 0.005, half + 0.0085], step=0.003))
        flc = column(samples_box(p, R, [-0.010, 0.007, -half - 0.0085], [0.010, 0.027, -half - 0.0005], step=0.003))
        fls = samples_box(p, R, [-0.010, -0.015, -half - 0.0085], [0.010, 0.027, -half - 0.0005], step=0.003)
        S_ = np.vstack([fu, flc, fls])
        outside = (np.abs(S_[:, 0]) > IX) | (np.abs(S_[:, 1]) > IY)
        nw = int((outside & (S_[:, 2] < ZO)).sum()); nf = int((S_[:, 2] < ZF).sum()); nm = int(mugm.contains(S_).sum())
        nc = 0
        if om is not None and len(om.faces):
            _, dd, _ = trimesh.proximity.closest_point(om, S_)
            nc = int((dd < T / 2 + 0.0005).sum())
        uh = np.array([u[0], u[1]]); uh /= np.linalg.norm(uh)
        r = dict(v=int(v), kind=kind, side=str(S["SIDE"][v]), flat=F2[v] * 1e3, p=p * 1e3, slope=slope, u=uh, thick=THK[v] * 1e3,
                 zlo=ZLO[v] * 1e3, zhi=ZHI[v] * 1e3, a=na, gap=gap * 1e3, b=(nw, nf, nm, nc),
                 dwall=min(IX - abs(p[0]), IY - abs(p[1])) * 1e3)
        r["ok_a"] = na == 0; r["ok_b"] = sum(r["b"]) == 0; r["ok_c"] = r["gap"] >= 6.0
        r["ok"] = r["ok_a"] and r["ok_b"] and r["ok_c"]
        rows.append(r)
    return sorted(rows, key=lambda r: (-int(r["ok"]), -(int(r["ok_a"]) + int(r["ok_b"])), -r["gap"], -r["dwall"]))

def hinge(Pl, sd, col_i=None):
    """片 sd 實際的「彎折處」:每一欄從底部折線(flat |y| = CY)往尖端走,先經過立起段(|dz| > |dy|),
    之後第一段 |dz| < |dy| 的起點 = 片從側面轉成往杯頂斜上的地方。col_i 給定 → 回傳那一欄的;另回傳 |flat x|<CX 各欄中位。
    回傳 (y, z, flat_y, 中位 y, 中位 z, 欄數)"""
    NX, F2, CX, CY = S["NX"], S["F2"], S["CX"], S["CY"]
    M = mid(Pl); sg = -1.0 if sd == "yn" else 1.0
    dxy = abs(F2[1, 0] - F2[0, 0])
    res = {}
    for i in range(NX + 1):
        col = np.where((S["ii"] == i) & (sg * F2[:, 1] > CY - 1e-9))[0]
        if not len(col): continue
        col = col[np.argsort(sg * F2[col, 1])]          # 由折線往尖端
        vert = False
        for k in range(len(col) - 1):
            d = M[col[k + 1]] - M[col[k]]
            if abs(d[2]) > abs(d[1]):
                vert = True                                  # 先經過立起的側面
            elif vert and abs(d[2]) < abs(d[1]):
                res[i] = (M[col[k], 1], M[col[k], 2], F2[col[k], 1]); break
    mainc = [i for i in res if abs(F2[i, 0]) <= CX - dxy]
    ym = float(np.median([res[i][0] for i in mainc])) if mainc else float("nan")
    zm = float(np.median([res[i][1] for i in mainc])) if mainc else float("nan")
    if col_i is not None and col_i in res:
        y, z, fy = res[col_i]
    else:
        y, z, fy = ym, zm, float("nan")
    return float(y), float(z), float(fy), ym, zm, len(mainc)

def matlen(Pl, v, sd, yh, zh):
    """夾點那一欄(flat x 同 v)上離鉸點 (y_h,z_h) 最近的頂點 → flat 距離。"""
    F2 = S["F2"]; M = mid(Pl); sg = -1.0 if sd == "yn" else 1.0
    col = np.where((S["ii"] == S["ii"][v]) & (sg * F2[:, 1] > S["CY"] - 1e-9))[0]
    d = np.hypot(M[col, 1] - yh, M[col, 2] - zh)
    h = col[np.argmin(d)]
    return float(abs(F2[v, 1] - F2[h, 1])), int(h), float(d.min())

if __name__ == "__main__":     # 離線自測:對 s2 snap_end 重現 grasp_points.py 的排名
    import sys, os
    HERE = os.path.dirname(os.path.abspath(__file__))
    d = np.load(os.path.join(HERE, "soft/s2/wrap.npz"))
    OFF = np.array([0.0, 0.200, 0.097])
    Pl = d["snap_end"] - OFF; MUG = d["snapmug_end"] - OFF
    setup(d["flat"], 35, 0.08463, 0.07150, trimesh.load(os.path.join(HERE, "mug.stl")).faces)
    box = dict(IX=0.132, IY=0.112, ZFLOOR=0.003, ZOBST=0.135)
    for sd in ("yn", "yp"):
        print(sd, "hinge", np.round(np.array(hinge(Pl, sd, 27)) * 1e3, 1))
        if "--hinge" in sys.argv: continue
        rr = rank(Pl, MUG, sd, box)
        print(sd, "OK", sum(r["ok"] for r in rr), "/", len(rr))
        for r in rr[:5]:
            print("  v%d %s p %s slope %.1f gap %.1f a %d b %s ok %s" % (r["v"], r["kind"], np.round(r["p"], 1), r["slope"], r["gap"], r["a"], r["b"], r["ok"]))
        hh = hinge(Pl, sd, S["ii"][rr[0]["v"]]); print("  hinge of col", hh)
