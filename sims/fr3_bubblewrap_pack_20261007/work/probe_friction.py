#!/usr/bin/env python3
"""probe_friction.py — 布對 kinematic 平板的摩擦有沒有作用?(骨架照 probe_detach.py)

    /isaac-sim/python.sh probe_friction.py --var a

背景:wrap_sim.py --movebox 實測,箱子沿 x 搬 300mm,布相對箱子滑 35mm、被後牆推著走;
  改 PhysX kinematic target、或放慢到 12s 都一樣 ⇒ 不是移動方式、也不是加速度。
場景:10x10 surface deformable 布(材料照 wrap_sim 定版那組:E 2e4 / thick 4mm / bend 4 / fric 0.8 / sleepy 參數),
  平放在一塊 kinematic 平板上(平板材質照紙箱 /Box/cardMat:UsdPhysics.MaterialAPI static 0.5 / dynamic 0.45,
  physics purpose 綁定)。板上另放一個 dynamic 5cm 方塊當剛體對照(每個變體都有)。
  板子沿 x 以 smoothstep 走 300mm/6s(靜置 2s、搬 6s、再 2s),每步 set_world_pose(= movebox xform 模式)。
var:
  a 原樣
  b 板子材質 static/dynamic 1.0
  c 布材質 omniphysics:dynamicFriction 2.0
  d 板子改綁新材質:UsdPhysics.MaterialAPI + PhysxMaterialAPI,friction 0.8(不沿用 cardMat 的寫法)
  f 原樣但布**不加** sleepy 三參數(settlingDamping 10 / settlingThreshold 0.10 / sleepThreshold 0.05)
  g 像紙箱:板厚 3mm **直接貼地**(頂面 z=3mm,同 carton 底板),布上壓一個 80g dynamic 方塊(= 杯子重量)
    —— 驗「布被壓穿底板、碰到地板,地板摩擦把布留住」
判準(跑之前寫死):搬完後 布質心相對板子的 x 位移 |dx| < 5mm ⇒ 帶得動。方塊同理。
"""
import os, argparse
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--var", required=True, choices=list("abcdfg"))
ap.add_argument("--move", type=float, default=0.30)
ap.add_argument("--move_t", type=float, default=6.0)
ap.add_argument("--wait", type=float, default=2.0)
ap.add_argument("--after", type=float, default=2.0)
a = ap.parse_args()

os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from isaacsim.core.prims import SingleXFormPrim
from pxr import Gf, Sdf, UsdGeom, UsdPhysics, UsdShade, PhysxSchema, Vt
from omni.physx.scripts import deformableUtils
import omni.usd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_fric_%s.log" % a.var)
LOG = open(OUT, "w")
def P(*s):
    m = " ".join(str(x) for x in s); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()

def sa(prim, n, v, tn=None):
    at = prim.GetAttribute(n)
    if not at or not at.IsValid():
        if tn is None:
            return None
        at = prim.CreateAttribute(n, tn)
    at.Set(v)
    return at

DT = 1/120.0
world = World(physics_dt=DT, rendering_dt=1/30.0)
world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

# ---- 平板:kinematic,頂面 z=0.05(離地,避免地板參與)----
PT, PZ = (0.003, 0.0015) if a.var == "g" else (0.02, 0.04)
plate = UsdGeom.Cube.Define(st, "/World/plate"); plate.CreateSizeAttr(1.0)
_x = UsdGeom.Xformable(plate)
_x.AddTranslateOp().Set(Gf.Vec3d(0, 0, PZ)); _x.AddScaleOp().Set(Gf.Vec3f(0.60, 0.60, PT))
UsdPhysics.CollisionAPI.Apply(plate.GetPrim())
UsdPhysics.RigidBodyAPI.Apply(plate.GetPrim()).CreateKinematicEnabledAttr(True)
TOP = PZ + PT/2

pm = UsdShade.Material.Define(st, "/World/plateMat")
mapi = UsdPhysics.MaterialAPI.Apply(pm.GetPrim())
if a.var == "b":
    mapi.CreateStaticFrictionAttr(1.0); mapi.CreateDynamicFrictionAttr(1.0)
elif a.var == "d":
    mapi.CreateStaticFrictionAttr(0.8); mapi.CreateDynamicFrictionAttr(0.8)
    px = PhysxSchema.PhysxMaterialAPI.Apply(pm.GetPrim())
    px.CreateFrictionCombineModeAttr("average")
