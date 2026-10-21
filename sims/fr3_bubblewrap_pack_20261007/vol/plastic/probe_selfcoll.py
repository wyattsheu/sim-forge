#!/usr/bin/env python3
"""probe_selfcoll.py — 烘焙 rest 之後自碰撞還在不在。
板 200x100x4(manual 50x25x1)平放地上,self collision on(filter 2*rest = 1mm,同 wrap_vol)。尖端 x=200 綁 kinematic 桿,
沿半圓(鉸線 x=100)對折到上層蓋在下層上方(中面高 = 下層 + T + 3mm),hold,--bake 1 時放手前 0.2s rest ← 當下 + SetActive 重建,
放手,1s 後 kinematic 壓板(80x80)從上方壓到 上層頂 − --press_mm,停 2s。量 vol_pen 自穿、上下層中面距離(配對頂點)。
    /isaac-sim/python.sh plastic/probe_selfcoll.py --bake 0|1 [--filter_mm -1] [--press_mm 3]
"""
import os, sys, argparse, time
import numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--bake", type=int, default=0)
ap.add_argument("--filter_mm", type=float, default=-1)
ap.add_argument("--press_mm", type=float, default=3.0)
ap.add_argument("--young", type=float, default=2e3)
ap.add_argument("--gap_mm", type=float, default=3.0, help="對折後上下層表面間距(= rest 裡的間距)")
ap.add_argument("--rebuild", type=int, default=0, help="1 = 烘焙改用 刪掉重建(build_plate, points = rest = 當下)")
ap.add_argument("--sc_toggle", type=int, default=0, help="重建後第 2 步把 selfCollision 設 False、第 4 步設 True(runtime 重新開自碰撞);2 = 只在第 2 步重寫 True + filter 1mm")
ap.add_argument("--prefold", type=int, default=0, help="1 = 一開始就建成對折形狀(points = rest = U 形),不走桿,0.3s 後直接壓")
ap.add_argument("--tag", default="")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
tag = a.tag or "sc_b%d_f%g_p%g_g%g_r%d_t%d_pf%d" % (a.bake, a.filter_mm, a.press_mm, a.gap_mm, a.rebuild, a.sc_toggle, a.prefold)
LOG = open(os.path.join(HERE, "logs", "probe_" + tag + ".log"), "w")
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
sys.path.insert(0, VOL)
import volcommon as VC, vol_pen as VP
dt = 1 / 120.0
world = World(physics_dt=dt, rendering_dt=dt); world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene")); pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
LX, LY, T = 0.2, 0.1, 0.004; ZB = 0.001; PATH = "/World/plate"; REST_OFF = 0.0005; HX = 0.100
def build(pmap=None):
    return VC.build_plate(st, PATH, LX, T, ZB, "manual", nxy=25, nz=1, nx=50, youngs=a.young, cx=LX / 2, cy=0, size_y=LY, solver=64,
               self_coll=True, self_filter=2 * REST_OFF, cont=0.002, rest=REST_OFF, P=P, pmap=pmap)
def ufold(p):                                                                  # 中面沿 x:x<HX 平;HX 處半圓(半徑 Rm)折回;上層 x' = 2HX - x
    q = p.copy(); Rm = (T + a.gap_mm / 1e3) / 2; zc = ZB + T / 2 + Rm; s_ = p[:, 0] - HX; h = p[:, 2] - (ZB + T / 2)   # h = 離中面(±T/2)
    arc = np.pi * Rm
    m1 = (s_ > 0) & (s_ <= arc); m2 = s_ > arc
    th = s_[m1] / Rm; r_ = Rm - h[m1]
    q[m1, 0] = HX + r_ * np.sin(th); q[m1, 2] = zc - r_ * np.cos(th)
    q[m2, 0] = HX - (s_[m2] - arc); q[m2, 2] = zc + Rm + (-h[m2])
    return q
PF0 = None
if a.prefold:
    import vol_pen as _VP
    _p, _t = _VP.grid_tets(50, 25, 1, LX / 50, LY / 25, T, np.array([0, -LY / 2, ZB])); PF0 = ufold(_p)
build(pmap=(lambda _q: ufold(_q)) if a.prefold else None)
mesh = VC.Mesh(st, PATH); P0 = mesh.pts(); TE = mesh.tets()
FL0 = _p if a.prefold else P0
TIP = np.where(FL0[:, 0] > LX - 1e-5)[0]
BAR0 = np.array([LX, 0, ZB + T / 2])
VC.kin_box(st, "/World/bar", [0.004, LY + 0.01, T + 0.004], BAR0, collide=False)
if not a.prefold: VC.attach_vtx(st, "/World/att_bar", PATH, PATH, "/World/bar", TIP, P0[TIP] - BAR0, P=P)
VC.kin_box(st, "/World/press", [0.08, 0.08, 0.01], [0.05, 0, 0.5])
world.reset()
bar = SingleXFormPrim("/World/bar", name="bar"); press = SingleXFormPrim("/World/press", name="press")
HX = 0.100; ZM = ZB + T / 2; GAP = T + a.gap_mm / 1e3; R = HX - 0.0  # 上層中面高 = ZM + GAP
ss = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.), 1.))
T0, SPAN, HOLD = (0.3, 2.0, 0.8) if not a.prefold else (0.0, 0.05, 0.25); TREL = T0 + SPAN + HOLD; TPL = TREL - 0.2; TEND = TREL + 4.0
def bar_pose(t):
    ph = np.pi * ss((t - T0) / SPAN)
    # 鉸線半徑 GAP/2 的小圓 + 直段:尖端 = 鉸點 + 旋轉後的 (L/2) 向量,鉸點中心 (HX, ZM + GAP/2)
    c = np.array([HX, 0, ZM + GAP / 2]); v = np.array([np.cos(ph), 0, np.sin(ph)])
    # 半圓底 (HX, ZM) 起;尖端 = c + R*(cos(-90+ph)...) 簡化:沿圓心 c 半徑 L/2 旋轉,起點 (HX+L/2, ZM)
    r = np.array([LX / 2 * np.cos(ph), 0, -GAP / 2 * np.cos(ph) + (LX / 2) * np.sin(ph) * 0.0])
    p = np.array([HX + LX / 2 * np.cos(ph), 0, ZM + GAP / 2 - GAP / 2 * np.cos(ph) + 0.06 * np.sin(ph)])
    return p, ph
