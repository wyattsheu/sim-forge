#!/usr/bin/env python3
"""probe_sc.py — 探針 2:改靜止折角之後自碰撞還在不在(surface 布)。

    /isaac-sim/python.sh crease/probe_sc.py --mode N [--press_mm 3] [--gap_mm 8] [--tag x]

200×100 mm 布(40×20 格,材料 = ccommon.MAT,selfCollision on)平放地上(有重力)。尖端 x=200 那排綁 kinematic 桿,
沿半圓繞鉸線 x=100 對折,上層中面停在下層上方 --gap_mm;hold;放手前 0.2 s 做 --mode;放手;1 s 後 kinematic 壓板
(80×80 mm,中心 x=50)從上方壓到「上層頂 − --press_mm」,停 2 s。
mode 同 probe_bend:0 對照 / 1 USD restAdjTriPairs+restBendAngles ← 當下 / 2 1+SetActive 重建 / 3 1+整場重載 /
     4 restShapePoints ← 當下 + restShapeDefault + SetActive 重建 / 6 只 SetActive 重建 /
     11 炸開 disjoint rest(ccommon.explode_rest)+ SetActive 重建(★ PhysX 建不起來 body,無效)
     12 rest = yieldrule.solve(角 = 當下、邊長 = 原長、疊層在 rest 裡撐開 ≥ --sep_mm)+ SetActive 重建
量:S1(wrap_sim 定義:邊穿面次數)、上下層 z 差(下層 x<80 mm 的頂點 ↔ xy 最近的上層頂點,上層 = 攤平 x>120 mm),<0 的頂點數 = 穿過。
"""
import os, sys, argparse, time
import numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--mode", type=int, default=0)
ap.add_argument("--press_mm", type=float, default=3.0)
ap.add_argument("--gap_mm", type=float, default=8.0)
ap.add_argument("--sign", type=float, default=1.0)
ap.add_argument("--bend", type=float, default=4.0, help="surfaceBendStiffness(wrap_sim 同款 4)")
ap.add_argument("--young", type=float, default=2e4)
ap.add_argument("--bake_at", default="pre", help="pre = 放手前 0.2 s(上層剛疊上、層距 ~2.1 mm);press = 壓住時(t_press+1.2 s,層距 ~1.6 mm,< 2*restOffset)")
ap.add_argument("--press2_mm", type=float, default=0.0, help="bake_at press 時:改完後壓板再往下多壓幾 mm(t_press+1.5~2.3 s)")
ap.add_argument("--sep_mm", type=float, default=3.0, help="mode 12:rest 裡疊層撐開的最小距離")
ap.add_argument("--tag", default="")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
tag = a.tag or ("sc_m%d_p%g_b%g" % (a.mode, a.press_mm, a.bend) + ("" if a.bake_at == "pre" else "_at%s_q%g" % (a.bake_at, a.press2_mm)))
os.makedirs(os.path.join(HERE, "logs"), exist_ok=True); os.makedirs(os.path.join(HERE, "rec"), exist_ok=True)
LOG = open(os.path.join(HERE, "logs", tag + ".log"), "w")
def P(*s):
    m = " ".join(str(x) for x in s); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from isaacsim.core.prims import SingleXFormPrim
