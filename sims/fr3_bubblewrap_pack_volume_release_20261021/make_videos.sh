#!/bin/bash
# 重新產生交付影片。這個交付版的 videos/ 已經附在 git 與 tgz 裡(使用者 2026-10-21 要求),這支是「重產」用。
#
#   ./make_videos.sh                 # 正式版 demo:sim/run_release.sh final → VOL_twohand_extract.mp4 + DEMO_twohand_extract_short.mp4(約 25 分鐘,需 GPU)
#   ./make_videos.sh --fast          # 同上但 --quality fast --edamp 0(約 14 分鐘;960x540,只給開發看,不覆蓋正式影片 → videos/fast/)
#   ./make_videos.sh --damped        # VOL_damped.mp4:舊綁定版完整鏈 + --edamp 0.05(docs/vol/DAMPING.md,約 20 分鐘)
#   ./make_videos.sh --variants      # VARIANTS_grid.mp4:24 種折序各跑 --until box 再拼格(24 × 4~5 分鐘 ≈ 2 小時)
#   ./make_videos.sh --montage DEV   # DEMO_1~6 + DEMO_ALL:純 ffmpeg 剪接;素材在開發資料夾 DEV(= handoff_20260929,見 README §5)
#
#   VIDEO_DIR=/tmp/v ./make_videos.sh   # 輸出到別處(預設 ./videos)
#   ISAAC=/path/to/python.sh ./make_videos.sh
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VID="${VIDEO_DIR:-$HERE/videos}"; mkdir -p "$VID"
cd "$HERE/sim"
case "${1:-}" in
  "")
    ./run_release.sh final MV
    cp ../runs/final_MV/wrap.mp4  "$VID/VOL_twohand_extract.mp4"
    cp ../runs/final_MV/short.mp4 "$VID/DEMO_twohand_extract_short.mp4" ;;
  --fast)
    ./run_release.sh fast MV
    mkdir -p "$VID/fast"; cp ../runs/fast_MV/wrap.mp4 "$VID/fast/VOL_twohand_extract_fast.mp4"
    bash cut_short.sh ../runs/fast_MV/wrap.mp4 "$VID/fast/DEMO_twohand_extract_short_fast.mp4" ;;
  --damped)
    # = docs/vol/DAMPING.md 的 vol/damp/full_cmd.txt(舊綁定版,2026-10-14),只換紙箱路徑
    if [ -n "$ISAAC" ]; then PY="$ISAAC"; else source find_isaac.sh; find_isaac || exit 5; PY="$ISAAC_PYTHON"; fi
    [ "$(id -u)" = 0 ] && export OMNI_KIT_ALLOW_ROOT=1
    O=../runs/damped_e0.05; mkdir -p $O
    PYTHONDONTWRITEBYTECODE=1 $PY wrap_vol.py --sheet_mm 500 --carton carton.usd --young 2e3 --poisson 0.45 --areal 0.1 --fric 0.8 \
      --cont 0.002 --rest 0.0005 --solver 128 --dt 0.004166666666666667 --tip_over_mm 30 --tuck 1 --movebox 0,0.20,0.10 --base_collider_pad 0.02 \
      --grasp 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --ffric 2.0 --pick_mode jaw --arc2 1 --clear_mm 6 --steep_deg 45 --second 1 \
      --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --edamp 0.05 --ldamp 0 --out $O > $O/stdout.txt 2>&1
    cp $O/wrap.mp4 "$VID/VOL_damped.mp4" ;;
  --variants)
    python3 fold_variants.py --orders
    python3 fold_variants.py --run --ids 'o_*'
    python3 fold_variants.py --csv
    python3 fold_variants.py --video
    cp videos/VARIANTS_grid.mp4 "$VID/VARIANTS_grid.mp4" ;;
  --montage)
    DEV="${2:?usage: $0 --montage /path/to/handoff_20260929}"
    # make_demo_videos.sh 寫死 R=開發資料夾;這裡照它的路徑跑,再把成品複製過來
    sed "s#^R=.*#R=$DEV#" make_demo_videos.sh > /tmp/make_demo_videos.$$.sh
    bash /tmp/make_demo_videos.$$.sh; rm -f /tmp/make_demo_videos.$$.sh
    cp "$DEV"/work/videos/demo/DEMO_{1,2,3,4,5,6}_*.mp4 "$DEV"/work/videos/demo/DEMO_ALL.mp4 "$DEV"/work/videos/demo/DEMO_INDEX.md "$VID/" ;;
  *) sed -n 2,13p "$0"; exit 2 ;;
esac
echo "Done -> $VID"; ls -la "$VID"
