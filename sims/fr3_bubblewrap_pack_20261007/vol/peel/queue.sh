#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
A="--arc2_over_mm 30"
B="--arc2_over_mm 30 --release_press_mm 6 --release_settle_s 1.0"
for i in 1 2 3; do peel/run.sh A$i $A; done
for i in 1 2 3; do peel/run.sh B$i $B; done
touch peel/queue.done
