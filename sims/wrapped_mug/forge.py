# -*- coding: utf-8 -*-
"""wrapped_mug —— 生成「紙箱 + 橫放馬克杯 + 包覆泡泡紙」的可互動 3D 資產。

做法(P0/P0-b 實測結論):
  * 顯式 restAdjTriPairs + restBendAngles 在 PhysX 107.3.26 被忽略 -> 不用
  * restShapePoints + restBendAnglesDefault="restShapeDefault" 有效 -> 走這條
  * 所以:先用曲率剖面解析地「折」出包覆形狀(等距,不拉伸),讓它成為
    膜的靜止形狀,再靜置貼合,最後把靜置結果烘回 restShapePoints。
    折痕變成零能量狀態,不需要任何黏合就不會彈開。

用法:
  /isaac-sim/python.sh forge_wrapped_mug.py            # 生成 + 烘焙 + 存檔
  /isaac-sim/python.sh forge_wrapped_mug.py --no-bake  # 只生成不烘(除錯用)
"""
import argparse, json, math, os, struct, sys, zlib

from isaacsim import SimulationApp

_ap = argparse.ArgumentParser()
_ap.add_argument("--no-bake", action="store_true")
_ap.add_argument("--settle-steps", type=int, default=None)
_ap.add_argument("--out", default=None)
_ap.add_argument("--rig", default=None,
                 help="把包裹裝進既有場景的紙箱裡(給 stationary_ai_carton_scene_flat.usd)")
ARGS = _ap.parse_args()

simulation_app = SimulationApp({"headless": True})

import carb
from pxr import Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade, PhysxSchema, Gf, Sdf, Vt
import omni.usd
from isaacsim.core.api import SimulationContext

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wf_common as wf
from params import CARTON, MUG, BUBBLE, WRAP, SIM, VIEW

OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
USD_OUT = ARGS.out or os.path.join(OUT, "wrapped_mug_in_carton.usd")
PNG_OUT = os.path.join(OUT, "bubble_normal.png")

_LOG = []


def log(msg):
    line = f"[forge] {msg}"
    _LOG.append(line)
    print(line, flush=True)
    carb.log_warn(line)


# =============================================================== 貼圖
def write_png(path, rgb):
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9))
                + chunk(b"IEND", b""))


def make_bubble_normal(path, size=192):
    """一格 = 一顆泡泡的無縫法線貼圖。球冠 + 邊緣平坦,四邊可 tile。"""
    import numpy as np
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    u = (xx + 0.5) / size - 0.5
    v = (yy + 0.5) / size - 0.5
    d = np.sqrt(u * u + v * v)
    # 泡泡佔格子的 84%,外圈留平坦的熱封邊 -> 邊界法線 = (0,0,1),可無縫拼接
    R = 0.42
    inside = d < R
    # 球冠高度場 h(d) = sqrt(R^2 - d^2) * k;斜率 dh/dd = -k*d/sqrt(R^2-d^2)
    safe = np.clip(R * R - d * d, 1e-6, None)
    k = BUBBLE["bubble_height"] / (BUBBLE["bubble_pitch"] * R)      # 真實泡高/泡距比
    slope = np.where(inside, -k * d / np.sqrt(safe), 0.0)
    nx = np.where(inside & (d > 1e-6), -slope * u / np.maximum(d, 1e-6), 0.0)
    ny = np.where(inside & (d > 1e-6), -slope * v / np.maximum(d, 1e-6), 0.0)
    nz = np.ones_like(nx)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    rgb = np.empty((size, size, 3), np.uint8)
    rgb[..., 0] = np.clip((nx / ln) * 0.5 + 0.5, 0, 1) * 255
    rgb[..., 1] = np.clip((ny / ln) * 0.5 + 0.5, 0, 1) * 255
    rgb[..., 2] = np.clip((nz / ln) * 0.5 + 0.5, 0, 1) * 255
    write_png(path, rgb)
    return path


