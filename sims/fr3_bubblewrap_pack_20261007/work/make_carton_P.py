#!/usr/bin/env python3
"""make_carton_P.py — Box B + 外包裝 + 可動箱體。  P = Packaged。

以 make_carton_B.py(定版 NOLIM 的建造器)為基礎,只加三件事,幾何與物理係數完全不動:

1. **`--dynamic`** —— base 從 kinematic 改成一般剛體。
   補上 CARTON_QA.md 的 S0 0.10。kinematic 時期「箱體位移 0.00」是恆真的,不算通過紀錄。

2. **`--parcel <seed>`** —— 外包裝貼花(貨運標籤 + 貼紙 + 牛皮紋),
   移植自 `make_carton_A.py`。**visual-only:無 CollisionAPI、無 RigidBody → 物理完全不動。**
   貼圖用相對路徑(`--texprefix`,預設 `../tex`),USD 要跟 tex 目錄保持相對位置。

3. **`--cardboard`** —— 箱體本身改用瓦楞紙貼圖(而不是平面色)。同樣 visual-only。

順手修掉 make_carton_B.py 的兩個 bug:
  * `--preset` 分支用了 `os` / `sys` 但檔案沒 import → NameError,preset 從來沒真正跑成功過
    (NOLIM.meta.json 裡 "preset": None 就是證據)
  * 結尾 print 有 5 個格式符卻只給 4 個參數 → TypeError。因為 Save() 在它前面,
    USD 和 meta.json 已經寫出去了,所以這個 crash 一直沒被發現
"""
import argparse, math, os, sys, json as _json
from isaacsim.simulation_app import SimulationApp
_app = SimulationApp({"headless": True})
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Gf, UsdShade, Sdf

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="carton_P.usd")
ap.add_argument("--hx", type=float, default=0.17)
ap.add_argument("--hy", type=float, default=0.17)
ap.add_argument("--height", type=float, default=0.26)
ap.add_argument("--t", type=float, default=0.0015, help="wall HALF-thickness(定版 0.0015 = 3mm 板)")
ap.add_argument("--layer_gap", type=float, default=-1.0)
ap.add_argument("--density", type=float, default=200.0)
ap.add_argument("--clear", type=float, default=0.0025)
ap.add_argument("--ajar", type=float, default=0.73, help="上層(±y)預抬角。★ 板厚/密度/摺線軟硬/尺寸任一變動都要重校")
ap.add_argument("--ajar_in", type=float, default=1.86, help="下層(±x)預抬角。同上")
ap.add_argument("--inner_only", action="store_true")
ap.add_argument("--no_flaps", action="store_true")
ap.add_argument("--half_out", type=float, default=-1.0,
                help="上層(±y)瓣半寬;<0 = **自動取齊邊**(IN_X - flush_gap)。"
                     "★ 2026-09-26 改:舊的自動值是 0.879*hx,上蓋會比箱子窄 —— "
                     "270 的箱子左右各留 14.7mm 的縫,使用者多次指出這不是要的。"
                     "齊邊之後左右各剩 flush_gap(預設 1mm)。"
                     "要回到舊行為就明確傳 --half_out 0.879*hx 的值。")
ap.add_argument("--flush_gap", type=float, default=0.001,
                help="齊邊時上蓋每邊留多少縫(m)。0.001 = 左右各 1mm")
ap.add_argument("--color", default="0.80,0.60,0.38")
ap.add_argument("--no_limit", action="store_true")
ap.add_argument("--preset", default=None)
ap.add_argument("--config", default=None,
                help="configs/box/<名稱>.json。★ 只填**沒有在命令列指定**的參數 —— "
                     "命令列永遠優先, 所以既有指令一行都不用改。")
# ---- 新增 ----
ap.add_argument("--dynamic", action="store_true",
                help="base 改成一般剛體(非 kinematic)。補上 S0 0.10;箱體會被蓋子的反作用力推動")
ap.add_argument("--parcel", type=int, default=-1,
                help=">=0:加外包裝貼花(標籤+貼紙+牛皮紋),此數字是風格亂數種子。visual-only,物理不動")
