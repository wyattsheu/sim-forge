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
#   ./open_in_webrtc.sh --check                  # 只印偵測結果(Isaac Sim 在哪、IP、port、GPU),不啟動
#   ./open_in_webrtc.sh --stop                   # 停止
#
# Isaac Sim 位置自動偵測(二進位版 / Docker / pip 版),見 sim/find_isaac.sh;偵測不到時指定:
#   ISAAC_SIM_PATH=<含 kit/kit 的目錄>  或  ISAAC_SIM_PIP_ENV=<含 bin/isaacsim 的 venv>
# WEBRTC_IP 沒設就用本機第一個非內網 IP;port 被佔用會自動往上找空的(WEBRTC_PORT 可指定起點)。
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
CHECK=0
for a in "$@"; do
  case "$a" in
    --check) CHECK=1 ;;
    --crease) CREASE=1 ;;
    *) SCENE="$(cd "$(dirname "$a")" && pwd)/$(basename "$a")" ;;
  esac
done
source "$HERE/sim/find_isaac.sh"
find_isaac || exit 5
isaac_kit_cmd stream
[ -f "$SCENE" ] || { echo "找不到場景:$SCENE" >&2; exit 2; }
PORT="${WEBRTC_PORT:-49100}"
if [ -z "${WEBRTC_PORT:-}" ]; then      # 沒指定就找第一個沒被佔用的
  for _ in $(seq 1 20); do ss -lnt 2>/dev/null | grep -q ":$PORT " || break; PORT=$((PORT+1)); done
fi
if ss -lnt 2>/dev/null | grep -q ":$PORT "; then
  echo "port $PORT 已被佔用 —— 換一個:WEBRTC_PORT=49110 $0 $*" >&2; exit 3
fi
# 對外 IP:優先 WEBRTC_IP;否則取本機第一個非內網、非 docker 的 IPv4(內網 / VPN 環境請自己設 WEBRTC_IP)
if [ -n "${WEBRTC_IP:-}" ]; then PUBLIC_IP="$WEBRTC_IP"
else
  PUBLIC_IP=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' \
    | grep -vE '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|127\.|169\.254\.)' | head -1)
  [ -n "$PUBLIC_IP" ] || PUBLIC_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  echo "IP     : 沒設 WEBRTC_IP,自動用 $PUBLIC_IP(不對的話:WEBRTC_IP=<client 連得到的 IP> $0)"
fi
if [ "$CHECK" = 1 ]; then
  echo "Isaac  : $ISAAC_KIND  $ISAAC_HOME"; echo "啟動   : ${KIT_CMD[*]}"
  echo "場景   : $SCENE"; echo "連線   : $PUBLIC_IP  signaling TCP $PORT / 媒體 UDP 47998"
  nvidia-smi --query-gpu=index,name,memory.free --format=csv,noheader 2>/dev/null | sed 's/^/GPU    : /'
  ss -lnu 2>/dev/null | grep -q ":47998 " && echo "警告   : UDP 47998 已被佔用(別的串流在跑?)"
  exit 0
fi
mkdir -p "$HERE/logs"; LOG="$HERE/logs/webrtc.log"
export HANDOFF_USD="$SCENE" HANDOFF_CREASE="$CREASE" HANDOFF_SIM="$HERE/sim" HANDOFF_NO_PLAY="${WEBRTC_NO_PLAY:-0}"
echo "Isaac  : $ISAAC_KIND  $ISAAC_HOME"
echo "場景   : $SCENE  (摺痕腳本: $([ $CREASE = 1 ] && echo 開 || echo 關))"
echo "連線   : Streaming Client 輸入 $PUBLIC_IP(signaling TCP $PORT、媒體 UDP 47998)"
echo "記錄檔 : $LOG   —— 看到 [handoff] READY 就可以連"
[ "$(id -u)" = 0 ] && export OMNI_KIT_ALLOW_ROOT=1
isaac_setup_ros
export HANDOFF_SIM="$HERE/sim"
nohup "${KIT_CMD[@]}" \
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
