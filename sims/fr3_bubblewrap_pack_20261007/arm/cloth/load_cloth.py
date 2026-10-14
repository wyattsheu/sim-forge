#!/usr/bin/env python3
"""load_cloth.py — 把 volume 包材(wrap.npz 的 snap_end,已定型:points = rest = 開蓋後形狀)放進雙臂場景。
    /isaac-sim/python.sh load_cloth.py [--young 2e3] [--settle 2.0] [--tag x]
場景:scene_final.usd,/World/Packed rotateZ +180(= yaw 270),原 Wrap/Mug deactivate;紙箱底 kinematic、四蓋純 xform。
座標:V(vol 世界)→ L = V − OFF → S = TB · L(TB = /World/Packed/Box 世界矩陣;另印與 cloth_iface 公式 T+Rz(270)L 的差)。
杯子 = snapmug_end 頂點(同樣換到 S),kinematic,convexDecomposition。蓋角:npz 無 → 四片 260°。
其他模組(dry_with_cloth.py)在 SimulationApp 之後 import,呼叫 setup(st, a, P)。"""
import os, sys, json, math
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # handoff_20260929
VOL = os.path.join(ROOT, "vol")
NPZ = os.path.join(VOL, "soft", "s2", "wrap.npz")
OFF = np.array([0.0, 0.200, 0.097])
SCENE = "/isaac-sim/test_scripts/manip_fr3/handoff_20261002/scene_final.usd"
BOX = "/World/Packed/Box"
LID_DEG = 260.0


def add_args(ap):
    ap.add_argument("--young", type=float, default=2e3)
    ap.add_argument("--poisson", type=float, default=0.45)
    ap.add_argument("--areal", type=float, default=0.1)
    ap.add_argument("--thick", type=float, default=0.004)
    ap.add_argument("--fric", type=float, default=0.8)
    ap.add_argument("--cont", type=float, default=0.002)
    ap.add_argument("--rest", type=float, default=0.0005)
    ap.add_argument("--solver", type=int, default=128)
    ap.add_argument("--dt", type=float, default=1 / 240.0)
    ap.add_argument("--snap", default="end")
    ap.add_argument("--tag", default="")


def rot_axis(k, deg):
    k = np.asarray(k, float); k = k / np.linalg.norm(k); t = math.radians(deg)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


