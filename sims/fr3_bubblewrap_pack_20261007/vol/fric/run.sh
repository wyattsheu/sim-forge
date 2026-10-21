#!/bin/bash
# usage: fric/run.sh NAME [extra flags...]   純摩擦(不綁定)第一隻手:--grasp_attach 0 --ffric 2.0 --gap_mm 2.5 --finger_mm 30 --peel_t 12;只掀 yn
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
PROG=${PROG:-wrap_vol.py}
BASE="--sheet_mm 500 --grasp 1 --grasp_attach 0 --pick_mode jaw --ffric 2.0 --gap_mm 2.5 --finger_mm 30 --peel_t 12 --arc2 1 --arc_k 0.8 --clear_mm 6 --steep_deg 45 --second 0 --young 2e3 --arc2_over_cap 0 --arc2_over_mm 30"
n=$1; shift; mkdir -p fric/$n
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 26000 ]; do sleep 30; done
echo "CMD: $PROG $BASE $* --out fric/$n" > fric/$n/stdout.txt
/isaac-sim/python.sh $PROG $BASE "$@" --out fric/$n >> fric/$n/stdout.txt 2>&1; echo "EXIT $?" >> fric/$n/stdout.txt
