#!/bin/bash
# 18 組正式精度(dt 1/240 solver 128):fast 的滑動 7~11mm 在 final 降到 3~4mm(fin/),全表重跑
cd "$(dirname "$0")"
while pgrep -f "queue3.sh" > /dev/null; do sleep 20; done
./run_probe.sh sweep_fin --dt 0.004166667 --solver 128
