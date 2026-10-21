#!/usr/bin/env python3
"""probe_yield.py — 探針 3:降伏規則原型(折痕塑性)在「四折一小塊」上的效果。

    /isaac-sim/python.sh crease/probe_yield.py --yield 0|1 [--bend 4] [--lam 0.5] [--ydeg 20] [--period 0.25] [--sep_mm 3]

160×160 mm 布(32×32 格,5 mm;材料 = ccommon.MAT、selfCollision on、重力)平放地上。
  A 折(0.3~2.3 s):x=+80 那排綁桿 A,繞鉸線 x=0 半圓翻到左半上面,2.8 s 放手。
  B 折(3.3~5.3 s):y=+80 那排(兩層都綁)綁桿 B,繞鉸線 y=0 翻到 y<0 上面,5.8 s 放手 → 四折(4 層 80×80)。
  觀察到 8.0 s(量「折完放手後保持形狀」:放手 → +2 s 全頂點位移 RMS、bbox 高)。
  C 掀開(8.0~9.5 s):同一排重新綁桿 C,把最上面那片繞 y=0 掀回 90°(直立),10.0 s 放手,觀察到 12.0 s
    (量「掀開放手後」那片的角度:180° = 蓋回去、90° = 還立著、0° = 攤平)。
--yield 1:每 --period 秒掃所有內部邊,|當下角 − 靜止角| > --ydeg 的邊 靜止角 += λ(當下 − 靜止);有邊降伏就
  yieldrule.solve 出一致的 rest 嵌入(邊長 = 原長、二面角 = 靜止角;--sep_mm > 0 時把疊層在 rest 裡撐開到 ≥ sep,
  避免 rest 層距 < selfCollisionFilterDistance 讓自碰撞被過濾),寫 restShapePoints + restShapeDefault,SetActive 重建。
--yield 2:同樣頻率只做 SetActive 重建、rest 不改(重建本身 = 速度歸零的影響)。
"""
import os, sys, argparse, time
import numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--yield", dest="yld", type=int, default=1)
ap.add_argument("--bend", type=float, default=4.0)
ap.add_argument("--young", type=float, default=2e4)
ap.add_argument("--lam", type=float, default=0.5)
ap.add_argument("--ydeg", type=float, default=20.0)
ap.add_argument("--period", type=float, default=0.25)
ap.add_argument("--sep_mm", type=float, default=3.0)
ap.add_argument("--sep_flat_mm", type=float, default=6.0, help="攤平時相距超過這個的頂點對才撐開")
ap.add_argument("--tag", default="")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
tag = a.tag or "yield_y%d_b%g_l%g_d%g_s%g_f%g" % (a.yld, a.bend, a.lam, a.ydeg, a.sep_mm, a.sep_flat_mm)
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
import omni.usd
sys.path.insert(0, HERE)
import ccommon as C
from yieldrule import YieldRule
C.MAT.update(bend=a.bend, young=a.young)
P("=== probe_yield %s ===" % tag); P("args:", vars(a))
DT = 1 / 120.0
world = World(physics_dt=DT, rendering_dt=DT); world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
L, N = 0.160, 32
ZB = 0.002; PATH = "/World/sheet"
P0, TRIS, IJ = C.grid(L, L, N, N, x0=-L / 2, y0=-L / 2, z0=ZB)
PAIRS = C.adj_pairs(TRIS); EDG = C.edges_of(TRIS)
YR = YieldRule(P0, TRIS, PAIRS, EDG, yield_deg=a.ydeg, lam=a.lam)
sp = C.build_cloth(st, PATH, P0, TRIS, selfcol=True, P=P)
ROW_A = np.where(IJ[:, 0] == N)[0]; ROW_B = np.where(IJ[:, 1] == N)[0]; HINGE_B = np.where(IJ[:, 1] == N // 2)[0]
PARK = np.array([0.0, 0.0, 1.0])
BA0 = np.array([L / 2, 0, ZB])
for nm in ("A", "B", "C"):
    C.kin_box(st, "/World/bar" + nm, [0.004, 0.004, 0.004], BA0 if nm == "A" else PARK + (0.1 if nm == "B" else 0.2) * np.array([1, 0, 0]), collide=False)
C.attach_vtx(st, "/World/att_A", PATH, "/World/barA", ROW_A, P0[ROW_A] - BA0, P=P)
world.reset()
bar = {nm: SingleXFormPrim("/World/bar" + nm, name="bar" + nm) for nm in ("A", "B", "C")}
bar["A"].set_world_pose(position=BA0, orientation=np.array([1., 0, 0, 0]))


def quat_x(al):
    return np.array([np.cos(al / 2), np.sin(al / 2), 0.0, 0.0])


GA, GB = 0.006, 0.010
TA0, TA1, TAR = 0.3, 2.3, 2.8
TB0, TB1, TBR = 3.35, 5.35, 5.85
TOBS = 7.8
TC0, TC1, TCR = 8.05, 9.55, 10.05
TEND = 12.0


def poseA(t):
    ph = np.pi * C.ss((t - TA0) / (TA1 - TA0))
    return np.array([L / 2 * np.cos(ph), 0, ZB + GA / 2 - GA / 2 * np.cos(ph) + 0.04 * np.sin(ph)]), C.quat_y(-ph)


B = {}


def poseB(t, ph):
    c = B["c0"]
    return np.array([c[0], L / 2 * np.cos(ph), c[2] + GB / 2 - GB / 2 * np.cos(ph) + 0.04 * np.sin(ph)])


def flap_angle(p):
    h = p[HINGE_B].mean(0); r = p[ROW_B].mean(0)
    return float(np.degrees(np.arctan2(r[2] - h[2], r[1] - h[1])))


def bbox(p):
    d = p.max(0) - p.min(0); return "%.0f×%.0f×%.1f mm" % tuple(d * 1e3)


def rebuild(cur, rest=None):
    prim = st.GetPrimAtPath(PATH)
    if rest is not None:
        C.sa(prim, "omniphysics:restShapePoints", Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in rest]))
        prim.GetAttribute("omniphysics:restBendAnglesDefault").Set("restShapeDefault")
    C.set_pts(st, PATH, cur); prim.SetActive(False); world.step(render=False)
    prim = st.GetPrimAtPath(PATH); prim.SetActive(True); C.set_pts(st, PATH, cur)