def omni_pbr(stage, path, color, roughness=0.5, metallic=0.0, opacity=None,
             normal_map=None, normal_strength=1.0, specular=None):
    mat = UsdShade.Material.Define(stage, path)
    s = UsdShade.Shader.Define(stage, path + "/Shader")
    s.CreateIdAttr("OmniPBR")
    s.SetSourceAsset("OmniPBR.mdl", "mdl")
    s.SetSourceAssetSubIdentifier("OmniPBR", "mdl")
    s.CreateInput("diffuse_color_constant", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    s.CreateInput("reflection_roughness_constant", Sdf.ValueTypeNames.Float).Set(float(roughness))
    s.CreateInput("metallic_constant", Sdf.ValueTypeNames.Float).Set(float(metallic))
    if opacity is not None:
        s.CreateInput("enable_opacity", Sdf.ValueTypeNames.Bool).Set(True)
        s.CreateInput("opacity_constant", Sdf.ValueTypeNames.Float).Set(float(opacity))
        s.CreateInput("opacity_mode", Sdf.ValueTypeNames.Int).Set(1)
        # threshold 不設會落到 cutout(二值)模式,看起來就是全不透明
        s.CreateInput("opacity_threshold", Sdf.ValueTypeNames.Float).Set(0.0)
        s.CreateInput("enable_opacity_texture", Sdf.ValueTypeNames.Bool).Set(False)
    if specular is not None:
        s.CreateInput("specular_level", Sdf.ValueTypeNames.Float).Set(float(specular))
    if normal_map:
        s.CreateInput("normalmap_texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(normal_map))
        s.CreateInput("bump_factor", Sdf.ValueTypeNames.Float).Set(float(normal_strength))
        s.CreateInput("flip_tangent_v", Sdf.ValueTypeNames.Bool).Set(True)
        s.CreateInput("project_uvw", Sdf.ValueTypeNames.Bool).Set(False)
    mat.CreateSurfaceOutput("mdl").ConnectToSource(s.ConnectableAPI(), "out")
    return mat


# =============================================================== 幾何工具
def revolve(profile, nseg=64):
    """(r,z) 剖面繞 Z 軸旋轉成封閉網格。profile 由下往上,首尾 r 可為 0。"""
    pts, faces = [], []
    ring_start = []
    for r, z in profile:
        if r < 1e-9:
            ring_start.append(("pole", len(pts)))
            pts.append(Gf.Vec3f(0.0, 0.0, z))
        else:
            ring_start.append(("ring", len(pts)))
            for i in range(nseg):
                a = 2 * math.pi * i / nseg
                pts.append(Gf.Vec3f(r * math.cos(a), r * math.sin(a), z))
    for k in range(len(profile) - 1):
        k0, i0 = ring_start[k]
        k1, i1 = ring_start[k + 1]
        if k0 == "ring" and k1 == "ring":
            for i in range(nseg):
                j = (i + 1) % nseg
                faces.append((i0 + i, i0 + j, i1 + j, i1 + i))
        elif k0 == "pole" and k1 == "ring":
            for i in range(nseg):
                j = (i + 1) % nseg
                faces.append((i0, i1 + j, i1 + i))
        elif k0 == "ring" and k1 == "pole":
            for i in range(nseg):
                j = (i + 1) % nseg
                faces.append((i0 + i, i0 + j, i1))
    return pts, faces


def torus_xz(center, major_r, minor_r, nu=40, nv=16):
    """環面,環心平面 = 局部 XZ 平面(管軸法向沿 Y)。"""
    pts, faces = [], []
    cx, cy, cz = center
    for i in range(nu):
        a = 2 * math.pi * i / nu
        for j in range(nv):
            b = 2 * math.pi * j / nv
            rr = major_r + minor_r * math.cos(b)
            pts.append(Gf.Vec3f(cx + rr * math.cos(a), cy + minor_r * math.sin(b), cz + rr * math.sin(a)))
    for i in range(nu):
        for j in range(nv):
            a0 = i * nv + j
            b0 = ((i + 1) % nu) * nv + j
            b1 = ((i + 1) % nu) * nv + (j + 1) % nv
            a1 = i * nv + (j + 1) % nv
            faces.append((a0, b0, b1, a1))
    return pts, faces


def poly_mesh(stage, path, pts, faces, color=None, double_sided=False):
    m = UsdGeom.Mesh.Define(stage, path)
    m.GetPointsAttr().Set(Vt.Vec3fArray(pts))
    m.GetFaceVertexCountsAttr().Set([len(f) for f in faces])
    m.GetFaceVertexIndicesAttr().Set([i for f in faces for i in f])
    m.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
    if double_sided:
        m.CreateDoubleSidedAttr(True)
    if color:
        m.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    return m


def _integrate(segs, step=2.5e-4):
    """回傳 (弧長, y, z) 端點。"""
    s = y = z = 0.0
    for length, p0, p1 in segs:
        n = max(int(math.ceil(length / step)), 1)
        for i in range(n):
            f = (i + 0.5) / n
            phi = math.radians(p0 + (p1 - p0) * f)
            d = length / n
            y += math.cos(phi) * d
            z += math.sin(phi) * d
            s += d
    return s, y, z


def cross_section(w):
    """用曲率剖面積分出半邊包覆截面,回傳 (arc_lengths, ys, zs, half_len)。

    沿弧長給定切線角 phi(s) 再積分 -> 保證等距映射,把平面膜折成這個形狀不會產生面內應變。
      平底 -> 箱底圓角(轉 90 度)-> 沿箱壁上升 -> 往內折(轉 fold_deg)-> 直線段
    """
    segs = [
        (w["bottom_span"] / 2.0, 0.0, 0.0),
        (w["corner_r"] * math.radians(90.0), 0.0, 90.0),
        (max(w["wall_rise"] - w["corner_r"], 1e-4), 90.0, 90.0),
        (w["fold_r"] * math.radians(w["fold_deg"]), 90.0, 90.0 + w["fold_deg"]),
    ]
    tip = w["tip_len"]
    if tip is None:
        # 自動求解直線段長度,讓左右尖端在杯子上方只留 target_gap
        y_a, z_a = _integrate(segs)[1:3]
        phi = math.radians(90.0 + w["fold_deg"])
        need = (w["target_gap"] / 2.0 - y_a) / math.cos(phi) if abs(math.cos(phi)) > 1e-6 else 0.0
        tip = max(need, 0.0)
    segs.append((tip, 90.0 + w["fold_deg"], 90.0 + w["fold_deg"]))
    step = 2.5e-4
    s_list, ys, zs = [0.0], [0.0], [0.0]
    s, y, z = 0.0, 0.0, 0.0
    for length, p0, p1 in segs:
        n = max(int(math.ceil(length / step)), 1)
        for i in range(n):
            f = (i + 0.5) / n
            phi = math.radians(p0 + (p1 - p0) * f)
            d = length / n
            y += math.cos(phi) * d
            z += math.sin(phi) * d
            s += d
            s_list.append(s)
            ys.append(y)
            zs.append(z)
    return s_list, ys, zs, s


def sample_section(s_list, ys, zs, s):
    """線性內插剖面。s 可為負(鏡射)。"""
    sgn = -1.0 if s < 0 else 1.0
    s = abs(s)
    if s >= s_list[-1]:
        return sgn * ys[-1], zs[-1]
    lo, hi = 0, len(s_list) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if s_list[mid] <= s:
            lo = mid
        else:
            hi = mid
    t = (s - s_list[lo]) / max(s_list[hi] - s_list[lo], 1e-12)
    return sgn * (ys[lo] + (ys[hi] - ys[lo]) * t), zs[lo] + (zs[hi] - zs[lo]) * t


# =============================================================== 建場景
log(f"runtime: {wf.enable_deformable_runtime()}")
RIG = ARGS.rig
if RIG:
    if not os.path.isabs(RIG):
        for _c in (os.path.join(os.getcwd(), RIG), os.path.join(HERE, RIG),
                   os.path.join(os.path.dirname(HERE), RIG)):
            if os.path.isfile(_c):
                RIG = _c
                break
    if not os.path.isfile(RIG):
        raise SystemExit(f"找不到 rig 場景: {ARGS.rig}")
    omni.usd.get_context().open_stage(RIG)
    log(f"rig mode: {RIG}")
else:
    omni.usd.get_context().new_stage()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
world = UsdGeom.Xform.Define(stage, "/World")
if not RIG:
    stage.SetDefaultPrim(world.GetPrim())
UsdGeom.Scope.Define(stage, "/World/attach")

px_scene = wf.make_physics_scene(stage, steps_per_second=SIM["bake_hz"])

# ---- 燈光 ----------------------------------------------------------------
if not RIG:
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(260.0)
    dome.CreateColorAttr(Gf.Vec3f(0.92, 0.95, 1.0))
    key = UsdLux.DistantLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(900.0)
    key.CreateAngleAttr(1.2)
    UsdGeom.Xformable(key).AddRotateXYZOp().Set(Gf.Vec3f(-42.0, 0.0, 28.0))

# ---- 地面 ----------------------------------------------------------------
if not RIG:
    ground = UsdGeom.Xform.Define(stage, "/World/Ground")
    gplane = UsdGeom.Plane.Define(stage, "/World/Ground/CollisionPlane")
    gplane.CreateAxisAttr("Z")
    gplane.CreatePurposeAttr(UsdGeom.Tokens.guide)
    UsdPhysics.CollisionAPI.Apply(gplane.GetPrim())
    gvis = UsdGeom.Cube.Define(stage, "/World/Ground/Visual")
    gvis.CreateSizeAttr(1.0)
    gx = UsdGeom.Xformable(gvis)
    gx.AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.004))
    gx.AddScaleOp().Set(Gf.Vec3f(1.6, 1.6, 0.008))

# ---- 材質 ----------------------------------------------------------------
make_bubble_normal(PNG_OUT)
log(f"bubble normal map -> {PNG_OUT}")

mat_kraft = omni_pbr(stage, "/World/Looks/Kraft", (0.62, 0.46, 0.30), roughness=0.82)
mat_kraft_in = omni_pbr(stage, "/World/Looks/KraftInner", (0.72, 0.57, 0.40), roughness=0.85)
mat_ceramic = omni_pbr(stage, "/World/Looks/Ceramic", (0.34, 0.42, 0.50), roughness=0.22)
mat_film = omni_pbr(stage, "/World/Looks/BubbleFilm", (0.72, 0.85, 0.91),
                    roughness=0.10,
                    opacity=BUBBLE["opacity"] if BUBBLE["transparent"] else None,
                    normal_map=PNG_OUT, normal_strength=BUBBLE["bump_factor"],
                    specular=1.0)

