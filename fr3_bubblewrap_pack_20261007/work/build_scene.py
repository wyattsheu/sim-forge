#!/usr/bin/env python3
"""把「他們的手臂場景 + 我們的紙箱 + 他們的馬克杯」組成一個 USD。

  /isaac-sim/python.sh build_scene.py --scene scene.usd --mug mug.stl --out out/scene_mug.usd

★ 三件必須知道的事
 1. 手臂與桌子完全不動,只刪掉舊的 /World/Carton 再用同一套命名重建。
 2. 紙箱的摺痕是**被動關節**(有 ±185° 限制、無 drive)。彈塑性摺痕是執行期的事,
    USD 帶不了 —— 一定要搭配 run_crease.py,否則蓋子會自己垂下來。
 3. 馬克杯用**量到的質量 0.0807 kg**,不是用 PLA 密度推(實心會算成 135 g,差 67%)。
"""
import argparse, os, math
ap = argparse.ArgumentParser()
ap.add_argument("--scene", required=True)
ap.add_argument("--mug",   required=True, help="STL")
ap.add_argument("--out",   default="out/scene_mug.usd")
ap.add_argument("--W", type=float, default=0.280, help="寬(蓋子鉸鏈平行這一邊)")
ap.add_argument("--L", type=float, default=0.180, help="長")
ap.add_argument("--H", type=float, default=0.150, help="高")
ap.add_argument("--board", type=float, default=0.003)
ap.add_argument("--inner", action="store_true", help="W/L/H 是內尺寸(預設當外尺寸)")
ap.add_argument("--carton_yaw", type=float, default=90.0,
                help="紙箱繞 Z 的擺放角(度)。0=長邊東西向;90=長邊南北向")
ap.add_argument("--carton", default="out/carton_m0921.usd",
                help="定版 make_carton_P.py 產出的紙箱 USD(只改尺寸)")
ap.add_argument("--mug_mass", type=float, default=0.0807)
ap.add_argument("--mug_rgb", default="144,163,189")
ap.add_argument("--lie", action="store_true", default=True, help="杯子躺平(預設開)")
ap.add_argument("--upright", dest="lie", action="store_false", help="改回直立")
ap.add_argument("--mug_roll", type=float, default=90.0, help="躺平後的初始滾轉角(度)")
ap.add_argument("--mug_axis", choices=["long","short"], default="short",
                help="杯軸順著箱子的長邊(long)還是短邊(short)")
ap.add_argument("--density", type=float, default=200.0, help="(已不用:紙箱密度由產生器的 config 決定)")
a = ap.parse_args()

from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import numpy as np, trimesh
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Gf, Sdf, UsdShade
P = lambda *x: print(*x, flush=True)

st = Usd.Stage.Open(a.scene)
TB = a.board
OW, OL, OH = (a.W + 2*TB, a.L + 2*TB, a.H + TB) if a.inner else (a.W, a.L, a.H)
IW, IL, IH = OW - 2*TB, OL - 2*TB, OH - TB          # 內部淨空
P("(命令列的 W/L/H 已不決定紙箱尺寸 —— 尺寸由 configs/box/*.json 決定,實測值見下方)")

# ── 桌面高度與舊箱子的中心,照抄 ──
bc = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render", "guide", "proxy"])
old = st.GetPrimAtPath("/World/Carton")
r = bc.ComputeWorldBound(old).ComputeAlignedRange()
CX, CY, Z0 = float((r.GetMin()[0]+r.GetMax()[0])*0.5), float((r.GetMin()[1]+r.GetMax()[1])*0.5), float(r.GetMin()[2])
P("舊箱中心 (%.1f, %.1f) mm,坐在 z=%.1f mm —— 新箱沿用" % (CX*1e3, CY*1e3, Z0*1e3))
st.RemovePrim("/World/Carton")

