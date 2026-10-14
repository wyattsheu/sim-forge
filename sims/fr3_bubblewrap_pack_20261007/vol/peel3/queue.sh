#!/bin/bash
R=/isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/peel3/run.sh
S="--site_xmax_mm 60 --grasp_site_k 13"
for n in a1 a2; do $R $n $S --arc2_over_cap 0 --arc2_over_mm 30; done
for n in c1 c2 c3 c4 c5; do $R $n $S --arc2_target centroid; done
touch /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/peel3/queue.done
