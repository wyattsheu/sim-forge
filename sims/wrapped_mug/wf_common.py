# -*- coding: utf-8 -*-
"""wrapped_mug 共用工具 —— 在 Isaac Sim runtime 內使用(需要 omni.physx)。

這裡收的每一個函式都對應一個實測踩到的坑,註解寫明原因。
"""
import math

import carb
from pxr import UsdGeom, UsdPhysics, UsdShade, PhysxSchema, Gf, Sdf, Vt

from omni.physx import get_physx_attachment_private_interface
from omni.physx.scripts import deformableUtils


# ---------------------------------------------------------------- 基礎
def set_attr(prim, name, value, type_name=None):
    """設定 codeless schema 屬性。屬性不存在且沒給 type_name 就回 False。"""
    a = prim.GetAttribute(name)
    if not (a and a.IsValid()):
        if type_name is None:
            carb.log_warn(f"[wf] attribute missing: {prim.GetPath()}.{name}")
            return False
        a = prim.CreateAttribute(name, type_name)
    a.Set(value)
    return True


def enable_deformable_runtime():
    """開 deformable beta,並要求把模擬結果寫回 USD。

    坑:不設 /physics/updateToUsd 的話,mesh.GetPointsAttr().Get() 讀到的
        永遠是作者時的值,模擬其實有跑但看起來像沒跑。
    """
    st = carb.settings.get_settings()
    st.set_bool("/persistent/physics/enableDeformableBeta", True)
    st.set_bool("/physics/updateToUsd", True)
    st.set_bool("/physics/updateVelocitiesToUsd", True)
    return {
        "enableDeformableBeta": st.get("/persistent/physics/enableDeformableBeta"),
        "updateToUsd": st.get("/physics/updateToUsd"),
    }


def enable_mouse_drag(picking_force=20.0, joint_drag=True, no_shift=True):
    """讓 viewport 可以用滑鼠拉動物體。

    omni.physx.ui 的 on_mouse_shift_drag_start 依序擋四關:
      1. omni.physx.ui 有在跑且持有 viewport overlay
      2. timeline 正在播放
      3. 全程按住 Shift(除非 _mouse_interaction_state = ENABLED)
      4. 沒有其他 gesture / hover 佔用游標(選取 gizmo 會搶)
    這裡處理 3,並把 forceGrab 關掉改用約束式拖曳(不受 pickingForce 縮放影響)。
    """
    st = carb.settings.get_settings()
    st.set_bool("/physics/mouseInteractionEnabled", True)
    st.set_bool("/physics/mouseGrab", True)
    st.set_bool("/physics/mouseGrabIgnoreInvisible", True)
    st.set_bool("/physics/forceGrab", not joint_drag)
    st.set_float("/physics/pickingForce", float(picking_force))
    applied = {
        "mouseInteractionEnabled": True,
        "mouseGrab": True,
        "forceGrab": not joint_drag,
        "pickingForce": float(picking_force),
        "no_shift": False,
    }
    if no_shift:
        try:
            import omni.physxui
            from omni.physxui.scripts.physxViewportOverlays import PhysxUIMouseInteraction
            ext = omni.physxui.get_physxui_instance()
            if ext is not None:
                ext.mouse_interaction_override_toggle(PhysxUIMouseInteraction.ENABLED)
                applied["no_shift"] = True
        except Exception as e:                                   # headless 沒有 UI 很正常
            carb.log_warn(f"[wf] mouse no-shift override unavailable: {e}")
    return applied


# ---------------------------------------------------------------- 場景
def make_physics_scene(stage, path="/physicsScene", steps_per_second=240):
    if not stage.GetPrimAtPath(path):
        UsdPhysics.Scene.Define(stage, path)
    px = PhysxSchema.PhysxSceneAPI.Apply(stage.GetPrimAtPath(path))
    px.CreateEnableGPUDynamicsAttr(True)
    px.CreateBroadphaseTypeAttr("GPU")
    px.CreateSolverTypeAttr("TGS")
    px.CreateTimeStepsPerSecondAttr(int(steps_per_second))
    return px