# ── 材質 ──
def mat(path, rgb, rough=0.75):
    m = UsdShade.Material.Define(st, path); s = UsdShade.Shader.Define(st, path + "/s")
    s.CreateIdAttr("UsdPreviewSurface")
    s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    s.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    m.CreateSurfaceOutput().ConnectToSource(s.ConnectableAPI(), "surface"); return m

CARD = mat("/World/Carton_mat", (0.80, 0.60, 0.38))
MUGC = tuple(int(v)/255.0 for v in a.mug_rgb.split(","))
MUGM = mat("/World/Mug_mat", MUGC, rough=0.45)

def body(path, kinematic):
    """剛體 Xform(馬克杯用;紙箱的剛體由產生器自己處理)"""
    p = UsdGeom.Xform.Define(st, path).GetPrim()
    UsdPhysics.RigidBodyAPI.Apply(p).CreateKinematicEnabledAttr(kinematic)
    UsdPhysics.MassAPI.Apply(p)
    return p

# ── 紙箱:**引用定版產生器的輸出**,不在這裡重寫 ────────────────────
# ★ 2026-09-24 修正:先前這裡是自己重寫的單層四片蓋,那不是我們的設計。
#   定版是 make_carton_P.py:上下兩層蓋(±x 下層 Z_IN、±y 上層 Z_OUT,差 layer_gap)、
#   上層較窄(0.879*hx)、有預抬角 ajar/ajar_in。現在只改尺寸,其餘一字不動。
root = UsdGeom.Xform.Define(st, "/World/Carton")
_rx = UsdGeom.Xformable(root.GetPrim())
_rx.AddTranslateOp().Set(Gf.Vec3d(CX, CY, Z0))
# ★ 擺放方向(使用者 2026-09-24):config 產出的是 280(local x) x 180(local y),
#   鉸鏈沿 local x、上層蓋在 ±local y。--carton_yaw 決定長邊朝哪:
#     0   → 長邊東西向(左右),中縫水平
#     90  → 長邊南北向(前後),中縫垂直
if abs(a.carton_yaw) > 1e-6:
    _rx.AddRotateZOp().Set(float(a.carton_yaw))
# ★ 引用用**檔名**(不是絕對路徑,也不是含目錄的相對路徑):
#   相對路徑是對「來源 layer 的目錄」解析,不是對輸出檔 —— 寫 out/xxx.usd 會在建檔時就找不到,
#   ComputeWorldBound 直接丟 'Invalid prim: null prim'(實測)。
#   做法:把紙箱複製到來源旁邊(建檔時解析得到),再複製到輸出旁邊(交付後解析得到)。
import shutil
_src_dir = os.path.dirname(os.path.abspath(a.scene)) or "."
_out_dir = os.path.dirname(os.path.abspath(a.out)) or "."
os.makedirs(_out_dir, exist_ok=True)
_base = os.path.basename(a.carton)
for _d in {_src_dir, _out_dir}:
    _dst = os.path.join(_d, _base)
    if os.path.abspath(a.carton) != os.path.abspath(_dst):
        shutil.copy(os.path.abspath(a.carton), _dst)
root.GetPrim().GetReferences().AddReference(_base)
_cp = _base
P("紙箱 = 引用 %s(相對路徑)" % _cp)
P("      (定版 make_carton_P.py + configs/box/boxM0921_280x180x150.json,只改 hx/hy/height)")
# ★ 想要蓋子預先掀開,**必須在產生階段**用 make_carton_P.py 的 --ajar / --ajar_in,
#   不能在這裡改蓋子的 xform —— 關節錨點是產生時算好的,事後只動 xform 會讓關節零點對不上,
#   實測:初始角度讀回來仍是 0°,其中一片被憋到 180° 極限甩開(有無摺痕都一樣)。
_missing = [nm for nm in ["base", "fxp", "fxn", "fyp", "fyn"]
            if not st.GetPrimAtPath("/World/Carton/" + nm).IsValid()]
