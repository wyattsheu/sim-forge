#!/bin/bash
F="--arc2_over_mm 30 --site_xmax_mm 50 --site_exclude_walltop 1 --hinge_from_state 1"
for n in r1 r2 r3 r4 r5; do /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/peel2/run.sh $n $F; done
touch /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/peel2/queue.done
