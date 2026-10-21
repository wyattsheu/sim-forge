#!/bin/bash
# 階段 2:不上抬(--pick_mm 0,同階段 1:下指滑入後直接合上指)、沿邊切線插(--chord 1)、指頂在布底下 2mm
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
F="--wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 1 --clear_mm 2 --pick_mm 0"
pgrasp/run2.sh C150 --wide_mm 150 $F &
sleep 100
pgrasp/run2.sh C100 --wide_mm 100 $F &
wait