else:   # 照 /Box/cardMat
    mapi.CreateStaticFrictionAttr(0.5); mapi.CreateDynamicFrictionAttr(0.45)
mapi.CreateRestitutionAttr(0.0); mapi.CreateDensityAttr(0.0)
UsdShade.MaterialBindingAPI.Apply(plate.GetPrim()).Bind(pm, UsdShade.Tokens.weakerThanDescendants, "physics")

# ---- 剛體對照方塊 ----
CS = 0.05
cube = UsdGeom.Cube.Define(st, "/World/cube"); cube.CreateSizeAttr(CS)
UsdGeom.Xformable(cube).AddTranslateOp().Set(Gf.Vec3d(0, 0.18, TOP + CS/2 + 0.001))
UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
UsdPhysics.RigidBodyAPI.Apply(cube.GetPrim())
UsdPhysics.MassAPI.Apply(cube.GetPrim()).CreateMassAttr(0.1)
WT = None
if a.var == "g":   # 杯子重量壓在布中央
    WT = UsdGeom.Cube.Define(st, "/World/weight"); WT.CreateSizeAttr(0.05)
    UsdGeom.Xformable(WT).AddTranslateOp().Set(Gf.Vec3d(0, -0.12, TOP + 0.004 + 0.025 + 0.003))
    UsdPhysics.CollisionAPI.Apply(WT.GetPrim()); UsdPhysics.RigidBodyAPI.Apply(WT.GetPrim())
    UsdPhysics.MassAPI.Apply(WT.GetPrim()).CreateMassAttr(0.0807)

# ---- 布:10x10,材料照 wrap_sim 定版那組 ----
YOUNGS, POISSON, THICK, BEND = 2.0e4, 0.45, 0.004, 4.0
FRIC = 2.0 if a.var == "c" else 0.8
DENS = 100.0
LDAMP, EDAMP, BDAMP = 0.20, 0.30, 0.30
CONT, REST = 0.005, 0.001
W, N, Y0 = 0.20, 10, -0.12
Z0 = TOP + THICK/2 + 0.001
verts = [Gf.Vec3f(-W/2 + i*W/N, Y0 - W/2 + j*W/N, Z0) for j in range(N+1) for i in range(N+1)]
tris = []
for j in range(N):
    for i in range(N):
        A0 = j*(N+1)+i
        tris += [(A0, A0+1, A0+N+2), (A0, A0+N+2, A0+N+1)]
sh = UsdGeom.Mesh.Define(st, "/World/sheet")
sh.GetPointsAttr().Set(Vt.Vec3fArray(verts))
sh.GetFaceVertexCountsAttr().Set([3]*len(tris))
sh.GetFaceVertexIndicesAttr().Set([k for t in tris for k in t])
sh.CreateDoubleSidedAttr(True)
sp = sh.GetPrim()
phm = UsdShade.Material.Define(st, "/World/sheetPhys"); pp = phm.GetPrim()
pp.ApplyAPI("OmniPhysicsBaseMaterialAPI")
sa(pp, "omniphysics:dynamicFriction", FRIC); sa(pp, "omniphysics:density", DENS)
pp.ApplyAPI("OmniPhysicsDeformableMaterialAPI")
sa(pp, "omniphysics:youngsModulus", YOUNGS); sa(pp, "omniphysics:poissonsRatio", POISSON)
pp.ApplyAPI("OmniPhysicsSurfaceDeformableMaterialAPI")
sa(pp, "omniphysics:surfaceThickness", THICK); sa(pp, "omniphysics:surfaceBendStiffness", BEND)
pp.ApplyAPI("PhysxSurfaceDeformableMaterialAPI")
sa(pp, "physxDeformableMaterial:elasticityDamping", EDAMP)
sa(pp, "physxDeformableMaterial:bendDamping", BDAMP)
ok = deformableUtils.set_physics_surface_deformable_body(st, sp.GetPath())
sp.ApplyAPI("PhysxSurfaceDeformableBodyAPI")
sa(sp, "physxDeformableBody:selfCollision", True)
sa(sp, "omniphysics:restBendAnglesDefault", "flatDefault", Sdf.ValueTypeNames.Token)
SLEEPY = a.var != "f"
if SLEEPY:   # 照 wrap_sim.py 預設(--sleepy default True)
    sa(sp, "physxDeformableBody:settlingDamping", 10.0, Sdf.ValueTypeNames.Float)
    sa(sp, "physxDeformableBody:settlingThreshold", 0.10, Sdf.ValueTypeNames.Float)
    sa(sp, "physxDeformableBody:sleepThreshold", 0.05, Sdf.ValueTypeNames.Float)