# 上下層配對:x<HX-10mm 的下層頂點 ↔ 對折後對面的頂點(flat x' = 2*HX - x)
mid = lambda p: p  # 用全部頂點
lo = np.where(FL0[:, 0] < HX - 0.02)[0]
def layer_gap(p):
    up = np.where(FL0[:, 0] > HX + 0.02)[0]
    if len(up) == 0: return np.nan
    from scipy.spatial import cKDTree
    tr = cKDTree(p[up][:, :2]); d, j = tr.query(p[lo][:, :2])
    dz = p[up][j, 2] - p[lo, 2]
    return float(np.median(dz) * 1e3), float(dz.min() * 1e3)
NS = int(round(TEND / dt)); released = bool(a.prefold)
for s in range(1, NS + 1):
    t = s * dt
    if not released and not a.prefold:
        p_, ph = bar_pose(t); bar.set_world_pose(position=p_, orientation=VC.quat_y(-ph))
    if abs(t - TPL) < dt / 2 and a.bake:
        cur = mesh.pts(); prim = st.GetPrimAtPath(PATH)
        if a.bake == 1: prim.GetAttribute("omniphysics:restShapePoints").Set(Vt.Vec3fArray.FromNumpy(cur.astype(np.float32)))   # bake 2 = 只 SetActive 重建、rest 不改
        if a.filter_mm >= 0: prim.GetAttribute("physxDeformableBody:selfCollisionFilterDistance").Set(a.filter_mm / 1e3)
        if a.rebuild == 2:                                                    # 整個 stage 重新載入 PhysX
            from omni.physx import get_physx_interface
            px = get_physx_interface(); px.release_physics_objects(); px.force_load_physics_from_usd(); mesh = VC.Mesh(st, PATH)
            P("  release_physics_objects + force_load_physics_from_usd")
        elif a.rebuild:
            st.RemovePrim(Sdf.Path("/World/att_bar")); st.RemovePrim(Sdf.Path(PATH)); build(pmap=lambda _p: cur.copy()); mesh = VC.Mesh(st, PATH)
            bp, _ = bar.get_world_pose(); VC.attach_vtx(st, "/World/att_bar", PATH, PATH, "/World/bar", TIP, (cur[TIP] - np.array(bp)) @ VC.rot_y(-np.pi), P=P)
        else:
            prim.SetActive(False); st.GetPrimAtPath(PATH).SetActive(True); mesh = VC.Mesh(st, PATH)
        mesh.pa.Set(Vt.Vec3fArray.FromNumpy(cur.astype(np.float32)))
        P("★ t=%.2f bake:rest ← 當下(filter %s)" % (t, a.filter_mm))
    if a.bake and a.sc_toggle:
        k = int(round((t - TPL) / dt))
        pr = st.GetPrimAtPath(PATH)
        if a.sc_toggle == 1 and k == 2: pr.GetAttribute("physxDeformableBody:selfCollision").Set(False); P("  sc False")
        if a.sc_toggle == 1 and k == 4: pr.GetAttribute("physxDeformableBody:selfCollision").Set(True); P("  sc True")
        if a.sc_toggle == 2 and k == 2: pr.GetAttribute("physxDeformableBody:selfCollision").Set(True); pr.GetAttribute("physxDeformableBody:selfCollisionFilterDistance").Set(0.001); P("  sc rewrite")
    if abs(t - TREL) < dt / 2 and not a.prefold:
        st.RemovePrim(Sdf.Path("/World/att_bar")); released = True; P("★ t=%.2f 放手" % t)
    if released:
        tr = t - TREL; top = mesh.pts()[:, 2].max()
        if tr >= 1.0:
            if "zp" not in globals():
                zp = top - a.press_mm / 1e3; P("★ 壓板下到 %.1f mm(上層頂 %.1f)" % (zp * 1e3, top * 1e3))
            w = ss((tr - 1.0) / 0.8); press.set_world_pose(position=np.array([0.05, 0, (0.3 * (1 - w) + zp * w) + 0.005]))
    world.step(render=False)
    if s % 30 == 0 or s == NS:
        p = mesh.pts(); n, _ = VP.self_pen_count(p, TE, FL0); g = layer_gap(p)
        P("t=%.2f 自穿 %d | 上下層 z 差 中位 %.2f 最小 %.2f mm | bbox z %.1f~%.1f" % (t, n, g[0], g[1], p[:, 2].min() * 1e3, p[:, 2].max() * 1e3))
p = mesh.pts(); n, _ = VP.self_pen_count(p, TE, FL0); g = layer_gap(p)
P("===== RESULT bake %d filter %g press %g gap %g rebuild %d toggle %d:自穿 %d 層距 中位 %.2f 最小 %.2f mm(T=4)" % (a.bake, a.filter_mm, a.press_mm, a.gap_mm, a.rebuild, a.sc_toggle, n, g[0], g[1]))
LOG.close(); sim.close()
