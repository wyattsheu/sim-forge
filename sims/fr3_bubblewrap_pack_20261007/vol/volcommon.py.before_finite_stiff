#!/usr/bin/env python3
"""volcommon.py — volume deformable 薄板探針共用:建板(manual / auto)、材質、量測、出圖。

只在 SimulationApp 啟動之後 import(要用 pxr / omni.physx)。

建法
  manual:自己把 nxy x nxy x nz 規則格寫成 UsdGeom.TetMesh(每個六面體切 5 個四面體,
          奇偶鏡像,與 deformableMeshUtils.createTetraVoxels 同一套),set_physics_volume_deformable_body。
          這個 TetMesh 同時是 simulation mesh 與 collision mesh。
  auto  :給一個細分過的 box 表面 Mesh 當 cooking source,create_auto_volume_deformable_hierarchy
          (simulation_hex_mesh_enabled=True),physxDeformableBody:resolution = 沿最長邊的六面體數。
          simTet = 體素六面體模擬網格(比幾何大一圈),colTet = 貼合 box 表面的 conforming 四面體。

量測對象(MEAS):manual 用 TetMesh 本身;auto 用 colTet(貼合真實幾何),另外 simTet 也算反轉。
"""
import subprocess, os
import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, Vt
from omni.physx.scripts import deformableUtils, physicsUtils

from vol_pen import grid_tets, tet_vol   # 純 numpy 版本放在 vol_pen.py(selftest 也用)


def sa(prim, n, v, tn=None):
    at = prim.GetAttribute(n)
    if not at or not at.IsValid():
        if tn is None:
            return None
        at = prim.CreateAttribute(n, tn)
    at.Set(v)
    return at


def box_surface(L, W, H, nx, ny, nz, origin):
    """細分 box 表面(三角形,外法線)。origin = 最小角。"""
    vd = {}; pts = []
    def gv(i, j, k):
        key = (i, j, k)
        if key not in vd:
            vd[key] = len(pts)
            pts.append(origin + np.array([L * i / nx, W * j / ny, H * k / nz]))
        return vd[key]
    F = []
    def quad(a, b, c, d):     # a b c d 逆時針(從外看)
        F.extend([(a, b, c), (a, c, d)])
    for j in range(ny):
        for i in range(nx):
            quad(gv(i, j, 0), gv(i, j + 1, 0), gv(i + 1, j + 1, 0), gv(i + 1, j, 0))       # 底 -z
            quad(gv(i, j, nz), gv(i + 1, j, nz), gv(i + 1, j + 1, nz), gv(i, j + 1, nz))   # 頂 +z
    for k in range(nz):
        for i in range(nx):
            quad(gv(i, 0, k), gv(i + 1, 0, k), gv(i + 1, 0, k + 1), gv(i, 0, k + 1))       # -y
            quad(gv(i, ny, k), gv(i, ny, k + 1), gv(i + 1, ny, k + 1), gv(i + 1, ny, k))   # +y
        for j in range(ny):
            quad(gv(0, j, k), gv(0, j, k + 1), gv(0, j + 1, k + 1), gv(0, j + 1, k))       # -x
            quad(gv(nx, j, k), gv(nx, j + 1, k), gv(nx, j + 1, k + 1), gv(nx, j, k + 1))   # +x
    return np.array(pts), np.array(F, int)


def add_material(st, path, youngs, poisson, density, fric, edamp=0.0):
    deformableUtils.add_deformable_material(st, path, density=density, static_friction=fric,
                                            dynamic_friction=fric, youngs_modulus=youngs, poissons_ratio=poisson)
    mp = st.GetPrimAtPath(path)
    if edamp > 0:
        mp.ApplyAPI("PhysxDeformableMaterialAPI")
        sa(mp, "physxDeformableMaterial:elasticityDamping", edamp, Sdf.ValueTypeNames.Float)
    return path


