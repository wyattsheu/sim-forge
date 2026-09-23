# -*- coding: utf-8 -*-
"""在 streaming Kit 內開場、開滑鼠拖曳、按播放。由 kit --exec 帶起來。

拖曳要成立必須同時滿足 omni.physx.ui 的四道閘門:
  1. omni.physx.ui 有在跑且持有 viewport overlay  <- full streaming app 才有
  2. timeline 正在播放                            <- 這裡自動按 Play
  3. 全程按住 Shift(除非狀態被設成 ENABLED)      <- 這裡設 ENABLED,左鍵直接拉
  4. 沒有其他 gesture / hover 佔用游標            <- 先點空白處取消選取即可
"""
import os
import carb
import omni.kit.app
import omni.timeline
import omni.usd

_SIM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USD = os.environ.get("WRAP_FORGE_USD", os.path.join(_SIM, "out", "wrapped_mug_on_rig.usd"))
DELAY_FRAMES = int(os.environ.get("WRAP_FORGE_BOOT_FRAMES", "180"))

_state = {"frame": 0, "opened": False, "done": False}
_st = carb.settings.get_settings()


def _apply_mouse_drag():
    _st.set_bool("/physics/mouseInteractionEnabled", True)
    _st.set_bool("/physics/mouseGrab", True)
    _st.set_bool("/physics/mouseGrabIgnoreInvisible", True)
    _st.set_bool("/physics/forceGrab", False)          # 約束式拖曳,不受 pickingForce 縮放影響
    _st.set_float("/physics/pickingForce", 25.0)
    ok = False
    try:
        # 注意是 get_physicsui_instance(physics),不是 physxui
        from omni.physxui.scripts.extension import get_physicsui_instance
        from omni.physxui.scripts.physxViewportOverlays import PhysxUIMouseInteraction
        inst = get_physicsui_instance()
        if inst is not None:
            inst.mouse_interaction_override_toggle(PhysxUIMouseInteraction.ENABLED)
            ov = getattr(inst, "_viewport_overlays", None)
            ok = ov is not None and ov._mouse_interaction_state == PhysxUIMouseInteraction.ENABLED
            carb.log_warn(f"[wrap-forge] mouse_interaction_state = "
                          f"{ov._mouse_interaction_state if ov else 'no overlay'}")
        else:
            carb.log_warn("[wrap-forge] omni.physx.ui extension instance is None (還沒載入?)")
    except Exception as e:
        carb.log_warn(f"[wrap-forge] no-shift override unavailable: {e}")
    carb.log_warn(f"[wrap-forge] mouse drag ready (no_shift={ok}, joint-drag, pickingForce=25)")
    return ok


def _look_through_viewcam():
    try:
        from omni.kit.viewport.utility import get_active_viewport
        vp = get_active_viewport()
        stage = omni.usd.get_context().get_stage()
        if vp is None:
            carb.log_warn("[wrap-forge] no active viewport!")
            return
        if stage and not stage.GetPrimAtPath("/World/ViewCam"):
            from pxr import UsdGeom, Gf
            c = UsdGeom.Camera.Define(stage, "/World/ViewCam")
            c.CreateFocalLengthAttr(26.0)
            c.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
            m = Gf.Matrix4d().SetLookAt(Gf.Vec3d(0.62, -0.62, 0.52), Gf.Vec3d(-0.02, 0.0, 0.07),
                                        Gf.Vec3d(0, 0, 1)).GetInverse()
            UsdGeom.Xformable(c).MakeMatrixXform().Set(m)
        if stage and stage.GetPrimAtPath("/World/ViewCam"):
            vp.camera_path = "/World/ViewCam"
            carb.log_warn(f"[wrap-forge] viewport camera -> {vp.camera_path} (res {vp.resolution})")
    except Exception as e:
        carb.log_warn(f"[wrap-forge] camera switch skipped: {e}")


def _watchdog():
    tl = omni.timeline.get_timeline_interface()
    playing = tl.is_playing()
    if not playing:
        tl.play()
        carb.log_warn("[wrap-forge] watchdog: timeline had stopped -> replayed")
    if _state["frame"] % 1800 == 0:
        carb.log_warn(f"[wrap-forge] heartbeat t={tl.get_current_time():.1f}s playing={tl.is_playing()}")


def _on_update(_e):
    if _state["done"]:
        _state["frame"] += 1
        if _state["frame"] % 300 == 0:
            _watchdog()
        return
    _state["frame"] += 1
    f = _state["frame"]
    if f in (30, 90, 150) and not _state["opened"]:
        carb.log_warn(f"[wrap-forge] opening {USD}")
        try:
            ok = omni.usd.get_context().open_stage(USD)
            st = omni.usd.get_context().get_stage()
            n = len(list(st.Traverse())) if st else 0
            root = st.GetRootLayer().identifier if st else "?"
            carb.log_warn(f"[wrap-forge] open_stage -> {ok}, prims={n}, layer={root}")
            if st:
                # 保險:就算 USD 裡的 endTimeCode 是 0 也要能持續播放
                st.SetTimeCodesPerSecond(60.0)
                st.SetStartTimeCode(0.0)
                st.SetEndTimeCode(1000000.0)
                carb.log_warn(f"[wrap-forge] timecodes -> {st.GetStartTimeCode()}..{st.GetEndTimeCode()}")
            omni.usd.get_context().get_selection().clear_selected_prim_paths()  # 閘門 4:別讓 gizmo 佔住游標
            _state["opened"] = n > 10
        except Exception as e:
            carb.log_warn(f"[wrap-forge] open_stage FAILED: {e}")
    elif f in (DELAY_FRAMES, DELAY_FRAMES + 120, DELAY_FRAMES + 300):
        _look_through_viewcam()
        _state["no_shift"] = _apply_mouse_drag()
    elif f == DELAY_FRAMES + 360:
        tl = omni.timeline.get_timeline_interface()
        tl.set_start_time(0.0)
        tl.set_end_time(100000.0)
        tl.set_looping(True)
        tl.play()
        carb.log_warn(f"[wrap-forge] play() -> is_playing={tl.is_playing()} "
                      f"range={tl.get_start_time()}..{tl.get_end_time()}")
        hint = "左鍵直接拖曳" if _state.get("no_shift") else "按住 Shift + 左鍵拖曳"
        carb.log_warn(f"[wrap-forge] READY — {hint}紙箱耳朵 / 馬克杯 / 泡泡紙")
        _state["done"] = True


_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
    _on_update, name="wrap_forge_boot")
carb.log_warn("[wrap-forge] boot script armed")
