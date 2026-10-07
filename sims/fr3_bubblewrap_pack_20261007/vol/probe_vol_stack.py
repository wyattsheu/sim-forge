#!/usr/bin/env python3
"""probe_vol_stack.py — V3:兩層 volume 薄板疊、壓、放,量層間距與互穿;以及同一塊板對折(自碰撞)。

    /isaac-sim/python.sh probe_vol_stack.py --mode stack [--thick_mm 4] [--size_mm 200] [--nxy 20]
    /isaac-sim/python.sh probe_vol_stack.py --mode fold  [--save_fold x.npz | --rest_npz x.npz]

stack:兩塊 size x size x T 板,下板底 z=1mm、上板底 = 下板頂 + 10mm,落下疊好(2s)。
fold :一塊板,+x 邊綁 kinematic 桿(create_auto_deformable_attachment),繞 x=0 折線轉 180° 蓋回自己身上
       (3s),終點上層中面 = 下層中面 + T + 2mm;hold 0.5s 後 RemovePrim 放手,靜置 1.5s。
       selfCollision=True。彈性體 rest shape 是平的,放手會彈開 ⇒ 兩段式:
         第一次 --save_fold x.npz(放手前存形狀),第二次 --rest_npz x.npz(restShapePoints = 折好的形狀)。
之後兩種模式一樣:kinematic 壓板(300x300x10mm)1s 內從上方降到底面 z = 0.9 x 2T,壓 2s,0.5s 抬開,再看 3s。
量測:層間距(上層中面 − 下層中面,配對頂點中位)、上層頂面高(中位)、互穿(vol_pen.py)。
判準(寫死):互穿 0、放開後回彈 < 壓縮量 30%、靜置層間距 <= T + 2mm。
"""
import os, sys, argparse, time
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["stack", "fold"], required=True)
ap.add_argument("--thick_mm", type=float, default=4.0)
ap.add_argument("--size_mm", type=float, default=200.0)
ap.add_argument("--nxy", type=int, default=20)
ap.add_argument("--nz", type=int, default=1)
ap.add_argument("--young", type=float, default=2e4)
ap.add_argument("--poisson", type=float, default=0.45)
ap.add_argument("--areal", type=float, default=0.1, help="面密度 kg/m²")
ap.add_argument("--cont", type=float, default=0.002)
ap.add_argument("--rest", type=float, default=0.0005)
ap.add_argument("--self_filter", type=float, default=None, help="selfCollisionFilterDistance(預設不設 = -inf 自動)")
ap.add_argument("--no_self", action="store_true", help="fold 模式關掉 selfCollision(對照)")
ap.add_argument("--solver", type=int, default=32)
ap.add_argument("--dt", type=float, default=1/120.0)
ap.add_argument("--press_frac", type=float, default=0.9)
ap.add_argument("--press_mode", choices=["abs", "rel"], default="abs",
                help="abs:壓板底面到 press_frac x 2T(離地);rel:到 press_frac x 靜置時實測上層頂面高")
ap.add_argument("--max_depen", type=float, default=None, help="physxDeformableBody:maxDepenetrationVelocity(m/s)")
ap.add_argument("--save_fold", default="")
ap.add_argument("--rest_npz", default="")
ap.add_argument("--offset_mm", type=float, default=0.0, help="stack:上板 xy 平移(錯開網格,mm)")
ap.add_argument("--crease_mm", type=float, default=15.0, help="fold:折痕吃掉的長度,桿終點 x = -(S/2 - crease)")
ap.add_argument("--prefold", action="store_true", help="fold:直接把板建成對折好的形狀(rest = points),不用桿")
ap.add_argument("--gap_mm", type=float, default=2.0, help="prefold:上下層表面初始間隙")
ap.add_argument("--nx", type=int, default=80, help="prefold:沿折疊方向格數(折痕要夠細)")
ap.add_argument("--press_mass", type=float, default=0.0, help=">0:壓板在 T_STATIC 改成動態剛體(此質量 kg,從 12mm 高放下),T_PRESSED 再抓回 kinematic 抬走")
ap.add_argument("--print_dt", type=float, default=0.25)
ap.add_argument("--tag", default="")
a = ap.parse_args()
T = a.thick_mm / 1e3; S = a.size_mm / 1e3
HERE = os.path.dirname(os.path.abspath(__file__))
tag = a.tag or "v3_%s_T%g_S%g_n%d_%d_E%.0e_%s%g%s" % (a.mode, a.thick_mm, a.size_mm, a.nxy, a.nz, a.young,
                                                 a.press_mode, a.press_frac, "_restfold" if a.rest_npz else "")
