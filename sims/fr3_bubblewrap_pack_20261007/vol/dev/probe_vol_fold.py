#!/usr/bin/env python3
"""probe_vol_fold.py — V2:volume 薄板能不能沿方塊折上去、蓋過頂面、放手。

    /isaac-sim/python.sh probe_vol_fold.py [--build manual|auto] [--thick_mm 4] [--size_mm 400]
        [--nxy 35] [--nz 1] [--res 0] [--young 2e4] [--attach auto|vtx] [--tag xxx]

場景:板 size x size x T 平鋪在地上(底面 z≈0.5mm);kinematic 方塊 100x100x90mm 壓在板中央上方(底面離板頂 1mm)。
  板的 +x 邊(整排邊緣頂點,上下層都含)綁到 kinematic 細長桿(attachment),桿走兩段圓弧:
    A 段 繞底部折線(方塊 +x 側面底)轉 90° → 立起來貼方塊側面
    B 段 繞頂部折線轉 90°(半徑 = 剩下的長度)→ 蓋過方塊頂面,終點中面高 = 方塊頂 + T + 2mm
  桿的姿態跟著轉(繞 y 共轉 180°),邊緣截面不會被扭。之後 hold 1s,stage.RemovePrim(attachment scope) 放手,再看 2s。
  ★ size 預設 400:方塊 90mm 高,折邊 = size/2 − 50mm,200 的板折邊只有 50mm、連方塊側面都蓋不滿。
量測:折過去(中央 |y|<50mm 的邊緣頂點最終 x 是否在 [-50,50]、z 高於方塊頂);全程最多反轉四面體數;
  折線處(兩條折線 ±20mm 內的頂/底配對)厚度最小值、< 0.5T 的配對數;體積比;四面體邊長比 max/min;
  放手那一步遠處頂點(離邊 > 100mm)單步位移;放手後 2s 邊緣(中央)z/x 變化。
"""
import os, sys, argparse, time
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--build", choices=["manual", "auto"], default="manual")
ap.add_argument("--thick_mm", type=float, default=4.0)
ap.add_argument("--size_mm", type=float, default=400.0)
ap.add_argument("--nxy", type=int, default=35)
ap.add_argument("--nz", type=int, default=1)
ap.add_argument("--res", type=int, default=0)
ap.add_argument("--young", type=float, default=2e4)
ap.add_argument("--attach", choices=["auto", "vtx"], default="auto")
ap.add_argument("--cont", type=float, default=0.002)
ap.add_argument("--rest", type=float, default=0.0005)
ap.add_argument("--solver", type=int, default=32)
ap.add_argument("--dt", type=float, default=1/120.0)
ap.add_argument("--span", type=float, default=2.5, help="每段弧線秒數")
ap.add_argument("--no_release", action="store_true")
ap.add_argument("--self_coll", action="store_true")
ap.add_argument("--plastic", action="store_true", help="放手前把 omniphysics:restShapePoints 改成當下形狀(runtime)")
ap.add_argument("--save_fold", default="", help="把 B 段結束的 sim mesh 形狀存成 npz")
ap.add_argument("--rest_npz", default="", help="建板時 restShapePoints 改用這個 npz 的形狀(points 仍是平的)")
ap.add_argument("--tag", default="")
a = ap.parse_args()
T = a.thick_mm / 1e3; S = a.size_mm / 1e3
RES = a.res if a.res > 0 else int(round(a.size_mm / a.thick_mm))
HERE = os.path.dirname(os.path.abspath(__file__))
tag = a.tag or "v2_%s_%s_T%g_S%g_%s_E%.0e" % (a.build, a.attach, a.thick_mm, a.size_mm,
                                              ("n%d_%d" % (a.nxy, a.nz)) if a.build == "manual" else "r%d" % RES, a.young)
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
from pxr import UsdGeom, PhysxSchema, Sdf
import omni.usd
sys.path.insert(0, HERE)
import volcommon as VC

P("=== V2 %s ===" % tag); P("args:", vars(a))
world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

ZB = 0.001                                  # 板底面初始高度
info = VC.build_plate(st, "/World/plate", S, T, ZB, a.build, nxy=a.nxy, nz=a.nz, res=RES, youngs=a.young,
                      cont=a.cont, rest=a.rest, solver=a.solver, self_coll=a.self_coll, P=P)
CUBE = np.array([0.10, 0.10, 0.09])
CZB = a.rest + T + 0.001                    # 方塊底面 = 板頂(落定後)+ 1mm
CTOP = CZB + CUBE[2]
VC.kin_box(st, "/World/cube", CUBE, [0, 0, CZB + CUBE[2] / 2])
P("方塊 100x100x90mm kinematic,底 z=%.1fmm 頂 z=%.1fmm" % (CZB * 1e3, CTOP * 1e3))

