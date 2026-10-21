"""ccommon.py — crease 探針共用:surface 布(wrap_sim 同款材料)、kinematic 方塊、vtx attachment、二面角、S1 自穿、錄影資料。
Kit 啟動後才 import(用到 pxr / deformableUtils)。"""
import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, PhysxSchema, Vt
from omni.physx.scripts import deformableUtils

# wrap_sim 同款(EXPERIMENTS.md 共用旗標 --young 2e4 --bend 4;cont/rest 5/1 mm;--thick 0.004)
MAT = dict(young=2.0e4, poisson=0.45, thick=0.004, bend=4.0, fric=0.8, dens=100.0,
           ldamp=0.20, edamp=0.30, bdamp=0.30, cont=0.005, rest=0.001, solver=64)


def sa(prim, n, v, tn=None):
    at = prim.GetAttribute(n)
    if not at or not at.IsValid():
        if tn is None:
            return None
        at = prim.CreateAttribute(n, tn)
    at.Set(v)
    return at


def grid(LX, LY, NX, NY, x0=0.0, y0=None, z0=0.0):
    """規則網格(i 沿 x、j 沿 y),每格兩三角形(同 wrap_sim 的切法)。回傳 P0 (N,3)、TRIS (T,3)、IJ (N,2)。"""
    y0 = -LY / 2 if y0 is None else y0
    P0 = np.array([[x0 + i * LX / NX, y0 + j * LY / NY, z0] for j in range(NY + 1) for i in range(NX + 1)], float)
    IJ = np.array([[i, j] for j in range(NY + 1) for i in range(NX + 1)], int)
    tris = []
    for j in range(NY):
        for i in range(NX):
            A0 = j * (NX + 1) + i
            tris += [(A0, A0 + 1, A0 + NX + 2), (A0, A0 + NX + 2, A0 + NX + 1)]
    return P0, np.array(tris, int), IJ


def adj_pairs(TRIS):
    """內部邊的相鄰三角形對 (ta, tb, p, q):ta < tb,p→q 為 ta 繞行順序中的共用邊方向。"""
    em = {}
    for t, (v0, v1, v2) in enumerate(TRIS):
        for p, q in ((v0, v1), (v1, v2), (v2, v0)):
            em.setdefault((min(p, q), max(p, q)), []).append((t, p, q))
    out = []
    for e, l in em.items():
        if len(l) == 2:
            (ta, pa, qa), (tb, pb, qb) = sorted(l)
            out.append((ta, tb, pa, qa))
    return np.array(out, int)


def dihedrals(Pt, TRIS, PAIRS):
    """帶號二面角(度):atan2(dot(nA×nB, e), nA·nB),平 = 0。"""
    A = Pt[TRIS[:, 0]]; B = Pt[TRIS[:, 1]]; C = Pt[TRIS[:, 2]]
    n = np.cross(B - A, C - A); n /= np.linalg.norm(n, axis=1)[:, None]
    nA = n[PAIRS[:, 0]]; nB = n[PAIRS[:, 1]]
    e = Pt[PAIRS[:, 3]] - Pt[PAIRS[:, 2]]; e /= np.linalg.norm(e, axis=1)[:, None]
    return np.degrees(np.arctan2(np.einsum("ij,ij->i", np.cross(nA, nB), e), np.einsum("ij,ij->i", nA, nB)))


