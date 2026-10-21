#!/usr/bin/env python3
"""probe_rest_runtime.py — runtime 改 volume deformable rest shape(模擬塑性)能不能讓板放手後不回彈。

    /isaac-sim/python.sh plastic/probe_rest_runtime.py --mode 0..5 [--grav 0|1] [--young 2e3] [--tag x]

板 200(x) x 100(y) x 4 mm,manual 50x25x1(4 mm 格),懸空 z=0.1 m。根部 x<=8mm 綁到固定 kinematic 塊;
尖端 x=200 那排綁到 kinematic 桿,桿沿 1/4 圓弧(R = 192/(π/2))走 + 繞 y 轉 90° → 板彎成 1/4 圓(尖端朝 +z)。
hold 後在「放手前 --pre 秒」做 --mode 的動作,放手 = RemovePrim 桿的 attachment;觀察 --tobs 秒。
mode 0 對照(不改)
     1 USD omniphysics:restShapePoints ← 當下(runtime 寫)
     2 1 + USD points ← 當下
     3 1 + prim SetActive(False) → step → SetActive(True)(強迫 PhysX 重新解析)
     4 刪掉整塊板 + 同路徑重建(points = rest = 當下),根部 attachment 也重建
     5 1 + RemoveAPI/ApplyAPI OmniPhysicsDeformableBodyAPI(schema resync)
量測:彎角 = 尖端段(最後 20mm)切線角 − 根部段(8~20mm)切線角(x-z 平面,deg);StVK 彈性能(相對當前生效的 rest)。
"""
import os, sys, argparse, time
import numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--mode", type=int, default=0)
ap.add_argument("--grav", type=int, default=0)
ap.add_argument("--young", type=float, default=2e3)
ap.add_argument("--poisson", type=float, default=0.45)
ap.add_argument("--solver", type=int, default=64)
ap.add_argument("--dt", type=float, default=1/120.0)
ap.add_argument("--bend_deg", type=float, default=90.0)
ap.add_argument("--span", type=float, default=1.5)
ap.add_argument("--hold", type=float, default=0.6)
ap.add_argument("--pre", type=float, default=0.2)
ap.add_argument("--tobs", type=float, default=5.0)
ap.add_argument("--ldamp", type=float, default=0.0)
ap.add_argument("--tag", default="")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
tag = a.tag or "m%d_g%d_E%.0e_b%.0f" % (a.mode, a.grav, a.young, a.bend_deg)
os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
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
from pxr import UsdGeom, PhysxSchema, Sdf, Vt, Gf, UsdPhysics
import omni.usd
sys.path.insert(0, VOL)
import volcommon as VC
P("=== probe_rest_runtime %s ===" % tag); P("args:", vars(a))
world = World(physics_dt=a.dt, rendering_dt=a.dt)
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
scn = UsdPhysics.Scene(st.GetPrimAtPath("/physicsScene"))
if not a.grav:
    scn.CreateGravityMagnitudeAttr().Set(0.0)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
LX, LY, T, NX, NY = 0.200, 0.100, 0.004, 50, 25
Z0 = 0.100; PATH = "/World/plate"
def build(pmap=None):
    return VC.build_plate(st, PATH, LX, T, Z0, "manual", nxy=NY, nz=1, nx=NX, youngs=a.young, poisson=a.poisson,
                          cx=LX / 2, cy=0.0, size_y=LY, solver=a.solver, ldamp=a.ldamp, pmap=pmap, P=P)
