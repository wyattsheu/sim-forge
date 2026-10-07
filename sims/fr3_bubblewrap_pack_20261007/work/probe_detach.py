#!/usr/bin/env python3
"""probe_detach.py — 同一次模擬裡,能不能把 surface deformable 布上的 attachment「放掉」?

    /isaac-sim/python.sh probe_detach.py --mode N [--n_anchors 3] [--rise_after] [--mass 1e-2]

背景:wrap_sim.py 用 kinematic 小方塊 + OmniPhysicsVtxXformAttachment(stiffness=inf)綁布的外緣頂點。
  2026-09-25 probe_release.py 實測 attachmentEnabled=False / stiffness=0 在跑的途中改都無效。
  這支探針試作者沒試過的路(mode 1/2/3/6/7),並把 4/5 當對照重做一次。

場景:10x10 surface deformable 布(材料參數照 wrap_sim.py 預設)。錨點 0 綁角落頂點 0,用**同一套**
  Scope(PhysxAutoDeformableAttachmentAPI)+ 子 prim(OmniPhysicsVtxXformAttachment)綁在 6mm kinematic 方塊上,
  t=0~1s 抬到 z=0.30m;--n_anchors 2~4 時再多綁頂點 N / N*(N+1) / N*(N+1)+N(另三個角落),抬到 z=0.15m
  且**全程不放**,用來看「放掉其中一個,其他錨點會不會被波及」。t=1.5s 對錨點 0 執行「放掉」,之後每 0.1s 印頂點 z。
  ★ 幾何注意:布 bend=2e3、rest 角 flat,只抓兩個對角(n_anchors=3)時布像翹翹板,放掉的角會被翹住不掉
    (2026-09-30 實測 m1_n3/m5_n3),所以多錨點要用 n_anchors=4:放掉後角落 0 應落到其他三角所在的 0.15 平面。

mode(放掉動作只對錨點 0 做):
  1  runtime 刪 prim:stage.RemovePrim(attachment Scope,連子 prim)          (--del_cmd 改用 omni.kit DeletePrims 指令,官方測試用法)
  2  子 prim 的 relationship omniphysics:src1 → SetTargets([])
  3  方塊 kinematicEnabled → False,mass=--mass(錨點自己變成會被布帶走的自由剛體)
  4  用有限 stiffness(--stiff,預設 1e4)建,runtime 把 stiffness → 0
  5  omniphysics:attachmentEnabled → False
  6  Scope 的 relationship physxAutoDeformableAttachment:attachable1 → SetTargets([])
  7  Scope SetActive(False)(不刪 prim,只 deactivate)
  10 重演 probe_release.py 的組合(需 --n_anchors>=2):同一步 錨點0 attachmentEnabled→False + 錨點1 stiffness→0
  0  什麼都不做(對照組:確認 attachment 真的抓得住)
--rise_after:放掉後**方塊 0** 再往上走 0.12m/1s(probe_release.py 的動法):頂點 0 若還跟著方塊走就是沒放掉

判準(跑之前寫死):放掉後 1 秒(t=2.5s)頂點 0 的 z 比放掉前(t=1.5s)低 > 0.10m ⇒ 成功;
  仍在 0.3m 附近 ⇒ 失敗。單錨點時自由落體 1s ≈ 4.9m,成功的話直接掉到地上(z≈0)。
  另印 頂點 0 與方塊 0 的 z 差(probe_release.py 的 R1 判準):< 5mm 仍跟著、> 50mm 已脫離。
  其他錨點(k>=1):放掉後 1s 該頂點與方塊的 z 差 < 5mm ⇒ 「仍抓住」。
副作用檢查:放掉那一步,**離錨點 0 > 0.1m 的其他頂點**單步位移最大值(對照放掉前一步),
  以及整張布有沒有被重設回初始平鋪位置(平均距初始位置)。

★ 2026-09-30 實測結果摘要(Isaac Sim 5.1 / omni.physx 107.3.26):
  成功(放掉後 0.3s 內自由落地;4 錨點時其餘錨點差 <0.6mm 不受影響;布不重設):
    mode 1 stage.RemovePrim(Scope)、mode 7 Scope.SetActive(False)、mode 5 attachmentEnabled=False —— 三者軌跡完全相同
  失敗(頂點一路跟著方塊):mode 2 清 src1、mode 6 清 attachable1、mode 4 stiffness→0(1e4 建的也一樣)
  不可用:mode 3 kinematic→dynamic 有生效,但 mass 1e-4 / 1e-2 都把整張布彈飛到 0.65~0.98m
  作者 09-25「attachmentEnabled 改無效」:原版 probe_release.py 三個錨點一起升,放掉的中點被兩側 11.7cm 的
    仍綁鄰居用近乎不可拉伸的布面撐住(差 1mm vs 真綁著的 0mm);改成只升被放掉那個錨點 → 差 122mm,確認有放掉。
"""
import os, sys, argparse, time
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--mode", type=int, required=True, help="0..7, 10,見檔頭")
ap.add_argument("--n_anchors", type=int, default=1, help="1~4 個錨點;放掉動作只對錨點 0 做")
ap.add_argument("--del_cmd", action="store_true", help="mode 1 改用 omni.kit.commands DeletePrims")
ap.add_argument("--stiff", type=float, default=1e4, help="mode 4 建 attachment 時的有限 stiffness")
ap.add_argument("--damp", type=float, default=1.0, help="mode 4 建 attachment 時的 damping")
ap.add_argument("--mass", type=float, default=1e-4, help="mode 3 方塊變動態後的質量(kg)")
ap.add_argument("--rise_after", action="store_true", help="放掉後方塊 0 再往上 0.12m/1s(看頂點 0 跟不跟)")
ap.add_argument("--t_rel", type=float, default=1.5, help="幾秒時放掉")
ap.add_argument("--t_end", type=float, default=3.0)
ap.add_argument("--solver", type=int, default=64)
a = ap.parse_args()
assert 1 <= a.n_anchors <= 4
if a.mode == 10:
    assert a.n_anchors >= 2, "mode 10 需要 --n_anchors >= 2"

