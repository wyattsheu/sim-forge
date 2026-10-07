# crease_hold_ui.py — 貼進 Isaac Sim UI 的 Script Editor 執行(Window > Script Editor),
# 之後按 Play,四片紙箱蓋就會有彈塑性摺痕撐住(= README 裡 crease_physics.py 的模型),
# 用 Shift + 左鍵拖曳可以把蓋子折開,放手後它會保持在折開的角度(塑性)。
# 停止:執行 crease_stop()
#
# 執行方式(p 換成這個檔案的實際路徑):
#   p = "/path/to/sim/crease_hold_ui.py"; exec(compile(open(p).read(), p, "exec"))
import os, sys, math
import numpy as np, torch
from omni.physx import get_physx_interface
from isaacsim.core.prims import RigidPrim

# ── sim/ 目錄在哪 ───────────────────────────────────────────────────────────
# 從 Script Editor 的 File > Open 開這支再按 Run 時,程式拿不到自己的路徑,
# 交付包不在預設位置的話,請把 sim/ 的完整路徑填在這裡:
SIM_DIR_OVERRIDE = ""
# 其餘情況自動判斷:exec(compile(open(p).read(), p, "exec")) 執行時 co_filename 就是 p。
_me = sys._getframe().f_code.co_filename
_cands = [SIM_DIR_OVERRIDE, os.environ.get("CREASE_SIM_DIR", ""),
          os.path.dirname(os.path.abspath(_me)) if _me.endswith("crease_hold_ui.py") else "",
          "/isaac-sim/test_scripts/manip_fr3/handoff_20261002/sim"]
SIM_DIR = next((d for d in _cands if d and os.path.isfile(os.path.join(d, "crease_physics.py"))), None)
if SIM_DIR is None:
    raise RuntimeError("[crease] 找不到 crease_physics.py —— 請把 sim/ 的路徑填進第 16 行的 SIM_DIR_OVERRIDE")
BOX = "/World/Packed/Box"
if SIM_DIR not in sys.path:
    sys.path.append(SIM_DIR)
from crease_physics import ElastoplasticCrease

_S = {}

def _qmul(a, b):
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2,
                     w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])
def _qconj(q): return np.array([q[0], -q[1], -q[2], -q[3]])
def _qrot(q, v): return _qmul(_qmul(q, np.r_[0.0, v]), _qconj(q))[1:]

def _setup():
    import uuid
    tag = uuid.uuid4().hex[:6]
    lids = RigidPrim(prim_paths_expr=BOX + "/f[xy][pn]", name="creaseui_lids_" + tag); lids.initialize()
    base = RigidPrim(prim_paths_expr=BOX + "/base", name="creaseui_base_" + tag); base.initialize()
    order = [str(p).rsplit("/", 1)[-1] for p in lids.prim_paths]
    _, qL = [np.array(x, float) for x in lids.get_world_poses()]
    _, qB = [np.array(x, float)[0] for x in base.get_world_poses()]
    rel0 = [_qmul(_qconj(qB), qL[i]) for i in range(len(order))]
    cr = ElastoplasticCrease(len(order), "cpu", k=3.2, my0=0.60, h=0.85, c=0.33, clip=3.0)
    cr.reset(torch.arange(len(order)), torch.zeros(len(order)))
    _S.update(lids=lids, base=base, order=order, rel0=rel0, cr=cr)
    print("[crease] 已接上", order)

def _state():
    lids, base, rel0 = _S["lids"], _S["base"], _S["rel0"]
    _, qL = [np.array(x, float) for x in lids.get_world_poses()]
    _, qB = [np.array(x, float)[0] for x in base.get_world_poses()]
    wL = np.array(lids.get_angular_velocities(), float)
    wB = np.array(base.get_angular_velocities(), float)[0]
    ang, rate, axes = [], [], []
    for i in range(len(_S["order"])):
        ax = _qrot(qL[i], np.array([1.0, 0, 0]))
        rr = _qmul(_qconj(rel0[i]), _qmul(_qconj(qB), qL[i]))
        if rr[0] < 0: rr = -rr
        ang.append(2*math.atan2(rr[1], rr[0]))
        rate.append(float(np.dot(wL[i] - wB, ax))); axes.append(ax)
    return np.array(ang), np.array(rate), axes

def _on_step(dt):
    if "cr" not in _S:
        try: _setup()
        except Exception as e:
            print("[crease] 還沒準備好:", e); return
    ang, rate, axes = _state()
    tq = _S["cr"].step(torch.tensor(ang, dtype=torch.float32),
                       torch.tensor(rate, dtype=torch.float32)).numpy()
    tau = np.stack([axes[i]*float(tq[i]) for i in range(len(axes))])
    _S["lids"].apply_forces_and_torques_at_pos(torques=tau, is_global=True)
    _S["base"].apply_forces_and_torques_at_pos(torques=-tau.sum(0, keepdims=True), is_global=True)

def crease_fix_solver(hz=120, pos_iter=8, vel_iter=1):
    """UI 預設的 PhysicsScene 是 60 Hz / posIter=1 / velIter=0,紙箱會陷進桌面 ~47 mm。
    這裡把目前 stage 的 PhysicsScene 調到 120 Hz / posIter>=8 → 實測位移 0.00 mm。"""
    import omni.usd
    from pxr import UsdPhysics, PhysxSchema
    st = omni.usd.get_context().get_stage()
    sc = [p for p in st.Traverse() if p.IsA(UsdPhysics.Scene)]
    if not sc:
        sc = [UsdPhysics.Scene.Define(st, "/physicsScene").GetPrim()]
        print("[crease] stage 沒有 PhysicsScene → 已新增 /physicsScene")
    for p in sc:
        api = PhysxSchema.PhysxSceneAPI.Apply(p)
        api.CreateTimeStepsPerSecondAttr().Set(hz)
        api.CreateMinPositionIterationCountAttr().Set(pos_iter)
        api.CreateMinVelocityIterationCountAttr().Set(vel_iter)
        api.CreateSolverTypeAttr().Set("TGS")
        api.CreateGpuFoundLostAggregatePairsCapacityAttr().Set(8192)
        api.CreateGpuTotalAggregatePairsCapacityAttr().Set(8192)
        print("[crease] %s -> %d Hz / posIter>=%d / velIter>=%d" % (p.GetPath(), hz, pos_iter, vel_iter))

def crease_stop():
    _S.pop("sub", None); _S.clear(); print("[crease] 已停止")

crease_fix_solver()
_S["sub"] = get_physx_interface().subscribe_physics_step_events(_on_step)
print("[crease] 摺痕力矩已掛上 physics step;按 Play 即生效。停止請執行 crease_stop()")
