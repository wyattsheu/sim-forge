#!/bin/bash
# usage: pgrasp/run2.sh NAME [extra flags...]   階段 2:wrap_vol 寬指純摩擦掀 yn
#   = matsweep/run.sh 的旗標(FINAL_PLAN §2 夾爪版 + 只掀 yn、放手後看 10 s:--hand2 off --extract 0 --second 0 --quality fast --edamp 0 --guard_yn 3.5 ...)
#     + --grasp_attach 0 --pick_mode wide(寬指、純摩擦、不綁定);--wide_mm / --wide_squeeze_mm 由 extra 給
#   後面的旗標覆蓋前面的(argparse 取最後一次)。GPU OOM 自動重跑。
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
BASE="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3 --grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30 --hand2 jaw --hand2_pad_mm 15 --hand2_keep 1 --hold_yp 1 --extract 1 --guard_yp 2.6 --guard_n 2 --extract_mode slide --extract_out_mm 280 --guard_yn 2.6 --slide_clear_mm 40 --hand1_jaw 1 --extract_grip jaw"
SWEEP="--hand2 off --hand2_keep 0 --hold_yp 0 --extract 0 --second 0 --quality fast --edamp 0 --guard_yn 3.5 --guard_n 2 --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --arc2_over_cap 0 --arc2_over_mm 30 --release_watch 1 --grasp_tail_s 8.5"
PG="--grasp_attach 0 --pick_mode wide"
n=$1; shift; D=pgrasp/$n; mkdir -p $D
for try in $(seq 1 30); do
  source pgrasp/gpuwait.sh
  echo "CMD: wrap_vol.py $BASE $SWEEP $PG $* --out $D" > $D/stdout.txt
  echo "START $(date +%T)" >> $D/stdout.txt
  /isaac-sim/python.sh wrap_vol.py $BASE $SWEEP $PG "$@" --out $D >> $D/stdout.txt 2>&1; echo "EXIT $? $(date +%T)" >> $D/stdout.txt
  if grep -qi "out-of-memory\|out of memory\|failed to allocate\|OUT_OF_DEVICE_MEMORY\|Scene state is corrupted" $D/stdout.txt; then
    mv $D/stdout.txt $D/stdout_oom$try.txt; sleep 60; continue
  fi
  break
done
