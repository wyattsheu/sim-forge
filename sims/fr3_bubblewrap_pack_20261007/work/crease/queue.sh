#!/bin/bash
# 依序跑(一次一個),每個開跑前等 GPU。用法: ./queue.sh "args1" "args2" ...   (args 給 probe 腳本,第一個字是腳本名)
# GPU OOM(PhysX "out-of-memory")的那次作廢重跑,最多 4 次。
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/work
for A in "$@"; do
  for TRY in $(seq 1 15); do
    source crease/gpuwait.sh
    echo "[$(date +%T)] start $A (gpu $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)) try $TRY"
    /isaac-sim/python.sh crease/$A > /dev/null 2> crease/logs/last_stderr.txt
    RC=$?
    if grep -q "out-of-memory\|failed to allocate" crease/logs/last_stderr.txt; then echo "[$(date +%T)] OOM   $A -> retry"; sleep 60; continue; fi
    echo "[$(date +%T)] done  $A rc=$RC"
    grep -E "\[Error\]" crease/logs/last_stderr.txt | grep -v "carb.windowing" | cut -c1-300 | sort | uniq -c | sort -rn | head -8 > "crease/logs/err_$(echo $A | tr -c "A-Za-z0-9_.-" "_").txt"
    grep -l Traceback crease/logs/last_stderr.txt && tail -20 crease/logs/last_stderr.txt
    break
  done
done
