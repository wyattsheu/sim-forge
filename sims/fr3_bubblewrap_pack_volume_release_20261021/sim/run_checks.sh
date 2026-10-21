#!/bin/bash
# run_checks.sh — volume 版的自動判讀(純 CPU,系統 python3 + numpy/scipy 即可;沒有就用 /isaac-sim/python.sh)。
#   ./run_checks.sh                    # 只跑工具自測:vol_pen.py --selftest、layer_gap.py --selftest
#   ./run_checks.sh ../runs/final_X1   # 自測 + 對一個 wrap_vol 輸出目錄(有 wrap_vol.log)逐項判讀
#   ./run_checks.sh RUN --json out.json
# 判讀項目、門檻與來源:checks/README.md(「volume 版」一節;surface 項目在這個交付版不適用)。exit 0 = 沒有 FAIL。
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$HERE"
if python3 -c "import numpy, scipy.spatial" 2>/dev/null; then PY=python3; else PY=/isaac-sim/python.sh; fi
export PYTHONDONTWRITEBYTECODE=1
FAILN=0
chk(){ local name=$1 pat=$2; shift 2; out=$("$@" 2>&1); rc=$?
  if [ $rc -eq 0 ] && grep -q "$pat" <<<"$out"; then echo "PASS  $name"; else echo "FAIL  $name(rc=$rc:$(tail -1 <<<"$out"))"; FAILN=$((FAILN+1)); fi; }
chk "vol_pen.py --selftest"   "SELFTEST PASS" $PY vol_pen.py --selftest
chk "layer_gap.py --selftest" "ALL PASS"      $PY layer_gap.py --selftest
for f in wrap_vol.py volcommon.py grasp_plan.py fold_variants.py cloth_iface.py; do
  chk "$f 語法" "" $PY -c "import ast,sys; ast.parse(open('$f').read())"; done
if [ -n "$1" ]; then
  $PY checks/run_checks.py "$1" --kind vol "${@:2}" || FAILN=$((FAILN+1))
fi
echo "run_checks.sh:FAIL $FAILN 項"
[ $FAILN -eq 0 ]