def make_film_material(stage, path, youngs, poisson, thickness, bend_stiff,
                       dyn_friction, elas_damp, bend_damp, density=None):
    """Surface deformable 物理材質。

    官方限制:staticFriction 無效;surfaceStretchStiffness / surfaceShearStiffness
    完全不支援;surfaceBendStiffness 是唯一的抗彎控制,且 edge bend ∝ SBS·thickness³。
    """
    mat = UsdShade.Material.Define(stage, path)
    p = mat.GetPrim()
    p.ApplyAPI("OmniPhysicsBaseMaterialAPI")
    set_attr(p, "omniphysics:dynamicFriction", float(dyn_friction))
    if density is not None:
        set_attr(p, "omniphysics:density", float(density))
    p.ApplyAPI("OmniPhysicsDeformableMaterialAPI")
    set_attr(p, "omniphysics:youngsModulus", float(youngs))
    set_attr(p, "omniphysics:poissonsRatio", float(poisson))
    p.ApplyAPI("OmniPhysicsSurfaceDeformableMaterialAPI")
    set_attr(p, "omniphysics:surfaceThickness", float(thickness))
    set_attr(p, "omniphysics:surfaceBendStiffness", float(bend_stiff))
    p.ApplyAPI("PhysxSurfaceDeformableMaterialAPI")
    set_attr(p, "physxDeformableMaterial:elasticityDamping", float(elas_damp))
    set_attr(p, "physxDeformableMaterial:bendDamping", float(bend_damp))
    return mat


# ---------------------------------------------------------------- 綁定
def create_attachment(stage, app, path, deformable_path, other_path,
                      overlap=0.006, filter_offset=0.02, max_updates=400):
    """建立 auto deformable attachment,並確認真的抓到頂點。

    兩個坑一起處理:
      1. deformableUtils.create_auto_deformable_attachment() 會立刻 setup,
         之後再改 deformableVertexOverlapOffset 不會重新 cook —— 所以這裡
         自己建 prim、先把 offset 設好,最後才呼叫 setup。
      2. 頂點資料是非同步填的。headless 腳本必須 pump app.update(),
         否則 vtxIndicesSrc0 會是空的:回傳 True 但等於沒綁。
    回傳 (ok, attached_vertex_count)。
    """
    scope = UsdGeom.Scope.Define(stage, path)
    p = scope.GetPrim()
    if not p.ApplyAPI("PhysxAutoDeformableAttachmentAPI"):
        return False, 0
    p.GetRelationship("physxAutoDeformableAttachment:attachable0").SetTargets([Sdf.Path(str(deformable_path))])
    p.GetRelationship("physxAutoDeformableAttachment:attachable1").SetTargets([Sdf.Path(str(other_path))])
    set_attr(p, "physxAutoDeformableAttachment:enableDeformableVertexAttachments", True)
    set_attr(p, "physxAutoDeformableAttachment:deformableVertexOverlapOffset", float(overlap))
    set_attr(p, "physxAutoDeformableAttachment:enableCollisionFiltering", True)
    set_attr(p, "physxAutoDeformableAttachment:collisionFilteringOffset", float(filter_offset))

    ok = get_physx_attachment_private_interface().setup_auto_deformable_attachment(str(path))
    if not ok:
        return False, 0

    for _ in range(max_updates):
        n = attached_vertex_count(stage, path)
        if n > 0:
            return True, n
        if app is not None:
            app.update()
    return True, attached_vertex_count(stage, path)


def attached_vertex_count(stage, path):
    v = stage.GetPrimAtPath(f"{path}/vtx_xform_attachment")
    if v and v.IsValid():
        idx = v.GetAttribute("omniphysics:vtxIndicesSrc0").Get()
        return len(idx) if idx else 0
    v = stage.GetPrimAtPath(f"{path}/vtx_vtx_attachment")
    if v and v.IsValid():
        idx = v.GetAttribute("omniphysics:vtxIndicesSrc0").Get()
        return len(idx) if idx else 0
    return 0


# ---------------------------------------------------------------- 幾何
def grid_mesh(nx, ny, lx, ly, z=0.0, origin=(0.0, 0.0)):
    """回傳 (points, tris)。三角化成對角線一致的規則網格。"""
    pts, tris = [], []
    ox, oy = origin
    for j in range(ny + 1):
        for i in range(nx + 1):
            pts.append(Gf.Vec3f(ox + lx * i / nx, oy + ly * j / ny, z))
    row = nx + 1
    for j in range(ny):
        for i in range(nx):
            a, b, c, d = j * row + i, j * row + i + 1, (j + 1) * row + i + 1, (j + 1) * row + i
            tris.append((a, b, c))
            tris.append((a, c, d))
    return pts, tris


