#!/bin/bash
# 協調者追加:軟材料 + 越壁 60 mm(放手時質心過壁?)
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
for c in "5e2 0.3" "1e3 0.3"; do set -- $c; n=E$1_d$2_over60
  [ -f matsweep/$n/stdout.txt ] && grep -q "^EXIT 0" matsweep/$n/stdout.txt && continue
  bash matsweep/run.sh $n --young $1 --areal $2 --arc2_over_mm 60 & sleep 2; done; wait
