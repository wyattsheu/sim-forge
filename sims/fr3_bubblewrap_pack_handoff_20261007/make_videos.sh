#!/bin/bash
# 重新產生交付影片(影片不進 git,一律用這支產生)。
#
#   ./make_videos.sh            # 物理驗證 3 支 + 環繞 1 支,約 5 分鐘
#   ./make_videos.sh --demo     # 再加成果影片 DEMO(wrap_sim 四段,約 10 分鐘,需 GPU)
#
#   VIDEO_DIR=/tmp/v ./make_videos.sh   # 輸出到別的地方(預設 ./videos)
#   ISAAC=/path/to/python.sh ./make_videos.sh   # 不設就自動找(ISAAC_SIM_PATH / ISAAC_SIM_PIP_ENV 可指定)
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "$ISAAC" ]; then PY="$ISAAC"
else source "$HERE/sim/find_isaac.sh"; find_isaac || exit 5; PY="$ISAAC_PYTHON"; fi
VID="${VIDEO_DIR:-$HERE/videos}"
WORK="${WORK_DIR:-$HERE/logs/make_videos}"
[ "$(id -u)" = 0 ] && export OMNI_KIT_ALLOW_ROOT=1
mkdir -p "$VID" "$WORK"
cd "$HERE/sim"

check() {   # check <影片名> <scene_physics_check.py 參數...>
  local name=$1; shift
  echo "== $name"
  "$PY" scene_physics_check.py "$HERE/scene_final.usd" --out "$WORK/$name" "$@" > "$WORK/$name.stdout" 2>&1 \
    || { echo "FAIL $name(see $WORK/$name.stdout)"; exit 1; }
  cp "$WORK/$name/physics_check.mp4" "$VID/$name.mp4"
  cp "$WORK/$name/physics_check.log" "$VID/$name.log"
  grep -A99 "結論" "$VID/$name.log" | sed 's/^/   /'
}
check scene_physics_crease_on  --secs 8
check scene_physics_crease_off --secs 8 --no_crease
check scene_physics_open_lids  --secs 10 --open_deg 170

echo "== scene_final_orbit"
"$PY" orbit_video.py "$HERE/scene_final.usd" "$VID/scene_final_orbit.mp4" > "$WORK/orbit.stdout" 2>&1 \
  || { echo "FAIL orbit(see $WORK/orbit.stdout)"; exit 1; }

if [ "$1" = "--demo" ]; then
  echo "== DEMO (4 wrap_sim stages)"
  ISAAC="$PY" ./run_demo.sh
  cp DEMO.mp4 "$VID/DEMO_new_order_sheet400.mp4"
fi
echo "Done -> $VID"
ls -la "$VID"
