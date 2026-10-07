#!/bin/bash
# 在 Isaac Sim 的 GUI 開場景。用法: ./open_in_ui.sh [usd 路徑]
HERE=$(cd "$(dirname "$0")" && pwd)
SCENE=${1:-$HERE/scene_final_ui.usd}
TMP=$(mktemp /tmp/open_stage_XXXX.py)
printf 'import omni.usd\nomni.usd.get_context().open_stage("%s")\n' "$SCENE" > $TMP
export DISPLAY=${DISPLAY:-:1}
export OMNI_KIT_ALLOW_ROOT=1
echo "開啟 $SCENE  (DISPLAY=$DISPLAY)"
exec /isaac-sim/isaac-sim.sh --exec "$TMP"
