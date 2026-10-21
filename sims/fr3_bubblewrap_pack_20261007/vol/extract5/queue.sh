#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
for n in X1 X2 X3; do bash extract5/run.sh $n; done
touch extract5/queue.done