def build_cloth(st, path, P0, TRIS, selfcol=True, mat=None, rest_pts=None, rest_default=None, rb_pairs=None, rb_angles=None,
                self_filter=None, P=print):
    m = dict(MAT); m.update(mat or {})
    sh = UsdGeom.Mesh.Define(st, path)
    sh.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in P0]))
    sh.GetFaceVertexCountsAttr().Set([3] * len(TRIS))
    sh.GetFaceVertexIndicesAttr().Set([int(k) for t in TRIS for k in t])
    sh.CreateDoubleSidedAttr(True)
    sh.CreateDisplayColorAttr([Gf.Vec3f(0.9, 0.55, 0.15)])
    sp = sh.GetPrim()
    mp = path + "_mat"
    phm = UsdShade.Material.Define(st, mp); pp = phm.GetPrim()
    pp.ApplyAPI("OmniPhysicsBaseMaterialAPI")
    sa(pp, "omniphysics:dynamicFriction", m["fric"]); sa(pp, "omniphysics:density", m["dens"])
    pp.ApplyAPI("OmniPhysicsDeformableMaterialAPI")
    sa(pp, "omniphysics:youngsModulus", m["young"]); sa(pp, "omniphysics:poissonsRatio", m["poisson"])
    pp.ApplyAPI("OmniPhysicsSurfaceDeformableMaterialAPI")
    sa(pp, "omniphysics:surfaceThickness", m["thick"]); sa(pp, "omniphysics:surfaceBendStiffness", m["bend"])
    pp.ApplyAPI("PhysxSurfaceDeformableMaterialAPI")
    sa(pp, "physxDeformableMaterial:elasticityDamping", m["edamp"])
    sa(pp, "physxDeformableMaterial:bendDamping", m["bdamp"])
    ok = deformableUtils.set_physics_surface_deformable_body(st, sp.GetPath())
    sp.ApplyAPI("PhysxSurfaceDeformableBodyAPI")
    sa(sp, "physxDeformableBody:selfCollision", bool(selfcol), Sdf.ValueTypeNames.Bool)
    if self_filter is not None:
        sa(sp, "physxDeformableBody:selfCollisionFilterDistance", float(self_filter), Sdf.ValueTypeNames.Float)
    sa(sp, "omniphysics:restBendAnglesDefault", rest_default or "flatDefault", Sdf.ValueTypeNames.Token)
    if rest_pts is not None:
        sa(sp, "omniphysics:restShapePoints", Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in rest_pts]))
    if rb_pairs is not None:
        write_rb(sp, rb_pairs, rb_angles)
    sa(sp, "physxDeformableBody:solverPositionIterationCount", int(m["solver"]), Sdf.ValueTypeNames.Int)
    sa(sp, "physxDeformableBody:linearDamping", float(m["ldamp"]), Sdf.ValueTypeNames.Float)
    pc = PhysxSchema.PhysxCollisionAPI.Apply(sp)
    pc.CreateRestOffsetAttr().Set(m["rest"]); pc.CreateContactOffsetAttr().Set(m["cont"])
    UsdShade.MaterialBindingAPI.Apply(sp).Bind(phm, UsdShade.Tokens.weakerThanDescendants, "physics")
    P("布 %s:%d 點 %d 三角 | E %.0e bend %g thick %.0fmm cont/rest %.0f/%.0f mm selfCollision %s ok=%s"
      % (path, len(P0), len(TRIS), m["young"], m["bend"], m["thick"] * 1e3, m["cont"] * 1e3, m["rest"] * 1e3, selfcol, ok))
    return sp


def write_rb(sp, pairs_tt, angles):
    """omniphysics:restAdjTriPairs (int2[], 三角形索引對) + omniphysics:restBendAngles (float[], 度)。"""
    sa(sp, "omniphysics:restAdjTriPairs", Vt.Vec2iArray([Gf.Vec2i(int(a), int(b)) for a, b in pairs_tt]), Sdf.ValueTypeNames.Int2Array)
    sa(sp, "omniphysics:restBendAngles", Vt.FloatArray([float(x) for x in angles]), Sdf.ValueTypeNames.FloatArray)


def kin_box(st, path, size_xyz, center, collide=True, visible=True):
    xf = UsdGeom.Xform.Define(st, path)
    xf.AddTranslateOp().Set(Gf.Vec3d(*map(float, center)))
    xf.AddOrientOp().Set(Gf.Quatf(1, 0, 0, 0))
    UsdPhysics.RigidBodyAPI.Apply(xf.GetPrim()).CreateKinematicEnabledAttr(True)
    cb = UsdGeom.Cube.Define(st, path + "/geom"); cb.CreateSizeAttr(1.0)
    UsdGeom.Xformable(cb).AddScaleOp().Set(Gf.Vec3f(*map(float, size_xyz)))
    if collide:
        UsdPhysics.CollisionAPI.Apply(cb.GetPrim())
    if not visible:
        UsdGeom.Imageable(xf.GetPrim()).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    return xf.GetPrim()


def attach_vtx(st, scope_path, body_path, rigid_path, vids, local_pos, P=print):
    """wrap_sim / probe_attach2 驗證過的結構:Scope(PhysxAutoDeformableAttachmentAPI)+ 子 OmniPhysicsVtxXformAttachment。"""
    sc = st.DefinePrim(scope_path, "Scope")
    sc.ApplyAPI("PhysxAutoDeformableAttachmentAPI")
    for k2, v2 in [("enableDeformableVertexAttachments", False), ("enableRigidSurfaceAttachments", False),
                   ("enableCollisionFiltering", True), ("enableDeformableFilteringPairs", False)]:
        sa(sc, "physxAutoDeformableAttachment:" + k2, v2, Sdf.ValueTypeNames.Bool)
    sa(sc, "physxAutoDeformableAttachment:collisionFilteringOffset", 0.010, Sdf.ValueTypeNames.Float)
    for rn, tg in [("attachable0", body_path), ("attachable1", rigid_path)]:
        (sc.GetRelationship("physxAutoDeformableAttachment:" + rn) or
         sc.CreateRelationship("physxAutoDeformableAttachment:" + rn)).SetTargets([Sdf.Path(tg)])
    ch = st.DefinePrim(scope_path + "/vtx_xform_attachment", "OmniPhysicsVtxXformAttachment")
    sa(ch, "omniphysics:attachmentEnabled", True, Sdf.ValueTypeNames.Bool)
    sa(ch, "omniphysics:damping", 0.0, Sdf.ValueTypeNames.Float)
    sa(ch, "omniphysics:stiffness", float("inf"), Sdf.ValueTypeNames.Float)
    sa(ch, "omniphysics:vtxIndicesSrc0", Vt.IntArray([int(v) for v in vids]), Sdf.ValueTypeNames.IntArray)
    sa(ch, "omniphysics:localPositionsSrc1", Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in local_pos]),
       Sdf.ValueTypeNames.Point3fArray)
    for rn, tg in [("src0", body_path), ("src1", rigid_path)]:
        (ch.GetRelationship("omniphysics:" + rn) or ch.CreateRelationship("omniphysics:" + rn)).SetTargets([Sdf.Path(tg)])
    P("attachment %s:%d 頂點 → %s" % (scope_path, len(vids), rigid_path))