os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from isaacsim.core.prims import SingleXFormPrim
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, PhysxSchema, Vt
from omni.physx.scripts import deformableUtils
import omni.usd
P = lambda *s: print(*s, flush=True)


def sa(prim, n, v, tn=None):
    at = prim.GetAttribute(n)
    if not at or not at.IsValid():
        if tn is None:
            return None
        at = prim.CreateAttribute(n, tn)
    at.Set(v)
    return at


# ---- 世界(照 wrap_sim.py 221~231)----
DT = 1/120.0
world = World(physics_dt=DT, rendering_dt=1/30.0)
world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")

# ---- 布:10x10,材料照 wrap_sim.py 預設(young 5e4 / thick 10mm / bend 2e3 / dens 100)----
YOUNGS, POISSON, THICK, BEND = 5.0e4, 0.45, 0.010, 2.0e3
FRIC, DENS = 0.8, 100.0
LDAMP, EDAMP, BDAMP = 0.20, 0.30, 0.30
CONT, REST = 0.005, 0.001
W, N, Z0 = 0.30, 10, 0.005
verts = [Gf.Vec3f(-W/2 + i*W/N, -W/2 + j*W/N, Z0) for j in range(N+1) for i in range(N+1)]
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
P("set_physics_surface_deformable_body ->", ok)
sp.ApplyAPI("PhysxSurfaceDeformableBodyAPI")
sa(sp, "physxDeformableBody:selfCollision", False)
sa(sp, "omniphysics:restBendAnglesDefault", "flatDefault", Sdf.ValueTypeNames.Token)
sa(sp, "physxDeformableBody:solverPositionIterationCount", a.solver, Sdf.ValueTypeNames.Int)
sa(sp, "physxDeformableBody:linearDamping", LDAMP, Sdf.ValueTypeNames.Float)
pc = PhysxSchema.PhysxCollisionAPI.Apply(sp)
pc.CreateRestOffsetAttr().Set(REST); pc.CreateContactOffsetAttr().Set(CONT)
UsdShade.MaterialBindingAPI.Apply(sp).Bind(phm, UsdShade.Tokens.weakerThanDescendants, "physics")