ap.add_argument("--cardboard", action="store_true",
                help="箱體用偏灰的回收紙板色(而非預設牛皮色)。visual-only。"
                     "★ 不用貼圖:UsdGeom.Cube 沒有 st primvar,貼圖取樣不到會渲成黑色(踩過)")
ap.add_argument("--anchor", action="store_true",
                help="箱體固定不動(base 設成 kinematic)。用途:要隔離摺線物理時,"
                     "把『箱體被蓋子掀翻』這個干擾變因拿掉。"
                     "★ 這會讓 S0 0.10 **正確地 FAIL**(base 是 kinematic)—— 這是刻意的,"
                     "而且比用 FixedJoint 焊死更誠實:焊死的話 base 仍是 dynamic,"
                     "P0.2 會假 PASS 但其實不可能被推動,那是更陰險的恆真陷阱。"
                     "★ 也不要用 FixedJoint:若不設 localPos0,它會把箱子往世界原點拽(踩過)")
ap.add_argument("--goods_kg", type=float, default=0.0,
                help=">0:在箱內放一塊內容物當配重(質量 kg)。"
                     "★ 沒有配重的話,base 改 dynamic 之後蓋子的反作用力會把 0.3 kg 的空箱掀翻 —— "
                     "實測九顆有六顆被甩下桌。這對應人力評估文件的「重內容物 -> 箱體維持不動,單臂即可」。"
                     "★ 不要改用 world FixedJoint 釘住,那會讓 S0 0.10 重新變成恆真")
ap.add_argument("--texprefix", default="../tex",
                help="貼圖目錄相對於輸出 USD 的路徑。USD 搬家時要一起搬")
a = ap.parse_args()

# ★ --config:把 configs/box/*.json 的值填進**沒有在命令列出現**的參數。
#   命令列優先 → 既有指令行為完全不變。設定檔的註解欄(底線開頭)一律忽略。
if a.config:
    import json as _j, sys as _s
    _p = a.config if os.path.sep in a.config else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "configs", "box", a.config + ".json")
    _c = _j.load(open(_p, encoding="utf-8"))
    _given = set(x.lstrip("-").split("=")[0] for x in _s.argv[1:] if x.startswith("--"))
    _map = {"t_half": "t", "joint_limit_deg": None}      # 設定檔欄名 → argparse 參數名
    _used = []
    for _k, _v in _c.items():
        if _k.startswith("_"):
            continue
        _k2 = _map.get(_k, _k)
        if _k2 and hasattr(a, _k2) and _k2 not in _given:
            setattr(a, _k2, _v); _used.append(_k2)
    print("[config] %s → 套用 %s" % (_p, sorted(_used)))

if a.preset:
    _pdirs = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "params"),
              os.path.expanduser("~/manip/overnight/params"),
              "/isaac-sim/test_scripts/manip_fr3/carton/params"]
    _pf = None
    for _d in _pdirs:
        _c = os.path.join(_d, a.preset if a.preset.endswith(".json") else a.preset + ".json")
        if os.path.exists(_c): _pf = _c; break
    if _pf is None:
        raise SystemExit("找不到 preset %s;找過:%s" % (a.preset, _pdirs))
    _P = _json.load(open(_pf))
    _g, _m, _c2 = _P["geometry"], _P["mass"], _P["precamber"]
    _given = set(x.lstrip("-").split("=")[0] for x in sys.argv[1:] if x.startswith("--"))
    def _set(name, val):
        if name not in _given: setattr(a, name, val)
    _set("hx", _g["hx"]); _set("hy", _g["hy"]); _set("height", _g["height"])
    _set("t", _g["t_half"]); _set("clear", _g["clear"])
    _set("layer_gap", _g["layer_gap"]); _set("half_out", _g["half_out"])
    _set("density", _m["density"])
    _set("ajar_in", _c2["ajar_in_deg"]); _set("ajar", _c2["ajar_deg"])
    print("PRESET %s <- %s" % (_P["version"], _pf))
    if _given: print("  命令列覆寫: %s" % sorted(_given))

