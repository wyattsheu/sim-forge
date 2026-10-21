#!/bin/bash
# make_definitive.sh — 定版紙箱的**唯一**生成指令。
#
# 2026-09-29。不要再從舊的 meta.json 的 inputs 抄指令 ——
# 那裡面帶著當時的 dynamic:False,抄過來就把「箱子不能黏在桌面上」這條需求弄丟了。
# 要改尺寸就改這支腳本裡的變數,不要在別處另開一行指令。
#
#   ./make_definitive.sh <輸出路徑.usd>
#
# 每個旗標為什麼是這個值,都寫在下面。沒有註解的旗標不要加。

set -e
OUT="${1:?用法: ./make_definitive.sh <輸出.usd>}"
HERE="$(cd "$(dirname "$0")" && pwd)"

# ── 尺寸:PPT 實物量測(270 x 230 外徑),高度為了裝得下杯子+包材而調整 ──────
# ★ 2026-09-29 試過並**回退**的兩條路,記在這裡免得重試:
#   (a) 過壓抵銷回彈:y 目標 210→壓住216→放開256;180→壓住186→放開266。
#       壓越緊彈越多 —— 布是彈性的沒有塑性定型,不通。
#   (b) hx/hy 對調讓箱子長邊沿 y:下蓋長度 115 是相對**長邊**量的,
#       對調之後下蓋變成沿短邊折,縫隙算出來 −6mm(兩片互相重疊),不通。
#   真正的問題在折疊:折完的包裹 223x273x162,而杯子只有 133x107x93 ——
#   折邊沒有貼下來。要修的是折疊,不是箱子。
HX=0.1335            # 牆中心線;外徑 = 2*(hx+t) = 270mm(長邊沿 x)
HY=0.1135            #                        = 230mm
HEIGHT=0.131         # ★ PPT 是 130。改 131 的理由:牆頂要降到「鉸鏈 - 2t」才不穿蓋子,
                     #   而 130 會讓 ±x 牆頂降到 119mm < 包裹高 120mm,包裹會從側面露出。
                     #   使用者 2026-09-26 核准這 1mm 的偏離。
T=0.0015             # 板半厚;2t = 3mm 板

# ── 蓋子 ────────────────────────────────────────────────────────────────
REACH_LOWER=0.115    # ★ 使用者 2026-09-29 指定:下蓋長度 115mm
                     #   ⇒ 兩片之間縫隙 = 內腔 264 - 2*115 = 34mm(真實 RSC 內側短翼不對接)
FLUSH_GAP=0.001      # 上蓋齊邊,每邊留 1mm(舊的自動值 0.879*hx 會每邊少 14.7mm)
LAYER_GAP=0.0065     # 上下層鉸鏈的高差
CLEAR=0.0025         # 蓋子側邊離箱壁的淨空

# ── 物理 ────────────────────────────────────────────────────────────────
# ★★ --dynamic 是**必要**的,不是選配。
#    PPT 成功定義:「箱子會隨著手臂運動而被移動,不能黏在桌面上」。
#    CARTON_QA.md 的 S0 0.10 也要求 base 必須 dynamic,
#    並把「base 是 kinematic 時去測『箱體沒被推動』」列為恆真陷阱(一定 PASS,毫無意義)。
DENSITY=200
#  ★ 不加 --goods_kg:生成器的配重是給**空箱**用的(避免蓋子反作用力把空箱掀翻)。
#    我們的箱子裡會放真的杯子+包材,那就是配重。加了會變成箱內有兩份內容物。
#  ★ 不加 --anchor:那會把 base 設回 kinematic,等於抵銷 --dynamic。

rm -f "$OUT" "${OUT%.usd}.meta.json"
/isaac-sim/python.sh "$HERE/make_carton_P.py" \
    --out "$OUT" \
    --hx $HX --hy $HY --height $HEIGHT --t $T \
    --reach_lower $REACH_LOWER --flush_gap $FLUSH_GAP \
    --layer_gap $LAYER_GAP --clear $CLEAR \
    --density $DENSITY --dynamic

echo
echo "生成完成:$OUT"
echo "接著必做:"
echo "  1. python3 carton_sweep.py ${OUT%.usd}.meta.json     # 蓋子不穿箱壁,要 0/361"
echo "  2. /isaac-sim/python.sh gap.py $OUT                  # 從 USD 量縫隙(不是讀參數)"
echo "  3. /isaac-sim/python.sh qa_carton.py $OUT <outdir>   # S0~S5 既有關卡"
