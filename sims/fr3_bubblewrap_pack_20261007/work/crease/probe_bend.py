#!/usr/bin/env python3
"""probe_bend.py — 探針 1:surface 布(零厚度)runtime 改靜止折角(restBendAngles 等)能不能做出折痕記憶。

    /isaac-sim/python.sh crease/probe_bend.py --mode N [--grav 0|1] [--sign 1] [--tag x]

200(x)×100(y) mm 布,40×20 格(5 mm),懸空 z=0.1;材料 = wrap_sim 同款(ccommon.MAT:E 2e4、bend 4、thick 4 mm、
cont/rest 5/1 mm、selfCollision on)。根部 x≤10 mm 綁固定 kinematic 塊;尖端 x=200 那排綁 kinematic 桿,桿沿 1/4 圓弧走
+ 繞 y 轉 90° → 布彎成 1/4 圓(彎折帶 = 整段自由長 190 mm,每條縱向邊 ≈ 2.4°)。hold 後「放手前 --pre 秒」做 --mode,
放手 = RemovePrim 桿的 attachment Scope,觀察 --tobs 秒。
mode(runtime,放手前 0.2 s):
  0 對照(不改)
  1 USD 寫 omniphysics:restAdjTriPairs + omniphysics:restBendAngles(全部內部邊 = 當下二面角 × --sign)
  2 1 + sim mesh SetActive(False) → step → SetActive(True)(PhysX 以 USD 重建,points = 當下)
  3 1 + physx release_physics_objects() + force_load_physics_from_usd()(整場重載)
  9 1 + RemoveAppliedSchema / AddAppliedSchema OmniPhysicsSurfaceDeformableSimAPI(中間 step)
  4 restShapePoints ← 當下 + restBendAnglesDefault = restShapeDefault + SetActive 重建(=vol PLASTIC 有效作法)
  5 restShapePoints ← 當下 + restShapeDefault,只寫 USD
  6 只 SetActive 重建,什麼都不改(重建本身的影響)
mode(建立時,不綁桿,只看平布會不會自己彎):
  7 建立時寫 restAdjTriPairs/restBendAngles = 解析 1/4 圓的二面角 × --sign
  8 建立時 restShapePoints = 解析 1/4 圓 + restShapeDefault(正對照)
量測:彎角 = 尖端段(x 180~200)切線角 − 根部段(x 10~20)切線角(中線 y=0,x-z 平面);另印中線 Σ二面角。
"""
import os, sys, argparse, time
import numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--mode", type=int, default=0)
ap.add_argument("--grav", type=int, default=0)
ap.add_argument("--sign", type=float, default=1.0)
ap.add_argument("--bend_deg", type=float, default=90.0)
ap.add_argument("--span", type=float, default=1.5)
ap.add_argument("--hold", type=float, default=0.6)
ap.add_argument("--pre", type=float, default=0.2)
ap.add_argument("--tobs", type=float, default=4.0)
ap.add_argument("--selfcol", type=int, default=1)
ap.add_argument("--bend", type=float, default=4.0, help="surfaceBendStiffness(wrap_sim 同款 4)")
ap.add_argument("--young", type=float, default=2e4)
ap.add_argument("--tag", default="")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
tag = a.tag or "bend_m%d_g%d_s%+g_b%g" % (a.mode, a.grav, a.sign, a.bend)
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
sys.path.insert(0, HERE)
import ccommon as C
C.MAT.update(bend=a.bend, young=a.young)
P("=== probe_bend %s ===" % tag); P("args:", vars(a)); P("MAT:", C.MAT)
DT = 1 / 120.0
world = World(physics_dt=DT, rendering_dt=DT)
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
if not a.grav:
    UsdPhysics.Scene(st.GetPrimAtPath("/physicsScene")).CreateGravityMagnitudeAttr().Set(0.0)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
