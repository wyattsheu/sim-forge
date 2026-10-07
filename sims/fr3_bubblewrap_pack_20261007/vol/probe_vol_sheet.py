#!/usr/bin/env python3
"""probe_vol_sheet.py — V1:volume deformable 薄板建得起來嗎、落地後穩不穩、厚度對不對。

    /isaac-sim/python.sh probe_vol_sheet.py --build manual|auto [--thick_mm 4] [--size_mm 200]
        [--nxy 20] [--nz 1] [--res 0(=size/T)] [--young 2e4] [--t_end 6] [--tag xxx]

場景:地板 z=0;板 size x size x T,底面在 z=20mm,中心在原點,自由落下。
材質:poisson 0.45、面密度 0.1 kg/m²(density = 0.1/T)、friction 0.8。
量測(每 0.5s 印):bbox、厚度(頂面頂點−對應底面頂點 距離的中位/最小)、最大頂點速度、
  反轉四面體數(sim mesh 與 collision mesh 各自)、總體積比。
判準(寫死):5s 時 厚度誤差 < 15%、最大速度 < 1 cm/s、反轉 0。
"""
import os, sys, argparse, time
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--build", choices=["manual", "auto"], required=True)
ap.add_argument("--thick_mm", type=float, default=4.0)
ap.add_argument("--size_mm", type=float, default=200.0)
ap.add_argument("--nxy", type=int, default=20)
ap.add_argument("--nz", type=int, default=1)
ap.add_argument("--res", type=int, default=0, help="auto:沿最長邊六面體數;0 = round(size/T)")
ap.add_argument("--young", type=float, default=2e4)
ap.add_argument("--cont", type=float, default=0.002)
ap.add_argument("--rest", type=float, default=0.0005)
ap.add_argument("--solver", type=int, default=32)
ap.add_argument("--dt", type=float, default=1/120.0)
ap.add_argument("--t_end", type=float, default=6.0)
ap.add_argument("--tag", default="")
a = ap.parse_args()
T = a.thick_mm / 1000.0; S = a.size_mm / 1000.0; Z0 = 0.020
RES = a.res if a.res > 0 else int(round(a.size_mm / a.thick_mm))
HERE = os.path.dirname(os.path.abspath(__file__))
tag = a.tag or "v1_%s_T%g_S%g_%s_E%.0e" % (a.build, a.thick_mm, a.size_mm,
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
from pxr import UsdGeom, PhysxSchema
import omni.usd
sys.path.insert(0, HERE)
import volcommon as VC

P("=== V1 %s ===" % tag)
P("args:", vars(a))
world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

info = VC.build_plate(st, "/World/plate", S, T, Z0, a.build, nxy=a.nxy, nz=a.nz, res=RES, youngs=a.young,
                      cont=a.cont, rest=a.rest, solver=a.solver, P=P)
P("density = %.1f kg/m³(面密度 0.1 kg/m² / T),預期質量 %.2f g" % (info["density"], 0.1 * S * S * 1e3))
t_build = time.time()
world.reset()
sim_m = VC.Mesh(st, info["sim_path"]); col_m = VC.Mesh(st, info["col_path"])
for k in range(3):
    ns, nc = len(sim_m.pts()), len(col_m.pts())
    P("reset 後第 %d 次查:sim mesh %d 點 %d tets;collision mesh %d 點 %d tets"
      % (k, ns, len(sim_m.tets()), nc, len(col_m.tets())))
    if ns > 0 and nc > 0:
        break
    world.step(render=False)
P("reset+cooking wall %.1fs" % (time.time() - t_build))
SP0, ST = sim_m.pts(), sim_m.tets()
CP0, CT = col_m.pts(), col_m.tets()
if len(SP0) == 0 or len(ST) == 0:
    P("★ 建不起來:sim mesh 沒有點/四面體"); P("判讀 V1:建成=否"); sim.close(); sys.exit(0)
SV0 = VC.tet_vol(SP0, ST); CV0 = VC.tet_vol(CP0, CT)
P("sim mesh bbox min %s max %s mm" % (np.round(SP0.min(0) * 1e3, 1), np.round(SP0.max(0) * 1e3, 1)))
P("col mesh bbox min %s max %s mm;rest 體積 sim %.3e col %.3e m³(幾何 %.3e);rest 已反轉 sim %d col %d"
  % (np.round(CP0.min(0) * 1e3, 1), np.round(CP0.max(0) * 1e3, 1), SV0.sum(), CV0.sum(), S * S * T,
     int((SV0 <= 0).sum()), int((CV0 <= 0).sum())))
PAIRS = VC.thickness_pairs(CP0, T, Z0)
P("厚度配對:%d 對(底面頂點 ↔ 正上方頂面頂點,在 collision mesh 上)" % len(PAIRS[0]))
if a.build == "auto":
    zs = np.unique(np.round(SP0[:, 2] * 1e4) / 10)
    P("auto sim 六面體網格 z 層(mm):%s" % zs[:12])

def stat(cur_s, cur_c, prev_s):
    th = VC.thickness(cur_c, PAIRS) if len(PAIRS[0]) else np.array([np.nan])
    vmax = np.linalg.norm(cur_s - prev_s, axis=1).max() / a.dt
    ninv_s, vs = VC.inverted(cur_s, ST, SV0)
    ninv_c, vc = VC.inverted(cur_c, CT, CV0)
    return dict(th_med=np.median(th), th_min=th.min(), th_max=th.max(), vmax=vmax, inv_s=ninv_s, inv_c=ninv_c,
                vol=vc.sum() / CV0.sum(), lo=cur_c.min(0), hi=cur_c.max(0))

NSTEP = int(round(a.t_end / a.dt)); PE = int(round(0.5 / a.dt)); S5 = int(round(5.0 / a.dt))
prev = SP0.copy(); res5 = None; vmax_sec = 0.0
VC.snap(os.path.join(HERE, "img", tag + "_0.png"), CP0, tag + " t=0", zlim=(-5, 40))
t0 = time.time(); twall5 = None; mem = None
for s in range(1, NSTEP + 1):
    world.step(render=False)
    cur_s = sim_m.pts()
    vstep = np.linalg.norm(cur_s - prev, axis=1).max() / a.dt
    vmax_sec = max(vmax_sec, vstep)
    if s % PE == 0 or s == S5:
        cur_c = col_m.pts()
        r = stat(cur_s, cur_c, prev)
        if not np.isfinite(cur_s).all():
            P("★ t=%.2f 出現 NaN/inf" % (s * a.dt))
        P("t=%.2fs bbox x[%.1f,%.1f] y[%.1f,%.1f] z[%.2f,%.2f]mm | 厚 中位 %.2f 最小 %.2f 最大 %.2f mm | "
          "v(此步) %.4f m/s v(本0.5s最大) %.4f | 反轉 sim %d col %d | 體積比 %.4f"
          % (s * a.dt, r["lo"][0] * 1e3, r["hi"][0] * 1e3, r["lo"][1] * 1e3, r["hi"][1] * 1e3,
             r["lo"][2] * 1e3, r["hi"][2] * 1e3, r["th_med"] * 1e3, r["th_min"] * 1e3, r["th_max"] * 1e3,
             r["vmax"], vmax_sec, r["inv_s"], r["inv_c"], r["vol"]))
        vmax_sec = 0.0
        if s == S5:
            res5 = r; twall5 = time.time() - t0; mem = VC.gpu_mem_mib()
            VC.snap(os.path.join(HERE, "img", tag + "_5s.png"), cur_c, tag + " t=5s", zlim=(-5, 40))
        if s == NSTEP // 2:
            VC.snap(os.path.join(HERE, "img", tag + "_mid.png"), cur_c, tag + " t=%.1fs" % (s * a.dt), zlim=(-5, 40))
    prev = cur_s
wall = time.time() - t0
P("\n===== 判讀 V1 %s =====" % tag)
P("建成=是  sim mesh %d 點 / %d tets;collision mesh %d 點 / %d tets" % (len(SP0), len(ST), len(CP0), len(CT)))
if res5 is not None:
    err = abs(res5["th_med"] - T) / T
    P("5s:厚度中位 %.2f mm(T=%.1f,誤差 %.1f%% %s)最小 %.2f | 最大速度 %.4f m/s(%s)| 反轉 sim %d col %d(%s)| 體積比 %.4f"
      % (res5["th_med"] * 1e3, T * 1e3, err * 100, "OK" if err < 0.15 else "NG", res5["th_min"] * 1e3,
         res5["vmax"], "OK" if res5["vmax"] < 0.01 else "NG", res5["inv_s"], res5["inv_c"],
         "OK" if res5["inv_s"] + res5["inv_c"] == 0 else "NG", res5["vol"]))
    P("bbox(5s,collision mesh)x %.1f y %.1f z[%.2f,%.2f] mm"
      % ((res5["hi"][0] - res5["lo"][0]) * 1e3, (res5["hi"][1] - res5["lo"][1]) * 1e3, res5["lo"][2] * 1e3, res5["hi"][2] * 1e3))
    P("wall/sim(前 5s)= %.2f;全程 %.1fs wall / %.1fs sim = %.2f | 顯存 %s"
      % (twall5 / 5.0, wall, a.t_end, wall / a.t_end, mem))
LOG.close()
sim.close()
