#!/bin/bash
# 階段 2 重複 + 越壁 60:C150 旗標再跑 2 次(共 3 次)+ --arc2_over_mm 60 一次;最多同時 2 個
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
F="--wide_mm 150 --wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 1 --clear_mm 2 --pick_mm 0"
while pgrep -f "queueC.sh" > /dev/null; do sleep 20; done
pgrasp/run2.sh C150_r2 $F &
sleep 100
pgrasp/run2.sh C150_o60 $F --arc2_over_mm 60 &
wait -n
pgrasp/run2.sh C150_r3 $F &
wait