def interior_edge_pairs(tris):
    """回傳 [((t1,t2),(u,v)), ...] —— 每條內部邊的相鄰三角形對與共用邊。"""
    edge_map = {}
    for ti, t in enumerate(tris):
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            key = (a, b) if a < b else (b, a)
            edge_map.setdefault(key, []).append(ti)
    out = []
    for edge, ts in edge_map.items():
        if len(ts) == 2:
            out.append(((ts[0], ts[1]), edge))
    return out


def dihedral_deg(pts, tris, tri_pair, edge):
    """兩個相鄰三角形之間的帶號二面角(度)。平面 = 0。"""
    def nrm(t):
        a, b, c = (Gf.Vec3d(*pts[i]) for i in tris[t])
        n = Gf.Cross(b - a, c - a)
        ln = n.GetLength()
        return n / ln if ln > 1e-12 else Gf.Vec3d(0, 0, 1)
    n1, n2 = nrm(tri_pair[0]), nrm(tri_pair[1])
    e = Gf.Vec3d(*pts[edge[1]]) - Gf.Vec3d(*pts[edge[0]])
    le = e.GetLength()
    e = e / le if le > 1e-12 else Gf.Vec3d(1, 0, 0)
    return math.degrees(math.atan2(Gf.Dot(Gf.Cross(n1, n2), e), Gf.Dot(n1, n2)))


def make_surface_deformable(stage, path, pts, tris, material, mass,
                            solver_iter=64, lin_damp=0.20, self_collision=False,
                            contact_off=0.005, rest_off=0.001,
                            collision_pair_update=1, collision_iter_mult=1,
                            max_depen_vel=0.5, uvs=None):
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.GetPointsAttr().Set(Vt.Vec3fArray(pts))
    mesh.GetFaceVertexCountsAttr().Set([3] * len(tris))
    mesh.GetFaceVertexIndicesAttr().Set([k for t in tris for k in t])
    mesh.CreateDoubleSidedAttr(True)
    if uvs is not None:
        UsdGeom.PrimvarsAPI(mesh.GetPrim()).CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex).Set(Vt.Vec2fArray(uvs))

    prim = mesh.GetPrim()
    ok = deformableUtils.set_physics_surface_deformable_body(stage, prim.GetPath())
    set_attr(prim, "omniphysics:mass", float(mass))
    prim.ApplyAPI("PhysxSurfaceDeformableBodyAPI")
    set_attr(prim, "physxDeformableBody:selfCollision", bool(self_collision))
    set_attr(prim, "physxDeformableBody:solverPositionIterationCount", int(solver_iter), Sdf.ValueTypeNames.UInt)
    set_attr(prim, "physxDeformableBody:linearDamping", float(lin_damp), Sdf.ValueTypeNames.Float)
    set_attr(prim, "physxDeformableBody:maxDepenetrationVelocity", float(max_depen_vel), Sdf.ValueTypeNames.Float)
    set_attr(prim, "physxDeformableBody:collisionPairUpdateFrequency", int(collision_pair_update), Sdf.ValueTypeNames.UInt)
    set_attr(prim, "physxDeformableBody:collisionIterationMultiplier", int(collision_iter_mult), Sdf.ValueTypeNames.UInt)
    c = PhysxSchema.PhysxCollisionAPI.Apply(prim)
    c.CreateRestOffsetAttr().Set(float(rest_off))
    c.CreateContactOffsetAttr().Set(float(contact_off))
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(material, UsdShade.Tokens.weakerThanDescendants, "physics")
    return mesh, bool(ok), c


def refresh_film_offsets(collision_api, contact_off, rest_off):
    """YM 坑 6:綁定建立時會回頭改膜的 offset,所以綁完要再設一次。"""
    collision_api.CreateRestOffsetAttr().Set(float(rest_off))
    collision_api.CreateContactOffsetAttr().Set(float(contact_off))


