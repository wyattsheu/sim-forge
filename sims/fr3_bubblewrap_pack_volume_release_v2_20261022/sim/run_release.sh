#!/bin/bash
# run_release.sh — v2 交付版一條指令跑整鏈(volume 4 mm 包材):
#   四折 + 膠帶(錨點跟著杯 / 包裹走)→ 入箱關蓋 → 搬箱 → 開蓋 → 手 2 整包取出放桌面 →
#   手 1 寬指純摩擦依序掀 yn、yp、xn、xp(放手後片自己攤在桌上)→ 手 2 取杯放旁邊。不用綁定。
#
#   ./run_release.sh final [NAME] [extra]   # 正式版 v2.1(docs/V2_FLOW.md「整鏈驗證」):--quality final --edamp 0.02;約 30~32 分鐘,1280x720,195 s
#   ./run_release.sh fast  [NAME] [extra]   # 開發用:--quality fast --edamp 0;約 11~15 分鐘,960x540(fast 的 x 片 / 杯自轉和 final 不同,見 README §9.2)
#   UNTIL=fold|box|move ./run_release.sh fast K1   # 只跑到四折完 / 入箱關蓋 / 搬完(會自動拿掉取出、x 片、取杯旗標:wrap_vol 的 --takeout 要 --until all)
#   後面多給的旗標原樣傳給 wrap_vol.py(argparse 取最後一次,所以可以覆蓋),例:
#   ./run_release.sh final S1 --save_state ../runs/final_S1/S.npz --at xflaps --save_exit 1   # 跑到 yn、yp 掀完(t = 122.0)存檔就停
#   LOADCHK=0 ./run_release.sh final R1 --load_state ../runs/final_S1/S.npz                    # 從存檔續跑 x 片 + 取杯(final 約 12~15 分鐘)
#
# 輸出:../runs/<mode>_<NAME>/1/(wrap.mp4、wrap_vol.log、wrap.npz、grasp.json、v2.json、key_*.png、stdout.txt、elapsed.txt);
#       跑完整鏈印 v2/table.py 的兩張表(= docs/V2_FLOW.md 表 1 / 表 2 的欄位);final 整鏈另外剪 ../runs/final_<NAME>/short.mp4(v2/cut_short2.sh,約 24 s)。
# GPU:經 run3.sh 開跑 —— 啟動鎖(一次只開一個)、等顯存 < GPU_MAX(預設 29500 MiB)、偵測「PhysX 不報錯但布沒在模擬」並自動重開(docs/SPEEDUP.md §3)。
#      兩個同時開會一起 OOM;和別的 run3.sh 共用一把鎖時設 LOCK=/path/to/.run3_launch.lock。
# ISAAC=/path/to/python.sh 指定直譯器;不設就自動找(find_isaac.sh)。
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$HERE"
MODE=${1:-final}; NAME=${2:-X1}; shift $(( $# >= 2 ? 2 : $# )) || true
# 正式旗標 = docs/V2_FLOW.md「整鏈驗證(v2.1)」:v2/run.sh 的基礎旗標 + 下面 V21
V21="--ut_release_up 1 --v2_xmode tapegrip --v2_h2_free 1 --wide_mm 150 --wide_mm_x 300 --v2_xrel_slide 2"
case "$MODE" in
  final) QUAL="--quality final --edamp 0.02" ;;
  fast)  QUAL="--quality fast --edamp 0" ;;
  *) sed -n 2,13p "$0"; exit 2 ;;
esac
if [ -z "$ISAAC" ]; then source "$HERE/find_isaac.sh"; find_isaac || exit 5; export ISAAC="$ISAAC_PYTHON"; fi
[ "$(id -u)" = 0 ] && export OMNI_KIT_ALLOW_ROOT=1

# = v2/run.sh(run3.sh @demo + 桌面掀法 + 寬指純摩擦 + v2 流程)
V2="--hand2 off --hand2_keep 0 --hold_yp 0 --second 1 --guard_yn 3.5 --guard_n 2 --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --release_watch 1 --grasp_tail_s 1"
WIDE="--grasp_attach 0 --pick_mode wide --wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 1 --clear_mm 2 --pick_mm 0"
FLOW="--tape_follow 1 --takeout 1 --v2_xflaps 1 --v2_hold_cup 1 --extract 1 --extract_mode lift --extract_out_mm 380"
UNTIL=${UNTIL:-all}
# --takeout 1 在 wrap_vol.py 裡 assert --until all;只跑一段時把取出 / x 片 / 扶杯 / 取杯關掉(膠帶 --tape_follow 1 保留)
[ "$UNTIL" != all ] && FLOW="--tape_follow 1 --takeout 0 --v2_xflaps 0 --v2_hold_cup 0 --v2_h2_free 0 --extract 0"

RUN="../runs/${MODE}_${NAME}"; OUT="$RUN/1"
N=1 KS=1 MAXPAR=1 GAP=0 TABLE= ./run3.sh "$RUN" @demo $V2 $WIDE $QUAL $V21 $FLOW --until $UNTIL "$@" || true   # run3.sh 結尾 TABLE 空時回傳 1,成敗看下面的 EXIT 行
grep -q "^EXIT 0" "$OUT/stdout.txt" || { echo "FAIL(見 $OUT/stdout.txt)"; tail -5 "$OUT/stdout.txt"; exit 1; }
grep -q "Traceback" "$OUT/stdout.txt" && { echo "FAIL:Traceback(見 $OUT/stdout.txt)"; grep -A3 Traceback "$OUT/stdout.txt" | tail -5; exit 1; }
grep -n "SUMMARY\|真的入箱了嗎" "$OUT/stdout.txt" | tail -12 || true
if [ "$UNTIL" = all ]; then
  python3 v2/table.py "$RUN" 2>/dev/null | tee "$RUN/TABLE.md" || true
  [ -n "$(ls $RUN/1/*.npz 2>/dev/null | head -1)" ] && python3 v2/rigid.py "$RUN" 2>/dev/null >> "$RUN/TABLE.md" || true
  if [ "$MODE" = final ] && ! echo "$*" | grep -q -- "--load_state"; then
    bash v2/cut_short2.sh "$OUT/wrap.mp4" "$RUN/short.mp4" >/dev/null && echo "short -> $RUN/short.mp4"
  fi
fi
echo "Done -> $OUT"
