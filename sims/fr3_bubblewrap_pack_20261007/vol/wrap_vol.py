#!/usr/bin/env python3
"""wrap_vol.py — volume deformable 薄板(4mm)包馬克杯 → 入紙箱關蓋 → 搬箱 → 開蓋,單一次模擬跑完全程。

    /isaac-sim/python.sh wrap_vol.py --sheet_mm 400 --out out_v400 [--until fold|box|move]

階段(預設時間,秒;--fold_span / --lid_span 可改):
  settle 0.5 → fold xp → fold xn → fold yp → fold yn(各 3.0 動 + 0.5 停)
  → into box(紙箱折疊期間停在旁邊 OFF_SIDE;折完把**箱子**剛性瞬移到包裹周圍 —— 與 surface 版
    「整包(布+杯子)用同一個向量搬」等價:只看相對位置)→ settle 1.0
  → close lower lids(4)→ close upper lids(4)→ release anchors(RemovePrim)+ 杯子轉 dynamic → settle 2
  → move box(6,smoothstep)→ settle 2 → open upper lids(3)→ open lower lids(3)→ hold 3

從 ../work/wrap_sim.py 搬來(標 [ws]):杯子躺平/方位(Rz(-90)+_Rm)、佔位/折線幾何(margin/wall)、
  FOLD_ORDER、SIDEPICK 角落歸屬規則、wrap_arc_from 兩段圓弧的想法、film_tex 泡泡材質、vmat、燈光、
  紙箱載入/不透明材質/meta 讀內腔與鉸鏈、蓋子 sgn 自檢、reset 前把蓋子擺開、lid_pose、關/開蓋順序、
  搬箱 smoothstep、base_collider_pad、地板碰撞關閉、inbox 逐頂點比對、相機/字幕。
從 vol/ 探針沿用:volcommon.build_plate(manual 35x35x1、5-tet 鏡像)、attach_vtx、vol_pen.self_pen_count。
"""
import os, sys, argparse, time, json
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--sheet_mm", type=float, default=400.0)
ap.add_argument("--sheet_x_mm", type=float, default=0.0, help="長方形布 x 邊長;0 = 沿用 --sheet_mm")
ap.add_argument("--sheet_y_mm", type=float, default=0.0, help="長方形布 y 邊長;0 = 沿用 --sheet_mm")
ap.add_argument("--out", default="out_vol")
ap.add_argument("--mug", default="mug.stl")
ap.add_argument("--carton", default="carton_w131.usd")
ap.add_argument("--tex", default="bubble_normal.png")
ap.add_argument("--tex_mm", type=float, default=200.0)
ap.add_argument("--thick_mm", type=float, default=4.0)
ap.add_argument("--nxy", type=int, default=35)
ap.add_argument("--young", type=float, default=2e4)
ap.add_argument("--poisson", type=float, default=0.45)
ap.add_argument("--areal", "--areal_density", dest="areal", type=float, default=0.1, help="面密度 kg/m²")
ap.add_argument("--fric", type=float, default=0.8)
ap.add_argument("--cont", type=float, default=0.002)
ap.add_argument("--rest", type=float, default=0.0005)
ap.add_argument("--solver", type=int, default=128)
ap.add_argument("--dt", type=float, default=1/240.0)
ap.add_argument("--margin", type=float, default=0.012, help="[ws] 佔位比杯子大多少(m)")
ap.add_argument("--wall", type=float, default=0.006, help="[ws] 折線離佔位側面(m)")
ap.add_argument("--fold_span", type=float, default=3.0, help="每折動作秒數")
ap.add_argument("--fold_hold", type=float, default=0.5, help="每折到位後停幾秒")
ap.add_argument("--slow", default="", help="某折放慢,例 yp:1.5,yn:1.5")
ap.add_argument("--tip_extra", default="", help="某折終點加高 mm,例 yp:2 或 all:2")
ap.add_argument("--tip_over_mm", type=float, default=30.0, help="尖端最多越過中線多少 mm(夾住)")
ap.add_argument("--lid_span", type=float, default=4.0)
ap.add_argument("--open_span", type=float, default=3.0)
ap.add_argument("--movebox", default="0,0.20,0.10")
ap.add_argument("--move_t", type=float, default=6.0)
ap.add_argument("--base_collider_pad", type=float, default=0.02)
ap.add_argument("--squeeze_t", type=float, default=2.5, help="四折後四面側板收到紙箱內腔-3mm 用幾秒(0=不做)")
ap.add_argument("--squeeze_mm", type=float, default=3.0, help="側板停在內腔內縮幾 mm")
ap.add_argument("--until", choices=["fold", "box", "move", "all"], default="all")
ap.add_argument("--rest_npz", default="", help="restShapePoints = 這個 npz 的 fold_end tet 頂點(points 仍平)")
ap.add_argument("--cam_ref", type=float, default=0.586)
ap.add_argument("--meas_dt", type=float, default=0.5)
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--tuck", type=int, default=1, help="1 = 四折後側板收耳(預設);0 = 不收耳(等同 --squeeze_t 0)")
ap.add_argument("--grasp", type=int, default=0, help="1 = 開蓋 hold 之後同一次模擬續跑:挑角 → 夾 → 沿弧線掀 yn(再掀 yp)")
ap.add_argument("--grasp_rank", type=int, default=1, help="yn 片用排名第幾的抓取點")
ap.add_argument("--pick_mm", type=float, default=25.0, help="挑角:單指伸進 25mm 後往上抬幾 mm")
ap.add_argument("--pick_in_mm", type=float, default=25.0, help="挑角:單指沿 −u 伸進幾 mm")
ap.add_argument("--arc_k", type=float, default=0.9, help="掀:弧半徑 = arc_k x 夾點到彎折處的材料長度")
ap.add_argument("--peel_t", type=float, default=3.0, help="掀:弧線秒數")
ap.add_argument("--gap_mm", type=float, default=4.5, help="夾:指面間距")
ap.add_argument("--ffric", type=float, default=2.0, help="指面摩擦")
ap.add_argument("--second", type=int, default=1, help="1 = yn 掀完接著掀 yp(不論 yn 判定)")
ap.add_argument("--gcam_focal", type=float, default=2.8, help="抓取段相機 focal(Camera API 單位,x10 = mm)")
a = ap.parse_args()
if a.tuck == 0:
    a.squeeze_t = 0.0
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
os.makedirs(a.out, exist_ok=True)
T = a.thick_mm / 1e3
WX = (a.sheet_x_mm or a.sheet_mm) / 1e3; WY = (a.sheet_y_mm or a.sheet_mm) / 1e3
WA = (WX, WY)                      # 依軸取邊長
W = max(WX, WY)                    # 只用在側板起始位置等「夠大就好」的地方
MOVE = np.array([float(x) for x in a.movebox.split(",")])
FOLD_ORDER = ["xp", "xn", "yp", "yn"]          # [ws] 唯一來源:先左右、後前後(前後在外層)
UORDER = list(reversed(FOLD_ORDER))

def kv(s):
    d = {}
    for it in [x for x in s.split(",") if x]:
        k, v = it.split(":"); d[k] = float(v)
    return d
SLOW = kv(a.slow); TIPX = kv(a.tip_extra)

LOG = open(os.path.join(a.out, "wrap_vol.log"), "w")
def P(*s):
    m = " ".join(str(x) for x in s); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()

os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from isaacsim.core.prims import SingleXFormPrim
from isaacsim.sensors.camera import Camera
from pxr import Usd, Gf, Sdf, UsdGeom, UsdPhysics, UsdShade, UsdLux, PhysxSchema, Vt
import omni.usd, imageio, trimesh
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, HERE)
import volcommon as VC
import vol_pen as VP
import grip_common as G
import layer_gap as LG

P("=== wrap_vol sheet %.0f ===" % a.sheet_mm); P("args:", vars(a))
world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
for at, v in [("CreateGpuCollisionStackSizeAttr", 128*1024*1024),
              ("CreateGpuFoundLostAggregatePairsCapacityAttr", 8192)]:
    try: getattr(pxs, at)(v)
    except Exception: pass

# ── 材質 [ws] ─────────────────────────────────────────────────────────
def vmat(path, col, op, rough=.25, ior=None):
    m = UsdShade.Material.Define(st, path); s = UsdShade.Shader.Define(st, path + "/S")
    s.CreateIdAttr("UsdPreviewSurface")
    s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*col))
    s.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    s.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(op)
    s.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(ior if ior is not None else (1.0 if op < 0.99 else 1.5))
    m.CreateSurfaceOutput().ConnectToSource(s.ConnectableAPI(), "surface"); return m

def film_tex(path, tex):
    m = UsdShade.Material.Define(st, path)
    sh = UsdShade.Shader.Define(st, path + "/S"); sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.90, .95, .97))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.18)
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
    sh.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.0)
    st_r = UsdShade.Shader.Define(st, path + "/st"); st_r.CreateIdAttr("UsdPrimvarReader_float2")
    st_r.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    st_r.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    nt = UsdShade.Shader.Define(st, path + "/nrm"); nt.CreateIdAttr("UsdUVTexture")
    nt.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(tex)
    nt.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_r.ConnectableAPI(), "result")
    nt.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(2, 2, 2, 1))
    nt.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(-1, -1, -1, 0))
    nt.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
    nt.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
    nt.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    sh.CreateInput("normal", Sdf.ValueTypeNames.Normal3f).ConnectToSource(nt.ConnectableAPI(), "rgb")
    m.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return m
FILM = film_tex("/World/film", os.path.abspath(a.tex))
MUGM = vmat("/World/mugm", (144/255./1.19*0.894, 163/255./1.11*0.931, 189/255./1.005), 1.0, .40)

# ── 杯子 [ws] ─────────────────────────────────────────────────────────
m_ = trimesh.load(a.mug)
V = np.asarray(m_.vertices, float); F = np.asarray(m_.faces)
unit = 0.001 if V.ptp(0).max() > 1.0 else 1.0
V = (V - V.mean(0)) * unit
Ry = lambda t: np.array([[np.cos(t), 0, np.sin(t)], [0, 1, 0], [-np.sin(t), 0, np.cos(t)]])
Rx = lambda t: np.array([[1, 0, 0], [0, np.cos(t), -np.sin(t)], [0, np.sin(t), np.cos(t)]])
Rz = lambda t: np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1]])
V = V @ Ry(-np.pi/2).T @ Rx(np.pi/2).T @ Rz(-np.pi/2).T      # 基準姿態:杯口 +y、杯耳 −x
_Rm = np.array([[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]])
V = V @ _Rm.T
V -= (V.max(0) + V.min(0)) / 2.0
ME = V.max(0) - V.min(0); hx, hy, H2 = ME / 2.0
MUG_VOL = float(np.prod(ME))
P("杯子躺平 %.0f x %.0f x %.0f mm;杯口 +y、杯耳 +x;watertight=%s" % (*(ME*1e3), m_.is_watertight))
A_, B_ = ME[0] + 2*a.margin, ME[1] + 2*a.margin
CX, CY = A_/2 + a.wall, B_/2 + a.wall
P("折線 CX=%.2f CY=%.2f mm;折邊長 x %.1f / y %.1f mm" % (CX*1e3, CY*1e3, (WX/2-CX)*1e3, (WY/2-CY)*1e3))

# ── 板 ───────────────────────────────────────────────────────────────
ZB = 0.001
REST_NPZ = None
if a.rest_npz:
    REST_NPZ = np.load(a.rest_npz)["fold_end_tet"]
info = VC.build_plate(st, "/World/plate", WX, T, ZB, "manual", nxy=a.nxy, nz=1, youngs=a.young, poisson=a.poisson,
                      areal=a.areal, fric=a.fric, cont=a.cont, rest=a.rest, solver=a.solver, self_coll=True,
                      self_filter=2*a.rest, P=P, size_y=WY)
PLATE = VC.Mesh(st, "/World/plate")
FLAT = PLATE.pts().copy(); TETS = PLATE.tets()
N1 = (a.nxy + 1) ** 2
assert len(FLAT) == 2 * N1
BOT, TOP = np.arange(N1), np.arange(N1, 2 * N1)
V0 = VP.tet_vol(FLAT, TETS)
EDG = np.unique(np.sort(np.concatenate([TETS[:, [i, j]] for i in range(4) for j in range(i + 1, 4)]), axis=1), axis=0)
L0 = np.linalg.norm(FLAT[EDG[:, 0]] - FLAT[EDG[:, 1]], axis=1)
if REST_NPZ is not None:
    assert len(REST_NPZ) == len(FLAT)
    PLATE.prim.GetAttribute("omniphysics:restShapePoints").Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in REST_NPZ]))
    V0 = VP.tet_vol(REST_NPZ, TETS)
    P("★ --rest_npz %s:restShapePoints = 折好的形狀(points 仍平);反轉以它為基準" % a.rest_npz)
