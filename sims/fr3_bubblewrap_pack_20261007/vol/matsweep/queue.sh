#!/bin/bash
# 9 組 E × 面密度(fast);每組 run.sh 自己等 GPU 鎖,這裡最多同時 3 個
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
for c in "5e2 0.3" "1e3 0.2" "2e3 0.1" "5e2 0.2" "1e3 0.3" "2e3 0.2" "5e2 0.1" "1e3 0.1" "2e3 0.3"; do
  set -- $c; n=E$1_d$2
  [ -f matsweep/$n/stdout.txt ] && grep -q "^EXIT" matsweep/$n/stdout.txt && continue
  while [ "$(pgrep -fc "matsweep/run.sh")" -ge 3 ]; do sleep 20; done
  bash matsweep/run.sh $n --young $1 --areal $2 &
  sleep 100
done
wait
