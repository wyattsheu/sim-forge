#!/usr/bin/env python3
"""probe_rest4.py — 解析四折 rest(make_rest.py 的 npz)建 volume 板,points = 平板。

    /isaac-sim/python.sh probe_rest4.py --npz rest_g10.npz --mode A|B [--rest_flat] [--cross] [--young 2e3] [--tag x]

  A:不建杯子、不折,只讓它自己落下 --tA 秒(看會不會自己折起來、炸不炸)。
  B:133x107x93 kinematic 方塊當杯子在中央;四根 kinematic 桿(無碰撞)用 VtxXformAttachment 綁四邊**非角落**
     最外圈(上下兩層),照 wrap_vol 順序 xp→xn→yp→yn 各 --span 秒(前半 弧1 立起 90°、後半 弧2 蓋頂 90°,
     弧長固定 = 等距;桿終點 = rest 的邊緣位姿),hold 0.5s,RemovePrim 全部 attachment 放手,看 --tobs 秒。
  --rest_flat:對照 C(rest = 平板,不設 restShapePoints)。--cross:去掉角落格(十字形板,make_rest 的 cross_keep)。
材料 / 建法照 wrap_vol:E 2e3、ν 0.45、T 4、面密度 0.1、manual 35x35x1、cont 2 / rest 0.5、自碰撞 filter 1mm、solver 128、dt 1/240。
量測:bbox、反轉(相對 rest 體積符號)、能量 proxy Σ V_rest Σ(σ-1)^2(F = rest→當下)、max 速度、自互穿(vol_pen,
  材料距離 > 3 格)、穿杯頂點數、各邊尖端(綁定頂點均值)位置、與 rest 的 RMS(A 用 Kabsch 對齊後、B 直接比)。
"""
import os, sys, argparse, time, json
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--npz", required=True)
ap.add_argument("--mode", choices=["A", "B"], required=True)
ap.add_argument("--rest_flat", action="store_true")
ap.add_argument("--cross", action="store_true")
ap.add_argument("--young", type=float, default=2e3)
ap.add_argument("--poisson", type=float, default=0.45)
ap.add_argument("--areal", type=float, default=0.1)
ap.add_argument("--solver", type=int, default=128)
ap.add_argument("--dt", type=float, default=1 / 240.0)
ap.add_argument("--self_filter", type=float, default=0.001)
ap.add_argument("--tA", type=float, default=3.0)
ap.add_argument("--span", type=float, default=3.0)
ap.add_argument("--tobs", type=float, default=3.0)
ap.add_argument("--tag", default="")
ap.add_argument("--pts_rest", action="store_true", help="診斷:points 也 = rest(預折,沒有初始應變)")
ap.add_argument("--self", type=int, default=1, help="自碰撞 1/0")
ap.add_argument("--diag", type=int, default=0, help="reset 前後與前 N 步逐步印 bbox/能量")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
NPZ = a.npz if os.path.isabs(a.npz) else os.path.join(HERE, a.npz)
Z = np.load(NPZ)
PRM = json.loads(str(Z["params"]))
tag = a.tag or "%s_%s%s%s_E%.0e" % (a.mode, os.path.splitext(os.path.basename(NPZ))[0],
                                    "_C" if a.rest_flat else "", "_cross" if a.cross else "", a.young)
os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
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
from pxr import UsdGeom, PhysxSchema, Sdf, Vt, Gf
from omni.physx.scripts import deformableUtils, physicsUtils
import omni.usd
sys.path.insert(0, os.path.dirname(HERE))
import volcommon as VC
import vol_pen as VP

