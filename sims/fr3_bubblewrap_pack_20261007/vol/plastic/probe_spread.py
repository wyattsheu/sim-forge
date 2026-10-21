#!/usr/bin/env python3
"""probe_spread.py — (A2) 烘焙 rest 時把疊層撐開 / 指定自碰撞濾除姿態,自碰撞還在不在(volume 板)。
板 200x100x4(manual 50x25x1,E 2e3,self collision on、filter 2*rest = 1 mm,cont 2 / rest 0.5 mm,同 wrap_vol)。
尖端綁 kinematic 桿沿半圓對折(上層表面在下層上方 --gap_mm),--bake_at pre:放手前 0.2 s 烘焙;press:壓住時烘焙(層貼著,同 wrap 關蓋時)。
烘焙 = rest ← spread_rest.solve(當下, d = --spread_mm)(0 = 當下原樣)+ 可選 DeformablePoseAPI "selfCollisionFilterPose"(--fpose none|flat|rest|cur)
       + SetActive(False)→step→SetActive(True)(同 wrap_vol --plastic_how step),points = 當下。
壓板:放手 1 s 後壓到絕對高度 --press_abs_mm(預設 ZB + 2T + 1 = 10 mm:兩層 8 mm + 1 mm,層間被擠到 < 2·restOffset);
     bake_at press:壓住 1.2 s 後烘焙,再多壓 --press2_mm。
量:vol_pen 自穿(flat 為參考)、中面層距(上層 column 中面 − 下層 column 中面,壓板正下方)、USD selfCollisionFilterDistance 實際值。
    /isaac-sim/python.sh plastic/probe_spread.py --bake 1 --spread_mm 5 --fpose rest --bake_at press
"""
import os, sys, argparse, time
import numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--bake", type=int, default=1, help="0 = 對照(不烘焙);1 = 烘焙;2 = 只重建(rest 不改)")
ap.add_argument("--spread_mm", type=float, default=0.0)
ap.add_argument("--fpose", default="none", choices=["none", "flat", "rest", "cur"])
ap.add_argument("--filter_mm", type=float, default=-1)
ap.add_argument("--bake_at", default="press", choices=["pre", "press"])
ap.add_argument("--press_abs_mm", type=float, default=-1)
ap.add_argument("--press2_mm", type=float, default=1.0)
ap.add_argument("--cont_mm", type=float, default=2.0)
ap.add_argument("--gap_mm", type=float, default=3.0)
ap.add_argument("--young", type=float, default=2e3)
ap.add_argument("--early_fpose", type=int, default=0, help="1 = 建立時(t=0)就套 fpose flat(檢查 PoseAPI 本身不壞事)")
ap.add_argument("--tag", default="")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
tag = a.tag or "sp_b%d_d%g_f%s_%s_fl%g_q%g_c%g" % (a.bake, a.spread_mm, a.fpose, a.bake_at, a.filter_mm, a.press2_mm, a.cont_mm)
OUT = os.path.join(HERE, "spread"); os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, tag + ".log"), "w")
def P(*s):
    m = " ".join(str(x) for x in s); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from isaacsim.core.prims import SingleXFormPrim
from pxr import UsdGeom, PhysxSchema, Sdf, Vt, Gf
import omni.usd
sys.path.insert(0, VOL); sys.path.insert(0, HERE)
import volcommon as VC, vol_pen as VP, spread_rest as SR
P("=== probe_spread %s ===" % tag); P("args:", vars(a))
dt = 1 / 120.0
world = World(physics_dt=dt, rendering_dt=dt); world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene")); pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
LX, LY, T = 0.2, 0.1, 0.004; ZB = 0.001; PATH = "/World/plate"; REST_OFF = 0.0005; HX = 0.100
VC.build_plate(st, PATH, LX, T, ZB, "manual", nxy=25, nz=1, nx=50, youngs=a.young, cx=LX / 2, cy=0, size_y=LY, solver=64,
               self_coll=True, self_filter=2 * REST_OFF, cont=a.cont_mm / 1e3, rest=REST_OFF, P=P)
