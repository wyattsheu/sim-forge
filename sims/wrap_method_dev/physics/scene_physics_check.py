#!/usr/bin/env python3
"""scene_physics_check.py — 開物理跑完整場景(手臂 + 桌子 + 紙箱),錄影並量數字。

  /isaac-sim/python.sh scene_physics_check.py scene_final.usd --out phys --secs 6
  /isaac-sim/python.sh scene_physics_check.py scene_final.usd --out phys_nc --no_crease   # 陰性對照

量什麼(全部用模擬讀回的姿態,不看畫面):
  * 箱底 base 的位移 / 底面離桌面的高度差(穿桌 or 浮空)
  * 四片蓋子繞鉸鏈的角度(摺痕撐不撐得住)
  * 兩支手臂的關節角漂移(紙箱放進去有沒有干擾到手臂)
摺痕:/World/Packed/Box/crease_* 是被動關節,彈塑性力矩每個物理步外加(係數同 wrap_sim.py),
     蓋子受 +tau、箱底受 −tau(作用力與反作用力)。
包材 / 杯子是靜態 Mesh(無碰撞),不參與物理。
"""
import argparse, os, sys, math
ap = argparse.ArgumentParser()
ap.add_argument("scene")
ap.add_argument("--out", default="phys")
ap.add_argument("--secs", type=float, default=6.0)
ap.add_argument("--no_crease", action="store_true", help="陰性對照:不加摺痕力矩")
ap.add_argument("--box", default="/World/Packed/Box")
ap.add_argument("--lid_nocollide", action="store_true",
                help="關掉蓋子與箱體(base)之間的碰撞(摺痕關節的 collisionEnabled=False)")
ap.add_argument("--open_deg", type=float, default=0.0,
                help="開箱檢查:四片蓋子先往外翻這麼多度(170 ≈ 翻到箱外略高於水平),"
                     "摺痕以這個姿態為靜止角撐住;鏡頭最後停在箱子正上方看箱內")
a = ap.parse_args()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
os.makedirs(a.out, exist_ok=True)

from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import numpy as np, torch, imageio
from PIL import Image, ImageDraw, ImageFont
import omni.usd
from isaacsim.core.api import World
from isaacsim.core.prims import RigidPrim, Articulation
from isaacsim.sensors.camera import Camera
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Gf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crease_physics import ElastoplasticCrease
LOG = open(os.path.join(a.out, "physics_check.log"), "w")
def P(*s):
    t = " ".join(str(x) for x in s); print(t, flush=True); LOG.write(t + "\n"); LOG.flush()

omni.usd.get_context().open_stage(os.path.abspath(a.scene))
for _ in range(10): sim.update()
st = omni.usd.get_context().get_stage()
if not any(p.IsA(UsdPhysics.Scene) for p in st.Traverse()):
    UsdPhysics.Scene.Define(st, "/physicsScene"); P("場景沒有 PhysicsScene → 加 /physicsScene")
world = World(physics_dt=1/120.0, rendering_dt=1/30.0, stage_units_in_meters=1.0)
FPS, SUB = 30, 4

# 預設燈太亮的話壓一點(只影響畫面)
for lp in st.Traverse():
    if "Light" in str(lp.GetTypeName()):
        P("  [light] %s %s intensity=%s" % (lp.GetPath(), lp.GetTypeName(), lp.GetAttribute("inputs:intensity").Get()))

FL = ["fxp", "fxn", "fyp", "fyn"]
BOX = a.box
bc = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
r = bc.ComputeWorldBound(st.GetPrimAtPath(BOX)).ComputeAlignedRange()
C = (r.GetMin() + r.GetMax()) / 2
TABLE_TOP = bc.ComputeWorldBound(st.GetPrimAtPath("/World/stationary_ai/tabletop_link")).ComputeAlignedRange().GetMax()[2]
P("紙箱 bbox 中心 (%.1f, %.1f, %.1f) mm;桌面 z=%.1f mm" % (C[0]*1e3, C[1]*1e3, C[2]*1e3, TABLE_TOP*1e3))

if a.open_deg:
    for n in ("fxp", "fxn", "fyp", "fyn"):
        xf = UsdGeom.Xformable(st.GetPrimAtPath(BOX + "/" + n))
        op = next(o for o in xf.GetOrderedXformOps() if o.GetOpName() == "xformOp:rotateX")
        op.Set(float(op.Get()) - a.open_deg)          # 蓋子往局部 -y 延伸:繞 X 轉負角 = 往上往外翻