# ------------------------------------------------- 手動低階綁定(headless 安全)
# 坑:deformableUtils.create_auto_deformable_attachment() 在 headless 會回傳 True,
#     但負責填頂點的 attachment authoring 掛在 UI 側,不會跑 —— vtxIndicesSrc0
#     永遠是空的,等於沒綁。下面直接自己算、自己寫低階 OmniPhysicsVtxXformAttachment。
from pxr import Usd


def verts_in_box(stage, mesh_path, box_path, pad=0.0):
    """回傳落在某個 UsdGeomCube(含 pad)裡的模擬網格頂點索引(世界座標判定)。"""
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath(mesh_path))
    pts = mesh.GetPointsAttr().Get()
    m2w = UsdGeom.Xformable(mesh).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    cube = stage.GetPrimAtPath(box_path)
    size = UsdGeom.Cube(cube).GetSizeAttr().Get() or 2.0
    c2w = UsdGeom.Xformable(cube).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    w2c = c2w.GetInverse()
    h = size / 2.0 + pad
    out = []
    for i, p in enumerate(pts):
        l = w2c.Transform(m2w.Transform(Gf.Vec3d(*p)))
        if abs(l[0]) <= h and abs(l[1]) <= h and abs(l[2]) <= h:
            out.append(i)
    return out


def attach_verts_to_xform(stage, path, mesh_path, xform_path, vtx_indices,
                          filter_elements=None):
    """把指定的模擬網格頂點硬綁到某個 Xformable 的座標系。

    src1 若是(或屬於)剛體,solver 會當成雙向約束;kinematic 剛體即單向拖著走。
    stiffness / damping 在目前的 PhysX 實作無效,綁定一律是硬約束。
    """
    vtx_indices = [int(i) for i in vtx_indices]
    if not vtx_indices:
        return False, 0

    mesh = UsdGeom.Mesh(stage.GetPrimAtPath(mesh_path))
    pts = mesh.GetPointsAttr().Get()
    m2w = UsdGeom.Xformable(mesh).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    x2w = UsdGeom.Xformable(stage.GetPrimAtPath(xform_path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    w2x = x2w.GetInverse()
    local = [Gf.Vec3f(w2x.Transform(m2w.Transform(Gf.Vec3d(*pts[i])))) for i in vtx_indices]

    p = stage.DefinePrim(path, "OmniPhysicsVtxXformAttachment")
    p.GetRelationship("omniphysics:src0").SetTargets([Sdf.Path(str(mesh_path))])
    p.GetRelationship("omniphysics:src1").SetTargets([Sdf.Path(str(xform_path))])
    set_attr(p, "omniphysics:attachmentEnabled", True, Sdf.ValueTypeNames.Bool)
    set_attr(p, "omniphysics:vtxIndicesSrc0", Vt.IntArray(vtx_indices), Sdf.ValueTypeNames.IntArray)
    set_attr(p, "omniphysics:localPositionsSrc1", Vt.Vec3fArray(local), Sdf.ValueTypeNames.Point3fArray)

    if filter_elements:
        f = stage.DefinePrim(path + "_filter", "OmniPhysicsElementCollisionFilter")
        f.GetRelationship("omniphysics:src0").SetTargets([Sdf.Path(str(mesh_path))])
        f.GetRelationship("omniphysics:src1").SetTargets([Sdf.Path(str(xform_path))])
        set_attr(f, "omniphysics:filterEnabled", True, Sdf.ValueTypeNames.Bool)
        set_attr(f, "omniphysics:groupElemCounts0", Vt.UIntArray([len(filter_elements)]), Sdf.ValueTypeNames.UIntArray)
        set_attr(f, "omniphysics:groupElemIndices0", Vt.UIntArray([int(i) for i in filter_elements]), Sdf.ValueTypeNames.UIntArray)
        set_attr(f, "omniphysics:groupElemCounts1", Vt.UIntArray([0]), Sdf.ValueTypeNames.UIntArray)
        set_attr(f, "omniphysics:groupElemIndices1", Vt.UIntArray([]), Sdf.ValueTypeNames.UIntArray)
    return True, len(vtx_indices)


def tris_touching(tris, vtx_set):
    vtx_set = set(vtx_set)
    return [i for i, t in enumerate(tris) if vtx_set & set(t)]
