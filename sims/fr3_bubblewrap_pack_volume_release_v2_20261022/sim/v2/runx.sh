#!/bin/bash
# usage: v2/runx.sh NAME [extra flags...]   → 結果在 v2/x/NAME/{1,2,3}/(環境變數 N / KS / MAXPAR / LOADCHK 照 run3.sh;預設 MAXPAR=2)
#   = v2/run.sh 的同一組旗標(run3.sh @demo + 桌面掀開 + 寬指純摩擦 + v2 旗標),[release] 改走 ./run3.sh(開發版 run3x.sh 已併入)
#   [v2x] 例:
#     存檔(整鏈跑到 x 片開始就停):N=1 v2/runx.sh S_fast --ut_release_up 1 --save_state 'v2/x/S_fast/S{k}.npz' --at xflaps --save_exit 1
#     續跑 x 片 + 取杯:          v2/runx.sh A_fast --ut_release_up 1 --load_state v2/x/S_fast/S1.npz --v2_xmode sweep
cd "$(dirname "$0")/.."   # [release] 原為開發機絕對路徑
n=$1; shift
V2="--hand2 off --hand2_keep 0 --hold_yp 0 --second 1 --quality fast --edamp 0 --guard_yn 3.5 --guard_n 2 --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --release_watch 1 --grasp_tail_s 1"
WIDE="--grasp_attach 0 --pick_mode wide --wide_mm 150 --wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 1 --clear_mm 2 --pick_mm 0"
FLOW="--tape_follow 1 --takeout 1 --v2_xflaps 1 --v2_hold_cup 1 --extract 1 --extract_mode lift --extract_out_mm 380"
mkdir -p v2/x
MAXPAR=${MAXPAR:-2} TABLE=${TABLE-"python3 v2/tablex.py"} ./run3.sh v2/x/$n @demo $V2 $WIDE $FLOW "$@"
