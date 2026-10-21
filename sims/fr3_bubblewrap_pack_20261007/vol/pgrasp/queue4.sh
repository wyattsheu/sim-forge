#!/bin/bash
# 指深 40 重跑(d40 第一次桌緣只懸空 30mm,指前緣 45mm 在桌面下 → 上指把布壓進桌面,作廢)
cd "$(dirname "$0")"
while pgrep -f "queue[23].sh" > /dev/null; do sleep 20; done
./run_probe.sh d40 --Ls 150,200 --mus 1.0,2.0 --gaps 3.0,2.5 --fd_mm 40 --insert_mm 45 --overhang_mm 55
./run_probe.sh oh55 --Ls 150,200 --mus 1.0,2.0 --gaps 3.0,2.5 --overhang_mm 55