def setup(st, a, P, gravity=True):
    """回傳 dict:PLATE(Mesh)、TETS、FLAT、REST_S、MUG_S、MTRI、TB、lid ops 等。stage 必須已開 SCENE。"""
    sys.path.insert(0, VOL)
    from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Gf, Sdf, Vt, UsdShade
    import volcommon as VC, vol_pen as VP, trimesh
    pk = st.GetPrimAtPath("/World/Packed")
    rz = next(o for o in UsdGeom.Xformable(pk).GetOrderedXformOps() if o.GetOpName() == "xformOp:rotateZ")
    rz.Set(float(rz.Get()) + 180.0)
    P("/World/Packed rotateZ = %.0f°(yaw 270 擺法)" % rz.Get())
    for p in ("/World/Packed/Wrap", "/World/Packed/Mug"):
        if st.GetPrimAtPath(p): st.GetPrimAtPath(p).SetActive(False)
    if not any(p.IsA(UsdPhysics.Scene) for p in st.Traverse()):
        ps = UsdPhysics.Scene.Define(st, "/physicsScene")
    else:
        ps = UsdPhysics.Scene(next(p for p in st.Traverse() if p.IsA(UsdPhysics.Scene)))
    ps.CreateGravityMagnitudeAttr().Set(9.81 if gravity else 0.0)
    ps.CreateGravityDirectionAttr().Set(Gf.Vec3f(0, 0, -1))
    pxs = PhysxSchema.PhysxSceneAPI.Apply(ps.GetPrim())
    pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
    for n in ("base", "fxp", "fxn", "fyp", "fyn"):
        UsdPhysics.RigidBodyAPI(st.GetPrimAtPath(BOX + "/" + n)).CreateKinematicEnabledAttr().Set(True)
    for n in ("fxp", "fxn", "fyp", "fyn"):
        UsdPhysics.RigidBodyAPI(st.GetPrimAtPath(BOX + "/" + n)).CreateRigidBodyEnabledAttr().Set(False)
        UsdPhysics.Joint(st.GetPrimAtPath(BOX + "/crease_" + n)).CreateJointEnabledAttr().Set(False)
    xc = UsdGeom.XformCache()
    Wm = lambda p: np.array(xc.GetLocalToWorldTransform(st.GetPrimAtPath(p))).T
    TB = Wm(BOX)
    # 蓋子 260°(用 reach.json 的鉸鏈)
    RJ = json.load(open(os.path.join(ROOT, "arm", "data", "reach.json")))
    lidinfo = {}
    for nm in ("fxp", "fxn", "fyp", "fyn"):
        L = RJ["lids"][nm]; hw = (TB @ np.r_[L["h"], 1])[:3]; aw = TB[:3, :3] @ np.array(L["ax"])
        T = np.eye(4); R = rot_axis(aw, L["sgn"] * LID_DEG); T[:3, :3] = R; T[:3, 3] = hw - R @ hw
        pr = st.GetPrimAtPath(BOX + "/" + nm); LT0 = Wm(BOX + "/" + nm)
        PAR = np.array(UsdGeom.Xformable(pr.GetParent()).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T
        xf = UsdGeom.Xformable(pr); xf.ClearXformOpOrder(); op = xf.AddTransformOp()
        op.Set(Gf.Matrix4d(*(np.linalg.inv(PAR) @ T @ LT0).T.flatten().tolist()))
        lidinfo[nm] = dict(op=op, PAR=PAR, LT0=LT0, T=T)
    P("四片蓋 → %.0f°(npz 無蓋角欄位)" % LID_DEG)
    # 布
    d = np.load(NPZ)
    key = "snap_" + a.snap
    Lm = d[key] - OFF
    S = (TB @ np.c_[Lm, np.ones(len(Lm))].T).T[:, :3]
    c, s_ = math.cos(math.radians(270)), math.sin(math.radians(270)); Rz = np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]])
    S_if = np.array([-0.020, 0.0, 0.020]) + Lm @ Rz.T
    P("布 %s:%d 點;TB 換算 vs cloth_iface 公式最大差 %.3f mm;S bbox min %s max %s mm"
      % (key, len(S), np.abs(S - S_if).max() * 1e3, np.round(S.min(0) * 1e3, 1).tolist(), np.round(S.max(0) * 1e3, 1).tolist()))
    TETS = d["tets"].astype(int); FLAT = d["flat"]
    mat = VC.add_material(st, "/World/cloth_mat", a.young, a.poisson, a.areal / a.thick, a.fric)
    tm = UsdGeom.TetMesh.Define(st, "/World/cloth")
    tm.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in S]))
    tm.GetTetVertexIndicesAttr().Set(Vt.Vec4iArray([Gf.Vec4i(*map(int, t)) for t in TETS]))
    from omni.physx.scripts import deformableUtils, physicsUtils
    ok = deformableUtils.set_physics_volume_deformable_body(st, Sdf.Path("/World/cloth"))
    body = st.GetPrimAtPath("/World/cloth")
    physicsUtils.add_physics_material_to_prim(st, body, mat)
    body.ApplyAPI("PhysxBaseDeformableBodyAPI")
    VC.sa(body, "physxDeformableBody:solverPositionIterationCount", int(a.solver), Sdf.ValueTypeNames.UInt)
    VC.sa(body, "physxDeformableBody:selfCollision", True, Sdf.ValueTypeNames.Bool)
    VC.sa(body, "physxDeformableBody:selfCollisionFilterDistance", float(2 * a.rest), Sdf.ValueTypeNames.Float)
    pc = PhysxSchema.PhysxCollisionAPI.Apply(body)
    pc.CreateContactOffsetAttr().Set(float(a.cont)); pc.CreateRestOffsetAttr().Set(float(a.rest))
    ra = body.GetAttribute("omniphysics:restShapePoints")
    rr = np.array(ra.Get(), float) if ra and ra.Get() else None
    P("cloth deformable ok=%s E %.0e;restShapePoints %s(與 points 差 %s mm)" % (
        ok, a.young, "有" if rr is not None else "無", "%.4f" % (np.abs(rr - S).max() * 1e3) if rr is not None and rr.shape == S.shape else "-"))
    if rr is None or rr.shape != S.shape:
        if not ra: ra = body.CreateAttribute("omniphysics:restShapePoints", Sdf.ValueTypeNames.Point3fArray)
        ra.Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in S]))
    vm = UsdShade.Material.Define(st, "/World/cloth_look"); sh = UsdShade.Shader.Define(st, "/World/cloth_look/s")
    sh.CreateIdAttr("UsdPreviewSurface"); sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.25, 0.75, 0.95))
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.85)
    vm.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(body).Bind(vm)
    # 杯子
    mk = "snapmug_" + a.snap
    mesh = trimesh.load(os.path.join(VOL, "mug.stl"))
    MV = d[mk] - OFF; assert len(MV) == len(mesh.vertices), (len(MV), len(mesh.vertices))
    MS = (TB @ np.c_[MV, np.ones(len(MV))].T).T[:, :3]; MF = np.asarray(mesh.faces)
    mug = UsdGeom.Xform.Define(st, "/World/cloth_mug")
    UsdPhysics.RigidBodyAPI.Apply(mug.GetPrim()).CreateKinematicEnabledAttr(True)
    g = UsdGeom.Mesh.Define(st, "/World/cloth_mug/geo")
    g.CreatePointsAttr([Gf.Vec3f(*map(float, p)) for p in MS])
    g.CreateFaceVertexIndicesAttr([int(i) for f in MF for i in f]); g.CreateFaceVertexCountsAttr([3] * len(MF))
    g.CreateSubdivisionSchemeAttr().Set("none"); g.CreateDoubleSidedAttr(True)
    UsdPhysics.CollisionAPI.Apply(g.GetPrim())
    UsdPhysics.MeshCollisionAPI.Apply(g.GetPrim()).CreateApproximationAttr("convexDecomposition")
    gc = PhysxSchema.PhysxCollisionAPI.Apply(g.GetPrim()); gc.CreateContactOffsetAttr(0.004); gc.CreateRestOffsetAttr(0.001)
    MTRI = trimesh.Trimesh(MS, MF, process=False)
    P("杯子 kinematic(%s),S bbox %s ~ %s mm" % (mk, np.round(MS.min(0) * 1e3, 1).tolist(), np.round(MS.max(0) * 1e3, 1).tolist()))
    PLATE = VC.Mesh(st, "/World/cloth")
    VR = VP.tet_vol(S, TETS); SGN = np.sign(VR)
    DmRi = np.linalg.inv(np.stack([S[TETS[:, i]] - S[TETS[:, 0]] for i in (1, 2, 3)], 2))
    h = float(np.median(np.linalg.norm(np.diff(FLAT[:36, :2], axis=0), axis=1)))
    def measure(Pc):
        Ds = np.stack([Pc[TETS[:, i]] - Pc[TETS[:, 0]] for i in (1, 2, 3)], 2)
        sv = np.linalg.svd(Ds @ DmRi, compute_uv=False)
        r = dict(finite=bool(np.isfinite(Pc).all()))
        r["bb"] = ((Pc.max(0) - Pc.min(0)) * 1e3).round(1).tolist()
        r["E"] = float((((sv - 1) ** 2).sum(1) * np.abs(VR)).sum())
        r["disp"] = float(np.linalg.norm(Pc - S, axis=1).max() * 1e3)
        r["inv"] = int(((VP.tet_vol(Pc, TETS) * SGN) <= 0).sum())
        r["pen"] = int(VP.self_pen_count(Pc, TETS, FLAT, far=3 * h)[0])
        lo, hi = MS.min(0) - 0.002, MS.max(0) + 0.002
        cand = np.where(((Pc > lo) & (Pc < hi)).all(1))[0]
        r["inmug"] = int(MTRI.contains(Pc[cand]).sum()) if len(cand) else 0
        return r
    r0 = measure(S)
    P("初始(= rest)量測:%s" % r0)
    return dict(PLATE=PLATE, TETS=TETS, FLAT=FLAT, S0=S, MS=MS, MTRI=MTRI, TB=TB, lid=lidinfo, measure=measure, body=body, r0=r0)


