#!/bin/bash
# run_release.sh — 一條指令跑出交付版影片(volume 4 mm 包材:四折 → 入箱 → 搬箱 → 開蓋 → 夾爪掀開撐住 → 取杯)。
#
#   ./run_release.sh final [NAME]   # 正式版:--quality final(dt 1/240、solver 128、1280x720)--edamp 0.02;約 20~25 分鐘
#   ./run_release.sh fast  [NAME]   # 開發用:--quality fast(dt 1/120、solver 48、960x540)--edamp 0;約 13~14 分鐘
#   ./run_release.sh final X2 --seed 3 --fold_order yp,yn,xp,xn   # 後面多給的旗標原樣傳給 wrap_vol.py(同名旗標以後給的為準)
#   UNTIL=box ./run_release.sh fast K1                             # 只跑到入箱關蓋(約 4~5 分鐘,換紙箱 / 折法時先篩這段)
#
# 輸出:../runs/<mode>_<NAME>/(wrap.mp4、wrap_vol.log、wrap.npz、grasp.json、key_*.png、stdout.txt);
#       final 且跑完整鏈時另外剪 ../runs/<mode>_<NAME>/short.mp4(= videos/DEMO_twohand_extract_short.mp4 的剪法,18 s)。
# GPU:開跑前等 nvidia-smi 已用量 < GPU_MAX(預設 26000 MiB);一次只跑一個(兩個錄影同時跑會 OOM)。
# ISAAC=/path/to/python.sh 指定直譯器;不設就自動找(ISAAC_SIM_PATH / ISAAC_SIM_PIP_ENV 可指定,見 find_isaac.sh)。
#
# 旗標來源:docs/vol/JAW.md「正式 demo 旗標(夾爪版)」+ [jaw3] `--jaw_collide 1`(指頭是碰撞體);
#           精度 docs/vol/QUALITY.md;阻尼 docs/vol/DAMPING.md、EXTRACT3 v5;紙箱 = surface 交付版那個 carton.usd(co7b 紙箱,幾何同 carton_w131)。
# TODO(MATSWEEP):docs/vol/MATSWEEP.md 的結論(越壁 60 + 軟材料,改 --young / --areal / --arc2_over_mm)出來後若可用,
#                 這裡的 MATERIAL / GRASP 要更新,README §1、§9 一併改。
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$HERE"
MODE=${1:-final}; NAME=${2:-X1}; shift $(( $# >= 2 ? 2 : $# )) || true
case "$MODE" in
  final) QUAL="--quality final --edamp 0.02" ;;
  fast)  QUAL="--quality fast --edamp 0" ;;
  *) echo "usage: $0 final|fast [NAME] [extra wrap_vol flags]"; exit 2 ;;
esac
if [ -n "$ISAAC" ]; then PY="$ISAAC"
else source "$HERE/find_isaac.sh"; find_isaac || exit 5; PY="$ISAAC_PYTHON"; fi
[ "$(id -u)" = 0 ] && export OMNI_KIT_ALLOW_ROOT=1

MATERIAL="--young 2e3 --poisson 0.45 --thick_mm 4 --areal 0.1 --fric 0.8 --ldamp 0"
GEOM="--sheet_mm 500 --nxy 35 --tip_over_mm 30 --tuck 1 --carton carton.usd --mug mug.stl --tex bubble_normal.png"
GRASP="--grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 \
--grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30"
HANDS="--hand1_jaw 1 --hand2 jaw --hand2_pad_mm 15 --hand2_keep 1 --hold_yp 1 --jaw_collide 1"
EXTRACT="--extract 1 --extract_grip jaw --extract_mode slide --extract_out_mm 280 --slide_clear_mm 40 --guard_yn 2.6 --guard_yp 2.6 --guard_n 2"
UNTIL=${UNTIL:-all}
# wrap_vol.py 的 --extract 沒有檢查 --until:--until box 加 --extract 1 時取杯段會接在 T_MOVE0 之後、在搬箱途中把杯子拖出箱外
# (2026-10-21 紙箱相容測試實測,README §11 #13)。所以只跑一段時拿掉取杯旗標(抓取段 wrap_vol 自己只在 --until all 才跑)。
[ "$UNTIL" != all ] && EXTRACT=""

OUT="$HERE/../runs/${MODE}_${NAME}"; mkdir -p "$OUT"
GPU_MAX=${GPU_MAX:-26000}
while [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)" -ge "$GPU_MAX" ]; do
  echo "GPU 已用 >= $GPU_MAX MiB,等 30 s"; sleep 30; done
CMD="$PY wrap_vol.py $MATERIAL $GEOM $GRASP $HANDS $EXTRACT $QUAL --until $UNTIL $* --out $OUT"
echo "CMD: $CMD" | tee "$OUT/stdout.txt"
PYTHONDONTWRITEBYTECODE=1 $CMD >> "$OUT/stdout.txt" 2>&1 || { echo "FAIL(見 $OUT/stdout.txt)"; tail -5 "$OUT/stdout.txt"; exit 1; }
grep -n "SUMMARY\|真的入箱了嗎" "$OUT/stdout.txt" | tail -12 || true
if [ "$UNTIL" = all ]; then
  python3 table.py "$OUT" 2>/dev/null || true
  [ "$MODE" = final ] && bash cut_short.sh "$OUT/wrap.mp4" "$OUT/short.mp4" >/dev/null && echo "short -> $OUT/short.mp4"
fi
echo "Done -> $OUT"