from pxr import UsdGeom, PhysxSchema, Sdf, Vt, Gf, UsdPhysics
import omni.usd, omni.physx
from scipy.spatial import cKDTree
sys.path.insert(0, HERE)
import ccommon as C
C.MAT.update(bend=a.bend, young=a.young)
P("=== probe_sc %s ===" % tag); P("args:", vars(a))
DT = 1 / 120.0
world = World(physics_dt=DT, rendering_dt=DT); world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
LX, LY, NX, NY = 0.200, 0.100, 40, 20
ZB = 0.002; HX = 0.100; PATH = "/World/sheet"
P0, TRIS, IJ = C.grid(LX, LY, NX, NY, x0=0.0, z0=ZB)
PAIRS = C.adj_pairs(TRIS); EDG = C.edges_of(TRIS)
sp = C.build_cloth(st, PATH, P0, TRIS, selfcol=True, P=P)
TIP = np.where(P0[:, 0] > LX - 1e-6)[0]
BAR0 = np.array([LX, 0, ZB])
C.kin_box(st, "/World/bar", [0.004, LY + 0.01, 0.006], BAR0, collide=False)
C.attach_vtx(st, "/World/att_bar", PATH, "/World/bar", TIP, P0[TIP] - BAR0, P=P)
PX = 0.05
C.kin_box(st, "/World/press", [0.08, 0.08, 0.01], [PX, 0, 0.3])
world.reset()
bar = SingleXFormPrim("/World/bar", name="bar"); press = SingleXFormPrim("/World/press", name="press")
GAP = a.gap_mm / 1e3
T0, SPAN, HOLD = 0.3, 2.0, 0.8; T_REL = T0 + SPAN + HOLD; T_PL = T_REL - 0.2; T_PR = T_REL + 1.0; T_END = T_REL + 4.0
if a.bake_at == "press":
    T_PL = T_PR + 1.2; T_END = T_PR + 4.0


def bar_pose(t):
    ph = np.pi * C.ss((t - T0) / SPAN)
    return np.array([HX + LX / 2 * np.cos(ph), 0, ZB + GAP / 2 - GAP / 2 * np.cos(ph) + 0.06 * np.sin(ph)]), ph


LO = np.where(P0[:, 0] < HX - 0.02)[0]; UP = np.where(P0[:, 0] > HX + 0.02)[0]
LOP = LO[np.abs(P0[LO, 0] - PX) < 0.035]          # 壓板正下方的下層頂點


def gap(p):
    tr = cKDTree(p[UP][:, :2]); d, j = tr.query(p[LOP][:, :2])
    dz = p[UP][j, 2] - p[LOP, 2]
    return float(np.median(dz) * 1e3), float(dz.min() * 1e3), int((dz < 0).sum())


def do_mode(cur):
    m = a.mode; prim = st.GetPrimAtPath(PATH); msg = []
    if m in (1, 2, 3):
        ang = C.dihedrals(cur, TRIS, PAIRS) * a.sign; C.write_rb(prim, PAIRS[:, :2], ang)
        msg.append("restAdjTriPairs/restBendAngles ← 當下(%d 對,|角| max %.1f°)" % (len(PAIRS), np.abs(ang).max()))
    if m == 4:
        C.sa(prim, "omniphysics:restShapePoints", Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in cur]))
        prim.GetAttribute("omniphysics:restBendAnglesDefault").Set("restShapeDefault")
        msg.append("restShapePoints ← 當下 + restShapeDefault")
    if m == 12:
        from yieldrule import YieldRule
        yr = YieldRule(P0, TRIS, PAIRS, EDG, yield_deg=0.0, lam=1.0); yr.step(cur)
        X, info = yr.solve(cur, sep=a.sep_mm / 1e3, sep_flat=0.006)
        C.sa(prim, "omniphysics:restShapePoints", Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in X]))
        prim.GetAttribute("omniphysics:restBendAnglesDefault").Set("restShapeDefault")
        msg.append("rest = yieldrule 解(角 = 當下、邊長 = 原長、疊層撐開 ≥ %.0f mm:撐開對 %d 最小 %.1f mm、應變 %.1e、角誤差 max %.1f°)"
                   % (a.sep_mm, info["nsep"], info["sep_min_mm"], info["strain"], info["ang"]))
    if m == 11:
        C.write_disjoint_rest(st, PATH, C.explode_rest(P0, TRIS, cur), len(TRIS)); prim = st.GetPrimAtPath(PATH)
        msg.append("炸開 disjoint rest(攤平原位 + 轉到當下法線)")
    if m in (2, 4, 6, 11, 12):
        C.set_pts(st, PATH, cur); prim.SetActive(False); world.step(render=False)
        prim = st.GetPrimAtPath(PATH); prim.SetActive(True); C.set_pts(st, PATH, cur)
        msg.append("SetActive 重建")
    if m == 3:
        C.set_pts(st, PATH, cur); px = omni.physx.get_physx_interface(); px.release_physics_objects(); px.force_load_physics_from_usd()
        msg.append("整場重載")
    return " + ".join(msg) or "不改(對照)"


