# source 進來用:watchdog <python.sh 的 pid> <stdout>:開跑前 60 s 內 log 出現 GPU OOM / 場景壞掉 → 殺掉自己這個模擬(只殺傳進來的 pid 與其子程序)
_wp=$1; _wf=$2
( for _i in $(seq 1 30); do
    sleep 3; kill -0 $_wp 2>/dev/null || exit 0
    if grep -qi "out-of-memory\|out of memory\|failed to allocate\|OUT_OF_DEVICE_MEMORY\|Scene state is corrupted" "$_wf" 2>/dev/null; then
      echo "WATCHDOG: GPU OOM → kill $_wp" >> "$_wf"; pkill -P $_wp 2>/dev/null; kill $_wp 2>/dev/null; exit 0
    fi
  done ) &
