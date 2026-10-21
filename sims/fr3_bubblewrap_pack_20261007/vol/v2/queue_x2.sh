#!/bin/bash
# [v2x] 全域最多 MAX(2)個本批模擬:每一行 "NAME K 旗標..." 等到 v2/x/ 底下在跑的 wrap_vol < MAX 才開 N=1 KS=K v2/runx.sh(GPU 門檻 / 啟動鎖照 run3x)
# usage: v2/queue_x2.sh jobs.txt
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
MAX=${MAX:-2}
while read -r name k flags; do
  [ -z "$name" ] && continue; case "$name" in \#*) continue;; esac
  while :; do
    # 已開但還沒起模擬的 run3x(在等 GPU / 鎖)也算一個
    pend=$(( $(pgrep -fc "^/bin/bash v2/run3x.sh v2/x/") / 2 ))
    [ "$pend" -lt "$MAX" ] && break; sleep 20
  done
  echo "$(date +%T) launch $name/$k :: $flags"
  N=$k KS=$k TABLE= eval v2/runx.sh $name $flags > v2/x_${name}_$k.log 2>&1 &
  sleep 30
done < "$1"
wait
