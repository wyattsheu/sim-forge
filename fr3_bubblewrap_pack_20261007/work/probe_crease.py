#!/usr/bin/env python3
"""probe_crease.py — surface deformable 的「靜止彎曲角」能不能在模擬中改成**當下的折疊狀態**(摺痕定型/塑性)?

    /isaac-sim/python.sh probe_crease.py --mode N [--fold_deg 90] [--sign 1] [--bend0 0]

場景:10×10 surface deformable 布(材料照 wrap_sim 預設),沿 x=-0.06 這條格線(i=3)把左側 3 格寬的
  邊條(flap)折起來:兩個角(頂點 0 與 110)各用一個 kinematic 方塊 + OmniPhysicsVtxXformAttachment(結構照 wrap_sim)
  沿圓弧繞摺線轉 fold_deg(0~1.5s),停 1s 讓它靜下來,t=2.5s 放手(stage.RemovePrim 兩個 attachment Scope,
  probe_detach.py 已驗證可行),之後每 0.1s 印角的 x/z 與摺線的實測二面角。
  ★ 用整條邊(兩個角)而不是單一角:摺線落在格線上、二面角每條邊都有定義、不扭,和 wrap_sim 折整邊一樣。

schema(OmniUsdPhysicsDeformableSchema/resources/schema.usda 405~442):
  uniform token omniphysics:restBendAnglesDefault  allowedTokens = ["flatDefault", "restShapeDefault"]
      restShapeDefault = 用 restShapePoints 這組點算相鄰三角形法線夾角當靜止角
  int2[]  omniphysics:restAdjTriPairs   逐「相鄰三角形對」明確給靜止角(覆蓋 default)
  float[] omniphysics:restBendAngles    度,[-180, 180),長度 = restAdjTriPairs

mode(放手那一步做的事):
  0  對照:什麼都不改(flatDefault)→ 應該彈回平
  1  restShapePoints := 當下(折好)的頂點 + restBendAnglesDefault := restShapeDefault
  6  只改 token restBendAnglesDefault := restShapeDefault(restShapePoints 仍是平的)
  2  restAdjTriPairs := 全部內部相鄰三角形對、restBendAngles := 由當下頂點算出的二面角 × --sign
  3  材質 omniphysics:surfaceBendStiffness := --bend0(runtime 改材質,不改靜止角;建議搭 --fold_deg 120 看它倒向哪邊)
  4  校正/載入期測試:**不用錨點**,建立時就寫 restAdjTriPairs/restBendAngles = 解析算出的「flap 折 fold_deg」二面角 × --sign,
     看平放的布會不會自己把 flap 折起來(角的 z → 0.09)。這同時決定 PhysX 的正負號慣例。
  7  = mode 2 之後再 physx.release_physics_objects() + force_load_physics_from_usd()(強迫重新載入,兩段合一段)
  5  = mode 1 之後再 release_physics_objects() + force_load_physics_from_usd()

判準:放手後 1s 角 0 的 z。折 90° 時折好 z≈0.095;彈回平 z≈0.005~0.01。> 0.06 算「定型」,< 0.03 算「回彈」。
  同時印摺線二面角(度,自己的慣例 × sign):定型 ≈ fold_deg,回彈 → 0。
"""
import os, sys, argparse, time
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--mode", type=int, required=True)
ap.add_argument("--fold_deg", type=float, default=90.0)
ap.add_argument("--sign", type=float, default=1.0, help="二面角正負號慣例(用 mode 4 校正)")
ap.add_argument("--bend0", type=float, default=0.0, help="mode 3:放手時 surfaceBendStiffness 改成多少")
ap.add_argument("--keep_anchor", action="store_true",
                help="放手時只拆角 0 的 attachment,角 110 的錨點留著並在放手後再升 5cm(看重載/放手後其他錨點還能不能用)")
ap.add_argument("--t_fold", type=float, default=1.5)
ap.add_argument("--t_rel", type=float, default=2.5)
ap.add_argument("--t_end", type=float, default=4.0)
ap.add_argument("--solver", type=int, default=64)
a = ap.parse_args()

os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from isaacsim.core.prims import SingleXFormPrim
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, PhysxSchema, Vt
from omni.physx.scripts import deformableUtils
import omni.usd, omni.physx
P = lambda *s: print(*s, flush=True)