hx, hy, H, t, CL = a.hx, a.hy, a.height, a.t, a.clear
IN_X, IN_Y = hx - t, hy - t
HALF = min(IN_X, IN_Y) - CL
# ★ 2026-09-26:自動值改成齊邊。舊值 0.879*hx 會讓上蓋左右各少 14.7mm(270 箱)。
HALF_OUT = (IN_X - a.flush_gap) if a.half_out < 0 else a.half_out
if HALF_OUT >= IN_X:
    raise SystemExit("half_out %.4f 必須小於內層鉸接 IN_X %.4f(否則上層蓋壓在下層蓋根部,力臂→0)"
                     % (HALF_OUT, IN_X))

stage = Usd.Stage.CreateNew(a.out)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/Box").GetPrim())
CARD = Gf.Vec3f(*[float(v) for v in a.color.split(",")])
if a.cardboard: CARD = Gf.Vec3f(0.72, 0.62, 0.50)   # 回收紙板灰褐
FLAPCOL = Gf.Vec3f(min(CARD[0]*1.08,1.0), min(CARD[1]*1.1,1.0), min(CARD[2]*1.1,1.0))
TEX = a.texprefix.rstrip("/")

mat = "/Box/cardMat"; _matp = UsdShade.Material.Define(stage, mat)
pm = UsdPhysics.MaterialAPI.Apply(stage.GetPrimAtPath(mat))
pm.CreateStaticFrictionAttr(0.5); pm.CreateDynamicFrictionAttr(0.45); pm.CreateRestitutionAttr(0.0)
# ★ 2026-08-17:cardMat 原本**只有** physics MaterialAPI、沒有 surface shader。
#   RTX 把它當可視材質解析時得到「沒有 surface」→ 整個箱子渲染成**純黑**。
#   實際踩到:九箱影片第一版九顆全黑,外包裝完全看不到(貼圖路徑其實是對的)。
#   修法:補一個 UsdPreviewSurface,顏色就是紙板色 —— 不管渲染器走哪條路徑都是紙板色。
_cs = UsdShade.Shader.Define(stage, mat + "/Shader")
_cs.SetSourceAsset("OmniPBR.mdl", "mdl")
_cs.SetSourceAssetSubIdentifier("OmniPBR", "mdl")
_cs.CreateInput("diffuse_color_constant", Sdf.ValueTypeNames.Color3f).Set(CARD)
_cs.CreateInput("reflection_roughness_constant", Sdf.ValueTypeNames.Float).Set(0.92)
_cs.CreateInput("metallic_constant", Sdf.ValueTypeNames.Float).Set(0.0)
_matp.CreateSurfaceOutput("mdl").ConnectToSource(_cs.ConnectableAPI(), "out")
_matp.CreateDisplacementOutput("mdl").ConnectToSource(_cs.ConnectableAPI(), "out")
_matp.CreateVolumeOutput("mdl").ConnectToSource(_cs.ConnectableAPI(), "out")
def bind(p): UsdShade.MaterialBindingAPI(p).Bind(UsdShade.Material(stage.GetPrimAtPath(mat)),
                                                 materialPurpose="physics")

