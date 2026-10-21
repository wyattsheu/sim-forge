#!/bin/bash
# usage: table/run.sh NAME attach|wide [extra flags...]   (環境變數 N / KS / MAXPAR 照 run3.sh;預設 MAXPAR=2)
#   = run3.sh @demo(FINAL_PLAN §2 夾爪版)+ matsweep/pgrasp 的「只掀 yn、放手後看 10 s」旗標 + 桌面掀開:
#     --hand2 off --hand2_keep 0 --hold_yp 0 --extract 0 --second 0 --quality fast --edamp 0 --guard_yn 3.5 --guard_n 2 --peel_t 8
#     --hand1_jaw 1 --jaw_collide 1 --release_watch 1 --grasp_tail_s 8.5 --until fold --unwrap_on_table 1
#   wide = + PGRASP.md 寬指純摩擦旗標(--grasp_attach 0 --pick_mode wide --wide_mm 150 --wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 1 --clear_mm 2 --pick_mm 0)
#   後面的旗標覆蓋前面的(argparse 取最後一次)。結果在 table/NAME/{1,2,3}/,跑完 python3 table/table.py table/NAME
cd "$(dirname "$0")/.."   # [release] 原為開發機絕對路徑;結果在 sim/table/NAME/
n=$1; mode=$2; shift 2
SWEEP="--hand2 off --hand2_keep 0 --hold_yp 0 --extract 0 --second 0 --quality fast --edamp 0 --guard_yn 3.5 --guard_n 2 --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --release_watch 1 --grasp_tail_s 8.5 --until fold --unwrap_on_table 1"
WIDE="--grasp_attach 0 --pick_mode wide --wide_mm 150 --wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 1 --clear_mm 2 --pick_mm 0"
[ "$mode" = wide ] && X="$WIDE" || X=""
MAXPAR=${MAXPAR:-2} ./run3.sh table/$n @demo $SWEEP $X "$@"
