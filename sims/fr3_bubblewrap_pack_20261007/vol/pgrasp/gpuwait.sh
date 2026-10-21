# source 進來用:等 GPU 連續 3 次(間隔 10 s)< GPU_START_MAX(預設 26500,比門檻 29500 保守:本程序要 ~5 GB,免得擠爆別人)(共用 matsweep 啟動鎖,開跑後 75 s 放鎖)
exec 9>/tmp/claude-0/-isaac-sim-test-scripts-manip-fr3-handoff-20260929/c7e55632-bf8d-46a1-89a0-934334fed54b/scratchpad/gpu_start.lock
flock 9
_ok=0
while [ $_ok -lt 3 ]; do
  if [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt ${GPU_START_MAX:-26500} ]; then _ok=$((_ok+1)); else _ok=0; fi
  sleep 10
done
( sleep 75; flock -u 9 ) &
