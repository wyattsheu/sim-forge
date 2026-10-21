#!/bin/bash
# 弧半徑對照:kR 1.0(弧長 = 材料長)/ 0.8(wrap_vol arc_k)
cd "$(dirname "$0")"
while pgrep -f "queue2.sh" > /dev/null; do sleep 20; done
./run_probe.sh kR10 --Ls 150,200 --mus 1.0,2.0 --gaps 3.0 --kR 1.0