os.makedirs(os.path.join(HERE, "logs"), exist_ok=True); os.makedirs(os.path.join(HERE, "img"), exist_ok=True)
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
import omni.usd
sys.path.insert(0, HERE)
import volcommon as VC
import vol_pen as VP

P("=== V3 %s ===" % tag); P("args:", vars(a))
world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

ZB = 0.001
kw = dict(nxy=a.nxy, nz=a.nz, youngs=a.young, poisson=a.poisson, areal=a.areal, cont=a.cont, rest=a.rest, solver=a.solver, P=P)
plates = []
if a.mode == "stack":
    plates.append(VC.build_plate(st, "/World/lower", S, T, ZB, "manual", **kw))
    plates.append(VC.build_plate(st, "/World/upper", S, T, ZB + T + 0.010, "manual",
                                 cx=a.offset_mm / 1e3, cy=a.offset_mm / 1e3, **kw))
    P("上板 xy 平移 %.1f mm(網格錯開)" % a.offset_mm)
elif a.prefold:
    G = a.gap_mm / 1e3
    ZL_, ZU_ = ZB + T / 2, ZB + 1.5 * T + G
    RM = (ZU_ - ZL_) / 2; LC = np.pi * RM; AA = (S - LC) / 2; XC = -S / 2 + AA; ZC = (ZL_ + ZU_) / 2
    def pmap(p):
        s_ = p[:, 0] + S / 2; w = p[:, 2] - (ZB + T / 2); q = p.copy()
        m1 = s_ <= AA; m3 = s_ >= AA + LC; m2 = ~m1 & ~m3
        q[m1, 0] = -S / 2 + s_[m1]; q[m1, 2] = ZL_ + w[m1]
        th = (s_[m2] - AA) / RM
        q[m2, 0] = XC + RM * np.sin(th) - w[m2] * np.sin(th); q[m2, 2] = ZC - RM * np.cos(th) + w[m2] * np.cos(th)
        q[m3, 0] = XC - (s_[m3] - AA - LC); q[m3, 2] = ZU_ - w[m3]
        return q
    P("prefold:折痕中面半徑 %.2fmm、弧長 %.1fmm、折線 x=%.1fmm;上下層表面間隙 %.1fmm;沿折向 %d 格(%.1fmm)"
      % (RM * 1e3, LC * 1e3, XC * 1e3, G * 1e3, a.nx, S / a.nx * 1e3))
    plates.append(VC.build_plate(st, "/World/plate", S, T, ZB, "manual", self_coll=not a.no_self,
                                 self_filter=a.self_filter, nx=a.nx, pmap=pmap, **kw))
    bp = st.GetPrimAtPath("/World/plate")
    P("selfCollision=%s selfCollisionFilterDistance=%s(schema 預設 -inf = 自動)"
      % (bp.GetAttribute("physxDeformableBody:selfCollision").Get(),
         bp.GetAttribute("physxDeformableBody:selfCollisionFilterDistance").Get()))
else:
    plates.append(VC.build_plate(st, "/World/plate", S, T, ZB, "manual", self_coll=not a.no_self,
                                 self_filter=a.self_filter, **kw))
    bp = st.GetPrimAtPath("/World/plate")
    P("selfCollision=%s selfCollisionFilterDistance=%s(schema 預設 -inf = 自動)"
      % (bp.GetAttribute("physxDeformableBody:selfCollision").Get(),
         bp.GetAttribute("physxDeformableBody:selfCollisionFilterDistance").Get()))