def sa(prim, n, v, tn=None):
    at = prim.GetAttribute(n)
    if not at or not at.IsValid():
        if tn is None:
            return None
        at = prim.CreateAttribute(n, tn)
    at.Set(v)
    return at


def ss(u):
    u = min(1.0, max(0.0, u))
    return u*u*(3 - 2*u)


# ---- 世界 ----
DT = 1/120.0
world = World(physics_dt=DT, rendering_dt=1/30.0)
world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

# ---- 布 ----
YOUNGS, POISSON, THICK, BEND = 5.0e4, 0.45, 0.010, 2.0e3
FRIC, DENS = 0.8, 100.0
LDAMP, EDAMP, BDAMP = 0.20, 0.30, 0.30
CONT, REST = 0.005, 0.001
W, N, Z0 = 0.30, 10, 0.005
IC = 3                                  # 摺線在第 IC 條格線 x = -W/2 + IC*W/N
XC = -W/2 + IC*W/N
verts = [Gf.Vec3f(-W/2 + i*W/N, -W/2 + j*W/N, Z0) for j in range(N+1) for i in range(N+1)]
tris = []
for j in range(N):
    for i in range(N):
        A0 = j*(N+1)+i
        tris += [(A0, A0+1, A0+N+2), (A0, A0+N+2, A0+N+1)]
TRIS = np.array(tris, dtype=int)
P0 = np.array([[p[0], p[1], p[2]] for p in verts], dtype=float)
IDX_I = np.array([k % (N+1) for k in range(len(verts))])
FLAP = np.where(IDX_I < IC)[0]          # 會被折起來的頂點(不含摺線上的)

# 相鄰三角形對(內部邊):共用邊的方向取「在 ta 的繞行順序中 p→q」
edge_map = {}
for t_idx, (v0, v1, v2) in enumerate(tris):
    for p, q in ((v0, v1), (v1, v2), (v2, v0)):
        edge_map.setdefault((min(p, q), max(p, q)), []).append((t_idx, p, q))
PAIRS = []                              # (ta, tb, p, q)
for e, lst in edge_map.items():
    if len(lst) == 2:
        (ta, pa, qa), (tb, pb, qb) = sorted(lst)
        PAIRS.append((ta, tb, pa, qa))
PAIRS = np.array(PAIRS, dtype=int)
CREASE = np.array([n for n, (ta, tb, p, q) in enumerate(PAIRS) if IDX_I[p] == IC and IDX_I[q] == IC])
P("內部相鄰三角形對 %d 組,其中落在摺線 x=%.2f 上的 %d 組" % (len(PAIRS), XC, len(CREASE)))


def dihedrals(Pt):
    """每一對相鄰三角形的帶號二面角(度):atan2(dot(cross(nA,nB), e), dot(nA,nB)),e = ta 中 p→q。平的 = 0。"""
    A = Pt[TRIS[:, 0]]; B = Pt[TRIS[:, 1]]; C = Pt[TRIS[:, 2]]
    nrm = np.cross(B - A, C - A); nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    nA = nrm[PAIRS[:, 0]]; nB = nrm[PAIRS[:, 1]]
    e = Pt[PAIRS[:, 3]] - Pt[PAIRS[:, 2]]; e /= np.linalg.norm(e, axis=1)[:, None]
    return np.degrees(np.arctan2(np.einsum("ij,ij->i", np.cross(nA, nB), e), np.einsum("ij,ij->i", nA, nB)))


