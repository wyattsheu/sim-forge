#!/bin/bash
# v2 正式批次(全域同時最多 2 個 v2 模擬,一個一個補):
#   B = fast 3 次(v2/run.sh 預設:--quality fast --edamp 0 --guard_yn 3.5)
#   F = final 2 次(--quality final --edamp 0.02)
#   ctl_fixed = 膠帶對照(--tape_follow 2 錨點固定,只跑到搬完)
# (v2/A = 前一版:沒有 --v2_hold_cup、x 片斜靠在杯側也硬夾 → A/2 推杯 52 mm、A/3 夾 x 片把杯拖走 115~355 mm;保留當紀錄)
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
nv2() { pgrep -f "kit/python/bin/python3 wrap_vol.py.*--out v2/" | wc -l; }
for spec in "B 1" "F 1" "F 2" "B 2" "B 3" "ctl 1"; do
  set -- $spec
  while [ "$(nv2)" -ge 2 ]; do sleep 20; done
  case $1 in
    B) KS="$2" N=3 MAXPAR=1 v2/run.sh B > v2/B$2.log 2>&1 & ;;
    F) KS="$2" N=2 MAXPAR=1 v2/run.sh F --quality final --edamp 0.02 > v2/F$2.log 2>&1 & ;;
    ctl) N=1 MAXPAR=1 ./run3.sh v2/ctl_fixed @demo --quality fast --edamp 0 --grasp 0 --extract 0 --hand2 off --until move --tape_follow 2 > v2/ctl_fixed.log 2>&1 & ;;
  esac
  sleep 150    # 等 python 起來(nv2 才算得到)
done
wait
python3 v2/table.py v2/B v2/F > v2/TABLE.md; cat v2/TABLE.md
