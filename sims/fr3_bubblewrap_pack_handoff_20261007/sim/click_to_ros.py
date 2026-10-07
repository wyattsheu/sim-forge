# click_to_ros.py — 在 Isaac Sim UI(本機視窗或 WebRTC)裡 **Ctrl + 左鍵** 點場景的任何地方,
# 把點到的 3D 世界座標用 ROS 2 發佈出去,給手臂當目標點。
#
#   topic   /clicked_point   geometry_msgs/msg/PointStamped   header.frame_id = "world"(Isaac 世界座標,Z-up,公尺)
#   topic   /clicked_prim    std_msgs/msg/String              點到的 prim 路徑(例如 /World/Packed/Box/fyp/geo)
#   QoS     reliable、transient_local、depth 1 → 後來才訂閱的節點也會立刻拿到最後一次點的點
#
# 執行方式:
#   - open_in_ui.sh / open_in_webrtc.sh 會自動載入(環境變數 CLICK_TO_ROS=0 可以關掉)
#   - 或在 Script Editor:p="/path/to/sim/click_to_ros.py"; exec(compile(open(p).read(), p, "exec"))
#   - 停止:click_to_ros_stop()
# 可調:環境變數 CLICK_TOPIC(預設 /clicked_point)、CLICK_FRAME(world)、CLICK_MODIFIER(ctrl | alt | none)
#
# 接收端(學長那邊,任何有 ROS 2 jazzy 的機器,同一個 ROS_DOMAIN_ID):
#   ros2 topic echo /clicked_point
#   或 python:見 sim/ros_click_listener.py
import os, sys, math
import carb, carb.input
import omni.kit.app, omni.usd, omni.ui as ui, omni.appwindow
from omni.ui import scene as sc
from omni.kit.viewport.utility import get_active_viewport_window
from pxr import UsdGeom, Gf, Sdf, UsdShade

TOPIC = os.environ.get("CLICK_TOPIC", "/clicked_point")
PRIM_TOPIC = os.environ.get("CLICK_PRIM_TOPIC", "/clicked_prim")
FRAME = os.environ.get("CLICK_FRAME", "world")
MODIFIER = os.environ.get("CLICK_MODIFIER", "ctrl").lower()      # ctrl | alt | none
MARKER = "/World/ClickMarker"
_S = globals().setdefault("_CLICK_TO_ROS_STATE", {})


def _log(m):
    carb.log_warn("[click_to_ros] " + m)
    print("[click_to_ros] " + m, flush=True)


# ---------------------------------------------------------------- ROS 2
def _ros_init():
    """在 Kit 裡載入 rclpy。優先用已經在 sys.path 上的(ros2 bridge extension 載入過的),
    否則用 Isaac 內建的 jazzy/humble rclpy;並把系統 /opt/ros 的 python 路徑拿掉(python 版本不同會互相干擾)。"""
    distro = os.environ.get("ROS_DISTRO", "jazzy")
    ext_rclpy = "/isaac-sim/exts/isaacsim.ros2.bridge/%s/rclpy" % distro
    sys.path[:] = [p for p in sys.path if not p.startswith("/opt/ros")]
    try:
        import rclpy  # noqa
    except Exception:
        if os.path.isdir(ext_rclpy) and ext_rclpy not in sys.path:
            sys.path.insert(0, ext_rclpy)
        import rclpy  # noqa
    import rclpy
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
    from geometry_msgs.msg import PointStamped
    from std_msgs.msg import String
    if not rclpy.ok():
        rclpy.init(args=None)
    node = rclpy.create_node("isaac_click_publisher")
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                     durability=DurabilityPolicy.TRANSIENT_LOCAL, history=HistoryPolicy.KEEP_LAST)
    _S["rclpy"] = rclpy; _S["node"] = node
    _S["pub"] = node.create_publisher(PointStamped, TOPIC, qos)
    _S["pub_prim"] = node.create_publisher(String, PRIM_TOPIC, qos)
    _S["PointStamped"] = PointStamped; _S["String"] = String
    _log("ROS 2 ready: %s (geometry_msgs/PointStamped, frame_id=%s), %s (std_msgs/String); rclpy=%s"
         % (TOPIC, FRAME, PRIM_TOPIC, rclpy.__file__))


