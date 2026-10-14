#!/bin/bash
R=/isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/peel4/run.sh
S="--site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30 --arc2_lay 1 --arc2_er_stop 2.0"
for n in L1 L2 L3 L4 L5; do $R $n $S; done
touch /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/peel4/queue.done