sa(sp, "physxDeformableBody:solverPositionIterationCount", 64, Sdf.ValueTypeNames.Int)
sa(sp, "physxDeformableBody:linearDamping", LDAMP, Sdf.ValueTypeNames.Float)
pc = PhysxSchema.PhysxCollisionAPI.Apply(sp)
pc.CreateRestOffsetAttr().Set(REST); pc.CreateContactOffsetAttr().Set(CONT)
UsdShade.MaterialBindingAPI.Apply(sp).Bind(phm, UsdShade.Tokens.weakerThanDescendants, "physics")
P("var=%s | set_physics_surface_deformable_body -> %s | 布 fric %.2f | sleepy %s | 板材質 %s"
  % (a.var, ok, FRIC, SLEEPY, {"b": "UsdPhysics 1.0/1.0", "d": "UsdPhysics+PhysxMaterialAPI 0.8"}.get(a.var, "cardMat 0.5/0.45")))

world.reset()
plx = SingleXFormPrim("/World/plate", name="platex")
cbx = SingleXFormPrim("/World/cube", name="cubex")
pp0, pq0 = plx.get_world_pose(); pp0 = np.array(pp0, float); pq0 = np.array(pq0, float)
pts = UsdGeom.Mesh(sp).GetPointsAttr()
ss = lambda u: (lambda v: v*v*(3-2*v))(min(max(u, 0.), 1.))
MV = np.array([a.move, 0.0, 0.0])
T_END = a.wait + a.move_t + a.after
NSTEP = int(round(T_END/DT))
REL0 = None
for s in range(NSTEP + 1):
    t = s*DT
    plx.set_world_pose(position=pp0 + MV*ss((t - a.wait)/a.move_t), orientation=pq0)
    world.step(render=False)
    if s % int(round(0.5/DT)) == 0 or s == NSTEP:
        S = np.array(pts.Get()); pc_ = np.array(plx.get_world_pose()[0], float); cc = np.array(cbx.get_world_pose()[0], float)
        rel = S.mean(0) - pc_; crel = cc - pc_
        if REL0 is None and t >= a.wait - 1e-9:
            REL0 = (rel.copy(), crel.copy())
        P("t=%5.2f 板 x %6.1f | 布質心−板 (%+6.1f,%+6.1f) 布最低−板頂 %+5.1f mm | 方塊−板 (%+6.1f,%+6.1f) 方塊底−板頂 %+5.1f mm"
          % (t, (pc_[0]-pp0[0])*1e3, *(rel[:2]*1e3), (S[:, 2].min() - (pc_[2] + PT/2))*1e3,
             *(crel[:2]*1e3), (cc[2] - CS/2 - (pc_[2] + PT/2))*1e3))
if a.var == "g":
    S = np.array(pts.Get())
    P("var g:布頂點 z<%.1fmm(板頂以下)%d 個、z<0.5mm(碰地)%d 個;布最低 z=%.2f mm"
      % (TOP*1e3, int((S[:, 2] < TOP).sum()), int((S[:, 2] < 0.0005).sum()), S[:, 2].min()*1e3))
d_s = (rel - REL0[0])*1e3; d_c = (crel - REL0[1])*1e3
P("\n===== 判讀 var=%s =====" % a.var)
P("板子實際走了 %.1f mm" % ((pc_[0]-pp0[0])*1e3))
P("布質心相對板子位移 dx=%+.1f dy=%+.1f mm ⇒ %s" % (d_s[0], d_s[1], "帶得動" if abs(d_s[0]) < 5 else "帶不動"))
P("方塊相對板子位移   dx=%+.1f dy=%+.1f mm ⇒ %s" % (d_c[0], d_c[1], "帶得動" if abs(d_c[0]) < 5 else "帶不動"))
LOG.close()
sim.close()