if a.max_depen is not None:
    for p_ in plates:
        VC.sa(st.GetPrimAtPath(p_["body_path"]), "physxDeformableBody:maxDepenetrationVelocity", float(a.max_depen),
              Sdf.ValueTypeNames.Float)
    P("maxDepenetrationVelocity = %g m/s(schema 預設 inf)" % a.max_depen)
PRESS_SZ = np.array([S + 0.1, S + 0.1, 0.010])
PRESS_Z0 = 0.060                                   # 壓板底面起始高度
VC.kin_box(st, "/World/press", PRESS_SZ, [0, 0, PRESS_Z0 + PRESS_SZ[2] / 2])
ZP = a.press_frac * 2 * T
P("壓板 %.0fx%.0fx%.0fmm,底面 %.0fmm → %.2fmm(= %.2f x 2T)" % (*(PRESS_SZ * 1e3), PRESS_Z0 * 1e3, ZP * 1e3, a.press_frac))

meshes = [VC.Mesh(st, p_["sim_path"]) for p_ in plates]
REST = [np.array(m.prim.GetAttribute("omniphysics:restShapePoints").Get(), float) for m in meshes]
TETS = [m.tets() for m in meshes]
# FLAT:攤平時的參數座標(配對、上下層分類、不相鄰判斷都用它);一般情況 = REST
if a.mode == "fold" and a.prefold:
    FLAT = [VP.grid_tets(a.nx, a.nxy, a.nz, S / a.nx, S / a.nxy, T / a.nz, [-S / 2, -S / 2, ZB])[0]]
    assert len(FLAT[0]) == len(REST[0])
else:
    FLAT = REST
SCOPE = "/World/attach_edge"
if a.mode == "fold" and not a.prefold:
    BX = 0.004
    BAR0 = np.array([S / 2, 0.0, ZB + T / 2])
    VC.kin_box(st, "/World/bar", [BX, S + 0.01, T + 0.004], BAR0)
    if a.rest_npz:
        _z = np.load(a.rest_npz)
        meshes[0].prim.GetAttribute("omniphysics:restShapePoints").Set(
            Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in _z["fold"]]))
        P("★ --rest_npz %s:restShapePoints = 折好的形狀(points 仍平)" % a.rest_npz)
    VC.attach_auto(st, SCOPE, "/World/plate", "/World/bar", P=P)
    from omni.physx import get_physx_attachment_private_interface
    get_physx_attachment_private_interface().update_auto_deformable_attachment(SCOPE)
    # -x 邊釘在不動的 kinematic 桿上(否則 4g 的板會被整片翻過去而不是折,實測 pass1 第一版)
    VC.kin_box(st, "/World/pin", [BX, S + 0.01, T + 0.004], [-S / 2, 0.0, ZB + T / 2])
    VC.attach_auto(st, "/World/attach_pin", "/World/plate", "/World/pin", P=P)
    get_physx_attachment_private_interface().update_auto_deformable_attachment("/World/attach_pin")

world.reset()
press = SingleXFormPrim("/World/press", name="press")
bar = SingleXFormPrim("/World/bar", name="bar") if (a.mode == "fold" and not a.prefold) else None
if bar is not None:
    vi = st.GetPrimAtPath(SCOPE + "/vtx_xform_attachment").GetAttribute("omniphysics:vtxIndicesSrc0").Get()
    P("attachment 綁住 %d 個頂點" % (len(vi) if vi else 0))
for p_, m in zip(plates, meshes):
    P("%s:%d 點 %d tets" % (p_["path"], len(m.pts()), len(m.tets())))

# 頂/底配對(用平的初始 rest:REST 是建板時寫的平板)
PAIRS = [VC.thickness_pairs(R_, T) for R_ in FLAT]
def mids(k, cur):
    b, t = PAIRS[k]
    return (cur[b] + cur[t]) / 2, cur[t], cur[b]

ss = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.), 1.))
if a.mode == "stack" or a.prefold:
    T_STATIC = 2.0