UsdGeom.Imageable(PLATE.prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
P("板 %.0fx%.0fx%.0fmm:%d 點 %d tets;dxy %.2fmm;solver %d dt 1/%.0f" % (WX*1e3, WY*1e3, T*1e3, len(FLAT), len(TETS),
                                                                   WX/a.nxy*1e3, a.solver, 1/a.dt))

# 視覺網格(外表面三角形),每個渲染幀寫入 sim 頂點
n = a.nxy
gid = lambda i, j, k: k * N1 + j * (n + 1) + i
VF = []
for j in range(n):
    for i in range(n):
        VF += [(gid(i, j, 1), gid(i+1, j, 1), gid(i+1, j+1, 1)), (gid(i, j, 1), gid(i+1, j+1, 1), gid(i, j+1, 1))]
        VF += [(gid(i, j, 0), gid(i+1, j+1, 0), gid(i+1, j, 0)), (gid(i, j, 0), gid(i, j+1, 0), gid(i+1, j+1, 0))]
for s_ in range(n):
    for (p0, p1) in [((s_, 0), (s_+1, 0)), ((n, s_), (n, s_+1)), ((s_+1, n), (s_, n)), ((0, s_+1), (0, s_))]:
        a0, a1 = gid(*p0, 0), gid(*p1, 0); b0, b1 = gid(*p0, 1), gid(*p1, 1)
        VF += [(a0, a1, b1), (a0, b1, b0)]
VF = np.array(VF, int)
vis = UsdGeom.Mesh.Define(st, "/World/sheet_vis")
vis.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in FLAT]))
vis.CreateFaceVertexCountsAttr([3] * len(VF)); vis.CreateFaceVertexIndicesAttr([int(x) for x in VF.ravel()])
vis.CreateSubdivisionSchemeAttr().Set("none"); vis.CreateDoubleSidedAttr(True)
_tl = a.tex_mm / 1000.0
UsdGeom.PrimvarsAPI(vis.GetPrim()).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex).Set(
    Vt.Vec2fArray([Gf.Vec2f(float(p[0]/_tl), float(p[1]/_tl)) for p in FLAT]))
UsdShade.MaterialBindingAPI.Apply(vis.GetPrim()).Bind(FILM)
VISPTS = vis.GetPointsAttr()
P("視覺網格 /World/sheet_vis:%d 三角形(上/下/側面),泡泡法線貼圖 %s" % (len(VF), a.tex))

# ── 杯子剛體 [ws] ───────────────────────────────────────────────────
PLATE_TOP0 = a.rest + T
MZ = PLATE_TOP0 + 0.002 + H2
MUGTOP = MZ + H2
mug = UsdGeom.Xform.Define(st, "/World/mug")
UsdGeom.Xformable(mug).AddTranslateOp().Set(Gf.Vec3d(0, 0, MZ))
UsdPhysics.RigidBodyAPI.Apply(mug.GetPrim()).CreateKinematicEnabledAttr(True)
prb = PhysxSchema.PhysxRigidBodyAPI.Apply(mug.GetPrim())
prb.CreateLinearDampingAttr(0.3); prb.CreateAngularDampingAttr(0.6)
UsdPhysics.MassAPI.Apply(mug.GetPrim()).CreateMassAttr(0.0807)
g = UsdGeom.Mesh.Define(st, "/World/mug/geo")
g.CreatePointsAttr([Gf.Vec3f(*map(float, p)) for p in V])
g.CreateFaceVertexIndicesAttr([int(i) for f in F for i in f])
g.CreateFaceVertexCountsAttr([3]*len(F)); g.CreateSubdivisionSchemeAttr().Set("none")
g.CreateDoubleSidedAttr(True)
UsdPhysics.CollisionAPI.Apply(g.GetPrim())
UsdPhysics.MeshCollisionAPI.Apply(g.GetPrim()).CreateApproximationAttr("convexDecomposition")
gc = PhysxSchema.PhysxCollisionAPI.Apply(g.GetPrim())
gc.CreateContactOffsetAttr(0.004); gc.CreateRestOffsetAttr(0.001)
UsdShade.MaterialBindingAPI.Apply(g.GetPrim()).Bind(MUGM)
MTRI = trimesh.Trimesh(V, F, process=False)
P("杯子 kinematic,底 z=%.1f 頂 z=%.1f mm" % ((MZ-H2)*1e3, MUGTOP*1e3))

# ── 折疊錨(每邊一根 kinematic 桿,無碰撞;VtxXformAttachment 綁該邊最外圈上下兩層)────
DXY = (WX / a.nxy, WY / a.nxy)
fx_, fy_ = FLAT[:, 0], FLAT[:, 1]
def sidepick(fx, fy):
    """[ws] SIDEPICK:以『超出折線多少』分邊,角落歸較大者(x 長邊 ⇒ 角落歸 y)。"""
    sx = max(0.0, abs(fx) - CX); sy = max(0.0, abs(fy) - CY)
    return ("yp" if fy > 0 else "yn") if sy >= sx else ("xp" if fx > 0 else "xn")
Z0 = a.rest + T / 2
SIDES = {}
for sd in FOLD_ORDER:
    ax = 0 if sd[0] == "x" else 1; sg = 1.0 if sd[1] == "p" else -1.0
    C = CX if ax == 0 else CY
    outer = np.abs(FLAT[:, ax] - sg * WA[ax] / 2) < 1e-6
    picked = np.array([v for v in np.where(outer)[0] if sidepick(fx_[v], fy_[v]) == sd])
    if sd in FOLD_ORDER[:2]:
        # 先折的兩邊:整條邊,不含角落(角落 SIDEPICK 歸 y)
        # 先折的兩邊:SIDEPICK 歸本邊的最外圈,再只留 |y| <= CY(杯子 y 範圍 + margin + wall)。
        # ★ 實測(out_v400_fold 第 1、2 版):照 SIDEPICK 抓到 |y|<=177 時,4mm 板的 x 折邊兩端(角落區)被桿釘在
        #   y=±177 的杯頂上,入箱前 y 超出內腔(±112)163~497 點;內腔 224mm 根本放不下 ±177 的錨點。
        vids = picked[np.abs(FLAT[picked, 1 - ax]) <= (CY if ax == 0 else CX) + 1e-6]
    else:
        # 後折的兩邊:只抓前兩折期間仍貼地的那段(|另一軸| <= 對方折線),等同 surface 版 floor_edges
        Co = CX if ax == 1 else CY
        vids = picked[np.abs(FLAT[picked, 1 - ax]) <= Co - 0.25 * DXY[1 - ax]]
    SIDES[sd] = dict(ax=ax, sg=sg, C=C, R=WA[ax]/2 - C, vids=vids, k=FOLD_ORDER.index(sd))
    P("錨 %s:最外圈 %d 點中 SIDEPICK 歸本邊 %d,綁 %d 點(上下兩層)" % (sd, int(outer.sum()), len(picked), len(vids)))

# 終點:尖端底面停在 杯頂 + 已疊層數 x (T+1mm) + 2mm;已疊層數 = 先前折的 flap 頂面範圍與本折重疊者
def plan_ends():
    for sd in FOLD_ORDER:
        S_ = SIDES[sd]
        prev = FOLD_ORDER[:S_["k"]]
        other = [pd for pd in prev if SIDES[pd]["ax"] != S_["ax"]]
        same = [pd for pd in prev if SIDES[pd]["ax"] == S_["ax"]]
        lay = 0
        if other:      # 另一軸先折的片在下面:兩片各佔一側,彼此重疊(尖端越過中線)才算兩層
            lay += 1
            if len(other) == 2 and SIDES[other[0]].get("along_end", 1) + SIDES[other[1]].get("along_end", 1) < 0:
                lay += 1
        for pd in same:
            if SIDES[pd]["along_end"] + S_.get("along_end", S_["C"]) < 0:
                lay += 1
        S_["lay"] = lay
        S_["zend"] = MUGTOP + lay * (T + 0.001) + 0.002 + T / 2 + TIPX.get(sd, TIPX.get("all", 0.0)) / 1e3
        S_["arm"] = S_["R"] - (S_["zend"] - Z0)
        S_["along_end"] = max(-a.tip_over_mm / 1e3, S_["C"] - S_["arm"])
plan_ends(); plan_ends()
for sd in FOLD_ORDER:
    S_ = SIDES[sd]
    P("  %s:折線 %.1f、折邊 %.1f、已疊 %d 層 → 尖端中面 z=%.1f(底面 %.1f)、越過頂面 arm %.1f → 尖端 along=%.1f mm%s"
      % (sd, S_["C"]*1e3, S_["R"]*1e3, S_["lay"], S_["zend"]*1e3, (S_["zend"]-T/2)*1e3, S_["arm"]*1e3,
         S_["along_end"]*1e3, "(搆不到中線)" if S_["along_end"] > 0.001 else "(到/越過中線)"))

UsdGeom.Xform.Define(st, "/World/bars")
def qaxis(axis, ang):
    axis = np.asarray(axis, float); axis /= np.linalg.norm(axis)
    return np.array([np.cos(ang/2), *(np.sin(ang/2) * axis)])
def qmul(p, q):
    w1, x1, y1, z1 = p; w2, x2, y2, z2 = q
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2, w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])
QI = np.array([1.0, 0, 0, 0])

def xmap(S_, s, u):
    """[ws wrap_arc_from 改寫] 折邊上離折線 s 的點,在折疊進度 u 時的 (along, z, 轉角)。
    A 段 繞底部折線 (C,Z0) 轉 90°;B 段 立起高度 H=zend-Z0 以內停在側面,超過的部分繞頂部折線 (C,zend) 再轉 90°。
    s = R 就是邊緣(桿)。半徑都 = 該點到折線的材料長度 ⇒ 不拉伸。"""
    C, ze = S_["C"], S_["zend"]; H = ze - Z0
    if u <= 0.5:
        th = np.pi * u
        return C + s*np.cos(th), Z0 + s*np.sin(th), th
    ps = np.pi * (u - 0.5)
    if s <= H:
        return C, Z0 + s, np.pi/2
    h = s - H
    return max(-a.tip_over_mm/1e3, C - h*np.sin(ps)), ze + h*np.cos(ps), np.pi/2 + ps

def yarc(S_, cur, u):
    """[ws wrap_arc_from] 後折的錨從**它當下的位置**起弧:A 段繞底部折線把它轉到正上方(半徑 = 當下到折線距離),
    B 段繞頂部折線 (C,zend) 蓋過去。回傳 (along, z, 本折累計轉角)。"""
    C, ze = S_["C"], S_["zend"]
    a0 = S_["sg"]*cur[S_["ax"]] - C; z0 = cur[2] - Z0
    Rv = float(np.hypot(max(a0, 1e-6), z0)); th0 = float(np.arctan2(z0, max(a0, 1e-6)))
    if u <= 0.5:
        th = th0 + (np.pi/2 - th0)*(u/0.5)
        return C + Rv*np.cos(th), Z0 + Rv*np.sin(th), th - th0
    ps = np.pi * (u - 0.5); h0 = Z0 + Rv - ze
    return max(-a.tip_over_mm/1e3, C - h0*np.sin(ps)), ze + h0*np.cos(ps), np.pi/2 - th0 + ps

ANC = []          # 每個 kinematic 錨:x 邊一根桿;y 邊每一欄一個(上下兩點)
for sd, S_ in SIDES.items():
    if S_["ax"] == 0:
        ctr = np.zeros(3); ctr[0] = S_["sg"] * WX / 2; ctr[2] = Z0
        groups = [(sd, ctr, S_["vids"])]
    else:
        groups = []
        cols = np.unique(np.round(FLAT[S_["vids"], 0], 6))
        for ci, cx_ in enumerate(cols):
            vv = S_["vids"][np.abs(FLAT[S_["vids"], 0] - cx_) < 1e-6]
            groups.append(("%s_c%02d" % (sd, ci), np.array([cx_, S_["sg"] * WY / 2, Z0]), vv))
    for nm_, ctr, vv in groups:
        pth = "/World/bars/" + nm_
        VC.kin_box(st, pth, [0.004, 0.004, 0.004], ctr, collide=False, visible=False)
        sc = "/World/attach/" + nm_
        VC.attach_vtx(st, sc, "/World/plate", "/World/plate", pth, vv, FLAT[vv] - ctr, P=lambda *x: None)
        ANC.append(dict(nm=nm_, side=sd, path=pth, scope=sc, c0=ctr, vids=vv))
P("錨:%d 個 kinematic 錨體(x 邊各 1 根桿;y 邊每欄 1 個,共 %d 欄),全部無碰撞;VtxXformAttachment 掛 /World/attach/*"
  % (len(ANC), sum(1 for A in ANC if A["side"][0] == "y")))

def anchor_pose(A, t):
    sd = A["side"]; S_ = SIDES[sd]
    if S_["ax"] == 0:
        t0, sp_ = FT[sd]; u = ss((t - t0)/sp_)
        al, z, ang = xmap(S_, S_["R"], u)
        p = np.array([S_["sg"]*al, 0.0, z])
        return p, qaxis([0, -S_["sg"], 0], ang)
    # y 邊的一欄:先跟著 x 折(若這欄在 x 折邊上 = 角落『耳朵』),再做自己的 y 折
    cx_ = A["c0"][0]
    sdx = "xp" if cx_ > 0 else "xn"; Sx = SIDES[sdx]
    s = abs(cx_) - CX
    def xstate(tt):
        if s <= 0: return np.array([cx_, A["c0"][1], Z0]), QI
        t0x, spx = FT[sdx]; ux = ss((tt - t0x)/spx)
        al, z, ang = xmap(Sx, s, ux)
        return np.array([Sx["sg"]*al, A["c0"][1], z]), qaxis([0, -Sx["sg"], 0], ang)
    t0, sp_ = FT[sd]
    if t < t0:
        return xstate(t)
    if "ystart" not in A:
        A["ystart"] = xstate(t0)
    cur, qx = A["ystart"]
    u = ss((t - t0)/sp_)
    al, z, ang = yarc(S_, cur, u)
    p = np.array([cur[0], S_["sg"]*al, z])
    return p, qmul(qaxis([S_["sg"], 0, 0], ang), qx)

