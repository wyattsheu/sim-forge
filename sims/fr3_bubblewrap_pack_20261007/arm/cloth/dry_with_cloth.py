#!/usr/bin/env python3
"""dry_with_cloth.py — load_cloth 的場景 + 回放 v2 軌跡 (b) 段(b1~b6;四蓋已 260°),不綁定。
    /isaac-sim/python.sh dry_with_cloth.py [--young 2e3] [--no_video]
軌跡 = arm/data/peel_traj_v2_pinch_fx1_g1_psi15_o260.npz(peel_traj_v2.py --lid_mode pinch --ajar 35 --lid_mid 50
       --open_deg 260 --psi 15 --yaw_extra 180 的輸出,30 fps),kinematic set_joint_positions;physics dt 1/240(每格 8 步)。
手臂只開右手兩指(gripper_left/right)的 collision,其他 follower collision 關(同 v2)。
量測(每 0.5 s + 每段末):指 OBB(collision 點 bbox,link 座標)對布頂點有號距離 → 最小距離 / 穿入深度;
  布頂點相對 b 開始時位移 > 10 mm 的數量;杯位移;另每格記錄全程最小值。抓取點 #1 = iface.json grasps[0](S 座標)。"""
import os, sys, json, math, argparse, functools, builtins
print = functools.partial(builtins.print, flush=True)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import load_cloth as LC
ap = argparse.ArgumentParser(); LC.add_args(ap)
ap.add_argument("--traj", default=os.path.join(LC.ROOT, "arm", "data", "peel_traj_v2_pinch_fx1_g1_psi15_o260"))
ap.add_argument("--settle", type=float, default=0.5)
ap.add_argument("--no_video", action="store_true")
a = ap.parse_args()
from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
import numpy as np, omni.usd
from pxr import Usd, UsdGeom, UsdPhysics, Gf
LOG = open(os.path.join(HERE, "logs", "dry_with_cloth.log"), "w")
def P(*s):
    t = " ".join(str(x) for x in s); print(t); LOG.write(t + "\n"); LOG.flush()
omni.usd.get_context().open_stage(LC.SCENE)
for _ in range(10): app.update()
st = omni.usd.get_context().get_stage()
C = LC.setup(st, a, P)
R0 = "/World/stationary_ai"
FING = ["%s/follower_right_gripper_left" % R0, "%s/follower_right_gripper_right" % R0]
xc = UsdGeom.XformCache(); Wm = lambda p: np.array(xc.GetLocalToWorldTransform(st.GetPrimAtPath(p))).T
OBB = {}
for b in FING:
    Wb = Wm(b); pts = []
    for p in Usd.PrimRange(st.GetPrimAtPath(b)):
        if p.IsA(UsdGeom.Mesh) and "/collisions/" in str(p.GetPath()):
            v = np.array(UsdGeom.Mesh(p).GetPointsAttr().Get(), float)
            M = np.linalg.inv(Wb) @ Wm(str(p.GetPath())); pts.append((M @ np.c_[v, np.ones(len(v))].T).T[:, :3])
    pts = np.vstack(pts); OBB[b] = (pts.min(0), pts.max(0))
    P("指 %s collision bbox(link 座標)%s mm" % (b.rsplit("/", 1)[1], np.round((pts.max(0) - pts.min(0)) * 1e3, 1).tolist()))
for p in Usd.PrimRange(st.GetPrimAtPath(R0)):
    if p.HasAPI(UsdPhysics.CollisionAPI) and "follower_" in str(p.GetPath()):
        keep = any(str(p.GetPath()).startswith(f + "/") for f in FING)
        UsdPhysics.CollisionAPI(p).CreateCollisionEnabledAttr().Set(bool(keep))
IF = json.load(open(os.path.join(LC.VOL, "soft", "s2", "iface.json")))
G1 = np.array(IF["grasps"][0]["pos"]["S"]) * 1e-3; V1 = IF["grasps"][0]["v"]
P("抓取點 #1 v%d S %s mm(iface.json, yaw %s)" % (V1, (G1 * 1e3).round(1).tolist(), IF["meta"]["yaw_deg"]))
Z = np.load(a.traj + ".npz"); J = json.load(open(a.traj + ".json")); FPS = int(Z["fps"])
segs = [s for s in J["segments"] if s["name"].startswith("b") and not s["name"].startswith("b0")]
f0 = int(round(segs[0]["t0"] * FPS)); f1 = len(Z["qR"])
P("回放 frame %d~%d(%.1f s)段:%s" % (f0, f1, (f1 - f0) / FPS, [s["name"].split()[0] for s in segs]))
G0, GK, MIM = J["gap"]["G0"], J["gap"]["GK"], J["gap"]["mimic"]