def build_plate(st, path, size, thick, z0, build, nxy=20, nz=1, res=0, youngs=2e4, poisson=0.45,
                areal=0.1, fric=0.8, cont=0.002, rest=0.0005, solver=32, self_coll=False,
                self_filter=None, ldamp=0.0, edamp=0.0, cx=0.0, cy=0.0, nx=None, pmap=None, P=print, size_y=None):
    """建一塊 size x size_y x thick 的板(size_y 未給 = 正方形),底面在 z0、中心在 (cx,cy)。回傳 dict。"""
    size_y = size if size_y is None else size_y
    origin = np.array([cx - size / 2, cy - size_y / 2, z0])
    density = areal / thick
    mat = add_material(st, path + "_mat", youngs, poisson, density, fric, edamp)
    info = dict(path=path, build=build, size=size, thick=thick, density=density)
    if build == "manual":
        nx_ = nx or nxy
        pts, tets = grid_tets(nx_, nxy, nz, size / nx_, size_y / nxy, thick / nz, origin)
        if pmap is not None:            # 例:預折(rest = points = 折好的形狀)
            pts = pmap(pts)
            v = tet_vol(pts, tets)
            P("  pmap 後四面體體積 min %.3e max %.3e(<=0 的 %d 個)" % (v.min(), v.max(), int((v <= 0).sum())))
        tm = UsdGeom.TetMesh.Define(st, path)
        tm.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in pts]))
        tm.GetTetVertexIndicesAttr().Set(Vt.Vec4iArray([Gf.Vec4i(*map(int, t)) for t in tets]))
        ok = deformableUtils.set_physics_volume_deformable_body(st, Sdf.Path(path))
        P("set_physics_volume_deformable_body(%s) -> %s" % (path, ok))
        body = col = sim = st.GetPrimAtPath(path)
        physicsUtils.add_physics_material_to_prim(st, body, mat)
        info.update(sim_path=path, col_path=path, body_path=path, ok=ok)
    else:
        UsdGeom.Xform.Define(st, path)
        nsx = max(1, nxy)
        spts, F = box_surface(size, size, thick, nsx, nsx, 1, origin)
        src = UsdGeom.Mesh.Define(st, path + "/mesh")
        src.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in spts]))
        src.CreateFaceVertexIndicesAttr([int(k) for f in F for k in f])
        src.CreateFaceVertexCountsAttr([3] * len(F))
        ok = deformableUtils.create_auto_volume_deformable_hierarchy(
            st, root_prim_path=path, simulation_tetmesh_path=path + "/simTet",
            collision_tetmesh_path=path + "/colTet", cooking_src_mesh_path=path + "/mesh",
            simulation_hex_mesh_enabled=True, cooking_src_simplification_enabled=False,
            set_visibility_with_guide_purpose=False)
        P("create_auto_volume_deformable_hierarchy(%s) -> %s  (cooking src %d 點 %d 三角形)"
          % (path, ok, len(spts), len(F)))
        body = st.GetPrimAtPath(path)
        sa(body, "physxDeformableBody:resolution", int(res), Sdf.ValueTypeNames.UInt)
        col = st.GetPrimAtPath(path + "/colTet")
        physicsUtils.add_physics_material_to_prim(st, body, mat)
        info.update(sim_path=path + "/simTet", col_path=path + "/colTet", body_path=path, ok=ok)
    # PhysX body 參數
    body.ApplyAPI("PhysxBaseDeformableBodyAPI")
    sa(body, "physxDeformableBody:solverPositionIterationCount", int(solver), Sdf.ValueTypeNames.UInt)
    sa(body, "physxDeformableBody:selfCollision", bool(self_coll), Sdf.ValueTypeNames.Bool)
    if self_filter is not None:
        sa(body, "physxDeformableBody:selfCollisionFilterDistance", float(self_filter), Sdf.ValueTypeNames.Float)
    if ldamp > 0:
        sa(body, "physxDeformableBody:linearDamping", float(ldamp), Sdf.ValueTypeNames.Float)
    # collider 偏移(在 collision mesh 上)
    from pxr import PhysxSchema
    pc = PhysxSchema.PhysxCollisionAPI.Apply(col)
    info["default_contact"] = pc.GetContactOffsetAttr().Get()
    info["default_rest"] = pc.GetRestOffsetAttr().Get()
    if cont is not None:
        pc.CreateContactOffsetAttr().Set(float(cont))
    if rest is not None:
        pc.CreateRestOffsetAttr().Set(float(rest))
    P("  collider %s:schema 預設 contactOffset=%s restOffset=%s → 設 %s / %s"
      % (info["col_path"], info["default_contact"], info["default_rest"], cont, rest))
    return info


