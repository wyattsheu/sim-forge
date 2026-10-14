#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
for d in "$@"; do L=$d/wrap_vol.log; echo "== $d"
 grep -o "wall [0-9].*= [0-9.]*" $L
 grep "fast_pts\]" $L
 grep -E "^  (fold_end|final) " $L | sed -E 's/ \| 杯頂上.*//; s/含杯 [0-9x]+ \| //'
 grep "全程最大" $L
 grep -o "超出內腔 [0-9]*" $L | sort | uniq -c | tr '\n' ' '; echo
 grep -E "^\s+\[(yn|yp)\] ATTACH" $L
 [ -f $d/wrap.npz ] && python3 jitter.py $d/wrap.npz $([ "$2" ] || true) | tail -1
done