def folded_points(deg):
    """解析:flap 繞摺線(x=XC, z=Z0,軸 +y)向上轉 deg 度後的頂點位置。"""
    Q = P0.copy()
    th = np.radians(deg)
    r = XC - P0[FLAP, 0]
    Q[FLAP, 0] = XC - r*np.cos(th)
    Q[FLAP, 2] = Z0 + r*np.sin(th)
    return Q


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
sa(pp, "omniphysics:surfaceThickness", THICK); at_bend = sa(pp, "omniphysics:surfaceBendStiffness", BEND)
pp.ApplyAPI("PhysxSurfaceDeformableMaterialAPI")
sa(pp, "physxDeformableMaterial:elasticityDamping", EDAMP)
sa(pp, "physxDeformableMaterial:bendDamping", BDAMP)
ok = deformableUtils.set_physics_surface_deformable_body(st, sp.GetPath())
P("set_physics_surface_deformable_body ->", ok)
sp.ApplyAPI("PhysxSurfaceDeformableBodyAPI")
sa(sp, "physxDeformableBody:selfCollision", False)
at_tok = sa(sp, "omniphysics:restBendAnglesDefault", "flatDefault", Sdf.ValueTypeNames.Token)
sa(sp, "physxDeformableBody:solverPositionIterationCount", a.solver, Sdf.ValueTypeNames.Int)
sa(sp, "physxDeformableBody:linearDamping", LDAMP, Sdf.ValueTypeNames.Float)
pc = PhysxSchema.PhysxCollisionAPI.Apply(sp)
pc.CreateRestOffsetAttr().Set(REST); pc.CreateContactOffsetAttr().Set(CONT)
UsdShade.MaterialBindingAPI.Apply(sp).Bind(phm, UsdShade.Tokens.weakerThanDescendants, "physics")
P("schema 檢查:restBendAnglesDefault=%s | 有 restAdjTriPairs 屬性? %s | 有 restBendAngles 屬性? %s | 有 restShapePoints? %s(%d 點)"
  % (at_tok.Get(), bool(sp.GetAttribute("omniphysics:restAdjTriPairs")), bool(sp.GetAttribute("omniphysics:restBendAngles")),
     bool(sp.GetAttribute("omniphysics:restShapePoints")), len(sp.GetAttribute("omniphysics:restShapePoints").Get() or [])))


def write_rest_arrays(angles_deg, which=None):
    """把 restAdjTriPairs / restBendAngles 寫進 sim mesh。which=None 全部寫,否則只寫那些 pair。"""
    sel = np.arange(len(PAIRS)) if which is None else np.asarray(which)
    pairs = Vt.Vec2iArray([Gf.Vec2i(int(PAIRS[n, 0]), int(PAIRS[n, 1])) for n in sel])
    angs = Vt.FloatArray([float(angles_deg[n]) for n in sel])
    sa(sp, "omniphysics:restAdjTriPairs", pairs, Sdf.ValueTypeNames.Int2Array)
    sa(sp, "omniphysics:restBendAngles", angs, Sdf.ValueTypeNames.FloatArray)
    return len(sel)


NOANCHOR = a.mode in (4, 8)
if a.mode == 4:
    Q = folded_points(a.fold_deg)
    ang = dihedrals(Q) * a.sign
    n_w = write_rest_arrays(ang)
    P("mode 4:建立時寫入 %d 對靜止角(摺線上 %d 對 = %.1f°,其餘 |角| max %.2f°),不建錨點,看布自己會不會折起來"
      % (n_w, len(CREASE), ang[CREASE].mean(), np.abs(np.delete(ang, CREASE)).max()))
if a.mode == 8:
    Q = folded_points(a.fold_deg)
    sa(sp, "omniphysics:restShapePoints", Vt.Vec3fArray([Gf.Vec3f(*[float(x) for x in p]) for p in Q]))
    at_tok.Set("restShapeDefault")
    P("mode 8:建立時 restShapePoints := 解析折好的點(flap %.0f°)+ restBendAnglesDefault := restShapeDefault,不建錨點" % a.fold_deg)