from isaacsim.core.api import World
from isaacsim.core.prims import Articulation, RigidPrim
world = World(physics_dt=a.dt, rendering_dt=1.0 / FPS, stage_units_in_meters=1.0)
pc_ = world.get_physics_context(); pc_.enable_gpu_dynamics(True); pc_.set_broadphase_type("GPU")
cams = []
if not a.no_video:
    from isaacsim.sensors.camera import Camera
    from isaacsim.core.utils.viewports import set_camera_view
    import imageio
    from PIL import Image, ImageDraw, ImageFont
    for i, (eye, tgt) in enumerate((((-0.55, -0.45, 0.50), (-0.03, -0.08, 0.13)), ((0.35, -0.30, 0.45), (-0.03, -0.05, 0.10)))):
        c = Camera(prim_path="/World/dc_cam%d" % i, resolution=(960, 540), frequency=FPS); cams.append((c, eye, tgt))
world.reset()
ART = Articulation(prim_paths_expr=R0, name="arms"); ART.initialize()
FR = RigidPrim(prim_paths_expr=FING, name="fing"); FR.initialize()
order = [str(p) for p in FR.prim_paths]
dof = list(ART.dof_names)
idx = {s: [dof.index("follower_%s_joint_%d" % (s, k)) for k in range(6)] for s in ("left", "right")}
cidx = {s: (dof.index("follower_%s_left_carriage_joint" % s), dof.index("follower_%s_right_carriage_joint" % s)) for s in ("left", "right")}
for c, eye, tgt in cams:
    c.initialize(); set_camera_view(eye=np.array(eye), target=np.array(tgt), camera_prim_path=c.prim_path)
    cp = UsdGeom.Camera(st.GetPrimAtPath(c.prim_path)); cp.GetFocalLengthAttr().Set(18.0)
    cp.GetHorizontalApertureAttr().Set(20.955); cp.GetVerticalApertureAttr().Set(20.955 * 540 / 960); cp.GetClippingRangeAttr().Set(Gf.Vec2f(0.01, 100.0))
def apply(f):
    Jq = np.array(ART.get_joint_positions(), float)[0]
    Jq[idx["left"]] = Z["qL"][f]; Jq[idx["right"]] = Z["qR"][f]
    for s, g in (("left", Z["gL"][f]), ("right", Z["gR"][f])):
        Jq[cidx[s][0]] = g; Jq[cidx[s][1]] = MIM * g
    ART.set_joint_positions(Jq[None]); ART.set_joint_position_targets(Jq[None]); ART.set_joint_velocities(np.zeros_like(Jq)[None])
def qmat(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
def finger_sd(Pc):
    pos, qs = [np.array(v, float) for v in FR.get_world_poses()]; best = np.full(len(Pc), 9.9)
    for j, b in enumerate(order):
        R = qmat(qs[j]); lo, hi = OBB[b]; c = (lo + hi) / 2; h = (hi - lo) / 2
        l = (Pc - pos[j]) @ R - c; d = np.abs(l) - h
        sd = np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(d.max(1), 0); best = np.minimum(best, sd)
    return best
apply(f0)
for _ in range(int(round(a.settle * FPS))): world.step(render=bool(cams))
from pxr import Vt
import trimesh as _tr
_T = C["TETS"]; _F = np.vstack([_T[:, [0, 2, 1]], _T[:, [0, 1, 3]], _T[:, [1, 2, 3]], _T[:, [0, 3, 2]]])
_k = np.sort(_F, 1); _u, _inv, _c = np.unique(_k, axis=0, return_inverse=True, return_counts=True); SF = _F[_c[_inv.ravel()] == 1]
VIS = UsdGeom.Mesh.Define(st, "/World/cloth_vis"); VIS.CreateFaceVertexIndicesAttr([int(i) for i in SF.ravel()]); VIS.CreateFaceVertexCountsAttr([3] * len(SF))
VIS.CreateDoubleSidedAttr(True); VIS.CreateDisplayColorAttr([Gf.Vec3f(0.2, 0.7, 0.95)])
def upd_vis(Pc): VIS.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in Pc]))
upd_vis(C["PLATE"].pts()); P("cloth_vis 表面三角形 %d" % len(SF))
Pb = C["PLATE"].pts(); MUGP = UsdGeom.Mesh(st.GetPrimAtPath("/World/cloth_mug/geo"))
r = C["measure"](Pb); P("settle %.1fs 後:位移(對 rest)%.2f mm 反轉 %d 互穿 %d 穿杯 %d" % (a.settle, r["disp"], r["inv"], r["pen"], r["inmug"]))
wr = None
if cams:
    try: FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 17)
    except Exception: FONT = None
    wr = imageio.get_writer(os.path.join(HERE, "videos", "dry_with_cloth.mp4"), fps=FPS, codec="libx264", quality=8, pixelformat="yuv420p")