# 桿:綁 +x 邊
dxy = S / a.nxy if a.build == "manual" else S / RES
BX = min(0.004, 0.6 * dxy)
ZMID0 = a.rest + T / 2
BAR0 = np.array([S / 2, 0.0, ZB + T / 2])
VC.kin_box(st, "/World/bar", [BX, S + 0.01, T + 0.004], BAR0)
P("桿 %.1f x %.0f x %.1f mm,中心 %s mm(邊緣頂點間距 %.1fmm)" % (BX * 1e3, (S + .01) * 1e3, (T + .004) * 1e3,
                                                       np.round(BAR0 * 1e3, 1), dxy * 1e3))

# 邊緣頂點(用建網格時的已知位置;auto 的 sim mesh 要 reset 後才有)
SCOPE = "/World/attach_edge"
def edge_ids(Prest):
    if len(Prest) == 0:
        return np.zeros(0, int)
    return np.where(Prest[:, 0] > Prest[:, 0].max() - 1e-4)[0]

sim_m = VC.Mesh(st, info["sim_path"]); col_m = VC.Mesh(st, info["col_path"])
# auto 建法:reset 前先讓 kit 跑幾次 update 觸發 cooking,才拿得到 sim mesh 的頂點去決定邊緣
for k in range(20):
    if len(sim_m.pts()) > 0:
        break
    sim.update()
P("reset 前 sim mesh 點數 %d(update %d 次)" % (len(sim_m.pts()), k))
REST = np.array(sim_m.prim.GetAttribute("omniphysics:restShapePoints").Get() or sim_m.pts(), float).reshape(-1, 3)
if a.rest_npz:
    from pxr import Vt, Gf
    _z = np.load(a.rest_npz)
    assert len(_z["fold"]) == len(REST), "npz 頂點數不符"
    sim_m.prim.GetAttribute("omniphysics:restShapePoints").Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in _z["fold"]]))
    P("★ --rest_npz %s:restShapePoints = 折好的形狀;points 仍是平的" % a.rest_npz)
E = edge_ids(REST)
P("邊緣頂點(sim mesh rest,x > S/2-0.1mm):%d 個" % len(E))
if a.attach == "auto":
    VC.attach_auto(st, SCOPE, info["body_path"], "/World/bar", P=P)
    from omni.physx import get_physx_attachment_private_interface
    P("update_auto_deformable_attachment -> %s" % get_physx_attachment_private_interface().update_auto_deformable_attachment(SCOPE))
else:
    VC.attach_vtx(st, SCOPE, info["body_path"], info["sim_path"], "/World/bar", E, REST[E] - BAR0, P=P)
world.reset()
SP0, ST = sim_m.pts(), sim_m.tets(); CP0, CT = col_m.pts(), col_m.tets()
P("sim mesh %d 點 %d tets;col mesh %d 點 %d tets" % (len(SP0), len(ST), len(CP0), len(CT)))
if len(REST) == 0:
    assert a.attach == "auto", "auto 建法在 reset 前拿不到 sim mesh,只能用 --attach auto"
    REST = np.array(sim_m.prim.GetAttribute("omniphysics:restShapePoints").Get(), float).reshape(-1, 3)
    E = edge_ids(REST)
    P("reset 後才有 sim mesh:rest bbox %s ~ %s mm;邊緣頂點(x=max)%d 個"
      % (np.round(REST.min(0) * 1e3, 1), np.round(REST.max(0) * 1e3, 1), len(E)))
P("--- attachment prim 內容(reset 後)---"); VC.dump_prim(st, SCOPE, P=P)
bar = SingleXFormPrim("/World/bar", name="bar")

SV0 = VC.tet_vol(REST, ST); CV0 = VC.tet_vol(CP0, CT)
PAIRS = VC.thickness_pairs(CP0, T)
EDG = np.unique(np.sort(np.concatenate([ST[:, [i, j]] for i in range(4) for j in range(i + 1, 4)]), axis=1), axis=0)
L0 = np.linalg.norm(REST[EDG[:, 0]] - REST[EDG[:, 1]], axis=1)

XA = CUBE[0] / 2 + 0.001 + T / 2            # 底部折線(中面)
ZA = ZMID0
R = S / 2 - XA
ZBM = CTOP + T + 0.002                      # 終點中面高
H = ZBM - ZA
ARM = R - H
P("折線 A x=%.1f z=%.1f;折邊長 R=%.1f;頂部折線 z=%.1f;越過頂面的長度 arm=%.1f → 邊緣終點 x=%.1f mm"
  % (XA * 1e3, ZA * 1e3, R * 1e3, ZBM * 1e3, ARM * 1e3, (XA - ARM) * 1e3))
