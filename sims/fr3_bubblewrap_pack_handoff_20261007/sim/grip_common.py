#!/usr/bin/env python3
"""grip_common.py — 三個夾取實驗的共用零件。

提供:
  scene_setup(world)                        場景/GPU/deformable beta/燈/地面
  cam_quat(eye,tgt)                         look-at 四元數 (抄 bear_a5)
  make_bear_mesh(scale)                     純 numpy 多橢球合併泰迪熊 (身體/頭/吻/兩耳/兩手/兩腳)
  add_soft_bear(stage, path, pts, faces...) Volume FEM 軟體熊 (add_physx_deformable_body)
  add_rigid_bear(stage, path, pts, faces...) 同網格但當剛體 (袋子內裝重物用)
  make_bag(stage, path, ...)                Surface deformable 薄膜袋 (toy_surf 配方)
  Gripper(...)                              兩片 kinematic 夾爪墊,每幀設位姿
  smoothstep(a,b,t)                         平滑插值

設計要點 (全部來自踩過的坑, 見 memory volume-fem / deformable-render):
  - deformable 一律 cook 到原點 → 頂點授權成原點置中, 再用 translate op 擺位
  - deformable 自己的 physxCollision:contactOffset 預設 ~2cm → 夾爪還沒碰到就被推開;
    一定要在 deformable 的 prim 上設小 (0.003), restOffset 0
  - Volume FEM 的 render mesh = 授權的 mesh, 會隨模擬變形 → 直接看得到熊 (bear_a5 驗證)
  - kinematic 夾爪墊: RigidBodyAPI + kinematicEnabled, 每幀寫 translate op (專案的推桿就這樣動)
  - 夾持建立時關重力幾步再開, 避免接觸瞬間衝量 (memory)
"""
import math, numpy as np
from pxr import UsdGeom, UsdPhysics, UsdShade, UsdLux, PhysxSchema, Gf, Sdf, Vt, Usd
from omni.physx.scripts import deformableUtils, physicsUtils
import omni.usd

P = lambda *s: print(*s, flush=True)


# ------------------------------------------------------------------ 場景
def scene_setup(world, ground=True):
    stage = omni.usd.get_context().get_stage()
    ps = PhysxSchema.PhysxSceneAPI.Apply(stage.GetPrimAtPath("/physicsScene"))
    ps.CreateEnableGPUDynamicsAttr(True)
    ps.CreateBroadphaseTypeAttr("GPU")
    # 兩種 deformable 都要 (task C 同場): soft body + surface
    for attr, val in [("CreateGpuMaxSoftBodyContactsAttr", 2 * 1048576),
                      ("CreateGpuMaxDeformableSurfaceContactsAttr", 4 * 1048576),
                      ("CreateGpuCollisionStackSizeAttr", 128 * 1024 * 1024)]:
        try:
            getattr(ps, attr)(val)
        except Exception as e:
            P("  (scene attr %s skipped: %s)" % (attr, e))
    if ground:
        world.scene.add_default_ground_plane()
    # 適中打光(deformable 全黑不是光的問題, 之前調太亮會過曝)。
    UsdLux.DomeLight.Define(stage, "/World/dome").CreateIntensityAttr(1000.0)
    for nm, r, inten in [("key", (-42, 25, 0), 1800), ("fill", (-35, -150, 0), 900),
                         ("front", (-22, -90, 0), 1200)]:
        dl = UsdLux.DistantLight.Define(stage, "/World/" + nm)
        dl.CreateIntensityAttr(float(inten))
        UsdGeom.Xformable(dl.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(*r))
    return stage


# ------------------------------------------------------------------ 相機
def look(cam, eye, tgt):
    """驗證過的 euler look-at (memory isaac-camera-lookat)。相機光軸 = local +X。
    別手刻旋轉矩陣, 之前那樣一律拍到地板。俯視時 eye 要留一點水平偏移避免 gimbal。"""
    import isaacsim.core.utils.numpy.rotations as rot
    e = np.array(eye, float); f = np.array(tgt, float) - e; f /= np.linalg.norm(f)
    cam.set_world_pose(e, rot.euler_angles_to_quats(
        np.array([0.0, math.degrees(math.asin(-f[2])), math.degrees(math.atan2(f[1], f[0]))]),
        degrees=True))


