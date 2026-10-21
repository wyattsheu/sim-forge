# source 進來用:等 GPU < 27000 MiB 且連續 3 次(間隔 10 s)都低於(本程序約 3~4 GB,開完總量 < 29500)。
while true; do
  ok=0
  for k in 1 2 3; do [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 27000 ] && ok=$((ok+1)); sleep 10; done
  [ $ok -eq 3 ] && break
done
