#!/bin/bash
# 在本機 Isaac Sim 的 GUI 開場景(需要螢幕 / DISPLAY)。用法: ./open_in_ui.sh [usd 路徑]
# 預設:交付包的 scene_final_phys.usd。從交付包複製,只改了路徑。
# 包材是 beta surface deformable,Kit 啟動時就要開 enableDeformableBeta,所以一律帶這兩個參數。
# 開好之後會載入 viewer/click_to_ros.py:Ctrl + 左鍵點場景 → 座標發佈到 ROS 2 /clicked_point。
HERE=$(cd "$(dirname "$0")" && pwd)
SCENE=${1:-$HERE/../fr3_bubblewrap_pack_surface_handoff_20261007/scene_final_phys.usd}
export HANDOFF_USD="$(cd "$(dirname "$SCENE")" && pwd)/$(basename "$SCENE")"
export DISPLAY=${DISPLAY:-:1}
[ "$(id -u)" = 0 ] && export OMNI_KIT_ALLOW_ROOT=1
source "$HERE/find_isaac.sh"
find_isaac || exit 5
isaac_kit_cmd ui
isaac_setup_ros
export HANDOFF_SIM="$HERE/viewer" WRAPDEV_CARTON_DIR="$HERE/carton"
echo "Opening $HANDOFF_USD  (DISPLAY=$DISPLAY, click_to_ros=$CLICK_TO_ROS, Isaac Sim: $ISAAC_KIND $ISAAC_HOME)"
exec "${KIT_CMD[@]}" \
  --/persistent/physics/enableDeformableBeta=true \
  --/physics/updateToUsd=true \
  --exec "$HERE/viewer/ui_boot.py"