if __name__ == "__main__":
    import argparse, functools, builtins
    print = functools.partial(builtins.print, flush=True)
    ap = argparse.ArgumentParser(); add_args(ap); ap.add_argument("--settle", type=float, default=2.0)
    a = ap.parse_args()
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    import omni.usd
    tag = "E%.0e%s" % (a.young, ("_" + a.tag) if a.tag else "")
    LOG = open(os.path.join(HERE, "logs", "load_cloth_%s.log" % tag), "w")
    def P(*s):
        t = " ".join(str(x) for x in s); print(t); LOG.write(t + "\n"); LOG.flush()
    omni.usd.get_context().open_stage(SCENE)
    for _ in range(10): app.update()
    st = omni.usd.get_context().get_stage()
    C = setup(st, a, P)
    from isaacsim.core.api import World
    world = World(physics_dt=a.dt, rendering_dt=a.dt, stage_units_in_meters=1.0)
    pc_ = world.get_physics_context(); pc_.enable_gpu_dynamics(True); pc_.set_broadphase_type("GPU")
    world.reset()
    Pc = C["PLATE"].pts(); P("reset 後 points vs 初始 max %.3f mm" % (np.linalg.norm(Pc - C["S0"], axis=1).max() * 1e3))
    n = int(round(a.settle / a.dt)); res = []
    for k in range(1, n + 1):
        world.step(render=False)
        if k % int(round(0.25 / a.dt)) == 0 or k == n:
            r = C["measure"](C["PLATE"].pts()); r["t"] = round(k * a.dt, 3); res.append(r)
            P("t=%.2f bbox %s | 位移 max %.2f mm | E %.3e | 反轉 %d | 互穿 %d | 穿杯 %d | finite %s"
              % (r["t"], r["bb"], r["disp"], r["E"], r["inv"], r["pen"], r["inmug"], r["finite"]))
            _p = C["PLATE"].pts(); _d = np.linalg.norm(_p - C["S0"], axis=1); _i = int(np.argmax(_d))
            P("    最大位移頂點 v%d 原 %s → %s mm;>5mm 頂點 %d" % (_i, np.round(C["S0"][_i]*1e3,1).tolist(), np.round(_p[_i]*1e3,1).tolist(), int((_d>0.005).sum())))
            if not r["finite"] or r["disp"] > 500: P("★ 炸開"); break
    last = res[-1]
    ok = last["disp"] < 5 and last["pen"] == 0 and last["inv"] == 0
    P("★ 判定:%s(位移 %.2f mm、互穿 %d、穿杯 %d、反轉 %d)" % ("PASS" if ok else "FAIL", last["disp"], last["pen"], last["inmug"], last["inv"]))
    json.dump(dict(args=vars(a), r0=C["r0"], hist=res, ok=ok), open(os.path.join(HERE, "logs", "load_cloth_%s.json" % tag), "w"), indent=1)
    app.close()
