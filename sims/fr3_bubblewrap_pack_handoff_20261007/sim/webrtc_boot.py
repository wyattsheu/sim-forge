# -*- coding: utf-8 -*-
"""open_in_webrtc.sh 用的開機腳本(kit --exec 帶起來):開場景 → 視角 → 滑鼠拖曳 → Play。
沿用 sim-forge/sims/wrapped_mug/viewer/viewer_boot.py 的做法。

滑鼠拖曳要成立,要同時滿足 omni.physx.ui 的四個條件:
  1. omni.physx.ui 在跑且持有 viewport overlay  ← 要用 full streaming app,headless standalone 沒有
  2. timeline 正在播放                          ← 這裡自動按 Play(HANDOFF_NO_PLAY=1 可以關掉)
  3. 按住 Shift(除非狀態設成 ENABLED)           ← 這裡設成 ENABLED,左鍵直接拖
  4. 沒有其他 gesture / hover 佔住游標           ← 開檔後先清掉選取,gizmo 才不會擋住
"""
import os
import carb
import omni.kit.app
import omni.timeline
import omni.usd

USD = os.environ["HANDOFF_USD"]
CREASE = os.environ.get("HANDOFF_CREASE", "0") == "1"
CREASE_MODE = CREASE
SIM = os.environ.get("HANDOFF_SIM", "")
NO_PLAY = os.environ.get("HANDOFF_NO_PLAY", "0") == "1"
DELAY = 180
_s = {"f": 0, "opened": False, "done": False}
_st = carb.settings.get_settings()


def _log(m):
    carb.log_warn("[handoff] " + m)
    print("[handoff] " + m, flush=True)   # 也印到 stdout,open_in_webrtc.sh 的 logs/webrtc.log 才看得到 READY
_hlog = _log      # kept: click_to_ros.py etc. are exec'd into these globals and redefine _log


def _mouse_drag():
    _st.set_bool("/physics/mouseInteractionEnabled", True)
    _st.set_bool("/physics/mouseGrab", True)
    _st.set_bool("/physics/mouseGrabIgnoreInvisible", True)
    # 2026-10-07 實測(sim/sweep 掃描):forceGrab=False(關節式)不管 pickingForce 多大,拖 15 cm 只動 1.4 cm;
    # forceGrab=True + pickingForce=100 拖 15 cm 動 14.5 cm、不傾斜,但抓箱壁往上提會翻箱;70 提起來只翹 26° 不翻。所以用力量式 70。
    _st.set_bool("/physics/forceGrab", True)
    _st.set_float("/physics/pickingForce", float(os.environ.get("MOUSE_PICKING_FORCE", "70")))
    try:
        from omni.physxui.scripts.extension import get_physicsui_instance
        from omni.physxui.scripts.physxViewportOverlays import PhysxUIMouseInteraction
        inst = get_physicsui_instance()
        if inst is not None:
            inst.mouse_interaction_override_toggle(PhysxUIMouseInteraction.ENABLED)
            return True
    except Exception as e:
        _log("no-Shift dragging unavailable, use Shift + left-drag: %s" % e)
    return False


def _camera():
    try:
        from omni.kit.viewport.utility import get_active_viewport
        from pxr import UsdGeom, Gf
        vp = get_active_viewport(); st = omni.usd.get_context().get_stage()
        if vp is None or st is None:
            return
        if not st.GetPrimAtPath("/World/ViewCam"):
            c = UsdGeom.Camera.Define(st, "/World/ViewCam")
            c.CreateFocalLengthAttr(26.0)
            c.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
            m = Gf.Matrix4d().SetLookAt(Gf.Vec3d(0.62, -0.62, 0.52), Gf.Vec3d(-0.02, 0.0, 0.08),
                                        Gf.Vec3d(0, 0, 1)).GetInverse()
            UsdGeom.Xformable(c).MakeMatrixXform().Set(m)
        vp.camera_path = "/World/ViewCam"
    except Exception as e:
        _log("camera switch skipped: %s" % e)


def _on_update(_e):
    _s["f"] += 1; f = _s["f"]
    if _s["done"]:
        return
    if f in (30, 90, 150) and not _s["opened"]:
        _log("opening " + USD)
        try:
            omni.usd.get_context().open_stage(USD)
            st = omni.usd.get_context().get_stage()
            n = len(list(st.Traverse())) if st else 0
            if st:
                st.SetTimeCodesPerSecond(60.0); st.SetStartTimeCode(0.0); st.SetEndTimeCode(1000000.0)
            omni.usd.get_context().get_selection().clear_selected_prim_paths()
            _s["opened"] = n > 10
            _log("open_stage prims=%d" % n)
        except Exception as e:
            _log("open_stage FAILED: %s" % e)
    elif f == DELAY and _s["opened"]:
        _camera()
        _s["no_shift"] = _mouse_drag()
        if CREASE:
            p = os.path.join(SIM, "crease_hold_ui.py")
            exec(compile(open(p).read(), p, "exec"), globals())
            _log("crease_hold_ui.py loaded (crease torque + solver fix)")
    elif f == DELAY + 60 and _s["opened"]:
        tl = omni.timeline.get_timeline_interface()
        tl.set_start_time(0.0); tl.set_end_time(100000.0); tl.set_looping(True)
        if not NO_PLAY:
            tl.play()
        hint = "left-drag" if _s.get("no_shift") else "Shift + left-drag"
        _log("READY -- %s the carton / lids (pickingForce=%s); %s" % (hint, _st.get("/physics/pickingForce"), "Play NOT pressed (HANDOFF_NO_PLAY=1)" if NO_PLAY else "Play pressed"))
        if os.environ.get("CLICK_TO_ROS", "1") == "1":
            p = os.path.join(SIM, "click_to_ros.py")
            try:
                exec(compile(open(p).read(), p, "exec"), globals())
            except Exception as e:
                _log("click_to_ros.py failed to load: %s" % e)
        # flap model: plastic = elastic-plastic crease (default, docs/CREASE_MECHANICS.md); latch = old open/shut
        # latch; spring = USD drive only (LID_LATCH=0 also means spring, for old command lines)
        lid_mode = os.environ.get("LID_MODE", "spring" if os.environ.get("LID_LATCH", "1") == "0" else "plastic")
        if not CREASE_MODE and lid_mode in ("plastic", "latch"):
            p = os.path.join(SIM, "crease_plastic.py" if lid_mode == "plastic" else "lid_latch.py")
            try:
                exec(compile(open(p).read(), p, "exec"), globals())
                _hlog("flap model: %s (%s)" % (lid_mode, os.path.basename(p)))
            except Exception as e:
                _hlog("%s failed to load: %s" % (os.path.basename(p), e))
        _s["done"] = True


_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(_on_update, name="handoff_boot")
_log("boot script armed")