else:
    T_SET, T_FOLD, T_HOLD = 0.5, 3.0, 0.5
    T_REL = T_SET + T_FOLD + T_HOLD
    T_STATIC = T_REL + 1.5
    ZL = a.rest + T / 2
    ZU = ZL + T + 0.002
    R = S / 2
T_DOWN, T_PH, T_UP, T_WAIT = 1.0, 2.0, 0.5, 3.0
T_PRESSED = T_STATIC + T_DOWN + T_PH
T_END = T_PRESSED + T_UP + T_WAIT

def press_z(t):
    global ZP
    if a.press_mode == "rel" and "static" in res and not ZP_SET[0]:
        ZP = a.press_frac * res["static"]["top"]; ZP_SET[0] = True
        P("  (rel)壓板目標底面 = %.2f x 靜置上層頂面 %.2f = %.2f mm" % (a.press_frac, res["static"]["top"] * 1e3, ZP * 1e3))
    if t < T_STATIC:
        return PRESS_Z0
    if t < T_STATIC + T_DOWN:
        return PRESS_Z0 + (ZP - PRESS_Z0) * ss((t - T_STATIC) / T_DOWN)
    if t < T_PRESSED:
        return ZP
    return ZP + (PRESS_Z0 - ZP) * ss((t - T_PRESSED) / T_UP)

def bar_pose(t):
    ph = np.pi * ss((t - T_SET) / T_FOLD)
    d = ZU - ZL
    # 折痕要吃掉一段長度(厚板 180° 折不可能零半徑):半徑隨角度線性縮 a.crease_mm
    Rr = R - a.crease_mm / 1e3 * ph / np.pi
    x = Rr * np.cos(ph); z = ZL + d / 2 + Rr * np.sin(ph) - d / 2 * np.cos(ph)
    return np.array([x, 0.0, z]), ph

def measure(curs):
    """回傳 dict:層間距、上層頂面高、互穿。"""
    r = {}
    if a.mode == "stack":
        mlo, tlo, blo = mids(0, curs[0]); mup, tup, bup = mids(1, curs[1])
        # 只取中央 |x|,|y| < S/2-20mm,避免邊緣下垂
        c0 = (np.abs(FLAT[0][PAIRS[0][0], 0]) < S / 2 - 0.02) & (np.abs(FLAT[0][PAIRS[0][0], 1]) < S / 2 - 0.02)
        c1 = (np.abs(FLAT[1][PAIRS[1][0], 0]) < S / 2 - 0.02) & (np.abs(FLAT[1][PAIRS[1][0], 1]) < S / 2 - 0.02)
        r["gap"] = np.median(mup[c1, 2]) - np.median(mlo[c0, 2])
        r["top"] = np.median(tup[c1, 2]); r["bot"] = np.median(blo[c0, 2])
        bot_up = PAIRS[1][0]
        r["pen_bot"], pidx = VP.pen_count(curs[1], bot_up, curs[0], TETS[0])
        r["th_lo"] = np.median((tlo - blo)[c0, 2]); r["th_up"] = np.median((tup - bup)[c1, 2])
        if len(pidx):
            from scipy.spatial import cKDTree
            _tr = cKDTree(tlo[:, :2]); _d, _k = _tr.query(curs[1][pidx, :2])
            r["pen_depth"] = float(np.max(tlo[_k, 2] - curs[1][pidx, 2]))
        else:
            r["pen_depth"] = 0.0
        r["pen_up_all"], _ = VP.pen_count(curs[1], np.arange(len(curs[1])), curs[0], TETS[0])
        r["pen_lo_all"], _ = VP.pen_count(curs[0], np.arange(len(curs[0])), curs[1], TETS[1])
        r["pen"] = r["pen_up_all"] + r["pen_lo_all"]
    else:
        cur = curs[0]
        mid, tp, bt = mids(0, cur)
        xr = FLAT[0][PAIRS[0][0], 0]; yr = FLAT[0][PAIRS[0][0], 1]
        inner = (np.abs(yr) < S / 2 - 0.02)
        lo = (xr < -0.02) & (xr > -S / 2 + 0.02) & inner
        up = (xr > 0.02) & (xr < S / 2 - 0.02) & inner
        r["gap"] = np.median(mid[up, 2]) - np.median(mid[lo, 2])
        r["top"] = np.median(np.maximum(tp[up, 2], bt[up, 2]) )     # 翻過來後 原底面在上
        r["bot"] = np.median(bt[lo, 2])
        r["pen"], _ = VP.self_pen_count(cur, TETS[0], FLAT[0])
    return r

