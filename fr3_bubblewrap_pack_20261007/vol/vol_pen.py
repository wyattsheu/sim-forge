#!/usr/bin/env python3
"""vol_pen.py — volume deformable 的互穿量測(純 numpy / scipy,不用模擬器)。

    python3 vol_pen.py --selftest
        兩塊 200x200x4mm 板(manual 規則格,5-tet):上板往下重疊 1mm → 互穿頂點必須 > 0;
        相隔 1mm → 必須 = 0;同一塊板對折(上半蓋到下半,重疊 1mm / 相隔 1mm)自互穿也同樣判。

函式
  grid_tets(nx,ny,nz,sx,sy,sz,origin)  規則格四面體(volcommon 也用這個)
  tet_vol(P,T)                         有號體積
  points_in_tets(Q, P, T, tol)         Q 的每個點落在 (P,T) 的哪個四面體內(-1 = 不在),tol>0 表示要「確實在內」
  pen_count(PA, idxA, PB, TB, tol)     A 的指定頂點有幾個在 B 的四面體內
  self_pen_count(P, T, P_rest, ...)    同一網格:頂點落在「rest 時離它很遠」的四面體內的個數(不相鄰重疊)
"""
import argparse, sys
import numpy as np
from scipy.spatial import cKDTree

CUBE5 = [[(0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 0, 1)],
         [(0, 0, 0), (1, 0, 1), (1, 1, 0), (0, 1, 1)],
         [(0, 0, 0), (0, 0, 1), (1, 0, 1), (0, 1, 1)],
         [(1, 0, 1), (1, 1, 1), (1, 1, 0), (0, 1, 1)],
         [(0, 0, 0), (1, 1, 0), (0, 1, 0), (0, 1, 1)]]


def tet_vol(P, T):
    a, b, c, d = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]], P[T[:, 3]]
    return np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a) / 6.0


def grid_tets(nx, ny, nz, sx, sy, sz, origin):
    """規則格 -> (pts (V,3), tets (T,4))。頂點索引 (k*(ny+1)+j)*(nx+1)+i。
    5-tet 分割 + 奇偶鏡像(同 deformableMeshUtils.createTetraVoxels),四面體 det[v1-v0,v2-v0,v3-v0] > 0。"""
    origin = np.asarray(origin, float)
    vid = lambda i, j, k: (k * (ny + 1) + j) * (nx + 1) + i
    ii, jj, kk = np.meshgrid(np.arange(nx + 1), np.arange(ny + 1), np.arange(nz + 1), indexing="ij")
    pts = np.zeros(((nx + 1) * (ny + 1) * (nz + 1), 3))
    pts[vid(ii, jj, kk).ravel()] = origin + np.stack([ii.ravel() * sx, jj.ravel() * sy, kk.ravel() * sz], 1)
    tets = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                mx, my, mz = i % 2, j % 2, k % 2
                flip = (mx + my + mz) % 2
                for st_ in CUBE5:
                    t = [st_[1], st_[0], st_[2], st_[3]] if flip else st_
                    tets.append([vid(i + mx + (1 - 2 * mx) * c[0], j + my + (1 - 2 * my) * c[1],
                                     k + mz + (1 - 2 * mz) * c[2]) for c in t])
    tets = np.array(tets, int)
    bad = tet_vol(pts, tets) < 0
    tets[bad] = tets[bad][:, [1, 0, 2, 3]]
    assert (tet_vol(pts, tets) > 0).all()
    return pts, tets


def _bary_setup(P, T):
    A = P[T[:, 0]]
    M = np.stack([P[T[:, 1]] - A, P[T[:, 2]] - A, P[T[:, 3]] - A], axis=2)    # (T,3,3) 欄 = 邊
    det = np.linalg.det(M)
    ok = np.abs(det) > 1e-18
    Minv = np.zeros_like(M)
    Minv[ok] = np.linalg.inv(M[ok])
    return A, Minv, ok


