#!/usr/bin/env python3
"""live_run.py — 用 WebRTC 即時看包裝模擬(包裝腳本本身不用改)。

    $ISAAC_PYTHON live_run.py <腳本.py> [腳本參數...]
    例:cd volume && $ISAAC_PYTHON ../viewer/live_run.py wrap_vol.py --sheet_mm 500 --until box --out out_live

一般由 ../run_wrap.sh --live 呼叫,不用自己打。

做法:wrap_vol.py / wrap_sim.py 都是 `from isaacsim import SimulationApp; SimulationApp({"headless": True})`。
這支在執行它們之前把 isaacsim.SimulationApp 換成子類別,建好 app 之後:
  1. 開 WebRTC 串流(omni.kit.livestream.app;Isaac Sim 5.x 退回 omni.kit.livestream.webrtc)
  2. 腳本建出 /World/cam 之後,把 viewport 切到那台相機(跟輸出影片同一個視角)
  3. 腳本跑完呼叫 close() 時,若 LIVE_HOLD=1(預設)就暫停物理、繼續串流最後的畫面,直到被 kill / Ctrl+C

環境變數(run_wrap.sh 會設):
  LIVE_IP     給 client 連的 IP(publicIp)
  LIVE_PORT   signaling TCP port(預設 49100)
  LIVE_MEDIA  media UDP port(預設 47998)
  LIVE_HOLD   1 = 跑完停在最後畫面繼續串流;0 = 跑完就關
  LIVE_CAM    viewport 要切到的相機 prim(預設 /World/cam;空字串 = 不切)
"""
import os, sys, runpy, signal, time

if len(sys.argv) < 2:
    raise SystemExit(__doc__)
SCRIPT = os.path.abspath(sys.argv[1])
IP = os.environ.get("LIVE_IP", "")
PORT = int(os.environ.get("LIVE_PORT", "49100"))
MEDIA = int(os.environ.get("LIVE_MEDIA", "47998"))
HOLD = os.environ.get("LIVE_HOLD", "1") == "1"
CAM = os.environ.get("LIVE_CAM", "/World/cam")


def _log(m):
    print("[live] " + m, flush=True)


import isaacsim
_Base = isaacsim.SimulationApp


class LiveSimulationApp(_Base):
    def __init__(self, launch_config=None, experience=""):
        cfg = dict(launch_config or {})
        cfg.setdefault("headless", True)
        cfg["hide_ui"] = False                      # 串流的是整個 app 視窗;藏 UI 會只剩黑畫面
        cfg.setdefault("width", 1280); cfg.setdefault("height", 720)
        super().__init__(cfg, experience)
        import carb
        from isaacsim.core.utils.extensions import enable_extension
        st = carb.settings.get_settings()
        st.set("/app/window/drawMouse", True)
        st.set("/app/livestream/port", PORT)                                   # 5.x 的設定名
        st.set("/exts/omni.kit.livestream.app/primaryStream/signalPort", PORT)  # 6.x
        st.set("/exts/omni.kit.livestream.app/primaryStream/streamPort", MEDIA)
        if IP:
            st.set("/app/livestream/publicEndpointAddress", IP)
            st.set("/exts/omni.kit.livestream.app/primaryStream/publicIp", IP)
        ok = False
        for ext in ("omni.kit.livestream.app", "omni.kit.livestream.webrtc"):
            try:
                ok = bool(enable_extension(ext))
            except Exception as e:
                _log("enable %s failed: %s" % (ext, e))
            if ok:
                _log("stream extension: %s" % ext); break
        for _ in range(10):
            self.update()
        _log("STREAMING -- connect the WebRTC Streaming Client to %s (signaling TCP %d, media UDP %d)"
             % (IP or "<this host>", PORT, MEDIA))
        self._cam_done = not CAM
        import omni.kit.app
        self._live_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
            self._live_tick, name="live_run")

    def _live_tick(self, _e):
        if self._cam_done:
            return
        try:
            import omni.usd
            stage = omni.usd.get_context().get_stage()
            if stage is None or not stage.GetPrimAtPath(CAM).IsValid():
                return
            from omni.kit.viewport.utility import get_active_viewport
            vp = get_active_viewport()
            if vp is not None:
                vp.camera_path = CAM
                _log("viewport camera -> %s" % CAM)
        except Exception as e:
            _log("viewport camera not switched: %s" % e)
        self._cam_done = True

    def close(self, *args, **kwargs):
        if HOLD and not getattr(self, "_holding", False):
            self._holding = True
            try:
                import omni.timeline
                omni.timeline.get_timeline_interface().pause()
            except Exception:
                pass
            _log("SIMULATION DONE -- physics paused, still streaming the last frame. "
                 "Stop with: ../run_wrap.sh --stop (or Ctrl+C)")
            stop = {"v": False}
            signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("v", True))
            try:
                while not stop["v"] and self.is_running():
                    self.update(); time.sleep(1 / 30)
            except KeyboardInterrupt:
                pass
        return super().close(*args, **kwargs)


isaacsim.SimulationApp = LiveSimulationApp
try:                                     # 有些腳本從子模組 import
    import isaacsim.simulation_app as _sa
    _sa.SimulationApp = LiveSimulationApp
except Exception:
    pass

sys.argv = [SCRIPT] + sys.argv[2:]
os.chdir(os.path.dirname(SCRIPT))       # 包裝腳本都假設在自己的資料夾裡執行
_log("running %s %s" % (os.path.basename(SCRIPT), " ".join(sys.argv[1:])))
try:
    runpy.run_path(SCRIPT, run_name="__main__")
except SystemExit as e:
    if e.code not in (None, 0):
        HOLD = False; _log("script exited with %s -- stream closed" % e.code)
    raise
except BaseException:
    HOLD = False                         # 腳本出錯就不要停在畫面上,直接結束(錯誤在上面的 traceback)
    import traceback; traceback.print_exc()
    _log("SCRIPT FAILED -- stream closed")
    sys.exit(1)
