#!/bin/bash
# 找滑動來源:指深 40 / 不壓縮 / 正式精度(L150,L200 x mu 1.0,2.0)
cd "$(dirname "$0")"
while pgrep -f "queue1.sh" > /dev/null; do sleep 20; done
./run_probe.sh d40 --Ls 150,200 --mus 1.0,2.0 --gaps 3.0,2.5 --fd_mm 40 --insert_mm 45
./run_probe.sh g40 --Ls 150,200 --mus 1.0,2.0 --gaps 4.0,3.5
./run_probe.sh fin --Ls 150,200 --mus 1.0,2.0 --gaps 3.0 --dt 0.004166667 --solver 128
