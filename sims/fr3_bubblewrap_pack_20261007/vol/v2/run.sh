#!/bin/bash
# usage: v2/run.sh NAME [extra flags...]   (環境變數 N / KS / MAXPAR 照 run3.sh;預設 MAXPAR=2)
#   v2 完整流程:折 → 入箱關蓋(膠帶 = 錨點保留、跟著杯子走)→ 搬箱 → 開蓋 → 手 2 取出整包放到桌面 → 手 1 寬指純摩擦掀 yn、yp(→ xn、xp)→ 手 2 取杯放旁邊
#   = run3.sh @demo(FINAL_PLAN §2 夾爪版)+ 桌面掀開旗標(table/run.sh)+ 寬指純摩擦(PGRASP.md)+ v2 旗標:
#     --hand2 off --hand2_keep 0 --hold_yp 0 --second 1 --quality fast --edamp 0 --guard_yn 3.5 --guard_n 2 --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --release_watch 1 --grasp_tail_s 1
#     --grasp_attach 0 --pick_mode wide --wide_mm 150 --wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 1 --clear_mm 2 --pick_mm 0
#     --tape_follow 1 --takeout 1 --v2_xflaps 1 --v2_hold_cup 1 --extract 1 --extract_mode lift --extract_out_mm 380
#   後面的旗標覆蓋前面的(argparse 取最後一次),例如 final:v2/run.sh F --quality final --edamp 0.02
#   結果在 v2/NAME/{1,2,3}/,跑完 python3 v2/table.py v2/NAME
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
n=$1; shift
V2="--hand2 off --hand2_keep 0 --hold_yp 0 --second 1 --quality fast --edamp 0 --guard_yn 3.5 --guard_n 2 --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --release_watch 1 --grasp_tail_s 1"
WIDE="--grasp_attach 0 --pick_mode wide --wide_mm 150 --wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 1 --clear_mm 2 --pick_mm 0"
FLOW="--tape_follow 1 --takeout 1 --v2_xflaps 1 --v2_hold_cup 1 --extract 1 --extract_mode lift --extract_out_mm 380"
MAXPAR=${MAXPAR:-2} ./run3.sh v2/$n @demo $V2 $WIDE $FLOW "$@"
