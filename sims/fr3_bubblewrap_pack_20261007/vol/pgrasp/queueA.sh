#!/bin/bash
# 階段 2 插入修正:下指沿「邊 → 往內第 3 排」的弦插(--chord 3)、指頂在布底下 1mm(--clear_mm 1;W1 的 6mm 把布邊往內推 20mm、指間只剩 1 點)
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
F="--wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 3 --clear_mm 1"
pgrasp/run2.sh A150 --wide_mm 150 $F &
sleep 100
pgrasp/run2.sh A100 --wide_mm 100 $F &
wait