def snap(name, curs, title):
    groups = []
    cols = ["tab:blue", "tab:orange"]
    for k, c in enumerate(curs):
        sl = np.where(np.abs(FLAT[k][:, 1]) < 0.012)[0]
        groups.append((sl, cols[k], "layer %d |y|<12mm" % k))
    pz = press_z(tnow)
    def pr(ax):
        ax[0].axhline(pz * 1e3, color="k", lw=0.8)
    allp = np.concatenate(curs)
    idx_off = np.cumsum([0] + [len(c) for c in curs])
    VC.snap(os.path.join(HERE, "img", tag + "_" + name + ".png"), allp, title,
            groups=[(g[0] + idx_off[k], g[1], g[2]) for k, g in enumerate(groups)], extra=[pr],
            zlim=(-2, 30))

NSTEP = int(round(T_END / a.dt)); PE = max(1, int(round(a.print_dt / a.dt)))
marks = {int(round(T_STATIC / a.dt)): "static", int(round((T_PRESSED - 0.01) / a.dt)): "pressed", NSTEP: "end"}
ZP_SET = [False]
res = {}; maxpen = 0; t0 = time.time(); released = False; tnow = 0.0
from pxr import UsdPhysics
PRB = UsdPhysics.RigidBodyAPI(st.GetPrimAtPath("/World/press"))
if a.press_mass > 0:
    UsdPhysics.MassAPI.Apply(st.GetPrimAtPath("/World/press")).CreateMassAttr(float(a.press_mass))
    P("壓板改成 %.2f kg 動態剛體(%.0f Pa)" % (a.press_mass, a.press_mass * 9.81 / (PRESS_SZ[0] * PRESS_SZ[1])))
