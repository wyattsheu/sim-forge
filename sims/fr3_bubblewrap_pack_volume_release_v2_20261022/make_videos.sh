#!/bin/bash
# 重新產生 v2 交付影片。videos/ 已經附在 git 與 tgz 裡,這支是「重產」用。全部經 sim/run3.sh 開跑(啟動鎖、GPU 門檻、凍住自動重開)。
#
#   ./make_videos.sh                 # ★ 正式版 v2.1:sim/run_release.sh final → VOL_v2_full.mp4 + DEMO_v2_short.mp4(約 32 分鐘)
#   ./make_videos.sh --fast          # 同上但 fast(約 15 分鐘;960x540,只給開發看 → videos/fast/,不覆蓋正式影片)
#   ./make_videos.sh --table         # 不入箱、直接在桌面掀:DEMO_unwrap_table_short.mp4(寬指,W)+ VOL_unwrap_table_yp.mp4(yn + yp,綁定版,Y)(約 12 分鐘)
#   ./make_videos.sh --pgrasp        # 箱內寬指純摩擦掀 yn(片翻不過壁的證據):VOL_pgrasp.mp4 + DEMO_pgrasp_short.mp4(約 9 分鐘)
#   ./make_videos.sh --x2            # x 片第二輪比較 VOL_v2x2_compare.mp4:final 存檔 1 次 + 6 次續跑(約 2 小時)
#   ./make_videos.sh --variants      # VARIANTS_grid.mp4:24 種折序各跑 --until box 再拼格(約 2 小時)
#   ./make_videos.sh --montage DEV   # DEMO_1~6 + DEMO_ALL(v1 那套):純 ffmpeg 剪接,素材在開發資料夾 DEV(= handoff_20260929)
#
#   VIDEO_DIR=/tmp/v ./make_videos.sh   # 輸出到別處(預設 ./videos)
#   ISAAC=/path/to/python.sh ./make_videos.sh
#   一次只跑一個;run3.sh 的 GPU_MAX(29500 MiB)/ LOCK 可用環境變數改。
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VID="${VIDEO_DIR:-$HERE/videos}"; mkdir -p "$VID"
cd "$HERE/sim"
if [ -z "$ISAAC" ]; then source find_isaac.sh; find_isaac || exit 5; export ISAAC="$ISAAC_PYTHON"; fi
[ "$(id -u)" = 0 ] && export OMNI_KIT_ALLOW_ROOT=1
# 開發版 v2/run.sh、table/run.sh 的基礎旗標(run_release.sh 也是這組)
V2="--hand2 off --hand2_keep 0 --hold_yp 0 --second 1 --quality fast --edamp 0 --guard_yn 3.5 --guard_n 2 --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --release_watch 1 --grasp_tail_s 1"
WIDE="--grasp_attach 0 --pick_mode wide --wide_mm 150 --wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 1 --clear_mm 2 --pick_mm 0"
case "${1:-}" in
  "")
    ./run_release.sh final MV
    cp ../runs/final_MV/1/wrap.mp4 "$VID/VOL_v2_full.mp4"
    cp ../runs/final_MV/short.mp4  "$VID/DEMO_v2_short.mp4" ;;
  --fast)
    ./run_release.sh fast MV
    mkdir -p "$VID/fast"; cp ../runs/fast_MV/1/wrap.mp4 "$VID/fast/VOL_v2_full_fast.mp4"
    bash v2/cut_short2.sh ../runs/fast_MV/1/wrap.mp4 "$VID/fast/DEMO_v2_short_fast.mp4" ;;
  --table)
    # = docs/TABLE_UNWRAP.md 重現:W(寬指純摩擦,只掀 yn)、Y(綁定版,yn + yp)
    N=1 table/run.sh W wide;               bash table/cut_short.sh table/W/1/wrap.mp4 "$VID/DEMO_unwrap_table_short.mp4"
    N=1 table/run.sh Y attach --second 1;  cp table/Y/1/wrap.mp4 "$VID/VOL_unwrap_table_yp.mp4" ;;
  --pgrasp)
    # = docs/PGRASP.md 階段 2 的 C150(箱內寬指純摩擦掀 yn、越壁 30 mm、放手後看 10 s);開發版 pgrasp/run2.sh 的旗標,改走 run3.sh
    SWEEP="--hand2 off --hand2_keep 0 --hold_yp 0 --extract 0 --second 0 --quality fast --edamp 0 --guard_yn 3.5 --guard_n 2 --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --arc2_over_cap 0 --arc2_over_mm 30 --release_watch 1 --grasp_tail_s 8.5"
    N=1 MAXPAR=1 TABLE= ./run3.sh pgrasp/C150 @demo $SWEEP $WIDE || true
    cp pgrasp/C150/1/wrap.mp4 "$VID/VOL_pgrasp.mp4"
    bash pgrasp/cut_short.sh pgrasp/C150/1/wrap.mp4 "$VID/DEMO_pgrasp_short.mp4" ;;
  --x2)
    # = docs/V2_FLOW.md「x 片 第二輪」重現:final 跑到 x 片開始(t = 122.0)存檔,再續跑 D / E / F / G / H / GH 各 1 次
    N=1 v2/runx.sh S_final --quality final --edamp 0.02 --ut_release_up 1 --save_state 'v2/x/S_final/S{k}.npz' --at xflaps --save_exit 1
    B="--quality final --edamp 0.02 --ut_release_up 1 --load_state v2/x/S_final/S1.npz --v2_xmode tapegrip"
    export LOADCHK=0 N=1 MAXPAR=1
    v2/runx.sh D_final  $B
    v2/runx.sh E_final  $B --v2_h2_free 1
    v2/runx.sh F_final  $B --v2_h2_free 1 --wide_mm 300
    v2/runx.sh G_final  $B --v2_h2_free 1 --wide_mm 300 --v2_xpress_s 2
    v2/runx.sh H_final  $B --v2_h2_free 1 --wide_mm 300 --v2_xrel_slide 1
    v2/runx.sh GH_final $B --v2_h2_free 1 --wide_mm 300 --v2_xrel_slide 1 --v2_xpress_s 2 --v2_xpress_depth_mm 4
    python3 v2/tablex2.py v2/x/D_final v2/x/E_final v2/x/F_final v2/x/G_final v2/x/H_final v2/x/GH_final | tee v2/x/TABLE_x2.md
    bash v2/cut_x.sh "$VID/VOL_v2x2_compare.mp4" "D old (hand2 holds)|v2/x/D_final/1/wrap.mp4" "E hand2 lets go|v2/x/E_final/1/wrap.mp4" \
      "F E+wide300|v2/x/F_final/1/wrap.mp4" "G F+press|v2/x/G_final/1/wrap.mp4" "H F+slide release|v2/x/H_final/1/wrap.mp4" "GH H+press|v2/x/GH_final/1/wrap.mp4" ;;
  --variants)
    python3 fold_variants.py --orders
    python3 fold_variants.py --run --ids 'o_*'
    python3 fold_variants.py --csv
    python3 fold_variants.py --video
    cp videos/VARIANTS_grid.mp4 "$VID/VARIANTS_grid.mp4" ;;
  --montage)
    DEV="${2:?usage: $0 --montage /path/to/handoff_20260929}"
    sed "s#^R=.*#R=$DEV#" make_demo_videos.sh > /tmp/make_demo_videos.$$.sh
    bash /tmp/make_demo_videos.$$.sh; rm -f /tmp/make_demo_videos.$$.sh
    cp "$DEV"/work/videos/demo/DEMO_{1,2,3,4,5,6}_*.mp4 "$DEV"/work/videos/demo/DEMO_ALL.mp4 "$DEV"/work/videos/demo/DEMO_INDEX.md "$VID/" ;;
  *) sed -n 2,15p "$0"; exit 2 ;;
esac
echo "Done -> $VID"; ls -la "$VID"
