#!/bin/bash
# usage: [PY=wrap_vol.py] extract5/run.sh NAME [extra flags...]   (= extract4 + --edamp 0.02;GPU < 26000 MiB 才開;PY 可換成 extract4 同版程式副本)
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
BASE="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3 --grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30 --hand2 attach --hand2_pad_mm 15 --hand2_keep 1 --hold_yp 1 --extract 1 --guard_yp 2.6 --guard_n 2 --extract_mode slide --extract_out_mm 280 --guard_yn 2.6 --slide_clear_mm 40 --edamp 0.02"
n=$1; shift; mkdir -p extract5/$n
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 26000 ]; do sleep 20; done
echo "CMD: ${PY:-wrap_vol.py} $BASE $* --out extract5/$n" > extract5/$n/stdout.txt
PY=${PY:-wrap_vol.py}; /isaac-sim/python.sh $PY $BASE "$@" --out extract5/$n >> extract5/$n/stdout.txt 2>&1; echo "EXIT $?" >> extract5/$n/stdout.txt