if a.lid_nocollide:
    for n in ("fxp", "fxn", "fyp", "fyn"):
        UsdPhysics.Joint(st.GetPrimAtPath(BOX + "/crease_" + n)).GetCollisionEnabledAttr().Set(False)
    P("★ 蓋子與箱體之間不碰撞")
if a.open_deg:
    P("★ 開箱檢查:四片蓋往外翻 %.0f°(只改這次模擬的 stage,不存檔)" % a.open_deg)

cam = Camera(prim_path="/World/checkcam", resolution=(1280, 720), frequency=FPS)

world.reset()
ARMS = Articulation(prim_paths_expr="/World/stationary_ai", name="arms"); ARMS.initialize()
LIDS = RigidPrim(prim_paths_expr=BOX + "/f[xy][pn]", name="lids"); LIDS.initialize()
BASE = RigidPrim(prim_paths_expr=BOX + "/base", name="cbase"); BASE.initialize()
order = [str(p).rsplit("/", 1)[-1] for p in LIDS.prim_paths]
P("蓋子順序 %s;手臂 DOF %d" % (order, ARMS.num_dof))
cam.initialize()
from isaacsim.core.utils.viewports import set_camera_view
_cp = UsdGeom.Camera(st.GetPrimAtPath("/World/checkcam"))
_cp.GetFocalLengthAttr().Set(16.0); _cp.GetHorizontalApertureAttr().Set(20.955)
_cp.GetVerticalApertureAttr().Set(20.955*720/1280); _cp.GetClippingRangeAttr().Set(Gf.Vec2f(0.01, 100.0))

def qmul(a_, b_):
    w1, x1, y1, z1 = a_; w2, x2, y2, z2 = b_
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2,
                     w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])
def qconj(q): return np.array([q[0], -q[1], -q[2], -q[3]])
def qrot(q, v): return qmul(qmul(q, np.r_[0.0, v]), qconj(q))[1:]

p0L, q0L = [np.array(x, float) for x in LIDS.get_world_poses()]
p0B, q0B = [np.array(x, float)[0] for x in BASE.get_world_poses()]
REL0 = [qmul(qconj(q0B), q0L[i]) for i in range(len(order))]     # 蓋子相對箱底的初始姿態
J0 = np.array(ARMS.get_joint_positions(), float)[0]
CREASE = ElastoplasticCrease(len(order), "cpu", k=3.2, my0=0.60, h=0.85, c=0.33, clip=3.0)
CREASE.reset(torch.arange(len(order)), torch.zeros(len(order)))

def lid_state():
    pL, qL = [np.array(x, float) for x in LIDS.get_world_poses()]
    _, qB = [np.array(x, float)[0] for x in BASE.get_world_poses()]
    wL = np.array(LIDS.get_angular_velocities(), float); wB = np.array(BASE.get_angular_velocities(), float)[0]
    ang, rate, axes = [], [], []
    for i in range(len(order)):
        ax = qrot(qL[i], np.array([1.0, 0, 0]))              # 鉸鏈 = 蓋子本地 X 軸
        rr = qmul(qconj(REL0[i]), qmul(qconj(qB), qL[i]))     # 相對初始的轉動(箱底座標)
        if rr[0] < 0: rr = -rr                                # 同一個轉動,取 w>=0
        # rr 是蓋子「自己初始座標」裡的轉動;鉸鏈 = 本地 X ⇒ 帶號角度看 rr 的 x 分量
        # (不能投到箱底座標去比:fxp/fxn 轉了 ±90°、fyn 轉了 180°,符號會錯或變 0)
        th = 2*math.atan2(rr[1], rr[0])
        ang.append(th); rate.append(float(np.dot(wL[i] - wB, ax))); axes.append(ax)
    return np.array(ang), np.array(rate), axes

try: FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 18)
except Exception: FONT = ImageFont.load_default()

def cam_pose(t):
    # 0~60%:從手臂前方(-x)繞半圈到側邊;之後推近俯視箱子
    u = min(1.0, t / (0.6*a.secs))
    th = math.pi + math.radians(-60 + 120*u)
    R, Hc = 1.25, 0.70
    eye = np.array([C[0] + R*math.cos(th), C[1] + R*math.sin(th), Hc])
    if t > 0.6*a.secs:
        v = (t - 0.6*a.secs)/(0.4*a.secs); v = v*v*(3-2*v)
        end = (np.array([C[0] - 0.12, C[1] - 0.06, C[2] + 0.62]) if a.open_deg      # 正上方看箱內
               else np.array([C[0] - 0.35, C[1] - 0.25, C[2] + 0.40]))
        eye = eye + (end - eye)*v
    return eye

