# source 進來用:拿鎖 → 等 GPU < 25500 MiB(本程序約 3~4 GB,開完總量 < 29500)(呼叫端自己決定何時放鎖)。一次只跑一個(協調者指示)。
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 25500 ]; do sleep 15; done