# ── 收耳朵用的四面側板(kinematic、不可見):四折完從外面收到紙箱內腔 −squeeze_mm ────
PADS = []
PAD_H = 0.16
for nm_, ax_, sg_ in (("pxp", 0, 1), ("pxn", 0, -1), ("pyp", 1, 1), ("pyn", 1, -1)):
    sz = [W + 0.12, W + 0.12, PAD_H]; sz[ax_] = 0.010
    c_ = np.zeros(3); c_[ax_] = sg_ * (W/2 + 0.03 + 0.005); c_[2] = PAD_H/2 + 0.0005
    pr_ = VC.kin_box(st, "/World/pads/" + nm_, sz, c_, collide=True, visible=False)
    _pc = PhysxSchema.PhysxCollisionAPI.Apply(st.GetPrimAtPath("/World/pads/%s/geom" % nm_))
    _pc.CreateContactOffsetAttr(0.002); _pc.CreateRestOffsetAttr(0.0005)
    PADS.append(dict(nm=nm_, ax=ax_, sg=sg_, c0=c_, path="/World/pads/" + nm_))

# ── 紙箱 [ws] ────────────────────────────────────────────────────────
_bx = st.DefinePrim("/World/Box", "Xform")
_bx.GetReferences().AddReference(os.path.abspath(a.carton))
_nk = 0
for _p in Usd.PrimRange(_bx):
    if _p.HasAPI(UsdPhysics.RigidBodyAPI):
        _at = _p.GetAttribute("physics:kinematicEnabled")
        (_at if _at and _at.IsValid() else _p.CreateAttribute("physics:kinematicEnabled", Sdf.ValueTypeNames.Bool)).Set(True)
        _nk += 1
_CB = vmat("/World/cartonmat", (0.62, 0.46, 0.29), 1.0, 0.85)
for _p in Usd.PrimRange(_bx):
    if _p.IsA(UsdGeom.Gprim):
        UsdShade.MaterialBindingAPI.Apply(_p).Bind(_CB, UsdShade.Tokens.strongerThanDescendants)
UsdShade.MaterialBindingAPI.Apply(_bx).Bind(_CB, UsdShade.Tokens.strongerThanDescendants)
_rr = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(_bx).ComputeAlignedRange()
CDZ = float(_rr.GetMin()[2]) + 0.003            # 箱底內面(箱子在原點時)
ZHI0 = float(_rr.GetMax()[2])                   # 箱口(含關著的蓋)最高點
BOXC = np.array([(_rr.GetMin()[0]+_rr.GetMax()[0])/2, (_rr.GetMin()[1]+_rr.GetMax()[1])/2])
_mj = os.path.splitext(os.path.abspath(a.carton))[0] + ".meta.json"
_dv = json.load(open(_mj))["derived"]
CBOX = dict(ix=float(_dv["wall_inner_x"]), iy=float(_dv["wall_inner_y"]), top=float(_dv["wall_top_x"]),
            top_y=float(_dv["wall_top_y"]), hz_lo=float(_dv["lower_hinge_z"]), hz_up=float(_dv["upper_hinge_z"]))
P("★ 紙箱 %s(meta %s):%d 剛體 kinematic;bbox %.0fx%.0fx%.0f;箱底內面 z=%.1f、箱口最高 %.1f;內腔 ±%.0f x ±%.0f;鉸鏈 %.1f/%.1f"
  % (a.carton, os.path.basename(_mj), _nk, *((np.array(_rr.GetMax())-np.array(_rr.GetMin()))*1e3), CDZ*1e3, ZHI0*1e3,
     CBOX["ix"]*1e3, CBOX["iy"]*1e3, CBOX["hz_lo"]*1e3, CBOX["hz_up"]*1e3))
if a.base_collider_pad > 0:
    _bt = st.GetPrimAtPath("/World/Box/base/bottom")
    _br = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(
        _bt if _bt.IsValid() else st.GetPrimAtPath("/World/Box/base")).ComputeAlignedRange()
    _lo, _hi = np.array(_br.GetMin()), np.array(_br.GetMax())
    _ctr = np.array([(_lo[0]+_hi[0])/2, (_lo[1]+_hi[1])/2, _lo[2] - a.base_collider_pad/2])
    _pad = UsdGeom.Cube.Define(st, "/World/Box/base/pad_collider"); _pad.CreateSizeAttr(1.0)
    _Wb = UsdGeom.Xformable(st.GetPrimAtPath("/World/Box/base")).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    _pxx = UsdGeom.Xformable(_pad)
    _pxx.AddTranslateOp().Set(_Wb.GetInverse().Transform(Gf.Vec3d(*map(float, _ctr))))
    _pxx.AddScaleOp().Set(Gf.Vec3f(float(_hi[0]-_lo[0]), float(_hi[1]-_lo[1]), float(a.base_collider_pad)))
    UsdPhysics.CollisionAPI.Apply(_pad.GetPrim()); _pad.CreatePurposeAttr(UsdGeom.Tokens.guide)
    P("★ 底板碰撞加厚 %.0fmm(不可見)" % (a.base_collider_pad*1e3))

def _rodr(v, h, ax, deg):
    ax = np.asarray(ax, float)/np.linalg.norm(ax); th = np.radians(deg); r = np.asarray(v, float) - h
    return h + r*np.cos(th) + np.cross(ax, r)*np.sin(th) + ax*np.dot(ax, r)*(1.0 - np.cos(th))
LIDS = []
_hx, _hy = CBOX["ix"], CBOX["iy"]
for nm, hinge, axis, order in (("fxp", (_hx, 0.0, CBOX["hz_lo"]), (0.0, 1.0, 0.0), 0),
                               ("fxn", (-_hx, 0.0, CBOX["hz_lo"]), (0.0, -1.0, 0.0), 0),
                               ("fyp", (0.0, _hy, CBOX["hz_up"]), (-1.0, 0.0, 0.0), 1),
                               ("fyn", (0.0, -_hy, CBOX["hz_up"]), (1.0, 0.0, 0.0), 1)):
    pr = st.GetPrimAtPath("/World/Box/" + nm)
    L = dict(nm=nm, h=np.array(hinge), ax=np.array(axis), order=order,
             T0=Gf.Matrix4d(UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(Usd.TimeCode.Default())))
    _r = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(pr).ComputeAlignedRange()
    _c = (np.array(_r.GetMin()) + np.array(_r.GetMax()))/2.0
    L["sgn"] = 1.0 if _rodr(_c, L["h"], L["ax"], 90)[2] >= _rodr(_c, L["h"], L["ax"], -90)[2] else -1.0
    L["rest_closed"] = bool(np.linalg.norm(_c[:2]) < np.linalg.norm(L["h"][:2]))
    L["c_loc"] = L["T0"].GetInverse().Transform(Gf.Vec3d(*map(float, _c)))
    L["cz0"] = _c[2]
    L["zmin0"] = float(_r.GetMin()[2])        # 關著時蓋子底面(箱子在原點)
    LIDS.append(L)
    P("  蓋 %s:USD 預設中心 z=%.1f → %s;開 = 轉 %s180°" % (nm, _c[2]*1e3, "關" if L["rest_closed"] else "開",
                                                        "+" if L["sgn"] > 0 else "−"))
BASE_T0 = Gf.Matrix4d(UsdGeom.Xformable(st.GetPrimAtPath("/World/Box/base")).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))

def lid_M(L, deg):
    h = Gf.Vec3d(*[float(x) for x in L["h"]])
    return (Gf.Matrix4d().SetTranslate(-h) * Gf.Matrix4d().SetRotate(
        Gf.Rotation(Gf.Vec3d(*[float(x) for x in L["ax"]]), float(deg)*L["sgn"])) * Gf.Matrix4d().SetTranslate(h))
def lid_pose(L, deg, off):
    Wm = L["T0"] * lid_M(L, deg)
    q = Wm.ExtractRotationQuat()
    return (np.array([float(x) for x in Wm.ExtractTranslation()]) + off,
            np.array([float(q.GetReal()), *[float(x) for x in q.GetImaginary()]]))
OFF_SIDE = np.array([-0.80, 0.45, -CDZ])
# reset 前:箱子擺到旁邊、蓋子擺開(180°)[ws「reset 前」]
for pth, Wm in [("/World/Box/base", BASE_T0)] + [("/World/Box/" + L["nm"], L["T0"] * lid_M(L, 180.0)) for L in LIDS]:
    _pr = st.GetPrimAtPath(pth)
    _Wm2 = Wm * Gf.Matrix4d().SetTranslate(Gf.Vec3d(*map(float, OFF_SIDE)))
    _par = UsdGeom.Xformable(_pr.GetParent()).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    _xf = UsdGeom.Xformable(_pr); _xf.ClearXformOpOrder(); _xf.AddTransformOp().Set(_Wm2 * _par.GetInverse())
P("★ 紙箱 reset 前擺到旁邊 %s mm、蓋子開(180°);箱底內面對齊地面(z 偏 −%.1fmm)" % (np.round(OFF_SIDE*1e3), CDZ*1e3))

# ── 抓取段的 kinematic 指(--grasp 1):挑角單指 rod + 平行夾爪上/下指;實體不可見,另放純視覺方塊 ──
if a.grasp:
    sys.path.insert(0, os.path.join(HERE, "grip"))
    import gutil as GU
    GFS = np.array([0.020, 0.020, 0.008])        # 指面 (t,u,n)
    GRS = np.array([0.008, 0.030, 0.008])        # 挑角單指(8mm 方桿,沿 u 30mm)
    GPARK = {"rod": np.array([3.0, 3.0, 1.0]), "up": np.array([3.0, 3.1, 1.0]), "lo": np.array([3.0, 3.2, 1.0])}
    GPATH = {k: "/World/gfing/" + k for k in GPARK}
    GVIS = {}
    for k_ in GPARK:
        GU.finger(st, GPATH[k_], GRS if k_ == "rod" else GFS, GPARK[k_], 0.5 if k_ == "rod" else a.ffric, cont=0.001, rest=0.0)
        UsdGeom.Imageable(st.GetPrimAtPath(GPATH[k_])).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
        GVIS[k_] = GU.VisBox(st, "/World/gvis_" + k_, GRS if k_ == "rod" else GFS,
                             (0.2, 0.7, 0.25) if k_ == "rod" else (0.9, 0.45, 0.1))
        GVIS[k_].set(GPARK[k_])
    P("★ --grasp 1:kinematic 指 rod %s / 上下指 %s mm,指面摩擦 %.1f(rod 0.5),cont 1 / rest 0;停在 %s"
      % (GRS*1e3, GFS*1e3, a.ffric, GPARK["rod"]))

# ── 相機 / 燈 [ws] ───────────────────────────────────────────────────
FPS = a.fps
cam = Camera(prim_path="/World/cam", resolution=(1280, 720))
cam.set_focal_length(4.0)
_gl = st.GetPrimAtPath("/World/defaultGroundPlane/SphereLight")
if _gl.IsValid():
    _ga = _gl.GetAttribute("inputs:intensity")
    if _ga and _ga.IsValid(): _ga.Set(_ga.Get()/12.0)
_cr = a.cam_ref
EYE_F = [_cr*1.5, -_cr*1.6, _cr*0.9]; TGT_F = [0, 0, 0]
G.look(cam, EYE_F, TGT_F)
G.add_headlight(st, EYE_F, TGT_F, intensity=245.0, name="hl1")
G.add_headlight(st, [-.5, -.5, .8], TGT_F, intensity=135.0, name="hl2")
UsdLux.DomeLight.Define(st, "/World/dome").CreateIntensityAttr(2600.0)
_dl = UsdLux.DistantLight.Define(st, "/World/toplight")
UsdGeom.Xformable(_dl).AddRotateXYZOp().Set(Gf.Vec3f(-70.0, 0.0, 25.0)); _dl.CreateIntensityAttr(0.0); _dl.CreateAngleAttr(2.0)
_dl2 = UsdLux.DistantLight.Define(st, "/World/toplight2")
UsdGeom.Xformable(_dl2).AddRotateXYZOp().Set(Gf.Vec3f(-90.0, 0.0, 0.0)); _dl2.CreateIntensityAttr(0.0); _dl2.CreateAngleAttr(4.0)

world.reset(); cam.initialize()
for k_ in range(3):
    sim.update()
ANCV = world.physics_sim_view.create_rigid_body_view([A["path"] for A in ANC])
_vp = list(ANCV.prim_paths); _pi = {A["path"]: i_ for i_, A in enumerate(ANC)}
ANC_ORD = np.array([_pi[p_] for p_ in _vp]); ANC_IDX = np.arange(ANCV.count, dtype=np.int32)
P("錨 rigid body view:%d 個(kinematic target)" % ANCV.count)
base_x = SingleXFormPrim("/World/Box/base", name="boxbase")
for L in LIDS:
    L["prim"] = SingleXFormPrim("/World/Box/" + L["nm"], name="lid_" + L["nm"])
_bp, _bq = BASE_T0.ExtractTranslation(), BASE_T0.ExtractRotationQuat()
BASE_P0 = np.array([float(x) for x in _bp]); BASE_Q0 = np.array([float(_bq.GetReal()), *[float(x) for x in _bq.GetImaginary()]])
mugx = SingleXFormPrim("/World/mug", name="mugx")
for q_ in PADS:
    q_["x"] = SingleXFormPrim(q_["path"], name=q_["nm"])