phys_film = wf.make_film_material(
    stage, "/World/Looks/FilmPhysics", BUBBLE["youngs"], BUBBLE["poisson"],
    BUBBLE["thickness"], BUBBLE["surface_bend_stiffness"], BUBBLE["dyn_friction"],
    BUBBLE["elasticity_damping"], BUBBLE["bend_damping"])


def rigid_physics_material(path, friction, restitution=0.05):
    m = UsdShade.Material.Define(stage, path)
    api = UsdPhysics.MaterialAPI.Apply(m.GetPrim())
    api.CreateDynamicFrictionAttr(friction)
    api.CreateStaticFrictionAttr(friction)
    api.CreateRestitutionAttr(restitution)
    return m


phys_kraft = rigid_physics_material("/World/Looks/KraftPhysics", CARTON["friction"])
phys_mug = rigid_physics_material("/World/Looks/MugPhysics", MUG["friction"])

# =============================================================== 馬克杯
# 先建杯子並量出實際尺寸,紙箱與包材都由它推導 —— 換杯子不用手改任何數字。
R, MH, WT, BT = MUG["outer_r"], MUG["height"], MUG["wall_t"], MUG["base_t"]

_lay = Gf.Matrix4d(); _lay.SetRotate(Gf.Rotation(Gf.Vec3d(0, 1, 0), -90.0))


def _roll_mat(deg):
    m = Gf.Matrix4d(); m.SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), deg)); return m


def auto_roll(mn, mx):
    """放倒(roll=0)後量出的 YZ 外框 -> 要轉幾度才能讓把手水平指向 +Y。

    杯身是圓柱,YZ 截面本該是半徑 r 的圓;把手會讓某一側外凸。
    取兩軸半寬的較小者當 r,較大者所在的方向就是把手。
    """
    hy = max(abs(mn[1]), abs(mx[1]))
    hz = max(abs(mn[2]), abs(mx[2]))
    r = min(hy, hz)
    if hz > hy * 1.08:                       # 把手在 Z 方向
        return -90.0 if (mx[2] - r) >= (-mn[2] - r) else 90.0
    if hy > hz * 1.08:                       # 把手已在 Y 方向
        return 0.0 if (mx[1] - r) >= (-mn[1] - r) else 180.0
    return 0.0                               # 量不出來(沒把手?)就不轉


_SCL = Gf.Matrix4d().SetScale(Gf.Vec3d(*( [float(MUG.get("scale", 1.0))] * 3 )))
_M = _SCL * _lay * _roll_mat(MUG["handle_roll_deg"] if MUG["handle_roll_deg"] != "auto" else 0.0)

mug = UsdGeom.Xform.Define(stage, "/World/mug")
mx = UsdGeom.Xformable(mug)
mug_tr = mx.AddTranslateOp()
mug_or = mx.AddOrientOp()
mug_or.Set(Gf.Quatf(1.0, 0.0, 0.0, 0.0))

src = MUG.get("source")
if src:
    src_path = src if os.path.isabs(src) else os.path.join(HERE, src)
    if not os.path.isfile(src_path):
        raise SystemExit(f"找不到杯子資產: {src_path}")
    # 官方資產的 defaultPrim 自帶 translate/rotateXYZ/scale,所以要多包一層乾淨的 Xform
    holder = UsdGeom.Xform.Define(stage, "/World/mug/asset")
    holder_xf = UsdGeom.Xformable(holder).MakeMatrixXform()
    holder_xf.Set(_M)
    ref = UsdGeom.Xform.Define(stage, "/World/mug/asset/ref")
    ref.GetPrim().GetReferences().AddReference(src_path)
    meshes = [pr for pr in Usd.PrimRange(ref.GetPrim()) if pr.IsA(UsdGeom.Mesh)]
    # 這顆資產的 /RootNode 帶 scale=(0.01,0.01,0.01),原始頂點是 9 單位級。
    # 網格碰撞體(convexHull / convexDecomposition / SDF)在這種縮放鏈下 cook 不出
    # 正確結果 —— 實測三種都讓杯子沉到地板下 38.8 mm,而對照方塊停在 0.00。
    # 改用解析形狀:杯身圓柱 + 把手球鏈。primitive 碰撞在 PhysX 最穩,也保留把手的孔。
    # 置中:杯軸放到原點,最低點壓到 z=0(之後再整體抬到箱底)
    c0 = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
    r0 = c0.ComputeWorldBound(mug.GetPrim()).ComputeAlignedRange()
    roll = MUG["handle_roll_deg"]
    if roll == "auto":
        roll = auto_roll(r0.GetMin(), r0.GetMax())
        log(f"auto_roll: yz half-extents "
            f"y={max(abs(r0.GetMin()[1]),abs(r0.GetMax()[1]))*1000:.1f} "
            f"z={max(abs(r0.GetMin()[2]),abs(r0.GetMax()[2]))*1000:.1f} mm -> roll {roll:+.0f} deg")
        _M = _SCL * _lay * _roll_mat(roll)
        holder_xf.Set(_M)
        c0 = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
        r0 = c0.ComputeWorldBound(mug.GetPrim()).ComputeAlignedRange()
    MUG["handle_roll_deg"] = roll
    mn0, mx0 = r0.GetMin(), r0.GetMax()
    shift = Gf.Vec3d(-(mn0[0] + mx0[0]) / 2.0, 0.0, -(mn0[2] + mx0[2]) / 2.0)
    holder_xf.Set(_M * Gf.Matrix4d().SetTranslate(shift))

    # ---- 解析形狀碰撞體(由實際頂點量出來)-------------------------------
    body_w = UsdGeom.Xformable(mug.GetPrim()).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    w2b = body_w.GetInverse()
    P = []
    for m_ in meshes:
        lw = UsdGeom.Xformable(m_).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        T = lw * w2b
        P += [T.Transform(Gf.Vec3d(*q)) for q in (UsdGeom.Mesh(m_).GetPointsAttr().Get() or [])]
    ax_half = max(abs(q[0]) for q in P)
    rad = max(abs(q[2]) for q in P)                       # 杯身半徑(放倒後即 z 半高)
    cyl = UsdGeom.Cylinder.Define(stage, "/World/mug/col_body")
    cyl.CreateAxisAttr("X")
    cyl.CreateRadiusAttr(rad * 0.985)
    cyl.CreateHeightAttr(2.0 * ax_half * 0.99)
    UsdGeom.Imageable(cyl.GetPrim()).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    UsdPhysics.CollisionAPI.Apply(cyl.GetPrim())
    _c1 = PhysxSchema.PhysxCollisionAPI.Apply(cyl.GetPrim())
    _c1.CreateRestOffsetAttr().Set(0.0012); _c1.CreateContactOffsetAttr().Set(0.008)
    UsdShade.MaterialBindingAPI.Apply(cyl.GetPrim()).Bind(phys_mug, UsdShade.Tokens.weakerThanDescendants, "physics")

    # 把手 = 落在杯身圓柱外的頂點。依角度分箱,每箱放一顆球 -> 可夾的環
    HP = [q for q in P if (q[1] * q[1] + q[2] * q[2]) ** 0.5 > rad * 1.015]
    n_ball = 0
    if HP:
        yc = (min(q[1] for q in HP) + max(q[1] for q in HP)) / 2.0
        zc = (min(q[2] for q in HP) + max(q[2] for q in HP)) / 2.0
        tube = max(max(abs(q[0]) for q in HP), 0.004)
        NB = 14
        bins = {}
        for q in HP:
            ang = math.atan2(q[2] - zc, q[1] - yc)
            bins.setdefault(int((ang + math.pi) / (2 * math.pi) * NB) % NB, []).append(q)
        for bi, qs in sorted(bins.items()):
            cyv = sum(q[1] for q in qs) / len(qs)
            czv = sum(q[2] for q in qs) / len(qs)
            rr = sum(((q[1] - cyv) ** 2 + (q[2] - czv) ** 2) ** 0.5 for q in qs) / len(qs)
            sp = UsdGeom.Sphere.Define(stage, f"/World/mug/col_handle_{bi:02d}")
            sp.CreateRadiusAttr(max(min(tube, 0.010), 0.0035))
            UsdGeom.Xformable(sp).AddTranslateOp().Set(Gf.Vec3d(0.0, cyv, czv))
            UsdGeom.Imageable(sp.GetPrim()).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            UsdPhysics.CollisionAPI.Apply(sp.GetPrim())
            _c2 = PhysxSchema.PhysxCollisionAPI.Apply(sp.GetPrim())
            _c2.CreateRestOffsetAttr().Set(0.0010); _c2.CreateContactOffsetAttr().Set(0.006)
            UsdShade.MaterialBindingAPI.Apply(sp.GetPrim()).Bind(phys_mug, UsdShade.Tokens.weakerThanDescendants, "physics")
            n_ball += 1
    log(f"mug asset: {os.path.basename(src_path)}  verts={len(P)}  "
        f"collider = cylinder(r={rad*1000:.1f} L={2*ax_half*1000:.1f}) + {n_ball} spheres (handle)")
