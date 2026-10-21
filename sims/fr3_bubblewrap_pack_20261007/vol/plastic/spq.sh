#!/bin/bash
# plastic/spq.sh "args1" "args2" ...  依序跑 probe_spread(共用 run3 啟動鎖、GPU < GPU_MAX、OOM/Scene corrupted 自動重跑)
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
GPU_MAX=${GPU_MAX:-29500}; LOCK=$PWD/speed2/.run3_launch.lock
gpu() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1; }
for args in "$@"; do
  for try in 1 2 3 4 5 6 7 8; do
    exec 9>>"$LOCK"; flock 9
    thr=$GPU_MAX; [ $try -gt 1 ] && thr=$((GPU_MAX-3000))
    while [ "$(gpu)" -ge "$thr" ]; do sleep 20; done
    f=plastic/spread/stdout_$(echo "$args" | tr -d ' -' | tr '/' '_').txt
    echo "$(date +%T) start [$args] try $try gpu $(gpu)" >> plastic/spread/queue.log
    /isaac-sim/python.sh plastic/probe_spread.py $args > $f 2>&1 9>&- & py=$!
    sleep 60; flock -u 9
    wait $py
    if grep -qE "Scene state is corrupted|out of memory|out-of-memory|failed to allocate|cudaErrorMemoryAllocation" $f || ! grep -q RESULT $f; then
      echo "$(date +%T) BAD [$args] try $try" >> plastic/spread/queue.log; sleep 30; continue; fi
    grep RESULT $f >> plastic/spread/queue.log; break
  done
done
