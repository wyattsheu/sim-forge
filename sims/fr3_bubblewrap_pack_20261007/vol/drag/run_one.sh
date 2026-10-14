#!/bin/bash
# usage: run_one.sh <name> <extra flags...>
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol; n=$1; shift; mkdir -p drag/$n
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 20000 ]; do sleep 30; done
/isaac-sim/python.sh wrap_vol.py --sheet_mm 500 --young 2e3 --tuck 1 --grasp 1 --chord 1 --clear_mm 6 --steep_deg 45 --arc_k 0.8 --peel_t 6 --arc2 1 --grasp_attach 1 --gap_mm 4 --attach_pad_mm 24 --out drag/$n "$@" > drag/$n/stdout.txt 2>&1; echo "EXIT $?" >> drag/$n/stdout.txt