P("=== probe_rest4 %s ===" % tag); P("args:", vars(a))
T = PRM["thick_mm"] / 1e3; S = PRM["sheet_mm"] / 1e3; n = PRM["nxy"]; h = S / n; ZB = PRM["ZB"]; r = PRM["r"]
SIDES = PRM["sides"]; MUGTOP, MUGBOT = PRM["MUGTOP"], PRM["MUGBOT"]
FLAT, TETS, REST = Z["flat"], Z["tets"], Z["fold"]
if a.cross:
    keep = Z["cross_keep"]; TETS = TETS[keep]
    used = np.unique(TETS); remap = -np.ones(len(FLAT), int); remap[used] = np.arange(len(used))
    FLAT, REST, TETS = FLAT[used], REST[used], remap[TETS]
P("板 %.0fmm n%d T%.0f r=%.1fmm gap=%.0fmm:%d 點 %d tets%s;rest = %s"
  % (S * 1e3, n, T * 1e3, r * 1e3, PRM["gap_mm"], len(FLAT), len(TETS), "(十字形)" if a.cross else "",
     "平板(C)" if a.rest_flat else "解析四折 " + os.path.basename(NPZ)))
RREF = FLAT if a.rest_flat else REST
PTS0 = REST if a.pts_rest else FLAT

world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

# ── 板(manual TetMesh,同 volcommon.build_plate 的 manual 分支)──
PATH = "/World/plate"
mat = VC.add_material(st, PATH + "_mat", a.young, a.poisson, a.areal / T, 0.8)
tm = UsdGeom.TetMesh.Define(st, PATH)
tm.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in PTS0]))
tm.GetTetVertexIndicesAttr().Set(Vt.Vec4iArray([Gf.Vec4i(*map(int, t)) for t in TETS]))
ok = deformableUtils.set_physics_volume_deformable_body(st, Sdf.Path(PATH))
body = st.GetPrimAtPath(PATH)
physicsUtils.add_physics_material_to_prim(st, body, mat)
body.ApplyAPI("PhysxBaseDeformableBodyAPI")
VC.sa(body, "physxDeformableBody:solverPositionIterationCount", int(a.solver), Sdf.ValueTypeNames.UInt)
VC.sa(body, "physxDeformableBody:selfCollision", bool(a.self), Sdf.ValueTypeNames.Bool)
VC.sa(body, "physxDeformableBody:selfCollisionFilterDistance", float(a.self_filter), Sdf.ValueTypeNames.Float)
pc = PhysxSchema.PhysxCollisionAPI.Apply(body)
pc.CreateContactOffsetAttr().Set(0.002); pc.CreateRestOffsetAttr().Set(0.0005)
ra = body.GetAttribute("omniphysics:restShapePoints")
P("set_physics_volume_deformable_body -> %s;restShapePoints 屬性存在 %s(%d 點)" % (ok, bool(ra), len(ra.Get() or [])))
if not a.rest_flat:
    ra.Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in REST]))
    P("★ restShapePoints ← 解析四折(points 仍平)")
MESH = VC.Mesh(st, PATH)

# ── 杯子 + 錨 ──
ZM0 = ZB + T / 2
ANC = []
if a.mode == "B":
    MUG = np.array([0.133, 0.107, 0.093])
    VC.kin_box(st, "/World/cup", MUG, [0, 0, MUGBOT + MUG[2] / 2])
    P("杯子方塊 133x107x93 kinematic,底 %.1f 頂 %.1f mm" % (MUGBOT * 1e3, MUGTOP * 1e3))
    s1x, s1y = SIDES["xp"]["s1"], SIDES["yp"]["s1"]
    for sd in ["xp", "xn", "yp", "yn"]:
        ax = 0 if sd[0] == "x" else 1; sg = 1.0 if sd[1] == "p" else -1.0
        other = s1y if ax == 0 else s1x
        vids = np.where((np.abs(FLAT[:, ax] - sg * S / 2) < 1e-6) & (np.abs(FLAT[:, 1 - ax]) <= other + 1e-6))[0]
        ctr = np.zeros(3); ctr[ax] = sg * S / 2; ctr[2] = ZM0
        pth = "/World/bars/" + sd
        VC.kin_box(st, pth, [0.004, 0.004, 0.004], ctr, collide=False, visible=False)
        sc = "/World/attach/" + sd
        VC.attach_vtx(st, sc, PATH, PATH, pth, vids, FLAT[vids] - ctr, P=lambda *x: None)
        ANC.append(dict(sd=sd, ax=ax, sg=sg, ctr=ctr, vids=vids, path=pth, scope=sc, p=SIDES[sd]))
        P("錨 %s:%d 點(非角落最外圈,上下兩層)" % (sd, len(vids)))

