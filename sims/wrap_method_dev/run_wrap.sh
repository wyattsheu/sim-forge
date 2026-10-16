#!/bin/bash
# run_wrap.sh — 跑一次包裝模擬(被包物 / 紙箱 / 包材參數由 case 檔決定)。可以順便用 WebRTC 即時看。
#
#   ./run_wrap.sh                                   # 預設 case、volume 模型、跑到入箱關蓋(--until box)
#   ./run_wrap.sh --case cases/mug_270x230x131.env  # 指定 case(換被包物 / 紙箱就換 case 檔)
#   ./run_wrap.sh --engine surface                  # 改用 surface 薄膜(四段模擬接力)
#   ./run_wrap.sh --until all                       # fold | box | move | all(搬箱 + 開蓋)
#   ./run_wrap.sh --out out/test1                   # 輸出資料夾(預設 out/<case>_<engine>)
#   ./run_wrap.sh -- --fold_order yp,yn,xp,xn       # `--` 之後的旗標原封不動交給 wrap_vol.py / wrap_sim.py
#
#   ./run_wrap.sh --live [...]                      # ★ 同上,但開 WebRTC 串流即時看(背景執行,log 在 <out>/live.log)
#   ./run_wrap.sh --live --check                    # 只印偵測結果(Isaac Sim、IP、port、GPU),不啟動
#   ./run_wrap.sh --stop                            # 停掉 --live 開的模擬 / 串流
#
#   WEBRTC_IP=1.2.3.4 WEBRTC_PORT=49110 ./run_wrap.sh --live   # 指定 client 連的 IP / signaling port
#   LIVE_HOLD=0 ./run_wrap.sh --live                # 跑完就關(預設跑完停在最後畫面繼續串流)
#   CUDA_VISIBLE_DEVICES=1 ./run_wrap.sh            # 指定 GPU
#
# 輸出:<out>/wrap.mp4、wrap.npz、wrap_vol.log 或 wrap_sim.log(結尾有驗收表:超出紙箱幾點、穿模、邊長比)。
# surface 版輸出四個子資料夾 c1 / c2 / box / mb_open,各自有 wrap.mp4,另外串成 <out>/DEMO.mp4。
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDF="$HERE/logs/live.pid"

if [ "$1" = "--stop" ]; then
  [ -f "$PIDF" ] || { echo "No live run is recorded ($PIDF)"; exit 0; }
  PG=$(cat "$PIDF")
  if kill -0 "$PG" 2>/dev/null; then
    kill -TERM -- "-$PG" 2>/dev/null || kill -TERM "$PG"
    echo -n "Stopping live run (process group $PG)"
    for i in $(seq 1 30); do kill -0 "$PG" 2>/dev/null || break; echo -n "."; sleep 1; done
    kill -0 "$PG" 2>/dev/null && { kill -KILL -- "-$PG" 2>/dev/null; echo -n " force-killed"; }
    echo " stopped"
  else
    echo "Live run $PG is not running"
  fi
  rm -f "$PIDF"; exit 0
fi

CASE="$HERE/cases/mug_270x230x131.env"; ENGINE=""; UNTIL=box; OUT=""; LIVE=0; CHECK=0; EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --case)   CASE="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"; shift 2 ;;
    --engine) ENGINE="$2"; shift 2 ;;
    --until)  UNTIL="$2"; shift 2 ;;
    --out)    OUT="$2"; shift 2 ;;
    --live)   LIVE=1; shift ;;
    --check)  CHECK=1; shift ;;
    --)       shift; EXTRA=("$@"); break ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see $0 --help)" >&2; exit 2 ;;
  esac
