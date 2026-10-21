#!/bin/bash
# 第 2 批:等 B 批次跑完 → Y(yp 第二片,綁定,1 次);等 W 批次跑完 → P(塑性對照:放錨點前 rest = 折好形狀、錨點全放,1 次)
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
( while pgrep -f "run3.sh table/B " >/dev/null; do sleep 30; done; N=1 MAXPAR=1 table/run.sh Y attach --second 1 > table/Y.log 2>&1 ) &
( while pgrep -f "run3.sh table/W " >/dev/null; do sleep 30; done; N=1 MAXPAR=1 table/run.sh P attach --plastic_on_fold 1 --ut_tape 0 > table/P.log 2>&1 ) &
wait
