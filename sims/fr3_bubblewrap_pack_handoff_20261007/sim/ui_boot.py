# ui_boot.py — open_in_ui.sh 用的開機腳本(kit --exec):開場景,然後載入 click_to_ros.py(Ctrl+點擊 → ROS 2 座標)。
import os, carb, omni.kit.app, omni.usd
USD = os.environ["HANDOFF_USD"]; SIM = os.environ.get("HANDOFF_SIM", os.path.dirname(os.path.abspath(__file__)))
CLICK = os.environ.get("CLICK_TO_ROS", "1") == "1"
CREASE_MODE = False
_s = {"f": 0, "opened": -1, "done": False}


def _log(m): carb.log_warn("[handoff] " + m)


def _on_update(_e):
    _s["f"] += 1; f = _s["f"]
    if _s["done"]: return
    if f == 30:
        omni.usd.get_context().open_stage(USD); _s["opened"] = f
        _log("opening " + USD)
    elif _s["opened"] > 0 and f == _s["opened"] + 150:
        # 滑鼠拖曳:力量式 + 100(見 webrtc_boot.py 的實測);免按 Shift
        st = carb.settings.get_settings()
        st.set_bool("/physics/mouseInteractionEnabled", True); st.set_bool("/physics/mouseGrab", True)
        st.set_bool("/physics/mouseGrabIgnoreInvisible", True); st.set_bool("/physics/forceGrab", True)
        st.set_float("/physics/pickingForce", float(os.environ.get("MOUSE_PICKING_FORCE", "70")))
        try:
            from omni.physxui.scripts.extension import get_physicsui_instance
            from omni.physxui.scripts.physxViewportOverlays import PhysxUIMouseInteraction
            inst = get_physicsui_instance()
            if inst is not None:
                inst.mouse_interaction_override_toggle(PhysxUIMouseInteraction.ENABLED); _log("mouse dragging without Shift")
        except Exception as e:
            _log("could not enable no-Shift dragging (use Shift + left-drag): %s" % e)
        if CLICK:
            p = os.path.join(SIM, "click_to_ros.py")
            try:
                exec(compile(open(p).read(), p, "exec"), globals())
            except Exception as e:
                _log("click_to_ros.py failed to load: %s" % e)
        if os.environ.get("LID_LATCH", "1") == "1" and not CREASE_MODE:
            p = os.path.join(SIM, "lid_latch.py")
            try:
                exec(compile(open(p).read(), p, "exec"), globals())
            except Exception as e:
                _log("lid_latch.py failed to load: %s" % e)
        _log("READY"); _s["done"] = True


_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(_on_update, name="handoff_ui_boot")
