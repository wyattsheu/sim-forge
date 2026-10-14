#!/bin/bash
# usage: run_hold.sh <name> <extra flags...>
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
N=$1; shift
BASE="--grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3"
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 20000 ]; do sleep 30; done
mkdir -p drag/$N
echo "CMD: /isaac-sim/python.sh wrap_vol.py $BASE $@ --out drag/$N" > drag/$N.stdout
/isaac-sim/python.sh wrap_vol.py $BASE "$@" --out drag/$N >> drag/$N.stdout 2>&1
echo "RUN_DONE rc=$?" >> drag/$N.stdout
