#!/bin/bash
# 影片:最佳組 D40(L150 mu2.0 g3.0,fast)+ 對照 D20(同組,overhang 55)
cd "$(dirname "$0")"
while pgrep -f "queue[45].sh" > /dev/null; do sleep 20; done
./run_probe.sh v_d40 --Ls 150 --mus 2.0 --gaps 3.0 --fd_mm 40 --insert_mm 45 --overhang_mm 55 --video
./run_probe.sh v_d20 --Ls 150 --mus 2.0 --gaps 3.0 --overhang_mm 55 --video