class Mesh:
    """讀一個 TetMesh prim(points/tets)。points 是 mesh space;這裡的 prim 都沒有 xform,等於 world。"""
    def __init__(self, st, path):
        self.prim = st.GetPrimAtPath(path)
        self.tm = UsdGeom.TetMesh(self.prim)
        self.pa = self.tm.GetPointsAttr()

    def tets(self):
        t = self.tm.GetTetVertexIndicesAttr().Get()
        return np.array(t, int).reshape(-1, 4) if t is not None and len(t) else np.zeros((0, 4), int)

    def pts(self):
        p = self.pa.Get()
        return np.array(p, float).reshape(-1, 3) if p is not None and len(p) else np.zeros((0, 3))

    def surf(self):
        f = self.tm.GetSurfaceFaceVertexIndicesAttr().Get()
        return np.array(f, int).reshape(-1, 3) if f is not None and len(f) else np.zeros((0, 3), int)


def thickness_pairs(P0, thick, z0=None, tol=None):
    """由(仍平的)初始位置找 (底面頂點, 頂面頂點) 配對:底面 z≈min、頂面 z≈min+thick,xy 相同。
    z0 不用(reset 時可能已經走了一步),以 P0 的最低 z 為底。"""
    tol = tol if tol is not None else thick * 0.05
    zb = P0[:, 2].min()
    bot = np.where(np.abs(P0[:, 2] - zb) < tol)[0]
    top = np.where(np.abs(P0[:, 2] - (zb + thick)) < tol)[0]
    from scipy.spatial import cKDTree
    tr = cKDTree(P0[bot, :2])
    d, k = tr.query(P0[top, :2])
    ok = d < 1e-4
    return bot[k[ok]], top[ok]


def thickness(P, pairs):
    b, t = pairs
    return np.linalg.norm(P[t] - P[b], axis=1)


def inverted(P, T, V0):
    v = tet_vol(P, T)
    return int((v * np.sign(V0) <= 0).sum()), v


def gpu_mem_mib():
    """這個 process 在 GPU 上用的顯存(MiB);拿不到就回整卡已用。"""
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,used_memory",
                                       "--format=csv,noheader,nounits"], text=True)
        for ln in out.strip().splitlines():
            pid, mem = [s.strip() for s in ln.split(",")]
            if int(pid) == os.getpid():
                return "%s MiB(本 process)" % mem
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used",
                                       "--format=csv,noheader,nounits"], text=True)
        return "%s MiB(整卡已用,process 列表查不到本 pid)" % out.strip()
    except Exception as e:
        return "n/a (%s)" % e