dyn = False
for s in range(1, NSTEP + 1):
    t = s * a.dt; tnow = t
    if a.press_mass > 0:
        if not dyn and "static" in res and t < T_PRESSED and not res.get("_dyn_done"):
            press.set_world_pose(position=np.array([0, 0, res["static"]["top"] + 0.003 + PRESS_SZ[2] / 2]),
                                 orientation=np.array([1., 0, 0, 0]))
            PRB.GetKinematicEnabledAttr().Set(False); dyn = True
        elif dyn and t >= T_PRESSED:
            PRB.GetKinematicEnabledAttr().Set(True); dyn = False; res["_dyn_done"] = True
        if dyn:
            world.step(render=False)
            if s % PE == 0 or s in marks:
                curs = [m.pts() for m in meshes]; r = measure(curs); maxpen = max(maxpen, r["pen"])
                pz_ = float(press.get_world_pose()[0][2]) - PRESS_SZ[2] / 2
                P("t=%.2fs 動態壓板底 %.2fmm | 層間距 %.2f mm | 上層頂面 %.2f | 互穿 %d" % (t, pz_ * 1e3, r["gap"] * 1e3, r["top"] * 1e3, r["pen"]))
                if s in marks:
                    res[marks[s]] = r
            continue
        if t >= T_PRESSED:
            press.set_world_pose(position=np.array([0, 0, PRESS_Z0 + PRESS_SZ[2] / 2]), orientation=np.array([1., 0, 0, 0]))
    else:
        press.set_world_pose(position=np.array([0, 0, press_z(t) + PRESS_SZ[2] / 2]), orientation=np.array([1., 0, 0, 0]))
    if bar is not None and not released:
        p_, ph = bar_pose(t)
        bar.set_world_pose(position=p_, orientation=VC.quat_y(-ph))
        if s == int(round(T_REL / a.dt)):
            cur = meshes[0].pts()
            if a.save_fold:
                np.savez(a.save_fold, fold=cur, rest=REST[0], tets=TETS[0]); P("存 %s" % a.save_fold)
            r_ = st.RemovePrim(Sdf.Path(SCOPE)); released = True
            m_ = measure([cur])
            P("★ t=%.2f 放手 RemovePrim -> %s;放手前 層間距 %.2fmm 自互穿 %d" % (t, r_, m_["gap"] * 1e3, m_["pen"]))
            snap("rel", [cur], tag + " before release t=%.2f" % t)
    world.step(render=False)
    if s % PE == 0 or s in marks:
        curs = [m.pts() for m in meshes]
        if not all(np.isfinite(c).all() for c in curs):
            P("★ NaN t=%.2f" % t); break
        r = measure(curs)
        maxpen = max(maxpen, r["pen"])
        ninv = sum(VC.inverted(c, TT, VC.tet_vol(R_, TT))[0] for c, TT, R_ in zip(curs, TETS, REST))
        if s == PE:
            P("  (t=%.2f)rest 形狀本身的自互穿(不相鄰):%d" % (t, VP.self_pen_count(REST[0], TETS[0], FLAT[0])[0]) if a.mode == "fold" else "")
        P("t=%.2fs 壓板底 %.2fmm | 層間距 %.2f mm | 上層頂面 %.2f 下層底面 %.2f mm | 互穿 %d%s | 反轉 %d"
          % (t, press_z(t) * 1e3, r["gap"] * 1e3, r["top"] * 1e3, r["bot"] * 1e3, r["pen"],
             (" (上層底面在下層內 %d,最深 %.2fmm)| 厚 下 %.2f 上 %.2f" % (r["pen_bot"], r["pen_depth"] * 1e3, r["th_lo"] * 1e3, r["th_up"] * 1e3))
             if "pen_bot" in r else "", ninv))
        if s in marks:
            res[marks[s]] = r
            snap(marks[s], curs, tag + " %s t=%.2f" % (marks[s], t))
wall = time.time() - t0
P("\n===== 判讀 V3 %s =====" % tag)
if all(k in res for k in ["static", "pressed", "end"]):
    hs, hp, he = res["static"]["top"], res["pressed"]["top"], res["end"]["top"]
    comp = hs - hp; reb = he - hp
    P("靜置層間距 %.2f mm(T + 2×rest = %.2f;判準 <= T+2mm = %.1f ⇒ %s)"
      % (res["static"]["gap"] * 1e3, (T + 2 * a.rest) * 1e3, (T + 0.002) * 1e3, "OK" if res["static"]["gap"] <= T + 0.002 else "NG"))
    P("上層頂面高:靜置 %.2f → 壓住 %.2f(壓板底 %.2f)→ 放開 3s %.2f mm;壓縮 %.2f 回彈 %.2f mm(%.0f%%,判準 < 30%% ⇒ %s)"
      % (hs * 1e3, hp * 1e3, ZP * 1e3, he * 1e3, comp * 1e3, reb * 1e3, 100 * reb / comp if comp > 0 else float("nan"),
         "OK" if comp > 0 and reb < 0.3 * comp else "NG"))
    P("層間距:靜置 %.2f 壓住 %.2f 放開 %.2f mm" % (res["static"]["gap"] * 1e3, res["pressed"]["gap"] * 1e3, res["end"]["gap"] * 1e3))
    P("互穿頂點:靜置 %d 壓住 %d 放開 %d;全程(每 0.25s 取樣)最多 %d ⇒ %s"
      % (res["static"]["pen"], res["pressed"]["pen"], res["end"]["pen"], maxpen, "OK" if maxpen == 0 else "NG"))
P("wall %.1fs / sim %.1fs = %.2f | 顯存 %s" % (wall, T_END, wall / T_END, VC.gpu_mem_mib()))
LOG.close()
sim.close()
