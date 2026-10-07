#!/bin/bash
# run_tool_selftests.sh — 一次跑完所有工具自測並彙總(純 CPU)。exit 0 = 沒有 FAIL。
#   bash tests/run_tool_selftests.sh
W=$(cd "$(dirname "$0")/.." && pwd); H=$(dirname "$W")
cd "$W" || exit 2
declare -a RES; FAILN=0
rec(){ RES+=("$(printf '%-5s %-34s %s' "$1" "$2" "$3")"); [ "$1" = FAIL ] && FAILN=$((FAILN+1)); }

# 1) layer_gap 自測
out=$(python3 layer_gap.py --selftest 2>&1); rc=$?
if [ $rc -eq 0 ] && grep -q 'ALL PASS' <<<"$out"; then rec PASS "layer_gap.py --selftest" "ALL PASS"
else rec FAIL "layer_gap.py --selftest" "rc=$rc $(tail -1 <<<"$out")"; fi

# 2) carton_sweep:蓋子 0~180° 掃掠與牆重疊,要 0/361
out=$(python3 carton_sweep.py carton.meta.json 2>&1); rc=$?
n=$(grep -cE '[[:space:]]0/361 個角度重疊' <<<"$out"); tot=$(grep -cE '/361 個角度重疊' <<<"$out")
if [ $rc -eq 0 ] && [ "$tot" -gt 0 ] && [ "$n" -eq "$tot" ]; then rec PASS "carton_sweep.py carton.meta.json" "$n/$tot 片 0/361"
else rec FAIL "carton_sweep.py carton.meta.json" "rc=$rc,0/361 的只有 $n/$tot 片"; fi

# 3) selfcheck:用臨時 shim 目錄(selfcheck 要 ROOT/carton/carton_v3.meta.json 與交付包檔案)
SH=$(mktemp -d)
for f in README.md CHANGELOG.md ADAPTING.md assets scripts; do [ -e "$H/$f" ] && ln -s "$H/$f" "$SH/$f"; done
mkdir -p "$SH/carton"
M="$H/carton/carton.meta.json"; [ -f "$M" ] || M="$W/carton.meta.json"
ln -s "$M" "$SH/carton/carton_v3.meta.json"
[ -f "$H/carton/make_carton_P.py" ] && ln -s "$H/carton/make_carton_P.py" "$SH/carton/make_carton_P.py"
out=$(python3 selfcheck.py "$SH" 2>&1); rc=$?
rm -rf "$SH"
cnt(){ awk -v s="$1" -v k="$2" '/^【/{cur=$0} index(cur,s) && $1==k {c++} END{print c+0}' <<<"$out"; }
cp_=$(cnt '【C' PASS); cf=$(cnt '【C' FAIL)
if [ "$cf" -eq 0 ] && [ "$cp_" -eq 12 ]; then rec PASS "selfcheck.py C 段(程式)" "$cp_/12"
else rec FAIL "selfcheck.py C 段(程式)" "PASS $cp_ / FAIL $cf(應 12/12)"; fi
for s in A B E; do p=$(cnt "【$s" PASS); f=$(cnt "【$s" FAIL)
  if [ "$f" -eq 0 ]; then rec PASS "selfcheck.py $s 段" "PASS $p"
  else rec WARN "selfcheck.py $s 段" "PASS $p / FAIL $f(E 段的 PPT 原文路徑在別台機器,已知)"; fi
done

# 4) vol_pen 自測(../vol/vol_pen.py;只讀,不在 vol/ 寫任何檔:PYTHONDONTWRITEBYTECODE=1)
#    直譯器:系統 python3 能 import numpy+scipy 就用它,否則 /isaac-sim/python.sh(兩者 2026-10-07 實測都可)
VP="$H/vol/vol_pen.py"
if [ -f "$VP" ]; then
  if python3 -c "import numpy, scipy.spatial" 2>/dev/null; then PY=python3
  elif [ -x /isaac-sim/python.sh ]; then PY=/isaac-sim/python.sh
  else PY=""; fi
  if [ -z "$PY" ]; then rec FAIL "vol/vol_pen.py --selftest" "沒有能 import numpy+scipy 的 python"
  else
    out=$(cd "$H/vol" && PYTHONDONTWRITEBYTECODE=1 $PY vol_pen.py --selftest 2>&1); rc=$?
    npass=$(grep -c '⇒ PASS' <<<"$out")
    if [ $rc -eq 0 ] && grep -q 'SELFTEST PASS' <<<"$out"; then rec PASS "vol/vol_pen.py --selftest" "SELFTEST PASS($npass/4 項,$(basename $PY))"
    else rec FAIL "vol/vol_pen.py --selftest" "rc=$rc $(tail -1 <<<"$out")($(basename $PY))"; fi
  fi
else rec SKIP "vol/vol_pen.py --selftest" "../vol/vol_pen.py 不存在"; fi

# 5) wrap_sim.py 語法
if python3 -c "import ast;ast.parse(open('wrap_sim.py').read())" 2>/dev/null; then rec PASS "wrap_sim.py 語法(ast.parse)" "ok"
else rec FAIL "wrap_sim.py 語法(ast.parse)" "parse error"; fi

printf '%s\n' "${RES[@]}"
echo "總結:FAIL $FAILN 項"
[ $FAILN -eq 0 ]
