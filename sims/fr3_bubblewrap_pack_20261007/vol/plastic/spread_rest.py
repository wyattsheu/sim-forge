#!/usr/bin/env python3
"""spread_rest.py — 把「當下(折好)形狀」解成 rest:邊長 = 當下、疊層(不相鄰的兩片中面)撐開到中面距 ≥ T + d。
volume 板 nz=1:頂點 [0,n) = 下表面、[n,2n) = 上表面(同一 column 上下對應),中面 M = (X[:n] + X[n:]) / 2。
    X, info = solve(cur, flat, tets, T, d)
疊層判定:column a、b 在 flat 上距離 > far(預設 2(T+d) + 2 格)且當下中面 3D 距離 < T + d + 2 mm → 一對;
殘差 = w_s·max(0, T+d − |M_a − M_b|)(對稱推開)+ 邊長(所有四面體邊,目標 = 當下長度)+ 很小的錨定(去剛體自由度)。
外迴圈 3 次(層移動後重找對)。scipy least_squares + 解析稀疏 Jacobian。"""
import numpy as np
import scipy.sparse as sp
from scipy.optimize import least_squares
from scipy.spatial import cKDTree


def tet_edges(tets):
    E = np.concatenate([tets[:, [i, j]] for i in range(4) for j in range(i + 1, 4)])
    E.sort(1)
    return np.unique(E, axis=0)


def tet_vol(P, T):
    a, b, c, d = (P[T[:, k]] for k in range(4))
    return np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a) / 6.0


def find_pairs(M, F2, D, far, margin=0.002):
    tr = cKDTree(M)
    pr = np.array(sorted(tr.query_pairs(D + margin)), int).reshape(-1, 2)
    if len(pr) == 0:
        return pr
    fd = np.linalg.norm(F2[pr[:, 0]] - F2[pr[:, 1]], axis=1)
    return pr[fd > far]


