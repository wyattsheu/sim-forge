#!/bin/bash
# 補充:final x 片等久一點(--v2_xcut_s 6,讓拆膠帶後的片先自己彈開、停下來再判斷)+ yp/xp 放手後觀察 10 s(--grasp_tail_s 8.5);等 v2/queue.sh 的對照組開了、有空位才開
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
nv2() { pgrep -f "kit/python/bin/python3 wrap_vol.py.*--out v2/" | wc -l; }
while [ ! -f v2/ctl_fixed/1/stdout.txt ] || [ "$(nv2)" -ge 2 ]; do sleep 20; done
N=1 MAXPAR=1 v2/run.sh X --quality final --edamp 0.02 --v2_xcut_s 6 --grasp_tail_s 8.5 > v2/X.log 2>&1
