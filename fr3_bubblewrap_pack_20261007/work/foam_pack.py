#!/usr/bin/env python3
"""foam_pack.py — volume deformable(FEM 泡棉)版包材:上下兩塊泡棉墊夾住馬克杯,剛性平板壓。

使用者 2026-09-25:「弄完之後 做一版 deformable volume 的」

為什麼不是把那張 586mm 的布改成 volume:四面體化器**照物體整體尺寸決定元素大小**,
586mm 見方的板子元素邊長會到數十 mm,薄板切不出厚度方向的層。
volume 版的正確形態是泡棉墊,這也是真實包裝的做法。

配方全部照 2026-09-07 定案(memory: foam-shell-working-params / volume-fem-cook-and-gravity):
  · **新版 beta API** create_auto_volume_deformable_hierarchy(舊版 add_physx_deformable_body
    跟 beta 旗標混用會讓 youngs_modulus 完全失效)
  · 形狀用**細分方塊**、頂點共用 → cook 一定過(UV 球必失敗)
  · **重力一開始就開**
  · solverPositionIterationCount = 64(全場景取最大)
  · PhysxCollisionAPI + physxCollision:contactOffset = 0.003(預設會離物約 20mm)
  · young 1e5 / poisson 0.30 / density 60
"""
import os, argparse
import numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--mug", default="mug.stl")
ap.add_argument("--out", default="out_foam")
ap.add_argument("--pad_x", type=float, default=0.240)
ap.add_argument("--pad_y", type=float, default=0.200)
ap.add_argument("--pad_z", type=float, default=0.030, help="單塊泡棉厚度")
ap.add_argument("--n", type=int, default=6, help="細分數(每邊)")
ap.add_argument("--young", type=float, default=1e5)
ap.add_argument("--poisson", type=float, default=0.30)
ap.add_argument("--density", type=float, default=60.0)
ap.add_argument("--solver", type=int, default=64)
ap.add_argument("--press", type=float, default=100.0, help="壓到幾 mm(紙箱內高)")
ap.add_argument("--carton", default="")
ap.add_argument("--carton_t", type=float, default=0.003)
a, _ = ap.parse_known_args()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
os.makedirs(a.out, exist_ok=True)

from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from isaacsim.core.prims import SingleXFormPrim
from isaacsim.sensors.camera import Camera
from pxr import Usd, Gf, Sdf, UsdGeom, UsdPhysics, UsdShade, UsdLux, PhysxSchema, Vt
from omni.physx.scripts import deformableUtils
import omni.usd, trimesh, imageio.v3 as iio
from PIL import Image, ImageDraw, ImageFont
import grip_common as G

LOG = open(os.path.join(a.out, "log.txt"), "w")
def P(*s):
    print(*s, flush=True); LOG.write(" ".join(str(x) for x in s) + "\n"); LOG.flush()

FPS = 30
world = World(physics_dt=1/120.0, rendering_dt=1/FPS)
world.scene.add_default_ground_plane()          # ★ 重力一開始就開,不要事後再開
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

def sa(prim, n, v, tn=None):
    at = prim.GetAttribute(n)
    if not at or not at.IsValid():
        if tn is None: return
        at = prim.CreateAttribute(n, tn)
    at.Set(v)

def vmat(path, rgb, op=1.0, rough=0.5):
    m = UsdShade.Material.Define(st, path)
    sh = UsdShade.Shader.Define(st, path + "/S"); sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(op)
    m.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return m
FOAM = vmat("/World/foamm", (0.93, 0.90, 0.84), 1.0, 0.85)
MUGM = vmat("/World/mugm", (144/255., 163/255., 189/255.), 1.0, .45)

# ── 紙箱(可選)──────────────────────────────────────────────────────
CDZ = 0.0
if a.carton:
    bxp = st.DefinePrim("/World/Box", "Xform")
    bxp.GetReferences().AddReference(os.path.abspath(a.carton))
    for p_ in Usd.PrimRange(bxp):
        if p_.HasAPI(UsdPhysics.RigidBodyAPI):
            at = p_.GetAttribute("physics:kinematicEnabled")
            (at if at and at.IsValid() else
             p_.CreateAttribute("physics:kinematicEnabled", Sdf.ValueTypeNames.Bool)).Set(True)
    bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
    rr = bb.ComputeWorldBound(bxp).ComputeAlignedRange()
    CDZ = float(rr.GetMin()[2]) + a.carton_t
    P("★ 紙箱 %s;箱底內面 z=%.1f mm" % (a.carton, CDZ*1e3))

