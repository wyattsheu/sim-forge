# source 進來用:拿鎖 → 等 GPU < 29500 → 回傳(呼叫端開跑後 60 s 再放鎖,讓顯存先長出來,避免多個同時開)
exec 9>/tmp/claude-0/-isaac-sim-test-scripts-manip-fr3-handoff-20260929/c7e55632-bf8d-46a1-89a0-934334fed54b/scratchpad/gpu_start.lock
flock 9
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 29500 ]; do sleep 10; done
( sleep 75; flock -u 9 ) &
