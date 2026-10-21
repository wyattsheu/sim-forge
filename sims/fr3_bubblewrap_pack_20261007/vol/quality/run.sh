#!/bin/bash
# usage: quality/run.sh NAME [extra flags...]   = extract4 正式旗標 + extra(例 --quality fast)。GPU < 26000 MiB 才開;自己一次一個
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
BASE="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3 --grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30 --hand2 attach --hand2_pad_mm 15 --hand2_keep 1 --hold_yp 1 --extract 1 --guard_yp 2.6 --guard_n 2 --extract_mode slide --extract_out_mm 280 --guard_yn 2.6 --slide_clear_mm 40"
n=$1; shift; mkdir -p quality/$n
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 26000 ] && ! pgrep -f "wrap_vol.py .*--out quality/" >/dev/null; do sleep 30; done
echo "CMD: wrap_vol.py $BASE $* --out quality/$n" > quality/$n/stdout.txt
# 背景記錄同時在跑的其他模擬數(倍率污染參考)
( while sleep 30; do echo "$(date +%T) gpu $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) others $(pgrep -f 'kit/python/bin/python3 .*wrap_vol' | wc -l)" >> quality/$n/conc.txt; done ) & MON=$!
/isaac-sim/python.sh wrap_vol.py $BASE "$@" --out quality/$n >> quality/$n/stdout.txt 2>&1; echo "EXIT $?" >> quality/$n/stdout.txt
kill $MON