else:
    profile = [(0.0, 0.0), (R, 0.0), (R, MH), (R - WT, MH), (R - WT, BT), (0.0, BT)]
    mug_pts, mug_faces = revolve(profile, nseg=72)
    h_pts_raw, h_faces = torus_xz((R + MUG["handle_offset"], 0.0, MH * 0.52),
                                  MUG["handle_major_r"], MUG["handle_minor_r"])
    if MUG["handle_roll_deg"] == "auto":
        MUG["handle_roll_deg"] = -90.0        # 程序化杯把手在局部 +X
        _M = _SCL * _lay * _roll_mat(-90.0)
    xf = lambda P: [Gf.Vec3f(_M.Transform(Gf.Vec3d(*q))) for q in P]
    mug_pts, h_pts = xf(mug_pts), xf(h_pts_raw)
    cx = (min(q[0] for q in mug_pts) + max(q[0] for q in mug_pts)) / 2.0
    cy = (min(q[1] for q in mug_pts) + max(q[1] for q in mug_pts)) / 2.0
    cz = (min(q[2] for q in mug_pts) + max(q[2] for q in mug_pts)) / 2.0
    mug_pts = [Gf.Vec3f(q[0] - cx, q[1] - cy, q[2] - cz) for q in mug_pts]
    h_pts = [Gf.Vec3f(q[0] - cx, q[1] - cy, q[2] - cz) for q in h_pts]
    body = poly_mesh(stage, "/World/mug/body", mug_pts, mug_faces)
    UsdPhysics.CollisionAPI.Apply(body.GetPrim())
    UsdPhysics.MeshCollisionAPI.Apply(body.GetPrim()).CreateApproximationAttr("convexHull")
    UsdShade.MaterialBindingAPI.Apply(body.GetPrim()).Bind(mat_ceramic)
    UsdShade.MaterialBindingAPI.Apply(body.GetPrim()).Bind(phys_mug, UsdShade.Tokens.weakerThanDescendants, "physics")
    handle = poly_mesh(stage, "/World/mug/handle", h_pts, h_faces)
    UsdPhysics.CollisionAPI.Apply(handle.GetPrim())
    UsdPhysics.MeshCollisionAPI.Apply(handle.GetPrim()).CreateApproximationAttr("convexDecomposition")
    UsdShade.MaterialBindingAPI.Apply(handle.GetPrim()).Bind(mat_ceramic)
    UsdShade.MaterialBindingAPI.Apply(handle.GetPrim()).Bind(phys_mug, UsdShade.Tokens.weakerThanDescendants, "physics")
    log(f"mug: procedural  body {len(mug_pts)}v + handle {len(h_pts)}v")

mug_rb = UsdPhysics.RigidBodyAPI.Apply(mug.GetPrim())
UsdPhysics.MassAPI.Apply(mug.GetPrim()).CreateMassAttr(MUG["mass"])
mug_prb = PhysxSchema.PhysxRigidBodyAPI.Apply(mug.GetPrim())
mug_prb.CreateLinearDampingAttr(MUG["lin_damp"])
mug_prb.CreateAngularDampingAttr(MUG["ang_damp"])
mug_prb.CreateSleepThresholdAttr(0.0005)
mug_prb.CreateMaxDepenetrationVelocityAttr(0.4)
# 質心釘回杯軸(本地原點就在軸上)。不設的話 PhysX 依凸包體積分配,
# 質心會被把手拉偏,躺著的圓柱就會往把手那側滾。
UsdPhysics.MassAPI(mug.GetPrim()).CreateCenterOfMassAttr(Gf.Vec3f(0, 0, 0))

# 量出放倒後的實際外框(杯軸在原點,最低點 z=0)
_c = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
_r = _c.ComputeWorldBound(mug.GetPrim()).ComputeAlignedRange()
MN, MX = _r.GetMin(), _r.GetMax()
MUG_HALF_L = max(abs(MN[0]), abs(MX[0]))          # 沿箱長的半長
MUG_Y_MIN, MUG_Y_MAX = MN[1], MX[1]               # 含把手的橫向範圍
MUG_R = max(abs(MN[2]), abs(MX[2]))               # 半徑(放倒後即半高)
log(f"mug bbox (laid down, axis at origin): x±{MUG_HALF_L*1000:.1f}  "
    f"y[{MUG_Y_MIN*1000:+.1f},{MUG_Y_MAX*1000:+.1f}]  z±{MUG_R*1000:.1f} mm  "
    f"handle_roll={MUG['handle_roll_deg']}")

# =============================================================== 紙箱
MUG_Y_C = (MUG_Y_MIN + MUG_Y_MAX) / 2.0
MUG_HALF_W = (MUG_Y_MAX - MUG_Y_MIN) / 2.0
T = CARTON["board_t"]