LX, LY, NX, NY, Z0 = 0.200, 0.100, 40, 20, 0.100
PATH = "/World/sheet"
P0, TRIS, IJ = C.grid(LX, LY, NX, NY, x0=0.0, z0=Z0)
PAIRS = C.adj_pairs(TRIS)
ROOT_X = 0.010
ROOT = np.where(P0[:, 0] < ROOT_X + 1e-6)[0]; TIP = np.where(P0[:, 0] > LX - 1e-6)[0]
Lf = LX - ROOT_X; PHI = np.radians(a.bend_deg)
MID = np.where(IJ[:, 1] == NY // 2)[0]; MID = MID[np.argsort(P0[MID, 0])]
MIDPAIRS = np.array([n for n, (ta, tb, p, q) in enumerate(PAIRS) if IJ[p, 0] == IJ[q, 0] and {IJ[p, 1], IJ[q, 1]} == {NY // 2, NY // 2 + 1}])


def arc_points(phi):
    """解析:x≤ROOT_X 平,之後彎成半徑 Lf/phi 的圓弧(往 +z 彎)。"""
    Q = P0.copy()
    if phi < 1e-9:
        return Q
    R = Lf / phi; s = np.clip(P0[:, 0] - ROOT_X, 0, None); th = s / R
    Q[:, 0] = np.where(P0[:, 0] > ROOT_X, ROOT_X + R * np.sin(th), P0[:, 0])
    Q[:, 2] = np.where(P0[:, 0] > ROOT_X, Z0 + R * (1 - np.cos(th)), Z0)
    return Q


def bend_deg(p):
    m = p[MID]; xs = P0[MID, 0]
    def ang(sel):
        q = m[sel]; d = q[-1] - q[0]; return np.degrees(np.arctan2(d[2], d[0]))
    r = (xs >= ROOT_X - 1e-6) & (xs <= 0.020 + 1e-6); t = xs >= LX - 0.020 - 1e-6
    return ang(t) - ang(r)


def mid_dsum(p):
    return float(C.dihedrals(p, TRIS, PAIRS)[MIDPAIRS].sum())


kw = {}
if a.mode == 7:
    ang = C.dihedrals(arc_points(PHI), TRIS, PAIRS) * a.sign
    kw = dict(rb_pairs=PAIRS[:, :2], rb_angles=ang)
    P("mode 7:建立時寫 %d 對 restBendAngles(中線 Σ %.1f°,|角| max %.2f°)" % (len(PAIRS), ang[MIDPAIRS].sum(), np.abs(ang).max()))
if a.mode == 8:
    kw = dict(rest_pts=arc_points(PHI), rest_default="restShapeDefault")
    P("mode 8:建立時 restShapePoints = 解析 1/4 圓 + restShapeDefault")
sp = C.build_cloth(st, PATH, P0, TRIS, selfcol=bool(a.selfcol), P=P, **kw)
P("內部相鄰三角形對 %d;中線縱向邊 %d 條" % (len(PAIRS), len(MIDPAIRS)))
CL0 = np.array([ROOT_X / 2, 0, Z0])
C.kin_box(st, "/World/clamp", [ROOT_X + 0.004, LY + 0.01, 0.006], CL0, collide=False)
C.attach_vtx(st, "/World/att_clamp", PATH, "/World/clamp", ROOT, P0[ROOT] - CL0, P=P)
BAR0 = np.array([LX, 0, Z0])
NOBAR = a.mode in (7, 8)
if not NOBAR:
    C.kin_box(st, "/World/bar", [0.004, LY + 0.01, 0.006], BAR0, collide=False)
    C.attach_vtx(st, "/World/att_bar", PATH, "/World/bar", TIP, P0[TIP] - BAR0, P=P)
world.reset()
bar = SingleXFormPrim("/World/bar", name="bar") if not NOBAR else None
T_SET = 0.3; T_REL = T_SET + a.span + a.hold; T_PL = T_REL - a.pre; T_END = T_REL + a.tobs
if NOBAR:
    T_REL = T_PL = 0.0; T_END = a.tobs


def bar_pose(t):
    ph = PHI * C.ss((t - T_SET) / a.span)
    if ph < 1e-9:
        return BAR0.copy(), 0.0
    r_ = Lf / ph
    return np.array([ROOT_X + r_ * np.sin(ph), 0, Z0 + r_ * (1 - np.cos(ph))]), ph


def do_mode(cur):
    m = a.mode; prim = st.GetPrimAtPath(PATH); msg = []
    if m in (1, 2, 3, 9):
        ang = C.dihedrals(cur, TRIS, PAIRS) * a.sign
        C.write_rb(prim, PAIRS[:, :2], ang)
        msg.append("USD restAdjTriPairs/restBendAngles ← 當下(%d 對,中線 Σ %.1f°,max |%.2f|°)" % (len(PAIRS), ang[MIDPAIRS].sum(), np.abs(ang).max()))
    if m in (4, 5):
        C.sa(prim, "omniphysics:restShapePoints", Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in cur]))
        prim.GetAttribute("omniphysics:restBendAnglesDefault").Set("restShapeDefault")
        msg.append("USD restShapePoints ← 當下 + restBendAnglesDefault = restShapeDefault")
    if m in (2, 4, 6):
        C.set_pts(st, PATH, cur)
        prim.SetActive(False); world.step(render=False)
        prim = st.GetPrimAtPath(PATH); prim.SetActive(True); C.set_pts(st, PATH, cur)
        msg.append("SetActive(False) → step → SetActive(True)")
    if m == 3:
        C.set_pts(st, PATH, cur)
        px = omni.physx.get_physx_interface(); px.release_physics_objects(); px.force_load_physics_from_usd()
        msg.append("release_physics_objects + force_load_physics_from_usd")
    if m == 9:
        api = [x for x in prim.GetAppliedSchemas() if x.startswith("OmniPhysicsSurfaceDeformableSimAPI")]
        for n in api: prim.RemoveAppliedSchema(n)
        world.step(render=False)
        for n in api: prim.AddAppliedSchema(n)
        C.set_pts(st, PATH, cur)
        msg.append("Remove/AddAppliedSchema %s(中間 step)" % api)
    return " + ".join(msg) or "不改(對照)"


NS = int(round(T_END / DT)); S_PL = int(round(T_PL / DT)); S_REL = int(round(T_REL / DT)); PE = int(round(0.25 / DT))
released = NOBAR; res = {}; t0 = time.time(); REC = []; RT = []; EV = []
for s in range(1, NS + 1):
    t = s * DT
    if not released:
        p_, ph = bar_pose(t); bar.set_world_pose(position=p_, orientation=C.quat_y(-ph))
    if s == S_PL and not NOBAR:
        cur = C.pts(st, PATH); res["bend_pl"] = bend_deg(cur)
        msg = do_mode(cur)
        world.step(render=False); c2 = C.pts(st, PATH)
        EV.append((t, "mode %d" % a.mode))
        P("★ t=%.2f mode %d:%s | 改前彎角 %.1f° 中線Σ %.1f° | 1 步後點數 %d 位移 max %.2f mm 彎角 %.1f°"
          % (t, a.mode, msg, res["bend_pl"], mid_dsum(cur), len(c2), np.abs(c2 - cur).max() * 1e3 if len(c2) == len(cur) else -1, bend_deg(c2)))
        continue
    if s == S_REL and not NOBAR:
        cur = C.pts(st, PATH); res["bend_rel"] = bend_deg(cur)
        st.RemovePrim(Sdf.Path("/World/att_bar")); released = True; EV.append((t, "release"))
        P("★ t=%.2f 放手(RemovePrim att_bar):彎角 %.1f° 中線Σ %.1f°,尖端 (%.1f,%.1f) mm" % (t, res["bend_rel"], mid_dsum(cur), cur[TIP, 0].mean() * 1e3, cur[TIP, 2].mean() * 1e3))
    world.step(render=False)
    cur = C.pts(st, PATH)
    if s % 4 == 0:
        REC.append(cur.astype(np.float32)); RT.append(t)
    if released and not NOBAR:
        for k in (0.5, 1.0, 2.0):
            if s == S_REL + int(round(k / DT)): res["b%.1f" % k] = bend_deg(cur)
    if s % PE == 0 or s == NS:
        if not np.isfinite(cur).all(): P("★ NaN t=%.2f" % t); break
        b = bend_deg(cur); tr = t - T_REL
        P("t=%.2f%s 彎角 %.1f° 中線Σ %.1f° 尖端 (%.1f,%.1f) mm" % (t, " (放手後 %.2fs)" % tr if released else "", b, mid_dsum(cur), cur[TIP, 0].mean() * 1e3, cur[TIP, 2].mean() * 1e3))
cur = C.pts(st, PATH); res["bend_end"] = bend_deg(cur)
S1 = C.self_pen(cur, TRIS)
np.savez_compressed(os.path.join(HERE, "rec", tag + ".npz"), P=np.array(REC), t=np.array(RT), tris=TRIS, ev=np.array([e[0] for e in EV]),
                    evn=np.array([e[1] for e in EV]), title=np.array("probe_bend %s" % tag))
if NOBAR:
    P("\n===== RESULT mode %d grav %d sign %+g(建立時):%.1fs 後彎角 %.1f°(目標 %.0f°,平 = 0)| S1 %d | wall %.1fs"
      % (a.mode, a.grav, a.sign, a.tobs, res["bend_end"], a.bend_deg, S1, time.time() - t0))
else:
    P("\n===== RESULT mode %d grav %d sign %+g:改前 %.1f° / 放手前 %.1f° → 0.5s %.1f° / 1s %.1f° / 2s %.1f° / %.0fs %.1f°;回彈(放手前 − 結束)= %.1f° | S1 %d | wall %.1fs"
      % (a.mode, a.grav, a.sign, res.get("bend_pl", np.nan), res.get("bend_rel", np.nan), res.get("b0.5", np.nan), res.get("b1.0", np.nan), res.get("b2.0", np.nan),
         a.tobs, res["bend_end"], res.get("bend_rel", np.nan) - res["bend_end"], S1, time.time() - t0))
LOG.close(); sim.close()