BOXV = world.physics_sim_view.create_rigid_body_view(["/World/Box/base"] + ["/World/Box/" + L["nm"] for L in LIDS])
kin = st.GetPrimAtPath("/World/mug").GetAttribute("physics:kinematicEnabled")
if a.grasp:
    GKEYS = list(GPARK)
    GFV = world.physics_sim_view.create_rigid_body_view([GPATH[k_] for k_ in GKEYS])
    _gpi = {GPATH[k_]: i_ for i_, k_ in enumerate(GKEYS)}
    GF_ORD = np.array([_gpi[p_] for p_ in GFV.prim_paths]); GF_IDX = np.arange(GFV.count, dtype=np.int32)
    P("抓取指 rigid body view:%d 個" % GFV.count)

# ── 時間表 ───────────────────────────────────────────────────────────
T_SET = 0.5
FT = {}
t_ = T_SET
for sd in FOLD_ORDER:
    sp_ = a.fold_span * SLOW.get(sd, 1.0)
    FT[sd] = (t_, sp_); t_ += sp_ + a.fold_hold
T_FOLD_END = t_
T_SQ0 = T_FOLD_END
T_SQ1 = T_SQ0 + a.squeeze_t
T_INBOX = T_SQ1 + (0.5 if a.squeeze_t > 0 else 0.0)
T_LID0 = T_INBOX + 1.0
T_LID1 = T_LID0 + a.lid_span
T_REL = T_LID1 + a.lid_span            # 蓋子關好 → 側板外撤 0.3s
T_ANC = T_REL + 0.4                     # 放錨點 + 杯子轉 dynamic
T_MOVE0 = T_ANC + 2.0
T_MOVE1 = T_MOVE0 + a.move_t
T_OPEN0 = T_MOVE1 + 2.0
T_OPEN1 = T_OPEN0 + a.open_span
T_OPEN2 = T_OPEN1 + a.open_span
T_END_ALL = T_OPEN2 + 3.0
T_END = {"fold": T_INBOX + 0.6, "box": T_MOVE0, "move": T_OPEN0, "all": T_END_ALL}[a.until]
# 抓取段時間表(相對每片的 S0;yn 在 open hold 完 + settle 1s 開始)
GT = dict(rod_above=1.0, rod_down=1.0, rod_in=1.0, rod_lift=1.0, pick_hold=0.5, lo_above=0.8, lo_down=0.8, lo_in=1.0,
          rod_out=0.6, rod_up=0.5, up_above=0.8, up_down=0.7, close=0.8, grip_hold=0.3, peel_hold=2.0, rel_open=0.5, rel_slide=0.5, rel_up=0.7)
G_TPICK = GT["rod_above"] + GT["rod_down"] + GT["rod_in"] + GT["rod_lift"] + GT["pick_hold"]            # 4.5
G_TLOIN = G_TPICK + GT["lo_above"] + GT["lo_down"] + GT["lo_in"]                                        # 7.1
G_TGRIP = G_TLOIN + GT["up_above"] + GT["up_down"] + GT["close"] + GT["grip_hold"]                      # 9.7
G_SHEET = G_TGRIP + a.peel_t + GT["peel_hold"] + GT["rel_open"] + GT["rel_slide"] + GT["rel_up"] + 0.3
G_SEQ = (["yn", "yp"] if a.second else ["yn"]) if a.grasp else []
TG0 = T_END_ALL + 1.0
if a.grasp and a.until == "all":
    T_END = TG0 + G_SHEET * len(G_SEQ)
    P("抓取段:open hold 完 %.2f → settle → %s 每片 %.1fs(挑角 0~%.1f、下指進 ~%.1f、夾好 %.1f、掀 %.1fs、停 %.1fs、放開);結束 %.2f"
      % (T_END_ALL, " / ".join("%s@%.2f" % (sd, TG0 + k_*G_SHEET) for k_, sd in enumerate(G_SEQ)), G_SHEET, G_TPICK, G_TLOIN,
         G_TGRIP, a.peel_t, GT["peel_hold"], T_END))
P("時間表:折 %s | 折完 %.2f | 入箱 %.2f | 關下蓋 %.2f | 關上蓋 %.2f | 放錨+杯動態 %.2f | 搬 %.2f~%.2f | 開上蓋 %.2f | 開下蓋 %.2f | 結束 %.2f(本次跑到 %.2f)"
  % (" ".join("%s@%.1f(%.1fs)" % (k, *v) for k, v in FT.items()), T_FOLD_END, T_INBOX, T_LID0, T_LID1, T_REL,
     T_MOVE0, T_MOVE1, T_OPEN0, T_OPEN1, T_END_ALL, T_END))
ss = lambda u: (lambda v: v*v*(3-2*v))(min(max(u, 0.), 1.))