def qaxis(axis, ang):
    axis = np.asarray(axis, float); axis /= np.linalg.norm(axis)
    return np.array([np.cos(ang / 2), *(np.sin(ang / 2) * axis)])

def edge_curve(p, a1, a2):
    """剖面:s1 處弧1(弧長 πr/2,轉 a1)、牆、弧2(弧長 πr/2,轉 a2)、到邊緣。回傳 (along, z, 總轉角)。"""
    L1 = np.pi * r / 2
    segs = [(p["s1"], 0.0), (L1, a1), (p["s2"] - p["s1"] - L1, 0.0), (L1, a2), (S / 2 - p["s3"], 0.0)]
    pos = np.array([0.0, ZM0]); th = 0.0
    for L, turn in segs:
        if abs(turn) < 1e-9:
            pos = pos + L * np.array([np.cos(th), np.sin(th)])
        else:
            rho = L / turn
            pos = pos + rho * np.array([np.sin(th + turn) - np.sin(th), -np.cos(th + turn) + np.cos(th)])
            th += turn
    return pos[0], pos[1], th

ss = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.), 1.))
T_SET = 0.5
FT = {A["sd"]: T_SET + k * a.span for k, A in enumerate(ANC)}
T_REL = T_SET + 4 * a.span + 0.5 if a.mode == "B" else 1e9
T_END = T_REL + a.tobs if a.mode == "B" else a.tA

def anchor_pose(A, t):
    u = ss((t - FT[A["sd"]]) / a.span)
    a1 = np.pi / 2 * min(1.0, 2 * u); a2 = np.pi / 2 * max(0.0, 2 * u - 1)
    al, z, th = edge_curve(A["p"], a1, a2)
    pos = np.zeros(3); pos[A["ax"]] = A["sg"] * al; pos[2] = z
    axis = [0, -A["sg"], 0] if A["ax"] == 0 else [A["sg"], 0, 0]
    return pos, qaxis(axis, th)
# 自檢:終點把邊緣送到 rest 位置
for A in ANC:
    pos, q = anchor_pose(A, 1e9)
    w, x_, y_, z_ = q
    Rm = np.array([[1 - 2 * (y_ * y_ + z_ * z_), 2 * (x_ * y_ - z_ * w), 2 * (x_ * z_ + y_ * w)],
                   [2 * (x_ * y_ + z_ * w), 1 - 2 * (x_ * x_ + z_ * z_), 2 * (y_ * z_ - x_ * w)],
                   [2 * (x_ * z_ - y_ * w), 2 * (y_ * z_ + x_ * w), 1 - 2 * (x_ * x_ + y_ * y_)]])
    tgt = pos + (FLAT[A["vids"]] - A["ctr"]) @ Rm.T
    P("  錨 %s 終點與 rest 邊緣差 max %.2f mm;終點 %s mm" % (A["sd"], np.abs(tgt - REST[A["vids"]]).max() * 1e3,
                                                   np.round(pos * 1e3, 1)))

if a.diag:
    _p = MESH.pts(); P("diag reset 前 USD points bbox %s mm" % np.round((_p.max(0) - _p.min(0)) * 1e3, 1))