# ---- 錨點:照 wrap_sim.py 809~839(Scope + 子 prim),錨點 0 抬到 0.30m,其餘抬到 0.15m ----
CORNERS = [0, N, N*(N+1), N*(N+1)+N]   # 四個角落頂點
ZTOP = [0.30, 0.15, 0.15, 0.15]
UsdGeom.Xform.Define(st, "/World/anchors")
ANC = []
for k in range(a.n_anchors):
    vi = CORNERS[k]
    p0 = np.array([verts[vi][0], verts[vi][1], verts[vi][2]], dtype=float)
    ap_ = "/World/anchors/a%03d" % k
    cb = UsdGeom.Cube.Define(st, ap_); cb.CreateSizeAttr(0.006)
    UsdGeom.Xformable(cb).AddTranslateOp().Set(Gf.Vec3d(*p0))
    UsdPhysics.CollisionAPI.Apply(cb.GetPrim())
    rb = UsdPhysics.RigidBodyAPI.Apply(cb.GetPrim())
    rb.CreateKinematicEnabledAttr(True)
    if a.mode == 3 and k == 0:
        UsdPhysics.MassAPI.Apply(cb.GetPrim()).CreateMassAttr(float(a.mass))
    UsdGeom.Imageable(cb.GetPrim()).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)

    scp = "/World/attach/a%03d" % k
    sc = st.DefinePrim(scp, "Scope")
    sc.ApplyAPI("PhysxAutoDeformableAttachmentAPI")
    for k2, v2 in [("enableDeformableVertexAttachments", True),
                   ("enableRigidSurfaceAttachments", False),
                   ("enableCollisionFiltering", True),
                   ("enableDeformableFilteringPairs", False)]:
        sa(sc, "physxAutoDeformableAttachment:" + k2, v2, Sdf.ValueTypeNames.Bool)
    sa(sc, "physxAutoDeformableAttachment:deformableVertexOverlapOffset", 0.008, Sdf.ValueTypeNames.Float)
    sa(sc, "physxAutoDeformableAttachment:collisionFilteringOffset", 0.030, Sdf.ValueTypeNames.Float)
    for rn, tg in [("attachable0", "/World/sheet"), ("attachable1", ap_)]:
        (sc.GetRelationship("physxAutoDeformableAttachment:" + rn) or
         sc.CreateRelationship("physxAutoDeformableAttachment:" + rn)).SetTargets([Sdf.Path(tg)])
    ch = st.DefinePrim(scp + "/vtx_xform_attachment", "OmniPhysicsVtxXformAttachment")
    stiff0 = a.stiff if (a.mode == 4 and k == 0) else float("inf")
    damp0 = a.damp if (a.mode == 4 and k == 0) else 0.0
    at_en = sa(ch, "omniphysics:attachmentEnabled", True, Sdf.ValueTypeNames.Bool)
    sa(ch, "omniphysics:damping", damp0, Sdf.ValueTypeNames.Float)
    at_st = sa(ch, "omniphysics:stiffness", stiff0, Sdf.ValueTypeNames.Float)
    sa(ch, "omniphysics:vtxIndicesSrc0", Vt.IntArray([vi]), Sdf.ValueTypeNames.IntArray)
    sa(ch, "omniphysics:localPositionsSrc1", Vt.Vec3fArray([Gf.Vec3f(0, 0, 0)]), Sdf.ValueTypeNames.Point3fArray)
    for rn, tg in [("src0", "/World/sheet"), ("src1", ap_)]:
        (ch.GetRelationship("omniphysics:" + rn) or
         ch.CreateRelationship("omniphysics:" + rn)).SetTargets([Sdf.Path(tg)])
    ANC.append(dict(k=k, vi=vi, p0=p0, path=ap_, scope=scp, sc=sc, ch=ch, rb=rb,
                    at_en=at_en, at_st=at_st, stiff0=stiff0, ztop=ZTOP[k]))
    P("錨點 %d:頂點 %d 綁在 %s(stiffness=%s damping=%s),抬到 z=%.2f" % (k, vi, ap_, stiff0, damp0, ZTOP[k]))
