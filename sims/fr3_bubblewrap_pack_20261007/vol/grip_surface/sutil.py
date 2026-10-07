#!/usr/bin/env python3
"""sutil.py — grip_surface/ 探針共用:surface deformable 布(照 work/wrap_sim.py 定案)+ 量測。

  build_sheet(st, path, S, n, z0, cx, cy, ...)  S x S 平面三角網格(n x n 格),surface deformable
  SMesh(st, path)                                讀 points
  tri_edges(F)                                   唯一邊
  bary_samples(k)                                三角形內均勻取樣的重心座標(含頂點、邊)
  edge_tri_cross(PA, EA, PB, FB)                 A 的邊穿過 B 的面 次數(work/wrap_sim.py self_pen 同法,跨兩片)
材料(定案,wrap_sim.py):young 2e4、nu 0.45、bend 4、surfaceThickness 4mm、density 100、摩擦 0.8、
  linDamp 0.2、elastDamp 0.3、bendDamp 0.3、selfCollision on、solver 64、restBend flatDefault、
  collider contactOffset 5mm / restOffset 1mm。sleep 參數預設不套(--sleepy 才套,見 wrap_sim 註解:會睡著)。
"""
import numpy as np
from pxr import Gf, Sdf, UsdGeom, UsdShade, PhysxSchema, Vt
from omni.physx.scripts import deformableUtils


def sa(prim, n, v, tn=None):
    at = prim.GetAttribute(n)
    if not at or not at.IsValid():
        if tn is None:
            return None
        at = prim.CreateAttribute(n, tn)
    at.Set(v)
    return at


def grid(S, n, z0, cx, cy):
    V = np.array([[cx - S / 2 + i * S / n, cy - S / 2 + j * S / n, z0] for j in range(n + 1) for i in range(n + 1)])
    F = []
    for j in range(n):
        for i in range(n):
            A0 = j * (n + 1) + i
            F += [(A0, A0 + 1, A0 + n + 2), (A0, A0 + n + 2, A0 + n + 1)]
    return V, np.array(F, int)


def build_sheet(st, path, S, n, z0, cx, cy, young=2e4, poisson=0.45, bend=4.0, thick=0.004, dens=100.0, fric=0.8,
                cont=0.005, rest=0.001, solver=64, selfcol=True, sleepy=False, color=(0.25, 0.55, 0.85)):
    V, F = grid(S, n, z0, cx, cy)
    sh = UsdGeom.Mesh.Define(st, path)
    sh.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in V]))
    sh.GetFaceVertexCountsAttr().Set([3] * len(F))
    sh.GetFaceVertexIndicesAttr().Set([int(k) for k in F.ravel()])
    sh.CreateDoubleSidedAttr(True)
    sh.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    sp = sh.GetPrim()
    mp = path + "_phys"
    phm = UsdShade.Material.Define(st, mp); pp = phm.GetPrim()
    pp.ApplyAPI("OmniPhysicsBaseMaterialAPI")
    sa(pp, "omniphysics:dynamicFriction", fric); sa(pp, "omniphysics:density", dens)
    pp.ApplyAPI("OmniPhysicsDeformableMaterialAPI")
    sa(pp, "omniphysics:youngsModulus", young); sa(pp, "omniphysics:poissonsRatio", poisson)
    pp.ApplyAPI("OmniPhysicsSurfaceDeformableMaterialAPI")
    sa(pp, "omniphysics:surfaceThickness", thick); sa(pp, "omniphysics:surfaceBendStiffness", bend)
    pp.ApplyAPI("PhysxSurfaceDeformableMaterialAPI")
    sa(pp, "physxDeformableMaterial:elasticityDamping", 0.3)
    sa(pp, "physxDeformableMaterial:bendDamping", 0.3)
    ok = deformableUtils.set_physics_surface_deformable_body(st, sp.GetPath())
    sp.ApplyAPI("PhysxSurfaceDeformableBodyAPI")
    sa(sp, "physxDeformableBody:selfCollision", bool(selfcol))
    sa(sp, "omniphysics:restBendAnglesDefault", "flatDefault", Sdf.ValueTypeNames.Token)
    if sleepy:
        sa(sp, "physxDeformableBody:settlingDamping", 10.0, Sdf.ValueTypeNames.Float)
        sa(sp, "physxDeformableBody:settlingThreshold", 0.10, Sdf.ValueTypeNames.Float)
        sa(sp, "physxDeformableBody:sleepThreshold", 0.05, Sdf.ValueTypeNames.Float)
    sa(sp, "physxDeformableBody:solverPositionIterationCount", int(solver), Sdf.ValueTypeNames.Int)
    sa(sp, "physxDeformableBody:linearDamping", 0.2, Sdf.ValueTypeNames.Float)
    pc = PhysxSchema.PhysxCollisionAPI.Apply(sp)
    pc.CreateRestOffsetAttr().Set(float(rest)); pc.CreateContactOffsetAttr().Set(float(cont))
    UsdShade.MaterialBindingAPI.Apply(sp).Bind(phm, UsdShade.Tokens.weakerThanDescendants, "physics")
    return dict(ok=ok, V=V, F=F, path=path)