P("      prim 檢查:%s" % ("全部到齊 base/fxp/fxn/fyp/fyn" if not _missing else "★ 缺 %s" % _missing))
_bc2 = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"])
_rb = _bc2.ComputeWorldBound(st.GetPrimAtPath("/World/Carton/base")).ComputeAlignedRange()
P("      箱體(不含蓋)外徑 %.0f x %.0f x %.0f mm"
  % ((_rb.GetMax()[0]-_rb.GetMin()[0])*1e3, (_rb.GetMax()[1]-_rb.GetMin()[1])*1e3,
     (_rb.GetMax()[2]-_rb.GetMin()[2])*1e3))
for _nm in ["fxp", "fxn", "fyp", "fyn"]:
    _fb = _bc2.ComputeWorldBound(st.GetPrimAtPath("/World/Carton/" + _nm)).ComputeAlignedRange()
    P("      %-4s 鉸鏈高 z=%.0f mm ;蓋子 bbox %.0f x %.0f x %.0f mm"
      % (_nm, _fb.GetMin()[2]*1e3, (_fb.GetMax()[0]-_fb.GetMin()[0])*1e3,
         (_fb.GetMax()[1]-_fb.GetMin()[1])*1e3, (_fb.GetMax()[2]-_fb.GetMin()[2])*1e3))

# ── 隙縫實測(不是憑印象)────────────────────────────────────────────
# ★ 蓋子的「寬」是沿鉸鏈的那一軸、「深」是折過去的那一軸。箱子若被轉過 90°,
#   兩者會對調 —— 所以不能寫死軸,要由「蓋子中心相對箱心的偏移方向」判斷。
_cx0 = (_rb.GetMin()[0]+_rb.GetMax()[0])/2; _cy0 = (_rb.GetMin()[1]+_rb.GetMax()[1])/2
_openx = (_rb.GetMax()[0]-_rb.GetMin()[0]) - 2*TB
_openy = (_rb.GetMax()[1]-_rb.GetMin()[1]) - 2*TB
P("  ── 隙縫實測 ──")
P("      箱口 %.0f x %.0f mm" % (_openx*1e3, _openy*1e3))
_info = {}
for _nm in ["fyp", "fyn", "fxp", "fxn"]:
    _b = _bc2.ComputeWorldBound(st.GetPrimAtPath("/World/Carton/"+_nm)).ComputeAlignedRange()
    _c = [(_b.GetMin()[i]+_b.GetMax()[i])/2 for i in range(2)]
    _fold = 0 if abs(_c[0]-_cx0) > abs(_c[1]-_cy0) else 1      # 偏移較大的那軸 = 折疊方向
    _ext = [_b.GetMax()[i]-_b.GetMin()[i] for i in range(2)]
    _info[_nm] = dict(fold=_fold, depth=_ext[_fold], width=_ext[1-_fold],
                      lo=_b.GetMin()[_fold], hi=_b.GetMax()[_fold])
for _lay, _pair in [("上層(外)", ["fyp","fyn"]), ("下層(內)", ["fxp","fxn"])]:
    _a1, _a2 = _info[_pair[0]], _info[_pair[1]]
    _openw = _openy if _a1["fold"] == 0 else _openx          # 寬度方向的開口
    _mid = max(_a1["lo"], _a2["lo"]) - min(_a1["hi"], _a2["hi"])
    P("      %s %s/%s:寬 %.0f mm / 開口 %.0f mm → 兩側各露 %.1f mm ;兩片中縫 %.1f mm"
      % (_lay, _pair[0], _pair[1], _a1["width"]*1e3, _openw*1e3,
         (_openw-_a1["width"])/2*1e3, _mid*1e3))
P("      ★ 上層兩側那兩條是定版 half_out=0.879*hx 的設計(力臂 19mm),不是 bug;")
P("        底下由下層蓋擋著 —— 兩層紙箱本來就長這樣。")


# ── 馬克杯(他們的 STL)──
m = trimesh.load(a.mug)
V = np.asarray(m.vertices, float)
unit = 0.001 if V.ptp(0).max() > 1.0 else 1.0                 # STL 無單位:>1 視為 mm
V = (V - V.mean(0)) * unit                                    # 置中