def snap(path, P, title, groups=None, xlim=None, zlim=None, extra=None):
    """存一張兩格圖:左 x-z 側視、右 x-y 俯視。groups = [(idx, color, label), ...]。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.2))
    groups = groups or [(np.arange(len(P)), "tab:blue", "verts")]
    for idx, c, lb in groups:
        ax[0].scatter(P[idx, 0] * 1e3, P[idx, 2] * 1e3, s=1.5, c=c, label=lb)
        ax[1].scatter(P[idx, 0] * 1e3, P[idx, 1] * 1e3, s=1.5, c=c, label=lb)
    if extra is not None:
        for fn in extra:
            fn(ax)
    ax[0].set_xlabel("x mm"); ax[0].set_ylabel("z mm"); ax[0].set_aspect("equal")
    ax[1].set_xlabel("x mm"); ax[1].set_ylabel("y mm"); ax[1].set_aspect("equal")
    if xlim: ax[0].set_xlim(*xlim); ax[1].set_xlim(*xlim)
    if zlim: ax[0].set_ylim(*zlim)
    ax[0].legend(loc="upper right", fontsize=7, markerscale=5)
    ax[0].grid(alpha=.3); ax[1].grid(alpha=.3)
    fig.suptitle(title)
    fig.tight_layout(); fig.savefig(path, dpi=90); plt.close(fig)


def kin_box(st, path, size_xyz, center, collide=True, visible=True):
    """kinematic 剛體:Xform(RigidBody,無 scale)+ 子 Cube(size 1 + scale,CollisionAPI)。
    body frame 不含 scale,所以 attachment 的 localPositionsSrc1 = 世界座標差轉到 body 旋轉框。"""
    from pxr import Gf
    xf = UsdGeom.Xform.Define(st, path)
    xf.AddTranslateOp().Set(Gf.Vec3d(*map(float, center)))
    xf.AddOrientOp().Set(Gf.Quatf(1, 0, 0, 0))
    rb = UsdPhysics.RigidBodyAPI.Apply(xf.GetPrim())
    rb.CreateKinematicEnabledAttr(True)
    cb = UsdGeom.Cube.Define(st, path + "/geom"); cb.CreateSizeAttr(1.0)
    UsdGeom.Xformable(cb).AddScaleOp().Set(Gf.Vec3f(*map(float, size_xyz)))
    if collide:
        UsdPhysics.CollisionAPI.Apply(cb.GetPrim())
    if not visible:
        UsdGeom.Imageable(xf.GetPrim()).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    return xf.GetPrim()


def attach_auto(st, scope_path, body_path, rigid_path, overlap=0.0, P=print):
    """create_auto_deformable_attachment(volume ↔ rigid)。回傳 scope path。"""
    ok = deformableUtils.create_auto_deformable_attachment(st, Sdf.Path(scope_path), Sdf.Path(body_path),
                                                           Sdf.Path(rigid_path))
    sc = st.GetPrimAtPath(scope_path)
    if sc and overlap > 0:
        sa(sc, "physxAutoDeformableAttachment:deformableVertexOverlapOffset", float(overlap), Sdf.ValueTypeNames.Float)
    P("create_auto_deformable_attachment(%s: %s ↔ %s) -> %s" % (scope_path, body_path, rigid_path, ok))
    return ok


def attach_vtx(st, scope_path, body_path, src0_path, rigid_path, vids, local_pos, P=print):
    """surface 版那套:Scope(PhysxAutoDeformableAttachmentAPI)+ 子 prim OmniPhysicsVtxXformAttachment。
    src0 指到 volume 的 simulation mesh。"""
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
    for rn, tg in [("src0", src0_path), ("src1", rigid_path)]:
        (ch.GetRelationship("omniphysics:" + rn) or ch.CreateRelationship("omniphysics:" + rn)).SetTargets([Sdf.Path(tg)])
    P("VtxXformAttachment %s:%d 個頂點,src0=%s src1=%s" % (scope_path, len(vids), src0_path, rigid_path))
    return True


def dump_prim(st, path, P=print, maxlen=6):
    """印出 prim 與子 prim 的型別、API、屬性(陣列只印長度)。"""
    for pr in Usd.PrimRange(st.GetPrimAtPath(path)):
        P("  [%s] %s apis=%s" % (pr.GetTypeName(), pr.GetPath(), list(pr.GetAppliedSchemas())))
        for at in pr.GetAttributes():
            v = at.Get()
            if v is None:
                continue
            try:
                n = len(v)
                if not isinstance(v, str) and n > maxlen:
                    v = "<len %d> %s ..." % (n, list(v[:maxlen]))
            except TypeError:
                pass
            P("      %s = %s" % (at.GetName(), v))
        for rl in pr.GetRelationships():
            P("      rel %s -> %s" % (rl.GetName(), rl.GetTargets()))


def quat_y(alpha):
    """繞 +y 轉 alpha(rad)的 quaternion (w,x,y,z)。+x 會轉向 -z(alpha>0)。"""
    return np.array([np.cos(alpha / 2), 0.0, np.sin(alpha / 2), 0.0])


def rot_y(alpha):
    c, s = np.cos(alpha), np.sin(alpha)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
