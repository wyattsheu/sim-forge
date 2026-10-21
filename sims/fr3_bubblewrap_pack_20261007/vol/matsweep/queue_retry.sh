#!/bin/bash
# E5e2_d0.1 第一次在 3 組並行時 GPU OOM(Texture creation failed)→ 等到 matsweep 模擬 < 2 個才重開
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
sleep 60
until [ "$(ps -eo comm,args | grep '^python3 .*--out matsweep/' | wc -l)" -lt 2 ] && ! pgrep -f "run.sh E2e3_d0.3|run.sh E5e2_d0.3_over60|run.sh E1e3_d0.3_over60" >/dev/null; do sleep 30; done
bash matsweep/run.sh E5e2_d0.1 --young 5e2 --areal 0.1
