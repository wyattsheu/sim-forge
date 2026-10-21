#!/bin/bash
# usage: extract6/run.sh NAME [extra flags...]   = extract4 正式旗標 + 三隻手都用夾爪(--hand1_jaw 1 --hand2 jaw --extract_grip jaw)
# GPU < 26000 MiB 才開。PROG 可覆寫(預設 wrap_vol.py)
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
PROG=${PROG:-wrap_vol.py}
BASE="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3 --grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30 --hand2 jaw --hand2_pad_mm 15 --hand2_keep 1 --hold_yp 1 --extract 1 --guard_yp 2.6 --guard_n 2 --extract_mode slide --extract_out_mm 280 --guard_yn 2.6 --slide_clear_mm 40 --hand1_jaw 1 --extract_grip jaw"
n=$1; shift; mkdir -p extract6/$n
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 26000 ]; do sleep 30; done
echo "CMD: $PROG $BASE $* --out extract6/$n" > extract6/$n/stdout.txt
/isaac-sim/python.sh $PROG $BASE "$@" --out extract6/$n >> extract6/$n/stdout.txt 2>&1; echo "EXIT $?" >> extract6/$n/stdout.txt
