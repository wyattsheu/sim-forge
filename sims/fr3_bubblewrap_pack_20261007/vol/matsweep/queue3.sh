#!/bin/bash
# 重跑被 H3F NameError(--extract 0 + --jaw_collide 1)打斷的 2 組
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
for c in "5e2 0.3" "1e3 0.2"; do set -- $c; bash matsweep/run.sh E$1_d$2 --young $1 --areal $2 & sleep 2; done; wait