info = build()
mesh = VC.Mesh(st, PATH)
P0 = mesh.pts(); TETS = mesh.tets()
P("板 %d 點 %d tets" % (len(P0), len(TETS)))
P("--- body schemas ---"); P("  apis=%s" % list(st.GetPrimAtPath(PATH).GetAppliedSchemas()))
P("  attrs=%s" % [x.GetName() for x in st.GetPrimAtPath(PATH).GetAttributes() if "omniphysics" in x.GetName() or "physx" in x.GetName()])
ROOT_X = 0.008 + 1e-5
ROOT = np.where(P0[:, 0] < ROOT_X)[0]; TIP = np.where(P0[:, 0] > LX - 1e-5)[0]
VC.kin_box(st, "/World/clamp", [0.012, LY + 0.01, T + 0.004], [0.004, 0, Z0 + T / 2], collide=False)
BAR0 = np.array([LX, 0, Z0 + T / 2])
VC.kin_box(st, "/World/bar", [0.004, LY + 0.01, T + 0.004], BAR0, collide=False)
CL0 = np.array([0.004, 0, Z0 + T / 2])
def clamp_att():
    VC.attach_vtx(st, "/World/att_clamp", PATH, PATH, "/World/clamp", ROOT, P0[ROOT] - CL0, P=P)
clamp_att()
VC.attach_vtx(st, "/World/att_bar", PATH, PATH, "/World/bar", TIP, P0[TIP] - BAR0, P=P)
world.reset()
bar = SingleXFormPrim("/World/bar", name="bar")
# 中線(y≈0 最近那排)上下層平均
jc = np.argmin(np.abs(np.unique(np.round(P0[:, 1], 6))))
ycs = np.unique(np.round(P0[:, 1], 6)); yc = ycs[jc]
LINE = {}
for v in np.where(np.abs(P0[:, 1] - yc) < 1e-5)[0]:
    LINE.setdefault(round(P0[v, 0], 5), []).append(v)
XS = sorted(LINE)
def mid(p):
    return np.array([p[LINE[x]].mean(0) for x in XS])
def bend_deg(p):
    m = mid(p); xs = np.array(XS)
    r = (xs >= 0.008 - 1e-6) & (xs <= 0.020 + 1e-6); t = xs >= LX - 0.020 - 1e-6
    def ang(sel):
        q = m[sel]; d = q[-1] - q[0]; return np.degrees(np.arctan2(d[2], d[0]))
    return ang(t) - ang(r), m[-1]
def stvk(p, rest):
    Dm = np.stack([rest[TETS[:, i]] - rest[TETS[:, 0]] for i in (1, 2, 3)], 2)
    Ds = np.stack([p[TETS[:, i]] - p[TETS[:, 0]] for i in (1, 2, 3)], 2)
    V = np.abs(np.linalg.det(Dm)) / 6
    F = Ds @ np.linalg.inv(Dm)
    E = 0.5 * (np.transpose(F, (0, 2, 1)) @ F - np.eye(3))
    mu = a.young / (2 * (1 + a.poisson)); lam = a.young * a.poisson / ((1 + a.poisson) * (1 - 2 * a.poisson))
    tr = np.trace(E, axis1=1, axis2=2)
    return float((V * (mu * (E * E).sum((1, 2)) + 0.5 * lam * tr * tr)).sum())
REST = P0.copy()
Lf = LX - 0.008; PHI = np.radians(a.bend_deg); R = Lf / PHI
ss = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.), 1.))
T_SET = 0.3; T_REL = T_SET + a.span + a.hold; T_PL = T_REL - a.pre; T_END = T_REL + a.tobs
def bar_pose(t):
    ph = PHI * ss((t - T_SET) / a.span)
    if ph < 1e-9:
        return BAR0.copy(), 0.0
    r_ = Lf / ph
    return np.array([0.008 + r_ * np.sin(ph), 0, Z0 + T / 2 + r_ * (1 - np.cos(ph))]), ph
NS = int(round(T_END / a.dt)); S_PL = int(round(T_PL / a.dt)); S_REL = int(round(T_REL / a.dt)); PE = int(round(0.25 / a.dt))
released = False; res = {}; t0 = time.time()
def setv(attr, arr):
    attr.Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in arr]))
