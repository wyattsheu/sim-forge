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
# [speed2] 快取 / 加速(結果不變,speed2/prof_plan.py 對 old 逐欄比對):
#   杯 Trimesh 依 MUGl 內容快取(gap_below 沒傳 mugm 時每次重建 49664 面的 rtree);
#   杯 contains 改用垂直射線(trimesh 預設斜射線的 bbox 很大 → rtree 候選面上萬;垂直射線結果逐點相同,1 s → 0.01 s);
#   他層最近距離只對「離最近頂點 < 門檻 + 最長邊」的取樣點算 closest_point(三角形內任一點離某頂點 <= 最長邊 → 精確剔除)。
_MUGC = {}
_BLAS = {}
def _blas_lib():
    """[speed2] 行程裡已載入的 OpenBLAS(numpy 內建)→ (lib, get, set) 或 None"""
    if "lib" not in _BLAS:
        _BLAS["lib"] = None
        try:
            import ctypes
            paths = sorted({l.split()[-1] for l in open("/proc/self/maps") if "openblas" in l.lower() and l.split()[-1].startswith("/")})
            for pth in paths:
                lib = ctypes.CDLL(pth)
                for sfx in ("64_", "_64_", ""):
                    if hasattr(lib, "openblas_set_num_threads" + sfx) and hasattr(lib, "openblas_get_num_threads" + sfx):
                        _BLAS["lib"] = (getattr(lib, "openblas_get_num_threads" + sfx), getattr(lib, "openblas_set_num_threads" + sfx)); break
                if _BLAS["lib"]: break
        except Exception:
            _BLAS["lib"] = None
    return _BLAS["lib"]

class blas1:
    """[speed2] 規劃期間 OpenBLAS 改單執行緒、結束還原。numpy 預設 32 執行緒對這些 (N,3)@(3,3) 小矩陣只會空轉:
    extract6/X2 yn rank 4.6 s wall / 106 s CPU → 2.5 s / 2.5 s(還會搶同機模擬的 CPU)。逐元素結果不變(k 維只有 3,不切)。"""
    def __enter__(self):
        b = _blas_lib(); self.n = None
        if b: self.n = b[0](); b[1](1)
    def __exit__(self, *e):
        b = _blas_lib()
        if b and self.n: b[1](self.n)

def mug_mesh(MUGl):
    k = hash(np.ascontiguousarray(MUGl).tobytes())
    if k not in _MUGC:
        _MUGC.clear(); _MUGC[k] = trimesh.Trimesh(MUGl, S["MF"], process=False)
    return _MUGC[k]

def _xygrid(mesh, h=0.003):
    """[speed2] 三角形 xy AABB(+1e-5,同 trimesh ray_bounds 的 buffer)→ 2D 格 CSR,快取在 mesh 上"""
    g = getattr(mesh, "_sp2_grid", None)
    if g is not None: return g
    tri = mesh.triangles.view(np.ndarray); lo = tri.min(1)[:, :2] - 2e-5; hi = tri.max(1)[:, :2] + 2e-5
    o = lo.min(0); i0 = np.floor((lo - o) / h).astype(int); i1 = np.floor((hi - o) / h).astype(int); nx_ = int(i1[:, 0].max()) + 1; ny_ = int(i1[:, 1].max()) + 1
    cells, tids = [], []
    for dx in range(int((i1 - i0)[:, 0].max()) + 1):
        for dy in range(int((i1 - i0)[:, 1].max()) + 1):
            m = (i0[:, 0] + dx <= i1[:, 0]) & (i0[:, 1] + dy <= i1[:, 1]); t = np.where(m)[0]
            cells.append((i0[t, 0] + dx) * ny_ + (i0[t, 1] + dy)); tids.append(t)
    cells = np.concatenate(cells); tids = np.concatenate(tids); od = np.argsort(cells, kind="stable")
    start = np.searchsorted(cells[od], np.arange(nx_ * ny_ + 1))
    g = dict(h=h, o=o, nx=nx_, ny=ny_, tids=tids[od], start=start, lo=lo, hi=hi, tri=tri, nrm=mesh.face_normals)
    mesh._sp2_grid = g
    return g