# ─────────── 貼圖材質:用 OmniPBR MDL,不用 UsdPreviewSurface ───────────
# ★ 2026-08-17 踩到:UsdPreviewSurface + UsdUVTexture 在 Isaac 的 RTX 下**貼圖讀不進來**,
#   貼花整片渲成黑色方塊(看起來像破洞)。st primvar 有、貼圖檔路徑也對(驗證器確認過),
#   問題在 renderer 這一端。
#   OmniPBR.mdl 是 Omniverse 原生材質,RTX 一定支援 —— 改走這條。
def tex_mat(path, texfile, rough=0.85, cutout=False):
    m = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/Shader")
    sh.SetSourceAsset("OmniPBR.mdl", "mdl")
    sh.SetSourceAssetSubIdentifier("OmniPBR", "mdl")
    sh.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset).Set(texfile)
    # ★ OmniPBR 的 diffuse_color_constant 預設是 0.2 灰,會跟貼圖相乘 -> 貼圖整體變暗
    #   (實測:標籤 mean 196 的圖渲出來幾乎看不清,中灰的牛皮紋直接變全黑)。
    #   明確設成白色,貼圖才是它原本的亮度。
    sh.CreateInput("diffuse_color_constant", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(1, 1, 1))
    sh.CreateInput("diffuse_tint", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(1, 1, 1))
    sh.CreateInput("reflection_roughness_constant", Sdf.ValueTypeNames.Float).Set(rough)
    sh.CreateInput("metallic_constant", Sdf.ValueTypeNames.Float).Set(0.0)
    # ★ 貼紙是去背 PNG:不開 opacity 的話,alpha=0 的區域會用 RGB(=0)渲成**黑色方框**
    #   (實測:綠色圓標周圍一圈黑)。用貼圖自己的 alpha 當裁切遮罩。
    if cutout:
        sh.CreateInput("enable_opacity", Sdf.ValueTypeNames.Bool).Set(True)
        sh.CreateInput("opacity_texture", Sdf.ValueTypeNames.Asset).Set(texfile)
        sh.CreateInput("opacity_mode", Sdf.ValueTypeNames.Int).Set(0)     # 0 = mono_alpha
        sh.CreateInput("opacity_threshold", Sdf.ValueTypeNames.Float).Set(0.35)
    m.CreateSurfaceOutput("mdl").ConnectToSource(sh.ConnectableAPI(), "out")
    m.CreateDisplacementOutput("mdl").ConnectToSource(sh.ConnectableAPI(), "out")
    m.CreateVolumeOutput("mdl").ConnectToSource(sh.ConnectableAPI(), "out")
    return m


def decal(name, parent, center, uvec, vvec, texfile, cutout=False):
    """visual-only 四邊形貼片。無 CollisionAPI、無 RigidBody → 物理完全不動。"""
    import numpy as _np
    c = _np.array(center, float); u = _np.array(uvec, float); v = _np.array(vvec, float)
    pts = [c-u/2-v/2, c+u/2-v/2, c+u/2+v/2, c-u/2+v/2]
    mesh = UsdGeom.Mesh.Define(stage, f"{parent}/{name}")
    mesh.CreatePointsAttr([Gf.Vec3f(*p) for p in pts])
    mesh.CreateFaceVertexCountsAttr([4]); mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    n = _np.cross(u, v); n = n / (_np.linalg.norm(n) + 1e-9)
    mesh.CreateNormalsAttr([Gf.Vec3f(*n)] * 4)
    pv = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
                                                 UsdGeom.Tokens.vertex)
    pv.Set([Gf.Vec2f(0, 0), Gf.Vec2f(1, 0), Gf.Vec2f(1, 1), Gf.Vec2f(0, 1)])
    UsdShade.MaterialBindingAPI(mesh.GetPrim()).Bind(
        tex_mat(f"{parent}/{name}Mat", texfile, cutout=cutout))

def coll(par, nm, c, h, col=CARD, tex=None):
    cu = UsdGeom.Cube.Define(stage, f"{par}/{nm}"); cu.CreateSizeAttr(2.0)
    cu.AddTranslateOp().Set(Gf.Vec3d(*c)); cu.AddScaleOp().Set(Gf.Vec3f(*h))
    cu.CreateDisplayColorAttr([col]); UsdPhysics.CollisionAPI.Apply(cu.GetPrim()); bind(cu.GetPrim())
    pc = PhysxSchema.PhysxCollisionAPI.Apply(cu.GetPrim())
    pc.CreateContactOffsetAttr(0.001); pc.CreateRestOffsetAttr(0.0)
    if tex:
        UsdShade.MaterialBindingAPI(cu.GetPrim()).Bind(tex_mat(f"{par}/{nm}Mat", tex))
    return cu

# ---- base ----
base = UsdGeom.Xform.Define(stage, "/Box/base")
rb = UsdPhysics.RigidBodyAPI.Apply(base.GetPrim())
# ★ S0 0.10:dynamic 才有鑑別力。kinematic 下「箱體沒被推動」是恆真的。
rb.CreateKinematicEnabledAttr((not a.dynamic) or a.anchor)   # --anchor -> 固定不動
UsdPhysics.MassAPI.Apply(base.GetPrim()).CreateDensityAttr(a.density)
# ★ 2026-09-26:鉸鏈高度(Z_IN/Z_OUT)原本定義在建牆之後,但建牆現在要用它們,
#   所以往前搬。順序問題今天已經踩過一次(wrap_sim.py 的 lid_pose NameError)。
REACH_X, REACH_Y = IN_X - 0.0015, IN_Y - 0.0015
G = 0.0015
Z_OUT = H - t
LAYER = (2*t + G) if a.layer_gap < 0 else a.layer_gap
Z_IN  = Z_OUT - LAYER