if RIG:
    # 用場景自己的紙箱:量出內壁圍出來的空間
    _cc = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])

    def _bb(path):
        pr = stage.GetPrimAtPath(path)
        if not (pr and pr.IsValid()):
            raise SystemExit(f"rig 場景裡找不到 {path}")
        r = _cc.ComputeWorldBound(pr).ComputeAlignedRange()
        return r.GetMin(), r.GetMax()

    CARTON_PATH = "/World/Carton"
    bo_mn, bo_mx = _bb(CARTON_PATH + "/base/bottom")
    xn_mn, xn_mx = _bb(CARTON_PATH + "/base/wxn")
    xp_mn, xp_mx = _bb(CARTON_PATH + "/base/wxp")
    yn_mn, yn_mx = _bb(CARTON_PATH + "/base/wyn")
    yp_mn, yp_mx = _bb(CARTON_PATH + "/base/wyp")
    IN_X0, IN_X1 = xn_mx[0], xp_mn[0]
    IN_Y0, IN_Y1 = yn_mx[1], yp_mn[1]
    Z_FLOOR = bo_mx[2]
    WALL_TOP = xn_mx[2]
    L, W, H = IN_X1 - IN_X0, IN_Y1 - IN_Y0, WALL_TOP - Z_FLOOR
    CX, CY = (IN_X0 + IN_X1) / 2.0, (IN_Y0 + IN_Y1) / 2.0
    base_rb = UsdPhysics.RigidBodyAPI.Apply(stage.GetPrimAtPath(CARTON_PATH + "/base"))
    _ka = base_rb.GetKinematicEnabledAttr()
    BASE_KIN_ORIG = bool(_ka.Get()) if _ka and _ka.HasAuthoredValue() else False
    flap_prims = {n: stage.GetPrimAtPath(f"{CARTON_PATH}/{n}") for n in ("fxp", "fxn", "fyp", "fyn")}
    # 他們的箱板只有 3 mm 厚且沒設 offset,薄板碰撞會讓東西沉下去(跟我自己箱子當初一樣的坑)
    _n_fix = 0
    for _p in Usd.PrimRange(stage.GetPrimAtPath(CARTON_PATH)):
        if _p.HasAPI(UsdPhysics.CollisionAPI):
            _pc = PhysxSchema.PhysxCollisionAPI.Apply(_p)
            # 板只有 3 mm 厚:contact offset 必須小於板厚,否則相鄰的箱壁會互相排斥,
            # 整個箱子會被自己撐爆(實測用 10 mm 時箱子直接飛出桌面)
            _pc.CreateRestOffsetAttr().Set(0.0005)
            _pc.CreateContactOffsetAttr().Set(0.0025)
            _n_fix += 1
    # 他們的 crease 鉸鏈沒有 limit 也沒有 drive:自由鉸鏈在重力下會無限擺盪,
    # 把整個箱子撞翻(實測箱子掉到桌面下 50 mm)。不加 drive,改用剛體阻尼壓住震盪 ——
    # 紙板耳朵本來就不會一直晃。
    for _fn, _fp in flap_prims.items():
        _fr = PhysxSchema.PhysxRigidBodyAPI.Apply(_fp)
        _fr.CreateAngularDampingAttr(4.0)
        _fr.CreateLinearDampingAttr(0.8)
        _fr.CreateSleepThresholdAttr(0.002)
    _br = PhysxSchema.PhysxRigidBodyAPI.Apply(stage.GetPrimAtPath(CARTON_PATH + "/base"))
    _br.CreateAngularDampingAttr(2.0)
    _br.CreateLinearDampingAttr(0.5)
    _br.CreateSleepThresholdAttr(0.002)
    log(f"rig carton: 補上 contact/rest offset 於 {_n_fix} 個碰撞體,耳朵加阻尼 4.0/0.8, "
        f"base kinematicEnabled 原值 = {BASE_KIN_ORIG}(會原樣還原)")
    flap_prims = {n: stage.GetPrimAtPath(f"{CARTON_PATH}/{n}") for n in ("fxp", "fxn", "fyp", "fyn")}
    for _jn in ("crease_fxp", "crease_fxn", "crease_fyp", "crease_fyn"):
        _j = stage.GetPrimAtPath(f"{CARTON_PATH}/{_jn}")
        if _j and _j.IsValid():
            _g = lambda n: (_j.GetAttribute(n).Get() if _j.GetAttribute(n) else None)
            log(f"  {_jn}: axis={_g('physics:axis')} target={_g('drive:angular:physics:targetPosition')} "
                f"limits=({_g('physics:lowerLimit')},{_g('physics:upperLimit')}) "
                f"stiff={_g('drive:angular:physics:stiffness')} damp={_g('drive:angular:physics:damping')}")
    log(f"rig carton: inner {L*1000:.1f} x {W*1000:.1f} x {H*1000:.1f} mm, "
        f"floor z={Z_FLOOR*1000:.1f}, centre=({CX*1000:+.1f},{CY*1000:+.1f}) mm")
else:
    BASE_KIN_ORIG = False
    L = max(2 * (MUG_HALF_L + CARTON["clear_l"]), CARTON["min_inner"][0])
    W = max(2 * (MUG_HALF_W + CARTON["clear_w"]), CARTON["min_inner"][1])
    H = max(2 * MUG_R + CARTON["clear_h"], CARTON["min_inner"][2])
    Z_FLOOR = T
    CX = CY = 0.0

MUG_AXIS_Z = Z_FLOOR + MUG_R + 0.006
mug_tr.Set(Gf.Vec3d(CX, CY - MUG_Y_C, MUG_AXIS_Z))
log(f"mug footprint: span x {2*MUG_HALF_L*1000:.1f} y {2*MUG_HALF_W*1000:.1f} z {2*MUG_R*1000:.1f} mm, "
    f"placed at ({CX*1000:+.1f},{(CY-MUG_Y_C)*1000:+.1f},{MUG_AXIS_Z*1000:.1f}) mm")