# ---- 錨點(兩個角:頂點 0 與 110),結構照 wrap_sim ----
ANC = []
if not NOANCHOR:
    UsdGeom.Xform.Define(st, "/World/anchors")
    for k, vi in enumerate([0, N*(N+1)]):
        ap_ = "/World/anchors/a%03d" % k
        cb = UsdGeom.Cube.Define(st, ap_); cb.CreateSizeAttr(0.006)
        UsdGeom.Xformable(cb).AddTranslateOp().Set(Gf.Vec3d(*P0[vi]))
        UsdPhysics.CollisionAPI.Apply(cb.GetPrim())
        UsdPhysics.RigidBodyAPI.Apply(cb.GetPrim()).CreateKinematicEnabledAttr(True)
        UsdGeom.Imageable(cb.GetPrim()).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
        scp = "/World/attach/a%03d" % k
        sc = st.DefinePrim(scp, "Scope")
        sc.ApplyAPI("PhysxAutoDeformableAttachmentAPI")
        for k2, v2 in [("enableDeformableVertexAttachments", True), ("enableRigidSurfaceAttachments", False),
                       ("enableCollisionFiltering", True), ("enableDeformableFilteringPairs", False)]:
            sa(sc, "physxAutoDeformableAttachment:" + k2, v2, Sdf.ValueTypeNames.Bool)
        sa(sc, "physxAutoDeformableAttachment:deformableVertexOverlapOffset", 0.008, Sdf.ValueTypeNames.Float)
        sa(sc, "physxAutoDeformableAttachment:collisionFilteringOffset", 0.030, Sdf.ValueTypeNames.Float)
        for rn, tg in [("attachable0", "/World/sheet"), ("attachable1", ap_)]:
            (sc.GetRelationship("physxAutoDeformableAttachment:" + rn) or
             sc.CreateRelationship("physxAutoDeformableAttachment:" + rn)).SetTargets([Sdf.Path(tg)])
        ch = st.DefinePrim(scp + "/vtx_xform_attachment", "OmniPhysicsVtxXformAttachment")
        sa(ch, "omniphysics:attachmentEnabled", True, Sdf.ValueTypeNames.Bool)
        sa(ch, "omniphysics:damping", 0.0, Sdf.ValueTypeNames.Float)
        sa(ch, "omniphysics:stiffness", float("inf"), Sdf.ValueTypeNames.Float)
        sa(ch, "omniphysics:vtxIndicesSrc0", Vt.IntArray([int(vi)]), Sdf.ValueTypeNames.IntArray)
        sa(ch, "omniphysics:localPositionsSrc1", Vt.Vec3fArray([Gf.Vec3f(0, 0, 0)]), Sdf.ValueTypeNames.Point3fArray)
        for rn, tg in [("src0", "/World/sheet"), ("src1", ap_)]:
            (ch.GetRelationship("omniphysics:" + rn) or
             ch.CreateRelationship("omniphysics:" + rn)).SetTargets([Sdf.Path(tg)])
        ANC.append(dict(k=k, vi=vi, path=ap_, scope=scp))

world.reset()
for q in ANC:
    q["prim"] = SingleXFormPrim(q["path"], name="anc%d" % q["k"])
pts = UsdGeom.Mesh(sp).GetPointsAttr()
V0 = 0                                   # 觀察的角:頂點 0
V1 = N*(N+1)


def anchor_pos(vi, t):
    th = np.radians(a.fold_deg * ss(min(t, a.t_rel) / a.t_fold))
    r = XC - P0[vi, 0]
    dz = 0.05 * min(1.0, max(0.0, (t - a.t_rel) / 1.0)) if a.keep_anchor else 0.0   # 留下的錨點放手後再升 5cm
    return np.array([XC - r*np.cos(th), P0[vi, 1], Z0 + r*np.sin(th) + dz])


def do_mode(cur):
    """放手那一步先做的動作(cur = 當下頂點)。回傳說明。"""
    m = a.mode
    if m == 0:
        return "對照:不改"
    if m in (1, 5):
        sa(sp, "omniphysics:restShapePoints", Vt.Vec3fArray([Gf.Vec3f(*[float(x) for x in p]) for p in cur]))
        at_tok.Set("restShapeDefault")
        return "restShapePoints := 當下頂點(%d 點)+ restBendAnglesDefault := restShapeDefault" % len(cur)
    if m == 6:
        at_tok.Set("restShapeDefault")
        return "只改 token restBendAnglesDefault := restShapeDefault"
    if m in (2, 7):
        ang = dihedrals(cur) * a.sign
        n_w = write_rest_arrays(ang)
        return "restAdjTriPairs/restBendAngles := 當下二面角 × %g(%d 對,摺線上平均 %.1f°)" % (a.sign, n_w, ang[CREASE].mean())
    if m == 3:
        at_bend.Set(float(a.bend0))
        return "材質 surfaceBendStiffness %g -> %g" % (BEND, a.bend0)
    raise SystemExit("unknown mode")