def points_in_tets(Q, P, T, tol=-1e-9, exclude=None):
    """回傳 (len(Q),) 的 tet index(-1 = 不在任何四面體內)。
    tol:重心座標都要 >= tol 才算「在內」(預設 -1e-9:落在內部共用邊/面上也算;tol 無因次)。
    exclude(qi, ti_array) -> bool mask:要排除的配對(例:自己所在的四面體)。"""
    if len(Q) == 0 or len(T) == 0:
        return np.full(len(Q), -1, int)
    A, Minv, ok = _bary_setup(P, T)
    C = P[T].mean(1)
    R = np.linalg.norm(P[T] - C[:, None, :], axis=2).max(1)          # 外接球半徑上界
    tree = cKDTree(C)
    cand = tree.query_ball_point(Q, r=float(R.max()) + 1e-9)
    out = np.full(len(Q), -1, int)
    for qi, lst in enumerate(cand):
        if not lst:
            continue
        ti = np.asarray(lst, int)
        ti = ti[ok[ti]]
        if exclude is not None and len(ti):
            ti = ti[~exclude(qi, ti)]
        if not len(ti):
            continue
        lam = np.einsum("tij,tj->ti", Minv[ti], Q[qi] - A[ti])
        l0 = 1.0 - lam.sum(1)
        inside = (lam >= tol).all(1) & (l0 >= tol)
        if inside.any():
            out[qi] = ti[np.argmax(inside)]
    return out


def pen_count(PA, idxA, PB, TB, tol=-1e-9):
    """A 的頂點 idxA 有幾個落在 B 的四面體內。回傳 (count, 落在內的 A 頂點 index)。"""
    hit = points_in_tets(PA[idxA], PB, TB, tol)
    m = hit >= 0
    return int(m.sum()), np.asarray(idxA)[m]


def self_pen_count(P, T, P_rest, far=None, tol=-1e-9, idx=None):
    """同一網格的不相鄰重疊:頂點 v 落在四面體 t 內,且 t 不含 v、rest 時 v 到 t 的重心距離 > far。
    far 預設 = 3 x rest 最長四面體邊。回傳 (count, 頂點 index)。"""
    E = np.concatenate([T[:, [i, j]] for i in range(4) for j in range(i + 1, 4)])
    Lmax = np.linalg.norm(P_rest[E[:, 0]] - P_rest[E[:, 1]], axis=1).max()
    far = 3.0 * Lmax if far is None else far
    Crest = P_rest[T].mean(1)
    idx = np.arange(len(P)) if idx is None else np.asarray(idx)

    def excl(qi, ti):
        v = idx[qi]
        own = (T[ti] == v).any(1)
        near = np.linalg.norm(Crest[ti] - P_rest[v], axis=1) <= far
        return own | near
    hit = points_in_tets(P[idx], P, T, tol, exclude=excl)
    m = hit >= 0
    return int(m.sum()), idx[m]


def _selftest():
    ok_all = True
    Tm = 0.004
    P1, T1 = grid_tets(20, 20, 1, 0.01, 0.01, Tm, [-0.1, -0.1, 0.0])
    for dz, want in [(-0.001, ">0"), (0.001, "=0")]:
        P2, _ = grid_tets(20, 20, 1, 0.01, 0.01, Tm, [-0.1, -0.1, Tm + dz])
        bot2 = np.where(np.abs(P2[:, 2] - P2[:, 2].min()) < 1e-9)[0]
        n_bot, _ = pen_count(P2, bot2, P1, T1)
        n_all, _ = pen_count(P2, np.arange(len(P2)), P1, T1)
        good = (n_bot > 0) if want == ">0" else (n_bot == 0 and n_all == 0)
        ok_all &= good
        print("兩塊板 上板底面離下板頂面 %+.1fmm:上板底面頂點在下板內 %d / %d(全部頂點 %d)要求 %s ⇒ %s"
              % (dz * 1e3, n_bot, len(bot2), n_all, want, "PASS" if good else "FAIL"))
    # 對折:40x20 格的板,x>0 的半邊繞 x=0 翻到上面(厚度方向鏡像),上層底面離下層頂面 dz
    for dz, want in [(-0.001, ">0"), (0.001, "=0")]:
        P, T = grid_tets(40, 20, 1, 0.005, 0.01, Tm, [-0.1, -0.1, 0.0])
        R = P.copy()
        Q = P.copy()
        m = P[:, 0] > 1e-9
        # 上半:x -> -x,z -> (Tm + dz) + (Tm - z)  (頂面變底面)
        Q[m, 0] = -P[m, 0]
        Q[m, 2] = Tm + dz + (Tm - P[m, 2])
        # 折線(x=0)那一排頂點維持原位;折線附近的四面體會被拉長(不影響 far 判斷)
        n, _ = self_pen_count(Q, T, R)
        good = (n > 0) if want == ">0" else (n == 0)
        ok_all &= good
        print("同一塊板對折 上層離下層 %+.1fmm:不相鄰重疊頂點 %d 要求 %s ⇒ %s" % (dz * 1e3, n, want, "PASS" if good else "FAIL"))
    print("SELFTEST", "PASS" if ok_all else "FAIL")
    return ok_all


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if _selftest() else 1)
    ap.print_help()