if not RIG:
    carton = UsdGeom.Xform.Define(stage, "/World/Carton")
    base = UsdGeom.Xform.Define(stage, "/World/Carton/base")
    UsdGeom.Xformable(base).AddTranslateOp().Set(Gf.Vec3d(0, 0, 0))
    base_rb = UsdPhysics.RigidBodyAPI.Apply(base.GetPrim())
    UsdPhysics.MassAPI.Apply(base.GetPrim()).CreateDensityAttr(CARTON["density"])
    PhysxSchema.PhysxRigidBodyAPI.Apply(base.GetPrim()).CreateSleepThresholdAttr(0.0005)

    def box_part(parent_path, name, size, center, mat_vis, mat_phys):
        c = UsdGeom.Cube.Define(stage, f"{parent_path}/{name}")
        c.CreateSizeAttr(1.0)
        x = UsdGeom.Xformable(c)
        x.AddTranslateOp().Set(Gf.Vec3d(*center))
        x.AddScaleOp().Set(Gf.Vec3f(*size))
        UsdPhysics.CollisionAPI.Apply(c.GetPrim())
        _pc = PhysxSchema.PhysxCollisionAPI.Apply(c.GetPrim())
        _pc.CreateRestOffsetAttr().Set(0.0015)
        _pc.CreateContactOffsetAttr().Set(0.010)
        UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(mat_vis)
        UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(mat_phys, UsdShade.Tokens.weakerThanDescendants, "physics")
        return c

    box_part("/World/Carton/base", "floor", (L + 2 * T, W + 2 * T, T), (0, 0, T / 2), mat_kraft, phys_kraft)
    box_part("/World/Carton/base", "wall_yp", (L + 2 * T, T, H), (0, W / 2 + T / 2, T + H / 2), mat_kraft, phys_kraft)
    box_part("/World/Carton/base", "wall_yn", (L + 2 * T, T, H), (0, -W / 2 - T / 2, T + H / 2), mat_kraft, phys_kraft)
    box_part("/World/Carton/base", "wall_xp", (T, W, H), (L / 2 + T / 2, 0, T + H / 2), mat_kraft, phys_kraft)
    box_part("/World/Carton/base", "wall_xn", (T, W, H), (-L / 2 - T / 2, 0, T + H / 2), mat_kraft, phys_kraft)

    FLAP_W = W / 2.0
    flaps = [
        ("flap_yp", (0, W / 2 + T / 2, T + H), "X", (L + 2 * T, T, FLAP_W), -1.0),
        ("flap_yn", (0, -W / 2 - T / 2, T + H), "X", (L + 2 * T, T, FLAP_W), +1.0),
        ("flap_xp", (L / 2 + T / 2, 0, T + H), "Y", (T, W, FLAP_W), +1.0),
        ("flap_xn", (-L / 2 - T / 2, 0, T + H), "Y", (T, W, FLAP_W), -1.0),
    ]
    flap_prims = {}
    for name, hinge, axis, size, sgn in flaps:
        fx = UsdGeom.Xform.Define(stage, f"/World/Carton/{name}")
        ang = sgn * CARTON["flap_open_deg"]
        xf2 = UsdGeom.Xformable(fx)
        xf2.AddTranslateOp().Set(Gf.Vec3d(*hinge))
        xf2.AddRotateXYZOp().Set(Gf.Vec3f(ang, 0, 0) if axis == "X" else Gf.Vec3f(0, ang, 0))
        UsdPhysics.RigidBodyAPI.Apply(fx.GetPrim())
        UsdPhysics.MassAPI.Apply(fx.GetPrim()).CreateDensityAttr(CARTON["density"])
        box_part(f"/World/Carton/{name}", "board", size, (0, 0, FLAP_W / 2), mat_kraft_in, phys_kraft)
        j = UsdPhysics.RevoluteJoint.Define(stage, f"/World/Carton/joints/{name}")
        j.CreateBody0Rel().SetTargets(["/World/Carton/base"])
        j.CreateBody1Rel().SetTargets([f"/World/Carton/{name}"])
        j.CreateAxisAttr(axis)
        j.CreateLocalPos0Attr(Gf.Vec3f(*hinge))
        j.CreateLocalPos1Attr(Gf.Vec3f(0, 0, 0))
        j.CreateLowerLimitAttr(-130.0)
        j.CreateUpperLimitAttr(130.0)
        d2 = UsdPhysics.DriveAPI.Apply(j.GetPrim(), "angular")
        d2.CreateTypeAttr("force")
        d2.CreateStiffnessAttr(CARTON["drive_stiffness"])
        d2.CreateDampingAttr(CARTON["drive_damping"])
        d2.CreateTargetPositionAttr(ang)
        flap_prims[name] = fx
    log(f"carton (built): inner {L*1000:.0f} x {W*1000:.0f} x {H*1000:.0f} mm, floor z={Z_FLOOR*1000:.1f} mm")

# =============================================================== 泡泡紙(十字裁片)
def _profile(segs, step=2.5e-4):
    """沿弧長積分切線角,回傳 (s[], d[], z[], total)。d = 沿臂方向的橫移,z = 高度。"""
    s_l, d_l, z_l = [0.0], [0.0], [0.0]
    s = d = z = 0.0
    for length, p0, p1 in segs:
        n = max(int(math.ceil(length / step)), 1)
        for i in range(n):
            f = (i + 0.5) / n
            phi = math.radians(p0 + (p1 - p0) * f)
            q = length / n
            d += math.cos(phi) * q
            z += math.sin(phi) * q
            s += q
            s_l.append(s); d_l.append(d); z_l.append(z)
    return s_l, d_l, z_l, s


def arm_profile(spec, root_offset):
    """一隻臂的剖面。root_offset = 臂根離中心的距離,用來求解尖端要走多長。"""
    segs = [
        (spec["corner_r"] * math.radians(90.0), 0.0, 90.0),
        (max(spec["wall_rise"] - spec["corner_r"], 1e-4), 90.0, 90.0),
        (spec["fold_r"] * math.radians(spec["fold_deg"]), 90.0, 90.0 + spec["fold_deg"]),
    ]
    tip = spec["tip_len"]
    if tip is None:                      # 自動求解:折到左右尖端只剩 target_gap
        _, d_a, _, _ = _profile(segs)
        d_a = d_a[-1] if isinstance(d_a, list) else d_a
        phi = math.radians(90.0 + spec["fold_deg"])
        want = spec["target_gap"] / 2.0 - root_offset
        tip = max((want - d_a) / math.cos(phi), 0.0) if abs(math.cos(phi)) > 1e-6 else 0.0
    segs.append((tip, 90.0 + spec["fold_deg"], 90.0 + spec["fold_deg"]))
    return _profile(segs)


def sample_arm(prof, s):
    s_l, d_l, z_l, tot = prof
    if s <= 0:
        return 0.0, 0.0
    if s >= tot:
        return d_l[-1], z_l[-1]
    lo, hi = 0, len(s_l) - 1
    while hi - lo > 1:
        m = (lo + hi) // 2
        if s_l[m] <= s:
            lo = m
        else:
            hi = m
    t = (s - s_l[lo]) / max(s_l[hi] - s_l[lo], 1e-12)
    return d_l[lo] + (d_l[hi] - d_l[lo]) * t, z_l[lo] + (z_l[hi] - z_l[lo]) * t


# 臂根的圓角會往外再走 corner_r,所以 A/B 必須讓「臂根 + 圓角」還留在內壁裡面,
# 否則膜一開始就被箱壁擠住,整片會被推出去(實測漂移 167 mm)。
# 臂要靠著箱壁往上爬才站得住:臂根離牆太遠會變成自立的板子,一定往外倒
# (實測臂根離牆 51 mm 時,短邊臂倒到箱外 43 mm)。所以中央panel 直接鋪到接近內壁。
A = max(MUG_HALF_L + 0.010, L / 2.0 - WRAP["end"]["corner_r"] - 0.006)
B = max(MUG_HALF_W + 0.010, W / 2.0 - WRAP["side"]["corner_r"] - 0.006)
log(f"clearance check: B+corner={((B + WRAP['side']['corner_r'])*1000):.1f} mm vs 內壁 {W/2*1000:.1f} mm | "
    f"A+corner={((A + WRAP['end']['corner_r'])*1000):.1f} vs {L/2*1000:.1f}")