def add_headlight(stage, eye, tgt, intensity=8000.0, name="headlight"):
    """★ 從相機方向打的 distant 光(headlight): 照亮相機看到的那一面。
    之前物體全黑不是 deformable 問題 —— 是相機在看物體的『背光面』(連剛體紅球都黑)。
    DistantLight 沿 local -Z 發光 → 把 -Z 轉到 (tgt-eye) 方向。"""
    d = np.array(tgt, float) - np.array(eye, float); d /= np.linalg.norm(d)
    dl = UsdLux.DistantLight.Define(stage, "/World/" + name)
    dl.CreateIntensityAttr(float(intensity)); dl.CreateAngleAttr(2.0)
    rot = Gf.Rotation(Gf.Vec3d(0, 0, -1), Gf.Vec3d(float(d[0]), float(d[1]), float(d[2])))
    UsdGeom.Xformable(dl.GetPrim()).AddOrientOp().Set(Gf.Quatf(rot.GetQuat()))
    return dl


def cam_quat(eye, tgt):
    """bear_a5 的矩陣式 look-at (實測會渲染)。回傳 [qw,qx,qy,qz], 配 set_world_pose(camera_axes='world')。"""
    f = np.array(tgt, float) - np.array(eye, float); f /= np.linalg.norm(f)
    up = np.array([0, 0, 1.0]); z = up - (up @ f) * f; z /= np.linalg.norm(z); y = np.cross(z, f)
    R = np.stack([f, y, z], 1); qw = math.sqrt(max(0, 1 + R.trace())) / 2
    return np.array([qw, (R[2, 1] - R[1, 2]) / (4 * qw),
                     (R[0, 2] - R[2, 0]) / (4 * qw), (R[1, 0] - R[0, 1]) / (4 * qw)])


# ------------------------------------------------------------------ 熊網格 (純 numpy, 原點置中)
def _ellipsoid(cx, cy, cz, rx, ry, rz, nlat=14, nlon=18):
    pts = []
    for i in range(nlat + 1):
        th = math.pi * i / nlat
        for j in range(nlon):
            ph = 2 * math.pi * j / nlon
            pts.append((cx + rx * math.sin(th) * math.cos(ph),
                        cy + ry * math.sin(th) * math.sin(ph),
                        cz + rz * math.cos(th)))
    idx = []
    for i in range(nlat):
        for j in range(nlon):
            a = i * nlon + j; b = i * nlon + (j + 1) % nlon
            c = (i + 1) * nlon + j; d = (i + 1) * nlon + (j + 1) % nlon
            idx += [a, b, d, a, d, c]
    return np.array(pts, float), np.array(idx, int).reshape(-1, 3)


# 抓取幾何常數 (原始未置中座標): 抓大肚子。坐姿→底盤寬、重心低、不會倒。
BELLY_CZ = 0.055        # 肚子中心 z (抓取高度)
BELLY_RX = 0.058        # 肚子半寬 x (夾爪從 ±x 夾這裡)


def load_bear_npz(path, scale=1.0):
    """載入 bear_a5 驗證過會渲染的泰迪熊網格 (bear_mesh_xl.npz)。原點置中(cook no-op)。"""
    d = np.load(path)
    V = d["points"].astype(np.float64) * scale
    F = d["faces"].astype(np.int64)
    ctr = V.mean(0); V = V - ctr
    P("  bear npz mesh: %d verts / %d tris (%s)" % (len(V), len(F), path))
    return V, F, float(ctr[2])


