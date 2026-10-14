#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
BASE="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3"
for F in 0.5 0.2 1.0; do
  N=drag/finite_stiff_proxy_f$F; mkdir -p $N
  until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 20000 ]; do sleep 20; done
  echo "START $N $(date)" >> drag/sweep_status.txt
  timeout 2400 /isaac-sim/python.sh wrap_vol.py $BASE --attach_proxy 1 --proxy_k 500 --proxy_fmax $F --out $N > $N/stdout.txt 2>&1
  echo "DONE $N exit $? $(date)" >> drag/sweep_status.txt
done
echo ALLDONE >> drag/sweep_status.txt