mug_c0 = None
from isaacsim.core.prims import SingleXFormPrim
MX = SingleXFormPrim("/World/cloth_mug", name="mugx"); mug_p0 = np.array(MX.get_world_pose()[0])
rows = []; segacc = {}
def segname(f):
    t = f / FPS
    for s in segs:
        if s["t0"] - 1e-6 <= t < s["t1"] - 1e-6: return s["name"].split()[0]
    return segs[-1]["name"].split()[0]
maxjerr = 0.0
for f in range(f0, f1):
    apply(f); world.step(render=bool(cams))
    Pc = C["PLATE"].pts(); upd_vis(Pc); sd = finger_sd(Pc); sn = segname(f)
    moved = np.linalg.norm(Pc - Pb, axis=1); mugd = np.linalg.norm(np.array(MX.get_world_pose()[0]) - mug_p0) * 1e3
    gap = G0 + GK * Z["gR"][f]
    A = segacc.setdefault(sn, dict(dmin=9e9, pen=0.0, moved=0, mug=0.0, v1d=9e9))
    A["dmin"] = min(A["dmin"], sd.min() * 1e3); A["pen"] = max(A["pen"], -sd.min() * 1e3); A["moved"] = max(A["moved"], int((moved > 0.010).sum()))
    A["mug"] = max(A["mug"], mugd); A["v1d"] = min(A["v1d"], sd[V1] * 1e3)
    A["v1move"] = float(moved[V1] * 1e3); A["finite"] = bool(np.isfinite(Pc).all())
    k = f - f0
    if k % (FPS // 2) == 0 or f == f1 - 1:
        rows.append(dict(t=round(f / FPS, 2), seg=sn, dmin=float(sd.min() * 1e3), npen=int((sd < 0).sum()), moved=int((moved > 0.010).sum()),
                         mmax=float(moved.max() * 1e3), mug=float(mugd), v1d=float(sd[V1] * 1e3)))
        P("t=%5.2f %-3s 指布最小有號距離 %7.2f mm(穿入頂點 %d)| 被推 >10mm %4d 頂點(max %.1f)| #1 頂點離指 %.1f mm | 杯位移 %.2f mm | gap %.1f"
          % (rows[-1]["t"], sn, rows[-1]["dmin"], rows[-1]["npen"], rows[-1]["moved"], rows[-1]["mmax"], rows[-1]["v1d"], mugd, gap))
    if wr:
        ims = []
        for c, _e, _t in cams:
            rgb = c.get_rgba(); ims.append(np.asarray(rgb)[:, :, :3] if rgb is not None and rgb.size else np.zeros((540, 960, 3), np.uint8))
        im = Image.fromarray(np.concatenate(ims, 1)); dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, 900, 44], fill=(0, 0, 0))
        dr.text((6, 3), "t=%5.2fs %s  finger-cloth min %.1f mm  pushed>10mm %d  gripR %.1f mm" % (f / FPS, sn, sd.min() * 1e3, int((moved > 0.010).sum()), gap), fill=(255, 255, 255), font=FONT)
        wr.append_data(np.asarray(im))
if wr: wr.close()
P("\n=== 各段總結(全格)")
for s in segs:
    n = s["name"].split()[0]; A = segacc.get(n)
    if A: P("  %-3s %-28s 指布最小 %.2f mm | 穿入 %.2f mm | 被推頂點 %d | 杯 %.2f mm | #1 最近 %.1f mm,#1 位移 %.1f mm | finite %s"
            % (n, s["name"][3:], A["dmin"], max(0, A["pen"]), A["moved"], A["mug"], A["v1d"], A["v1move"], A["finite"]))
r = C["measure"](C["PLATE"].pts()); P("結束:對 rest 位移 %.1f mm 反轉 %d 互穿 %d 穿杯 %d" % (r["disp"], r["inv"], r["pen"], r["inmug"]))
json.dump(dict(rows=rows, seg=segacc, end=r), open(os.path.join(HERE, "logs", "dry_with_cloth.json"), "w"), indent=1)
app.close()