A0 = ANC[0]
VI = A0["vi"]

world.reset()
for q in ANC:
    q["prim"] = SingleXFormPrim(q["path"], name="anc%d" % q["k"])
pts = UsdGeom.Mesh(sp).GetPointsAttr()
P_INIT = np.array(pts.Get())
FAR = np.where(np.linalg.norm(P_INIT[:, :2] - P_INIT[VI, :2], axis=1) > 0.10)[0]   # 離錨點 0 >10cm 的頂點
P("布 %d 個頂點,其中離錨點 0 >10cm 的 %d 個當「其他頂點跳動」的觀察對象" % (len(P_INIT), len(FAR)))

T_LIFT = 1.0
def anchor_pos(q, t):
    u = min(1.0, max(0.0, t / T_LIFT))
    z = q["p0"][2] + (q["ztop"] - q["p0"][2]) * u
    if a.rise_after and q["k"] == 0 and t > a.t_rel:
        z += 0.12 * min(1.0, (t - a.t_rel) / 1.0)
    return np.array([q["p0"][0], q["p0"][1], z])


def release(mode):
    """回傳一行說明字串。"""
    if mode == 0:
        return "對照組:不放"
    if mode == 1:
        if a.del_cmd:
            import omni.kit.commands
            omni.kit.commands.execute("DeletePrims", paths=[A0["scope"]])
            return "omni.kit.commands DeletePrims(%s)" % A0["scope"]
        r = st.RemovePrim(Sdf.Path(A0["scope"]))
        return "stage.RemovePrim(%s) -> %s" % (A0["scope"], r)
    if mode == 2:
        A0["ch"].GetRelationship("omniphysics:src1").SetTargets([])
        return "子 prim omniphysics:src1 SetTargets([])"
    if mode == 3:
        A0["rb"].GetKinematicEnabledAttr().Set(False)
        return "方塊 physics:kinematicEnabled -> False(mass %g kg)" % a.mass
    if mode == 4:
        A0["at_st"].Set(0.0)
        return "omniphysics:stiffness %s -> 0" % A0["stiff0"]
    if mode == 5:
        A0["at_en"].Set(False)
        return "omniphysics:attachmentEnabled -> False"
    if mode == 6:
        A0["sc"].GetRelationship("physxAutoDeformableAttachment:attachable1").SetTargets([])
        return "Scope physxAutoDeformableAttachment:attachable1 SetTargets([])"
    if mode == 7:
        A0["sc"].SetActive(False)
        return "Scope SetActive(False)"
    if mode == 10:
        A0["at_en"].Set(False)
        ANC[1]["at_st"].Set(0.0)
        return "重演 probe_release:錨點0 attachmentEnabled->False + 錨點1 stiffness inf->0(同一步)"
    raise SystemExit("unknown mode %d" % mode)


def fmt_others(cur):
    s = ""
    for q in ANC[1:]:
        apos, _ = q["prim"].get_world_pose()
        s += " | 錨%d 頂點%d z=%.4f 方塊 z=%.4f" % (q["k"], q["vi"], cur[q["vi"], 2], float(apos[2]))
    return s