frames, rows = [], []
N = int(a.secs*FPS)
for k in range(N):
    t = k/FPS
    eye = cam_pose(t); set_camera_view(eye=eye, target=np.array(C), camera_prim_path="/World/checkcam")
    for s in range(SUB):
        if not a.no_crease:
            ang, rate, axes = lid_state()
            tq = CREASE.step(torch.tensor(ang, dtype=torch.float32), torch.tensor(rate, dtype=torch.float32)).numpy()
            tauL = np.stack([axes[i]*float(tq[i]) for i in range(len(order))])
            LIDS.apply_forces_and_torques_at_pos(torques=tauL, is_global=True)
            BASE.apply_forces_and_torques_at_pos(torques=-tauL.sum(0, keepdims=True), is_global=True)
        world.step(render=(s == SUB-1))
    ang, _, _ = lid_state()
    pB = np.array(BASE.get_world_poses()[0], float)[0]
    J = np.array(ARMS.get_joint_positions(), float)[0]
    dB = (pB - p0B)*1e3
    jd = np.degrees(np.abs(J - J0)).max()
    rows.append((t, *dB, *np.degrees(ang), jd))
    if k % FPS == 0 or k == N-1:
        P("t=%4.1f 箱底位移 (%+.2f, %+.2f, %+.2f) mm | 蓋角 %s deg | 手臂關節最大漂移 %.3f deg"
          % (t, *dB, " ".join("%s=%+.1f" % (n, d) for n, d in zip(order, np.degrees(ang))), jd))
    rgb = cam.get_rgba()
    if rgb is not None and rgb.size:
        im = Image.fromarray(np.asarray(rgb)[:, :, :3]); d = ImageDraw.Draw(im); W, Hh = im.size
        d.rectangle([0, Hh-62, W, Hh], fill=(16, 16, 18))
        d.text((10, Hh-58), "t=%.2fs  physics ON  crease %s%s  | box disp (%+.1f,%+.1f,%+.1f) mm"
               % (t, "OFF (negative control)" if a.no_crease else "ON",
                  "  lids opened %.0f°" % a.open_deg if a.open_deg else "", *dB), fill=(235,)*3, font=FONT)
        d.text((10, Hh-32), "lids " + "  ".join("%s %+.1f°" % (n, v) for n, v in zip(order, np.degrees(ang)))
               + "   | arm joint drift max %.2f°" % jd, fill=(170, 200, 230), font=FONT)
        frames.append(np.array(im))

# 最終:箱底底面 vs 桌面(用 base 的碰撞幾何 bbox)
bc2 = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
zmin = bc2.ComputeWorldBound(st.GetPrimAtPath(BOX + "/base")).ComputeAlignedRange().GetMin()[2]
R_ = np.array(rows)
P("\n===== 結論(%s)=====" % ("陰性對照:無摺痕" if a.no_crease else "有摺痕"))
P("箱底最終位移 (%+.2f, %+.2f, %+.2f) mm;全程 |位移| 最大 %.2f mm"
  % (*R_[-1, 1:4], np.abs(R_[:, 1:4]).max()))
P("箱底面 z=%.2f mm,桌面 z=%.2f mm ⇒ 差 %+.2f mm(負 = 穿桌)" % (zmin*1e3, TABLE_TOP*1e3, (zmin - TABLE_TOP)*1e3))
for i, n in enumerate(order):
    P("蓋 %s:最終 %+.1f°,全程最大 |角| %.1f°" % (n, R_[-1, 4+i], np.abs(R_[:, 4+i]).max()))
P("手臂關節最大漂移 %.3f°" % R_[:, -1].max())
np.save(os.path.join(a.out, "rows.npy"), R_)
if frames:
    iio = imageio.get_writer(os.path.join(a.out, "physics_check.mp4"), fps=FPS, codec="libx264", quality=8, pixelformat="yuv420p")
    for f in frames: iio.append_data(f)
    iio.close(); Image.fromarray(frames[-1]).save(os.path.join(a.out, "last.png"))
    P("→ %s(%d 幀)" % (os.path.join(a.out, "physics_check.mp4"), len(frames)))
sim.close()
