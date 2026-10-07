#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/rest
run() { timeout 1200 /isaac-sim/python.sh probe_rest4.py "$@" > /dev/null 2>&1; }
( run --npz rest_g10.npz --mode A --teleport --tag A_full_g10_tp; run --npz rest_g6.npz --mode A --teleport --tag A_full_g6_tp; run --npz rest_g10.npz --mode A --cross --teleport --tag A_cross_g10_tp; run --npz rest_g6.npz --mode A --cross --teleport --tag A_cross_g6_tp; run --npz rest_g10.npz --mode B --rest_flat --tag C_full_g10 ) &
( run --npz rest_g10.npz --mode B --teleport --tag B_full_g10_tp; run --npz rest_g6.npz --mode B --teleport --tag B_full_g6_tp; run --npz rest_g6.npz --mode B --rest_flat --tag C_full_g6 ) &
( run --npz rest_g10.npz --mode B --cross --teleport --tag B_cross_g10_tp; run --npz rest_g6.npz --mode B --cross --teleport --tag B_cross_g6_tp; run --npz rest_g10.npz --mode B --cross --rest_flat --tag C_cross_g10; run --npz rest_g6.npz --mode B --cross --rest_flat --tag C_cross_g6 ) &
wait
echo BATCH_DONE