# ── 杯子(躺平,跟 surface 版同一個姿態)──────────────────────────────
m = trimesh.load(a.mug)
V = np.asarray(m.vertices, float); F = np.asarray(m.faces)
unit = 0.001 if np.ptp(V, axis=0).max() > 1.0 else 1.0
V = (V - V.mean(0))*unit
Ry = lambda t: np.array([[np.cos(t), 0, np.sin(t)], [0, 1, 0], [-np.sin(t), 0, np.cos(t)]])
Rx = lambda t: np.array([[1, 0, 0], [0, np.cos(t), -np.sin(t)], [0, np.sin(t), np.cos(t)]])
V = V @ Ry(-np.pi/2).T @ Rx(np.pi/2).T
V -= (V.max(0) + V.min(0))/2.0
ME = V.max(0) - V.min(0)
P("杯子躺平 %.0f x %.0f x %.0f mm" % tuple(ME*1e3))

MZ = CDZ + a.pad_z + ME[2]/2                     # 杯子躺在下墊上
mug = UsdGeom.Xform.Define(st, "/World/mug")
UsdGeom.Xformable(mug).AddTranslateOp().Set(Gf.Vec3d(0, 0, MZ))
UsdPhysics.RigidBodyAPI.Apply(mug.GetPrim()).CreateKinematicEnabledAttr(True)
g = UsdGeom.Mesh.Define(st, "/World/mug/geo")
g.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*[float(x) for x in p]) for p in V]))
g.GetFaceVertexCountsAttr().Set([3]*len(F))
g.GetFaceVertexIndicesAttr().Set([int(k) for t in F for k in t])
UsdPhysics.CollisionAPI.Apply(g.GetPrim())
UsdPhysics.MeshCollisionAPI.Apply(g.GetPrim()).CreateApproximationAttr("convexDecomposition")
gc = PhysxSchema.PhysxCollisionAPI.Apply(g.GetPrim())
gc.CreateContactOffsetAttr(0.004); gc.CreateRestOffsetAttr(0.001)
UsdShade.MaterialBindingAPI.Apply(g.GetPrim()).Bind(MUGM)

# ── 泡棉墊:細分方塊(共用頂點 → watertight → cook 一定過)────────────
def box_mesh(sx, sy, sz, n):
    """細分方塊。★ 直接抄 deform/02_foam/indent5.py 的 flat_top_blob —— 那個版本
    2026-09-07 實測 cook 得過(六個面各自寫死繞向,頂點用 dict 共用)。
    我自己用一個通用 face() 產的版本 cook 失敗 5 次(Mesh is invalid),不要重造。
    唯一的改動:邊長可以三軸不同(原版是立方)。"""
    vd = {}; pts = []
    def gv(i, j, k):
        key = (i, j, k)
        if key not in vd:
            vd[key] = len(pts)
            pts.append((-sx/2 + sx*i/n, -sy/2 + sy*j/n, -sz/2 + sz*k/n))
        return vd[key]
    F = []
    for j in range(n):
        for i in range(n):
            a, b, c, d = gv(i, j, 0), gv(i+1, j, 0), gv(i+1, j+1, 0), gv(i, j+1, 0); F += [(a, c, b), (a, d, c)]
            a, b, c, d = gv(i, j, n), gv(i+1, j, n), gv(i+1, j+1, n), gv(i, j+1, n); F += [(a, b, c), (a, c, d)]
    for i in range(n):
        for k in range(n):
            a, b, c, d = gv(i, 0, k), gv(i+1, 0, k), gv(i+1, 0, k+1), gv(i, 0, k+1); F += [(a, b, c), (a, c, d)]
            a, b, c, d = gv(i, n, k), gv(i+1, n, k), gv(i+1, n, k+1), gv(i, n, k+1); F += [(a, c, b), (a, d, c)]
    for j in range(n):
        for k in range(n):
            a, b, c, d = gv(0, j, k), gv(0, j+1, k), gv(0, j+1, k+1), gv(0, j, k+1); F += [(a, c, b), (a, d, c)]
            a, b, c, d = gv(n, j, k), gv(n, j+1, k), gv(n, j+1, k+1), gv(n, j, k+1); F += [(a, b, c), (a, c, d)]
    return np.array(pts), F

