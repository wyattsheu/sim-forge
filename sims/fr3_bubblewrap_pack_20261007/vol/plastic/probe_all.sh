#!/bin/bash
# usage: plastic/probe_all.sh "0 1 2 3 4 5" [extra flags]  — 依序跑探針,每個開跑前等 GPU < 26000 MiB
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
modes=$1; shift
for m in $modes; do
  until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 26000 ]; do sleep 20; done
  /isaac-sim/python.sh plastic/probe_rest_runtime.py --mode $m "$@" > plastic/logs/stdout_m${m}_$(echo "$@" | tr -d ' -').txt 2>&1
done
