#!/bin/bash
# 在 Isaac Sim 的 GUI 開場景。用法: ./open_in_ui.sh [usd 路徑](預設 scene_final_phys.usd)
# 包材是 beta surface deformable,Kit 啟動時就要開 enableDeformableBeta,所以一律帶這兩個參數。
# 開好之後會載入 sim/click_to_ros.py:Ctrl + 左鍵點場景 → 座標發佈到 ROS 2 /clicked_point。
HERE=$(cd "$(dirname "$0")" && pwd)
SCENE=${1:-$HERE/scene_final_phys.usd}
export HANDOFF_USD="$(cd "$(dirname "$SCENE")" && pwd)/$(basename "$SCENE")"
export DISPLAY=${DISPLAY:-:1}
export OMNI_KIT_ALLOW_ROOT=1
# ROS 2:用 Isaac 內建的 jazzy 函式庫與 rclpy(python 3.11)。系統的 /opt/ros 是 python 3.12,
# 一起放進 Kit 會互相干擾(rclpy 載入失敗),所以把 /opt/ros 從 PYTHONPATH / LD_LIBRARY_PATH 拿掉。
export ROS_DISTRO=${ROS_DISTRO:-jazzy}
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
ROS_EXT=/isaac-sim/exts/isaacsim.ros2.bridge/$ROS_DISTRO
export PYTHONPATH=$(echo "$PYTHONPATH" | tr ':' '\n' | grep -v '^/opt/ros' | paste -sd: -)
export LD_LIBRARY_PATH=$ROS_EXT/lib:$(echo "$LD_LIBRARY_PATH" | tr ':' '\n' | grep -v '^/opt/ros' | paste -sd: -)
unset AMENT_PREFIX_PATH
export CLICK_TO_ROS=${CLICK_TO_ROS:-1}          # 0 = 不載入 Ctrl+點擊 → ROS 2 座標的功能
export HANDOFF_SIM="$HERE/sim"
echo "開啟 $HANDOFF_USD  (DISPLAY=$DISPLAY, click_to_ros=$CLICK_TO_ROS)"
exec /isaac-sim/isaac-sim.sh \
  --/persistent/physics/enableDeformableBeta=true \
  --/physics/updateToUsd=true \
  --exec "$HERE/sim/ui_boot.py"