NSTEP = int(round(a.t_end / DT)); S_REL = int(round(a.t_rel / DT)); PE = int(round(0.1 / DT))
S_CHK = S_REL + int(round(1.0 / DT))
released = NOANCHOR
rec = {}
t0 = time.time()
for s in range(NSTEP + 1):
    t = s * DT
    for q in ANC:
        if released and not (a.keep_anchor and q["k"] == 1):
            continue
        q["prim"].set_world_pose(position=anchor_pos(q["vi"], t), orientation=np.array([1., 0, 0, 0]))
    if s == S_REL and not NOANCHOR:
        cur = np.array(pts.Get())
        rec["rel"] = (cur[V0, 0], cur[V0, 2], dihedrals(cur)[CREASE].mean() * a.sign)
        msg = do_mode(cur)
        for q in ANC:
            if a.keep_anchor and q["k"] == 1:
                continue
            st.RemovePrim(Sdf.Path(q["scope"]))
        released = True
        P("\n★ t=%.2fs 放手(RemovePrim %s)+ %s" % (t, "角 0 的 attachment Scope,角 110 留著" if a.keep_anchor else "兩個 attachment Scope", msg))
        P("   放手前:角0 x=%.4f z=%.4f | 摺線二面角 %.1f°" % rec["rel"])
        if a.mode in (5, 7):
            px = omni.physx.get_physx_interface()
            px.release_physics_objects(); px.force_load_physics_from_usd()
            P("   已 release_physics_objects() + force_load_physics_from_usd()")
        world.step(render=False)
        cur2 = np.array(pts.Get())
        P("   放手那一步:全部頂點單步位移 max %.2f mm,平均 %.2f mm" % (np.linalg.norm(cur2 - cur, axis=1).max()*1e3,
                                                                np.linalg.norm(cur2 - cur, axis=1).mean()*1e3))
        continue
    world.step(render=False)
    cur = np.array(pts.Get())
    if s % PE == 0 or s == S_CHK:
        dh = dihedrals(cur) * a.sign
        P("t=%.2fs  角0 x=%.4f z=%.4f | 角110 z=%.4f | 摺線二面角 mean %.1f° (min %.1f max %.1f) | 其餘對 |角| max %.1f° | 布 z max %.4f%s"
          % (t, cur[V0, 0], cur[V0, 2], cur[V1, 2], dh[CREASE].mean(), dh[CREASE].min(), dh[CREASE].max(),
             np.abs(np.delete(dh, CREASE)).max(), cur[:, 2].max(), "  <- 放手後 1s" if s == S_CHK else ""))
    if s == S_CHK:
        rec["chk"] = (cur[V0, 0], cur[V0, 2], dihedrals(cur)[CREASE].mean() * a.sign)
        if a.keep_anchor and ANC:
            rec["keep"] = (float(cur[V1, 2]), float(ANC[1]["prim"].get_world_pose()[0][2]))

P("\n===== 判讀 mode %d(fold %.0f°, sign %+g%s)=====" % (a.mode, a.fold_deg, a.sign, (", bend0 %g" % a.bend0) if a.mode == 3 else ""))
if NOANCHOR:
    x, z, d = rec["chk"]
    P("建立時預設摺痕(%s)、無錨點:t=%.1fs 角0 z=%.4f(折起來應≈%.3f,平的≈0.005)| 摺線二面角 %.1f°(目標 %.0f°)"
      % ("restAdjTriPairs/restBendAngles" if a.mode == 4 else "restShapePoints+restShapeDefault",
         a.t_rel + 1.0, z, Z0 + (XC - P0[0, 0])*np.sin(np.radians(a.fold_deg)), d, a.fold_deg))
    P("⇒ %s" % ("載入時有效(布自己折起來)" if z > 0.06 else
                ("有作用但往另一邊折" if abs(d) > 30 else "沒有作用(布還是平的)")))
else:
    (x0, z0, d0), (x1, z1, d1) = rec["rel"], rec["chk"]
    P("放手前 角0 z=%.4f(x=%.3f,摺線 %.1f°) → 放手後 1s z=%.4f(x=%.3f,摺線 %.1f°)" % (z0, x0, d0, z1, x1, d1))
    P("⇒ %s" % ("定型(z 仍 > 0.06)" if z1 > 0.06 else ("回彈(z < 0.03)" if z1 < 0.03 else "介於中間")))
    if "keep" in rec:
        zv, za = rec["keep"]
        P("留著的錨點(角 110):放手後 1s 頂點 z=%.4f 方塊 z=%.4f 差 %.1f mm ⇒ %s"
          % (zv, za, abs(zv - za)*1e3, "attachment 仍有效、錨點仍可動" if abs(zv - za) < 0.005 else "**錨點失效**"))
P("wall %.1fs" % (time.time() - t0))
sim.close()
