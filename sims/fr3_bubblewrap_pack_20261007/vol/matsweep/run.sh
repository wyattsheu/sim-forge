#!/bin/bash
# usage: matsweep/run.sh NAME --young E --areal D [extra flags...]
#   = FINAL_PLAN §2 夾爪版旗標(extract6/run.sh)改成「只掀 yn、放手不撐」+ 材料掃描:
#     --hand2 off --hand2_keep 0 --hold_yp 0 --extract 0 --second 0 --quality fast --edamp 0 --guard_yn 3.5 --guard_n 2
#     (協調者 10-21 06:00:fast + edamp 0.02 掀前邊長比就 2.6~2.8、反轉 46~58,守衛一進弧線就放手 → 改 edamp 0、guard_yn 3.5)
#     --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --arc2_over_cap 0 --arc2_over_mm 30
#     + --release_watch 1(放手後 0.5/2/10 s 印 越線/壁外/質心)+ --grasp_tail_s 8.5(放手後共停 ~10.5 s)
#   後面的旗標覆蓋前面的(argparse 取最後一次)。GPU < 29500 MiB 才開(與 plastic/ 共用同一把啟動鎖)。
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
BASE="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3 --grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30 --hand2 jaw --hand2_pad_mm 15 --hand2_keep 1 --hold_yp 1 --extract 1 --guard_yp 2.6 --guard_n 2 --extract_mode slide --extract_out_mm 280 --guard_yn 2.6 --slide_clear_mm 40 --hand1_jaw 1 --extract_grip jaw"
SWEEP="--hand2 off --hand2_keep 0 --hold_yp 0 --extract 0 --second 0 --quality fast --edamp 0 --guard_yn 3.5 --guard_n 2 --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --arc2_over_cap 0 --arc2_over_mm 30 --release_watch 1 --grasp_tail_s 8.5"
n=$1; shift; mkdir -p matsweep/$n
source matsweep/gpuwait.sh
echo "CMD: wrap_vol.py $BASE $SWEEP $* --out matsweep/$n" > matsweep/$n/stdout.txt
echo "START $(date +%T)" >> matsweep/$n/stdout.txt
/isaac-sim/python.sh wrap_vol.py $BASE $SWEEP "$@" --out matsweep/$n >> matsweep/$n/stdout.txt 2>&1; echo "EXIT $? $(date +%T)" >> matsweep/$n/stdout.txt
