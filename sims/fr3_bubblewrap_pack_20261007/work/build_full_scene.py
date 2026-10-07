#!/usr/bin/env python3
"""build_full_scene.py — 完整交付場景:他們的手臂 + 桌子 + 我們的紙箱 + 包材 + 杯子。

  /isaac-sim/python.sh build_full_scene.py \
      --scene scene.usd --carton out/carton_ppt130.usd \
      --wrap out_final130/wrap.npz --mug mug.stl --out out/scene_full.usd

★ 手臂與桌子完全不動(沿用 deliver_mission0921/build_scene.py 的原則)。
★ 包材是把模擬跑完的頂點直接寫成靜態 Mesh —— surface deformable 的狀態 USD 帶不了,
  但交付場景要的是「包好的樣子」,所以存成固定幾何。
★ 紙箱綁不透明材質、包材 opacity=1.0:2026-09-26 實測,opacity<1 的布會被畫在
  所有東西前面(連翻到箱外的蓋子都被蓋住),只有 1.0 不會。
"""
import argparse, os
import numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--scene",  required=True, help="他們的手臂場景 USD")
ap.add_argument("--carton", required=True)
ap.add_argument("--wrap",   required=True, help="wrap.npz(sheet/mug 頂點)")
ap.add_argument("--mug",    default="mug.stl")
ap.add_argument("--out",    default="out/scene_full.usd")
ap.add_argument("--res",    type=int, default=34)
ap.add_argument("--tex",    default="bubble_normal.png")
ap.add_argument("--tex_mm", type=float, default=200.0)
ap.add_argument("--yaw", type=float, default=90.0,
                help="★ 整組(箱+包材+杯子)繞 z 轉幾度。使用者 2026-09-26:"
                     "「長邊平行 y、杯口垂直 y」。未轉時紙箱 270 沿 x、杯軸沿 y;"
                     "轉 90° 之後 270 沿 y、杯軸沿 x —— 兩個條件同時滿足,"
                     "而且 PPT 的構造不變(115mm 那對蓋子仍鉸接在 270 那條邊)。"
                     "手臂在 y=±455,桌長邊也是 y。")
ap.add_argument("--place",  default="0,0,0", help="整組(箱+包裹)放在桌上的 xyz 位移(m)")
a = ap.parse_args()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)

from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
from pxr import Usd, UsdGeom, UsdShade, UsdPhysics, Sdf, Gf, Vt
import trimesh
P = lambda *s: print(*s, flush=True)

st = Usd.Stage.Open(a.scene)
P("載入手臂場景 %s" % a.scene)
DX, DY, DZ = [float(v) for v in a.place.split(",")]

def vmat(path, col, op=1.0, rough=0.5):
    m = UsdShade.Material.Define(st, path)
    sh = UsdShade.Shader.Define(st, path + "/S"); sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*col))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(op)
    sh.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.5 if op >= 0.99 else 1.0)
    m.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return m

# ── 舊的紙箱/包材先清掉,再放新的 ─────────────────────────────────────
for p in ("/World/Carton", "/World/Box", "/World/Wrap", "/World/MugPacked"):
    if st.GetPrimAtPath(p).IsValid():
        st.RemovePrim(p); P("  移除舊的 %s" % p)

ROOT = UsdGeom.Xform.Define(st, "/World/Packed")
_xr = UsdGeom.Xformable(ROOT)
_xr.AddTranslateOp().Set(Gf.Vec3d(DX, DY, DZ))
_xr.AddRotateZOp().Set(float(a.yaw))
P("整組繞 z 轉 %.0f°(長邊 270 → y;杯口垂直 y);放在 (%.0f, %.0f, %.0f) mm"
  % (a.yaw, DX*1e3, DY*1e3, DZ*1e3))

bx = st.DefinePrim("/World/Packed/Box", "Xform")
bx.GetReferences().AddReference(os.path.abspath(a.carton))
CB = vmat("/World/Packed/cartonmat", (0.62, 0.46, 0.29), 1.0, 0.85)
n_ = 0
for p in Usd.PrimRange(bx):
    if p.IsA(UsdGeom.Gprim):
        UsdShade.MaterialBindingAPI.Apply(p).Bind(CB, UsdShade.Tokens.strongerThanDescendants); n_ += 1
P("  紙箱 %s(%d 個 Gprim 綁不透明材質)" % (a.carton, n_))

# ── 包材:把模擬結果寫成靜態 Mesh ─────────────────────────────────────
d = np.load(a.wrap); SP = d["sheet"]; MW = d["mug"]
n = a.res
tris = []
for j in range(n):
    for i in range(n):
        A = j*(n+1)+i
        tris += [(A, A+1, A+n+2), (A, A+n+2, A+n+1)]
sh = UsdGeom.Mesh.Define(st, "/World/Packed/Wrap")
sh.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*[float(x) for x in p]) for p in SP]))
sh.GetFaceVertexCountsAttr().Set([3]*len(tris))
sh.GetFaceVertexIndicesAttr().Set([int(k) for t in tris for k in t])
sh.CreateDoubleSidedAttr(True)
WM = vmat("/World/Packed/filmmat", (0.90, 0.95, 0.97), 1.0, 0.18)
UsdShade.MaterialBindingAPI.Apply(sh.GetPrim()).Bind(WM)
e = (SP.max(0) - SP.min(0))*1e3
P("  包材 %d 頂點,bbox %.0f x %.0f x %.0f mm" % (len(SP), *e))

# ── 杯子:用模擬結束時的頂點 ──────────────────────────────────────────
F = np.asarray(trimesh.load(a.mug).faces)
mg = UsdGeom.Mesh.Define(st, "/World/Packed/Mug")
mg.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*[float(x) for x in p]) for p in MW]))
mg.GetFaceVertexCountsAttr().Set([3]*len(F))
mg.GetFaceVertexIndicesAttr().Set([int(k) for t in F for k in t])
MM = vmat("/World/Packed/mugmat", (144/255./1.19*0.894, 163/255./1.11*0.931, 189/255./1.005), 1.0, 0.40)
UsdShade.MaterialBindingAPI.Apply(mg.GetPrim()).Bind(MM)
em = (MW.max(0) - MW.min(0))*1e3
P("  杯子 %d 頂點,bbox %.0f x %.0f x %.0f mm" % (len(MW), *em))

import math
_c, _s = math.cos(math.radians(a.yaw)), math.sin(math.radians(a.yaw))
def _rot(Q):
    R = Q.copy(); R[:, 0] = Q[:, 0]*_c - Q[:, 1]*_s; R[:, 1] = Q[:, 0]*_s + Q[:, 1]*_c
    return R
_e2 = (_rot(SP).max(0) - _rot(SP).min(0))*1e3
_m2 = (_rot(MW).max(0) - _rot(MW).min(0))*1e3
P("\n轉 %.0f° 之後(世界座標):" % a.yaw)
P("  包材 %.0f (x) x %.0f (y) x %.0f (z) mm" % tuple(_e2))
P("  杯子 %.0f (x) x %.0f (y) x %.0f (z) mm ← x 較長 = 杯軸沿 x = 杯口垂直 y" % tuple(_m2))
P("  紙箱內腔 224 (x) x 264 (y) mm(270 沿 y)")
P("  ⇒ x %s、y %s" % ("OK" if _e2[0] < 224 else "超出", "OK" if _e2[1] < 264 else "超出"))

st.GetRootLayer().Export(os.path.abspath(a.out))
P("\n→ %s" % os.path.abspath(a.out))
P("   /World/Packed 底下:Box(紙箱)+ Wrap(包材)+ Mug(杯子);手臂與桌子未更動")
sim.close()