def foam(name, z):
    Pn, T = box_mesh(a.pad_x, a.pad_y, a.pad_z, a.n)
    root = UsdGeom.Xform.Define(st, "/World/" + name)
    UsdGeom.Xformable(root).AddTranslateOp().Set(Gf.Vec3d(0, 0, z))
    mesh = UsdGeom.Mesh.Define(st, "/World/%s/mesh" % name)
    mesh.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*[float(x) for x in p]) for p in Pn]))
    mesh.GetFaceVertexCountsAttr().Set([3]*len(T))
    mesh.GetFaceVertexIndicesAttr().Set([int(k) for t in T for k in t])
    # ★ 新版 beta API。舊版 add_physx_deformable_body 跟 beta 旗標混用 → young 完全失效
    deformableUtils.create_auto_volume_deformable_hierarchy(
        st, "/World/" + name, "/World/%s/simTet" % name, "/World/%s/colTet" % name,
        "/World/%s/mesh" % name,
        simulation_hex_mesh_enabled=False, cooking_src_simplification_enabled=False)
    rp = root.GetPrim()
    rp.ApplyAPI("PhysxBaseDeformableBodyAPI")
    sa(rp, "physxDeformableBody:solverPositionIterationCount", a.solver, Sdf.ValueTypeNames.Int)
    PhysxSchema.PhysxCollisionAPI.Apply(rp)
    sa(rp, "physxCollision:contactOffset", 0.003, Sdf.ValueTypeNames.Float)
    sa(rp, "physxCollision:restOffset", 0.0, Sdf.ValueTypeNames.Float)
    UsdShade.MaterialBindingAPI.Apply(rp).Bind(FMAT, UsdShade.Tokens.weakerThanDescendants, "physics")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(FOAM)
    P("  %s:%d 點 %d 面,%.0f x %.0f x %.0f mm,中心 z=%.0f mm"
      % (name, len(Pn), len(T), a.pad_x*1e3, a.pad_y*1e3, a.pad_z*1e3, z*1e3))
    return root

FMAT = UsdShade.Material.Define(st, "/World/fmat"); fmp = FMAT.GetPrim()
fmp.ApplyAPI("OmniPhysicsBaseMaterialAPI")
sa(fmp, "omniphysics:dynamicFriction", 0.7); sa(fmp, "omniphysics:density", a.density)
fmp.ApplyAPI("OmniPhysicsDeformableMaterialAPI")
sa(fmp, "omniphysics:youngsModulus", a.young); sa(fmp, "omniphysics:poissonsRatio", a.poisson)

P("泡棉墊(volume FEM,young=%.0e poisson=%.2f density=%.0f solver=%d):" % (a.young, a.poisson, a.density, a.solver))
LOW = foam("foam_lo", CDZ + a.pad_z/2)
UP  = foam("foam_up", CDZ + a.pad_z + ME[2] + a.pad_z/2)

# ── 壓板 ────────────────────────────────────────────────────────────
PLZ0 = CDZ + 0.30
pl = UsdGeom.Cube.Define(st, "/World/press"); pl.CreateSizeAttr(1.0)
xf = UsdGeom.Xformable(pl); PT = xf.AddTranslateOp(); xf.AddScaleOp().Set(Gf.Vec3f(0.16, 0.14, 0.010))
PT.Set(Gf.Vec3d(0, 0, PLZ0))
UsdPhysics.CollisionAPI.Apply(pl.GetPrim())
UsdPhysics.RigidBodyAPI.Apply(pl.GetPrim()).CreateKinematicEnabledAttr(True)
pc = PhysxSchema.PhysxCollisionAPI.Apply(pl.GetPrim())
pc.CreateContactOffsetAttr(0.005); pc.CreateRestOffsetAttr(0.001)
UsdShade.MaterialBindingAPI.Apply(pl.GetPrim()).Bind(MUGM)

cam = Camera(prim_path="/World/cam", resolution=(1280, 720), frequency=FPS)
cam.set_focal_length(4.0)
world.reset(); cam.initialize()
plate = SingleXFormPrim("/World/press", name="plate")
R = 0.42
G.look(cam, [R*1.45, -R*1.55, CDZ + R*1.0], [0, 0, CDZ + 0.05])
G.add_headlight(st, [R*1.45, -R*1.55, CDZ + R*1.0], [0, 0, CDZ + 0.05], intensity=2000.0, name="hl1")
G.add_headlight(st, [-.5, -.5, .8], [0, 0, CDZ + 0.05], intensity=1200.0, name="hl2")
UsdLux.DomeLight.Define(st, "/World/dome").CreateIntensityAttr(500.0)

