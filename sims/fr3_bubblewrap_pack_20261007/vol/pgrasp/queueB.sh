#!/bin/bash
# 階段 2:下指起點足跡 u∈[+7,+47](寬指修正)、沿弦(第 3 排)插 45mm、指頂在布底下 1mm;L150 / L100
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
F="--wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 3 --clear_mm 1"
pgrasp/run2.sh B150 --wide_mm 150 $F &
sleep 100
pgrasp/run2.sh B100 --wide_mm 100 $F &
wait
