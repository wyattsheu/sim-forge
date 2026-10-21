"""yieldrule.py — 降伏規則(逐邊靜止角)→ 一致的 rest 嵌入 → 炸開逐三角形 rest(純 numpy/scipy,不碰 Kit)。

每 period 秒:θ = 當下二面角;dev = θ − θ_rest;|dev| > yield_deg 的邊 θ_rest += λ·dev。
有邊降伏 → 解 X = argmin Σ_邊 ((|xi−xj| − L0)/L0)² + Σ_對 wrap(θ(X) − θ_rest)²(從當下形狀起算,幾次 TRF)
→ ccommon.explode_rest(P0, TRIS, X) → 寫 restShapePoints(3T 點)+ restTriVtxIndices + restShapeDefault → SetActive 重建。
(USD 的 omniphysics:restBendAngles 陣列 PhysX 107.3 不讀,見 CREASE.md,所以要繞道 rest 形狀。)"""
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix


def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


class YieldRule:
    def __init__(self, P0, TRIS, PAIRS, E, yield_deg=20.0, lam=0.5):
        self.P0, self.TRIS, self.PAIRS, self.E = P0, TRIS, PAIRS, E
        self.L0 = np.linalg.norm(P0[E[:, 1]] - P0[E[:, 0]], axis=1)
        self.th_rest = np.zeros(len(PAIRS))
        self.ylim = np.radians(yield_deg); self.lam = lam
        # 每對的 4 個頂點:p, q(共用邊)+ 兩個對頂點
        op = []
        for ta, tb, p, q in PAIRS:
            a = [v for v in TRIS[ta] if v != p and v != q][0]; b = [v for v in TRIS[tb] if v != p and v != q][0]
            op.append((a, b))
        self.OP = np.array(op, int)
        n = len(P0); m = len(E) + len(PAIRS)
        S = lil_matrix((m, 3 * n), dtype=int)
        for r, (i, j) in enumerate(E):
            for v in (i, j):
                S[r, 3 * v:3 * v + 3] = 1
        for r, ((ta, tb, p, q), (a, b)) in enumerate(zip(PAIRS, self.OP)):
            for v in (p, q, a, b):
                S[len(E) + r, 3 * v:3 * v + 3] = 1
        self.S = S.tocsr()

    def dihedral(self, X):
        T = self.TRIS; A = X[T[:, 0]]; B = X[T[:, 1]]; C = X[T[:, 2]]
        nn = np.cross(B - A, C - A); nn /= np.linalg.norm(nn, axis=1)[:, None] + 1e-30
        nA = nn[self.PAIRS[:, 0]]; nB = nn[self.PAIRS[:, 1]]
        e = X[self.PAIRS[:, 3]] - X[self.PAIRS[:, 2]]; e /= np.linalg.norm(e, axis=1)[:, None] + 1e-30
        return np.arctan2(np.einsum("ij,ij->i", np.cross(nA, nB), e), np.einsum("ij,ij->i", nA, nB))

    def step(self, X):
        """回傳 (有無降伏, 降伏邊數, 當下 max|dev| 度)。只更新 th_rest。"""
        th = self.dihedral(X); dev = wrap(th - self.th_rest)
        y = np.abs(dev) > self.ylim
        self.th_rest[y] = wrap(self.th_rest[y] + self.lam * dev[y])
        return bool(y.any()), int(y.sum()), float(np.degrees(np.abs(dev).max()))

    def solve(self, X0, max_nfev=30, sep=0.0, sep_flat=0.015, w_sep=3.0):
        """sep > 0:另外要求「攤平時相距 > sep_flat、現在相距 < sep」的頂點對在 rest 裡至少隔 sep
        (把疊在一起的層在 rest 裡撐開,讓 rest 層距 > selfCollisionFilterDistance ≥ 2·restOffset,避免自碰撞被過濾)。"""
        from scipy.spatial import cKDTree
        from scipy.sparse import vstack
        n = len(X0); ne = len(self.E); npr = len(self.PAIRS)
        SP = np.zeros((0, 2), int)
        if sep > 0:
            pr = np.array(sorted(cKDTree(X0).query_pairs(sep)), int).reshape(-1, 2)
            if len(pr):
                pr = pr[np.linalg.norm(self.P0[pr[:, 0]] - self.P0[pr[:, 1]], axis=1) > sep_flat]
            SP = pr
        S = self.S
        if len(SP):
            S2 = lil_matrix((len(SP), 3 * n), dtype=int)
            for r, (i, j) in enumerate(SP):
                S2[r, 3 * i:3 * i + 3] = 1; S2[r, 3 * j:3 * j + 3] = 1
            S = vstack([self.S, S2.tocsr()]).tocsr()
        def res(z):
            X = z.reshape(n, 3)
            r1 = (np.linalg.norm(X[self.E[:, 1]] - X[self.E[:, 0]], axis=1) - self.L0) / self.L0
            r2 = wrap(self.dihedral(X) - self.th_rest)
            if len(SP):
                d = np.linalg.norm(X[SP[:, 1]] - X[SP[:, 0]], axis=1)
                return np.concatenate([r1, r2, w_sep * np.maximum(0.0, sep - d) / sep])
            return np.concatenate([r1, r2])
        r0 = res(X0.ravel())
        sol = least_squares(res, X0.ravel(), jac_sparsity=S, method="trf", x_scale="jac", max_nfev=max_nfev, tr_solver="lsmr")
        r = sol.fun
        X = sol.x.reshape(n, 3)
        info = dict(strain0=float(np.abs(r0[:ne]).max()), ang0=float(np.degrees(np.abs(r0[ne:ne + npr]).max())),
                    strain=float(np.abs(r[:ne]).max()), ang=float(np.degrees(np.abs(r[ne:ne + npr]).max())),
                    ang_med=float(np.degrees(np.median(np.abs(r[ne:ne + npr])))), nfev=int(sol.nfev), nsep=int(len(SP)),
                    sep_min_mm=float(np.linalg.norm(X[SP[:, 1]] - X[SP[:, 0]], axis=1).min() * 1e3) if len(SP) else -1.0)
        return X, info
