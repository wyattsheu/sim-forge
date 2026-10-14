#!/bin/bash
# usage: peel2/run.sh NAME [extra flags...]   (BASE = robust/run.sh 同指令)
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
BASE="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3 --grasp_site state --grasp_retry 2"
n=$1; shift; mkdir -p peel2/$n
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 20000 ]; do sleep 30; done
echo "CMD: wrap_vol.py $BASE $* --out peel2/$n" > peel2/$n/stdout.txt
/isaac-sim/python.sh wrap_vol.py $BASE "$@" --out peel2/$n >> peel2/$n/stdout.txt 2>&1; echo "EXIT $?" >> peel2/$n/stdout.txt