def _publish(pos, prim_path):
    node = _S["node"]
    m = _S["PointStamped"]()
    m.header.stamp = node.get_clock().now().to_msg()
    m.header.frame_id = FRAME
    m.point.x, m.point.y, m.point.z = float(pos[0]), float(pos[1]), float(pos[2])
    _S["pub"].publish(m)
    s = _S["String"](); s.data = str(prim_path); _S["pub_prim"].publish(s)
    _S["n"] = _S.get("n", 0) + 1
    _S["last"] = (float(pos[0]), float(pos[1]), float(pos[2]), str(prim_path))


# ---------------------------------------------------------------- 標記球
def _marker(pos):
    st = omni.usd.get_context().get_stage()
    if st is None:
        return
    if not st.GetPrimAtPath(MARKER).IsValid():
        sp = UsdGeom.Sphere.Define(st, MARKER); sp.CreateRadiusAttr(0.006)
        sp.GetPrim().CreateAttribute("primvars:displayColor", Sdf.ValueTypeNames.Color3fArray).Set([Gf.Vec3f(1.0, 0.1, 0.1)])
        UsdGeom.Xformable(sp).AddTranslateOp()
    xf = UsdGeom.Xformable(st.GetPrimAtPath(MARKER))
    ops = xf.GetOrderedXformOps()
    (ops[0] if ops else xf.AddTranslateOp()).Set(Gf.Vec3d(float(pos[0]), float(pos[1]), float(pos[2])))


# ---------------------------------------------------------------- 滑鼠
class _Pass(sc.GestureManager):               # 不要搶走 viewport 原本的選取 / 物理拖曳手勢
    def can_be_prevented(self, gesture): return False
    def should_prevent(self, gesture, preventer): return False


def _modifier_down():
    if MODIFIER == "none":
        return True
    inp = carb.input.acquire_input_interface(); kb = omni.appwindow.get_default_app_window().get_keyboard()
    K = carb.input.KeyboardInput
    keys = (K.LEFT_CONTROL, K.RIGHT_CONTROL) if MODIFIER == "ctrl" else (K.LEFT_ALT, K.RIGHT_ALT)
    return any(inp.get_keyboard_value(kb, k) for k in keys)


def _on_query(prim_path, world_pos, *rest):
    if not prim_path or world_pos is None:
        _log("點到空的地方(沒有物件),不發佈"); return
    _publish(world_pos, prim_path); _marker(world_pos)
    _log("#%d  %s  →  (%.4f, %.4f, %.4f) m  已發佈到 %s" % (_S["n"], prim_path, world_pos[0], world_pos[1], world_pos[2], TOPIC))


def _on_click(sender):
    if not _modifier_down():
        return
    vw = _S.get("vw")
    if vw is None:
        return
    ndc = sender.gesture_payload.mouse                 # -1..1
    W, H = vw.viewport_api.resolution
    px = int((ndc[0] + 1.0) * 0.5 * W); py = int((1.0 - ndc[1]) * 0.5 * H)
    vw.viewport_api.request_query((px, py), _on_query, query_name="click_to_ros")


def click_to_ros_start():
    if _S.get("frame") is not None:
        _log("已經在執行"); return
    vw = get_active_viewport_window()
    if vw is None:
        _log("找不到 viewport 視窗(headless?),無法接滑鼠"); return
    _ros_init()
    _S["vw"] = vw
    frame = vw.get_frame("handoff.click_to_ros.frame")
    with frame:
        sv = sc.SceneView(); vw.viewport_api.add_scene_view(sv)
        with sv.scene:
            sc.Screen(gesture=[sc.ClickGesture(_on_click, manager=_Pass())])
    _S["frame"] = frame; _S["sv"] = sv
    mod = {"ctrl": "Ctrl + 左鍵", "alt": "Alt + 左鍵", "none": "左鍵"}.get(MODIFIER, MODIFIER)
    _log("READY —— 在 viewport 裡 %s 點任何物件,座標會發佈到 %s(frame_id=%s)" % (mod, TOPIC, FRAME))


def click_to_ros_stop():
    sv = _S.pop("sv", None); vw = _S.pop("vw", None); fr = _S.pop("frame", None)
    try:
        if sv is not None and vw is not None: vw.viewport_api.remove_scene_view(sv)
        if fr is not None: fr.clear()
    except Exception as e:
        _log("清除 viewport 疊層時出錯:%s" % e)
    node = _S.pop("node", None)
    if node is not None:
        node.destroy_node()
    for k in ("pub", "pub_prim"): _S.pop(k, None)
    _log("已停止")


if os.environ.get("CLICK_TO_ROS_AUTOSTART", "1") == "1":
    click_to_ros_start()