mesh = VC.Mesh(st, PATH); FL0 = mesh.pts(); TE = mesh.tets(); NV = len(FL0); NC = NV // 2
def set_fpose(prim, pts, name="scf"):
    prim.ApplyAPI("OmniPhysicsDeformablePoseAPI", name)
    prim.CreateAttribute("deformablePose:%s:omniphysics:purposes" % name, Sdf.ValueTypeNames.TokenArray).Set(["selfCollisionFilterPose"])
    prim.CreateAttribute("deformablePose:%s:omniphysics:points" % name, Sdf.ValueTypeNames.Point3fArray).Set(Vt.Vec3fArray.FromNumpy(pts.astype(np.float32)))
if a.early_fpose: set_fpose(st.GetPrimAtPath(PATH), FL0)
def attrs(prim):
    return " ".join("%s=%s" % (n.split(":", 1)[-1] if n.startswith("physxDeformableBody") else n, (lambda v: ("[%d]" % len(v)) if hasattr(v, "__len__") and not isinstance(v, str) and len(v) > 4 else v)(prim.GetAttribute(n).Get()))
                    for n in prim.GetPropertyNames() if ("selfColl" in n or "deformablePose" in n or n.endswith("restOffset") or n.endswith("contactOffset")))
P("建立時屬性:", attrs(st.GetPrimAtPath(PATH)))
TIP = np.where(FL0[:, 0] > LX - 1e-5)[0]
BAR0 = np.array([LX, 0, ZB + T / 2])
VC.kin_box(st, "/World/bar", [0.004, LY + 0.01, T + 0.004], BAR0, collide=False)
VC.attach_vtx(st, "/World/att_bar", PATH, PATH, "/World/bar", TIP, FL0[TIP] - BAR0, P=P)
PX = 0.05
VC.kin_box(st, "/World/press", [0.08, 0.08, 0.01], [PX, 0, 0.5])
world.reset()
bar = SingleXFormPrim("/World/bar", name="bar"); press = SingleXFormPrim("/World/press", name="press")
ZM = ZB + T / 2; GAP = T + a.gap_mm / 1e3
ss = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.), 1.))
T0, SPAN, HOLD = 0.3, 2.0, 0.8; TREL = T0 + SPAN + HOLD; TPR = TREL + 1.0
TPL = TREL - 0.2 if a.bake_at == "pre" else TPR + 1.2
TEND = TPR + 4.0
ZABS = (ZB + 2 * T + 0.001) if a.press_abs_mm < 0 else a.press_abs_mm / 1e3
def bar_pose(t):
    ph = np.pi * ss((t - T0) / SPAN)
    return np.array([HX + LX / 2 * np.cos(ph), 0, ZM + GAP / 2 - GAP / 2 * np.cos(ph) + 0.06 * np.sin(ph)]), ph
F2 = (FL0[:NC] + FL0[NC:]) / 2
LOC = np.where((F2[:, 0] < HX - 0.02) & (np.abs(F2[:, 0] - PX) < 0.035) & (np.abs(F2[:, 1]) < 0.035))[0]   # 壓板正下方的下層 column
UPC = np.where(F2[:, 0] > HX + 0.02)[0]
from scipy.spatial import cKDTree
def mid_gap(p):
    M = (p[:NC] + p[NC:]) / 2; tr = cKDTree(M[UPC][:, :2]); _, j = tr.query(M[LOC][:, :2]); dz = M[UPC][j, 2] - M[LOC, 2]
    return float(np.median(dz) * 1e3), float(dz.min() * 1e3)