# 臂沿箱壁爬升的高度不能超過箱壁 —— 超出的部分沒東西撐,會往外翻並把整片拖出箱外
# (實測:爬到 104.5 mm 而箱壁只有 87 mm,結果整片滑出去,漂移 297 mm)。
# 折進來的圓弧本身會再抬 fold_r,尖端剛好落在杯頂上,視覺上就是「蓋過去」。
# 折進來的圓弧會再抬 fold_r,所以尖端高度 = LIFT + wall_rise + fold_r。
# 要求尖端留在箱緣以下,否則超出的部分沒東西撐會往外翻並把整片拖出去。
_lift_h = 0.006
_side_cap = H - WRAP["side"]["fold_r"] - _lift_h - 0.006
_end_cap = H - WRAP["end"]["fold_r"] - _lift_h - 0.010
WRAP["side"]["wall_rise"] = min(2 * MUG_R + 0.012, _side_cap)
WRAP["end"]["wall_rise"] = min(2 * MUG_R + 0.008, _end_cap)
log(f"arm rise capped by carton: side {WRAP['side']['wall_rise']*1000:.1f} (cap {_side_cap*1000:.1f}) "
    f"end {WRAP['end']['wall_rise']*1000:.1f} | 杯頂 {(2*MUG_R+0.010)*1000:.1f} mm above floor")
log(f"wrap panel (derived): center half x={A*1000:.1f} y={B*1000:.1f} mm, "
    f"side wall_rise={WRAP['side']['wall_rise']*1000:.1f} mm")
# 短邊臂的尖端要折到蓋住杯子端面(不是固定長度,否則臂根一外移就搆不到,會站著往外倒)
if WRAP["end"].get("target_gap") is None:
    WRAP["end"]["target_gap"] = 2.0 * max(MUG_HALF_L - 0.012, 0.010)
side = arm_profile(WRAP["side"], B)      # 長邊:繞杯身捲上去,杯頂合攏
end = arm_profile(WRAP["end"], A)        # 短邊:立起來往內壓,封住前後端面
LS, LE = side[3], end[3]
log(f"arms: side len {LS*1000:.1f} mm tip d={side[1][-1]*1000:+.1f} z={side[2][-1]*1000:.1f} -> "
    f"y={(B+side[1][-1])*1000:+.1f} mm | end len {LE*1000:.1f} mm tip d={end[1][-1]*1000:+.1f} "
    f"z={end[2][-1]*1000:.1f} -> x={(A+end[1][-1])*1000:+.1f} mm")

h = BUBBLE["cell_size"]
NU = 2 * int(math.ceil((A + LE) / h))            # 材料空間格數(偶數,中心在格線上)
NV = 2 * int(math.ceil((B + LS) / h))
HU, HV = A + LE, B + LS
LIFT = Z_FLOOR + _lift_h


def mat_uv(i, j):
    return -HU + 2 * HU * i / NU, -HV + 2 * HV * j / NV


def keep(i, j):
    u, v = mat_uv(i, j)
    return abs(u) <= A + 1e-9 or abs(v) <= B + 1e-9    # 十字:四個角不留料


def to3d(u, v):
    if abs(u) <= A + 1e-9 and abs(v) <= B + 1e-9:
        return Gf.Vec3f(CX + u, CY + v, LIFT)                          # 中央:貼箱底
    if abs(v) > B:                                                     # 長邊臂
        d, z = sample_arm(side, abs(v) - B)
        return Gf.Vec3f(CX + u, CY + math.copysign(B + d, v), LIFT + z)
    d, z = sample_arm(end, abs(u) - A)                                 # 短邊臂
    return Gf.Vec3f(math.copysign(A + d, u), v, LIFT + z)


idx, wrap_pts, wrap_flat, wrap_uv = {}, [], [], []
pitch = BUBBLE["bubble_pitch"]
for j in range(NV + 1):
    for i in range(NU + 1):
        if not keep(i, j):
            continue
        u, v = mat_uv(i, j)
        idx[(i, j)] = len(wrap_pts)
        wrap_pts.append(to3d(u, v))
        wrap_flat.append(Gf.Vec3f(CX + u, CY + v, LIFT))   # 攤平的材料佈局(自碰撞過濾用)
        wrap_uv.append(Gf.Vec2f(u / pitch, v / pitch))  # 一格 UV = 一顆泡泡
wrap_tris = []
for j in range(NV):
    for i in range(NU):
        q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
        if not all(c in idx for c in q):
            continue
        a_, b_, c_, d_ = (idx[c] for c in q)
        wrap_tris.append((a_, b_, c_))
        wrap_tris.append((a_, c_, d_))

# 面積由實際三角形算,質量才對
area = 0.0
for t in wrap_tris:
    p0, p1, p2 = (Gf.Vec3d(*wrap_flat[k]) for k in t)
    area += Gf.Cross(p1 - p0, p2 - p0).GetLength() * 0.5
wrap_mass = BUBBLE["areal_mass"] * area

wrap_mesh, wrap_ok, wrap_coll = wf.make_surface_deformable(
    stage, "/World/wrap", wrap_pts, wrap_tris, phys_film, wrap_mass,
    solver_iter=SIM["bake_solver_iter"], lin_damp=BUBBLE["lin_damp"],
    self_collision=True, contact_off=BUBBLE["contact_offset"], rest_off=BUBBLE["rest_offset"],
    collision_pair_update=SIM["bake_collision_pair_update"],
    collision_iter_mult=SIM["bake_collision_iter_mult"],
    max_depen_vel=SIM["max_depen_vel"], uvs=wrap_uv)
wrap_prim = wrap_mesh.GetPrim()
UsdShade.MaterialBindingAPI.Apply(wrap_prim).Bind(mat_film)


def mesh_normals(pts, tris):
    acc = [Gf.Vec3f(0, 0, 0)] * len(pts)
    for t in tris:
        a0, b0, c0 = (Gf.Vec3d(*pts[i]) for i in t)
        n = Gf.Cross(b0 - a0, c0 - a0)
        ln = n.GetLength()
        if ln < 1e-12:
            continue
        nf = Gf.Vec3f(n / ln)
        for i in t:
            acc[i] = acc[i] + nf
    out = []
    for v in acc:
        l = v.GetLength()
        out.append(v / l if l > 1e-9 else Gf.Vec3f(0, 0, 1))
    return out


wrap_mesh.CreateNormalsAttr().Set(Vt.Vec3fArray(mesh_normals(wrap_pts, wrap_tris)))
wrap_mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)

# 核心:把「已經折好」的形狀直接當成靜止形狀 -> 折痕是零能量狀態,不會彈開
wf.set_attr(wrap_prim, "omniphysics:restShapePoints", Vt.Vec3fArray(wrap_pts))
wf.set_attr(wrap_prim, "omniphysics:restBendAnglesDefault", "restShapeDefault")

# 自碰撞過濾姿態 = 攤平的材料佈局。
# 不設的話 PhysX 會拿「當下(已經折疊重疊)」的點去做過濾,把互相蓋住的臂判成
# 本來就重疊而排除自碰撞 -> 四隻臂會彼此穿透。
try:
    wrap_prim.ApplyAPI("OmniPhysicsDeformablePoseAPI", "scFilter")
except Exception as e:
    carb.log_warn(f"[forge] DeformablePoseAPI apply: {e}")