def solve(cur, flat, tets, T, d, far=None, w_e=1.0, w_s=3.0, w_a=0.02, outer=3, P=print, w_v=3.0, vmin_ratio=0.3):
    V = len(cur); n = V // 2
    F2 = (flat[:n] + flat[n:]) / 2
    cell = np.median(np.linalg.norm(np.diff(F2[:2], axis=0), axis=1)) if n > 1 else 0.01
    far = 2 * (T + d) + 2 * cell if far is None else far
    D = T + d
    E = tet_edges(tets); L = np.linalg.norm(cur[E[:, 0]] - cur[E[:, 1]], axis=1)
    V0 = np.abs(tet_vol(cur, tets)) + 1e-15; NT = len(tets)                  # 體積障礙:rest 四面體體積 >= vmin_ratio x 當下(防反轉)
    X = cur.copy(); info = dict(D_mm=D * 1e3, far_mm=far * 1e3)
    for it in range(outer):
        M = (X[:n] + X[n:]) / 2
        pr = find_pairs(M, F2, D, far)
        npair = len(pr)
        if npair == 0 and it == 0:
            info.update(npair=0, sep_min_mm=float("nan"), strain=0.0, vmin=float(tet_vol(X, tets).min()), it=0)
            return X, info
        ne, ns = len(E), npair
        # 稀疏結構
        rows = []; cols = []
        for k in range(3):
            rows += [np.arange(ne), np.arange(ne)]; cols += [3 * E[:, 0] + k, 3 * E[:, 1] + k]
        pv = np.stack([pr[:, 0], pr[:, 0] + n, pr[:, 1], pr[:, 1] + n], 1) if ns else np.zeros((0, 4), int)
        for k in range(3):
            for c in range(4):
                rows.append(ne + np.arange(ns)); cols.append(3 * pv[:, c] + k)
        rows.append(ne + ns + np.arange(3 * V)); cols.append(np.arange(3 * V))
        for c in range(4):
            for k in range(3):
                rows.append(ne + ns + 3 * V + np.arange(NT)); cols.append(3 * tets[:, c] + k)
        rows = np.concatenate(rows); cols = np.concatenate(cols)
        X0 = cur.ravel().copy()

        def parts(x):
            Y = x.reshape(-1, 3)
            de = Y[E[:, 0]] - Y[E[:, 1]]; le = np.linalg.norm(de, axis=1) + 1e-12; ue = de / le[:, None]
            if ns:
                Ma = (Y[pr[:, 0]] + Y[pr[:, 0] + n]) / 2; Mb = (Y[pr[:, 1]] + Y[pr[:, 1] + n]) / 2
                ds = Ma - Mb; ls = np.linalg.norm(ds, axis=1) + 1e-12; us = ds / ls[:, None]; act = (ls < D).astype(float)
            else:
                ls = us = act = np.zeros((0,)); us = np.zeros((0, 3))
            return Y, le, ue, ls, us, act

        def fun(x):
            Y, le, ue, ls, us, act = parts(x)
            r_e = w_e * (le - L) / np.maximum(L, 1e-6)
            r_s = w_s * act * (D - ls) / D if ns else np.zeros(0)
            r_a = w_a * (x - X0) / 0.01
            vr = tet_vol(Y, tets) / V0
            r_v = w_v * np.maximum(0.0, vmin_ratio - vr)
            return np.concatenate([r_e, r_s, r_a, r_v])

        def jac(x):
            Y, le, ue, ls, us, act = parts(x)
            ke = (w_e / np.maximum(L, 1e-6))[:, None] * ue
            vals = []
            for k in range(3):
                vals += [ke[:, k], -ke[:, k]]
            ks = (-(w_s / D) * act)[:, None] * us if ns else np.zeros((0, 3))
            for k in range(3):
                for c, sg in enumerate([0.5, 0.5, -0.5, -0.5]):
                    vals.append(sg * ks[:, k])
            vals.append(np.full(3 * V, w_a / 0.01))
            A_, B_, C_, D_ = (Y[tets[:, k]] for k in range(4))
            gb = np.cross(C_ - A_, D_ - A_) / 6; gc = np.cross(D_ - A_, B_ - A_) / 6; gd = np.cross(B_ - A_, C_ - A_) / 6; ga = -(gb + gc + gd)
            act_v = (-(w_v) * ((tet_vol(Y, tets) / V0) < vmin_ratio) / V0)[:, None]
            for gk in (ga, gb, gc, gd):
                for k in range(3):
                    vals.append(act_v[:, 0] * gk[:, k])
            return sp.csr_matrix((np.concatenate(vals), (rows, cols)), shape=(ne + ns + 3 * V + NT, 3 * V))

        res = least_squares(fun, X.ravel(), jac=jac, method="trf", tr_solver="lsmr", max_nfev=60, x_scale=0.001, xtol=1e-10, ftol=1e-10)
        X = res.x.reshape(-1, 3)
        Mx = (X[:n] + X[n:]) / 2
        sepd = np.linalg.norm(Mx[pr[:, 0]] - Mx[pr[:, 1]], axis=1) if ns else np.array([np.nan])
        le = np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1)
        info.update(npair=int(ns), sep_min_mm=float(sepd.min() * 1e3), sep_p5_mm=float(np.percentile(sepd, 5) * 1e3),
                    strain=float(np.abs(le / L - 1).max()), strain_med=float(np.median(np.abs(le / L - 1))),
                    vmin=float(tet_vol(X, tets).min()), disp_max_mm=float(np.linalg.norm(X - cur, axis=1).max() * 1e3), it=it + 1,
                    nfev=int(res.nfev))
        P("  [spread] it %d:疊層對 %d(中面目標 ≥ %.1f mm,far %.1f mm)→ 最小 %.2f p5 %.2f mm | 邊長應變 max %.3f 中位 %.4f | 位移 max %.1f mm | 四面體體積 min %.2e | nfev %d"
          % (it + 1, ns, D * 1e3, far * 1e3, info["sep_min_mm"], info["sep_p5_mm"], info["strain"], info["strain_med"], info["disp_max_mm"], info["vmin"], res.nfev))
    return X, info


def selftest():
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import vol_pen as VP
    T = 0.004; LX, LY = 0.2, 0.1
    p, t = VP.grid_tets(50, 25, 1, LX / 50, LY / 25, T, np.array([0, -LY / 2, 0.001]))
    HX = 0.1; gap = 0.0015; Rm = (T + gap) / 2; zc = 0.001 + T / 2 + Rm; s_ = p[:, 0] - HX; h = p[:, 2] - (0.001 + T / 2); arc = np.pi * Rm
    q = p.copy(); m1 = (s_ > 0) & (s_ <= arc); m2 = s_ > arc; th = s_[m1] / Rm; r_ = Rm - h[m1]
    q[m1, 0] = HX + r_ * np.sin(th); q[m1, 2] = zc - r_ * np.cos(th); q[m2, 0] = HX - (s_[m2] - arc); q[m2, 2] = zc + Rm - h[m2]
    for d in (0.003, 0.005, 0.008):
        X, info = solve(q, p, t, T, d)
        n = len(p) // 2; M = (X[:n] + X[n:]) / 2; F2 = (p[:n] + p[n:]) / 2
        lo = np.where(F2[:, 0] < HX - 0.03)[0]; up = np.where(F2[:, 0] > HX + 0.03)[0]
        tr = cKDTree(M[up][:, :2]); _, j = tr.query(M[lo][:, :2]); dz = M[up][j, 2] - M[lo, 2]
        print("d %.0f mm:中面 z 差 中位 %.2f 最小 %.2f mm(目標 ≥ %.1f)vmin %.2e" % (d * 1e3, np.median(dz) * 1e3, dz.min() * 1e3, (T + d) * 1e3, info["vmin"]))


if __name__ == "__main__":
    selftest()