if ARM <= 0:
    P("★ 折邊不夠長,蓋不過頂面(size 要更大)")
# 折線附近的配對(以 rest x 判)
xr = CP0[PAIRS[0], 0]
FOLD_A = np.abs(xr - XA) < 0.02
FOLD_B = np.abs(xr - (XA + H)) < 0.02
P("厚度配對 %d;折線 A 附近 %d、折線 B 附近 %d" % (len(xr), FOLD_A.sum(), FOLD_B.sum()))
FAR = np.where(SP0[:, 0] < S / 2 - 0.10)[0]
CEN = E[np.abs(SP0[E, 1]) < 0.05]

ss = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.), 1.))
T_SET, SPAN, T_HOLD, T_OBS = 0.5, a.span, 1.0, 2.0
T_REL = T_SET + 2 * SPAN + T_HOLD
T_END = T_REL + T_OBS
def bar_pose(t):
    if t <= T_SET + SPAN:
        ph = np.pi / 2 * ss((t - T_SET) / SPAN)
        x, z = XA + R * np.cos(ph), ZA + R * np.sin(ph)
    else:
        ph = np.pi / 2 + np.pi / 2 * ss((t - T_SET - SPAN) / SPAN)
        x, z = XA + ARM * np.cos(ph), ZA + H + ARM * np.sin(ph)
    return np.array([x, 0.0, z]), ph

def side_snap(name, cur, title):
    sl = np.where(np.abs(SP0[:, 1]) < 0.03)[0] if a.build == "manual" else np.where(np.abs(SP0[:, 1]) < 0.01)[0]
    def cube(ax):
        ax[0].add_patch(__import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(
            (-50, CZB * 1e3), 100, 90, fill=False, ec="k"))
        ax[1].add_patch(__import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(
            (-50, -50), 100, 100, fill=False, ec="k"))
    VC.snap(os.path.join(HERE, "img", tag + "_" + name + ".png"), cur, title,
            groups=[(sl, "tab:blue", "slice |y|<30mm"), (E, "tab:red", "attached edge")], extra=[cube])

NSTEP = int(round(T_END / a.dt)); PE = int(round(0.25 / a.dt)); S_REL = int(round(T_REL / a.dt))
worst = dict(inv_s=0, inv_c=0, thA=9, thB=9, thall=9, nthin=0, lmax=0, lmin=9, volmin=9, volmax=0)
prev = SP0.copy(); t0 = time.time(); released = False; rel = {}
side_snap("0", SP0, tag + " t=0")
for s in range(1, NSTEP + 1):
    t = s * a.dt
    if not released:
        p, ph = bar_pose(t)
        bar.set_world_pose(position=p, orientation=VC.quat_y(-ph))
    if s == S_REL and not a.no_release:
        cur = sim_m.pts()
        rel["edge_before"] = cur[CEN].mean(0)
        if a.plastic:
            from pxr import Vt, Gf
            _ra = sim_m.prim.GetAttribute("omniphysics:restShapePoints")
            _ra.Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in cur]))
            P("   ★ --plastic:restShapePoints ← 當下形狀(%d 點)" % len(cur))
        r_ = st.RemovePrim(Sdf.Path(SCOPE)); released = True
        world.step(render=False)
        cur2 = sim_m.pts()
        d = np.linalg.norm(cur2 - cur, axis=1)
        dprev = np.linalg.norm(cur - prev, axis=1)
        P("\n★ t=%.2fs 放手:stage.RemovePrim(%s) -> %s;scope 還在? %s" % (t, SCOPE, r_, bool(st.GetPrimAtPath(SCOPE))))
        P("   放手那一步 遠處頂點(離邊>100mm,%d 個)單步位移 max %.3f mm(前一步 %.3f mm);邊緣(中央)單步位移 max %.3f mm"
          % (len(FAR), d[FAR].max() * 1e3, dprev[FAR].max() * 1e3, d[CEN].max() * 1e3))
        side_snap("rel", cur, tag + " before release t=%.2f" % t)
        prev = cur2
        continue
    if s % PE == 0 or s == NSTEP:
        prev = sim_m.pts()
    world.step(render=False)
    if s % PE == 0 or s == NSTEP:
        cur = sim_m.pts(); curc = col_m.pts()
        ni_s, _ = VC.inverted(cur, ST, SV0); ni_c, vc = VC.inverted(curc, CT, CV0)
        th = VC.thickness(curc, PAIRS)
        L = np.linalg.norm(cur[EDG[:, 0]] - cur[EDG[:, 1]], axis=1) / L0
        vol = vc.sum() / CV0.sum()
        worst.update(inv_s=max(worst["inv_s"], ni_s), inv_c=max(worst["inv_c"], ni_c),
                     thA=min(worst["thA"], th[FOLD_A].min()), thB=min(worst["thB"], th[FOLD_B].min()),
                     thall=min(worst["thall"], th.min()), nthin=max(worst["nthin"], int((th < 0.5 * T).sum())),
                     lmax=max(worst["lmax"], L.max()), lmin=min(worst["lmin"], L.min()),
                     volmin=min(worst["volmin"], vol), volmax=max(worst["volmax"], vol))
        bp = np.array(bar.get_world_pose()[0])
        ec = cur[CEN].mean(0)
        P("t=%.2fs 桿 (%.1f,%.1f)mm | 邊緣中央均值 (%.1f,%.1f,%.1f)mm 與桿差 %.1fmm | 反轉 sim %d col %d | "
          "厚 中位 %.2f 最小 %.2f 折A最小 %.2f 折B最小 %.2f(<0.5T 有 %d 對)| 邊長比 [%.3f,%.3f] 體積比 %.4f | vmax %.3f m/s"
          % (t, bp[0] * 1e3, bp[2] * 1e3, *(ec * 1e3), np.linalg.norm(ec[[0, 2]] - bp[[0, 2]]) * 1e3 if not released else -1,
             ni_s, ni_c, np.median(th) * 1e3, th.min() * 1e3, th[FOLD_A].min() * 1e3, th[FOLD_B].min() * 1e3,
             int((th < 0.5 * T).sum()), L.min(), L.max(), vol, np.linalg.norm(cur - prev, axis=1).max() / a.dt))
        if not np.isfinite(cur).all():
            P("★ NaN"); break
        if abs(t - (T_SET + SPAN)) < 1e-6:
            side_snap("A", cur, tag + " end of arc A t=%.2f" % t)
        if abs(t - (T_SET + 2 * SPAN)) < 1e-6:
            rel["fold_end"] = cur.copy()
            if a.save_fold:
                np.savez(a.save_fold, fold=cur, rest=REST, tets=ST)
                P("   存 %s" % a.save_fold)
            side_snap("B", cur, tag + " end of arc B t=%.2f" % t)