wf.set_attr(wrap_prim, "deformablePose:scFilter:omniphysics:purposes",
            Vt.TokenArray(["selfCollisionFilterPose"]), Sdf.ValueTypeNames.TokenArray)
wf.set_attr(wrap_prim, "deformablePose:scFilter:omniphysics:points",
            Vt.Vec3fArray(wrap_flat), Sdf.ValueTypeNames.Point3fArray)

log(f"wrap: {len(wrap_pts)} verts / {len(wrap_tris)} tris, material grid {NU}x{NV} @ {h*1000:.1f} mm, "
    f"area={area*1e4:.1f} cm2, mass={wrap_mass*1000:.2f} g (areal {BUBBLE['areal_mass']*1000:.0f} g/m2), "
    f"bendStiffness={BUBBLE['surface_bend_stiffness']:.1f} (D={BUBBLE['flexural_rigidity']:.3e} N*m), "
    f"selfCollision=on")

# =============================================================== 烘焙
report = {
    "isaac_version": open("/isaac-sim/VERSION").read().strip(),
    "carton_inner_mm": [L * 1000, W * 1000, H * 1000],
    "wrap_verts": len(wrap_pts), "wrap_tris": len(wrap_tris),
    "wrap_mass_kg": round(wrap_mass, 6),
    "wrap_area_cm2": round(area * 1e4, 2),
    "surface_bend_stiffness": round(BUBBLE["surface_bend_stiffness"], 3),
    "flexural_rigidity_Nm": BUBBLE["flexural_rigidity"],
    "baked": not ARGS.no_bake,
}

if not ARGS.no_bake:
    steps = ARGS.settle_steps or SIM["settle_steps"]
    # 兩階段原則:靜置時杯子固定,膜自己貼合 -> 只有一個 deformable 在動,最穩
    mug_rb.CreateKinematicEnabledAttr(True)
    base_rb.CreateKinematicEnabledAttr(True)   # 耳朵維持動態:kinematic 之間不能建 joint

    sim = SimulationContext(physics_dt=1.0 / SIM["bake_hz"], rendering_dt=1.0 / SIM["bake_hz"],
                            stage_units_in_meters=1.0)
    pcx = sim.get_physics_context()
    pcx.enable_gpu_dynamics(True)
    pcx.set_broadphase_type("GPU")
    pcx.set_solver_type("TGS")
    sim.initialize_physics()
    sim.play()

    def settle(n, tag):
        prev = list(wrap_mesh.GetPointsAttr().Get())
        done = n
        for k in range(n):
            sim.step(render=False)
            if k % 60 == 59:
                cur = list(wrap_mesh.GetPointsAttr().Get())
                v = max(math.dist(tuple(cur[i]), tuple(prev[i])) for i in range(len(cur))) * SIM["bake_hz"] / 60.0
                prev = cur
                if k > 180 and v < SIM["settle_vel_eps"]:
                    done = k + 1
                    log(f"{tag}: settled at step {done} (max vertex speed {v:.5f} m/s)")
                    return done
        log(f"{tag}: ran full {n} steps")
        return done

    # 階段 1:杯子固定,只有膜在動 -> 場上只有一個 deformable 在接觸,最穩
    a1 = settle(steps, "phase1 mug-kinematic")
    # 階段 2:杯子轉動態,讓膜的搖籃真的把它托住
    mug_rb.CreateKinematicEnabledAttr(False)
    a2 = settle(SIM["settle2_steps"], "phase2 mug-dynamic")
    settled_at = a1 + a2

    settled = list(wrap_mesh.GetPointsAttr().Get())
    drift = max(math.dist(tuple(settled[i]), tuple(wrap_pts[i])) for i in range(len(settled)))
    sim.stop()

    alpha = SIM["plasticity_alpha"]
    if alpha >= 0.999:
        new_rest = settled
    else:
        new_rest = [Gf.Vec3f(*(Gf.Vec3f(*wrap_pts[i]) + (Gf.Vec3f(*settled[i]) - Gf.Vec3f(*wrap_pts[i])) * alpha))
                    for i in range(len(settled))]

    wrap_mesh.GetPointsAttr().Set(Vt.Vec3fArray(settled))
    wrap_mesh.GetNormalsAttr().Set(Vt.Vec3fArray(mesh_normals(settled, wrap_tris)))
    wrap_mesh.CreateVelocitiesAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0, 0, 0)] * len(settled)))
    wf.set_attr(wrap_prim, "omniphysics:restShapePoints", Vt.Vec3fArray(new_rest))
    xs = [p[0] for p in settled]; yy = [p[1] for p in settled]; zz = [p[2] for p in settled]
    wrap_mesh.GetExtentAttr().Set(Vt.Vec3fArray([Gf.Vec3f(min(xs), min(yy), min(zz)),
                                                 Gf.Vec3f(max(xs), max(yy), max(zz))]))

    # 交付狀態:杯子轉動態;紙箱還原成場景原本的設定。
    # 他們的 /World/Carton/base 本來就是 kinematicEnabled=True,擅自改成 dynamic
    # 會讓整個箱子掉下桌(實測 min z 掉到 -31 mm)。PPT 要求「箱子會被手臂推動」時
    # 再由手臂團隊決定要不要轉動態。
    base_rb.CreateKinematicEnabledAttr(BASE_KIN_ORIG)
    px_scene.CreateTimeStepsPerSecondAttr(SIM["deliver_hz"])
    wf.set_attr(wrap_prim, "physxDeformableBody:solverPositionIterationCount",
                int(SIM["deliver_solver_iter"]), Sdf.ValueTypeNames.UInt)
    wf.refresh_film_offsets(wrap_coll, BUBBLE["contact_offset"], BUBBLE["rest_offset"])

    report.update(settle_steps_run=settled_at, settle_drift_m=round(drift, 5),
                  plasticity_alpha=alpha)
    log(f"bake done: settled in {settled_at} steps, drift {drift*1000:.2f} mm, alpha={alpha}")

# 預設觀看相機:一開 viewer 就對著箱子
_cam = UsdGeom.Camera.Define(stage, "/World/ViewCam")
_cam.CreateFocalLengthAttr(30.0)
_cam.CreateClippingRangeAttr(Gf.Vec2f(0.01, 50.0))
_cam.CreateFocusDistanceAttr(0.55)
_m = Gf.Matrix4d().SetLookAt(Gf.Vec3d(0.40, -0.40, 0.30), Gf.Vec3d(0.0, 0.0, 0.05),
                             Gf.Vec3d(0, 0, 1)).GetInverse()
UsdGeom.Xformable(_cam).MakeMatrixXform().Set(_m)

# endTimeCode 不能是 0:timeline 一播放就會立刻到結尾停住,
# 而「timeline 正在播放」是 omni.physx.ui 滑鼠拖曳的第二道閘門。
stage.SetTimeCodesPerSecond(60.0)
stage.SetStartTimeCode(0.0)
stage.SetEndTimeCode(1000000.0)
stage.GetRootLayer().Export(USD_OUT) if not RIG else stage.Export(USD_OUT)
report["usd"] = USD_OUT
report["log"] = _LOG
with open(os.path.join(OUT, "forge_report.json"), "w") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
log(f"saved -> {USD_OUT}")

simulation_app.close()
os._exit(0)
