#!/bin/bash
# 重現 DEMO_new_order_sheet400.mp4:四段模擬串接(每段約 2-3 分鐘,需 Isaac Sim 5.1 + GPU)
# 用法:cd sim && ./run_demo.sh   (ISAAC=/path/to/python.sh 可覆寫)
set -e
cd "$(dirname "$0")"
if [ -n "$ISAAC" ]; then P="$ISAAC"
else source ./find_isaac.sh; find_isaac || exit 5; P="$ISAAC_PYTHON"; fi
[ "$(id -u)" = 0 ] && export OMNI_KIT_ALLOW_ROOT=1
C="--wrapsim --tex bubble_normal.png --thick 0.004 --hold_mm 6 --tip_over_mm 0 --sheet_mm 400 --layer_mm 5 --young 2e4 --bend 4"
run(){ o=$1; shift; rm -rf $o; echo "== $o"; $P wrap_sim.py $C "$@" --out $o > $o.stdout 2>&1; [ -f $o/wrap.npz ] || { echo "FAIL $o(看 $o.stdout)"; exit 1; }; }
run c1      --wrap_edge --wrap_n 2 --cam_ref 0.586                                   # 1. 包第一對邊
run c2      --stage2 --init_npz c1/wrap.npz --cam_ref 0.586                          # 2. 包第二對邊
run box     --init_npz c2/wrap.npz --carton carton.usd --close_lid --lid_span 4 --no_anchor   # 3. 入箱 + 關蓋
run mb_open --init_npz box/wrap.npz --carton carton.usd --no_anchor --in_box_already \
            --no_ground_collision --base_collider_pad 0.02 --movebox 0,0.20,0.10 \
            --move_t 6 --move_wait 2 --settle 3 --move_open --lid_span 3              # 4. 搬箱 + 開蓋
: > list.txt
for d in c1 c2 box mb_open; do
  ffmpeg -y -loglevel error -ss 0.5 -i $d/wrap.mp4 -c:v libx264 -pix_fmt yuv420p -crf 20 $d/trim.mp4
  echo "file '$PWD/$d/trim.mp4'" >> list.txt
done
ffmpeg -y -loglevel error -f concat -safe 0 -i list.txt -c copy DEMO.mp4
echo "DONE → sim/DEMO.mp4"
for d in box mb_open; do grep -A7 '真的入箱了嗎' $d/wrap_sim.log | tail -1; done