for s in range(1, NS + 1):
    t = s * a.dt
    if not released:
        p_, ph = bar_pose(t); bar.set_world_pose(position=p_, orientation=VC.quat_y(-ph))
    if s == S_PL:
        cur = mesh.pts(); b, _ = bend_deg(cur)
        e_old = stvk(cur, REST); res["bend_pl"] = b
        prim = st.GetPrimAtPath(PATH)
        if a.mode in (1, 2, 3, 5):
            setv(prim.GetAttribute("omniphysics:restShapePoints"), cur)
            if a.mode == 2:
                setv(mesh.pa, cur)
            if a.mode == 3:
                prim.SetActive(False); world.step(render=False); prim = st.GetPrimAtPath(PATH); prim.SetActive(True)
                mesh = VC.Mesh(st, PATH)
                setv(mesh.pa, cur)
            if a.mode == 5:
                api = [x for x in prim.GetAppliedSchemas() if "DeformableBody" in x and "Physx" not in x]
                P("   mode5 RemoveAPI/ApplyAPI %s" % api)
                for n in api: prim.RemoveAppliedSchema(n)
                world.step(render=False)
                for n in api: prim.AddAppliedSchema(n)
                setv(mesh.pa, cur)
        if a.mode == 4:
            st.RemovePrim(Sdf.Path("/World/att_clamp")); st.RemovePrim(Sdf.Path("/World/att_bar")); st.RemovePrim(Sdf.Path(PATH))
            info = build(pmap=lambda _p: cur.copy()); mesh = VC.Mesh(st, PATH)
            clamp_att()
            # 桿那排用當下位置對桿當下姿態的 local
            bp, bq = bar.get_world_pose(); Rb = VC.rot_y(-ph)
            VC.attach_vtx(st, "/World/att_bar", PATH, PATH, "/World/bar", TIP, (cur[TIP] - np.array(bp)) @ Rb, P=P)
        if a.mode:
            REST = cur.copy()
        world.step(render=False)
        c2 = mesh.pts(); ra = st.GetPrimAtPath(PATH).GetAttribute("omniphysics:restShapePoints").Get()
        ra = np.array(ra, float).reshape(-1, 3) if ra is not None else np.zeros((0, 3))
        P("★ t=%.2f mode %d:改 rest 前 彎角 %.1f° 彈性能(舊 rest)%.3e J;改後 彈性能(新 rest)%.3e J | 1 步後點數 %d 位移 max %.2f mm | USD rest 讀回與當下差 max %.2f mm"
          % (t, a.mode, b, e_old, stvk(cur, REST), len(c2), np.abs(c2 - cur).max() * 1e3 if len(c2) == len(cur) else -1,
             np.abs(ra - cur).max() * 1e3 if len(ra) == len(cur) else -1))
        continue
    if s == S_REL:
        cur = mesh.pts(); b, tip = bend_deg(cur); res["bend_rel"] = b
        st.RemovePrim(Sdf.Path("/World/att_bar")); released = True
        P("★ t=%.2f 放手(RemovePrim att_bar):彎角 %.1f°,尖端 (%.1f,%.1f) mm" % (t, b, tip[0] * 1e3, tip[2] * 1e3))
    world.step(render=False)
    if s % PE == 0 or s == NS:
        cur = mesh.pts()
        if not np.isfinite(cur).all(): P("★ NaN t=%.2f" % t); break
        b, tip = bend_deg(cur)
        tr = t - T_REL
        P("t=%.2f%s 彎角 %.1f° 尖端 (%.1f,%.1f) mm 彈性能 %.3e" % (t, " (放手後 %.2fs)" % tr if released else "", b, tip[0] * 1e3, tip[2] * 1e3, stvk(cur, REST)))
        for k in (0.5, 2.0, 5.0):
            if released and abs(tr - k) < a.dt / 2 + 1e-9: res["b%.1f" % k] = b
cur = mesh.pts(); res["bend_end"] = bend_deg(cur)[0]
P("\n===== RESULT mode %d grav %d E %.0e:放手前 %.1f° → 0.5s %.1f° / 2s %.1f° / 5s %.1f°;回彈(放手前 − 5s)= %.1f° | wall %.1fs"
  % (a.mode, a.grav, a.young, res.get("bend_rel", np.nan), res.get("b0.5", np.nan), res.get("b2.0", np.nan), res.get("bend_end", np.nan),
     res.get("bend_rel", np.nan) - res.get("bend_end", np.nan), time.time() - t0))
LOG.close(); sim.close()