class SMesh:
    def __init__(self, st, path):
        self.pa = UsdGeom.Mesh(st.GetPrimAtPath(path)).GetPointsAttr()

    def pts(self):
        return np.array(self.pa.Get(), float).reshape(-1, 3)


def tri_edges(F):
    return np.unique(np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1), axis=0)


def bary_samples(k=4):
    B = [(i / k, j / k, 1 - i / k - j / k) for i in range(k + 1) for j in range(k + 1 - i)]
    return np.array(B)


def surf_samples(P, F, B):
    """(nF*nB, 3) 三角形面上取樣點。"""
    return np.einsum("bk,fkd->fbd", B, P[F]).reshape(-1, 3)


def tri_normals(P, F):
    n = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)


def edge_tri_cross(PA, EA, PB, FB, CH=128):
    """A 的邊(EA)穿過 B 的三角形(FB)的次數。兩片不共用頂點,不用排除相鄰。"""
    P0, P1 = PA[EA[:, 0]], PA[EA[:, 1]]
    D = P1 - P0
    V0, V1, V2 = PB[FB[:, 0]], PB[FB[:, 1]], PB[FB[:, 2]]
    E1, E2 = V1 - V0, V2 - V0
    hits = 0
    for s0 in range(0, len(FB), CH):
        e1 = E1[s0:s0 + CH]; e2 = E2[s0:s0 + CH]; v0 = V0[s0:s0 + CH]
        pv = np.cross(D[:, None, :], e2[None, :, :])
        det = (e1[None, :, :] * pv).sum(-1)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = P0[:, None, :] - v0[None, :, :]
        u = (tv * pv).sum(-1) * inv
        qv = np.cross(tv, np.broadcast_to(e1[None, :, :], tv.shape))
        v = (D[:, None, :] * qv).sum(-1) * inv
        tt = (e2[None, :, :] * qv).sum(-1) * inv
        hit = ok & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (tt > 1e-9) & (tt < 1 - 1e-9)
        hits += int(hit.sum())
    return hits


def self_cross(P, E, F, CH=128):
    """同一片:邊穿面(排除共用頂點)。"""
    P0, P1 = P[E[:, 0]], P[E[:, 1]]
    D = P1 - P0
    V0, V1, V2 = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    E1, E2 = V1 - V0, V2 - V0
    hits = 0
    for s0 in range(0, len(F), CH):
        e1 = E1[s0:s0 + CH]; e2 = E2[s0:s0 + CH]; v0 = V0[s0:s0 + CH]; tr = F[s0:s0 + CH]
        pv = np.cross(D[:, None, :], e2[None, :, :])
        det = (e1[None, :, :] * pv).sum(-1)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = P0[:, None, :] - v0[None, :, :]
        u = (tv * pv).sum(-1) * inv
        qv = np.cross(tv, np.broadcast_to(e1[None, :, :], tv.shape))
        v = (D[:, None, :] * qv).sum(-1) * inv
        tt = (e2[None, :, :] * qv).sum(-1) * inv
        hit = ok & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (tt > 1e-9) & (tt < 1 - 1e-9)
        share = np.zeros_like(hit)
        for a_ in range(2):
            for b_ in range(3):
                share |= E[:, None, a_] == tr[None, :, b_]
        hits += int((hit & ~share).sum())
    return hits
