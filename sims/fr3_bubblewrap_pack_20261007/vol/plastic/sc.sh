#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 26000 ]; do sleep 10; done
/isaac-sim/python.sh plastic/probe_selfcoll.py "$@" > plastic/logs/stdout_sc_$(echo "$@" | tr -d ' -').txt 2>&1
