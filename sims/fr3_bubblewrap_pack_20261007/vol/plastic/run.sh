#!/bin/bash
# usage: plastic/run.sh NAME [extra flags...]
#   = JAW.md 正式旗標(extract6)改成「放手不撐」:--hand2 off --hand2_keep 0 --hold_yp 0,+ extra(例 --plastic_on_release 1 --quality fast)
#   後面的旗標覆蓋前面的(argparse 取最後一次)。GPU < 26000 MiB 才開。
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
BASE="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3 --grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30 --hand2 off --hand2_pad_mm 15 --hand2_keep 0 --hold_yp 0 --extract 1 --guard_yp 2.6 --guard_n 2 --extract_mode slide --extract_out_mm 280 --guard_yn 2.6 --slide_clear_mm 40 --hand1_jaw 1 --extract_grip jaw"
n=$1; shift; mkdir -p plastic/$n
sleep $((RANDOM % 20))
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 26000 ]; do sleep 30; done
echo "CMD: wrap_vol.py $BASE $* --out plastic/$n" > plastic/$n/stdout.txt
/isaac-sim/python.sh wrap_vol.py $BASE "$@" --out plastic/$n >> plastic/$n/stdout.txt 2>&1; echo "EXIT $?" >> plastic/$n/stdout.txt