coll("/Box/base", "bottom", (0, 0, t), (hx, hy, t))
# ★ 2026-09-26(使用者:「下蓋與紙箱壁穿模了」→「把紙箱壁與底蓋的連接處 順應 底蓋的位置 降低」)
#   四面牆改成**各自的高度**,讓箱壁在跟蓋子交接處讓位給蓋子的板厚。
#   為什麼原本會穿:鉸鏈放在箱壁內面(x = IN_X),但蓋子是 2t 厚的板 ——
#   蓋子一旦傾斜,它的外上角就掃進箱壁那 2t 的帶子,而且此時還在箱口以下。
#   解析掃掠(0~180°,每 0.5°)實測:牆頂 = 該面蓋子的鉸鏈 z − 2t 時,全程 0/361 重疊。
#   只到「鉸鏈 z」還不夠(180/361),因為蓋子全開時是水平朝外躺在 [鉸鏈−2t, 鉸鏈]。
WTOP_X = H if a.no_flaps else (Z_IN  - 2*t)     # ±x 牆:下層蓋在這兩面
WTOP_Y = H if a.no_flaps else (Z_OUT - 2*t)     # ±y 牆:上層蓋在這兩面
coll("/Box/base", "wxp", ( hx, 0, WTOP_X*0.5), (t, hy, WTOP_X*0.5))
coll("/Box/base", "wxn", (-hx, 0, WTOP_X*0.5), (t, hy, WTOP_X*0.5))
coll("/Box/base", "wyp", (0,  hy, WTOP_Y*0.5), (hx, t, WTOP_Y*0.5))
coll("/Box/base", "wyn", (0, -hy, WTOP_Y*0.5), (hx, t, WTOP_Y*0.5))