def top_of(root):
    pa = UsdGeom.Mesh(st.GetPrimAtPath(str(root.GetPath()) + "/mesh")).GetPointsAttr().Get()
    if pa is None: return float("nan")
    w = Gf.Matrix4d(UsdGeom.Xformable(root).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
    return max(float(w.Transform(Gf.Vec3d(p[0], p[1], p[2]))[2]) for p in pa)

try: FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 17)
except Exception: FONT = ImageFont.load_default()
L1 = ("VOLUME FEM foam pads %.0fx%.0fx%.0f mm x2 | mug %.0fx%.0fx%.0f | press to %.0fmm"
      % (a.pad_x*1e3, a.pad_y*1e3, a.pad_z*1e3, *(ME*1e3), a.press))
L2 = ("young=%.0e poisson=%.2f density=%.0f solver=%d contactOffset=3mm | N=%d"
      % (a.young, a.poisson, a.density, a.solver, a.n))

T_SET, T_DOWN, T_HOLD, T_OFF = 1.5, 4.0, 3.0, 3.0
T_END = T_SET + T_DOWN + T_HOLD + T_OFF
ss = lambda u: (lambda v: v*v*(3-2*v))(min(max(u, 0.), 1.))
H = {}
frames = []
for k in range(int(T_END*FPS)):
    t = k/FPS
    z1 = CDZ + a.press/1000.0 + 0.010
    if   t < T_SET:                        z = PLZ0; ph = "settle"
    elif t < T_SET + T_DOWN:               z = PLZ0 + (z1-PLZ0)*ss((t-T_SET)/T_DOWN); ph = "press down"
    elif t < T_SET + T_DOWN + T_HOLD:      z = z1; ph = "hold %.0fmm" % a.press
    else:                                  z = PLZ0; ph = "plate off"
    plate.set_world_pose(position=np.array([0., 0., z]), orientation=np.array([1., 0, 0, 0]))
    for _ in range(4): world.step(render=False)
    world.step(render=True)
    tu = top_of(UP)
    if ph == "settle": H["before"] = tu
    elif ph.startswith("hold"): H["held"] = tu
    elif ph == "plate off": H["after"] = tu
    rgb = cam.get_rgba()
    if rgb is not None and rgb.size:
        im = Image.fromarray((rgb[:, :, :3]*255).astype(np.uint8) if rgb.dtype != np.uint8 else rgb[:, :, :3])
        d = ImageDraw.Draw(im); W, Hh = im.size
        d.rectangle([0, Hh-58, W, Hh], fill=(16, 16, 18))
        d.text((10, Hh-54), L1, fill=(235,)*3, font=FONT)
        d.text((10, Hh-30), L2, fill=(170, 200, 230), font=FONT)
        d.text((W-300, 10), "t=%.2fs  %s" % (t, ph), fill=(255,)*3, font=FONT)
        frames.append(np.array(im))
    if k % 30 == 0:
        P("  t=%5.2f %-12s 上墊頂面 %6.1f mm" % (t, ph, tu*1e3))
iio.imwrite(os.path.join(a.out, "foam.mp4"), frames, fps=FPS, codec="libx264", quality=8)
P("影格 %d → %s/foam.mp4" % (len(frames), a.out))

P("\n===== 泡棉壓平判讀 =====")
P("V1 上墊頂面:壓之前 %.0f mm → 壓住 %.0f mm(下降 %.0f mm)→ 抬走 %.0f mm(回彈 %.0f mm)"
  % (H.get("before", 0)*1e3, H.get("held", 0)*1e3,
     (H.get("before", 0)-H.get("held", 0))*1e3, H.get("after", 0)*1e3,
     (H.get("after", 0)-H.get("held", 0))*1e3))
mp_ = SingleXFormPrim("/World/mug", name="mugx").get_world_pose()[0]
P("V2 杯心 (%.0f, %.0f, %.0f) mm(起點 0,0,%.0f);位移 %.1f mm"
  % (*(np.array(mp_)*1e3), MZ*1e3, np.linalg.norm(np.array(mp_) - np.array([0, 0, MZ]))*1e3))
P("V4 壓住時整包 %.0f x %.0f x %.0f mm(紙箱內徑 264 x 224 x 100)"
  % (a.pad_x*1e3, a.pad_y*1e3, H.get("held", 0)*1e3))
P("★ V0 cook 有沒有過:跑完用 grep -c 'tetrahedral meshes.*failed' 看 log,必須是 0")
LOG.close(); sim.close()