def contains_v(mesh, pts):
    """[speed2] = trimesh.ray.ray_util.contains_points(mesh.ray, pts, check_direction=+z)(垂直射線;同一套 planes_lines / barycentric / forward /
    unique_rows / 正反向一致才算),但候選三角形用 2D 格(xy AABB 含點、pad 1e-5 = rtree 的 ray_bounds 超集),不走 rtree。
    與 trimesh 預設斜射線版本逐點比對相同(speed2/prof_plan.py)。"""
    from trimesh import intersections as IS, triangles as TR, bounds as BD, grouping as GR
    pts = np.asanyarray(pts, dtype=np.float64); out = np.zeros(len(pts), bool)
    ia = np.where(BD.contains(mesh.bounds, pts))[0]
    if not len(ia): return out
    g = _xygrid(mesh); Q = pts[ia]
    ci = np.floor((Q[:, :2] - g["o"]) / g["h"]).astype(int)
    okc = (ci >= 0).all(1) & (ci[:, 0] < g["nx"]) & (ci[:, 1] < g["ny"])
    cid = np.where(okc, ci[:, 0] * g["ny"] + ci[:, 1], 0)
    n_ = np.where(okc, g["start"][cid + 1] - g["start"][cid], 0)
    if n_.sum() == 0: return out
    qp = np.repeat(np.arange(len(Q)), n_); off = np.arange(n_.sum()) - np.repeat(np.cumsum(n_) - n_, n_)
    qt = g["tids"][np.repeat(g["start"][cid], n_) + off]
    keep = (g["lo"][qt] <= Q[qp, :2] + 1e-5).all(1) & (g["hi"][qt] >= Q[qp, :2] - 1e-5).all(1)
    qp, qt = qp[keep], qt[keep]
    cnt = [np.zeros(len(Q), bool), np.zeros(len(Q), bool)]
    D = np.zeros((len(qp), 3)); D[:, 2] = 1.0; tc = g["tri"][qt]                 # ±z 的交點 / valid / barycentric 逐位元相同(只差正負號)→ 算一次
    loc, valid = IS.planes_lines(plane_origins=tc[:, 0, :], plane_normals=g["nrm"][qt], line_origins=Q[qp], line_directions=D)
    if valid.any():
        bc = TR.points_to_barycentric(tc[valid], loc)
        hit = (bc > -trimesh.tol.zero).all(1) & (bc < 1 + trimesh.tol.zero).all(1)
        rr0 = qp[valid][hit]; lh0 = loc[hit]; dzh = lh0[:, 2] - Q[rr0, 2]
        for k, fw in enumerate((dzh > -1e-6, -dzh > -1e-6)):
            rr, lh = rr0[fw], lh0[fw]
            if len(rr):
                u = GR.unique_rows(np.column_stack((lh, rr)))[0]
                cnt[k] = np.bincount(rr[u], minlength=len(Q)) % 2 == 1
    agree = cnt[0] == cnt[1]
    out[ia[agree]] = cnt[0][agree]
    nr = ia[_near_surface(mesh, Q, 2e-5) | ~agree]                           # 離表面 < 20 µm 或正反向不一致(射線方向會影響結果的點)→ 用原本的 mesh.contains
    if len(nr): out[nr] = mesh.contains(pts[nr])
    return out

