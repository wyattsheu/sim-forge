#!/bin/bash
# vol/run3.sh NAME [flags...]   同一組旗標開 3 個模擬(各自等 GPU < 29500 MiB),跑完產 NAME/TABLE.md
#   旗標裡 @demo = 正式 demo 旗標(JAW.md / FINAL_PLAN §2 夾爪版,extract6/run.sh 那組);{k} 會換成 1/2/3(例 --save_state NAME/S{k}.npz)
#   環境變數:N=3(次數)、MAXPAR=3(同時最多幾個,另有優先模擬在跑時可設 1)、GPU_MAX=29500、GAP=90(開一個之後隔幾秒才檢查下一個,讓顯存先漲上來)
#   例:./run3.sh speed2/A @demo --quality fast
#       ./run3.sh speed2/R @demo --quality fast --load_state speed2/A/S1.npz
cd "$(dirname "$0")"
NAME=$1; shift
[ -z "$NAME" ] && { sed -n 2,7p "$0"; exit 1; }
DEMO="--sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 --second 1 --young 2e3 --grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30 --hand2 jaw --hand2_pad_mm 15 --hand2_keep 1 --hold_yp 1 --extract 1 --guard_yp 2.6 --guard_n 2 --extract_mode slide --extract_out_mm 280 --guard_yn 2.6 --slide_clear_mm 40 --hand1_jaw 1 --extract_grip jaw --edamp 0.02"
ARGS=(); for x in "$@"; do if [ "$x" = "@demo" ]; then ARGS+=($DEMO); else ARGS+=("$x"); fi; done
N=${N:-3}; MAXPAR=${MAXPAR:-3}; GPU_MAX=${GPU_MAX:-29500}; GAP=${GAP:-90}
mkdir -p "$NAME"
echo "$(date +%F\ %T) run3 $NAME N=$N MAXPAR=$MAXPAR GPU_MAX=$GPU_MAX :: ${ARGS[*]}" | tee -a "$NAME/run3.log"
gpu() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1; }
PIDS=()
for k in $(seq 1 $N); do
  OUT="$NAME/$k"; mkdir -p "$OUT"
  A=(); for x in "${ARGS[@]}"; do A+=("${x//\{k\}/$k}"); done
  # 等:GPU 顯存 < 門檻 且 自己這批同時在跑的 < MAXPAR
  while :; do
    nrun=0; for p in "${PIDS[@]}"; do kill -0 $p 2>/dev/null && nrun=$((nrun+1)); done
    [ "$nrun" -lt "$MAXPAR" ] && [ "$(gpu)" -lt "$GPU_MAX" ] && break
    sleep 20
  done
  (
    t0=$(date +%s); echo "CMD: wrap_vol.py ${A[*]} --out $OUT" > "$OUT/stdout.txt"
    echo "$(date +%T) start $k gpu $(gpu) MiB" >> "$NAME/run3.log"
    /isaac-sim/python.sh wrap_vol.py "${A[@]}" --out "$OUT" >> "$OUT/stdout.txt" 2>&1; rc=$?
    t1=$(date +%s); echo "EXIT $rc" >> "$OUT/stdout.txt"; echo "elapsed $((t1-t0))" > "$OUT/elapsed.txt"
    echo "$(date +%T) done $k rc $rc elapsed $((t1-t0)) s" >> "$NAME/run3.log"
  ) &
  PIDS+=($!)
  [ "$k" -lt "$N" ] && sleep "$GAP"
done
wait
python3 speed2/table3.py "$NAME" > "$NAME/TABLE.md"; cat "$NAME/TABLE.md"
