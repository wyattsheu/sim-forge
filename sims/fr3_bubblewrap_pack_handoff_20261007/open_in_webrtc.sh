#!/bin/bash
# 用 WebRTC 串流開場景(遠端用 Isaac Sim WebRTC Streaming Client 連進來看、用滑鼠操作)。
# 做法沿用 sim-forge/sims/wrapped_mug/viewer/start_viewer.sh。
#
#   ./open_in_webrtc.sh                          # 預設 scene_final_phys.usd(包材 / 杯子有物理)
#   ./open_in_webrtc.sh scene_final.usd --crease # 原檔 + 彈塑性摺痕(crease_hold_ui.py)
#   WEBRTC_IP=1.2.3.4 WEBRTC_PORT=49110 ./open_in_webrtc.sh
#   WEBRTC_NO_PLAY=1 ./open_in_webrtc.sh         # 開好不要自動按 Play
#   CLICK_TO_ROS=0 ./open_in_webrtc.sh           # 不載入 Ctrl+點擊 → ROS 2 座標
#
#   ./open_in_webrtc.sh --stop                   # 停止
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENE="$HERE/scene_final_phys.usd"; CREASE=0
PIDF="$HERE/logs/webrtc.pid"
BOOT="$HERE/sim/webrtc_boot.py"
running() { pgrep -f -- "--exec $BOOT" ; }      # 這個資料夾開出來的所有串流實例
if [ "$1" = "--stop" ]; then
  P_=$(running)
  if [ -z "$P_" ]; then echo "沒有在跑"; rm -f "$PIDF"; exit 0; fi
  kill $P_ 2>/dev/null
  echo -n "停止中(pid $(echo $P_ | tr '\n' ' '))"
  for i in $(seq 1 30); do [ -z "$(running)" ] && break; echo -n "."; sleep 1; done   # Kit 要幾秒才會真的結束
  if [ -n "$(running)" ]; then kill -9 $(running) 2>/dev/null; sleep 1; echo -n " 強制結束"; fi
  echo " 已停止"; rm -f "$PIDF"; exit 0
fi
if [ -n "$(running)" ]; then
  echo "已經有串流在跑(pid $(running | tr '\n' ' '))。" >&2
  echo "同時開兩個會互相干擾(client 可能連到另一個、或黑畫面)。先執行:$0 --stop" >&2
  exit 4
fi
for a in "$@"; do
  case "$a" in
    --crease) CREASE=1 ;;
    *) SCENE="$(cd "$(dirname "$a")" && pwd)/$(basename "$a")" ;;
  esac
done
PORT="${WEBRTC_PORT:-49100}"
PUBLIC_IP="${WEBRTC_IP:-140.96.68.42}"
[ -f "$SCENE" ] || { echo "找不到場景:$SCENE" >&2; exit 2; }
if ss -lnt 2>/dev/null | grep -q ":$PORT "; then
  echo "port $PORT 已被佔用 —— 換一個:WEBRTC_PORT=49110 $0 $*" >&2; exit 3
fi
mkdir -p "$HERE/logs"; LOG="$HERE/logs/webrtc.log"
export HANDOFF_USD="$SCENE" HANDOFF_CREASE="$CREASE" HANDOFF_SIM="$HERE/sim" HANDOFF_NO_PLAY="${WEBRTC_NO_PLAY:-0}"
echo "場景   : $SCENE  (摺痕腳本: $([ $CREASE = 1 ] && echo 開 || echo 關))"
echo "連線   : Streaming Client 輸入 $PUBLIC_IP(signaling TCP $PORT、媒體 UDP 47998)"
echo "記錄檔 : $LOG   —— 看到 [handoff] READY 就可以連"
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
nohup /isaac-sim/kit/kit /isaac-sim/apps/isaacsim.exp.full.streaming.kit \
  --no-window --allow-root \
  --/persistent/physics/enableDeformableBeta=true \
  --/physics/updateToUsd=true \
  --/physics/mouseInteractionEnabled=true \
  --/physics/mouseGrab=true \
  --/physics/forceGrab=false \
  --/physics/pickingForce=25.0 \
  --/app/livestream/publicEndpointAddress="$PUBLIC_IP" \
  --/app/livestream/port="$PORT" \
  --/app/window/drawMouse=true \
  --/app/livestream/allowResize=true \
  --/app/livestream/allowDynamicResize=true \
  --exec "$BOOT" \
  > "$LOG" 2>&1 &
echo $! > "$PIDF"
echo "pid    : $!(停止:$0 --stop)"