world.reset()
if a.diag:
    for _at in body.GetAttributes():
        _v = _at.Get()
        try:
            _n = len(_v) if not isinstance(_v, str) else -1
        except TypeError:
            _n = -1
        P("  attr %s %s" % (_at.GetName(), ("<len %d>" % _n) if _n > 6 else _v))
    _p = MESH.pts(); P("diag reset 後 USD points bbox %s mm;與初始 points 差 max %.2f mm"
                       % (np.round((_p.max(0) - _p.min(0)) * 1e3, 1), np.abs(_p - PTS0).max() * 1e3))
bars = {A["sd"]: SingleXFormPrim(A["path"], name="bar_" + A["sd"]) for A in ANC}
P0 = MESH.pts(); assert len(P0) == len(FLAT)
VR = VP.tet_vol(RREF, TETS); SGN = np.sign(VR)
DmR = np.stack([RREF[TETS[:, i]] - RREF[TETS[:, 0]] for i in (1, 2, 3)], 2); DmRi = np.linalg.inv(DmR)

def energy(Pc):
    Ds = np.stack([Pc[TETS[:, i]] - Pc[TETS[:, 0]] for i in (1, 2, 3)], 2)
    sv = np.linalg.svd(Ds @ DmRi, compute_uv=False)
    return float((((sv - 1) ** 2).sum(1) * np.abs(VR)).sum()), float(sv[:, 0].max()), float((1 / np.maximum(sv[:, 2], 1e-9)).max())

def kabsch_rms(Pc, Q):
    a0, b0 = Pc.mean(0), Q.mean(0); H = (Pc - a0).T @ (Q - b0)
    U, _, Vt_ = np.linalg.svd(H); d = np.sign(np.linalg.det(Vt_.T @ U.T))
    Rm = Vt_.T @ np.diag([1, 1, d]) @ U.T
    return float(np.sqrt((((Pc - a0) @ Rm.T - (Q - b0)) ** 2).sum(1).mean()))

CUPLO = np.array([-0.0665, -0.0535, MUGBOT]); CUPHI = np.array([0.0665, 0.0535, MUGTOP])
def meas(Pc, prev, t, label, pen=False):
    e, smax, sinv = energy(Pc)
    inv = int(((VP.tet_vol(Pc, TETS) * SGN) <= 0).sum())
    bb = (Pc.max(0) - Pc.min(0)) * 1e3
    vmax = np.linalg.norm(Pc - prev, axis=1).max() / a.dt if prev is not None else 0.0
    incup = int(((Pc > CUPLO) & (Pc < CUPHI)).all(1).sum()) if a.mode == "B" else -1
    sp = VP.self_pen_count(Pc, TETS, FLAT, far=3 * h)[0] if pen else -1
    rms_al = kabsch_rms(Pc, REST) * 1e3; rms = float(np.sqrt(((Pc - REST) ** 2).sum(1).mean())) * 1e3
    tips = " ".join("%s(%.0f,%.0f,%.0f)" % (A["sd"], *(Pc[A["vids"]].mean(0) * 1e3)) for A in ANC)
    P("t=%5.2f %-8s bbox %3.0fx%3.0fx%3.0f | E %.3e σmax %.2f 1/σmin %.2f | 反轉 %d | vmax %.3f m/s | 穿杯 %d | 自穿 %d"
      " | 對 rest RMS %.1f(對齊後 %.1f)mm %s"
      % (t, label, *bb, e, smax, sinv, inv, vmax, incup, sp, rms, rms_al, tips))
    return dict(t=t, bb=bb, e=e, inv=inv, vmax=vmax, incup=incup, sp=sp, rms=rms, rms_al=rms_al)

