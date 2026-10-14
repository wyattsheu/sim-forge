#!/bin/bash
# usage: robust/run.sh r1 r2 ...  (BASE = out_ga3 原樣 + --grasp_site state --grasp_retry 2)
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
BASE="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3"
for n in "$@"; do
  mkdir -p robust/$n
  until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 20000 ]; do sleep 30; done
  echo "CMD: wrap_vol.py $BASE --grasp_site state --grasp_retry 2 --out robust/$n" > robust/$n/stdout.txt
  /isaac-sim/python.sh wrap_vol.py $BASE --grasp_site state --grasp_retry 2 --out robust/$n >> robust/$n/stdout.txt 2>&1; echo "EXIT $?" >> robust/$n/stdout.txt
done
touch robust/queue.done