def _near_surface(mesh, Q, eps):
    """[speed2] Q 中離 mesh 表面 < eps 的布林遮罩。小三角形(形心到頂點 <= 99 百分位):形心 KD-tree 半徑 eps + 該上限(精確超集);
    大三角形(杯 STL 有少數細長面):AABB + eps 逐對篩。候選對再用 trimesh.triangles.closest_point。"""
    from scipy.spatial import cKDTree
    from trimesh import triangles as TR
    g = getattr(mesh, "_sp2_ckd", None)
    if g is None:
        tri = mesh.triangles.view(np.ndarray); c = tri.mean(1); ri = np.linalg.norm(tri - c[:, None], axis=2).max(1)
        rs = float(np.percentile(ri, 99)); sm = np.where(ri <= rs)[0]; bg = np.where(ri > rs)[0]
        g = mesh._sp2_ckd = (tri, sm, cKDTree(c[sm]), rs, bg, tri[bg].min(1), tri[bg].max(1), c[sm], ri[sm])
    tri, sm, kt, rs, bg, blo, bhi, cs, rs_i = g; best = np.full(len(Q), np.inf)
    def acc(qp, qt):
        if not len(qp): return
        dv = Q[qp] - TR.closest_point(tri[qt], Q[qp]); np.minimum.at(best, qp, np.einsum("ij,ij->i", dv, dv))
    d0, _ = kt.query(Q, distance_upper_bound=eps + rs + 1e-9); sel = np.where(np.isfinite(d0))[0]
    if len(sel):
        lists = kt.query_ball_point(Q[sel], eps + rs + 1e-9)
        qn = np.array([len(l) for l in lists]); qp = np.repeat(sel, qn); qk = np.concatenate([np.asarray(l, int) for l in lists])
        dc = Q[qp] - cs[qk]; k = np.einsum("ij,ij->i", dc, dc) < (eps + rs_i[qk] + 1e-9) ** 2      # 逐對:該三角形自己的形心到頂點距離
        acc(qp[k], sm[qk[k]])
    if len(bg):
        pi, bi = np.where(((Q[:, None, :] >= blo[None] - eps) & (Q[:, None, :] <= bhi[None] + eps)).all(2)); acc(pi, bg[bi])
    return np.sqrt(best) < eps

def near_count(om, pts, thr):
    """[speed2] = int((trimesh.proximity.closest_point(om, pts)[1] < thr).sum())。
    候選三角形:形心 KD-tree 半徑 thr + 最大形心到頂點距離,再逐對用該三角形自己的形心到頂點距離篩(三角形上任一點離形心 <= 它 → 精確超集);
    某頂點離點 < thr 的直接算(到三角形距離 <= 到頂點距離);其餘逐對用同一個 trimesh.triangles.closest_point。"""
    from scipy.spatial import cKDTree
    from trimesh import triangles as TR
    tri = om.triangles.view(np.ndarray); c = tri.mean(1); ri = np.linalg.norm(tri - c[:, None], axis=2).max(1); rc = float(ri.max())
    kt = cKDTree(c); rr = thr + rc + 1e-9
    d0, _ = kt.query(pts, distance_upper_bound=rr); sel = np.where(np.isfinite(d0))[0]
    if not len(sel): return 0
    fv = np.unique(om.faces); dv, _ = cKDTree(om.vertices[fv]).query(pts[sel], distance_upper_bound=thr)
    sure = np.isfinite(dv) & (dv < thr - 2e-5); n_sure = int(sure.sum()); sel = sel[~sure]
    if not len(sel): return n_sure
    lists = kt.query_ball_point(pts[sel], rr)
    qn = np.array([len(l) for l in lists]); qt = np.concatenate([np.asarray(l, int) for l in lists]); qp = np.repeat(sel, qn)
    dc = pts[qp] - c[qt]; k = np.einsum("ij,ij->i", dc, dc) < (thr + ri[qt] + 1e-9) ** 2; qp, qt = qp[k], qt[k]
    if not len(qp): return n_sure
    cl = TR.closest_point(tri[qt], pts[qp]); dvv = pts[qp] - cl; d2 = np.einsum("ij,ij->i", dvv, dvv)
    best = np.full(len(pts), np.inf); np.minimum.at(best, qp, d2); best = np.sqrt(best)
    amb = np.where(np.abs(best - thr) < 2e-5)[0]                              # 離門檻 < 20 µm:trimesh 的「兩面等距時換面」會讓回報距離差 ~1e-6 → 這幾點直接用 trimesh
    if len(amb):
        _, dd, _ = trimesh.proximity.closest_point(om, pts[amb]); best[amb] = dd
    return n_sure + int((best < thr).sum())

