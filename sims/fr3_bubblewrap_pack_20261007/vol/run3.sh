#!/bin/bash
# vol/run3.sh NAME [flags...]   同一組旗標開 3 個模擬(各自等 GPU < 29500 MiB),跑完產 NAME/TABLE.md
#   旗標裡 @demo = 正式 demo 旗標(JAW.md / FINAL_PLAN §2 夾爪版,extract6/run.sh 那組,含 --edamp 0.02);
#          @x4   = extract4 旗標(quality/run.sh 那組,QUALITY.md 驗過 fast 的;手 2 attach、無 edamp)
#   {k} 會換成 1/2/3(例 --save_state NAME/S{k}.npz)
#   環境變數:N=3(次數)、KS="1 2 3"(只補跑某幾次)、MAXPAR=3(同時最多幾個)、GPU_MAX=29500、GAP=20(開一個之後隔幾秒才排下一個;真正的啟動序列化靠鎖 speed2/.run3_launch.lock:確認布在動才放鎖)
#            HEAD=3000 / TRIES=6 / STARTUP_S=240:偵測到布沒在模擬或 PhysX 場景壞掉(顯存不夠時會這樣、不報錯)→ 殺掉、等顯存 < GPU_MAX−HEAD 再重開
#   例:./run3.sh speed2/A @demo --quality fast
#       ./run3.sh speed2/R @demo --quality fast --load_state speed2/A/S1.npz
cd "$(dirname "$0")"
NAME=$1; shift
[ -z "$NAME" ] && { sed -n 2,7p "$0"; exit 1; }
DEMO="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3 --grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30 --hand2 jaw --hand2_pad_mm 15 --hand2_keep 1 --hold_yp 1 --extract 1 --guard_yp 2.6 --guard_n 2 --extract_mode slide --extract_out_mm 280 --guard_yn 2.6 --slide_clear_mm 40 --hand1_jaw 1 --extract_grip jaw --edamp 0.02"
X4="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3 --grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30 --hand2 attach --hand2_pad_mm 15 --hand2_keep 1 --hold_yp 1 --extract 1 --guard_yp 2.6 --guard_n 2 --extract_mode slide --extract_out_mm 280 --guard_yn 2.6 --slide_clear_mm 40"
ARGS=(); for x in "$@"; do case "$x" in @demo) ARGS+=($DEMO);; @x4) ARGS+=($X4);; *) ARGS+=("$x");; esac; done
N=${N:-3}; MAXPAR=${MAXPAR:-3}; GPU_MAX=${GPU_MAX:-29500}; GAP=${GAP:-20}; HEAD=${HEAD:-3000}; TRIES=${TRIES:-6}; STARTUP_S=${STARTUP_S:-240}; KS=${KS:-$(seq 1 $N)}; LOCK=${LOCK:-$PWD/speed2/.run3_launch.lock}
mkdir -p "$NAME"
echo "$(date +%F\ %T) run3 $NAME N=$N MAXPAR=$MAXPAR GPU_MAX=$GPU_MAX :: ${ARGS[*]}" | tee -a "$NAME/run3.log"
gpu() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1; }
PIDS=()
for k in $KS; do
  OUT="$NAME/$k"; mkdir -p "$OUT"
  A=(); for x in "${ARGS[@]}"; do A+=("${x//\{k\}/$k}"); done
  # 等:GPU 顯存 < 門檻 且 自己這批同時在跑的 < MAXPAR
  while :; do
    nrun=0; for p in "${PIDS[@]}"; do kill -0 $p 2>/dev/null && nrun=$((nrun+1)); done
    [ "$nrun" -lt "$MAXPAR" ] && [ "$(gpu)" -lt "$GPU_MAX" ] && break
    sleep 20
  done
  (
    t0=$(date +%s); echo "$(date +%T) start $k gpu $(gpu) MiB" >> "$NAME/run3.log"
    rc=-1
    for try in $(seq 1 $TRIES); do
      # 啟動序列化(跨批次共用鎖):拿到鎖 → 等顯存 → 開 → 確認布在動(前 3 筆量測)才放鎖;同時兩個一起開會一起 OOM(PhysX 不報錯就不模擬布)
      exec 9>>"$LOCK"; flock 9
      thr=$GPU_MAX; [ $try -gt 1 ] && thr=$((GPU_MAX-HEAD))
      while [ "$(gpu)" -ge "$thr" ]; do sleep 20; done
      t0=$(date +%s); echo "CMD: wrap_vol.py ${A[*]} --out $OUT" > "$OUT/stdout.txt"
      [ $try -gt 1 ] && echo "$(date +%T) retry $k try $try gpu $(gpu) MiB" >> "$NAME/run3.log"
      /isaac-sim/python.sh wrap_vol.py "${A[@]}" --out "$OUT" >> "$OUT/stdout.txt" 2>&1 9>&- & py=$!
      bad=""; checked=0
      # 壞掉偵測(顯存不夠時 PhysX 不報錯就不模擬布,或 "Scene state is corrupted" 卡住):
      #   (1) log 出現 Scene state is corrupted / out of memory;(2) 前 3 筆量測布沒在動(整鏈:t≈1 s 邊長比還是 [1.000,1.000];續跑:3 筆逐字相同);
      #   (3) 啟動 STARTUP_S 秒還沒有第一筆量測。→ 殺掉、等顯存 < GPU_MAX − HEAD 再從頭重開(最多 TRIES 次)
      while kill -0 $py 2>/dev/null; do
        if grep -qE "Scene state is corrupted|out of memory|cudaErrorMemoryAllocation" "$OUT/stdout.txt"; then bad="PhysX 場景壞掉/顯存不足"; break; fi
        if [ $checked = 0 ]; then
          L=$(grep -E "^t=" "$OUT/stdout.txt" | head -3 | sed -E 's/^t= *[0-9.]+ +[^|]*bbox//')
          if [ "$(echo "$L" | grep -c .)" -ge 3 ]; then
            if echo "$L" | sed -n 3p | grep -q "邊長比 \[1.000,1.000\]" || { grep -q "\[load\]" "$OUT/stdout.txt" && [ "$(echo "$L" | sort -u | wc -l)" -eq 1 ]; }; then bad="布沒在模擬"; break; fi
            checked=1; flock -u 9
          elif [ $(( $(date +%s) - t0 )) -gt $STARTUP_S ]; then bad="啟動 ${STARTUP_S} s 沒有量測"; break; fi
        fi
        sleep 10
      done
      if [ -n "$bad" ]; then
        pkill -P $py 2>/dev/null; kill $py 2>/dev/null; sleep 5; pkill -9 -P $py 2>/dev/null; sleep 10
        echo "$(date +%T) FROZEN $k try $try($bad,gpu $(gpu) MiB)→ 等顯存 < $((GPU_MAX-HEAD)) 再重開" >> "$NAME/run3.log"
        mv "$OUT/stdout.txt" "$OUT/frozen_try$try.txt"; flock -u 9
        continue
      fi
      flock -u 9; wait $py; rc=$?; break
    done
    t1=$(date +%s); echo "EXIT $rc" >> "$OUT/stdout.txt"; echo "elapsed $((t1-t0))" > "$OUT/elapsed.txt"
    echo "$(date +%T) done $k rc $rc elapsed $((t1-t0)) s" >> "$NAME/run3.log"
  ) &
  PIDS+=($!)
  sleep "$GAP"
done
wait
python3 speed2/table3.py "$NAME" > "$NAME/TABLE.md"; cat "$NAME/TABLE.md"