def make_flap(name, hinge, yaw_deg, reach, zlift, ajar_deg=0.0, half=None):
    fp = f"/Box/{name}"
    fx = UsdGeom.Xform.Define(stage, fp)
    fx.AddTranslateOp().Set(Gf.Vec3d(*hinge))
    if yaw_deg: fx.AddRotateZOp().Set(float(yaw_deg))
    if ajar_deg: fx.AddRotateXOp().Set(float(-ajar_deg))
    UsdPhysics.RigidBodyAPI.Apply(fx.GetPrim())
    _m = UsdPhysics.MassAPI.Apply(fx.GetPrim()); _m.CreateDensityAttr(a.density)
    # 等效慣量 = 定版 armature 0.006。crease 當外加剛體力矩會繞過 armature,
    # 不設這個的話顯式阻尼穩定條件 c*dt/I < 2 破功 → 力矩每步正負跳、發散(踩過)
    _m.CreateDiagonalInertiaAttr(Gf.Vec3f(0.006, 0.006, 0.006))
    _m.CreatePrincipalAxesAttr(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
    g = UsdGeom.Cube.Define(stage, fp + "/geo"); g.CreateSizeAttr(2.0)
    g.AddTranslateOp().Set(Gf.Vec3d(0, -reach/2, zlift))
    g.AddScaleOp().Set(Gf.Vec3f(HALF if half is None else half, reach/2, t))
    g.CreateDisplayColorAttr([FLAPCOL]); UsdPhysics.CollisionAPI.Apply(g.GetPrim()); bind(g.GetPrim())
    pc = PhysxSchema.PhysxCollisionAPI.Apply(g.GetPrim())
    pc.CreateContactOffsetAttr(0.001); pc.CreateRestOffsetAttr(0.0)
    j = UsdPhysics.RevoluteJoint.Define(stage, f"/Box/crease_{name}")
    j.CreateBody0Rel().SetTargets(["/Box/base"]); j.CreateBody1Rel().SetTargets([fp])
    j.CreateAxisAttr("X")
    j.CreateLocalPos0Attr(Gf.Vec3f(*hinge)); j.CreateLocalPos1Attr(Gf.Vec3f(0, 0, 0))
    if yaw_deg:
        h2 = math.radians(yaw_deg)/2.0
        j.CreateLocalRot0Attr(Gf.Quatf(float(math.cos(h2)), 0.0, 0.0, float(math.sin(h2))))
    if not a.no_limit:
        j.CreateLowerLimitAttr(-185.0); j.CreateUpperLimitAttr(185.0)
    j.CreateCollisionEnabledAttr(True)
    PhysxSchema.PhysxJointAPI.Apply(j.GetPrim()).CreateArmatureAttr(0.006)
    return j

if not a.no_flaps:
    make_flap("fxp", ( IN_X, 0, Z_IN),  -90.0, REACH_X, t, a.ajar_in)
    make_flap("fxn", (-IN_X, 0, Z_IN),   90.0, REACH_X, t, a.ajar_in)
    if not a.inner_only:
        make_flap("fyp", (0,  IN_Y, Z_OUT),   0.0, REACH_Y, t, a.ajar, HALF_OUT)
        make_flap("fyn", (0, -IN_Y, Z_OUT), 180.0, REACH_Y, t, a.ajar, HALF_OUT)

# ─────────── 內容物(配重) ───────────
# 需要多重:要抵抗蓋子把箱子掀翻,m > tau_max / (g * 半寬)。
# 以定版尺寸:4.3 N*m / (9.81 * 0.17) = 2.6 kg,取 1.5 倍餘裕約 4 kg —— 對 340mm 紙箱很正常。
if a.goods_kg > 0:
    gh = 0.62 * H                      # 高度只到箱高六成,不會撐到蓋子
    gx, gy = 0.80 * IN_X, 0.80 * IN_Y  # 四周留縫,不擠著箱壁
    gp = "/Box/goods"
    gx_prim = UsdGeom.Xform.Define(stage, gp)
    gx_prim.AddTranslateOp().Set(Gf.Vec3d(0, 0, 2*t + gh/2))
    UsdPhysics.RigidBodyAPI.Apply(gx_prim.GetPrim())
    UsdPhysics.MassAPI.Apply(gx_prim.GetPrim()).CreateMassAttr(a.goods_kg)  # 這裡刻意寫死質量
    gcu = UsdGeom.Cube.Define(stage, gp + "/geo"); gcu.CreateSizeAttr(2.0)
    gcu.AddScaleOp().Set(Gf.Vec3f(gx, gy, gh/2))
    gcu.CreateDisplayColorAttr([Gf.Vec3f(0.55, 0.42, 0.30)])
    UsdPhysics.CollisionAPI.Apply(gcu.GetPrim()); bind(gcu.GetPrim())
    _pc = PhysxSchema.PhysxCollisionAPI.Apply(gcu.GetPrim())
    _pc.CreateContactOffsetAttr(0.001); _pc.CreateRestOffsetAttr(0.0)

# ─────────── 外包裝 ───────────
_parcel_files = []
if a.parcel >= 0:
    import random
    rng = random.Random(a.parcel)
    # ★ 2026-08-18:大張貨運標籤拿掉。實測它在 RTX 下一律渲成**實心黑方塊**,
    #   看起來像破洞,比沒有更糟。試過五種做法全部無效:
    #     UsdPreviewSurface -> OmniPBR、相對路徑 -> 絕對路徑、
    #     diffuse_color_constant/diffuse_tint 設白、RGB -> RGBA 轉檔、enable_opacity 開 cutout。
    #   而**同一段程式、同一個 decal() 函式**畫出來的貼紙(sticker_*.png)渲染完美。
    #   差別只剩貼圖檔本身(label_*.png 是 680x440,貼紙是 240x240),原因未查明。
    #   結論:只留貼紙。貼紙就是外包裝,而且它是對的。
    stks = [f"{TEX}/sticker_fragile.png", f"{TEX}/sticker_up.png", f"{TEX}/sticker_round_0.png"]
    e = 0.002
    # ★ 貼片一律**固定實體尺寸**,不隨箱子縮放。
    #   實測規律:貼片越大越容易整片渲成黑色 —— 大張標籤(0.30m)一定黑,
    #   最大箱的貼紙(0.136m)也黑,小箱的貼紙(0.087m)正常。
    #   推測 OmniPBR 沒有吃 mesh 的 st primvar 而是用某種世界尺度的 UV,
    #   超過某個尺寸就取樣到範圍外。**未查明,但固定尺寸可重現地有效。**
    #   附帶好處:真實世界的貼紙本來就是固定尺寸,不會跟著箱子變大。
    SK = 0.075
    # 前面(-y)牆兩張貼紙
    for j, (ox, oz) in enumerate([(-0.42, 0.62), (0.40, 0.40)]):
        decal("stk_y%d" % j, "/Box/base",
              (ox * hx, -(hy + t + e), H * oz),
              (SK, 0, 0), (0, 0, SK),
              stks[rng.randrange(len(stks))], cutout=True)
    # 右側(+x)牆一張
    decal("stk_x0", "/Box/base",
          (hx + t + e, rng.uniform(-0.35, 0.35) * hy, H * rng.uniform(0.45, 0.70)),
          (0, SK, 0), (0, 0, SK),
          stks[rng.randrange(len(stks))], cutout=True)
    # 左側(-x)牆一張,轉到另一邊也看得到
    decal("stk_x1", "/Box/base",
          (-(hx + t + e), rng.uniform(-0.35, 0.35) * hy, H * rng.uniform(0.45, 0.70)),
          (0, SK * 0.95, 0), (0, 0, SK * 0.95),
          stks[rng.randrange(len(stks))], cutout=True)
    _parcel_files = list(stks)

BUILDER_VERSION = "make_carton_P/2026-08-17"
_meta = {
  "builder_version": BUILDER_VERSION,
  "_note": "衍生量由建造端輸出。消費端(qa_carton / shot / stair2)讀這裡,不要自己算公式",
  "_based_on": "make_carton_B/2026-07-30(幾何與物理係數完全相同;新增 dynamic base / 外包裝)",
  "inputs": {k: (v if not isinstance(v, (list, tuple)) else list(v))
             for k, v in sorted(vars(a).items()) if not k.startswith("_")},
  "derived": {
    "board_thickness": 2*t,
    "wall_inner_x": IN_X, "wall_inner_y": IN_Y,
    "wall_top_z": H,
    # ★ 2026-09-26:四面牆各自的頂端高度(讓位給蓋子板厚)。消費端要判斷「箱口多高」
    #   應該讀這兩個,不要再讀 wall_top_z —— 那個現在只是 height 參數本身。
    "wall_top_x": WTOP_X, "wall_top_y": WTOP_Y,
    "_wall_top_note": "±x 牆頂 = 下鉸鏈 - 2t、±y 牆頂 = 上鉸鏈 - 2t。"
                      "解析掃掠 0~180° 實測這樣蓋子才 0 重疊箱壁;只到鉸鏈高度還有 180/361 重疊",
    "upper_hinge_z": Z_OUT, "lower_hinge_z": Z_IN,
    "layer_gap": LAYER,
    "flap_half_width_lower": HALF, "flap_half_width_upper": HALF_OUT,
    "reach_x": REACH_X, "reach_y": REACH_Y,
    "lever_arm": IN_X - HALF_OUT,
    "_lever_note": "上層蓋側邊到下層蓋摺線的距離。壓上層蓋推下層蓋的力臂",
    "force_cap_torque_Nm_at_30N": 30.0 * REACH_Y,
    "_force_cap_note": "★ 力上限是「力的上限」不是力矩上限:τ_max = 30 N × 力臂。尺寸不同 → 上限不同,不可共用"
  },
  "mass": {
    "mode": "density", "density": a.density,
    "lower_flap_kg": (2*HALF)*REACH_X*2*t*a.density,
    "upper_flap_kg": (2*HALF_OUT)*REACH_Y*2*t*a.density
  },
  "precamber": {"ajar_in_deg": a.ajar_in, "ajar_deg": a.ajar,
                "_note": "上翹量只對這組板厚+密度+摺線軟硬+尺寸有效,任一項變動要重新校準"},
  "goods": {"kg": a.goods_kg,
            "_note": ("箱內配重。沒有它的話 dynamic base 會被蓋子的反作用力掀翻(實測 9 顆倒 6 顆)。"
                      "質量刻意寫死 —— 它代表『裝了東西的箱子』,不是紙板")
            } if a.goods_kg > 0 else None,
  "anchored": bool(a.anchor),
  "_anchored_note": ("★ 箱體固定不動(base=kinematic)。S0 0.10 會 FAIL —— 這是刻意的。"
                     "此模式用於隔離摺線物理,不可當成箱體可動性的通過紀錄。"
                     "『箱體會被蓋子掀翻』另有獨立實測記錄(NINE_LESSONS E-4:九顆倒六顆)"
                     ) if a.anchor else None,
  "base_dynamic": bool(a.dynamic),
  "_base_dynamic_note": ("dynamic:S0 0.10 有鑑別力" if a.dynamic else
                         "kinematic:S0 0.10 未通過,且『箱體沒被推動』這類檢查恆真(VACUOUS)"),
  "packaging": {"parcel_seed": a.parcel, "cardboard": bool(a.cardboard),
                "texprefix": TEX, "textures": _parcel_files,
                "_note": "貼花是 visual-only(無 CollisionAPI/RigidBody),物理與無包裝版完全相同。"
                         "貼圖用相對路徑 → USD 搬家要連 tex 目錄一起搬"},
  "prims": {
    "carton_root_hint": "/Box",
    "base": "/Box/base", "walls": ["wxp","wxn","wyp","wyn"],
    "lower_flaps": ["fxp","fxn"], "upper_flaps": ["fyp","fyn"],
    "joints": ["crease_fxp","crease_fxn","crease_fyp","crease_fyn"],
    "geo_child": "geo",
    "_crease_note": "joint 無 drive。彈性由 runner 每一個物理步外加,見 crease_physics.py"
  }
}
_mp = a.out.rsplit(".", 1)[0] + ".meta.json"
_json.dump(_meta, open(_mp, "w"), indent=2, ensure_ascii=False)
stage.GetRootLayer().Save()

print("WROTE %s + %s" % (a.out, _mp))
print("  外尺寸 %.0f x %.0f x %.0f mm | 板厚 %.1f mm | density %.0f"
      % (2*hx*1000, 2*hy*1000, H*1000, 2*t*1000, a.density))
print("  base = %s%s" % ("DYNAMIC 剛體(S0 0.10 有鑑別力)" if a.dynamic
                         else "kinematic(★ S0 0.10 未通過)",
                         "" if a.dynamic else " — 三個 QA 檢查會是 VACUOUS"))
print("  上層半寬 %.4f(內層鉸接 ±%.4f)→ 力臂 %.1f mm" % (HALF_OUT, IN_X, (IN_X-HALF_OUT)*1000))
print("  層間錯開 LAYER=%.4f m;下層鉸接 z=%.4f、上層 z=%.4f(鋼緣 z=%.4f)" % (LAYER, Z_IN, Z_OUT, H))
print("  力矩上限(30 N × 力臂 %.4f m)= %.3f N*m   ★ 這顆箱子專屬,不可沿用別顆" % (REACH_Y, 30.0*REACH_Y))
print("  預抬 上 %.2f° / 下 %.2f°  ★ 尺寸或摺線軟硬變了就必須重校" % (a.ajar, a.ajar_in))
if a.anchor:
    print("  ★ 箱體已固定(base=kinematic)-> S0 0.10 會 FAIL,這是刻意的(隔離變因)")
if a.goods_kg > 0:
    print("  內容物配重 %.2f kg(抗掀翻門檻 %.2f kg = tau_cap/(g*hx))"
          % (a.goods_kg, (30.0*REACH_Y)/(9.81*hx)))
if a.parcel >= 0:
    print("  外包裝 seed=%d:%s" % (a.parcel, ", ".join(_parcel_files)))
print("  質量(密度×體積):下層蓋 %.4f kg / 上層蓋 %.4f kg"
      % ((2*HALF)*REACH_X*2*t*a.density, (2*HALF_OUT)*REACH_Y*2*t*a.density))
_app.close()