NS = int(round(TEND / DT)); PER = int(round(a.period / DT))
REC = []; RT = []; EV = []; res = {}; t0 = time.time(); nreb = 0; s1max = 0; tsolve = 0.0
attA = True; attB = False; attC = False
for s in range(1, NS + 1):
    t = s * DT
    if attA:
        p_, q_ = poseA(t); bar["A"].set_world_pose(position=p_, orientation=q_)
        if t >= TAR - 1e-9:
            st.RemovePrim(Sdf.Path("/World/att_A")); attA = False; EV.append((t, "A release")); P("★ t=%.2f A 放手 | bbox %s" % (t, bbox(C.pts(st, PATH))))
    for nm, tg in (("B", TB0), ("C", TC0)):
        if abs(t - (tg - 0.1)) < DT / 2:                       # 先把桿移到抓取點(kinematic 目標要走一步才生效),0.1 s 後才建 attachment
            cur = C.pts(st, PATH); bar[nm].set_world_pose(position=cur[ROW_B].mean(0), orientation=np.array([1., 0, 0, 0]))
    if not attB and abs(t - TB0) < DT / 2:
        cur = C.pts(st, PATH); c0 = cur[ROW_B].mean(0); B["c0"] = c0
        bar["B"].set_world_pose(position=c0, orientation=np.array([1., 0, 0, 0]))
        C.attach_vtx(st, "/World/att_B", PATH, "/World/barB", ROW_B, cur[ROW_B] - c0, P=P); attB = True; EV.append((t, "B grab"))
        B["d0"] = c0 - poseB(t, 0.0)
    if attB:
        ph = np.pi * C.ss((t - TB0) / (TB1 - TB0))
        bar["B"].set_world_pose(position=poseB(t, ph) + B["d0"], orientation=quat_x(ph))
        if t >= TBR - 1e-9:
            st.RemovePrim(Sdf.Path("/World/att_B")); attB = False; cur = C.pts(st, PATH); res["relB"] = cur.copy()
            EV.append((t, "B release")); P("★ t=%.2f B 放手(四折完成)| bbox %s | S1 %d" % (t, bbox(cur), C.self_pen(cur, TRIS, EDG)))
    if abs(t - TOBS) < DT / 2:
        cur = C.pts(st, PATH); d = np.linalg.norm(cur - res["relB"], axis=1)
        res["hold"] = (float(np.sqrt((d ** 2).mean()) * 1e3), float(d.max() * 1e3), bbox(res["relB"]), bbox(cur),
                       float((res["relB"][:, 2].max()) * 1e3), float(cur[:, 2].max() * 1e3))
        P("★ t=%.2f 四折放手後 2 s:位移 RMS %.2f mm / max %.2f mm | bbox %s → %s | 頂高 %.1f → %.1f mm" % ((t,) + res["hold"]))
    if not attC and abs(t - TC0) < DT / 2:
        cur = C.pts(st, PATH); c0 = cur[ROW_B].mean(0); B["cc"] = c0; B["fa0"] = flap_angle(cur)
        bar["C"].set_world_pose(position=c0, orientation=np.array([1., 0, 0, 0]))
        C.attach_vtx(st, "/World/att_C", PATH, "/World/barC", ROW_B, cur[ROW_B] - c0, P=P); attC = True; EV.append((t, "C grab"))
        h = cur[HINGE_B].mean(0); B["h"] = h; B["r0"] = c0 - h
        P("★ t=%.2f C 抓最上片(flap 角 %.1f°)" % (t, B["fa0"]))
    if attC:
        al = -np.pi / 2 * C.ss((t - TC0) / (TC1 - TC0))         # 繞 x 轉 -90°:從蓋著(指向 -y)掀到直立
        R = np.array([[1, 0, 0], [0, np.cos(al), -np.sin(al)], [0, np.sin(al), np.cos(al)]])
        bar["C"].set_world_pose(position=B["h"] + R @ B["r0"] + np.array([0, 0, 0.004 * np.sin(-al)]), orientation=quat_x(al))
        if t >= TCR - 1e-9:
            cur = C.pts(st, PATH); res["fa_rel"] = flap_angle(cur)
            st.RemovePrim(Sdf.Path("/World/att_C")); attC = False; EV.append((t, "C release"))
            P("★ t=%.2f C 放手:flap 角 %.1f°" % (t, res["fa_rel"]))
    near_grab = min(abs(t - TB0), abs(t - TC0)) < 3 * DT     # attachment 剛建的那幾步不要重建(會變 invalid actors)
    if a.yld and s % PER == 0 and t < TEND - 0.5 and not near_grab:
        cur = C.pts(st, PATH)
        if a.yld == 1:
            yes, ny, dmax = YR.step(cur)
            if yes:
                ts = time.time(); X, info = YR.solve(cur, sep=a.sep_mm / 1e3, sep_flat=a.sep_flat_mm / 1e3); tsolve += time.time() - ts
                rebuild(cur, X); nreb += 1
                if nreb <= 3 or nreb % 8 == 0:
                    P("  [yield] t=%.2f 降伏邊 %d(max|dev| %.0f°)| 解 rest:應變 %.1e 角誤差 max %.2f° 中位 %.3f° | 撐開對 %d(最小 %.1f mm)| 第 %d 次重建"
                      % (t, ny, dmax, info["strain"], info["ang"], info["ang_med"], info["nsep"], info["sep_min_mm"], nreb))
        else:
            rebuild(cur); nreb += 1
    world.step(render=False)
    if s % 4 == 0:
        REC.append(C.pts(st, PATH).astype(np.float32)); RT.append(t)
    if s % 30 == 0 or s == NS:
        p = C.pts(st, PATH)
        if not np.isfinite(p).all(): P("NaN t=%.2f" % t); break
        n = C.self_pen(p, TRIS, EDG); s1max = max(s1max, n)
        P("t=%.2f S1 %d | bbox %s | flap %.0f° | 重建 %d" % (t, n, bbox(p), flap_angle(p), nreb))
p = C.pts(st, PATH); res["fa_end"] = flap_angle(p)
np.savez_compressed(os.path.join(HERE, "rec", tag + ".npz"), P=np.array(REC), t=np.array(RT), tris=TRIS, ev=np.array([e[0] for e in EV]),
                    evn=np.array([e[1] for e in EV]), title=np.array("probe_yield %s" % tag))
h = res.get("hold", (np.nan,) * 6)
P("\n===== RESULT yield %d bend %g λ %g ydeg %g sep %g:四折放手→+2s 位移 RMS %.2f / max %.2f mm,頂高 %.1f → %.1f mm,bbox %s → %s | 掀開:放手時 flap %.1f° → 2 s 後 %.1f°(180 蓋回 / 90 直立 / 0 攤平)| S1 全程最大 %d 結束 %d | 重建 %d 次(解 rest 共 %.1f s)| wall %.0fs"
  % (a.yld, a.bend, a.lam, a.ydeg, a.sep_mm, h[0], h[1], h[4], h[5], h[2], h[3], res.get("fa_rel", np.nan), res["fa_end"], s1max, C.self_pen(p, TRIS, EDG), nreb, tsolve, time.time() - t0))
LOG.close(); sim.close()
