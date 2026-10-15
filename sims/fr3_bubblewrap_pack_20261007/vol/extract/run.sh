#!/bin/bash
# usage: extract/run.sh NAME [extra flags...]   一次一個;GPU < 20000 MiB 且沒有其他 wrap_vol 才開
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
BASE="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3 --grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30 --hand2 attach --hand2_pad_mm 15 --hand2_keep 1 --hold_yp 1 --extract 1"
n=$1; shift; mkdir -p extract/$n
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 20000 ] && ! pgrep -f "python.*wrap_vol.py" >/dev/null; do sleep 30; done
echo "CMD: wrap_vol.py $BASE $* --out extract/$n" > extract/$n/stdout.txt
/isaac-sim/python.sh wrap_vol.py $BASE "$@" --out extract/$n >> extract/$n/stdout.txt 2>&1; echo "EXIT $?" >> extract/$n/stdout.txt