NS = int(round(T_END / DT)); released = False; zp = None; REC = []; RT = []; EV = []; s1max = 0; t0 = time.time(); res = {}
for s in range(1, NS + 1):
    t = s * DT
    if not released:
        p_, ph = bar_pose(t); bar.set_world_pose(position=p_, orientation=C.quat_y(-ph))
    if abs(t - T_PL) < DT / 2:
        cur = C.pts(st, PATH); res["pl"] = (C.self_pen(cur, TRIS, EDG), gap(cur))
        msg = do_mode(cur); EV.append((t, "mode %d" % a.mode))
        P("★ t=%.2f mode %d:%s | 改前 S1 %d 層距 中位 %.2f 最小 %.2f mm" % (t, a.mode, msg, res["pl"][0], res["pl"][1][0], res["pl"][1][1]))
    if abs(t - T_REL) < DT / 2:
        st.RemovePrim(Sdf.Path("/World/att_bar")); released = True; EV.append((t, "release")); P("★ t=%.2f 放手" % t)
    if t >= T_PR:
        if zp is None:
            cur = C.pts(st, PATH); top = cur[UP][np.abs(cur[UP, 0] - PX) < 0.035, 2].max(); zp = top - a.press_mm / 1e3
            res["pre"] = (C.self_pen(cur, TRIS, EDG), gap(cur))
            EV.append((t, "press"))
            P("★ t=%.2f 壓前 S1 %d 層距 中位 %.2f 最小 %.2f mm;壓板底下到 %.1f mm(上層頂 %.1f)" % (t, res["pre"][0], res["pre"][1][0], res["pre"][1][1], zp * 1e3, top * 1e3))
        w = C.ss((t - T_PR) / 0.8); w2 = C.ss((t - T_PR - 1.5) / 0.8) if a.bake_at == "press" else 0.0
        press.set_world_pose(position=np.array([PX, 0, (0.3 * (1 - w) + zp * w) - a.press2_mm / 1e3 * w2 + 0.005]))
    world.step(render=False)
    if s % 4 == 0:
        REC.append(C.pts(st, PATH).astype(np.float32)); RT.append(t)
    if s % 30 == 0 or s == NS:
        p = C.pts(st, PATH)
        if not np.isfinite(p).all(): P("NaN"); break
        n = C.self_pen(p, TRIS, EDG); g = gap(p)
        if t > T_PL: s1max = max(s1max, n)
        P("t=%.2f S1 %d | 層距 中位 %.2f 最小 %.2f mm(<0 頂點 %d)| z %.1f~%.1f mm" % (t, n, g[0], g[1], g[2], p[:, 2].min() * 1e3, p[:, 2].max() * 1e3))
p = C.pts(st, PATH); n = C.self_pen(p, TRIS, EDG); g = gap(p)
np.savez_compressed(os.path.join(HERE, "rec", tag + ".npz"), P=np.array(REC), t=np.array(RT), tris=TRIS, ev=np.array([e[0] for e in EV]),
                    evn=np.array([e[1] for e in EV]), title=np.array("probe_sc %s" % tag))
P("\n===== RESULT mode %d press %g gap %g:改前 S1 %d | 壓前 S1 %d 層距 %.2f mm | 結束 S1 %d(改後最大 %d)層距 中位 %.2f 最小 %.2f mm 穿過頂點 %d | wall %.1fs"
  % (a.mode, a.press_mm, a.gap_mm, res["pl"][0], res["pre"][0], res["pre"][1][0], n, s1max, g[0], g[1], g[2], time.time() - t0))
LOG.close(); sim.close()
