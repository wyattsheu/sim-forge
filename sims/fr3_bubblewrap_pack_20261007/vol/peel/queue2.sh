#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
until [ -f peel/queue.done ]; do sleep 30; done
C="--arc2_over_mm 30 --arc_grow_max_mm 20"
for i in 1 2 3; do peel/run.sh C$i $C; done
touch peel/queue2.done