def phase(t):
    if t < T_SET: return "settle"
    for sd in FOLD_ORDER:
        t0, sp_ = FT[sd]
        if t < t0 + sp_ + a.fold_hold: return "fold " + sd
    if t < T_INBOX: return "tuck ears (side squeeze)"
    if t < T_LID0: return "into box"
    if t < T_LID1: return "close lower lids"
    if t < T_REL: return "close upper lids"
    if t < T_ANC: return "release paddles"
    if t < T_MOVE0: return "release anchors / settle"
    if t < T_MOVE1: return "move box"
    if t < T_OPEN0: return "settle"
    if t < T_OPEN1: return "open upper lids"
    if t < T_OPEN2: return "open lower lids"
    if t < T_END_ALL or not a.grasp: return "hold"
    if t < TG0: return "grasp settle"
    k_ = min(int((t - TG0) // G_SHEET), len(G_SEQ) - 1); sd = G_SEQ[k_]; r_ = t - TG0 - k_ * G_SHEET
    for nm_, tt_ in [("pick: rod to corner", GT["rod_above"] + GT["rod_down"]), ("pick: rod insert", GT["rod_above"] + GT["rod_down"] + GT["rod_in"]),
                     ("pick: lift corner", G_TPICK), ("lower finger in", G_TLOIN), ("close gripper", G_TGRIP),
                     ("PEEL arc", G_TGRIP + a.peel_t), ("hold peeled", G_TGRIP + a.peel_t + GT["peel_hold"])]:
        if r_ < tt_: return "%s %s" % (sd, nm_)
    return "%s release" % sd

ST = dict(inbox=False, released=False, OFF_IN=None)
def box_off(t):
    if not ST["inbox"]: return OFF_SIDE
    return ST["OFF_IN"] + MOVE * ss((t - T_MOVE0) / a.move_t)
def lid_deg(L, t):
    if not ST["inbox"]: return 180.0
    if t < T_OPEN0:
        t0 = T_LID0 if L["order"] == 0 else T_LID1
        return 180.0 * (1.0 - ss((t - t0) / a.lid_span))
    t0 = T_OPEN0 if L["order"] == 1 else T_OPEN1
    return 180.0 * ss((t - t0) / a.open_span)

def drive(t):
    if not ST["released"]:
        D = np.zeros((len(ANC), 7), np.float32)
        for i_, A in enumerate(ANC):
            p, q = anchor_pose(A, t)
            D[i_, :3] = p; D[i_, 3:6] = q[1:]; D[i_, 6] = q[0]
        ANCV.set_kinematic_targets(D[ANC_ORD], ANC_IDX)
    if a.squeeze_t > 0 and not ST.get("pads_gone") and t >= T_SQ0 - 0.1:
        lim = {0: CBOX["ix"] - a.squeeze_mm/1e3, 1: CBOX["iy"] - a.squeeze_mm/1e3}
        u = ss((t - T_SQ0)/a.squeeze_t)
        # ★ 第 4 版(out_v400 第 1 次全程):側板在入箱時就撤,4mm 板回彈 → 關下蓋時 y 端被擠到 y 牆頂上方,
        #   上蓋再把它夾在牆頂外(關蓋後 y 超 20 點,z 122~138)。改成側板留到上下蓋都關好才撤(往外退 40mm,分離方向)。
        back = 0.04 * ss((t - T_REL)/0.3)
        for q_ in PADS:
            d0 = abs(q_["c0"][q_["ax"]]); d1 = lim[q_["ax"]] + 0.005
            c_ = q_["c0"].copy(); c_[q_["ax"]] = q_["sg"]*(d0 + (d1 - d0)*u + back)
            if t >= T_REL + 0.35:
                c_ = np.array([0, 0, -3.0]); ST["pads_gone"] = True
            q_["x"].set_world_pose(position=c_, orientation=QI)
    if ST["inbox"]:
        off = box_off(t)
        base_x.set_world_pose(position=BASE_P0 + off, orientation=BASE_Q0)
        for L in LIDS:
            p, q = lid_pose(L, lid_deg(L, t), off)
            L["prim"].set_world_pose(position=p, orientation=q)

# ── 量測 ─────────────────────────────────────────────────────────────
def mug_world():
    mp, mq = mugx.get_world_pose()
    w_, x_, y_, z_ = [float(v) for v in mq]
    Rq = np.array([[1-2*(y_*y_+z_*z_), 2*(x_*y_-z_*w_), 2*(x_*z_+y_*w_)],
                   [2*(x_*y_+z_*w_), 1-2*(x_*x_+z_*z_), 2*(y_*z_-x_*w_)],
                   [2*(x_*z_-y_*w_), 2*(y_*z_+x_*w_), 1-2*(x_*x_+y_*y_)]])
    return np.array(mp, float), Rq, V @ Rq.T + np.array(mp, float)

def sheet_in_mug(Pp, mp, Rq):
    loc = (Pp - mp) @ Rq                         # 世界 → 杯子局部
    lo, hi = V.min(0) - 0.002, V.max(0) + 0.002
    cand = np.where(((loc > lo) & (loc < hi)).all(1))[0]
    if not len(cand): return 0, cand
    ins = MTRI.contains(loc[cand])
    return int(ins.sum()), cand[ins]

IX, IY = CBOX["ix"], CBOX["iy"]
def inbox(nm, Q, off):
    """[ws inbox] 逐頂點比對內腔;off = 箱子目前位移(箱子在原點時的座標系 + off)。"""
    Q = Q - off
    ox = np.abs(Q[:, 0] - BOXC[0]) > IX; oy = np.abs(Q[:, 1] - BOXC[1]) > IY
    olo = Q[:, 2] < CDZ - 0.0005; ohi = Q[:, 2] > ZHI0
    bad = ox | oy | olo | ohi
    dlo = (CDZ - Q[olo, 2]).max()*1e3 if olo.any() else 0.0
    P("  %-4s %5d 點;超出內腔 %d | x 超 %d / y 超 %d / 低於底 %d(最深 %.2fmm)/ 高於口 %d | x %.1f~%.1f(±%.0f) y %.1f~%.1f(±%.0f) z %.1f~%.1f(%.1f~%.1f)"
      % (nm, len(Q), int(bad.sum()), int(ox.sum()), int(oy.sum()), int(olo.sum()), dlo, int(ohi.sum()),
         (Q[:, 0].min()-BOXC[0])*1e3, (Q[:, 0].max()-BOXC[0])*1e3, IX*1e3, (Q[:, 1].min()-BOXC[1])*1e3,
         (Q[:, 1].max()-BOXC[1])*1e3, IY*1e3, Q[:, 2].min()*1e3, Q[:, 2].max()*1e3, CDZ*1e3, ZHI0*1e3))
    return dict(n=int(bad.sum()), x=int(ox.sum()), y=int(oy.sum()), lo=int(olo.sum()), hi=int(ohi.sum()), dlo=dlo)

def lid_cz():
    return {L["nm"]: UsdGeom.Xformable(st.GetPrimAtPath("/World/Box/" + L["nm"])).ComputeLocalToWorldTransform(
        Usd.TimeCode.Default()).Transform(L["c_loc"])[2] for L in LIDS}

def layers(Pp, MW):
    mid = (Pp[BOT] + Pp[TOP]) / 2
    try:
        R = LG.measure(mid, MW, grid_mm=5.0, shrink_mm=15.0)
    except Exception as e:
        return None
    na = R["nabove"]
    try:
        R0 = LG.measure(mid, MW, grid_mm=5.0, shrink_mm=0.0)
        cov = float((R0["nabove"] >= 1).mean())
    except Exception:
        cov = float("nan")
    allg = np.concatenate([R["gaps"][k] for k in R["gaps"]]) if R["gaps"] else np.array([])
    return dict(nlay=float(np.median(na)), dist={int(u): int(c) for u, c in zip(*np.unique(na, return_counts=True))},
                gap=float(np.median(allg))*1e3 if len(allg) else float("nan"),
                top=float(np.median(R["thick"]))*1e3 + T/2*1e3 if len(R["thick"]) else float("nan"),
                first=float(np.median(R["first"]))*1e3 - T/2*1e3 if len(R["first"]) else float("nan"), cov=cov)

def measure(t, full=False):
    Pp = PLATE.pts()
    mp, Rq, MW = mug_world()
    r = dict(t=t, ph=phase(t))
    r["finite"] = bool(np.isfinite(Pp).all())
    r["bb"] = (Pp.max(0) - Pp.min(0)) * 1e3
    r["pen"], _ = VP.self_pen_count(Pp, TETS, FLAT)
    r["inmug"], _ = sheet_in_mug(Pp, mp, Rq)
    r["inv"], v = VC.inverted(Pp, TETS, V0)
    r["volr"] = v.sum() / V0.sum()
    Lr = np.linalg.norm(Pp[EDG[:, 0]] - Pp[EDG[:, 1]], axis=1) / L0
    r["lr"] = (Lr.min(), Lr.max())
    r["mug"] = mp
    allp = np.vstack([Pp, MW])
    r["pkg"] = (allp.max(0) - allp.min(0)) * 1e3
    r["pkgvol"] = float(np.prod(Pp.max(0) - Pp.min(0))) / MUG_VOL
    if full:
        r["lay"] = layers(Pp, MW)
    return r, Pp, MW

# ── 抓取段(--grasp 1)────────────────────────────────────────────────
if a.grasp:
    import grasp_plan as GPL
    from scipy.spatial.transform import Rotation as _Rot
    import itertools
    GPL.setup(FLAT, a.nxy, CX, CY, np.asarray(m_.faces), thick=T)
    GSIDE2 = GPL.S["SIDE2"]; GF2 = GPL.S["F2"]
    BOXL = dict(IX=IX, IY=IY, ZFLOOR=CDZ, ZOBST=max(CBOX["top"], CBOX["top_y"], CBOX["hz_up"]) + 0.005)
    GAPG = a.gap_mm / 1e3
    GF = {k_: dict(segs=[], last=(GPARK[k_].copy(), np.eye(3))) for k_ in GPARK}
    GS = dict(k=-1, plans=[], rows=[])
    def rq(Rm):
        x_, y_, z_, w_ = _Rot.from_matrix(Rm).as_quat(); return np.array([w_, x_, y_, z_])
    def rotm(axis, ang):
        return _Rot.from_rotvec(np.asarray(axis, float) / np.linalg.norm(axis) * ang).as_matrix()
    def g_lin(k_, t0, dur, pos, Rm=None):
        p0, R0_ = GF[k_]["last"]; R1 = R0_ if Rm is None else Rm
        p0 = np.array(p0, float); pos = np.array(pos, float)
        GF[k_]["segs"].append((t0, t0 + dur, lambda w, p0=p0, pos=pos, R1=R1: (p0 + (pos - p0) * w, R1)))
        GF[k_]["last"] = (pos, R1)
    def g_fn(k_, t0, dur, fn):
        GF[k_]["segs"].append((t0, t0 + dur, fn)); GF[k_]["last"] = fn(1.0)
    def g_pose(k_, t):
        cur = None
        for (t0, t1, fn) in GF[k_]["segs"]:
            if t >= t1: cur = fn(1.0)
            elif t >= t0: return fn(ss((t - t0) / (t1 - t0)))
            else: break
        return cur if cur is not None else (GPARK[k_], np.eye(3))
    def g_drive(t):
        D = np.zeros((len(GKEYS), 7), np.float32)
        for i_, k_ in enumerate(GKEYS):
            p_, R_ = g_pose(k_, t); q_ = rq(R_)
            D[i_, :3] = p_; D[i_, 3:6] = q_[1:]; D[i_, 6] = q_[0]
        GFV.set_kinematic_targets(D[GF_ORD], GF_IDX)
    def g_vis(t):
        for k_ in GKEYS:
            p_, R_ = g_pose(k_, t); GVIS[k_].set(p_, rq(R_))
    def g_offw():
        return box_off(T_END_ALL) + np.array([BOXC[0], BOXC[1], 0.0])
    def g_state():
        offw = g_offw(); Pw = PLATE.pts(); mp, Rq, MW = mug_world()
        return offw, Pw, Pw - offw, MW - offw, mp
    def g_frame_now(t):
        pu, Ru = g_pose("up", t); pl_, _ = g_pose("lo", t)
        return (pu + pl_) / 2, Ru
    def g_between(Pw, t):
        gc, Rg = g_frame_now(t)
        L_ = (Pw - gc) @ Rg
        m_ = (np.abs(L_[:, 0]) < GFS[0] / 2) & (np.abs(L_[:, 1]) < GFS[1] / 2) & (np.abs(L_[:, 2]) <= GAPG / 2 + 0.0005)
        return np.where(m_)[0], L_
    def lid_top_local(sd):
        nm_ = "fyn" if sd == "yn" else "fyp"
        r_ = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(
            st.GetPrimAtPath("/World/Box/" + nm_)).ComputeAlignedRange()
        return float(r_.GetMax()[2]) - g_offw()[2]

    def g_plan(sd, S0):
        """S0:用 sim 當下頂點算抓取點 → 排定挑角/下指/上指的 kinematic 路徑(掀的弧線在夾好後才排)。"""
        tw = time.time()
        offw, Pw, Pl, MUGl, mp = g_state()
        sg = -1.0 if sd == "yn" else 1.0
        rows = GPL.rank(Pl, MUGl, sd, BOXL)
        P("\n★ t=%.2f [%s] 抓取點即時排名(%d 候選,(a)上方沒被壓 %d / (b)掃掠不撞 %d / (c)下方空隙>=6mm %d / 全過 %d;算了 %.1fs)"
          % (S0, sd, len(rows), sum(r["ok_a"] for r in rows), sum(r["ok_b"] for r in rows), sum(r["ok_c"] for r in rows),
             sum(r["ok"] for r in rows), time.time() - tw))
        for k_, r in enumerate(rows[:6]):
            P("   #%d v%-4d %-4s %-4s flat(%4.0f,%4.0f) 位置(箱局部) (%6.1f,%6.1f,%6.1f) 坡度 %5.1f° 下方空隙 %5.1f 上方他層 %d 掃掠 牆/底/杯/布 %s %s"
              % (k_ + 1, r["v"], r["kind"], r["side"], *r["flat"], *r["p"], r["slope"], r["gap"], r["a"], "/".join(map(str, r["b"])),
                 "OK" if r["ok"] else "NG"))
        okr = [r for r in rows if r["ok"]]
        rk = a.grasp_rank if sd == "yn" else 1
        if okr:
            pick = rows[min(rk, len(okr)) - 1]; why = "合格第 %d 名" % min(rk, len(okr))
        else:
            pick = max(rows, key=lambda r: r["gap"]); why = "★ 沒有合格點 → 退而求其次:下方空隙最大"
        v = pick["v"]
        R0, slope = GPL.frame(Pl, v); tt_, uu, nn_ = R0[:, 0], R0[:, 1], R0[:, 2]
        M = GPL.mid(Pl); half = np.linalg.norm(Pl[v + N1] - Pl[v]) / 2
        i_, j_ = v % (a.nxy + 1), v // (a.nxy + 1)
        nbs = [v - 1, v + 1] if j_ in (0, a.nxy) else [v - (a.nxy + 1), v + (a.nxy + 1)]
        nbs = [b_ for b_ in nbs if 0 <= b_ < N1 and GSIDE2[b_] == sd]
        nb = min(nbs, key=lambda b_: np.linalg.norm(M[b_, :2])) if nbs else v
        toff = float(np.dot(M[nb] - M[v], tt_)) / 2
        p = M[v] + tt_ * toff
        P("  [%s] 選 %s:v%d(%s)位置 (%.1f,%.1f,%.1f) mm、邊坡度 %.1f°、下方空隙 %.1f mm;外法線 u=(%.2f,%.2f,%.2f);指面沿邊置中在 v%d/v%d 之間(t 偏 %.1fmm)"
          % (sd, why, v, pick["kind"], *(M[v] * 1e3), slope, pick["gap"], *uu, v, nb, toff * 1e3))
        pin = a.pick_in_mm / 1e3; lift = a.pick_mm / 1e3
        rod_ins = p + R0 @ [0, 0.020 - pin, -(half + 0.003 + GRS[2] / 2)]      # rod 長 30(沿 u):前端 = 中心 −15mm;起點前端在布邊外 +5mm,伸進 pin
        rod_pre = rod_ins + R0 @ [0, pin, 0]
        rod_above = rod_pre + [0, 0, 0.08]
        rod_lift = rod_ins + [0, 0, lift]
        rod_out = rod_lift + R0 @ [0, 0.045, 0]; rod_up = rod_out + [0, 0, 0.08]
        lo_f = rod_lift + R0 @ [0, (-0.0075) - (0.020 - pin), 0.0005]      # 下指足跡 u ∈ [−17.5, +2.5](布邊 u=0)
        lo_pre = lo_f + R0 @ [0, 0.032, 0]; lo_above = lo_pre + [0, 0, 0.06]
        up_f = lo_f + R0 @ [0, 0, GFS[2] + GAPG]
        up_pre = up_f + R0 @ [0, 0, 0.012]; up_above = up_pre + [0, 0, 0.06]
        W_ = lambda x: np.asarray(x) + offw
        g_lin("rod", S0, GT["rod_above"], W_(rod_above), R0)
        t_ = S0 + GT["rod_above"]; g_lin("rod", t_, GT["rod_down"], W_(rod_pre))
        t_ += GT["rod_down"]; g_lin("rod", t_, GT["rod_in"], W_(rod_ins))
        t_ += GT["rod_in"]; g_lin("rod", t_, GT["rod_lift"], W_(rod_lift))
        t_ = S0 + G_TLOIN
        g_lin("rod", t_, GT["rod_out"], W_(rod_out)); g_lin("rod", t_ + GT["rod_out"], GT["rod_up"], W_(rod_up))
        g_lin("rod", t_ + GT["rod_out"] + GT["rod_up"], 1.0, GPARK["rod"])
        # 上/下指的路徑在挑角完(S0+G_TPICK)才用『當下』的布邊位置/局部框排(第 1 次實跑:照挑角前規劃 → 角幾乎直立時下指足跡整個在布邊外,夾到 0)
        P("  [%s] 挑角路徑(箱局部 mm):rod 從上方降到 %s(前端在布邊外 %.0fmm、頂面在布底下 3mm)→ 沿 −u 伸進 %.0fmm 到 %s → 上抬 %.0fmm 到 %s;下指進來後 rod 沿 +u 撤 45mm"
          % (sd, np.round(rod_pre * 1e3, 1), 5.0, pin * 1e3, np.round(rod_ins * 1e3, 1), lift * 1e3, np.round(rod_lift * 1e3, 1)))
        others = {"yn": ("yp", "xp", "xn"), "yp": ("xp", "xn")}[sd]
        TOPS = np.where((GSIDE2 == sd) & (sg * Pl[:, 1] < CY - 0.003))[0]
        r_, _, _ = measure(S0, full=True)
        pl = dict(sd=sd, sg=sg, S0=S0, v=v, nb=nb, R0=R0, p=p, half=half, pick=pick, rows=rows[:6], offw=offw, P0=Pw.copy(), Pl0=Pl.copy(),
                  mug0=mp.copy(), others=np.isin(GSIDE2, others), osides=others, TOPS=TOPS, lo_f=lo_f, up_f=up_f, z_v0=float(M[v, 2]),
                  cov0=(r_.get("lay") or {}).get("cov", float("nan")), r_plan=r_, slip=[], ev={})
        SNAP["g_%s_plan" % sd] = (Pw.copy(), mug_world()[2].copy(), r_)
        P("  [%s] 翻面量測集:%s 片在折線(y=%+.1fmm)內側的頂點 %d 個;他片 %s 共 %d 頂點;杯頂俯視覆蓋 %.0f%%(露出 %.0f%%)"
          % (sd, sd, sg * CY * 1e3, len(TOPS), "/".join(others), int(pl["others"].sum()), 100 * pl["cov0"], 100 * (1 - pl["cov0"])))
        GS["plans"].append(pl)
        return pl

    def g_after_pick(pl, t):
        offw, Pw, Pl, MUGl, mp = g_state(); v = pl["v"]
        M = GPL.mid(Pl); Rn, _ = GPL.frame(Pl, v)
        gap = GPL.gap_below(Pl, MUGl, v, Rn, BOXL) * 1e3
        d_ = np.linalg.norm(Pw - pl["P0"], axis=1)
        om = pl["others"] | ((GSIDE2 != pl["sd"]) & (GSIDE2 != "base"))
        oth = (GSIDE2 != pl["sd"])
        n10 = int((d_[oth] > 0.010).sum())
        pl["ev"]["pick"] = dict(z0=pl["z_v0"] * 1e3, z1=float(M[v, 2]) * 1e3, gap0=pl["pick"]["gap"], gap1=gap, adj_n10=n10,
                                adj_max=float(d_[oth].max()) * 1e3, adj_tot=int(oth.sum()))
        e = pl["ev"]["pick"]
        P("\n★ t=%.2f [%s] 挑角完:角 v%d z %.1f → %.1f mm(+%.1f);下方空隙 %.1f → %.1f mm;相鄰層(非 %s 片)位移 >10mm 頂點 %d / %d,最大 %.1f mm"
          % (t, pl["sd"], v, e["z0"], e["z1"], e["z1"] - e["z0"], e["gap0"], e["gap1"], pl["sd"], n10, e["adj_tot"], e["adj_max"]))
        SNAP["g_%s_pick" % pl["sd"]] = (Pw.copy(), mug_world()[2].copy(), measure(t)[0])
        # 用當下的布邊排上/下指
        R1, sl1 = GPL.frame(Pl, v); t1 = R1[:, 0]
        nb = pl["nb"]; toff = float(np.dot(M[nb] - M[v], t1)) / 2 if nb != v else 0.0
        p1 = M[v] + t1 * toff
        lo_f = p1 + R1 @ [0, -0.0075, -(GAPG / 2 + GFS[2] / 2)]; up_f = p1 + R1 @ [0, -0.0075, GAPG / 2 + GFS[2] / 2]
        lo_pre = lo_f + R1 @ [0, 0.032, 0]; lo_above = lo_pre + [0, 0, 0.06]
        up_pre = up_f + R1 @ [0, 0, 0.012]; up_above = up_pre + [0, 0, 0.06]
        W_ = lambda x: np.asarray(x) + offw
        t_ = pl["S0"] + G_TPICK
        g_lin("lo", t_, GT["lo_above"], W_(lo_above), R1); t_ += GT["lo_above"]
        g_lin("lo", t_, GT["lo_down"], W_(lo_pre)); t_ += GT["lo_down"]
        g_lin("lo", t_, GT["lo_in"], W_(lo_f)); t_ += GT["lo_in"]
        g_lin("up", t_, GT["up_above"], W_(up_above), R1); t_ += GT["up_above"]
        g_lin("up", t_, GT["up_down"], W_(up_pre)); t_ += GT["up_down"]
        g_lin("up", t_, GT["close"], W_(up_f))
        pl.update(lo_f=lo_f, up_f=up_f, R0=R1)
        P("  [%s] 夾爪路徑(用挑角後的布邊:v%d (%.1f,%.1f,%.1f) 坡度 %.1f°,外法線 u=(%.2f,%.2f,%.2f)):下指從上方降到 %s(布邊外 32mm)→ 沿 −u 進到 %s(足跡 u∈[−17.5,+2.5]);"
              "上指從 +z 降到 %s → 沿 −n 合 12mm 到 %s(指面間距 %.1fmm)"
          % (pl["sd"], v, *(M[v] * 1e3), sl1, *R1[:, 1], np.round(lo_pre * 1e3, 1), np.round(lo_f * 1e3, 1), np.round(up_pre * 1e3, 1),
             np.round(up_f * 1e3, 1), a.gap_mm))

    def g_grip_and_arc(pl, t):
        """夾好:登記夾到的頂點;用『現在』的彎折處排弧線(半徑 = arc_k x 材料長度)+ 停 + 放開。"""
        offw, Pw, Pl, MUGl, mp = g_state(); sd, sg, v = pl["sd"], pl["sg"], pl["v"]
        G_, L_ = g_between(Pw, t)
        pl["G"] = G_; pl["rel0"] = L_[G_].copy()
        P("\n★ t=%.2f [%s] 夾好:指面之間(間距 %.1fmm、足跡 20x20)的布頂點 %d 個(歸屬 %s)"
          % (t, sd, a.gap_mm, len(G_), dict(zip(*np.unique(GSIDE2[G_], return_counts=True))) if len(G_) else {}))
        pl["ev"]["grip"] = dict(n=len(G_))
        SNAP["g_%s_grip" % sd] = (Pw.copy(), mug_world()[2].copy(), measure(t)[0])
        col_i = v % (a.nxy + 1)
        hy, hz, hfy, ym, zm, nc = GPL.hinge(Pl, sd, col_i)
        M = GPL.mid(Pl)
        col = np.where((GPL.S["ii"] == col_i) & (sg * GF2[:, 1] > CY - 1e-9))[0]
        col = col[np.argsort(sg * GF2[col, 1])]
        kb = int(np.argmin(np.abs(GF2[col, 1] - hfy))) if np.isfinite(hfy) else 0
        seg = col[kb:]; Lcur = float(np.linalg.norm(np.diff(M[seg], axis=0), axis=1).sum()) if len(seg) > 1 else float("nan")
        Lflat = float(abs(GF2[v, 1] - hfy))
        Lmat = max(Lcur, Lflat)
        Rr = a.arc_k * (Lmat - 0.0075)
        gc0 = (pl["lo_f"] + pl["up_f"]) / 2; R0 = pl["R0"]
        o_ = {"up": pl["up_f"] - gc0, "lo": pl["lo_f"] - gc0}
        Ba, Bz = -sg * hy, hz
        Ea, Ez = -(IY + 0.0015), CBOX["top_y"] + T / 2 + 0.002
        a0, z0 = -sg * gc0[1] - Ba, gc0[2] - Bz; r0 = float(np.hypot(a0, z0)); th0 = float(np.arctan2(z0, a0))
        BE = float(np.hypot(Ea - Ba, Ez - Bz)); th1 = float(np.arctan2(Ez - Bz, Ea - Ba))
        R2 = Rr - BE; two = R2 > 0.012
        if th0 >= th1:
            th1 = th0
        s1 = Rr * (th1 - th0); s2 = R2 * (np.pi - th1) if two else 0.0
        zclear = lid_top_local(sd) + T + 0.002
        axis = np.array([-sg, 0.0, 0.0])
        corners = np.array(list(itertools.product((-1, 1), repeat=3)), float) * GFS / 2
        def at(w):
            s_ = w * (s1 + s2)
            if not two or s_ <= s1:
                th = th0 + (th1 - th0) * (s_ / s1 if s1 > 0 else 1.0)
                r = r0 + (Rr - r0) * min(1.0, (th - th0) / max(1e-6, 0.3 * (th1 - th0)))
                A_, Z_ = Ba + r * np.cos(th), Bz + r * np.sin(th)
            else:
                th = th1 + (np.pi - th1) * ((s_ - s1) / s2)
                A_, Z_ = Ea + R2 * np.cos(th), Ez + R2 * np.sin(th)
            Rt = rotm(axis, th - th0)
            gc = np.array([gc0[0], -sg * A_, Z_])
            Pf = {k_: gc + Rt @ o_[k_] for k_ in o_}; Rf = Rt @ R0
            cs = np.array([Pf[k_] + c_ @ Rf.T for k_ in Pf for c_ in corners])
            m_ = sg * cs[:, 1] > IY - 0.003
            if m_.any():
                dz = max(0.0, zclear - cs[m_, 2].min())
                Pf = {k_: Pf[k_] + [0, 0, dz] for k_ in Pf}
            return Pf, Rf, th
        TP0 = t; TP1 = TP0 + a.peel_t
        for k_ in ("up", "lo"):
            g_fn(k_, TP0, a.peel_t, lambda w, k_=k_: (at(w)[0][k_] + offw, at(w)[1]))
        Pf1, Rf1, th_e = at(1.0)
        n_e, u_e = Rf1[:, 2], Rf1[:, 1]
        TR = TP1 + GT["peel_hold"]
        for k_, sgn in (("up", 1.0), ("lo", -1.0)):
            p1 = Pf1[k_] + offw
            g_lin(k_, TR, GT["rel_open"], p1 + sgn * n_e * 0.010)
            g_lin(k_, TR + GT["rel_open"], GT["rel_slide"], p1 + sgn * n_e * 0.010 + u_e * 0.030)
            g_lin(k_, TR + GT["rel_open"] + GT["rel_slide"], GT["rel_up"], p1 + sgn * n_e * 0.010 + u_e * 0.030 + [0, 0, 0.08])
        pl.update(TP0=TP0, TP1=TP1, TR=TR, hinge=(hy, hz), Lcur=Lcur, Lflat=Lflat, Rr=Rr, r0=r0, th0=th0, th1=th1, R2=R2, two=two,
                  zclear=zclear, end_local=(Pf1["up"] + Pf1["lo"]) / 2)
        P("  [%s] 弧線:彎折處(夾點那欄,即時)y=%.1f z=%.1f mm(|flat x|<CX 各欄中位 y=%.1f z=%.1f;題目名義折線 y=%+.1f);材料長度 現在 %.1f / flat %.1f mm → 半徑 %.2f x (%.1f − 7.5) = %.1f mm(夾爪中心起始離彎折處 %.1f mm,前 30%% 角度內漸變)"
          % (sd, hy * 1e3, hz * 1e3, ym * 1e3, zm * 1e3, sg * CY * 1e3, Lcur * 1e3, Lflat * 1e3, a.arc_k, Lmat * 1e3, Rr * 1e3, r0 * 1e3))
        P("  [%s] 第 1 段繞彎折處 %.0f° → %.0f°(指向箱壁外頂角 y=%+.1f z=%.1f);第 2 段 %s;箱外指頭最低點 >= 蓋頂 %.1f + T + 2 = %.1f mm;終點夾爪中心 (%.1f,%.1f,%.1f) mm;%.1fs 後停 %.1fs 再放開"
          % (sd, np.degrees(th0), np.degrees(th1), sg * (IY + 0.0015) * 1e3, Ez * 1e3,
             ("繞箱壁頂角 半徑 %.1fmm 轉到 180°" % (R2 * 1e3)) if two else ("略過(半徑剩 %.1fmm < 12)" % (R2 * 1e3)),
             (zclear - T - 0.002) * 1e3, zclear * 1e3, *(pl["end_local"] * 1e3), a.peel_t, GT["peel_hold"]))

    def g_metrics(pl, t, Pw=None):
        offw = g_offw()
        if Pw is None: Pw = PLATE.pts()
        Pl = Pw - offw; sd, sg = pl["sd"], pl["sg"]
        r = dict(t=t)
        gc, Rg = g_frame_now(t)
        r["up"] = (g_pose("up", t)[0] - offw) * 1e3; r["lo"] = (g_pose("lo", t)[0] - offw) * 1e3
        Gn, L_ = g_between(Pw, t); r["ngrip"] = len(Gn)
        if "G" in pl and len(pl["G"]) and pl.get("TP0") is not None and t <= pl["TR"] + 1e-6:
            dd = np.linalg.norm(L_[pl["G"]] - pl["rel0"], axis=1)
            r["slip"] = float(np.median(dd)) * 1e3; r["slip_max"] = float(dd.max()) * 1e3
            pl["slip"].append((t, r["slip"], r["slip_max"]))
        else:
            r["slip"] = r["slip_max"] = float("nan")
        r["cross"] = float((sg * Pl[pl["TOPS"], 1] > CY).mean()) if len(pl["TOPS"]) else float("nan")
        msd = GSIDE2 == sd
        r["cross_all"] = float((sg * Pl[msd, 1] > CY).mean())
        d_ = np.linalg.norm(Pw - pl["P0"], axis=1)
        o_ = pl["others"]; r["oth_n10"] = int((d_[o_] > 0.010).sum()); r["oth_pct"] = 100.0 * r["oth_n10"] / max(1, int(o_.sum()))
        r["oth_max"] = float(d_[o_].max()) * 1e3
        r["oth_side"] = {s_: int(((GSIDE2 == s_) & (d_ > 0.010)).sum()) for s_ in pl["osides"]}
        r["mug_d"] = float(np.linalg.norm(mug_world()[0] - pl["mug0"])) * 1e3
        return r

    def g_line(pl, r, rm):
        P("  G[%s] t=%6.2f %-26s 上指 (%6.1f,%6.1f,%6.1f) 下指 (%6.1f,%6.1f,%6.1f) | 夾到 %2d | 滑動 中位 %s 最大 %s | %s 越過折線 %3.0f%%(整片 %3.0f%%)| 他片 >10mm %4d(%.1f%%)最大 %5.1f | 杯位移 %.1f | 自穿 %d 穿杯 %d 反轉 %d"
          % (pl["sd"], r["t"], phase(r["t"]), *r["up"], *r["lo"], r["ngrip"], "%.1f" % r["slip"] if np.isfinite(r["slip"]) else "-",
             "%.1f" % r["slip_max"] if np.isfinite(r["slip_max"]) else "-", pl["sd"], 100 * r["cross"], 100 * r["cross_all"],
             r["oth_n10"], r["oth_pct"], r["oth_max"], r["mug_d"], rm["pen"], rm["inmug"], rm["inv"]))
        GS["rows"].append(dict(sd=pl["sd"], **{k_: (v_.tolist() if isinstance(v_, np.ndarray) else v_) for k_, v_ in r.items()},
                               pen=rm["pen"], inmug=rm["inmug"], inv=rm["inv"]))

    def g_events(t):
        """每個物理步呼叫:到點就做規劃 / 量測。"""
        k_ = int((t - TG0) // G_SHEET)
        if k_ >= len(G_SEQ): return
        S0 = TG0 + k_ * G_SHEET
        if GS["k"] < k_:
            GS["k"] = k_; g_plan(G_SEQ[k_], S0)
            if k_ == 0:
                EYE = g_offw() + np.array([0.62, -0.06, 0.50]); TGT = g_offw() + np.array([0.0, -0.06, 0.07])
                cam.set_focal_length(a.gcam_focal)
                try: cam.set_clipping_range(0.01, 100.0)
                except Exception: pass
                G.look(cam, list(EYE), list(TGT))
        pl = GS["plans"][k_]; ev = pl["ev"]
        if "pick" not in ev and t >= S0 + G_TPICK - 1e-6:
            g_after_pick(pl, t)
        if "grip" not in ev and t >= S0 + G_TGRIP - 1e-6:
            g_grip_and_arc(pl, t)
        for nm_, tt_ in (("peel_1_3", pl.get("TP0", 1e9) + a.peel_t / 3), ("peel_2_3", pl.get("TP0", 1e9) + 2 * a.peel_t / 3),
                         ("peeled", pl.get("TP1", 1e9)), ("held", pl.get("TR", 1e9) - 1e-3), ("released", S0 + G_SHEET - 0.05)):
            if nm_ not in ev and t >= tt_:
                rm, Pw, _ = measure(t, full=nm_ in ("held", "released"))
                r = g_metrics(pl, t, Pw); r["rm"] = dict(pen=rm["pen"], inmug=rm["inmug"], inv=rm["inv"],
                                                          cov=(rm.get("lay") or {}).get("cov", float("nan")))
                ev[nm_] = r
                SNAP["g_%s_%s" % (pl["sd"], nm_)] = (Pw.copy(), mug_world()[2].copy(), rm)
                P("\n★ t=%.2f [%s] %s" % (t, pl["sd"], nm_)); g_line(pl, r, rm)
                if nm_ in ("held", "released"):
                    P("  杯頂俯視覆蓋 %.0f%% → 露出 %.0f%%(開始時 %.0f%%)" % (100 * r["rm"]["cov"], 100 * (1 - r["rm"]["cov"]), 100 * (1 - pl["cov0"])))

# ── 主迴圈 ───────────────────────────────────────────────────────────
try: FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 17)
except Exception: FONT = ImageFont.load_default()
L1 = ("VOLUME sheet %.0fx%.0fx%.0fmm n%d | E=%.0e nu=%.2f %.2fkg/m2 mu=%.1f | mug %.0fx%.0fx%.0f | fold %s"
      % (WX*1e3, WY*1e3, T*1e3, a.nxy, a.young, a.poisson, a.areal, a.fric, *(ME*1e3), "-".join(FOLD_ORDER)))
L2 = ("solver %d dt 1/%.0f cont %.1f rest %.2f self on | tip=top+lay*(T+1)+2mm %s%s | move %s | carton w131%s"
      % (a.solver, 1/a.dt, a.cont*1e3, a.rest*1e3, ("extra " + a.tip_extra + " ") if a.tip_extra else "",
         ("slow " + a.slow) if a.slow else "", a.movebox, " | REST=folded" if a.rest_npz else ""))
def stamp(rgb, t, ph_):
    im = Image.fromarray(rgb[:, :, :3]); d = ImageDraw.Draw(im); Wd, Hh = im.size
    d.rectangle([0, Hh-58, Wd, Hh], fill=(16, 16, 18))
    d.text((10, Hh-54), L1, fill=(235,)*3, font=FONT)
    d.text((10, Hh-30), L2, fill=(170, 200, 230), font=FONT)
    d.rectangle([Wd-430, 4, Wd-4, 32], fill=(16, 16, 18))
    d.text((Wd-424, 8), "t=%5.2fs  %s" % (t, ph_), fill=(255,)*3, font=FONT)
    return np.array(im)

writer = imageio.get_writer(os.path.join(a.out, "wrap.mp4"), fps=FPS, quality=7, macro_block_size=1)
SPF = int(round(1.0 / (FPS * a.dt)))                 # 每個渲染幀幾個物理步
NFR = int(round(T_END * FPS))
ME_EVERY = int(round(a.meas_dt * FPS))
KEYS = {"fold_half": FT[FOLD_ORDER[2]][0] - 0.05, "fold_done": T_FOLD_END - 0.05, "in_box": T_LID0 - 0.05,
        "lids_closed": T_MOVE0 - 0.05, "after_move": T_OPEN0 - 0.05, "opened": T_END_ALL - 0.05}
KEYF = {k: int(round(v * FPS)) - 1 for k, v in KEYS.items()}
LOGR = []; SNAP = {}; TRAJ_T = []; TRAJ_P = []; TRAJ_M = []
EV = {}
t0w = time.time(); step = 0; tcur = 0.0; nan = False
P("渲染 %d fps,每幀 %d 物理步;共 %d 幀" % (FPS, SPF, NFR))
for fr in range(NFR):
    for k in range(SPF):
        step += 1; tcur = step * a.dt
        # ── 事件 ──
        if not ST["inbox"] and tcur >= T_INBOX:
            Pp = PLATE.pts(); mp, Rq, MW = mug_world()
            r_, _, _ = measure(tcur, full=True); SNAP["fold_end"] = (Pp.copy(), MW.copy(), r_)
            c = (Pp[:, :2].min(0) + Pp[:, :2].max(0)) / 2
            if a.squeeze_t > 0:
                c = np.zeros(2)          # 側板以原點為中心收,箱子也以原點為中心
            ST["OFF_IN"] = np.array([c[0] - BOXC[0], c[1] - BOXC[1], -CDZ])
            # ★ 箱子用 PhysX tensor set_transforms **瞬移**(不經 kinematic target)。
            #   第 3 版用 USD set_world_pose 瞬移:kinematic 以 ~200 m/s 的速度「走」過去,同時側板以 720 m/s 往下撤,
            #   碰到的布被摩擦拖走 → 那一格自穿 4→211、反轉 0→19、布穿杯 0→6。
            _off = ST["OFF_IN"]
            _D = np.zeros((BOXV.count, 7), np.float32)
            for i_, pth_ in enumerate(BOXV.prim_paths):
                if pth_.endswith("/base"):
                    p_, q_w = BASE_P0 + _off, BASE_Q0
                else:
                    L_ = [L for L in LIDS if pth_.endswith("/" + L["nm"])][0]
                    p_, q_w = lid_pose(L_, 180.0, _off)
                _D[i_, :3] = p_; _D[i_, 3:6] = q_w[1:]; _D[i_, 6] = q_w[0]
            BOXV.set_transforms(_D, np.arange(BOXV.count, dtype=np.int32))
            BOXV.set_velocities(np.zeros((BOXV.count, 6), np.float32), np.arange(BOXV.count, dtype=np.int32))
            P("  箱子 tensor set_transforms 瞬移 %d 個剛體(base + 4 蓋)" % BOXV.count)
            P("\n★ t=%.3f 入箱:包裹(布)bbox 中心 (%.1f,%.1f) mm,杯心 (%.1f,%.1f,%.1f);箱子剛性瞬移到 %s mm(箱底內面 = 地面)"
              % (tcur, c[0]*1e3, c[1]*1e3, *(mp*1e3), np.round(ST["OFF_IN"]*1e3, 1)))
            P("  入箱前(瞬移前)以箱子目標位置比對內腔:")
            EV["pre_in"] = (inbox("布", Pp, ST["OFF_IN"]), inbox("杯子", MW, ST["OFF_IN"]))
            ST["inbox"] = True
            _ng = 0
            for _gp in Usd.PrimRange(st.GetPrimAtPath("/World/defaultGroundPlane")):
                if _gp.HasAPI(UsdPhysics.CollisionAPI):
                    UsdPhysics.CollisionAPI(_gp).CreateCollisionEnabledAttr(False); _ng += 1
            P("  地板碰撞關閉(%d collider);箱底(+pad)接手" % _ng)
            _dl.GetIntensityAttr().Set(3500.0); _dl2.GetIntensityAttr().Set(2200.0)
            _R = 0.64
            EB = np.array([_R*1.55, -_R*1.70, _R*2.05]) + MOVE/2 + ST["OFF_IN"] * [1, 1, 0]
            TB = np.array([0, 0, 0.030]) + MOVE/2 + ST["OFF_IN"] * [1, 1, 0]
            G.look(cam, list(EB), list(TB))
        if not ST["released"] and tcur >= T_ANC:
            Pp = PLATE.pts(); mp, Rq, MW = mug_world()
            r_, _, _ = measure(tcur, full=True); SNAP["closed_pre_release"] = (Pp.copy(), MW.copy(), r_)
            st.RemovePrim(Sdf.Path("/World/attach"))
            kin.Set(False)
            ST["released"] = True
            P("\n★ t=%.3f 關蓋完成 → RemovePrim 全部錨點(4 scope);杯子轉 dynamic" % tcur)
        drive(tcur)
        if a.grasp and tcur >= TG0 - 1e-9:
            g_events(tcur); g_drive(tcur)
        world.step(render=(k == SPF - 1))
    # ── 渲染幀 ──
    Pp = PLATE.pts()
    if not np.isfinite(Pp).all():
        P("★ NaN t=%.3f" % tcur); nan = True; break
    VISPTS.Set(Vt.Vec3fArray.FromNumpy(Pp.astype(np.float32)))
    if a.grasp and tcur >= TG0 - 1e-9:
        g_vis(tcur)
    rgb = cam.get_rgba()
    ph_ = phase(tcur)
    if rgb is not None and rgb.size:
        img = stamp(rgb, tcur, ph_)
        writer.append_data(img)
        for kname, kf in KEYF.items():
            if fr == kf:
                Image.fromarray(img).save(os.path.join(a.out, "key_%s.png" % kname))
    # ── 量測 ──
    if fr % ME_EVERY == 0 or fr == NFR - 1:
        full = (fr % (ME_EVERY * 4) == 0) or fr == NFR - 1
        r, Pp, MW = measure(tcur, full=full)
        LOGR.append(r); TRAJ_T.append(tcur); TRAJ_P.append(Pp.astype(np.float32)); TRAJ_M.append(np.r_[r["mug"]])
        s_ = ("t=%6.2f %-24s bbox %3.0fx%3.0fx%3.0f | 自穿 %4d | 布穿杯 %3d | 反轉 %3d | 體積比 %.4f | 邊長比 [%.3f,%.3f] | 杯心 (%5.1f,%5.1f,%5.1f)"
              % (tcur, ph_, *r["bb"], r["pen"], r["inmug"], r["inv"], r["volr"], *r["lr"], *(r["mug"]*1e3)))
        if ST["inbox"]:
            off = box_off(tcur); lz = lid_cz()
            s_ += " | 箱位移 (%.0f,%.0f,%.0f) 蓋z(相對箱底) %s" % (*((off - ST["OFF_IN"])*1e3),
                                                          " ".join("%s=%.1f" % (k_, (v_ - off[2] - CDZ)*1e3) for k_, v_ in lz.items()))
        if r.get("lay"):
            s_ += " | 杯頂上 %.0f 層 間距 %.2f 頂厚 %.1f" % (r["lay"]["nlay"], r["lay"]["gap"], r["lay"]["top"])
        P(s_)
        if a.grasp and GS["plans"] and tcur >= TG0:
            _pl = GS["plans"][-1]; g_line(_pl, g_metrics(_pl, tcur, Pp), r)
    # 階段快照
    for nm_, tt_ in [("fold_" + FOLD_ORDER[1], FT[FOLD_ORDER[2]][0] - 1e-6), ("after_move", T_OPEN0 - 1e-6),
                     ("before_move", T_MOVE0 - 1e-6), ("end", T_END_ALL - 1e-6)]:
        if nm_ not in SNAP and tcur >= tt_ - 1.0/FPS and tcur < tt_ + 1.0/FPS:
            _P = PLATE.pts(); _, _, _MW = mug_world(); r_, _, _ = measure(tcur, full=True)
            SNAP[nm_] = (_P.copy(), _MW.copy(), r_)
            if nm_ == "before_move":
                SNAP[nm_] = (_P.copy(), _MW.copy(), r_, box_off(tcur).copy(), mugx.get_world_pose()[0].copy())
writer.close()
wall = time.time() - t0w
P("\n影片 → %s/wrap.mp4(%d 幀);wall %.1fs / sim %.2fs = %.2f" % (a.out, fr + 1, wall, tcur, wall / max(tcur, 1e-9)))

# ── 結尾判讀 ─────────────────────────────────────────────────────────
Pf = PLATE.pts(); mpf, Rqf, MWf = mug_world()
rf, _, _ = measure(tcur, full=True)
SNAP.setdefault("final", (Pf.copy(), MWf.copy(), rf))
P("\n===== 判讀 wrap_vol sheet %.0f(%s)=====" % (a.sheet_mm, "NaN 中止" if nan else "跑到 %s" % a.until))
def row(nm_, r):
    ly = r.get("lay") or {}
    P("  %-22s t=%6.2f bbox 布 %3.0fx%3.0fx%3.0f / 含杯 %3.0fx%3.0fx%3.0f | 體積÷杯 %.2f | 自穿 %d | 布穿杯 %d | 反轉 %d | 體積比 %.4f | 杯頂上 %s 層(分佈 %s)間距 %s 頂厚 %s 第1層離杯頂 %s"
      % (nm_, r["t"], *r["bb"], *r["pkg"], r["pkgvol"], r["pen"], r["inmug"], r["inv"], r["volr"],
         ly.get("nlay", "-"), ly.get("dist", "-"), "%.2f" % ly["gap"] if ly else "-",
         "%.1f" % ly["top"] if ly else "-", "%.1f" % ly["first"] if ly else "-")
      + (" | 杯頂俯視覆蓋 %.0f%%" % (100*ly["cov"]) if ly else ""))
for nm_ in ["fold_" + FOLD_ORDER[1], "fold_end", "closed_pre_release", "before_move", "after_move", "end", "final"]:
    if nm_ in SNAP:
        row(nm_, SNAP[nm_][2])
P("  全程最大:自穿 %d(t=%.2f %s)| 布穿杯 %d | 反轉 %d | 邊長比 [%.3f, %.3f]"
  % (max(r["pen"] for r in LOGR), max(LOGR, key=lambda r: r["pen"])["t"], max(LOGR, key=lambda r: r["pen"])["ph"],
     max(r["inmug"] for r in LOGR), max(r["inv"] for r in LOGR), min(r["lr"][0] for r in LOGR), max(r["lr"][1] for r in LOGR)))
# 每折自穿增量
P("  每階段結束時自穿:")
lastph = None
for r in LOGR:
    if lastph is not None and r["ph"] != lastph[0]:
        P("    %-26s 結束 t=%.2f 自穿 %d" % (lastph[0], lastph[1], lastph[2]))
    lastph = (r["ph"], r["t"], r["pen"])
if lastph: P("    %-26s 結束 t=%.2f 自穿 %d" % lastph)
# 折疊驅動檢查:每折錨點尖端位置
if "fold_end" in SNAP:
    Pfe = SNAP["fold_end"][0]
    for sd, S_ in SIDES.items():
        vv_ = S_["vids"] if S_["ax"] == 0 else S_["vids"][np.abs(FLAT[S_["vids"], 0]) <= CX]
        q = Pfe[vv_]
        P("  折 %s 尖端(綁的、|x|<=CX 的 %d 點)along %.1f~%.1f z %.1f~%.1f mm(目標 along %.1f z %.1f±2)"
          % (sd, len(q), (S_["sg"]*q[:, S_["ax"]]).min()*1e3, (S_["sg"]*q[:, S_["ax"]]).max()*1e3, q[:, 2].min()*1e3,
             q[:, 2].max()*1e3, S_["along_end"]*1e3, S_["zend"]*1e3))
if ST["inbox"]:
    P("\n===== 真的入箱了嗎(逐頂點比對內腔)=====")
    if "closed_pre_release" in SNAP:
        P(" 關蓋後(放錨前):")
        EV["closed"] = (inbox("布", SNAP["closed_pre_release"][0], ST["OFF_IN"]), inbox("杯子", SNAP["closed_pre_release"][1], ST["OFF_IN"]))
    if "before_move" in SNAP:
        P(" 搬前:")
        bm = SNAP["before_move"]
        EV["bm"] = (inbox("布", bm[0], bm[3]), inbox("杯子", bm[1], bm[3]))
    if "after_move" in SNAP:
        P(" 搬後(原點 = 箱子最終位置):")
        offm = box_off(T_OPEN0 - 1e-6)
        EV["am"] = (inbox("布", SNAP["after_move"][0], offm), inbox("杯子", SNAP["after_move"][1], offm))
        bm = SNAP["before_move"]; am = SNAP["after_move"]
        rel0 = bm[0].mean(0) - bm[3]; rel1 = am[0].mean(0) - offm
        mr0 = bm[4] - bm[3]; mr1 = am[2]["mug"] - offm
        P("  搬箱:箱位移 (%.1f,%.1f,%.1f) mm;布質心相對箱 搬前→搬後 差 %.1f mm;杯心相對箱 差 %.1f mm"
          % (*((offm - bm[3])*1e3), np.linalg.norm(rel1 - rel0)*1e3, np.linalg.norm(mr1 - mr0)*1e3))
        P("  杯心相對箱中心(搬後):(%+.1f, %+.1f, %+.1f) mm(z 相對箱底內面)"
          % ((mr1[0]-BOXC[0])*1e3, (mr1[1]-BOXC[1])*1e3, (mr1[2]-CDZ)*1e3))
    if tcur >= T_END_ALL - 0.1:
        P(" 開蓋後(結束):")
        offe = box_off(tcur)
        EV["end"] = (inbox("布", SNAP["end"][0], offe), inbox("杯子", SNAP["end"][1], offe)) if "end" in SNAP else (inbox("布", Pf, offe), inbox("杯子", MWf, offe))
    off = box_off(tcur); lz = lid_cz()
    P("  蓋中心 z(相對箱底內面):%s;關著時預設 %s"
      % (" ".join("%s=%.1f" % (k_, (v_ - off[2] - CDZ)*1e3) for k_, v_ in lz.items()),
         " ".join("%s=%.1f" % (L["nm"], (L["cz0"] - CDZ)*1e3) for L in LIDS)))
    def verdict(e, lid_open=False):
        s, m = e
        if lid_open:      # 蓋子開著:高於口不算出箱,只看 x/y/底
            s = dict(s, n=s["x"] + s["y"] + s["lo"], hi=0); m = dict(m, n=m["x"] + m["y"] + m["lo"], hi=0)
        if s["n"] + m["n"] == 0: return "PASS"
        if s["x"] + s["y"] + s["hi"] + m["x"] + m["y"] + m["hi"] == 0 and s["n"] + m["n"] <= 10 and max(s["dlo"], m["dlo"]) < 5: return "WARN"
        return "FAIL"
    def cnt(v_, lid_open):
        return [(d["x"] + d["y"] + d["lo"]) if lid_open else d["n"] for d in v_]
    P("  驗收:" + " | ".join("%s %s(布 %d 杯 %d)" % (k_, verdict(v_, k_ in ("pre_in", "end")), *cnt(v_, k_ in ("pre_in", "end")))
                            for k_, v_ in EV.items()) + "(pre_in / end 蓋子開著,只計 x/y/底)")
    _q = mugx.get_world_pose()[1]
    P("  杯子姿態:相對初始轉了 %.1f°(dynamic 之後)" % np.degrees(2*np.arccos(min(1.0, abs(float(_q[0]))))))
# ── 軟度掃描用摘要 ──
def zrel(Pp, off): return (Pp[:, 2] - off[2] - CDZ) * 1e3          # 相對箱底內面 mm
LIDBOT = min(L["zmin0"] for L in LIDS) - CDZ                         # 下蓋底面(相對箱底內面),m
try:
    pre = [r for r in LOGR if r["t"] <= T_SQ0 + 1e-6][-1]
    P("\n===== SUMMARY =====")
    P("  E %.0e T %.1fmm 面密度 %.2f cont %.2f rest %.2f tuck %d" % (a.young, a.thick_mm, a.areal, a.cont*1e3, a.rest*1e3, a.tuck))
    P("  四折後(收耳前 t=%.2f)bbox %.0fx%.0fx%.0f;側板內縮目標 %.0fx%.0f ⇒ 側板%s碰到布(四折後 bbox 是否超出)"
      % (pre["t"], *pre["bb"], 2*(IX - a.squeeze_mm/1e3)*1e3, 2*(IY - a.squeeze_mm/1e3)*1e3,
         "會" if (pre["bb"][0] > 2*(IX - a.squeeze_mm/1e3)*1e3 or pre["bb"][1] > 2*(IY - a.squeeze_mm/1e3)*1e3) else "不會"))
    if "fold_end" in SNAP: P("  收耳後/入箱前 bbox %.0fx%.0fx%.0f" % tuple(SNAP["fold_end"][2]["bb"]))
    if "closed_pre_release" in SNAP:
        r_ = SNAP["closed_pre_release"][2]; P("  關蓋後 bbox %.0fx%.0fx%.0f 體積÷杯 %.2f" % (*r_["bb"], r_["pkgvol"]))
    if "closed_pre_release" in SNAP and "before_move" in SNAP:
        z1 = zrel(SNAP["closed_pre_release"][0], ST["OFF_IN"]); z2 = zrel(SNAP["before_move"][0], SNAP["before_move"][3])
        P("  頂力代理:下蓋底面 %.1fmm;布頂 z(max/99%%)放錨前 %.1f/%.1f → 放錨後 2s %.1f/%.1f;離蓋底 <2mm 的頂點 %d → %d"
          % (LIDBOT*1e3, z1.max(), np.percentile(z1, 99), z2.max(), np.percentile(z2, 99),
             int((z1 > LIDBOT*1e3 - 2).sum()), int((z2 > LIDBOT*1e3 - 2).sum())))
    if "end" in SNAP and tcur >= T_END_ALL - 0.1:
        ze = zrel(SNAP["end"][0], box_off(tcur)); ly = SNAP["end"][2].get("lay") or {}
        P("  開蓋後 3s:布頂 z max %.1f / 99%% %.1f mm(箱口 %.1f);杯頂俯視覆蓋 %.0f%%" % (ze.max(), np.percentile(ze, 99), (ZHI0-CDZ)*1e3, 100*ly.get("cov", float("nan"))))
    P("  全程最大 自穿 %d 布穿杯 %d 反轉 %d 邊長比 [%.3f,%.3f] 體積比 [%.4f,%.4f]"
      % (max(r["pen"] for r in LOGR), max(r["inmug"] for r in LOGR), max(r["inv"] for r in LOGR),
         min(r["lr"][0] for r in LOGR), max(r["lr"][1] for r in LOGR), min(r["volr"] for r in LOGR), max(r["volr"] for r in LOGR)))
    P("  wall %.1fs" % wall)
except Exception as e:
    P("SUMMARY 失敗:%s" % e)
if a.grasp:
    P("\n===== 抓取段判讀(--grasp 1;rank %d、挑角 %.0f/%.0fmm、半徑係數 %.2f、掀 %.1fs、間距 %.1fmm、指面摩擦 %.1f)====="
      % (a.grasp_rank, a.pick_in_mm, a.pick_mm, a.arc_k, a.peel_t, a.gap_mm, a.ffric))
    GSUM = []
    for pl in GS["plans"]:
        ev = pl["ev"]; sd = pl["sd"]
        if "held" not in ev:
            P("  [%s] 沒跑完(ev %s)" % (sd, list(ev))); continue
        h = ev["held"]; pk = ev.get("pick", {}); rl = ev.get("released", h)
        rows_ = [r for r in GS["rows"] if r["sd"] == sd and pl.get("TP0", 1e9) - 1e-6 <= r["t"] <= pl["TR"] + 1e-6]
        slip_med = max([s_[1] for s_ in pl["slip"]] or [float("nan")]); slip_mx = max([s_[2] for s_ in pl["slip"]] or [float("nan")])
        mugmax = max([r["mug_d"] for r in GS["rows"] if r["sd"] == sd] + [h["mug_d"]])
        allr = [r for r in GS["rows"] if r["sd"] == sd]
        pen_mx = max([r["pen"] for r in allr] + [0]); inm_mx = max([r["inmug"] for r in allr] + [0]); inv_mx = max([r["inv"] for r in allr] + [0])
        ok = dict(grip=ev["grip"]["n"] >= 6, slip=(slip_med < 10.0), cross=h["cross"] >= 0.8, oth=h["oth_pct"] < 5.0, mug=mugmax < 5.0, inmug=inm_mx == 0)
        allok = all(ok.values())
        P("  [%s] 抓取點 v%d 位置 (%.1f,%.1f,%.1f) 坡度 %.1f° 空隙 %.1f | 挑角後 z %.1f→%.1f 空隙 %.1f→%.1f 相鄰層 >10mm %d(最大 %.1f)"
          % (sd, pl["v"], *pl["pick"]["p"], pl["pick"]["slope"], pl["pick"]["gap"], pk.get("z0", np.nan), pk.get("z1", np.nan),
             pk.get("gap0", np.nan), pk.get("gap1", np.nan), pk.get("adj_n10", -1), pk.get("adj_max", np.nan)))
        P("  [%s] 夾到 %d %s | 滑動(夾持中 中位/最大頂點)%.1f / %.1f mm %s | 越過折線 %.0f%%(整片 %.0f%%)%s;放開後 %.0f%% | 他片 >10mm %d(%.1f%%)最大 %.1f mm %s %s | 杯位移最大 %.1f mm %s | 自穿最多 %d 穿杯 %d %s 反轉 %d | 露出 %.0f%% → %.0f%%(放開後 %.0f%%)⇒ %s"
          % (sd, ev["grip"]["n"], "OK" if ok["grip"] else "NG", slip_med, slip_mx, "OK" if ok["slip"] else "NG", 100 * h["cross"], 100 * h["cross_all"],
             "OK" if ok["cross"] else "NG", 100 * rl["cross"], h["oth_n10"], h["oth_pct"], h["oth_max"], h["oth_side"], "OK" if ok["oth"] else "NG",
             mugmax, "OK" if ok["mug"] else "NG", pen_mx, inm_mx, "OK" if ok["inmug"] else "NG", inv_mx, 100 * (1 - pl["cov0"]),
             100 * (1 - h["rm"]["cov"]), 100 * (1 - rl["rm"]["cov"]), "PASS" if allok else "FAIL"))
        GSUM.append(dict(sd=sd, v=pl["v"], pick=pk, grip=ev["grip"]["n"], slip_med=slip_med, slip_max=slip_mx, cross=h["cross"],
                         cross_rel=rl["cross"], oth_n10=h["oth_n10"], oth_pct=h["oth_pct"], oth_max=h["oth_max"], mug=mugmax, pen=pen_mx,
                         inmug=inm_mx, inv=inv_mx, cov0=pl["cov0"], cov_held=h["rm"]["cov"], cov_rel=rl["rm"]["cov"], ok=ok, PASS=allok,
                         hinge=pl.get("hinge"), Lcur=pl.get("Lcur"), Lflat=pl.get("Lflat"), Rr=pl.get("Rr"), r0=pl.get("r0"),
                         th0=pl.get("th0"), th1=pl.get("th1"), R2=pl.get("R2"), events={k_: ev[k_]["t"] for k_ in ev if isinstance(ev[k_], dict) and "t" in ev[k_]},
                         TP0=pl.get("TP0"), TP1=pl.get("TP1"), S0=pl["S0"]))
    json.dump(dict(summary=GSUM, rows=GS["rows"]), open(os.path.join(a.out, "grasp.json"), "w"), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    P("  抓取段明細 → %s/grasp.json" % a.out)
np.savez_compressed(os.path.join(a.out, "wrap.npz"),
                    sheet_mid=(Pf[BOT] + Pf[TOP]) / 2, tet=Pf, tets=TETS, flat=FLAT, mug=MWf, mugrest=V,
                    fold_end_tet=SNAP["fold_end"][0] if "fold_end" in SNAP else Pf,
                    **{"snap_" + k_: v_[0] for k_, v_ in SNAP.items()},
                    **{"snapmug_" + k_: v_[1] for k_, v_ in SNAP.items()},
                    traj_t=np.array(TRAJ_T), traj_tet=np.array(TRAJ_P), traj_mug=np.array(TRAJ_M))
P("npz → %s/wrap.npz" % a.out)
LOG.close()
sim.close()