NSTEP = int(round(a.t_end / DT))
S_REL = int(round(a.t_rel / DT))
PRINT_EVERY = int(round(0.1 / DT))
released = False
z_at_rel = None
z_after_1s = None
others_after_1s = []
S_CHECK = S_REL + int(round(1.0 / DT))
prev = P_INIT.copy()
t0 = time.time()
for s in range(NSTEP + 1):
    t = s * DT
    for q in ANC:
        if released and a.mode == 3 and q["k"] == 0:   # mode 3 放掉之後不再指定方塊 0 的位置(它是動態剛體了)
            continue
        q["prim"].set_world_pose(position=anchor_pos(q, t), orientation=np.array([1., 0, 0, 0]))
    if s == S_REL:
        cur = np.array(pts.Get())
        z_at_rel = float(cur[VI, 2])
        d_prev = np.linalg.norm(cur - prev, axis=1)              # 放掉前一步的單步位移
        msg = release(a.mode)
        released = True
        P("\n★ t=%.2fs 放掉:%s" % (t, msg))
        P("   放掉前 頂點%d z=%.4f m%s | 前一步其他頂點(FAR)單步位移 max=%.2f mm"
          % (VI, z_at_rel, fmt_others(cur), d_prev[FAR].max()*1e3))
        world.step(render=False)
        cur2 = np.array(pts.Get())
        d_now = np.linalg.norm(cur2 - cur, axis=1)
        P("   放掉那一步 其他頂點(FAR)單步位移 max=%.2f mm,>5mm 的有 %d 個 | 整張布距初始平鋪位置平均 %.1f mm(放掉前 %.1f mm)"
          % (d_now[FAR].max()*1e3, int((d_now[FAR] > 0.005).sum()),
             np.linalg.norm(cur2 - P_INIT, axis=1).mean()*1e3, np.linalg.norm(cur - P_INIT, axis=1).mean()*1e3))
        scp = A0["scope"]
        P("   錨點 0 的 Scope prim 還在?%s  子 prim 還在?%s  Scope active?%s"
          % (bool(st.GetPrimAtPath(scp)), bool(st.GetPrimAtPath(scp + "/vtx_xform_attachment")),
             st.GetPrimAtPath(scp).IsActive() if st.GetPrimAtPath(scp) else "n/a"))
        prev = cur2
        continue
    world.step(render=False)
    cur = np.array(pts.Get())
    if s % PRINT_EVERY == 0:
        apos, _ = A0["prim"].get_world_pose()
        P("t=%.2fs  頂點%d z=%.4f m | 方塊0 z=%.4f m%s | 布 z 平均 %.4f 最高 %.4f | 布 xy bbox %.0fx%.0f mm%s"
          % (t, VI, cur[VI, 2], float(apos[2]), fmt_others(cur), cur[:, 2].mean(), cur[:, 2].max(),
             (cur[:, 0].max()-cur[:, 0].min())*1e3, (cur[:, 1].max()-cur[:, 1].min())*1e3,
             "  <- 放掉後 1s" if s == S_CHECK else ""))
    if s == S_CHECK:
        z_after_1s = float(cur[VI, 2])
        cube0_after_1s = float(apos[2]) if s % PRINT_EVERY == 0 else float(A0["prim"].get_world_pose()[0][2])
        for q in ANC[1:]:
            apos, _ = q["prim"].get_world_pose()
            others_after_1s.append((q["k"], q["vi"], float(cur[q["vi"], 2]), float(apos[2])))
    prev = cur

P("\n===== 判讀 mode %d(n_anchors=%d%s)=====" % (a.mode, a.n_anchors, ", rise_after" if a.rise_after else ""))
if a.mode == 0:
    P("對照組:放掉前 z=%.4f,1s 後 z=%.4f(應該都在 0.30 附近,證明 attachment 抓得住)" % (z_at_rel, z_after_1s))
else:
    drop = z_at_rel - z_after_1s
    verdict = "成功(掉了 %.3f m)" % drop if drop > 0.10 else "失敗(只降 %.3f m,還吊著)" % drop
    P("錨點 0 頂點%d:放掉前 z=%.4f m → 放掉後 1s z=%.4f m ⇒ %s" % (VI, z_at_rel, z_after_1s, verdict))
    gap = abs(z_after_1s - cube0_after_1s)
    P("錨點 0 頂點%d 與方塊 0 的 z 差(R1 判準):%.1f mm ⇒ %s"
      % (VI, gap*1e3, "仍跟著方塊(沒放掉)" if gap < 0.005 else ("已脫離方塊" if gap > 0.05 else "曖昧(5~50mm)")))
for (k, vi, zv, za) in others_after_1s:
    P("錨點 %d 頂點%d:放掉後 1s 頂點 z=%.4f 方塊 z=%.4f,差 %.1f mm ⇒ %s"
      % (k, vi, zv, za, abs(zv - za)*1e3, "仍抓住" if abs(zv - za) < 0.005 else "**鬆掉了**"))
P("wall %.1fs" % (time.time() - t0))
sim.close()
