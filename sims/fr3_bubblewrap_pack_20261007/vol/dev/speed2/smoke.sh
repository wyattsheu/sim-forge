#!/bin/bash
# 煙霧測試:整鏈 fast 存檔即停 → 續跑 --until yn
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/dev
N=1 MAXPAR=1 GAP=0 ./run3.sh speed2/smokeA @demo --quality fast --save_state speed2/smokeA/S.npz --save_exit 1
N=1 MAXPAR=1 GAP=0 ./run3.sh speed2/smokeR @demo --quality fast --load_state speed2/smokeA/S.npz --until yn
