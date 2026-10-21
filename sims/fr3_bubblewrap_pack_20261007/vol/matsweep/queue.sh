#!/bin/bash
# 9 組 E × 面密度(fast、edamp 0、guard_yn 3.5)全部排上;每組 run.sh 拿啟動鎖 + 等 GPU 門檻(gpuwait.sh)才開,記憶體夠就並行
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
for c in "5e2 0.3" "1e3 0.2" "2e3 0.1" "5e2 0.2" "1e3 0.3" "2e3 0.2" "5e2 0.1" "1e3 0.1" "2e3 0.3"; do
  set -- $c; n=E$1_d$2
  [ -f matsweep/$n/stdout.txt ] && grep -q "^EXIT 0" matsweep/$n/stdout.txt && continue
  bash matsweep/run.sh $n --young $1 --areal $2 &
  sleep 2
done
wait