done
[ -f "$CASE" ] || { echo "Case file not found: $CASE" >&2; exit 2; }
CLI_ENGINE="$ENGINE"
# shellcheck disable=SC1090
source "$CASE"
ENGINE="${CLI_ENGINE:-${ENGINE:-volume}}"
case "$ENGINE" in volume|surface) ;; *) echo "--engine must be volume or surface" >&2; exit 2 ;; esac
case "$UNTIL" in fold|box|move|all) ;; *) echo "--until must be fold, box, move or all" >&2; exit 2 ;; esac
abs() { case "$1" in /*) echo "$1" ;; *) echo "$HERE/$1" ;; esac; }
ITEM=$(abs "$ITEM"); CARTON=$(abs "$CARTON"); TEX=$(abs "$TEX")
for f in "$ITEM" "$CARTON" "${CARTON%.usd}.meta.json" "$TEX"; do
  [ -f "$f" ] || { echo "Missing file from case $(basename "$CASE"): $f" >&2; exit 2; }
done
CNAME=$(basename "$CASE" .env)
OUT=$(abs "${OUT:-out/${CNAME}_${ENGINE}}")

source "$HERE/find_isaac.sh"
find_isaac || exit 5
[ "$(id -u)" = 0 ] && export OMNI_KIT_ALLOW_ROOT=1
export OMNI_KIT_ACCEPT_EULA=${OMNI_KIT_ACCEPT_EULA:-YES}
PY="$ISAAC_PYTHON"

# ── 串流設定(--live)──────────────────────────────────────────────────
if [ "$LIVE" = 1 ]; then
  if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
    echo "A live run is already going (process group $(cat "$PIDF")). Stop it first: $0 --stop" >&2; exit 4
  fi
  PORT="${WEBRTC_PORT:-49100}"
  if [ -z "${WEBRTC_PORT:-}" ]; then
    for _ in $(seq 1 20); do ss -lnt 2>/dev/null | grep -q ":$PORT " || break; PORT=$((PORT+1)); done
  fi
  ss -lnt 2>/dev/null | grep -q ":$PORT " && { echo "Port $PORT is in use -- pick another: WEBRTC_PORT=49110 $0 ..." >&2; exit 3; }
  MEDIA="${WEBRTC_MEDIA_PORT:-47998}"
  if [ -z "${WEBRTC_MEDIA_PORT:-}" ]; then
    for _ in $(seq 1 20); do ss -lnu 2>/dev/null | grep -q ":$MEDIA " || break; MEDIA=$((MEDIA+1)); done
  fi
  if [ -n "${WEBRTC_IP:-}" ]; then IP="$WEBRTC_IP"
  else
    IP=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' \
      | grep -vE '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|127\.|169\.254\.)' | head -1)
    [ -n "$IP" ] || IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  fi
  export LIVE_IP="$IP" LIVE_PORT="$PORT" LIVE_MEDIA="$MEDIA" LIVE_HOLD="${LIVE_HOLD:-1}"
fi

echo "Case   : $CASE"
echo "Item   : $ITEM"
echo "Carton : $CARTON"
echo "Engine : $ENGINE   until: $UNTIL   out: $OUT"
echo "Isaac  : $ISAAC_KIND  $ISAAC_HOME"
if [ "$LIVE" = 1 ]; then
  echo "Connect: $LIVE_IP in the WebRTC Streaming Client (signaling TCP $LIVE_PORT, media UDP $LIVE_MEDIA)"
fi
if [ "$CHECK" = 1 ]; then
  nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/GPU    : /'
  exit 0
fi
mkdir -p "$OUT" "$HERE/logs"

# ── 組指令 ────────────────────────────────────────────────────────────
# runner <資料夾> <腳本> <參數...>:一般模式直接跑;--live 經過 viewer/live_run.py
runner() {
  local dir="$1"; shift
  if [ "$LIVE" = 1 ]; then (cd "$dir" && "$PY" "$HERE/viewer/live_run.py" "$@")
  else (cd "$dir" && "$PY" "$@"); fi
}

run_volume() {
  # shellcheck disable=SC2086
  runner "$HERE/volume" wrap_vol.py --mug "$ITEM" --carton "$CARTON" --tex "$TEX" \
      $VOL_ARGS --until "$UNTIL" --out "$OUT" "${EXTRA[@]}"
}

run_surface() {
  # 四段接力,與 surface/run_demo.sh 相同(那支用固定素材;這裡改成讀 case)
  local stages=(c1 c2)
  case "$UNTIL" in box) stages+=(box) ;; move|all) stages+=(box mb_open) ;; esac
  local last="${stages[-1]}" hold="${LIVE_HOLD:-1}" s
  for s in "${stages[@]}"; do
    rm -rf "$OUT/$s"; echo "== surface stage $s"
    [ "$LIVE" = 1 ] && { [ "$s" = "$last" ] && export LIVE_HOLD="$hold" || export LIVE_HOLD=0; }
    local A=()
    case "$s" in
      c1)      A=(--wrap_edge --wrap_n 2 --cam_ref 0.586) ;;
      c2)      A=(--stage2 --init_npz "$OUT/c1/wrap.npz" --cam_ref 0.586) ;;
      box)     A=(--init_npz "$OUT/c2/wrap.npz" --carton "$CARTON" --close_lid --lid_span 4 --no_anchor) ;;
      mb_open) A=(--init_npz "$OUT/box/wrap.npz" --carton "$CARTON" --no_anchor --in_box_already
                  --no_ground_collision --base_collider_pad 0.02 --movebox 0,0.20,0.10
                  --move_t 6 --move_wait 2 --settle 3 --move_open --lid_span 3) ;;
    esac
    # shellcheck disable=SC2086
    runner "$HERE/surface" wrap_sim.py $SURF_ARGS --mug "$ITEM" --tex "$TEX" "${A[@]}" --out "$OUT/$s" "${EXTRA[@]}"
    [ -f "$OUT/$s/wrap.npz" ] || { echo "FAIL: stage $s produced no wrap.npz (see $OUT/$s/wrap_sim.log)" >&2; return 1; }
  done
  if command -v ffmpeg >/dev/null; then
    : > "$OUT/list.txt"
    for s in "${stages[@]}"; do
      ffmpeg -y -loglevel error -ss 0.5 -i "$OUT/$s/wrap.mp4" -c:v libx264 -pix_fmt yuv420p -crf 20 "$OUT/$s/trim.mp4"
      echo "file '$OUT/$s/trim.mp4'" >> "$OUT/list.txt"
    done
    ffmpeg -y -loglevel error -f concat -safe 0 -i "$OUT/list.txt" -c copy "$OUT/DEMO.mp4" && echo "DEMO -> $OUT/DEMO.mp4"
  fi
}

if [ "$LIVE" = 1 ]; then
  LOG="$OUT/live.log"
  export -f runner run_volume run_surface
  export HERE PY LIVE OUT UNTIL ITEM CARTON TEX VOL_ARGS SURF_ARGS
  EXTRA_Q=""; [ ${#EXTRA[@]} -gt 0 ] && EXTRA_Q=$(printf '%q ' "${EXTRA[@]}")
  setsid bash -c "EXTRA=($EXTRA_Q); run_$ENGINE" > "$LOG" 2>&1 < /dev/null &
  echo $! > "$PIDF"
  echo "Log    : $LOG   -- connect once it shows [live] STREAMING (first start can take a few minutes)"
  echo "Stop   : $0 --stop"
else
  "run_$ENGINE"
  echo "Done -> $OUT"
fi