e0 = energy(PTS0)
P("t=0 能量(points=平板 vs rest):E %.3e σmax %.2f 1/σmin %.2f" % e0)
NSTEP = int(round(T_END / a.dt)); PE = int(round(0.25 / a.dt)); S_REL = int(round(T_REL / a.dt))
prev = P0.copy(); hist = []; released = False; rel = {}
hist.append(meas(P0, None, 0.0, "init", pen=True))
t0w = time.time(); boom = False
for k in range(a.diag):
    _q = MESH.pts(); world.step(render=False); _p = MESH.pts()
    P("diag step %d:bbox %s mm | E %.3e σmax %.2f 1/σmin %.2f | 單步位移 max %.2f mm"
      % (k + 1, np.round((_p.max(0) - _p.min(0)) * 1e3, 1), *energy(_p), np.linalg.norm(_p - _q, axis=1).max() * 1e3))
for s in range(1, NSTEP + 1):
    t = s * a.dt
    if not released:
        for A in ANC:
            p_, q_ = anchor_pose(A, t)
            bars[A["sd"]].set_world_pose(position=p_, orientation=q_)
    if s == S_REL and a.mode == "B":
        cur = MESH.pts()
        rel["P"] = cur.copy(); rel["tips"] = {A["sd"]: cur[A["vids"]].mean(0) for A in ANC}
        hist.append(meas(cur, prev, t, "放手前", pen=True))
        for A in ANC:
            st.RemovePrim(Sdf.Path(A["scope"]))
        released = True
        P("★ t=%.2f 放手(RemovePrim 4 個 attachment)" % t)
    if s % PE == 0:
        prev = MESH.pts()
    world.step(render=False)
    if s % PE == 0 or s == NSTEP:
        cur = MESH.pts()
        if not np.isfinite(cur).all():
            P("★ t=%.2f NaN" % t); boom = True; break
        lab = "A自由" if a.mode == "A" else ("放手後" if released else "折中")
        m = meas(cur, prev, t, lab, pen=(s % (4 * PE) == 0 or s == NSTEP))
        hist.append(m)
cur = MESH.pts()
P("\n===== 判讀 %s =====" % tag)
P("t=0 能量 %.3e σmax %.2f 1/σmin %.2f;wall %.1fs" % (*e0, time.time() - t0w))
H = [m for m in hist]
P("全程:bbox 最大 %s mm;反轉最多 %d;vmax 最大 %.3f m/s;能量最大 %.3e;自穿最多 %d;穿杯最多 %d"
  % (np.round(np.max([m["bb"] for m in H], 0)), max(m["inv"] for m in H), max(m["vmax"] for m in H),
     max(m["e"] for m in H), max(m["sp"] for m in H), max(m["incup"] for m in H)))
fin = H[-1]
P("結束:bbox %s;能量 %.3e;反轉 %d;對 rest RMS %.1f(對齊後 %.1f)mm" % (np.round(fin["bb"]), fin["e"], fin["inv"], fin["rms"], fin["rms_al"]))
if a.mode == "B" and "tips" in rel:
    for A in ANC:
        p0 = rel["tips"][A["sd"]]; p1 = cur[A["vids"]].mean(0); pr = REST[A["vids"]].mean(0)
        P("尖端 %s:放手前 (%.0f,%.0f,%.0f) → %.1fs 後 (%.0f,%.0f,%.0f) mm | dz %+.1f dxy %.1f mm | 對 rest 差 %.1f mm"
          % (A["sd"], *(p0 * 1e3), a.tobs, *(p1 * 1e3), (p1[2] - p0[2]) * 1e3, np.linalg.norm(p1[:2] - p0[:2]) * 1e3,
             np.linalg.norm(p1 - pr) * 1e3))
    d = np.linalg.norm(cur - rel["P"], axis=1)
    P("放手後 %.1fs 全板位移 中位 %.1f max %.1f mm" % (a.tobs, np.median(d) * 1e3, d.max() * 1e3))
np.savez(os.path.join(HERE, "logs", tag + "_final.npz"), final=cur, flat=FLAT, rest=REST, tets=TETS,
         before_rel=rel.get("P", cur))
P("wall %.1fs" % (time.time() - t0w))
LOG.close()
sim.close()