def ray_first(mesh, O, D, bounds=None):
    """[speed2] = mesh.ray.intersects_location(O, D, multiple_hits=False) 的「每條射線第一個交點離起點距離」(沒交到 = inf)。
    不建 rtree:先用射線(截在 mesh AABB 內)聯集 bbox 剔三角形(精確超集),逐對用 trimesh 同一套 planes_lines / points_to_barycentric / forward > -1e-6。"""
    from trimesh import intersections as IS, triangles as TR
    cb = getattr(mesh, "_sp2_tb", None)
    if cb is None: cb = mesh._sp2_tb = (mesh.triangles.view(np.ndarray), mesh.face_normals, mesh.triangles.view(np.ndarray).min(1), mesh.triangles.view(np.ndarray).max(1))
    tri, nrm, tl, th_ = cb
    lo, hi = (mesh.bounds if bounds is None else bounds); lo = lo - 1e-6; hi = hi + 1e-6
    out = np.full(len(O), np.inf)
    with np.errstate(divide="ignore", invalid="ignore"):
        t0 = (lo - O) / D; t1 = (hi - O) / D
    tn = np.nanmax(np.where(np.isfinite(t0), np.minimum(t0, t1), -np.inf), axis=1); tx = np.nanmin(np.where(np.isfinite(t1), np.maximum(t0, t1), np.inf), axis=1)
    inside_slab = np.all(np.where(D == 0, (O >= lo) & (O <= hi), True), axis=1)
    tn = np.maximum(tn, -1e-3); ok = inside_slab & (tx >= tn)
    if not ok.any(): return out
    E0 = O[ok] + D[ok] * tn[ok, None]; E1 = O[ok] + D[ok] * tx[ok, None]
    blo = np.minimum(E0, E1).min(0) - 1e-6; bhi = np.maximum(E0, E1).max(0) + 1e-6
    tm = np.all((th_ >= blo) & (tl <= bhi), axis=1); fi = np.where(tm)[0]
    if not len(fi): return out
    ri = np.where(ok)[0]
    pr = np.repeat(ri, len(fi)); pf = np.tile(fi, len(ri))
    S0 = np.minimum(E0, E1) - 1e-6; S1 = np.maximum(E0, E1) + 1e-6; k_ = np.repeat(np.arange(len(ri)), len(fi))   # 每條射線自己的線段 AABB 再篩一次
    kp = np.all((th_[pf] >= S0[k_]) & (tl[pf] <= S1[k_]), axis=1); pr, pf = pr[kp], pf[kp]
    if not len(pr): return out
    tc = tri[pf]
    loc, valid = IS.planes_lines(plane_origins=tc[:, 0, :], plane_normals=nrm[pf], line_origins=O[pr], line_directions=D[pr])
    if not valid.any(): return out
    bc = TR.points_to_barycentric(tc[valid], loc)
    hit = (bc > -trimesh.tol.zero).all(1) & (bc < 1 + trimesh.tol.zero).all(1)
    rr = pr[valid][hit]; loc = loc[hit]
    dist = np.einsum("ij,ij->i", loc - O[rr], D[rr]); fw = dist > -1e-6
    rr, loc, dist = rr[fw], loc[fw], dist[fw]
    for r_ in np.unique(rr):
        g = np.where(rr == r_)[0]; q = loc[g[dist[g].argmin()]]
        out[r_] = np.linalg.norm(q - O[r_])
    return out

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

def frame(Pl, v, rows=1):
    """rows=2:外法線 u 用『布邊 → 往內第 2 排』的弦(布面凸起時比切線陡,指沿弦插不會撞到內側的布)"""
    M = mid(Pl); vin, _ = inward(v)
    vin = v + rows * (vin - v)                # 往內的索引步長固定(±1 或 ±(NX+1))
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
    if mugm is None: mugm = mug_mesh(MUGl)                                     # [speed2] 快取
    O = samples_box(p, R, [-0.010, -0.015, -half - 1e-4], [0.010, 0.005, -half - 1e-4], step=0.005)
    D = np.tile(-n, (len(O), 1)); dist = np.full(len(O), np.inf)
    if -n[2] < -1e-6:
        dist = np.minimum(dist, (O[:, 2] - box["ZFLOOR"]) / n[2])
    for mesh, off in ((om, T / 2), (mugm, 0.0)):
        if mesh is None or not len(mesh.faces): continue
        dist = np.minimum(dist, ray_first(mesh, O, D) - off)                   # [speed2] 不建 rtree、同一套交點數學
    return float(dist.min())