# ── 杯子躺平(使用者 2026-09-24)────────────────────────────────────
# 繞 y 轉 -90° → 杯軸水平;再繞杯軸滾 90° → 把手朝側面(自然躺平的姿態)。
# 杯子是**動態剛體**,放進去之後姿態由重力決定,這裡只給初始條件。
if a.lie:
    _c, _s = np.cos(-np.pi/2), np.sin(-np.pi/2)
    V = V @ np.array([[_c,0,_s],[0,1,0],[-_s,0,_c]]).T           # Ry(-90)
    _c, _s = np.cos(np.radians(a.mug_roll)), np.sin(np.radians(a.mug_roll))
    V = V @ np.array([[1,0,0],[0,_c,-_s],[0,_s,_c]]).T           # Rx(roll)
    # ★ 對齊規則講清楚:Ry(-90) 之後**杯軸沿 x**。
    #   mug_axis=long → 杯軸順著箱子的長邊;short → 杯軸順著短邊。
    #   先前是用「最長的水平尺寸」對齊,但那是把手方向不是杯軸,會剛好轉 90°。
    _axis_is_x = (a.mug_axis == "long") == (_openx > _openy)
    if not _axis_is_x:
        V = V @ np.array([[0,-1,0],[1,0,0],[0,0,1]]).T           # Rz(90)
    V -= (V.max(0) + V.min(0)) / 2.0
    P("馬克杯:躺平,杯軸順著箱子的%s邊(初始滾轉 %.0f°,實際姿態由重力決定)"
      % ("長" if a.mug_axis == "long" else "短", a.mug_roll))
F = np.asarray(m.faces)
ext = V.max(0) - V.min(0)
P("馬克杯 %.0f x %.0f x %.0f mm  (單位判定 x%.3f)" % (*(ext*1e3), unit))
MZ = Z0 + TB + (-V.min(0)[2]) + 0.002                         # 底面離箱底 1mm
mp = body("/World/Mug", False)
UsdPhysics.MassAPI(mp).CreateDensityAttr(0.0)
UsdPhysics.MassAPI(mp).CreateMassAttr(float(a.mug_mass))      # ★ 量到的質量
UsdGeom.Xformable(mp).AddTranslateOp().Set(Gf.Vec3d(CX, CY, MZ))
g = UsdGeom.Mesh.Define(st, "/World/Mug/geo")
g.CreatePointsAttr([Gf.Vec3f(*map(float, p_)) for p_ in V])
g.CreateFaceVertexIndicesAttr([int(i) for f_ in F for i in f_])
g.CreateFaceVertexCountsAttr([3]*len(F))
g.CreateSubdivisionSchemeAttr().Set("none")
UsdPhysics.CollisionAPI.Apply(g.GetPrim())
mc = UsdPhysics.MeshCollisionAPI.Apply(g.GetPrim())
mc.CreateApproximationAttr("convexDecomposition")             # ★ 杯口是開的, 單一凸包會封死
pc = PhysxSchema.PhysxCollisionAPI.Apply(g.GetPrim())
pc.CreateContactOffsetAttr(0.0012); pc.CreateRestOffsetAttr(0.0)
UsdShade.MaterialBindingAPI(g.GetPrim()).Bind(MUGM)

os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
st.Export(a.out)
P("WROTE %s" % a.out)
# ★ 一律用**量到的**箱口,不要用命令列參數推 —— 箱子換方向後 IW/IL 會反,先前就印錯過
_openz = (_rb.GetMax()[2]-_rb.GetMin()[2]) - TB
P("箱口(實測) %.0f x %.0f x %.0f mm ;杯子 %.0f x %.0f x %.0f mm ;餘裕 %.0f / %.0f / %.0f mm"
  % (_openx*1e3, _openy*1e3, _openz*1e3, *(ext*1e3),
     (_openx-ext[0])*1e3, (_openy-ext[1])*1e3, (_openz-ext[2])*1e3))
sim.close()
