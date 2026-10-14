#!/bin/bash
# 用 out_ga3 的 args 重跑:run.sh <out> <until> [額外旗標...]
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
OUT=$1; UNTIL=$2; shift 2
BASE=$(python3 - "$OUT" "$UNTIL" <<'PY'
import ast,sys
d=ast.literal_eval(open("grasp/out_ga3/wrap_vol.log").readlines()[1].split("args:",1)[1].strip())
d["out"]=sys.argv[1]; d["until"]=sys.argv[2]
print(" ".join("--%s %s"%(k, v if v!="" else "''") for k,v in d.items()))
PY
)
eval /isaac-sim/python.sh wrap_vol.py $BASE "$@" > /dev/null 2>speed/$(basename $OUT).err
