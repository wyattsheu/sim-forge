#!/bin/bash
# 啟動一個獨立的 Isaac Sim WebRTC 檢視器,載入包好的資產,並開啟滑鼠拖曳。
#
# 刻意不碰既有那個 session:它佔著 49100,這支用 49110。
# 用 full streaming app(不是 headless standalone)—— 因為只有它帶 omni.physx.ui,
# 那是滑鼠拖曳的第一道閘門。
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PORT="${WRAP_FORGE_PORT:-49100}"
PUBLIC_IP="${WRAP_FORGE_IP:-140.96.68.42}"
SIM="$(cd "$HERE/.." && pwd)"
export WRAP_FORGE_USD="${WRAP_FORGE_USD:-$SIM/out/wrapped_mug_on_rig.usd}"

if [ ! -f "$WRAP_FORGE_USD" ]; then
  echo "找不到資產:$WRAP_FORGE_USD" >&2
  echo "先跑:/isaac-sim/python.sh $SIM/forge.py" >&2
  exit 2
fi

if ss -lnt 2>/dev/null | grep -q ":$PORT "; then
  echo "port $PORT 已被佔用 —— 換一個 WRAP_FORGE_PORT,或直接用那個 viewer。" >&2
  exit 3
fi

mkdir -p "$SIM/logs"
LOG="$SIM/logs/viewer.log"

echo "資產   : $WRAP_FORGE_USD"
echo "端點   : $PUBLIC_IP  signaling port $PORT"
echo "記錄檔 : $LOG"

exec /isaac-sim/kit/kit \
  /isaac-sim/apps/isaacsim.exp.full.streaming.kit \
  --no-window \
  --allow-root \
  --/persistent/physics/enableDeformableBeta=true \
  --/physics/updateToUsd=true \
  --/physics/mouseInteractionEnabled=true \
  --/physics/mouseGrab=true \
  --/physics/forceGrab=false \
  --/physics/pickingForce=25.0 \
  --/app/livestream/publicEndpointAddress="$PUBLIC_IP" \
  --/app/livestream/port="$PORT" \
  --/rtx/raytracing/fractionalCutoutOpacity=true \
  --/rtx/pathtracing/fractionalCutoutOpacity=true \
  --/app/window/drawMouse=true \
  --/app/livestream/allowResize=true \
  --/app/livestream/allowDynamicResize=true \
  --exec "$HERE/viewer_boot.py" \
  >> "$LOG" 2>&1
