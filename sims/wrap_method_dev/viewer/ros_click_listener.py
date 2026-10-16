#!/usr/bin/env python3
"""ros_click_listener.py — 接收 Isaac 裡 Ctrl+點擊發佈的座標(學長那邊的範例)。

  source /opt/ros/jazzy/setup.bash
  python3 ros_click_listener.py            # 印出每一次點擊;也可以直接 ros2 topic echo /clicked_point

訊息:geometry_msgs/msg/PointStamped,header.frame_id = "world"(Isaac 世界座標,Z-up,公尺)。
QoS 是 transient_local,所以啟動後會先收到最後一次點的點。
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from geometry_msgs.msg import PointStamped
from std_msgs.msg import String


class ClickListener(Node):
    def __init__(self):
        super().__init__("click_listener")
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(PointStamped, "/clicked_point", self.on_point, qos)
        self.create_subscription(String, "/clicked_prim", self.on_prim, qos)
        self.get_logger().info("waiting for /clicked_point ...")

    def on_point(self, m: PointStamped):
        self.get_logger().info("point  frame=%s  x=%.4f y=%.4f z=%.4f  (m)" % (m.header.frame_id, m.point.x, m.point.y, m.point.z))
        # ← 在這裡把 (x, y, z) 交給手臂的運動規劃

    def on_prim(self, m: String):
        self.get_logger().info("prim   %s" % m.data)


def main():
    rclpy.init()
    n = ClickListener()
    try:
        rclpy.spin(n)
    except KeyboardInterrupt:
        pass
    n.destroy_node(); rclpy.shutdown()


if __name__ == "__main__":
    main()