def make_bear_mesh(scale=1.0, grid=84, thresh=0.32, big_ears=False, arms_out=False):
    """坐姿泰迪熊, metaball + marching cubes → 單一封閉曲面(無重疊內面 → 不會有黑塊, 平滑完整)。
    +y 正面(吻/朝相機)。原點置中(cook no-op)。回傳 (points, faces, ctr_z)。
    坐姿: 大肚子在下 + 腿往前伸 → 底盤寬、重心低、靜置不倒。抓取點=肚子 (BELLY_CZ, 半寬 BELLY_RX)。
    big_ears=True: 耳朵改豎起細長柱(手指能兜住 → 夾得到耳)。"""
    from skimage import measure
    if big_ears:   # 豎起細長耳(兩段疊高、細), 頭頂突出的柱
        ears = [(-0.033, 0.0, 0.185, 0.015, 0.013, 0.024), (-0.033, 0.0, 0.222, 0.013, 0.011, 0.024),
                (0.033, 0.0, 0.185, 0.015, 0.013, 0.024), (0.033, 0.0, 0.222, 0.013, 0.011, 0.024)]
        hi_z = 0.265
    else:
        ears = [(-0.030, 0.0, 0.170, 0.017, 0.013, 0.017), (0.030, 0.0, 0.170, 0.017, 0.013, 0.017)]
        hi_z = 0.205
    blobs = [   # (cx,cy,cz, rx,ry,rz)  各向異性橢球 metaball
        (0.000, 0.000, 0.055, 0.058, 0.052, 0.052),   # 肚子 belly (大、低、寬 → 穩)
        (0.000, 0.006, 0.132, 0.042, 0.042, 0.040),   # 頭 head
        (0.000, 0.042, 0.122, 0.021, 0.022, 0.018),   # 吻部 snout (+y 前)
    ]
    if arms_out:   # T-pose: 手臂在體側中高、清楚外伸的粗橫柱(z~體心, 細 → 不跟身體糊成盤)
        arms = [(-0.076, 0.0, 0.062, 0.024, 0.023, 0.023), (-0.106, 0.0, 0.062, 0.025, 0.020, 0.020),
                (-0.132, 0.0, 0.060, 0.023, 0.019, 0.019),
                (0.076, 0.0, 0.062, 0.024, 0.023, 0.023), (0.106, 0.0, 0.062, 0.025, 0.020, 0.020),
                (0.132, 0.0, 0.060, 0.023, 0.019, 0.019)]
        hi_x = 0.162
    else:
        arms = [(-0.060, 0.014, 0.070, 0.018, 0.020, 0.028), (0.060, 0.014, 0.070, 0.018, 0.020, 0.028)]
        hi_x = 0.105
    blobs = blobs + arms + [
        (-0.032, 0.054, 0.024, 0.026, 0.036, 0.024),  # 左腿 (往前伸 +y, 低 → 寬底盤)
        (0.032, 0.054, 0.024, 0.026, 0.036, 0.024),   # 右腿
    ]
    lo = np.array([-hi_x, -0.075, -0.008]); hi = np.array([hi_x, 0.115, hi_z])
    xs = np.linspace(lo[0], hi[0], grid); ys = np.linspace(lo[1], hi[1], grid); zs = np.linspace(lo[2], hi[2], grid)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    field = np.zeros_like(X)
    for (cx, cy, cz, rx, ry, rz) in blobs:
        d2 = ((X - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2 + ((Z - cz) / rz) ** 2
        field += np.exp(-d2)
    spacing = tuple((hi - lo) / (grid - 1))
    verts, faces, _n, _v = measure.marching_cubes(field, level=thresh, spacing=spacing)
    verts = verts + lo                          # index*spacing → 世界座標
    V = verts.astype(np.float64) * scale
    F = faces.astype(np.int64)                  # marching_cubes 'descent' → 法線本就朝外
    ctr = V.mean(0)
    V = V - ctr                                 # 原點置中(cook no-op), 之後 translate op 擺回
    P("  bear metaball mesh: %d verts / %d tris" % (len(V), len(F)))
    return V, F, float(ctr[2])


def _author_mesh(stage, path, V, F, color, double_sided=True, subdiv=None):
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr([Gf.Vec3f(*p) for p in V])
    m.CreateFaceVertexIndicesAttr([int(i) for i in F.reshape(-1)])
    m.CreateFaceVertexCountsAttr([3] * len(F))
    m.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    m.CreateDoubleSidedAttr(double_sided)
    if subdiv:
        # ★ deformable 變形後不會重算法線 → 未設會渲成黑。catmullClark 每幀從更新後的點重算法線
        #   (bear_ball 的球就靠這個)。
        m.CreateSubdivisionSchemeAttr(subdiv)
    return m


def _place(stage, path, x, y, z):
    UsdGeom.Xformable(stage.GetPrimAtPath(path)).AddTranslateOp().Set(Gf.Vec3d(x, y, z))


def add_soft_bear(stage, path, V, F, at=(0, 0, 0), color=(0.48, 0.30, 0.16),
                  young=1.6e5, poisson=0.40, density=110.0, friction=1.5, res=16,
                  contact_offset=0.003):
    """Volume FEM 軟體熊。at = 熊「底部貼地」的擺放中心 (x,y,z_floor)。
    ★ 位置烘進頂點(不加 translate op)—— 完全照 bear_a5。translate op 會讓 deformable render mesh 渲成黑。"""
    Vw = np.asarray(V, float).copy()
    Vw[:, 0] += at[0]; Vw[:, 1] += at[1]; Vw[:, 2] += at[2]
    m = _author_mesh(stage, path, Vw, F, color, double_sided=True)   # bear_a5 極簡設定, 頂點已在世界位置
    deformableUtils.add_physx_deformable_body(
        stage, m.GetPath(), collision_simplification=True,
        simulation_hexahedral_resolution=res)
    matp = omni.usd.get_stage_next_free_path(stage, path + "Mat", True)
    deformableUtils.add_deformable_material(
        stage, matp, density=density, dynamic_friction=friction,
        youngs_modulus=young, poissons_ratio=poisson)
    physicsUtils.add_physics_material_to_prim(stage, m.GetPrim(), matp)
    P("  soft bear @ %s  young=%.0e res=%d fric=%.1f (baked, no translate op)" % (str(at), young, res, friction))
    return m


def add_rigid_bear(stage, path, V, F, at=(0, 0, 0), color=(0.48, 0.30, 0.16),
                   mass=0.18, friction=1.2):
    """同一顆熊網格但當剛體 (袋子內裝重物 / task B 用)。凸包碰撞。"""
    m = _author_mesh(stage, path, V, F, color, double_sided=False)
    _place(stage, path, at[0], at[1], at[2])
    pr = m.GetPrim()
    UsdPhysics.CollisionAPI.Apply(pr)
    mca = UsdPhysics.MeshCollisionAPI.Apply(pr); mca.CreateApproximationAttr("convexHull")
    UsdPhysics.RigidBodyAPI.Apply(pr)
    UsdPhysics.MassAPI.Apply(pr).CreateMassAttr(mass)
    _bind_rigid_friction(stage, pr, friction)
    P("  rigid bear @ %s mass=%.2f" % (str(at), mass))
    return m


# ------------------------------------------------------------------ 塑膠袋 (surface deformable, toy_surf/bag_lift 配方)
def make_bag(stage, path, cx=0.0, cy=0.0, z_floor=0.004, R=0.085, H=0.30,
             na=28, nz=26, stretch=4000.0, shear=60.0, bend=1.5, thick=0.00008,
             density=920.0, friction=1.5, iters=24, color=(0.86, 0.91, 0.94),
             opacity=0.38, contact_offset=0.003):
    """開口圓筒 + 封底的薄膜袋。回傳 root prim path (讀點用 path+'/simMesh')。"""
    UsdGeom.Xform.Define(stage, path)               # ★ 根必須是 Xform
    pts = []; idx = []
    for j in range(nz + 1):
        z = z_floor + H * j / nz
        for i in range(na):
            ph = 2 * math.pi * i / na
            pts.append(Gf.Vec3f(cx + R * math.cos(ph), cy + R * math.sin(ph), z))
    base_i = len(pts)
    pts.append(Gf.Vec3f(cx, cy, z_floor))           # 封底中心
    for j in range(nz):                             # 側壁
        for i in range(na):
            a = j * na + i; b = j * na + (i + 1) % na
            c = (j + 1) * na + i; d = (j + 1) * na + (i + 1) % na
            idx += [a, b, d, a, d, c]
    for i in range(na):                             # 底面扇形
        a = i; b = (i + 1) % na
        idx += [base_i, b, a]
    mesh = UsdGeom.Mesh.Define(stage, path + "/mesh")
    mesh.CreatePointsAttr(pts)
    mesh.CreateFaceVertexIndicesAttr(idx)
    mesh.CreateFaceVertexCountsAttr([3] * (len(idx) // 3))
    ok = deformableUtils.create_auto_surface_deformable_hierarchy(
        stage, root_prim_path=path, simulation_mesh_path=path + "/simMesh",
        cooking_src_mesh_path=path + "/mesh",
        cooking_src_simplification_enabled=False, set_visibility_with_guide_purpose=False)
    P("  bag hierarchy -> %s" % ok)
    rp = stage.GetPrimAtPath(path); rp.ApplyAPI("PhysxSurfaceDeformableBodyAPI")
    rp.GetAttribute("physxDeformableBody:selfCollision").Set(True)
    rp.GetAttribute("physxDeformableBody:solverPositionIterationCount").Set(iters)
    sm = stage.GetPrimAtPath(path + "/simMesh")
    sm.ApplyAPI(PhysxSchema.PhysxCollisionAPI)
    PhysxSchema.PhysxCollisionAPI(sm).GetRestOffsetAttr().Set(0.0)
    PhysxSchema.PhysxCollisionAPI(sm).GetContactOffsetAttr().Set(contact_offset)
    matp = omni.usd.get_stage_next_free_path(stage, path + "Mat", True)
    deformableUtils.add_surface_deformable_material(
        stage, matp, density=density, dynamic_friction=friction,
        surface_thickness=thick, surface_stretch_stiffness=stretch,
        surface_shear_stiffness=shear, surface_bend_stiffness=bend)
    physicsUtils.add_physics_material_to_prim(stage, rp, matp)
    mp = stage.GetPrimAtPath(matp); mp.ApplyAPI("PhysxSurfaceDeformableMaterialAPI")
    mp.GetAttribute("physxDeformableMaterial:elasticityDamping").Set(0.05)
    mp.GetAttribute("physxDeformableMaterial:bendDamping").Set(0.02)
    # 半透膜外觀
    mat = UsdShade.Material.Define(stage, path + "vis")
    sh = UsdShade.Shader.Define(stage, path + "vis/pbr"); sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.42)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    sh.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.45)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI(mesh.GetPrim()).Bind(mat)
    UsdShade.MaterialBindingAPI(sm).Bind(mat)
    return path + "/simMesh"


def make_ball_bag(stage, path, cx=0.0, cy=0.0, cz=0.15, R=0.16,
                  na=28, nz=20, stretch=4000.0, shear=60.0, bend=1.5, thick=0.00008,
                  density=920.0, friction=1.5, iters=24, color=(0.86, 0.91, 0.94),
                  opacity=0.38, contact_offset=0.003):
    """封閉的『球形塑膠袋』(UV sphere, 兩極封口) —— 完整包覆整隻熊。回傳 simMesh path。
    幾何用球面, 其餘 surface-deformable pipeline 與 make_bag 完全相同。"""
    UsdGeom.Xform.Define(stage, path)
    pts = []; idx = []
    # 兩極 + 中間 (nz-1) 圈緯線
    top_i = 0; pts.append(Gf.Vec3f(cx, cy, cz + R))                 # 北極
    for j in range(1, nz):                                          # 緯線 (不含兩極)
        th = math.pi * j / nz
        z = cz + R * math.cos(th); r = R * math.sin(th)
        for i in range(na):
            ph = 2 * math.pi * i / na
            pts.append(Gf.Vec3f(cx + r * math.cos(ph), cy + r * math.sin(ph), z))
    bot_i = len(pts); pts.append(Gf.Vec3f(cx, cy, cz - R))          # 南極
    def ring(j):  # 第 j 圈 (1..nz-1) 的頂點起始索引
        return 1 + (j - 1) * na
    for i in range(na):                                            # 北極扇形
        a = ring(1) + i; b = ring(1) + (i + 1) % na
        idx += [top_i, a, b]
    for j in range(1, nz - 1):                                     # 側環
        for i in range(na):
            a = ring(j) + i; b = ring(j) + (i + 1) % na
            c = ring(j + 1) + i; d = ring(j + 1) + (i + 1) % na
            idx += [a, b, d, a, d, c]
    for i in range(na):                                            # 南極扇形
        a = ring(nz - 1) + i; b = ring(nz - 1) + (i + 1) % na
        idx += [bot_i, b, a]
    mesh = UsdGeom.Mesh.Define(stage, path + "/mesh")
    mesh.CreatePointsAttr(pts)
    mesh.CreateFaceVertexIndicesAttr(idx)
    mesh.CreateFaceVertexCountsAttr([3] * (len(idx) // 3))
    ok = deformableUtils.create_auto_surface_deformable_hierarchy(
        stage, root_prim_path=path, simulation_mesh_path=path + "/simMesh",
        cooking_src_mesh_path=path + "/mesh",
        cooking_src_simplification_enabled=False, set_visibility_with_guide_purpose=False)
    P("  ball bag hierarchy -> %s" % ok)
    rp = stage.GetPrimAtPath(path); rp.ApplyAPI("PhysxSurfaceDeformableBodyAPI")
    rp.GetAttribute("physxDeformableBody:selfCollision").Set(True)
    rp.GetAttribute("physxDeformableBody:solverPositionIterationCount").Set(iters)
    sm = stage.GetPrimAtPath(path + "/simMesh")
    sm.ApplyAPI(PhysxSchema.PhysxCollisionAPI)
    PhysxSchema.PhysxCollisionAPI(sm).GetRestOffsetAttr().Set(0.0)
    PhysxSchema.PhysxCollisionAPI(sm).GetContactOffsetAttr().Set(contact_offset)
    matp = omni.usd.get_stage_next_free_path(stage, path + "Mat", True)
    deformableUtils.add_surface_deformable_material(
        stage, matp, density=density, dynamic_friction=friction,
        surface_thickness=thick, surface_stretch_stiffness=stretch,
        surface_shear_stiffness=shear, surface_bend_stiffness=bend)
    physicsUtils.add_physics_material_to_prim(stage, rp, matp)
    mp = stage.GetPrimAtPath(matp); mp.ApplyAPI("PhysxSurfaceDeformableMaterialAPI")
    mp.GetAttribute("physxDeformableMaterial:elasticityDamping").Set(0.05)
    mp.GetAttribute("physxDeformableMaterial:bendDamping").Set(0.02)
    mat = UsdShade.Material.Define(stage, path + "vis")
    sh = UsdShade.Shader.Define(stage, path + "vis/pbr"); sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.42)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI(mesh.GetPrim()).Bind(mat)
    UsdShade.MaterialBindingAPI(sm).Bind(mat)
    return path + "/simMesh"


# ------------------------------------------------------------------ 剛體摩擦材質
def _bind_rigid_friction(stage, prim, friction):
    mpath = "/World/_rigidFric_%d" % int(round(friction * 100))   # ★ prim 名不能有小數點
    if not stage.GetPrimAtPath(mpath).IsValid():
        mp = stage.DefinePrim(mpath, "Material")
        pm = UsdPhysics.MaterialAPI.Apply(mp)
        pm.CreateStaticFrictionAttr(friction)
        pm.CreateDynamicFrictionAttr(friction)
        pm.CreateRestitutionAttr(0.0)
    physicsUtils.add_physics_material_to_prim(stage, prim, mpath)


# ------------------------------------------------------------------ 夾爪 (兩片 kinematic 墊)
class Gripper:
    def __init__(self, stage, y_span=0.07, z_span=0.05, thick=0.012,
                 friction=2.0, color=(0.13, 0.14, 0.17)):
        self.thick = thick
        self.ops = {}
        for nm, sx in (("L", -1), ("R", +1)):
            p = "/World/grip_" + nm
            cube = UsdGeom.Cube.Define(stage, p); cube.CreateSizeAttr(1.0)
            xf = UsdGeom.Xformable(cube.GetPrim())
            t = xf.AddTranslateOp()
            xf.AddScaleOp().Set(Gf.Vec3f(thick, y_span, z_span))   # 全尺寸 = scale
            cube.CreateDisplayColorAttr([Gf.Vec3f(*color)])
            cube.GetPrim().CreateAttribute("primvars:doNotCastShadows",
                                           Sdf.ValueTypeNames.Bool).Set(True)  # 別遮到被夾物
            pr = cube.GetPrim()
            UsdPhysics.CollisionAPI.Apply(pr)
            rb = UsdPhysics.RigidBodyAPI.Apply(pr); rb.CreateKinematicEnabledAttr(True)
            _bind_rigid_friction(stage, pr, friction)
            self.ops[nm] = t
        self.set(0.20, 0.5)   # 先停遠處
        P("  gripper: pad %gx%gx%g thick, fric=%.1f" % (thick, y_span, z_span, friction))

    def set(self, half_gap, z, x_center=0.0, y=0.0):
        """half_gap = 中心到墊心距離; 墊內面 = x_center ± (half_gap - thick/2)。"""
        self.ops["L"].Set(Gf.Vec3d(x_center - half_gap, y, z))
        self.ops["R"].Set(Gf.Vec3d(x_center + half_gap, y, z))


# ------------------------------------------------------------------ 抓握黏合 (夾爪↔deformable)
def attach_grasp_manual(stage, deform_path, deform_tz, rigid_path, name, mask_fn, points_path=None):
    """★ 手動 attachment (照 dflap_box 驗證配方): 直接把 mask_fn 選中的 deformable 頂點釘到夾爪剛體。
    auto-attachment 對圓軟體會靜默留空(points0=0), 手動指定才可靠。不套 AutoAttachmentAPI(會被覆寫)。
    points0 = 頂點在 deformable 區域座標; points1 = 同頂點換到剛體區域座標。
    deform_tz = deformable 的 translate op z (區域→世界只差這個)。
    points_path = 讀點的 mesh (surface deformable 的點在 simMesh); 預設 = deform_path。回傳釘住的頂點數。"""
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath(points_path or deform_path))
    Pl = np.array([[q[0], q[1], q[2]] for q in mesh.GetPointsAttr().Get()])   # 區域座標
    sel = np.where(mask_fn(Pl))[0]
    if len(sel) == 0:
        P("  grasp %s: ★ 0 頂點被選到 (mask 沒中)" % name)
        return 0
    w2l = Gf.Matrix4d(UsdGeom.Xformable(stage.GetPrimAtPath(rigid_path))
                      .ComputeLocalToWorldTransform(Usd.TimeCode.Default())).GetInverse()
    P0 = Vt.Vec3fArray([Gf.Vec3f(*Pl[i]) for i in sel])
    P1 = Vt.Vec3fArray([Gf.Vec3f(*w2l.Transform(Gf.Vec3d(Pl[i][0], Pl[i][1], Pl[i][2] + deform_tz)))
                        for i in sel])
    att = PhysxSchema.PhysxPhysicsAttachment.Define(stage, deform_path + "/grasp_" + name)
    att.GetActor0Rel().SetTargets([Sdf.Path(deform_path)])
    att.GetActor1Rel().SetTargets([Sdf.Path(rigid_path)])
    att.CreatePoints0Attr().Set(P0)
    att.CreatePoints1Attr().Set(P1)
    att.CreateAttachmentEnabledAttr().Set(True)                 # ★ 不套 AutoAttachmentAPI
    P("  grasp %s: pinned %d verts" % (name, len(sel)))
    return len(sel)


# ------------------------------------------------------------------ 剛體抓握: 夾攏後鎖固定關節
def fix_grasp(stage, path, pad_path, body_path):
    """在夾爪墊(kinematic)與剛體物件之間建 FixedJoint, 鎖住當下相對位姿 → 物件隨夾爪移動。
    合法的「夾緊抓握」模型(剛體版, 對應軟體的 manual attachment)。"""
    Ta = Gf.Matrix4d(UsdGeom.Xformable(stage.GetPrimAtPath(pad_path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
    Tb = Gf.Matrix4d(UsdGeom.Xformable(stage.GetPrimAtPath(body_path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
    Trel = Tb * Ta.GetInverse()                     # bear-local → pad-local
    q = Trel.ExtractRotation().GetQuat()
    j = UsdPhysics.FixedJoint.Define(stage, path)
    j.CreateBody0Rel().SetTargets([Sdf.Path(pad_path)])
    j.CreateBody1Rel().SetTargets([Sdf.Path(body_path)])
    j.CreateLocalPos0Attr().Set(Gf.Vec3f(*Trel.ExtractTranslation()))
    j.CreateLocalRot0Attr().Set(Gf.Quatf(q.GetReal(), *q.GetImaginary()))
    j.CreateLocalPos1Attr().Set(Gf.Vec3f(0, 0, 0))
    j.CreateLocalRot1Attr().Set(Gf.Quatf(1, 0, 0, 0))
    P("  fix_grasp %s <-> %s" % (pad_path, body_path))
    return j


# ------------------------------------------------------------------ 小工具
def smoothstep(a, b, t):
    t = max(0.0, min(1.0, t)); t = t * t * (3 - 2 * t)
    return a + (b - a) * t