def rank(Pl, MUGl, sd, box):
    with blas1():                                                             # [speed2]
        return _rank(Pl, MUGl, sd, box)

def _rank(Pl, MUGl, sd, box):
    N1, F2, ii, jj, NX = S["N1"], S["F2"], S["ii"], S["jj"], S["NX"]
    sg = -1.0 if sd == "yn" else 1.0
    M = mid(Pl); ZLO = np.minimum(Pl[:N1, 2], Pl[N1:, 2]); ZHI = np.maximum(Pl[:N1, 2], Pl[N1:, 2])
    THK = np.linalg.norm(Pl[N1:] - Pl[:N1], axis=1)
    bnd = (ii == 0) | (ii == NX) | (jj == 0) | (jj == NX)
    cand = np.where(bnd & (sg * F2[:, 1] > S["CY"] - 1e-9))[0]
    mugm = mug_mesh(MUGl)                                                      # [speed2] 快取
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
        nw = int((outside & (S_[:, 2] < ZO)).sum()); nf = int((S_[:, 2] < ZF).sum()); nm = int(contains_v(mugm, S_).sum())   # [speed2] 垂直射線
        nc = 0
        if om is not None and len(om.faces):
            nc = near_count(om, S_, T / 2 + 0.0005)                           # [speed2] 先剔除遠點
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