def quat_y(alpha):
    return np.array([np.cos(alpha / 2), 0.0, np.sin(alpha / 2), 0.0])


def rot_y(alpha):
    c, s = np.cos(alpha), np.sin(alpha)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def pts(st, path):
    return np.array(UsdGeom.Mesh(st.GetPrimAtPath(path)).GetPointsAttr().Get(), float)


def set_pts(st, path, arr):
    UsdGeom.Mesh(st.GetPrimAtPath(path)).GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in arr]))


def edges_of(TRIS):
    ES = set()
    for t in TRIS:
        for u, v in ((0, 1), (1, 2), (2, 0)):
            ES.add((min(t[u], t[v]), max(t[u], t[v])))
    return np.array(sorted(ES), int)


def self_pen(SP, TRI, E=None):
    """S1(wrap_sim 同定義):布的邊穿過布的面的次數(排除共用頂點)。"""
    E = edges_of(TRI) if E is None else E
    P0, P1 = SP[E[:, 0]], SP[E[:, 1]]
    D = P1 - P0
    V0, V1, V2 = SP[TRI[:, 0]], SP[TRI[:, 1]], SP[TRI[:, 2]]
    E1, E2 = V1 - V0, V2 - V0
    hits = 0
    CH = 64
    for s0 in range(0, len(TRI), CH):
        e1 = E1[s0:s0 + CH]; e2 = E2[s0:s0 + CH]; v0 = V0[s0:s0 + CH]; tr = TRI[s0:s0 + CH]
        pv = np.cross(D[:, None, :], e2[None, :, :])
        det = (e1[None, :, :] * pv).sum(-1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = P0[:, None, :] - v0[None, :, :]
        u = (tv * pv).sum(-1) * inv
        qv = np.cross(tv, np.broadcast_to(e1[None, :, :], tv.shape))
        v = (D[:, None, :] * qv).sum(-1) * inv
        tt = (e2[None, :, :] * qv).sum(-1) * inv
        hit = ok & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (tt > 1e-9) & (tt < 1 - 1e-9)
        share = ((E[:, None, 0] == tr[None, :, 0]) | (E[:, None, 0] == tr[None, :, 1]) |
                 (E[:, None, 0] == tr[None, :, 2]) | (E[:, None, 1] == tr[None, :, 0]) |
                 (E[:, None, 1] == tr[None, :, 1]) | (E[:, None, 1] == tr[None, :, 2]))
        hits += int((hit & ~share).sum())
    return hits


def ss(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def explode_rest(P0, TRIS, X):
    """「炸開」的逐三角形 rest:每個三角形 = 攤平時的三角形(P0,在原位置)繞自己重心轉 R_t,
    R_t = 攤平三角形對齊到 X 中同一三角形的最佳旋轉(Kabsch)。
    → 每個三角形面內形狀 = 原始(無應變),相鄰三角形法線夾角 = X 的二面角,但各三角形留在攤平位置,
      rest 裡不同層之間的距離 = 攤平時的距離(不會 < selfCollisionFilterDistance)。回傳 (3T,3) 點。"""
    F = P0[TRIS]; Q = X[TRIS]                                    # (T,3,3)
    cf = F.mean(1, keepdims=True); cq = Q.mean(1, keepdims=True)
    H = np.einsum("tki,tkj->tij", F - cf, Q - cq)
    U, S, Vt_ = np.linalg.svd(H)
    d = np.sign(np.linalg.det(np.einsum("tij,tjk->tik", Vt_.transpose(0, 2, 1), U.transpose(0, 2, 1))))
    D = np.tile(np.eye(3), (len(TRIS), 1, 1)); D[:, 2, 2] = d
    R = np.einsum("tij,tjk,tkl->til", Vt_.transpose(0, 2, 1), D, U.transpose(0, 2, 1))   # R @ f ≈ q
    out = cf + np.einsum("tij,tkj->tki", R, F - cf)
    return out.reshape(-1, 3)


def write_disjoint_rest(st, path, RP, ntri):
    prim = st.GetPrimAtPath(path)
    sa(prim, "omniphysics:restShapePoints", Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in RP]))
    sa(prim, "omniphysics:restTriVtxIndices", Vt.Vec3iArray([Gf.Vec3i(3 * k, 3 * k + 1, 3 * k + 2) for k in range(ntri)]))
    prim.GetAttribute("omniphysics:restBendAnglesDefault").Set("restShapeDefault")
