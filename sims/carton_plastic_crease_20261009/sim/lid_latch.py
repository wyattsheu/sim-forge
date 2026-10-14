# lid_latch.py — 讓四片紙箱蓋在 UI 裡用滑鼠(或之後用手臂)拉得開、關得上,而且放手後會停住。
#
# 做法:蓋子的摺痕關節有一個弱彈簧 drive(目標角 0 = 關)。每個物理步量蓋子的開角:
#   開角超過 OPEN_DEG(預設 25°)→ drive 目標改成 OPEN_TARGET(170°,蓋子自己翻開並停在開的位置)
#   開角被壓回 CLOSE_DEG(12°)以下 → drive 目標改回 0(關)
# 就是一個有遲滯的雙穩態閂鎖。拉一下就翻開、壓回去就關上;放手不會彈回。
#
# 由 ui_boot.py / webrtc_boot.py 自動載入(LID_LATCH=0 關掉)。Script Editor:
#   p = "/path/to/sim/lid_latch.py"; exec(compile(open(p).read(), p, "exec"))
# 停止:lid_latch_stop()。不要和 crease_hold_ui.py(彈塑性摺痕)同時用。
import os, math
import numpy as np
import omni.usd
from omni.physx import get_physx_interface
from pxr import UsdPhysics

BOX = "/World/Packed/Box"
OPEN_DEG = float(os.environ.get("LID_OPEN_DEG", "25"))   # 滑鼠(力道 100)把上層蓋拉 15 cm 約 37~74°、下層蓋約 29~43°,門檻要低於這些
CLOSE_DEG = float(os.environ.get("LID_CLOSE_DEG", "12"))
OPEN_TARGET = float(os.environ.get("LID_OPEN_TARGET", "170"))
_L = globals().setdefault("_LID_LATCH_STATE", {})


def _qmul(a, b):
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2,
                     w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])
def _qc(q): return np.array([q[0], -q[1], -q[2], -q[3]])


def _setup():
    from isaacsim.core.prims import RigidPrim
    import uuid
    tag = uuid.uuid4().hex[:6]
    lids = RigidPrim(prim_paths_expr=BOX + "/f[xy][pn]", name="latch_lids_" + tag); lids.initialize()
    base = RigidPrim(prim_paths_expr=BOX + "/base", name="latch_base_" + tag); base.initialize()
    order = [str(p).rsplit("/", 1)[-1] for p in lids.prim_paths]
    st = omni.usd.get_context().get_stage()
    drives = {n: UsdPhysics.DriveAPI.Get(st.GetPrimAtPath(BOX + "/crease_" + n), "angular") for n in order}
    # 參考姿態 = 載入時的關閉姿態(USD 預設角 = 關)
    _, qL = [np.array(x, float) for x in lids.get_world_poses()]
    _, qB = [np.array(x, float)[0] for x in base.get_world_poses()]
    rel0 = [_qmul(_qc(qB), qL[i]) for i in range(len(order))]
    _L.update(lids=lids, base=base, order=order, rel0=rel0, drives=drives, open={n: False for n in order})
    print("[lid_latch] 已接上", order, "open>%g° close<%g° target %g°" % (OPEN_DEG, CLOSE_DEG, OPEN_TARGET))


def _angles():
    _, qL = [np.array(x, float) for x in _L["lids"].get_world_poses()]
    _, qB = [np.array(x, float)[0] for x in _L["base"].get_world_poses()]
    out = []
    for i in range(len(_L["order"])):
        rr = _qmul(_qc(_L["rel0"][i]), _qmul(_qc(qB), qL[i]))
        if rr[0] < 0: rr = -rr
        out.append(math.degrees(2*math.atan2(rr[1], rr[0])))     # 繞鉸鏈(蓋子本地 X)的帶號角度
    return out


def _on_step(dt):
    if "lids" not in _L:
        try: _setup()
        except Exception as e:
            print("[lid_latch] 還沒準備好:", e); return
    for n, a in zip(_L["order"], _angles()):
        d = _L["drives"][n]
        if not _L["open"][n] and abs(a) > OPEN_DEG:
            d.GetTargetPositionAttr().Set(math.copysign(OPEN_TARGET, a)); _L["open"][n] = True
            print("[lid_latch] %s 翻開(%.0f°)" % (n, a))
        elif _L["open"][n] and abs(a) < CLOSE_DEG:
            d.GetTargetPositionAttr().Set(0.0); _L["open"][n] = False
            print("[lid_latch] %s 關上(%.0f°)" % (n, a))


def lid_latch_stop():
    _L.pop("sub", None)
    for n, d in _L.get("drives", {}).items(): d.GetTargetPositionAttr().Set(0.0)
    _L.clear(); print("[lid_latch] 已停止(目標角全部歸零)")


def lids_open(): # 程式直接打開四片(先上層 fyp/fyn,再下層)
    for n in ("fyp", "fyn", "fxp", "fxn"):
        a = dict(zip(_L["order"], _angles())).get(n, 0.0) if "lids" in _L else 0.0
        _L["drives"][n].GetTargetPositionAttr().Set(math.copysign(OPEN_TARGET, a if abs(a) > 1 else -1.0)); _L["open"][n] = True
def lids_close():
    for n, d in _L["drives"].items(): d.GetTargetPositionAttr().Set(0.0); _L["open"][n] = False


_L["sub"] = get_physx_interface().subscribe_physics_step_events(_on_step)
print("[lid_latch] 已掛上 physics step;Play 後拉蓋子超過 %g° 會自己翻開並停住。停止:lid_latch_stop()" % OPEN_DEG)