def pen(p): return VP.self_pen_count(p, TE, FL0)[0]
def bake(t):
    global mesh
    cur = mesh.pts(); prim = st.GetPrimAtPath(PATH); msg = []
    n0, g0 = pen(cur), mid_gap(cur)
    if a.bake == 1:
        if a.spread_mm > 0:
            t0 = time.time(); X, info = SR.solve(cur, FL0, TE, T, a.spread_mm / 1e3, P=P)
            msg.append("rest = spread %.0f mm(疊層對 %d,中面最小 %.2f mm,應變 max %.3f,解 %.1f s)" % (a.spread_mm, info["npair"], info["sep_min_mm"], info["strain"], time.time() - t0))
        else:
            X = cur.copy(); msg.append("rest = 當下")
        prim.GetAttribute("omniphysics:restShapePoints").Set(Vt.Vec3fArray.FromNumpy(X.astype(np.float32)))
    else:
        X = np.array(prim.GetAttribute("omniphysics:restShapePoints").Get(), float)
        msg.append("rest 不改")
    if a.fpose != "none":
        set_fpose(prim, {"flat": FL0, "rest": X, "cur": cur}[a.fpose]); msg.append("selfCollisionFilterPose = %s" % a.fpose)
    if a.filter_mm >= 0:
        prim.GetAttribute("physxDeformableBody:selfCollisionFilterDistance").Set(a.filter_mm / 1e3); msg.append("filter %g mm" % a.filter_mm)
    prim.SetActive(False); world.step(render=False)
    st.GetPrimAtPath(PATH).SetActive(True); mesh = VC.Mesh(st, PATH)
    mesh.pa.Set(Vt.Vec3fArray.FromNumpy(cur.astype(np.float32)))
    P("★ t=%.2f 烘焙:%s + SetActive 重建 | 改前 自穿 %d 中面層距 中位 %.2f 最小 %.2f mm" % (t, ", ".join(msg), n0, g0[0], g0[1]))
    P("  重建後屬性:", attrs(st.GetPrimAtPath(PATH)))
NS = int(round(TEND / dt)); released = False; zp = None; mx_after = 0; t0w = time.time(); REC = []
for s in range(1, NS + 1):
    t = s * dt
    if not released:
        p_, ph = bar_pose(t); bar.set_world_pose(position=p_, orientation=VC.quat_y(-ph))
    if abs(t - TPL) < dt / 2 and a.bake: bake(t)
    if abs(t - TREL) < dt / 2:
        st.RemovePrim(Sdf.Path("/World/att_bar")); released = True; P("★ t=%.2f 放手" % t)
    if t >= TPR:
        w = ss((t - TPR) / 0.8); w2 = ss((t - TPR - 1.5) / 0.8) if a.bake_at == "press" else 0.0
        zb = (0.3 * (1 - w) + ZABS * w) - a.press2_mm / 1e3 * w2
        press.set_world_pose(position=np.array([PX, 0, zb + 0.005]))
    world.step(render=False)
    if s % 4 == 0: REC.append(mesh.pts().astype(np.float32))
    if s % 30 == 0 or s == NS:
        p = mesh.pts(); n = pen(p); g = mid_gap(p)
        if t > TPL and a.bake: mx_after = max(mx_after, n)
        P("t=%.2f 自穿 %d | 中面層距(壓板下)中位 %.2f 最小 %.2f mm | z %.1f~%.1f | 壓板底 %.1f mm" % (t, n, g[0], g[1], p[:, 2].min() * 1e3, p[:, 2].max() * 1e3, zb * 1e3 if t >= TPR else 300))
p = mesh.pts(); n = pen(p); g = mid_gap(p)
np.savez_compressed(os.path.join(OUT, tag + ".npz"), P=np.array(REC), tets=TE, flat=FL0)
P("===== RESULT %s:bake %d spread %g fpose %s at %s filter %g:自穿 結束 %d(烘焙後最大 %d)中面層距 中位 %.2f 最小 %.2f mm(貼合 = T+2·rest = 5.0)wall %.0fs"
  % (tag, a.bake, a.spread_mm, a.fpose, a.bake_at, a.filter_mm, n, mx_after, g[0], g[1], time.time() - t0w))
LOG.close(); sim.close()