cur = sim_m.pts()
side_snap("end", cur, tag + " end t=%.2f" % T_END)
wall = time.time() - t0
P("\n===== 判讀 V2 %s =====" % tag)
FE = rel.get("fold_end", cur)
ex = FE[CEN, 0]; ez = FE[CEN, 2]
ok_fold = (np.abs(ex) < 0.05).all() and (ez > CTOP).all()
P("折過去(B 段結束時,中央 %d 個邊緣頂點):x ∈ [%.1f, %.1f] mm、z ∈ [%.1f, %.1f] mm(方塊頂 %.1f)⇒ %s"
  % (len(CEN), ex.min() * 1e3, ex.max() * 1e3, ez.min() * 1e3, ez.max() * 1e3, CTOP * 1e3, "是" if ok_fold else "否"))
P("全程最多反轉:sim %d col %d | 厚度最小:全板 %.2f 折線A %.2f 折線B %.2f mm(T=%.1f;<0.5T 最多 %d 對)"
  % (worst["inv_s"], worst["inv_c"], worst["thall"] * 1e3, worst["thA"] * 1e3, worst["thB"] * 1e3, T * 1e3, worst["nthin"]))
P("體積比範圍 [%.4f, %.4f];四面體邊長比範圍 [%.3f, %.3f]" % (worst["volmin"], worst["volmax"], worst["lmin"], worst["lmax"]))
if "edge_before" in rel:
    e0 = rel["edge_before"]; e1 = cur[CEN].mean(0)
    P("放手:前 邊緣中央 (%.1f,%.1f,%.1f) → 2s 後 (%.1f,%.1f,%.1f) mm;dz=%+.1f mm dx=%+.1f mm"
      % (*(e0 * 1e3), *(e1 * 1e3), (e1[2] - e0[2]) * 1e3, (e1[0] - e0[0]) * 1e3))
    P("放手後 2s 中央邊緣頂點 x ∈ [%.1f, %.1f] z ∈ [%.1f, %.1f] mm(仍在頂面上? %s)"
      % (cur[CEN, 0].min() * 1e3, cur[CEN, 0].max() * 1e3, cur[CEN, 2].min() * 1e3, cur[CEN, 2].max() * 1e3,
         "是" if ((np.abs(cur[CEN, 0]) < 0.05).all() and (cur[CEN, 2] > CTOP).all()) else "否"))
P("wall %.1fs / sim %.1fs = %.2f | 顯存 %s" % (wall, T_END, wall / T_END, VC.gpu_mem_mib()))
LOG.close()
sim.close()