def hinge_state(Pl, sd, col_i, zfloor, r_mm=16., dz_mm=2., tol=0.006):
    """[peel2] 彎折處偵測 nan 時:用頂點狀態找實際彎折線。夾點那欄(沒有就 |flat x|<CX 各欄)由折線往尖端走,
    頂點「著地」= 中面離箱底 < tol + 半厚,或 layer_order 下面有他片(under);取連續著地段的最前緣頂點。
    回傳 (y, z, flat_y, 著地點數) 或 None。"""
    import layer_order as LO
    NX, F2, CX, CY, ii = S["NX"], S["F2"], S["CX"], S["CY"], S["ii"]
    M = mid(Pl); sg = -1.0 if sd == "yn" else 1.0
    idx, over, who, under = LO.analyze(M * 1e3, S["SIDE"], sd, r=r_mm, dz=dz_mm)
    UN = np.zeros(len(M), bool); UN[idx] = np.array([u != "" for u in under])
    thk = np.linalg.norm(Pl[len(M):2 * len(M)] - Pl[:len(M)], axis=1) if len(Pl) >= 2 * len(M) else np.full(len(M), 0.004)
    ground = (M[:, 2] - thk / 2 - zfloor < tol) | UN
    def front(i):
        col = np.where((ii == i) & (sg * F2[:, 1] > CY - 1e-9))[0]
        if not len(col): return None
        col = col[np.argsort(sg * F2[col, 1])]
        g = ground[col]
        if not g.any(): return None
        k0 = int(np.argmax(g)); k = k0
        while k + 1 < len(col) and g[k + 1]: k += 1
        return col[k], int(g.sum())
    r = front(col_i) if col_i is not None else None
    if r is None:
        fr = [front(i) for i in range(NX + 1) if abs(F2[i, 0]) <= CX]
        fr = [x for x in fr if x is not None]
        if not fr: return None
        hs = np.array([x[0] for x in fr]); k = np.argsort(M[hs, 1] * sg)[len(hs) // 2]
        r = (hs[k], fr[k][1])
    h, n = r
    return float(M[h, 1]), float(M[h, 2]), float(F2[h, 1]), n

def site_filter(cs, xmax_mm=0., walltop=0, iy=None, ztop=None):
    """[peel2] 排除位置 |x|(箱局部)>= xmax_mm、與已在箱壁頂上(|y| > 內壁 iy 且 z > 壁頂 ztop − 10mm)的候選。回傳 (留下, [(候選, 原因)])"""
    keep, rej = [], []
    for c in cs:
        why = []
        if xmax_mm > 0 and abs(c["p"][0]) >= xmax_mm: why.append("位置 |x| %.1f >= %.0f" % (abs(c["p"][0]), xmax_mm))
        if walltop and iy is not None and abs(c["p"][1]) > iy * 1e3 and c["p"][2] > ztop * 1e3 - 10:
            why.append("箱壁頂上 y %.1f(內壁 %.1f)z %.1f > 壁頂 %.1f − 10" % (c["p"][1], iy * 1e3, c["p"][2], ztop * 1e3))
        (rej.append((c, ";".join(why))) if why else keep.append(c))
    return keep, rej

def site_candidates(*args, **kw):
    with blas1():                                                             # [speed2]
        return _site_candidates(*args, **kw)

def _site_candidates(Pl, sd, gap, pad, nk=7, r_mm=16., dz_mm=2., press_frac=0.3, chord=1, x_margin=0.040):
    """[robust] --grasp_site state:在片 sd 的自由邊(layer_order 的 TOP 邊,j=0/NX 那排)沿邊等距取 nk 個候選,
    對每個候選照 wrap_vol 綁定模式的夾爪框(邊內 12mm、指沿 t 置中於 v 與鄰點之間)離線算
      n_att = |t|,|u| < pad、n ∈ [-(gap/2+4), gap/2+4] mm、歸屬 sd 的頂點數(上下層都算,同 wrap_vol 綁定規則)
      press = 窗內 sd 中面點被他片壓住(layer_order.analyze over)的比例
    回傳依 (未被壓, n_att, 離邊中點近) 排序的 list of dict。"""
    import layer_order as LO
    NX, N1, F2, ii, jj = S["NX"], S["N1"], S["F2"], S["ii"], S["jj"]
    sg = -1.0 if sd == "yn" else 1.0
    jrow = 0 if sd == "yn" else NX
    edge = [v for v in np.where(jj == jrow)[0] if S["SIDE"][v] == sd]
    xs = F2[edge, 0]; lo_x, hi_x = xs.min() + x_margin, xs.max() - x_margin
    edge = [v for v in edge if lo_x <= F2[v, 0] <= hi_x]
    pick = sorted(set(int(round(k)) for k in np.linspace(0, len(edge) - 1, nk)))
    M = mid(Pl)
    idx, over, who, _ = LO.analyze(M * 1e3, S["SIDE"], sd, r=r_mm, dz=dz_mm)
    OV = np.zeros(N1, bool); OV[idx] = over
    WHO = np.array([""] * N1, dtype=object); WHO[idx] = who
    sd2 = S["SIDE2"] == sd
    out = []
    for k in pick:
        v = int(edge[k])
        R0, slope = frame(Pl, v, rows=chord); tt = R0[:, 0]
        nbs = [b for b in (v - 1, v + 1) if 0 <= b < N1 and jj[b] == jrow and S["SIDE"][b] == sd]
        nb = min(nbs, key=lambda b: np.linalg.norm(M[b, :2])) if nbs else v
        p = M[v] + tt * float(np.dot(M[nb] - M[v], tt)) / 2
        pc = p + R0 @ [0, -0.012, 0]
        L = (Pl - pc) @ R0
        win = (np.abs(L[:, 0]) < pad) & (np.abs(L[:, 1]) < pad)
        ma = win & (np.abs(L[:, 2]) <= gap / 2 + 0.004) & sd2
        wm = win[:N1] & sd2[:N1] & (np.abs(L[:N1, 2]) < 0.030)
        nw = int(wm.sum()); npr = int((wm & OV).sum())
        wh = [w for w in WHO[wm & OV] if w]
        out.append(dict(v=v, flat_x=F2[v, 0] * 1e3, p=M[v] * 1e3, slope=slope, n_att=int(ma.sum()), n_win=nw, n_press=npr,
                        press=(npr > press_frac * max(nw, 1)), who=(max(set(wh), key=wh.count) if wh else "-"),
                        n_above=int((win & (L[:, 2] > gap / 2 + 0.004) & sd2).sum()), dmid=abs(F2[v, 0] - (xs.min() + xs.max()) / 2)))
    out.sort(key=lambda c: (c["press"], -c["n_att"], c["dmid"]))
    return out

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
