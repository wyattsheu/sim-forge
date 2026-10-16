#!/bin/bash
# make_carton.sh — 產生任意尺寸的紙箱(外徑,mm),輸出到 ../assets/cartons/carton_<長>x<寬>x<高>.usd + .meta.json
#
#   ./make_carton.sh 270 230 131            # = 定版紙箱(下層蓋 115 mm)
#   ./make_carton.sh 320 260 160            # 新尺寸;下層蓋長度預設跟定版同比例(115/132 x 內腔半長)
#   ./make_carton.sh 320 260 160 120        # 指定下層蓋長度 120 mm
#
# 長邊沿 x(下層蓋 fxp/fxn 鉸接在 ±x 牆,上層蓋 fyp/fyn 在 ±y 牆),跟定版紙箱同一套慣例。
# 其餘旗標(板厚 3 mm、蓋子縫隙、密度、--dynamic)= make_definitive.sh 的定版值,每個值的理由寫在那支裡。
# 做完記得:
#   python3 carton_sweep.py ../assets/cartons/carton_<...>.meta.json    # 蓋子 0~180° 不穿箱壁,要 0/361
#   然後在 case 檔把 CARTON= 指到新檔。
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
L=${1:?用法: ./make_carton.sh <外長mm> <外寬mm> <高mm> [下層蓋長mm]}; W=${2:?}; H=${3:?}; RL=${4:-}
OUT="$HERE/../assets/cartons/carton_${L}x${W}x${H}.usd"
T=0.0015                                                        # 板半厚(3 mm 板)
read -r HX HY HEIGHT REACH < <(python3 -c "
L,W,H,t=$L/1000,$W/1000,$H/1000,$T
hx,hy=L/2-t,W/2-t                       # 牆中心線:外徑 = 2*(hx+t)
rl='$RL'
reach=float(rl)/1000 if rl else (hx-t)*0.115/0.132   # 定版:內腔半長 132 → 下層蓋 115
print(hx,hy,H,reach)")
source "$HERE/../find_isaac.sh"; find_isaac || exit 5
[ "$(id -u)" = 0 ] && export OMNI_KIT_ALLOW_ROOT=1
export OMNI_KIT_ACCEPT_EULA=${OMNI_KIT_ACCEPT_EULA:-YES}
echo "carton ${L}x${W}x${H} mm: hx=$HX hy=$HY height=$HEIGHT reach_lower=$REACH -> $OUT"
rm -f "$OUT" "${OUT%.usd}.meta.json"
"$ISAAC_PYTHON" "$HERE/make_carton_P.py" \
    --out "$OUT" \
    --hx "$HX" --hy "$HY" --height "$HEIGHT" --t $T \
    --reach_lower "$REACH" --flush_gap 0.001 \
    --layer_gap 0.0065 --clear 0.0025 \
    --density 200 --dynamic
echo "done: $OUT"
echo "check: python3 $HERE/carton_sweep.py ${OUT%.usd}.meta.json"
