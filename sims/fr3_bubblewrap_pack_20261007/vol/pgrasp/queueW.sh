#!/bin/bash
# 階段 2:3 次同旗標(最多同時 2 個)。寬指 L150 x D40 x T6、指間 3.0(壓 1.0)、指面摩擦 2.0(--ffric 預設)、下指伸進 45mm
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
F="--wide_mm 150 --wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0"
pgrasp/run2.sh W1 $F &
sleep 120
pgrasp/run2.sh W2 $F &
wait -n
pgrasp/run2.sh W3 $F &
wait
