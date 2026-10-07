#!/usr/bin/env python3
"""wrap_sim.py — 包材四邊折包覆馬克杯(Isaac)。幾何全部由 wrap_plan.py 的公式算。

    /isaac-sim/python.sh wrap_sim.py --mug mug.stl --out out_wrap
    /isaac-sim/python.sh wrap_sim.py --mug mug.stl --out out_ctrl --no_push   # 陰性對照

★ 與 2026-09-23 四次失敗的差別 —— 只改了**幾何**,機構還是純碰撞:
  1. **折邊長度算對了**。9/23 的布太短(FLAP 只有 176~276mm 卻要爬 93 + 橫過 107),
     根本跨不過杯頂 → 俯視遮蔽 0%。正確長度 = √(壁距²+佔位高²) + 橫過一半 + 重疊。
  2. **加了佔位長方體**(只有碰撞、折完移除)。9/23 杯子被布拖走 100~300mm,
     就是因為沒有東西擋著。
  3. 掃桿半徑固定 = 折邊長 ⇒ 布不會被拉伸(9/23 有一版把布拉到 638mm)。
  4. 折疊期間杯子 kinematic,折完放開(使用者說的「給杯子一個力或 attach」)。

★ 不用 attachment:實測 auto attachment 解析後綁到 0 個頂點(234/234)、
  舊 PhysxPhysicsAttachment 對新 beta surface deformable 無效、手寫 vtx 掛 mesh 底下不讀。
"""
import os, sys, argparse
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--mug", default="mug.stl")
ap.add_argument("--out", default="out_wrap")
ap.add_argument("--margin",  type=float, default=0.012, help="佔位塊比杯子大多少(m)")
ap.add_argument("--wall",    type=float, default=0.006, help="折線離佔位塊側面(m)")
ap.add_argument("--overlap", type=float, default=0.025, help="兩片在頂面重疊(m)")
ap.add_argument("--res",     type=int,   default=34)
ap.add_argument("--cube",    type=float, default=0.018, help="掃桿方塊邊長(m,不加 scale)")
ap.add_argument("--sweep",   type=float, default=150.0, help="掃桿掃到幾度")
ap.add_argument("--hold_mug", action="store_true", default=True,
                help="杯子全程 kinematic(使用者指示:先固定)")
ap.add_argument("--free_mug", dest="hold_mug", action="store_false")
ap.add_argument("--lift", type=float, default=0.0,
                help="把布架高多少(m)。★ 平鋪在地上的布,任何夾具都碰不到它的邊 —— "
                     "架高之後折邊會自己垂下來,掃桿才有東西可以掃")
ap.add_argument("--fold_init", action="store_true", default=True,
                help="★ 直接把布的初始頂點就生成「已折好」的形狀,再讓引擎鬆弛落定。"
                     "不用任何夾具 —— 五種夾具(托/夾/壓/掃/架高掃)實測俯視遮蔽全部 0%")
ap.add_argument("--flat_init", dest="fold_init", action="store_false",
                help="陰性對照:布平鋪,不預折")
ap.add_argument("--no_push", action="store_true", help="陰性對照:只落下不折")
ap.add_argument("--bend",  type=float, default=2.0e3,
                help="彎曲剛性。★ 折好的盒狀要「變軟」才會塌到杯子上(使用者 2026-09-24)")
ap.add_argument("--young", type=float, default=5.0e4, help="面內楊氏模數")
ap.add_argument("--thick", type=float, default=0.010,
                help="★ surfaceThickness(m)。這是**碰撞厚度**,直接決定疊起來多高:"
                     "四折的包裹高 = 杯子 93 + 上下各一層 thick + 3 x layer_mm。"
                     "使用者 2026-09-25「壓到 130」:10mm -> 6mm 可省 8mm。")
ap.add_argument("--settle", type=float, default=6.0, help="折好之後再鬆弛幾秒")
ap.add_argument("--move_open", action="store_true", help="搬完靜置後原地把四片蓋打開(上蓋先、下蓋後),確認箱內狀態")
ap.add_argument("--cam_ref", type=float, default=0.0,
                help="非紙箱段相機距離基準(m)。0 = 舊行為 max(WX,WY);sheet 400 時鏡頭太近,建議 0.586")
ap.add_argument("--square", action="store_true", default=True,
                help="布做成**正方形**(邊長 = 兩軸需求的較大者)。PPT 的泡泡紙是 400x400 正方形")
ap.add_argument("--rect", dest="square", action="store_false")
ap.add_argument("--sheet_mm", type=float, default=0.0,
                help="直接指定正方形邊長(mm)。0 = 用算出來的最小需求")
ap.add_argument("--unfold", action="store_true",
                help="★ 從折好的狀態**攤開**:用已驗證的 attachment 抓四片外緣拉回平面")
ap.add_argument("--wrapsim", action="store_true",
                help="★ 最暴力也最正確(使用者 2026-09-24):布從**攤平**開始,四個邊各一個施力點,"
                     "一次抬一邊沿圓弧轉上去再蓋過杯頂,疊層與碰撞交給物理自己解;S0 天生 = 0")
ap.add_argument("--carton", default="",
                help="把定版紙箱 USD 載進場景,並把包裹放進箱內(整個紙箱設成 kinematic,"
                     "維持它被生成時的開蓋姿態;這是交付用的靜態場景,不是紙箱力學測試)")
ap.add_argument("--layer_mm", type=float, default=12.0,
                help="★ 使用者 2026-09-25:「兩者的 xy 可以重複,z 分開就好」。"
                     "每一折的終點高度按折序往上疊這麼多 mm。布的碰撞厚度是 "
                     "surfaceThickness 10mm,所以間距要 >10 才不會把後折的尖端拉進前一片裡。"
                     "0 = 全部同高(先前的作法,實測兩折就 140 次自穿模)")
ap.add_argument("--pentrack", type=float, default=0.5,
                help="★ 使用者 2026-09-25:「你從置放的初始就要測了」。"
                     "每隔幾秒量一次自穿模,從第 0 格開始,這樣才看得出是**哪一折**把它弄壞的,"
                     "而不是只有頭尾兩個數字。0 = 關掉")
ap.add_argument("--close_lid", action="store_true",
                help="★ 暴力法(使用者 2026-09-25):先開蓋 → 入箱 → **關蓋**,讓蓋子把包材壓進去。"
                     "我先前算『最低 118mm』是假設兩層布留在杯子正上方;關蓋會把它們往旁邊推,"
                     "而 x/y 還有 34x37mm 空位。下層 fx 先關、上層 fy 後蓋上。")
ap.add_argument("--reveal", action="store_true",
                help="★ 交付用的開箱序列:紙蓋從蓋住轉到打開(上層 fy 先、下層 fx 後),"
                     "接著把包材往外拉開露出杯子。鉸鏈幾何由 insp_carton.py 量出來:"
                     "fxp(132,0,92) fxn(-132,0,92) 軸 -y/+y;fyp(0,112,98.5) fyn(0,-112,98.5) 軸 +x/-x")
ap.add_argument("--carton_t", type=float, default=0.003, help="紙箱板厚(m),用來算箱底內面")
ap.add_argument("--press", type=float, default=0.0,
                help="★ 用剛性平板把包好的東西壓到幾 mm 高(使用者 2026-09-25:"
                     "『直接做一個 rigid plane 來壓 就不用箱子了』)。"
                     "配 --init_npz 用:布以包好的狀態出生、完全不施力,只有平板壓下來。"
                     "紙箱 carton_ppt 的內高是 100mm,所以預設目標就是 100。")
ap.add_argument("--hide_cloth", action="store_true",
                help="★ 渲染診斷:把布整個隱藏。箱子若還有黑塊 = 陰影;乾淨 = 透過箱壁看到布。")
ap.add_argument("--press6", default="",
                help="★ 使用者 2026-09-26:「先做一個被六面體壓過的再塞」。"
                     "六片剛性板從外面收到目標尺寸 W,L,H(mm),布沒有地方可以溢 → 壓實成方塊。"
                     "只壓頂面的話布會往旁邊攤(實測 239x233 攤成 284x270,撐破箱壁)。"
                     "例:--press6 250,210,115")
ap.add_argument("--film_op", type=float, default=1.0,
                help="膜的 opacity。★ 2026-09-26 判別測試(紅箱)證實:opacity < 1 的布會被"
                     "**畫在所有東西前面**,連翻到箱外那片蓋子都被蓋住 —— 不是透過箱壁看到布,"
                     "是半透明面的合成無視深度。唯一不觸發的是 1.0,所以預設改成 1.0;"
                     "泡泡的外觀靠法線貼圖保留。")
ap.add_argument("--film_ior", type=float, default=1.0, help="膜的 ior。1.0 = 無折射,可能是黑的原因")
ap.add_argument("--light_probe", action="store_true",
                help="★ 渲染診斷:把預設地板燈關掉、dome 拉到 100000(全方向均勻照),其餘不動。"
                     "黑色若消失 = 照不到光;黑色若還在 = 材質/背面的問題。一次只改這一個變數。")
ap.add_argument("--unbox", action="store_true",
                help="★ 開箱序列(使用者 2026-09-26):從包好的狀態出發,"
                     "上層蓋先開 → 下層蓋開 → 再把包材往外上方掀開露出杯子。"
                     "蓋子用 kinematic 轉(開箱不需要布頂住蓋子,方向是離開布的)。")
ap.add_argument("--flat_z", type=float, default=0.40,
                help="完整攤平時,搬運路徑**中途**的最高點(m)。要讓吊在下面的布袋底越過打開的紙蓋。")
ap.add_argument("--flat_x", type=float, default=-0.56,
                help="完整攤平的落點往 x 偏多少(m)。布半徑 0.293 + 紙箱含打開紙蓋 ~0.24,"
                     "所以 |flat_x| 至少 0.53 才不會疊在箱子上。負值 = 相機遠側。")
ap.add_argument("--flat_t", type=float, default=8.0, help="完整攤平用幾秒")
# ★ 使用者 2026-09-27:「包裹完包材後 直接施力在杯子上 讓他升起來 我要看包材的狀況」
#   證偽測試:包得好 → 整包跟著離地;沒包住 → 布留在原地或杯子從布裡穿出去。
#   (--lift 這個名字已經被「架高」用掉,所以叫 lift_mug)
ap.add_argument("--lift_mug", type=float, default=0.0,
                help="包好之後把杯子垂直提起多少 m(0=不做)。布完全不建錨點,只靠包覆撐住")
ap.add_argument("--lift_t", type=float, default=6.0, help="提升過程幾秒")
ap.add_argument("--lift_wait", type=float, default=3.0, help="提之前先靜置幾秒")
ap.add_argument("--unbox_out", type=float, default=0.10, help="包材往外掀多遠(m)")
ap.add_argument("--unbox_up",  type=float, default=0.12, help="包材往上掀多高(m)")
ap.add_argument("--lid_dynamic", action="store_true",
                help="★ 使用者 2026-09-26:蓋子改成**動態剛體 + 關節 drive**,而不是 kinematic 硬轉。"
                     "kinematic 的蓋子不管布在不在都會轉到 0°,布擋不住它,所以量到的 2.1mm 穿模"
                     "是『硬壓進去』不是『被頂住』。動態之後布頂得住蓋子就會停在那裡,"
                     "紙箱與包材有沒有真的穿才看得出來。")
ap.add_argument("--lid_span", type=float, default=4.0,
                help="每一層蓋子關上用幾秒。★ 4 秒轉 180° 太快,實測把布掃穿箱壁 315 點、"
                     "箱底 108 點(kinematic 蓋子 vs deformable,solver 來不及解)。放慢。")
ap.add_argument("--press_down", type=float, default=4.0,
                help="壓板下降用幾秒。★ 上一次壓穿箱壁 315 點,原因之一是 4 秒降 230mm 太快,"
                     "solver 來不及解接觸就讓布穿出去。放慢是唯一不改物理的旋鈕。")
ap.add_argument("--press_hold", type=float, default=3.0, help="壓到位之後壓住幾秒")
ap.add_argument("--press_off",  type=float, default=3.0, help="抬走之後再看幾秒(量回彈)")
ap.add_argument("--init_npz", default="",
                help="★ 第二段模擬:布**直接以第一段跑完的頂點位置出生**(wrap.npz 的 sheet)。"
                     "2026-09-25 實測:attachmentEnabled / stiffness 在跑的途中改**完全無效**"
                     "(probe_release.py:鬆手後頂點還是一路跟到底),所以「跑到一半放力」"
                     "在單一次模擬裡做不到,只能拆兩段。")
ap.add_argument("--stage2", action="store_true",
                help="第二段:只建兩組錨點 —— (1) 停在杯子正上方的維持壓住 "
                     "(2) 當下還貼地的那條邊,拿去折後兩折。其餘一個都不建 = 真的放力")
ap.add_argument("--floor_edges", default="",
                help="json:後兩折要抓哪些頂點。★ 由**兩折版實跑的結果**量出來的『折完仍貼地』"
                     "的那條邊(floor_edges.json)。這些點釘住也不影響前兩折,"
                     "因為它們本來就會留在地板上 —— 這是唯一能避開『無窮硬 attachment "
                     "等於從第 0 秒釘死』的辦法。")
ap.add_argument("--wrap_n", type=int, default=4,
                help="wrapsim 折幾邊(使用者 2026-09-25:後兩次先暫停 → 2)")
ap.add_argument("--wrap_edge", action="store_true",
                help="wrapsim 施力點改成**整條邊**(使用者 2026-09-25:前兩次動整邊),"
                     "不是只有邊的中點一個")
ap.add_argument("--anchors", type=int, default=0,
                help="攤開用幾個施力點:0=整圈外緣逐點(舊);4=四個邊的最外側中點各一個")
ap.add_argument("--selfcol", action="store_true", default=False,
                help="打開布的自碰撞(他們的檔案是關的)")
ap.add_argument("--sleepy", action="store_true", default=True,
                help="套用 tex_bubble_mug.usd 的 settling/sleep 四參數(實測會讓布提早睡著)")
ap.add_argument("--no_sleepy", dest="sleepy", action="store_false")
ap.add_argument("--tex", default="", help="泡泡布法線貼圖(tex 版外觀;剛體泡泡那款用 --bubbles)")
ap.add_argument("--tex_mm", type=float, default=200.0, help="貼圖代表幾 mm 見方")
ap.add_argument("--bubbles", action="store_true",
                help="★ 用他們那款包材:半透明膜 + 剛體泡泡(參數照抄 mission0921/step10)")
ap.add_argument("--bub_pitch", type=float, default=0.030, help="泡泡間距(他們的值)")
ap.add_argument("--bub_r",     type=float, default=0.013, help="泡泡半徑(他們的值)")
ap.add_argument("--checker", action="store_true",
                help="不綁半透明材質,直接顯示攤平座標的棋盤格 —— 用來確認是同一張布")
ap.add_argument("--solver",  type=int,   default=64)
# ★ 2026-09-30 壓實調查:布 collider 的偏移量原本寫死 CONT=5mm / REST=1mm。
#   交接量到層與層之間 3mm、改 surfaceThickness 沒反應 ⇒ 懷疑就是這裡。開成旗標好掃。
ap.add_argument("--cont", type=float, default=0.005, help="布 collider contactOffset(m),原寫死 0.005")
ap.add_argument("--rest", type=float, default=0.001, help="布 collider restOffset(m),原寫死 0.001")
ap.add_argument("--self_filter", type=float, default=-1.0,
                help="physxDeformableBody:selfCollisionFilterDistance(m);<0 = 不設(沿用引擎預設)")
ap.add_argument("--pair_freq", type=int, default=0,
                help="physxDeformableBody:collisionPairUpdateFrequency;0 = 不設")
ap.add_argument("--col_iter_mult", type=int, default=0,
                help="physxDeformableBody:collisionIterationMultiplier;0 = 不設")
ap.add_argument("--ccd", action="store_true", help="physxDeformableBody:enableSpeculativeCCD")
# ★ 2026-09-30 layer_gap.py 量到:c1 兩折後布最高點離杯頂 17mm、四折 43mm、壓實後仍 29mm;
#   而 --cont/--rest 縮 2.5 倍層間距完全沒變(5.46→5.44)。撐高的是**錨點終點的幾何**:
#   折邊尖端被無窮硬 attachment 釘在 杯頂 + LZ_HOLD(12mm) + lay*layer_mm,而且一段模擬內放不掉;
#   壓實段(press6)還會建 4 個錨把折邊中點釘在起始高度。這三個旗標就是拿掉這些幾何。
ap.add_argument("--hold_mm", type=float, default=12.0,
                help="折完錨點停在杯頂上方幾 mm(原寫死 LZ_HOLD=12)。要疊得貼就往 1~3 調")
ap.add_argument("--no_anchor", action="store_true",
                help="完全不建錨點(壓實/入箱段用:讓布只受重力與壓板,不被釘在空中)")
ap.add_argument("--tip_over_mm", type=float, default=0.0,
                help="折邊尖端越過杯子中線多少 mm(原本終點剛好在中線,兩片只是對接不是疊)")
# ★ 2026-09-30 probe_detach.py 實測:attachment 在模擬中 **可以** 放掉 ——
#   st.RemovePrim(Scope) / attachmentEnabled=False / SetActive(False) 三種都當步生效,頂點立刻自由落下,
#   其他錨點不受影響、布不會重 cook。原作者 09-25「改了無效」是三個錨點同邊一起升、被鄰居撐住的量測假象。
#   所以折到位之後可以真的放手,讓重力把布貼下去,不必再靠終點高度硬撐。
ap.add_argument("--release_after", type=float, default=-1.0,
                help="每一折拉到位之後幾秒放掉錨點(刪 attachment Scope、方塊收到 z=-5)。<0 = 不放(舊行為)")
ap.add_argument("--no_hold", action="store_true",
                help="第二段不建『杯子正上方維持壓住』那 100 個 hold 錨(放手流程下不需要它們)")
ap.add_argument("--movebox", default="",
                help="搬紙箱:X,Y,Z(m)。空 = 關。蓋子一開始就關著,箱體+四片蓋 kinematic 平移,杯子改成動態")
ap.add_argument("--move_t", type=float, default=6.0, help="--movebox 搬運用幾秒(smoothstep)")
ap.add_argument("--move_wait", type=float, default=2.0, help="--movebox 搬之前先靜置幾秒")
ap.add_argument("--move_mode", default="xform", choices=["xform", "ktarget"],
                help="--movebox 怎麼移箱子:xform = 每步 set_world_pose 改 USD(舊);"
                     "ktarget = PhysX tensor API set_kinematic_targets(PhysX 會由目標推出速度,摩擦才帶得動)")
ap.add_argument("--ground_z", type=float, default=0.0,
                help="地板高度(m)。預設 0。診斷用:kinematic 紙箱不需要地板,降到 -0.02 讓"
                     "壓穿 3mm 箱底的布頂點碰不到地板(contactOffset 5mm)")
ap.add_argument("--no_ground_collision", action="store_true",
                help="關掉預設地板的碰撞(視覺保留)。movebox + kinematic 紙箱時地板沒有功能")
ap.add_argument("--base_collider_pad", type=float, default=0.0,
                help="紙箱底板碰撞往下加厚幾 m(base 下方加不可見碰撞方塊)。0 = 不改")
ap.add_argument("--in_box_already", action="store_true",
                help="--init_npz 已是箱內座標(如 lidcheck/wrap.npz):跳過入箱的置中/墊高平移")
a, _ = ap.parse_known_args()
MOVE = (np.array([float(x) for x in a.movebox.split(",")], float) if a.movebox else None)
if MOVE is not None:
    assert MOVE.shape == (3,), "--movebox 要 X,Y,Z 三個數"
    a.hold_mug = False          # 杯子要跟著包裹被箱子帶走,不能 kinematic 釘在原地
if a.wrapsim:
    # wrapsim 蘊含:攤平起步、布要擋得住布、只用四個施力點
    a.fold_init = False; a.selfcol = True; a.anchors = 4; a.unfold = False
if a.unbox:
    a.close_lid = True          # 借用蓋子的建構;方向在 drive() 裡反過來
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
os.makedirs(a.out, exist_ok=True)

# ── 折序:**唯一來源** ─────────────────────────────────────────────────
# ★ 2026-09-30:PPT 開箱是 前後(±y)先開、左右(±x)後開;先開的一定是外層,
#   所以包材的外層必須是 ±y ⇒ **先折 ±x、後折 ±y**(後折的疊在外面)。
#   以前 ORD_ / WORDER / UORDER / ORDER / _ORD 五處各自寫死一份順序,改順序時漏一處
#   就 ValueError(WORDER.index)或 y 邊沒折到(stage2 寫死抓 x 邊)。
#   現在**只准改下面這一行**,其餘全部從它衍生;selfcheck.py C 段會驗。
FOLD_ORDER = ["xp", "xn", "yp", "yn"]
STAGE2_SIDES = FOLD_ORDER[2:]                 # 第二段(--stage2)折的是後兩折
UORDER = ["yn", "yp", "xn", "xp"]             # = FOLD_ORDER 反序(--unbox/--unfold 逆向打開用)。selfcheck 用 regex 抓字面值,所以寫死、由下一行守住
assert UORDER == list(reversed(FOLD_ORDER)), "UORDER 必須是 FOLD_ORDER 的反序"
assert sorted(FOLD_ORDER) == ["xn", "xp", "yn", "yp"], "FOLD_ORDER 要剛好四邊各一次"
assert FOLD_ORDER[0][0] == FOLD_ORDER[1][0] and FOLD_ORDER[2][0] == FOLD_ORDER[3][0], \
    "FOLD_ORDER 前兩折要同一軸、後兩折要同一軸(對邊成對折)"

from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from isaacsim.core.prims import SingleXFormPrim
from isaacsim.sensors.camera import Camera
from pxr import Usd, Gf, Sdf, UsdGeom, UsdPhysics, UsdShade, UsdLux, PhysxSchema, Vt
from omni.physx.scripts import deformableUtils
import omni.usd, imageio.v2 as imageio, trimesh
from PIL import Image, ImageDraw, ImageFont
import grip_common as G

LOG = open(os.path.join(a.out, "wrap_sim.log"), "w")
def P(*s):
    m = " ".join(str(x) for x in s); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()

YOUNGS, POISSON, THICK, BEND = a.young, 0.45, a.thick, a.bend
FRIC, DENS = 0.8, 100.0
LDAMP, EDAMP, BDAMP = 0.20, 0.30, 0.30
CONT, REST = a.cont, a.rest
FLOOR, FPS = 0.003, 30

world = World(physics_dt=1/120.0, rendering_dt=1/FPS)
world.scene.add_default_ground_plane(z_position=a.ground_z)
st = omni.usd.get_context().get_stage()
if a.no_ground_collision:
    # 視覺地板保留,只關掉碰撞:movebox 時紙箱 kinematic,地板沒有功能,
    # 反而會從底板下方拖住被杯子壓進 3mm 底板的布頂點(mb3/mb4/mb5 實測)
    _ng = 0
    for _gp in Usd.PrimRange(st.GetPrimAtPath("/World/defaultGroundPlane")):
        if _gp.HasAPI(UsdPhysics.CollisionAPI):
            UsdPhysics.CollisionAPI(_gp).CreateCollisionEnabledAttr(False); _ng += 1
    P("★ 地板碰撞關閉(%d 個 collider),視覺地板保留" % _ng)
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
for at, v in [("CreateGpuMaxDeformableSurfaceContactsAttr", 4*1048576),
              ("CreateGpuCollisionStackSizeAttr", 128*1024*1024),
              ("CreateGpuFoundLostAggregatePairsCapacityAttr", 8192)]:
    try: getattr(pxs, at)(v)
    except Exception: pass

def sa(prim, n, v, tn=None):
    at = prim.GetAttribute(n)
    if not at or not at.IsValid():
        if tn is None: return
        at = prim.CreateAttribute(n, tn)
    at.Set(v)

def vmat(path, col, op, rough=.25, ior=None):
    """★ 2026-09-26:ior 原本寫死 1.0(當初是為了做半透明膜),結果**所有**用 vmat 的
    材質都繼承了,包括紙箱 —— ior=1.0 等於跟空氣一樣、完全不折射直接穿透,
    所以紙箱 opacity 設 1.0 還是看得到裡面(把布隱藏就證實了:箱子乾淨沒有黑塊)。
    現在:不透明材質預設 ior=1.5,只有膜才用 1.0。"""
    m = UsdShade.Material.Define(st, path); s = UsdShade.Shader.Define(st, path + "/S")
    s.CreateIdAttr("UsdPreviewSurface")
    s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*col))
    s.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    s.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(op)
    s.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(
        ior if ior is not None else (1.0 if op < 0.99 else 1.5))
    m.CreateSurfaceOutput().ConnectToSource(s.ConnectableAPI(), "surface"); return m

def film_tex(path, tex, tile_m):
    """半透明泡泡布:UsdPreviewSurface + 法線貼圖。
    ★ 不走 MDL —— 這個容器的 shadercache 是 root 的,需要現場編譯的 MDL 一律失敗。
    法線貼圖的 scale (2,2,2,1) / bias (-1,-1,-1,0) 是 0..1 → -1..1 的換算。"""
    m = UsdShade.Material.Define(st, path)
    sh = UsdShade.Shader.Define(st, path + "/S"); sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.90, .95, .97))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.18)
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(a.film_op)
    sh.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(a.film_ior)
    st_r = UsdShade.Shader.Define(st, path + "/st"); st_r.CreateIdAttr("UsdPrimvarReader_float2")
    st_r.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    st_r.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    nt = UsdShade.Shader.Define(st, path + "/nrm"); nt.CreateIdAttr("UsdUVTexture")
    nt.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(tex)
    nt.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_r.ConnectableAPI(), "result")
    nt.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(2, 2, 2, 1))
    nt.CreateInput("bias",  Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(-1, -1, -1, 0))
    nt.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
    nt.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
    nt.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    sh.CreateInput("normal", Sdf.ValueTypeNames.Normal3f).ConnectToSource(nt.ConnectableAPI(), "rgb")
    m.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return m

FILM = (film_tex("/World/film", a.tex, a.tex_mm/1000.0) if a.tex
        else vmat("/World/film", (.90, .95, .97), a.film_op))
BUBM = vmat("/World/bubm", (.72, .85, .95), .35)      # 他們的泡泡色
# 使用者 2026-09-25「杯子的顏色還是很怪」。實測(out_col 第 20 格,量杯身像素):
#   指定 diffuse (0.30,0.40,0.56) → 渲出來 (219,230,236)/255 = (0.86,0.90,0.93)
#   ⇒ 整個場景**過曝約 2.9 倍**(背景地板同樣偏亮),材質是綁上的(色相對:B>G>R)。
# 所以用量到的係數反推:要渲出原本指定的藍灰 (144,163,189)/255,diffuse 就設 /2.9。
# 使用者 2026-09-25「杯子的顏色還是很怪」。判別測試:指定純紅 → 渲出 (242,1,1),
# G/B 都是 0 ⇒ **材質是綁上的、有效的**,也沒有環境加色。
# 真因是**場景照度約 3.7 倍**:diffuse 0.195 x 3.7 = 0.73(實測 0.73);
# 純紅 1.0 x 3.7 被截到 1.0(實測 0.95)。⇒ diffuse 只要 > 0.27 就一律爆白。
# 修法不是改顏色,是把照度降回 1 倍(見下面的 headlight / dome),顏色就一次全對。
# 照度修正後實測杯身 (172,181,190),目標 (144,163,189) ⇒ R 高 19%、G 高 11%、B 準。
# 用量到的比例反修:
# 第二輪:上一版實測 (161,175,190),目標 (144,163,189) ⇒ 再乘 (0.894, 0.931, 1.0)
MUGM = vmat("/World/mugm", (144/255./1.19*0.894, 163/255./1.11*0.931, 189/255./1.005), 1.0, .40)

# ── 杯子:躺平 + 方位(杯口朝前 +y、杯耳朝右 +x)──────────────────────
m = trimesh.load(a.mug)
V = np.asarray(m.vertices, float); F = np.asarray(m.faces)
unit = 0.001 if V.ptp(0).max() > 1.0 else 1.0
V = (V - V.mean(0)) * unit
Ry = lambda t: np.array([[np.cos(t), 0, np.sin(t)], [0, 1, 0], [-np.sin(t), 0, np.cos(t)]])
Rx = lambda t: np.array([[1, 0, 0], [0, np.cos(t), -np.sin(t)], [0, np.sin(t), np.cos(t)]])
Rz = lambda t: np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1]])
# ★ 2026-09-30 從 mug.stl **網格本身**量過(純 numpy:端面是「環」= 杯口/底足、「盤」= 封底;
#   超出杯身半徑的點 = 杯耳;量法見 work/FOLDORDER_NOTES.md):原始 STL 是直立杯,杯口 +z、杯耳 +x。
#   舊的 Ry(-90)·Rx(90) 躺平後是 **杯口 −x、杯耳 −y**(杯軸躺在 x 上!),跟 selfcheck.py 註解
#   假設的「套 _Rm 前 = 杯口 +y / 杯耳 −x」不符 —— 在它上面直接套 _Rm 會得到 杯口 +x、杯耳 −y。
#   所以躺平多轉一步 Rz(-90),讓「套 _Rm 前」的基準姿態真的是 杯口 +y / 杯耳 −x(selfcheck 前提成立),
#   再由 _Rm 把杯耳從 −x 翻到 +x。三步合起來恰好 = Rx(-90)。
V = V @ Ry(-np.pi/2).T @ Rx(np.pi/2).T @ Rz(-np.pi/2).T      # 基準姿態:杯口 +y、杯耳 −x
# ★ 杯子方位矩陣(ORIENTATION_AND_SIZE.md §3:杯口朝前 +y、杯耳朝右 +x)。純旋轉 det=+1(不是鏡像),
#   繞 y 轉 180°:_Rm@(0,1,0)=(0,1,0) 杯口留在 +y;_Rm@(-1,0,0)=(1,0,0) 杯耳 −x→+x。
#   selfcheck.py C 段用 regex 抓這一行 eval 驗 det 與這兩個向量,所以矩陣寫成一行、np.array([[ 開頭、]]) 結尾。
_Rm = np.array([[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]])
V = V @ _Rm.T
V -= (V.max(0) + V.min(0)) / 2.0
ME = V.max(0) - V.min(0); hx, hy, H2 = ME / 2.0
P("杯子躺平 %.0f x %.0f x %.0f mm;方位:杯口 +y(前)、杯耳 +x(右),det(_Rm)=%+.0f"
  % (ME[0]*1e3, ME[1]*1e3, ME[2]*1e3, np.linalg.det(_Rm)))

# ── 幾何:照 wrap_plan.py 的公式 ──────────────────────────────────────
A, B, HC = ME[0] + 2*a.margin, ME[1] + 2*a.margin, ME[2] + a.margin   # 佔位塊
CY, CX = B/2 + a.wall, A/2 + a.wall                                   # 折線
climb = np.hypot(a.wall, HC)
FLAPY = climb + B/2 + a.overlap
FLAPX = climb + A/2 + a.overlap
WX, WY = A + 2*a.wall + 2*FLAPX, B + 2*a.wall + 2*FLAPY
NEED_SQ = max(WX, WY)
if a.sheet_mm > 0:
    WX = WY = a.sheet_mm/1000.0
elif a.square:
    WX = WY = NEED_SQ
P("★ 正方形布的最小需求 %.0f x %.0f mm;實際採用 %.0f x %.0f mm%s"
  % (NEED_SQ*1e3, NEED_SQ*1e3, WX*1e3, WY*1e3,
     "  ← 不足,包不滿" if WX < NEED_SQ - 1e-6 else ""))
P("佔位塊 %.0f x %.0f x %.0f mm" % (A*1e3, B*1e3, HC*1e3))
P("折邊長 ±y %.0f mm(爬升 %.0f + 橫過 %.0f + 重疊 %.0f);±x %.0f mm"
  % (FLAPY*1e3, climb*1e3, B/2*1e3, a.overlap*1e3, FLAPX*1e3))
P("★ 最高點 = 折邊長,發生在繞折線轉 90°:±y %.0f mm / ±x %.0f mm" % (FLAPY*1e3, FLAPX*1e3))
P("包材 %.0f x %.0f mm" % (WX*1e3, WY*1e3))

# ── 平台:把布架高,四片折邊自然垂在平台側面 ──────────────────────────
# ★ 這是 2026-09-23 四次失敗之後唯一沒試過的構型。先前布平鋪在地上,
#   掃桿/鏟板/夾爪/滾壓桿都碰不到布的「邊」(邊被壓在地上),所以俯視遮蔽一直是 0%。
#   架高之後折邊垂在半空,掃桿從外面往上掃就抓得到。
PLAT_Z = a.lift
PW, PL = A + 2*a.wall, B + 2*a.wall
if PLAT_Z <= 1e-6:
    P("不架高(使用者 2026-09-24:長方體原意是預留給杯子的空間,不是實體平台)")
plat = UsdGeom.Cube.Define(st, "/World/plat") if PLAT_Z > 1e-6 else None
if plat is not None:
    plat.CreateSizeAttr(1.0)
if plat is not None:
    _px2 = UsdGeom.Xformable(plat)
    _px2.AddTranslateOp().Set(Gf.Vec3d(0, 0, PLAT_Z/2))
    _px2.AddScaleOp().Set(Gf.Vec3f(PW/2, PL/2, PLAT_Z/2))
    UsdPhysics.CollisionAPI.Apply(plat.GetPrim())
    UsdPhysics.RigidBodyAPI.Apply(plat.GetPrim()).CreateKinematicEnabledAttr(True)
    plat.CreateDisplayColorAttr([Gf.Vec3f(0.42, 0.45, 0.50)])
    P("平台 %.0f x %.0f mm,高 %.0f mm" % (PW*1e3, PL*1e3, PLAT_Z*1e3))

# ── 佔位長方體:**只當算折邊長度的數字,不做成碰撞體** ────────────────
# ★ 2026-09-24 實測:把它做成實體會把杯子整個包在裡面(佔位塊 z 230~335,
#   杯子 232~325)—— 布罩的是佔位塊不是杯子,貼合 0%、中位距離 112mm。
#   真正的障礙物就是杯子本身。
# ── 紙箱(可選)────────────────────────────────────────────────────
CDZ = 0.0
if a.carton:
    _bx = st.DefinePrim("/World/Box", "Xform")
    _bx.GetReferences().AddReference(os.path.abspath(a.carton))
    # 整個紙箱固定住:交付場景要的是「箱子維持生成時的開蓋姿態」,
    # 不是再跑一次摺線力學(那是 stair2 的事)。
    _nk = 0
    _LIDNAMES = ("fxp", "fxn", "fyp", "fyn")
    for _p in Usd.PrimRange(_bx):
        if a.lid_dynamic and _p.GetName() in _LIDNAMES:
            continue          # 蓋子留成動態,才會被布頂住
        if _p.HasAPI(UsdPhysics.RigidBodyAPI):
            _a = _p.GetAttribute("physics:kinematicEnabled")
            (_a if _a and _a.IsValid() else
             _p.CreateAttribute("physics:kinematicEnabled", Sdf.ValueTypeNames.Bool)).Set(True)
            _nk += 1
    # ★ 使用者 2026-09-26:「你給我一個 紙箱是不透明的」。
    #   生成器帶進來的材質是半透明的,黑色的布直接從箱壁透出來(見 box_last.png)。
    #   這裡強制把箱子每一片 Mesh 綁上不透明的紙板材質。
    _CB = vmat("/World/cartonmat", (0.62, 0.46, 0.29), 1.0, 0.85)
    # 紙箱的幾何不是直接的 Mesh prim(是 Xform + geo 子節點),所以用 Imageable 判斷,
    #   而且綁在 /World/Box 根上並用 strongerThanDescendants 蓋掉原本的半透明材質。
    _nm2 = 0
    for _p in Usd.PrimRange(_bx):
        if _p.IsA(UsdGeom.Gprim):
            UsdShade.MaterialBindingAPI.Apply(_p).Bind(
                _CB, UsdShade.Tokens.strongerThanDescendants)
            _nm2 += 1
    UsdShade.MaterialBindingAPI.Apply(_bx).Bind(_CB, UsdShade.Tokens.strongerThanDescendants)
    P("★ 紙箱改成不透明紙板材質(%d 個 Gprim + 根節點)" % _nm2)

    _bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
    _rr = _bb.ComputeWorldBound(_bx).ComputeAlignedRange()
    # ★ 不要拿 /Box/base 的 bbox 上緣當箱底 —— 那個 prim 含子物件,上緣是 100mm(箱口),
    #   第一次跑就把包裹墊到箱子**上面**去了。箱底內面 = 整箱最低點 + 板厚。
    CDZ = float(_rr.GetMin()[2]) + a.carton_t
    P("★ 紙箱:%s;%d 個剛體設成 kinematic;整箱 bbox %.0f x %.0f x %.0f mm;"
      "最低點 z=%.1f mm → 箱底內面 z=%.1f mm"
      % (a.carton, _nk, *((np.array(_rr.GetMax()) - np.array(_rr.GetMin()))*1e3),
         float(_rr.GetMin()[2])*1e3, CDZ*1e3))
    if a.base_collider_pad > 0:
        # ★ 2026-10-02:底板只有 3mm,動態杯子把布頂點壓穿底板 → 碰到地板 → 地板摩擦把布留住
        #   (mb3_x30 布相對箱子滑 35mm;地板降到 -0.02 時降到 7.7mm)。
        #   這裡在 base 底下加一塊不可見的碰撞方塊(base 的子 prim ⇒ 併進 base 剛體一起動),
        #   等於把底板碰撞加厚,布穿不過去。只改 stage,不改 USD 檔、不改視覺。
        _bt = st.GetPrimAtPath("/World/Box/base/bottom")
        _br = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(
            _bt if _bt.IsValid() else st.GetPrimAtPath("/World/Box/base")).ComputeAlignedRange()
        _lo, _hi = np.array(_br.GetMin()), np.array(_br.GetMax())
        _ctr = np.array([(_lo[0]+_hi[0])/2, (_lo[1]+_hi[1])/2, _lo[2] - a.base_collider_pad/2])
        _pad = UsdGeom.Cube.Define(st, "/World/Box/base/pad_collider"); _pad.CreateSizeAttr(1.0)
        _Wb = UsdGeom.Xformable(st.GetPrimAtPath("/World/Box/base")).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        _cl = _Wb.GetInverse().Transform(Gf.Vec3d(*map(float, _ctr)))
        _px = UsdGeom.Xformable(_pad)
        _px.AddTranslateOp().Set(_cl)
        _px.AddScaleOp().Set(Gf.Vec3f(float(_hi[0]-_lo[0]), float(_hi[1]-_lo[1]), float(a.base_collider_pad)))
        UsdPhysics.CollisionAPI.Apply(_pad.GetPrim())
        _pad.CreatePurposeAttr(UsdGeom.Tokens.guide)        # 不渲染、不進 bbox
        _cbm = _bt.GetRelationship("material:binding:physics") if _bt.IsValid() else None
        if _cbm and _cbm.GetTargets():
            UsdShade.MaterialBindingAPI.Apply(_pad.GetPrim()).Bind(
                UsdShade.Material(st.GetPrimAtPath(_cbm.GetTargets()[0])),
                UsdShade.Tokens.weakerThanDescendants, "physics")
        P("★ 底板碰撞加厚:base 下方加不可見碰撞方塊 %.0f x %.0f x %.0f mm(z %.1f~%.1f mm),材質同底板"
          % ((_hi[0]-_lo[0])*1e3, (_hi[1]-_lo[1])*1e3, a.base_collider_pad*1e3,
             (_lo[2]-a.base_collider_pad)*1e3, _lo[2]*1e3))

LIDS = []
LID_DRIVE = {}
CBOX = {}          # 紙箱的內腔尺寸,從 meta 讀,不要寫死
if a.carton:
    _mj = os.path.splitext(os.path.abspath(a.carton))[0] + ".meta.json"
    if os.path.exists(_mj):
        import json as _js
        _dv = _js.load(open(_mj))["derived"]
        # ★ 2026-09-26:箱壁改成四面各自的高度(讓位給蓋子板厚)之後,
        #   wall_top_z 只剩下「--height 參數本身」的意思,不再是任何一面牆的實際高度。
        #   真正的牆高是 wall_top_x(±x,下層蓋那兩面)/ wall_top_y(±y,上層蓋那兩面)。
        #   舊的 meta 沒有這兩個欄位 → 退回 wall_top_z。
        CBOX = dict(ix=float(_dv["wall_inner_x"]), iy=float(_dv["wall_inner_y"]),
                    top=float(_dv.get("wall_top_x", _dv["wall_top_z"])),
                    top_y=float(_dv.get("wall_top_y", _dv["wall_top_z"])),
                    hz_lo=float(_dv["lower_hinge_z"]), hz_up=float(_dv["upper_hinge_z"]))
        P("★ 紙箱幾何(從 meta 讀,不寫死):內腔 ±%.0f x ±%.0f;"
          "牆高 ±x %.1f / ±y %.1f;鉸鏈 下層 %.1f / 上層 %.1f mm"
          % (CBOX["ix"]*1e3, CBOX["iy"]*1e3, CBOX["top"]*1e3, CBOX["top_y"]*1e3,
             CBOX["hz_lo"]*1e3, CBOX["hz_up"]*1e3))
    else:
        P("⚠ 找不到 %s —— 沒有 meta 就不要猜鉸鏈位置" % _mj)

LID_REST_CLOSED = False
def _rodr(v, h, ax, deg):
    """點 v 繞過 h、方向 ax 的軸轉 deg 度(右手)。蓋子方向自檢用。"""
    ax = np.asarray(ax, float)/np.linalg.norm(ax); th = np.radians(deg); r = np.asarray(v, float) - h
    return h + r*np.cos(th) + np.cross(ax, r)*np.sin(th) + ax*np.dot(ax, r)*(1.0 - np.cos(th))

if a.carton and CBOX and (a.reveal or a.close_lid or MOVE is not None):
    # ★ 2026-09-25 兩個訂正:
    #   (1) 鉸鏈高度**不可寫死**。我原本用 100mm 箱的 0.092/0.0985,
    #       套到 130/180 的箱子就變成繞著低 80mm 的軸轉,蓋子從箱子中段掃過去把布掀飛
    #       (實測布從 139mm 爆到 273mm)。現在從 meta 的 lower/upper_hinge_z 讀。
    #   (2) 角度方向也反了:生成器產出的姿態是**蓋住**(折邊從箱壁往箱內延伸),
    #       所以 0°=關、180°=開,要 180°→0° 才是關蓋。
    _hx, _hy = CBOX["ix"], CBOX["iy"]
    for nm, hinge, axis, order in (
            # ★ 2026-09-25 第三個訂正:轉軸方向也反了。
            #   折邊是從鉸鏈往**箱內**指的(fxp 在 x=+132,板子往 -x 延伸)。
            #   要把它往上掀,fxp 必須繞 **+y**:R(+y,90°)(-x̂) = +ẑ。
            #   我原本用 -y,R(-y,90°)(-x̂) = -ẑ —— 蓋子是往箱內**下方**掃,
            #   直接插進布裡,實測布被擠成 x 145mm、高度爆到 255mm。
            ("fxp", ( _hx, 0.0, CBOX["hz_lo"]), (0.0,  1.0, 0.0), 0),
            ("fxn", (-_hx, 0.0, CBOX["hz_lo"]), (0.0, -1.0, 0.0), 0),
            ("fyp", (0.0,  _hy, CBOX["hz_up"]), (-1.0, 0.0, 0.0), 1),
            ("fyn", (0.0, -_hy, CBOX["hz_up"]), ( 1.0, 0.0, 0.0), 1)):
        pr = st.GetPrimAtPath("/World/Box/" + nm)
        if not pr.IsValid():
            P("  ⚠ 找不到 /World/Box/%s" % nm); continue
        LIDS.append(dict(nm=nm, h=np.array(hinge), ax=np.array(axis), order=order,
                         T0=Gf.Matrix4d(UsdGeom.Xformable(pr)
                                        .ComputeLocalToWorldTransform(Usd.TimeCode.Default()))))
        # ★ 2026-10-02 蓋子方向自檢(從 USD 量,不信註解):
        #   USD 預設姿態是開還是關 = 蓋子中心在鉸鏈的箱內側還是箱外側;
        #   「開」的方向 = 轉 +90° 與 −90° 哪一個讓蓋子中心比較高。
        _L = LIDS[-1]
        _r = (UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
              .ComputeWorldBound(pr).ComputeAlignedRange())
        _c = (np.array(_r.GetMin()) + np.array(_r.GetMax()))/2.0
        _zp = _rodr(_c, _L["h"], _L["ax"], +90.0)[2]; _zn = _rodr(_c, _L["h"], _L["ax"], -90.0)[2]
        _L["sgn"] = 1.0 if _zp >= _zn else -1.0
        _L["rest_closed"] = bool(np.linalg.norm(_c[:2]) < np.linalg.norm(_L["h"][:2]))
        _L["c_loc"] = _L["T0"].GetInverse().Transform(Gf.Vec3d(*map(float, _c)))   # 蓋中心(蓋子局部座標)
        P("  蓋 %s:USD 預設中心 (%.1f, %.1f, %.1f) mm → %s;轉 +90° 中心 z=%.1f、−90° z=%.1f ⇒ 開 = 轉 %s180°"
          % (nm, *(_c*1e3), "關(在鉸鏈內側)" if _L["rest_closed"] else "開(在鉸鏈外側)",
             _zp*1e3, _zn*1e3, "+" if _L["sgn"] > 0 else "−"))
    _rc = [L["rest_closed"] for L in LIDS]
    LID_REST_CLOSED = bool(_rc) and all(_rc)
    P("★ 蓋子:%d 片。下層 fx 鉸鏈 z=%.1f、上層 fy z=%.1f;USD 預設 = %s;關蓋 = 180°→0°"
      % (len(LIDS), CBOX["hz_lo"]*1e3, CBOX["hz_up"]*1e3,
         "關" if LID_REST_CLOSED else ("開" if not any(_rc) else "混合(%s)" % _rc)))
    if a.lid_dynamic:
        # ★ 2026-09-26:USD 只帶**被動關節**(±185°、無 drive)。彈塑性摺痕是**執行期**的事,
        #   USD 帶不了 —— 沒有它蓋子就會自己垂下來(使用者看出來的:「底蓋居然是向下彎」)。
        #   作法照 run_crease.py:每個物理步算力矩,用 apply_forces_and_torques_at_pos
        #   施加**全域力矩**在蓋子剛體上,不是用關節 drive。
        P("  ★ 蓋子動態 + 彈塑性摺痕(每物理步外加力矩,照 run_crease.py 的作法)")

# ── 杯子剛體 ─────────────────────────────────────────────────────────
# ★ 使用者 2026-09-25:「開始的時候杯子在布上面,看起來杯子有穿模」。
#   布的 surfaceThickness = 10mm ⇒ 碰撞面比網格面外擴 5mm。
#   先前放在 H2 + 2mm,杯底其實陷在布的碰撞層裡面 3mm,畫面上就是陷進去。
MZ = PLAT_Z + H2 + THICK/2 + 0.002 + CDZ
mug = UsdGeom.Xform.Define(st, "/World/mug")
UsdGeom.Xformable(mug).AddTranslateOp().Set(Gf.Vec3d(0, 0, MZ))
# ★ 使用者指示「杯子可以先固定」:**從第 0 幀就 kinematic**。
# 先前從 t=1.5s 才固定,結果折好的布在那之前就把杯子擠出去(z 278→202,掉 76mm),
# 於是 W1 俯視遮蔽 99% 是假的 —— 布懸在杯子正上方,射線當然打得到。
UsdPhysics.RigidBodyAPI.Apply(mug.GetPrim()).CreateKinematicEnabledAttr(bool(a.hold_mug))
prb = PhysxSchema.PhysxRigidBodyAPI.Apply(mug.GetPrim())
prb.CreateLinearDampingAttr(0.3); prb.CreateAngularDampingAttr(0.6)
UsdPhysics.MassAPI.Apply(mug.GetPrim()).CreateMassAttr(0.0807)
g = UsdGeom.Mesh.Define(st, "/World/mug/geo")
g.CreatePointsAttr([Gf.Vec3f(*map(float, p)) for p in V])
g.CreateFaceVertexIndicesAttr([int(i) for f in F for i in f])
g.CreateFaceVertexCountsAttr([3]*len(F)); g.CreateSubdivisionSchemeAttr().Set("none")
g.CreateDoubleSidedAttr(True)   # STL 的面繞向不一定一致;看到背面就是暗的
UsdPhysics.CollisionAPI.Apply(g.GetPrim())
UsdPhysics.MeshCollisionAPI.Apply(g.GetPrim()).CreateApproximationAttr("convexDecomposition")
gc = PhysxSchema.PhysxCollisionAPI.Apply(g.GetPrim())
gc.CreateContactOffsetAttr(0.004); gc.CreateRestOffsetAttr(0.001)
UsdShade.MaterialBindingAPI.Apply(g.GetPrim()).Bind(MUGM)

# ── 布 ───────────────────────────────────────────────────────────────
nx = ny = a.res
K_CORNER = 0.15          # 角落錐面比例。0 會讓角落塌成一條線 → 110 個退化三角形

def fold_map(u, v):
    """最近點投影折疊。純幾何,沒有物理。

    ★ 2026-09-24 第三版。前兩版都錯:
      v1 兩個 if 接連套用 → 角落被壓成零面積,500 個退化三角形,**整塊布不模擬**
      v2 角落跳過 x 映射 → 只有上下折、左右沒折(使用者看出來的)
      v3(這版)每個點投影到內框邊界上最近的點當落點,沿「爬杯側 → 橫過杯頂」走它的距離。
                角落自然沿對角線走,四邊都完整;角落再加一個小錐面(真實包裝的三角摺),
                否則整個角落象限會塌到內框角的那一條垂直線上。
    """
    Hm = ME[2]
    qx = min(max(u, -CX), CX); qy = min(max(v, -CY), CY)
    dx, dy = u - qx, v - qy
    s_ = float(np.hypot(dx, dy))
    if s_ < 1e-12:
        return u, v, PLAT_Z
    nx_, ny_ = dx/s_, dy/s_
    corner = (abs(u) > CX) and (abs(v) > CY)
    kc = K_CORNER if corner else 0.0
    if s_ <= Hm:
        rho = kc*s_
        return qx + nx_*rho, qy + ny_*rho, PLAT_Z + s_*np.sqrt(max(1e-9, 1.0-kc*kc))
    d = s_ - Hm
    rho0 = kc*Hm
    return qx + nx_*rho0 - nx_*d, qy + ny_*rho0 - ny_*d, PLAT_Z + Hm

ap_center = True
SP0 = None
if a.init_npz:
    SP0 = np.load(a.init_npz)["sheet"]
    P("★ 第二段:布以第一段的結果出生(%s,%d 頂點)" % (a.init_npz, len(SP0)))
    if a.carton:
        # ★ 使用者 2026-09-25:「放進去的時候 未壓之前 穿模就要為 0」。
        #   實測:包裹的 bbox 中心在 (0.3, -21.4) mm,整包往 -y 偏了 21mm,
        #   於是有 14 個頂點在 y=-128~-112 穿出箱壁(牆在 ±112)。
        #   放進箱子時先把 xy 置中 —— 這是純座標的事,不是物理問題。
        #
        # ★ 2026-09-26 修:入箱要把**布和杯子當成一整包剛性搬進去**。
        #   舊版只搬布的 xy,杯子留在原地、而且還被 MZ 公式另外加了 CDZ
        #   ⇒ 布相對杯子位移了 (2.4, -3.4, -3.0) mm,三個軸都錯開。
        #   實測後果:入箱的第 0 格就有 94 條邊陷進杯面約 2mm,而且關蓋全程沒再變糟
        #   —— 階躍而非漸增,坐實是搬移造成的,不是被壓出來的。
        #   (量法:每條邊取 19 個內點做 trimesh.contains。只測頂點會漏 —— 頂點判定是 0。)
        _c = (SP0[:, :2].min(0) + SP0[:, :2].max(0))/2.0
        _dz = CDZ - float(SP0[:, 2].min())      # 整包坐到箱底內面上,順便保證不穿箱底
        _sh = np.array([-_c[0], -_c[1], _dz])
        # ★ 2026-10-02 修:杯子靜止頂點 V 是 **bbox 置中**(V -= (max+min)/2),不是平均置中。
        #   舊版用頂點平均當杯子平移量,實測平均在 (-8.8,-5.5) mm ⇒ 杯子被多搬一次、跟布錯開 ~10mm。
        #   杯子是 kinematic 沒轉 ⇒ 世界頂點的 bbox 中心才是它的平移量。
        _mq = np.load(a.init_npz)["mug"]
        _mp0 = (_mq.min(0) + _mq.max(0))/2.0         # 上一段杯子的世界位置
        #   ★ 2026-09-30(foldorder):npz 的 mug 是上一段的**世界座標**頂點(V @ Rm.T + 平移),這裡只拿它的中心
        #     當平移量;方位由每一段各自在載入 STL 時套 _Rm 到 V 決定,所以不會被轉兩次。
        #     但也因此 **_Rm 加進來之前產生的 npz 不能混用**(那時的布是包在 杯口 −x/杯耳 −y 的杯子外面)。
        if a.in_box_already:
            # npz 已經是箱內座標(例如 lidcheck/wrap.npz)⇒ 不再平移。
            # 下面建布頂點會每點 +CDZ,這裡先扣掉,淨位移 = 0(實測不扣時會多墊 +2mm 再被杯子壓進底板)
            _sh = np.zeros(3)
            SP0 -= np.array([0.0, 0.0, CDZ])
        else:
            SP0 += _sh
        # 下面建布頂點時每點還會再 +CDZ(第一段沿用的寫法),杯子也要加同一個量,兩者才是同一個位移
        _sh_all = _sh + np.array([0.0, 0.0, 0.0 if a.in_box_already else CDZ])
        UsdGeom.Xformable(mug).GetOrderedXformOps()[0].Set(Gf.Vec3d(*(_mp0 + _sh_all)))
        P("★ 入箱:整包(布+杯子)剛性搬 (%+.1f, %+.1f, %+.1f) mm —— "
          "杯子跟著搬,保住包覆時的相對位置;杯心 %s → %s mm"
          % (*(_sh_all*1e3), np.round(_mp0*1e3, 1), np.round((_mp0 + _sh_all)*1e3, 1)))

verts = []
for j in range(ny+1):
    for i in range(nx+1):
        u0 = -WX/2 + i*WX/nx; v0 = -WY/2 + j*WY/ny
        if SP0 is not None:
            u1, v1, z1 = SP0[j*(nx+1)+i]
            z1 += CDZ
            verts.append(Gf.Vec3f(float(u1), float(v1), float(z1)))
            continue
        if a.fold_init:
            u1, v1, z1 = fold_map(u0, v0)
        else:
            u1, v1, z1 = u0, v0, PLAT_Z
        verts.append(Gf.Vec3f(float(u1), float(v1), float(z1)))
P("布的初始幾何:%s" % ("第一段模擬的結果" if SP0 is not None else ("**直接生成已折好的形狀**(不用夾具)" if a.fold_init else "平鋪")))
if SP0 is not None:
    # ★ 2026-10-02:movebox 時杯子(動態)一開始就落 ~5mm,把布壓穿底板。量出生時杯子懸空多少:
    #   杯子最低點 z − 杯子正下方(杯子 xy 範圍內、低於杯心)布頂點的最高 z。
    _mt = np.array(UsdGeom.Xformable(mug).GetOrderedXformOps()[0].Get(), float)
    _MW0 = V + _mt
    _SV = np.array([[p[0], p[1], p[2]] for p in verts])
    # 杯子躺平,最低處是一條線:只取杯子最低 3mm 那圈頂點的 xy(外擴 10mm)當「正下方」,
    # 不然包在杯子側面的布也會被算進去(第一版量出 -43.7mm 就是這個錯)
    _bot = _MW0[_MW0[:, 2] < _MW0[:, 2].min() + 0.003]
    _lo2, _hi2 = _bot[:, :2].min(0) - 0.010, _bot[:, :2].max(0) + 0.010
    _under = ((_SV[:, 0] > _lo2[0]) & (_SV[:, 0] < _hi2[0]) & (_SV[:, 1] > _lo2[1]) & (_SV[:, 1] < _hi2[1])
              & (_SV[:, 2] < _mt[2] - 0.020))
    if _under.any():
        _gap = float(_MW0[:, 2].min() - _SV[_under, 2].max())
        P("★ 杯子出生:最低點 z=%.1f mm,正下方布最高 z=%.1f mm(%d 頂點)⇒ 差 %.1f mm(布半厚 %.1f mm)"
          % (_MW0[:, 2].min()*1e3, _SV[_under, 2].max()*1e3, int(_under.sum()), _gap*1e3, THICK/2*1e3))
        if MOVE is not None and _gap - THICK/2 > 0.002:
            _dz2 = _gap - THICK/2
            UsdGeom.Xformable(mug).GetOrderedXformOps()[0].Set(Gf.Vec3d(*(_mt - np.array([0, 0, _dz2]))))
            P("   ⇒ movebox:杯子懸空 > 2mm,初始 z 降 %.1f mm 到剛好碰到布面(差 = 布半厚)" % (_dz2*1e3))
tris = []
for j in range(ny):
    for i in range(nx):
        A0 = j*(nx+1)+i
        tris += [(A0, A0+1, A0+nx+2), (A0, A0+nx+2, A0+nx+1)]
sh = UsdGeom.Mesh.Define(st, "/World/sheet")
sh.GetPointsAttr().Set(Vt.Vec3fArray(verts))
sh.GetFaceVertexCountsAttr().Set([3]*len(tris))
sh.GetFaceVertexIndicesAttr().Set([k for t in tris for k in t])
sh.CreateDoubleSidedAttr(True)
sp = sh.GetPrim()
# ★ 依**攤平時**的 (u,v) 上棋盤格 → 折起來後格子跟著彎,
#   一眼就能確認「這是同一張布被折」,不是拼出來的盒子。
NSQ = 8
cols = []
for j in range(ny+1):
    for i in range(nx+1):
        u0 = -WX/2 + i*WX/nx; v0 = -WY/2 + j*WY/ny
        k = (int((u0 + WX/2)/(WX/NSQ)) + int((v0 + WY/2)/(WY/NSQ))) % 2
        cols.append(Gf.Vec3f(0.95, 0.55, 0.15) if k else Gf.Vec3f(0.10, 0.22, 0.45))  # 高對比,淡色會被打光打爆
sh.CreateDisplayColorAttr(cols)
if a.tex:
    _tl = a.tex_mm/1000.0
    _stv = Vt.Vec2fArray([Gf.Vec2f(float((-WX/2 + i2*WX/nx)/_tl), float((-WY/2 + j2*WY/ny)/_tl))
                          for j2 in range(ny+1) for i2 in range(nx+1)])
    _pv = UsdGeom.PrimvarsAPI(sp).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
                                                UsdGeom.Tokens.vertex)
    _pv.Set(_stv)
    P("★ 泡泡布貼圖:%s,一張代表 %.0fmm 見方 → 布上平鋪 %.1f x %.1f 次"
      % (a.tex, a.tex_mm, WX/_tl, WY/_tl))
sh.GetPrim().GetAttribute("primvars:displayColor").SetMetadata("interpolation", "vertex")
P("布上了 %dx%d 棋盤格(依攤平座標)—— 折起來後看格子就知道是同一張布" % (NSQ, NSQ))
phm = UsdShade.Material.Define(st, "/World/sheetPhys"); pp = phm.GetPrim()
pp.ApplyAPI("OmniPhysicsBaseMaterialAPI")
sa(pp, "omniphysics:dynamicFriction", FRIC); sa(pp, "omniphysics:density", DENS)
pp.ApplyAPI("OmniPhysicsDeformableMaterialAPI")
sa(pp, "omniphysics:youngsModulus", YOUNGS); sa(pp, "omniphysics:poissonsRatio", POISSON)
pp.ApplyAPI("OmniPhysicsSurfaceDeformableMaterialAPI")
sa(pp, "omniphysics:surfaceThickness", THICK); sa(pp, "omniphysics:surfaceBendStiffness", BEND)
pp.ApplyAPI("PhysxSurfaceDeformableMaterialAPI")
sa(pp, "physxDeformableMaterial:elasticityDamping", EDAMP)
sa(pp, "physxDeformableMaterial:bendDamping", BDAMP)
ok = deformableUtils.set_physics_surface_deformable_body(st, sp.GetPath())
sp.ApplyAPI("PhysxSurfaceDeformableBodyAPI")
# ★ 以下四項照 tex_bubble_mug.usd 讀出來的值(先前我自己設 selfCollision=True,其餘沒設)
sa(sp, "physxDeformableBody:selfCollision", bool(a.selfcol))
sa(sp, "omniphysics:restBendAnglesDefault", "flatDefault", Sdf.ValueTypeNames.Token)
if a.sleepy:
    # ★ 2026-09-24 實測:這三個一起上,布在 t=0.83s 後 16 秒 bbox 一動也不動(睡著了),
    #   折疊階段等於沒跑。要讓布真的被折,就得 --no_sleepy。
    sa(sp, "physxDeformableBody:settlingDamping", 10.0, Sdf.ValueTypeNames.Float)
    sa(sp, "physxDeformableBody:settlingThreshold", 0.10, Sdf.ValueTypeNames.Float)
    sa(sp, "physxDeformableBody:sleepThreshold", 0.05, Sdf.ValueTypeNames.Float)
P("★ 折疊終點 z 分層:每折 +%.0f mm(布碰撞厚度 10mm)" % a.layer_mm)
P("sleep 參數(他們的):%s" % ("套用" if a.sleepy else "關閉"))
sa(sp, "physxDeformableBody:solverPositionIterationCount", a.solver, Sdf.ValueTypeNames.Int)
sa(sp, "physxDeformableBody:linearDamping", LDAMP, Sdf.ValueTypeNames.Float)
if a.self_filter >= 0:
    sa(sp, "physxDeformableBody:selfCollisionFilterDistance", float(a.self_filter), Sdf.ValueTypeNames.Float)
if a.pair_freq > 0:
    sa(sp, "physxDeformableBody:collisionPairUpdateFrequency", int(a.pair_freq), Sdf.ValueTypeNames.Int)
if a.col_iter_mult > 0:
    sa(sp, "physxDeformableBody:collisionIterationMultiplier", int(a.col_iter_mult), Sdf.ValueTypeNames.Int)
if a.ccd:
    sa(sp, "physxDeformableBody:enableSpeculativeCCD", True, Sdf.ValueTypeNames.Bool)
P("布 collider:contactOffset %.1fmm / restOffset %.2fmm | surfaceThickness %.0fmm | layer_mm %.0f | selfFilter %s pairFreq %s colIterMult %s ccd %s"
  % (CONT*1e3, REST*1e3, THICK*1e3, a.layer_mm, a.self_filter, a.pair_freq, a.col_iter_mult, a.ccd))
P("錨點幾何:hold_mm %.1f | tip_over_mm %.1f | no_anchor %s | release_after %s | no_hold %s"
  % (a.hold_mm, a.tip_over_mm, a.no_anchor, ("%.2fs" % a.release_after) if a.release_after >= 0 else "never", a.no_hold))
pc = PhysxSchema.PhysxCollisionAPI.Apply(sp)
pc.CreateRestOffsetAttr().Set(REST); pc.CreateContactOffsetAttr().Set(CONT)
mb = UsdShade.MaterialBindingAPI.Apply(sp)
mb.Bind(phm, UsdShade.Tokens.weakerThanDescendants, "physics")
if not a.checker:
    mb.Bind(FILM)          # 半透明膜
else:
    P("★ checker 模式:不綁材質,直接顯示頂點棋盤色(要看出是同一張布)")
P("surface deformable=%s ;布 %d 頂點" % (ok, len(verts)))

# ── 攤開用的錨:抓住四片折邊的外緣,拉回攤平位置 ──────────────────────
# ★ 這是 probe_attach2 驗證過的結構(誤差 0mm、帶起 109mm、陰性對照完全不動):
#   帶 PhysxAutoDeformableAttachmentAPI 的 Scope +**掛在 Scope 底下**的 vtx 子 prim。
#   掛在 mesh 底下不生效 —— 這是兩天裡最關鍵的一個位置差異。
# ── 他們那款包材:剛體泡泡貼在膜上 ──────────────────────────────────
# 參數照抄 mission0921/step10_rigid_bubble_pack_lift.py:
#   半徑 13mm、壓扁 0.45、間距 30mm、質量 1g、膜 opacity 0.18、泡泡 0.35
# 綁定用已驗證的結構(Scope 帶 API + **子 prim 掛 Scope 底下**)。
if a.bubbles:
    UsdGeom.Xform.Define(st, "/World/bubbles")
    _FL = np.array([[-WX/2 + i2*WX/nx, -WY/2 + j2*WY/ny, 0.0]
                    for j2 in range(ny+1) for i2 in range(nx+1)])
    _FD = np.array([[v[0], v[1], v[2]] for v in verts])
    nb = 0; _placed = []
    for by in np.arange(-WY/2 + a.bub_pitch, WY/2 - a.bub_pitch/2, a.bub_pitch):
        for bx in np.arange(-WX/2 + a.bub_pitch, WX/2 - a.bub_pitch/2, a.bub_pitch):
            vi = int(np.argmin((_FL[:, 0]-bx)**2 + (_FL[:, 1]-by)**2))   # 最近的布頂點
            # ★ 泡泡要照**折好之後**的位置做間距檢查。照攤平座標鋪的話,
            #   折疊會把很多頂點擠在一起 → 泡泡互相重疊 → 剛體互斥把布炸開
            #   (實測 bbox 衝到 1121x1304mm)。他們的 step10 是鋪在平的布上,沒這問題。
            if _placed and min(np.linalg.norm(np.array(_placed) - _FD[vi], axis=1)) < a.bub_r*2.2:
                continue
            _placed.append(_FD[vi])
            nb += 1
            bp = "/World/bubbles/b%03d" % nb
            sph = UsdGeom.Sphere.Define(st, bp); sph.CreateRadiusAttr(a.bub_r)
            _bx = UsdGeom.Xformable(sph)
            _bx.AddTranslateOp().Set(Gf.Vec3d(*[float(x) for x in _FD[vi]]))
            _bx.AddScaleOp().Set(Gf.Vec3f(1, 1, 0.45))                   # 他們的壓扁比
            UsdPhysics.RigidBodyAPI.Apply(sph.GetPrim())
            UsdPhysics.MassAPI.Apply(sph.GetPrim()).CreateMassAttr(0.001)
            UsdPhysics.CollisionAPI.Apply(sph.GetPrim())
            _bc = PhysxSchema.PhysxCollisionAPI.Apply(sph.GetPrim())
            _bc.CreateRestOffsetAttr().Set(0.0); _bc.CreateContactOffsetAttr().Set(0.002)
            UsdShade.MaterialBindingAPI.Apply(sph.GetPrim()).Bind(BUBM)
            _sc = st.DefinePrim("/World/attach/bub%03d" % nb, "Scope")
            _sc.ApplyAPI("PhysxAutoDeformableAttachmentAPI")
            for _k, _v in [("enableDeformableVertexAttachments", True),
                           ("enableRigidSurfaceAttachments", False),
                           ("enableCollisionFiltering", True),
                           ("enableDeformableFilteringPairs", False)]:
                sa(_sc, "physxAutoDeformableAttachment:" + _k, _v, Sdf.ValueTypeNames.Bool)
            sa(_sc, "physxAutoDeformableAttachment:deformableVertexOverlapOffset", 0.006, Sdf.ValueTypeNames.Float)
            sa(_sc, "physxAutoDeformableAttachment:collisionFilteringOffset", 0.022, Sdf.ValueTypeNames.Float)
            for _rn, _tg in [("attachable0", "/World/sheet"), ("attachable1", bp)]:
                (_sc.GetRelationship("physxAutoDeformableAttachment:" + _rn) or
                 _sc.CreateRelationship("physxAutoDeformableAttachment:" + _rn)).SetTargets([Sdf.Path(_tg)])
            _ch = st.DefinePrim("/World/attach/bub%03d/vtx_xform_attachment" % nb,
                                "OmniPhysicsVtxXformAttachment")
            sa(_ch, "omniphysics:attachmentEnabled", True, Sdf.ValueTypeNames.Bool)
            sa(_ch, "omniphysics:damping", 0.0, Sdf.ValueTypeNames.Float)
            sa(_ch, "omniphysics:stiffness", float("inf"), Sdf.ValueTypeNames.Float)
            sa(_ch, "omniphysics:vtxIndicesSrc0", Vt.IntArray([vi]), Sdf.ValueTypeNames.IntArray)
            sa(_ch, "omniphysics:localPositionsSrc1", Vt.Vec3fArray([Gf.Vec3f(0, 0, 0)]),
               Sdf.ValueTypeNames.Point3fArray)
            for _rn, _tg in [("src0", "/World/sheet"), ("src1", bp)]:
                (_ch.GetRelationship("omniphysics:" + _rn) or
                 _ch.CreateRelationship("omniphysics:" + _rn)).SetTargets([Sdf.Path(_tg)])
            # ★ 第二個子 prim:關掉泡泡與它腳下那塊布的碰撞。
            #   他們存檔裡每個 attachment 都有 vtx_xform_attachment **和** element_filter_0。
            #   只寫前者的話,每顆泡泡都在跟自己黏著的布互斥 → 布被炸開
            #   (實測 bbox 衝到 1624x1189mm)。
            _near = [ti for ti, _t in enumerate(tris)
                     if np.linalg.norm(_FD[list(_t)] - _FD[vi], axis=1).min() < 0.022]
            _ef = st.DefinePrim("/World/attach/bub%03d/element_filter_0" % nb,
                                "OmniPhysicsElementCollisionFilter")
            sa(_ef, "omniphysics:filterEnabled", True, Sdf.ValueTypeNames.Bool)
            sa(_ef, "omniphysics:groupElemCounts0", Vt.UIntArray([len(_near)]), Sdf.ValueTypeNames.UIntArray)
            sa(_ef, "omniphysics:groupElemIndices0", Vt.UIntArray([int(x) for x in _near]), Sdf.ValueTypeNames.UIntArray)
            sa(_ef, "omniphysics:groupElemCounts1", Vt.UIntArray([]), Sdf.ValueTypeNames.UIntArray)
            sa(_ef, "omniphysics:groupElemIndices1", Vt.UIntArray([]), Sdf.ValueTypeNames.UIntArray)
            for _rn, _tg in [("src0", "/World/sheet"), ("src1", bp)]:
                (_ef.GetRelationship("omniphysics:" + _rn) or
                 _ef.CreateRelationship("omniphysics:" + _rn)).SetTargets([Sdf.Path(_tg)])
    P("★ 他們那款包材:%d 顆泡泡(折好座標下最小間距 %.0fmm 過濾後)" % (nb, a.bub_r*2.2*1e3) if False else "★ 他們那款包材:%d 顆泡泡(半徑 %.0fmm、壓扁 0.45、間距 %.0fmm、1g),各自綁在最近的布頂點"
      % (nb, a.bub_r*1e3, a.bub_pitch*1e3))

Z_FLOOR = 0.015      # 「還貼在地板上」的門檻(m)
LZ_HOLD = a.hold_mm/1000.0   # 折完之後錨點停在杯頂上方幾 m(原寫死 0.012,現由 --hold_mm 給)
FLOORE = None
INFOLD = set()
if a.floor_edges and os.path.exists(a.floor_edges):
    import json as _json
    FLOORE = {k: set(v) for k, v in _json.load(open(a.floor_edges)).items()}
    P("★ 後兩折抓的邊來自實測:%s" % {k: len(v) for k, v in FLOORE.items()})
    # ★ 2026-09-30:floor_edges.json 記的是「後兩折那條邊上還貼地的頂點」,鍵名就是後兩折的邊。
    #   折序改成 x 先之後後兩折是 y;舊 json(鍵 xp/xn)會讓 FLOORE.get("yp", []) 全空
    #   ⇒ 後兩折一個錨點都不建、y 邊安靜地沒折到。直接擋掉,逼人用新折序的兩折結果重量。
    if set(FLOORE) != set(STAGE2_SIDES):
        raise SystemExit("★ %s 的鍵 %s 不是後兩折 %s —— 這份是舊折序量的,要重量"
                         % (a.floor_edges, sorted(FLOORE), STAGE2_SIDES))

PULLS = []
#   ★ 提杯測試不建錨點:布要完全自由,才測得出「是不是靠包覆撐住」
if (a.unfold or a.wrapsim or a.unbox) and a.press <= 0 and (a.unbox or not a.carton) \
        and a.lift_mug <= 0 and not a.no_anchor:
    # ★ 攤開要攤成**正方形**,所以整圈外緣的每一個點都要有自己的錨,
    #   各自拉回它攤平時的位置。先前只用 4 個錨抓四條邊的中段 →
    #   四個角沒人拉,留在對角線上凸出去,攤開變成菱形(610x613 且形狀不方)。
    FLAT = np.array([[-WX/2 + i2*WX/nx, -WY/2 + j2*WY/ny, PLAT_Z]
                     for j2 in range(ny+1) for i2 in range(nx+1)])
    FOLD = np.array([[v[0], v[1], v[2]] for v in verts])
    bnd = np.where((np.abs(FLAT[:, 0]) > WX/2 - 1e-6) | (np.abs(FLAT[:, 1]) > WY/2 - 1e-6))[0]
    SIDEPICK = {}      # 挑點時決定的「這個頂點屬於哪一邊」(wrapsim / unbox 用;見下面 PULLS 的分邊)
    if a.unbox:
        # ★ 使用者 2026-09-26:「把之間的 attach 點拿回來逆向」。
        #   開包材不是整圈一起掀:
        #     先打開的是**最後折的兩邊**(FOLD_ORDER[2:],現在是 ±y)—— 當初只抓「還貼地的那一段」(floor_edges),不是整條
        #     後打開的是**先折的兩邊**(FOLD_ORDER[:2],現在是 ±x)—— 當初是**整條邊**(不含角落)
        #   所以這裡用跟折疊完全相同的分組,只是順序反過來(順序本身在 drive() 用 UORDER)。
        keep2 = []
        for vi_ in bnd:
            fx_, fy_ = FLAT[vi_][0], FLAT[vi_][1]
            sx_ = max(0.0, abs(fx_) - CX); sy_ = max(0.0, abs(fy_) - CY)
            sd_ = ("yp" if fy_ > 0 else "yn") if sy_ >= sx_ else ("xp" if fx_ > 0 else "xn")
            ax_ = 1 if sd_ in ("yp", "yn") else 0                                  # 這條邊沿哪一軸(軸語意)
            if abs(abs(FLAT[vi_][ax_]) - (WY/2 if ax_ == 1 else WX/2)) > 1e-6: continue   # 只取該邊最外圈
            if sd_ in FOLD_ORDER[:2]:                                              # 先折的邊:整條,不含角落
                if abs(FLAT[vi_][1 - ax_]) > (WX/2 if ax_ == 1 else WY/2) - 1e-6: continue
            else:                                                                  # 後折的邊:只有實測仍貼地的那段
                if FLOORE is not None and int(vi_) not in FLOORE.get(sd_, []): continue
            keep2.append(int(vi_)); SIDEPICK[int(vi_)] = sd_
        INFOLD = set(keep2)      # 當初折疊真正施力的那些;其餘只在最後「完整攤平」時才動
        P("★ 開箱錨點:整圈外緣 %d 個;其中當初折疊用的 %d 個(逆向打開用),"
          "其餘 %d 個只在最後完整攤平時才動"
          % (len(bnd), len(INFOLD), len(bnd)-len(INFOLD)))
    elif a.stage2:
        # ★ 使用者 2026-09-25:「後兩折的時候,前兩折只剩杯子以上維持,其他都放力」
        hx_, hy_ = ME[0]/2, ME[1]/2
        hold = np.where((FOLD[:, 2] > ME[2]*0.65) &
                        (np.abs(FOLD[:, 0]) < hx_) & (np.abs(FOLD[:, 1]) < hy_))[0]
        if a.no_hold:
            hold = np.array([], dtype=int)      # --no_hold:第一段的布完全放力,靠重力與摩擦留在原地
        # ★ 2026-09-30:「還貼地的那條邊」要抓**後兩折那一軸**的最外圈,由 STAGE2_SIDES 決定,
        #   不再寫死 x(折序改 x 先之後,後兩折是 y;寫死抓 x 邊會讓 y 一個錨點都沒有)。
        _s2ax = 0 if STAGE2_SIDES[0] in ("xp", "xn") else 1      # 後兩折的軸:0=x、1=y
        _s2w = WX if _s2ax == 0 else WY
        fl = [int(v) for v in bnd
              if abs(abs(FLAT[v, _s2ax]) - _s2w/2) < 1e-6 and FOLD[v, 2] < Z_FLOOR]
        SIDE2 = {}
        for v in hold: SIDE2[int(v)] = "hold"
        for v in fl:   SIDE2[int(v)] = "xy"[_s2ax] + ("p" if FLAT[v, _s2ax] > 0 else "n")
        assert all(s in STAGE2_SIDES for s in SIDE2.values() if s != "hold")
        bnd = np.array(sorted(SIDE2.keys()))
        P("★ 第二段錨點:杯子正上方維持壓住 %d 個;還貼地(z<%.0fmm)的 %s 邊 %d 個;"
          "其餘 %d 個頂點完全不施力"
          % (len(hold), Z_FLOOR*1e3, "/".join(STAGE2_SIDES), len(fl), len(FOLD) - len(bnd)))
    elif a.wrapsim:
        # ★ 使用者 2026-09-25:前兩次動**整邊**,後兩次先暫停。
        #   要折的邊 → 那條邊上的**每一個**外緣頂點都給施力點(整邊一起抬)
        #   暫停的邊 → 完全不建錨點,布自己垂著,一點力都不施
        ORD_ = FOLD_ORDER[:max(1, min(4, a.wrap_n))]
        keep = []
        for vi_ in bnd:
            fx_, fy_ = FLAT[vi_][0], FLAT[vi_][1]
            sx_ = max(0.0, abs(fx_) - CX); sy_ = max(0.0, abs(fy_) - CY)
            sd_ = ("yp" if fy_ > 0 else "yn") if sy_ >= sx_ else ("xp" if fx_ > 0 else "xn")
            if sd_ not in ORD_:
                continue
            if a.wrap_edge:
                # 整邊:只取**最外圈**那一排(該邊的極值座標),不含垂直於它的兩側
                ax_ = 1 if sd_ in ("yp", "yn") else 0
                lim_ = (WY/2 if ax_ == 1 else WX/2)
                if abs(abs(FLAT[vi_][ax_]) - lim_) > 1e-6:
                    continue
                # ★ 使用者 2026-09-25:「後兩邊依樣是邊,只是這個邊不是整個正方形邊,
                #   而只剩最靠近地板的」。所以**整條邊都建錨點**,
                #   輪到它的那一刻才用「當下 z 是否還貼地」決定哪些真的施力(見 drive())。
                #   實測 wrap2:+x 端 455 個點裡有 165 個還貼地(z<15mm),
                #   我先前用攤平座標圈只圈到 9 個 —— 那是錯的。
                # ★ 2026-09-30:下面兩條是**折序**語意(先折/後折),不是軸語意,所以看 FOLD_ORDER。
                if sd_ in FOLD_ORDER[:2] and abs(FLAT[vi_][1 - ax_]) > (WX/2 if ax_ == 1 else WY/2) - 1e-6:
                    continue          # 先折的兩邊不含角落(角落被兩折同時牽動,會互相拉扯)
                if sd_ in FOLD_ORDER[2:] and FLOORE is not None and int(vi_) not in FLOORE.get(sd_, []):
                    continue          # 後折的兩邊只留「兩折版實測仍貼地」的那條邊
                keep.append(int(vi_)); SIDEPICK[int(vi_)] = sd_
            else:
                pass
        if a.wrap_edge and keep:
            bnd = np.array(keep)
        else:
            pick = []
            for sd_ in ORD_:
                ax_ = 1 if sd_ in ("yp", "yn") else 0
                sg_ = 1 if sd_ in ("yp", "xp") else -1
                lim_ = (WY/2 if ax_ == 1 else WX/2)*sg_
                cand = bnd[np.abs(FLAT[bnd, ax_] - lim_) < 1e-6]
                pick.append(int(cand[np.argmin(np.abs(FLAT[cand, 1 - ax_]))]))
                SIDEPICK[pick[-1]] = sd_
            bnd = np.array(pick)
    elif a.anchors == 4:
        # 四個邊的**最外側中點**各一個:該邊的極值座標 + 另一軸最接近 0
        pick = []
        for ax, sgn in [(1, +1), (1, -1), (0, +1), (0, -1)]:
            lim = (WY/2 if ax == 1 else WX/2)*sgn
            cand = bnd[np.abs(FLAT[bnd, ax] - lim) < 1e-6]
            pick.append(int(cand[np.argmin(np.abs(FLAT[cand, 1 - ax]))]))
        bnd = np.array(pick)
    UsdGeom.Xform.Define(st, "/World/anchors")
    for kk, vi in enumerate(bnd):
        ap_ = "/World/anchors/a%03d" % kk
        cb = UsdGeom.Cube.Define(st, ap_); cb.CreateSizeAttr(0.006)
        UsdGeom.Xformable(cb).AddTranslateOp().Set(Gf.Vec3d(*[float(x) for x in FOLD[vi]]))
        UsdPhysics.CollisionAPI.Apply(cb.GetPrim())
        UsdPhysics.RigidBodyAPI.Apply(cb.GetPrim()).CreateKinematicEnabledAttr(True)
        UsdGeom.Imageable(cb.GetPrim()).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
        sc = st.DefinePrim("/World/attach/a%03d" % kk, "Scope")
        sc.ApplyAPI("PhysxAutoDeformableAttachmentAPI")
        for k2, v2 in [("enableDeformableVertexAttachments", True),
                       ("enableRigidSurfaceAttachments", False),
                       ("enableCollisionFiltering", True),
                       ("enableDeformableFilteringPairs", False)]:
            sa(sc, "physxAutoDeformableAttachment:" + k2, v2, Sdf.ValueTypeNames.Bool)
        sa(sc, "physxAutoDeformableAttachment:deformableVertexOverlapOffset", 0.008, Sdf.ValueTypeNames.Float)
        sa(sc, "physxAutoDeformableAttachment:collisionFilteringOffset", 0.030, Sdf.ValueTypeNames.Float)
        for rn, tg in [("attachable0", "/World/sheet"), ("attachable1", ap_)]:
            (sc.GetRelationship("physxAutoDeformableAttachment:" + rn) or
             sc.CreateRelationship("physxAutoDeformableAttachment:" + rn)).SetTargets([Sdf.Path(tg)])
        ch = st.DefinePrim("/World/attach/a%03d/vtx_xform_attachment" % kk,
                           "OmniPhysicsVtxXformAttachment")
        sa(ch, "omniphysics:attachmentEnabled", True, Sdf.ValueTypeNames.Bool)
        sa(ch, "omniphysics:damping", 0.0, Sdf.ValueTypeNames.Float)
        sa(ch, "omniphysics:stiffness", float("inf"), Sdf.ValueTypeNames.Float)
        sa(ch, "omniphysics:vtxIndicesSrc0", Vt.IntArray([int(vi)]), Sdf.ValueTypeNames.IntArray)
        sa(ch, "omniphysics:localPositionsSrc1", Vt.Vec3fArray([Gf.Vec3f(0, 0, 0)]),
           Sdf.ValueTypeNames.Point3fArray)
        for rn, tg in [("src0", "/World/sheet"), ("src1", ap_)]:
            (ch.GetRelationship("omniphysics:" + rn) or
             ch.CreateRelationship("omniphysics:" + rn)).SetTargets([Sdf.Path(tg)])
        # 這個點屬於哪一邊(角落歸給座標絕對值較大的那一軸)
        # ★ SIDE2 只有上面 `elif a.stage2:` 那條分支會建。--unbox 走的是更前面的
        #   `if a.unbox:` 分支,不會建 SIDE2 —— 所以同時給 --unbox --stage2 會 NameError。
        #   2026-09-26 踩過一次,補上守衛。
        # ★ 2026-09-30:wrapsim / unbox 挑點時是以「超出折線多少」分邊(角落歸折線較近的那軸),
        #   跟下面 |x|>=|y| 的分法在**角落**會不同邊。以前角落剛好落在後折的 x 邊所以兩者一致;
        #   杯子方位轉正(x 變長邊)+ 折序改 x 先之後,角落會被挑到後折的 y 邊、卻在這裡被改判成 x,
        #   錨點就跟著錯的那一折走。所以挑點時記下的 SIDEPICK 優先。
        if a.stage2 and not a.unbox:
            _side = SIDE2[int(vi)]
        elif int(vi) in SIDEPICK:
            _side = SIDEPICK[int(vi)]
        else:
            _fx, _fy = FLAT[vi][0], FLAT[vi][1]
            if abs(_fx) >= abs(_fy): _side = "xp" if _fx > 0 else "xn"
            else:                    _side = "yp" if _fy > 0 else "yn"
        _axs = 1 if _side in ("yp", "yn") else 0
        PULLS.append(dict(nm="a%03d" % kk, path=ap_, c0=FOLD[vi], c1=FLAT[vi], n=1,
                          side=_side, off=float(FLAT[vi][1 - _axs]), vi=int(vi), c_start=None,
                          infold=(int(vi) in INFOLD)))
    P("★ %s:%s,共 %d 個施力點(每個抓 1 個頂點),其餘完全不施力"
      % ("模擬包起來" if a.wrapsim else "攤開",
         "四個邊的最外側中點" if a.anchors == 4 else "整圈外緣逐點錨", len(PULLS)))
BARS = []
PLATE = None
P6 = None
if a.press6:
    _w, _l, _h = [float(v)/1000.0 for v in a.press6.split(",")]
    _T = 0.010                      # 板厚半值
    _OPEN = 0.42                    # 起始張開到多遠
    P6 = dict(w=_w/2, l=_l/2, h=_h, t=_T, open=_OPEN, plates=[])
    #  (名稱, 軸, 正負) —— bottom 用地面,不另外做
    for nm, ax, sgn in (("top", 2, +1), ("xp", 0, +1), ("xn", 0, -1),
                        ("yp", 1, +1), ("yn", 1, -1)):
        pp = "/World/p6_" + nm
        cb = UsdGeom.Cube.Define(st, pp); cb.CreateSizeAttr(1.0)
        xf = UsdGeom.Xformable(cb)
        tr = xf.AddTranslateOp()
        sc = [0.30, 0.30, 0.30]
        sc[ax] = _T
        xf.AddScaleOp().Set(Gf.Vec3f(*sc))
        UsdPhysics.CollisionAPI.Apply(cb.GetPrim())
        UsdPhysics.RigidBodyAPI.Apply(cb.GetPrim()).CreateKinematicEnabledAttr(True)
        _pc6 = PhysxSchema.PhysxCollisionAPI.Apply(cb.GetPrim())
        _pc6.CreateContactOffsetAttr(0.005); _pc6.CreateRestOffsetAttr(0.001)
        UsdShade.MaterialBindingAPI.Apply(cb.GetPrim()).Bind(MUGM)
        UsdGeom.Imageable(cb.GetPrim()).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
        P6["plates"].append(dict(nm=nm, ax=ax, sgn=sgn, prim_path=pp, tr=tr))
    P("★ 六面壓實:目標 %.0f x %.0f x %.0f mm(底面用地板);五片板從 %.0f mm 外收進來"
      % (_w*1e3, _l*1e3, _h*1e3, _OPEN*1e3))

if a.press > 0:
    # ★ 平板要**剛好等於箱內尺寸**。
    #   240x200 太小 → 布從邊緣 12mm 的縫擠出去,越壓越高(實測 165→189、211→258)。
    #   平板和箱壁都是 kinematic、彼此不互相解算,所以可以做到齊平,布就無處可逃。
    PWX_, PWY_ = ((0.264, 0.224) if a.carton else (max(WX, WY)*0.75,)*2)
    PW_ = PWX_
    _pl = UsdGeom.Cube.Define(st, "/World/press"); _pl.CreateSizeAttr(1.0)
    _xf = UsdGeom.Xformable(_pl)
    PLATE_T = _xf.AddTranslateOp(); _xf.AddScaleOp().Set(Gf.Vec3f(PWX_/2, PWY_/2, 0.010))
    PLATE_T.Set(Gf.Vec3d(0, 0, CDZ + 0.35))
    UsdPhysics.CollisionAPI.Apply(_pl.GetPrim())
    UsdPhysics.RigidBodyAPI.Apply(_pl.GetPrim()).CreateKinematicEnabledAttr(True)
    _pc = PhysxSchema.PhysxCollisionAPI.Apply(_pl.GetPrim())
    _pc.CreateContactOffsetAttr(0.005); _pc.CreateRestOffsetAttr(0.001)
    UsdShade.MaterialBindingAPI.Apply(_pl.GetPrim()).Bind(MUGM)
    PLATE = dict(half=0.010, target=a.press/1000.0)
    P("★ 壓平:剛性平板 %.0f x %.0f mm,壓到 %.0f mm 高(紙箱 carton_ppt 內高 100mm)"
      % (PWX_*1e3, PWY_*1e3, a.press))

def self_pen(SP, TRI):
    """S1 自穿模:布的「邊」穿過布的「面」的次數(排除共用頂點的相鄰對)。
    Moller-Trumbore 線段對三角形,分塊算。
    ★ 使用者問的就是這個:包材跟包材穿模。這是實測,不是推論。"""
    ES = set()
    for t_ in TRI:
        for u_, v_ in ((0, 1), (1, 2), (2, 0)):
            ES.add((min(t_[u_], t_[v_]), max(t_[u_], t_[v_])))
    E = np.array(sorted(ES), int)
    P0, P1 = SP[E[:, 0]], SP[E[:, 1]]
    D = P1 - P0
    V0, V1, V2 = SP[TRI[:, 0]], SP[TRI[:, 1]], SP[TRI[:, 2]]
    E1, E2 = V1 - V0, V2 - V0
    hits = 0
    CH = 128
    for s0 in range(0, len(TRI), CH):
        e1 = E1[s0:s0+CH]; e2 = E2[s0:s0+CH]; v0 = V0[s0:s0+CH]; tr = TRI[s0:s0+CH]
        pv = np.cross(D[:, None, :], e2[None, :, :])
        det = (e1[None, :, :]*pv).sum(-1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0/np.where(ok, det, 1.0), 0.0)
        tv = P0[:, None, :] - v0[None, :, :]
        u = (tv*pv).sum(-1)*inv
        qv = np.cross(tv, np.broadcast_to(e1[None, :, :], tv.shape))
        v = (D[:, None, :]*qv).sum(-1)*inv
        tt = (e2[None, :, :]*qv).sum(-1)*inv
        hit = ok & (u >= 0) & (u <= 1) & (v >= 0) & (u+v <= 1) & (tt > 1e-9) & (tt < 1-1e-9)
        share = ((E[:, None, 0] == tr[None, :, 0]) | (E[:, None, 0] == tr[None, :, 1]) |
                 (E[:, None, 0] == tr[None, :, 2]) | (E[:, None, 1] == tr[None, :, 0]) |
                 (E[:, None, 1] == tr[None, :, 1]) | (E[:, None, 1] == tr[None, :, 2]))
        hits += int((hit & ~share).sum())
    return hits, len(E), len(TRI)


if a.hide_cloth:
    UsdGeom.Imageable(sp).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    P("★ 渲染診斷:布已隱藏")

cam = Camera(prim_path="/World/cam", resolution=(1280, 720), frequency=FPS)
cam.set_focal_length(4.0)
# ★ 2026-09-25:照度砍 3.7 倍後杯子亮度幾乎沒變(186→188)⇒ 主要光源不是我加的。
#   列出所有燈才發現真凶:add_default_ground_plane() 自己帶一盞
#   /World/defaultGroundPlane/SphereLight,**intensity = 100000**,
#   我加的 245/135/405 在它面前完全不算數。真正的曝光旋鈕是這一盞。
_gl = st.GetPrimAtPath("/World/defaultGroundPlane/SphereLight")
if _gl.IsValid():
    _ga = _gl.GetAttribute("inputs:intensity")
    if _ga and _ga.IsValid():
        if a.light_probe:
            _ga.Set(0.0)
            P("  ★ 渲染診斷:預設地板燈關掉(0),改由 dome 全方向照")
        else:
            # ★ 2026-09-26:這盞是點光源,打出的硬陰影把近黑的布投在箱壁上,看起來像箱子透明。
            #   證據:light_probe(只用 dome)那張,箱壁是白的、完全沒有黑塊。
            #   所以降這盞、拉高 dome,陰影才會散開。
            _ga.Set(_ga.Get()/12.0)
            P("  ★ 預設地板燈 100000 → %.0f(點光源硬陰影會把黑布投到箱壁上)" % _ga.Get())
for _lp in st.Traverse():
    _tn = str(_lp.GetTypeName())
    if "Light" in _tn:
        _i = _lp.GetAttribute("inputs:intensity")
        P("  [light] %-34s %-16s intensity=%s" % (_lp.GetPath(), _tn,
          _i.Get() if _i and _i.IsValid() else "-"))
if LIDS and LID_REST_CLOSED and a.close_lid and not a.unbox and MOVE is None:
    # ★ 2026-10-02 修:定版紙箱 USD 預設 = **關**。舊版物理在 world.reset() 時蓋子還是關的,
    #   第一格 drive(0) 才把它甩到 180°(開)—— 那一下蓋子已經壓進布裡(out_bl_boxmeta:
    #   t=0 布從 216x195x163 被壓成 272x195x117,之後整段都停在 115~117)。
    #   改成 reset 之前就把蓋子的 USD 姿態擺到「開」(= drive 的起點 180°),物理從開蓋起步。
    for L in LIDS:
        _pr = st.GetPrimAtPath("/World/Box/" + L["nm"])
        _h = Gf.Vec3d(*[float(x) for x in L["h"]])
        _M = (Gf.Matrix4d().SetTranslate(-_h)
              * Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(*[float(x) for x in L["ax"]]), 180.0*L["sgn"]))
              * Gf.Matrix4d().SetTranslate(_h))
        _Wm = L["T0"] * _M
        _par = UsdGeom.Xformable(_pr.GetParent()).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        _xf = UsdGeom.Xformable(_pr); _xf.ClearXformOpOrder()
        _xf.AddTransformOp().Set(_Wm * _par.GetInverse())
    P("★ 蓋子 USD 預設 = 關 ⇒ reset 前先擺到 180°(開),物理從開蓋起步;drive 再 180°→0° 關上")
world.reset(); cam.initialize()
_TRI0 = np.array(tris, int)
_p0 = self_pen(np.array(UsdGeom.Mesh(sp).GetPointsAttr().Get()), _TRI0)[0]
P("S0 **出生時**(%s、物理還沒跑)布自穿模 %d 次"
  % ("布是攤平的" if not a.fold_init else "解析折疊圖剛擺好", _p0))
P("   ← 若 > 0,代表穿模是我「擺」出來的,不是模擬造成的" )
for p_ in PULLS:
    p_["prim"] = SingleXFormPrim(p_["path"], name="anc_" + p_["nm"])
if PLATE is not None:
    PLATE["prim"] = SingleXFormPrim("/World/press", name="pressplate")
if P6 is not None:
    for q in P6["plates"]:
        q["prim"] = SingleXFormPrim(q["prim_path"], name="p6_" + q["nm"])
for L in LIDS:
    L["prim"] = SingleXFormPrim("/World/Box/" + L["nm"], name="lid_" + L["nm"])
mugx = SingleXFormPrim("/World/mug", name="mugx")
MOVEB = None
if MOVE is not None:
    assert a.carton and LIDS, "--movebox 需要 --carton(且讀得到 meta、建得出四片蓋)"
    # 箱體(base 含四面牆)+ 四片蓋,全部 kinematic,每個物理步設成「原位 + 向量 × smoothstep」。
    # 蓋子用 USD 預設姿態 = 關(上面自檢印過),不轉。
    MOVEB = []
    for _pth in ["/World/Box/base"] + ["/World/Box/" + L["nm"] for L in LIDS]:
        _x = SingleXFormPrim(_pth, name="mv_" + _pth.split("/")[-1])
        _p, _q = _x.get_world_pose()
        MOVEB.append(dict(x=_x, p0=np.array(_p, float), q0=np.array(_q, float)))
    _rb = (UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
           .ComputeWorldBound(st.GetPrimAtPath("/World/Box")).ComputeAlignedRange())
    BOXC0 = np.array([(_rb.GetMin()[0] + _rb.GetMax()[0])/2.0, (_rb.GetMin()[1] + _rb.GetMax()[1])/2.0, CDZ])
    P("★ 搬箱:向量 (%.0f, %.0f, %.0f) mm;靜置 %.1fs → 搬 %.1fs(smoothstep)→ 靜置 %.1fs;"
      "箱體+%d 片蓋 kinematic、蓋子維持關;杯子動態(不 kinematic)"
      % (*(MOVE*1e3), a.move_wait, a.move_t, a.settle, len(LIDS)))
    P("   箱底中心(箱底內面)起點 (%.1f, %.1f, %.1f) mm" % tuple(BOXC0*1e3))
    BOXZHI0 = float(_rb.GetMax()[2])
    MVIEW = None
    if a.move_mode == "ktarget":
        # PhysX kinematic target:PhysX 由「這步目標 − 上步位置」推出 kinematic 速度,
        # 接觸/摩擦看得到箱底在動。xform 模式改的是 USD,可能被當成瞬移(速度 0)。
        MVIEW = world.physics_sim_view.create_rigid_body_view(
            ["/World/Box/base"] + ["/World/Box/" + L["nm"] for L in LIDS])
        MV_T0 = np.array(MVIEW.get_transforms(), float).copy()     # (n,7) x y z qx qy qz qw
        MV_IDX = np.arange(MVIEW.count, dtype=np.int32)
        P("   移動方式 ktarget:rigid body view %d 個(base + 蓋);起點 base %s mm"
          % (MVIEW.count, np.round(MV_T0[0, :3]*1e3, 1)))
    else:
        P("   移動方式 xform:每步 SingleXFormPrim.set_world_pose(改 USD)")

def box_off():
    """箱子目前相對起點的位移(m)。ktarget 模式從 PhysX 讀,xform 模式從 USD 讀。"""
    if MVIEW is not None:
        return np.array(MVIEW.get_transforms(), float)[0, :3] - MV_T0[0, :3]
    return np.array(MOVEB[0]["x"].get_world_pose()[0], float) - MOVEB[0]["p0"]

def move_box(tt):
    s_ = ss((tt - a.move_wait)/a.move_t)
    if MVIEW is not None:
        _d = MV_T0.copy(); _d[:, :3] += MOVE*s_
        MVIEW.set_kinematic_targets(_d.astype(np.float32), MV_IDX)
        return s_
    _t_open = a.move_wait + a.move_t + a.settle
    for _i, b_ in enumerate(MOVEB):
        if a.move_open and _i > 0 and tt >= _t_open:
            # ★ 搬完後原地開蓋:上蓋(order 大的)先開、下蓋後開;0=關 → 180=開
            L_ = LIDS[_i - 1]
            _k = (max(l2["order"] for l2 in LIDS) - L_["order"])
            _u = ss((tt - _t_open - _k*a.lid_span)/a.lid_span)
            _p, _o = lid_pose(L_, 180.0*_u)
            b_["x"].set_world_pose(position=_p + MOVE*s_, orientation=_o)
            continue
        b_["x"].set_world_pose(position=b_["p0"] + MOVE*s_, orientation=b_["q0"])
    return s_

if a.carton:
    # ★ 高俯角,否則只看到箱子側面、箱內是背光面(全黑)。見 memory: render-black-headlight-fix
    # ★ 2026-09-26:--unbox 的最後要把布攤在箱子旁邊的地上(flat_x),相機得拉遠、
    #   瞄準點往落點方向偏,才能讓「箱子 + 攤開的布」同框。
    _R = 0.64 if (a.unbox or MOVE is not None) else 0.46
    _tx = a.flat_x*0.40 if a.unbox else 0.0
    EYE = [_R*1.55 + _tx, -_R*1.70, CDZ + _R*2.05]; TGT = [_tx, 0, CDZ + 0.030]
    if MOVE is not None:      # 瞄準搬運路徑的中點,起點終點都同框
        EYE = list(np.array(EYE) + MOVE/2.0); TGT = list(np.array(TGT) + MOVE/2.0)
else:
    _cr = a.cam_ref if a.cam_ref > 0 else max(WX, WY)    # --cam_ref:相機距離基準(0 = 舊行為 max(WX,WY))
    EYE = [_cr*1.5, -_cr*1.6, PLAT_Z + _cr*0.9]; TGT = [0, 0, PLAT_Z*0.75]
G.look(cam, EYE, TGT)
# ★ 使用者 2026-09-25:「顏色也不對」。杯子指定的是藍灰 (144,163,189) 卻渲成白的 —— 
#   headlight 2000/1200 對 dome 500 太強,淡色被打爆(這支腳本自己的註解就寫過)。
#   改成主光降一半、環境光拉高,顏色才出得來。
# ★ 照度校正(2026-09-25 由像素實測定出來的 3.7 倍過曝):整體除以 3.7
G.add_headlight(st, EYE, TGT, intensity=(135.0 if a.checker else 245.0), name="hl1")
G.add_headlight(st, [-.5, -.5, .8], TGT, intensity=(80.0 if a.checker else 135.0), name="hl2")
UsdLux.DomeLight.Define(st, "/World/dome").CreateIntensityAttr(100000.0 if a.light_probe else 2600.0)
if a.carton:
    # ★ 箱內是凹的,側面打光照不進去(第一版整個箱內全黑)。
    #   SphereLight 在 0.55m 外也不夠亮 —— 改用**垂直向下的 DistantLight**,
    #   平行光不受距離衰減影響,一定照得到箱底。
    _dl = UsdLux.DistantLight.Define(st, "/World/toplight")
    UsdGeom.Xformable(_dl).AddRotateXYZOp().Set(Gf.Vec3f(-70.0, 0.0, 25.0))
    _dl.CreateIntensityAttr(3500.0); _dl.CreateAngleAttr(2.0)
    _dl2 = UsdLux.DistantLight.Define(st, "/World/toplight2")
    UsdGeom.Xformable(_dl2).AddRotateXYZOp().Set(Gf.Vec3f(-90.0, 0.0, 0.0))
    _dl2.CreateIntensityAttr(2200.0); _dl2.CreateAngleAttr(4.0)

T_SET, T_SW, T_HOLD, T_OFF = 1.5, 3.0, 0.8, 1.2
WORDER = (STAGE2_SIDES if a.stage2                      # 第二段只折後兩折(= FOLD_ORDER[2:]);以前寫死 ["xp","xn"] 是因為那時後兩折是 x
          else FOLD_ORDER[:max(1, min(4, a.wrap_n))])
# ★ 修:加 stage2 的時候把 T_END 從 wrap_n 改成 len(WORDER),但 WORDER 一直是 4 個,
#   於是 --wrap_n 2 還是跑四個階段(後兩個沒有錨點、什麼都不做),白燒 6.5 秒模擬。
SPAN_W = 3.5                                   # 每一邊折上去用幾秒
T_DOWN = a.press_down
T_LID = 8.0 if a.close_lid else 0.0
T_UNW = 8.0
T_END = (a.move_wait + a.move_t + a.settle + ((2*a.lid_span + 3.0) if a.move_open else 0.0)) if MOVE is not None else \
        (a.lift_wait + a.lift_t + a.settle) if a.lift_mug > 0 else \
        (T_SET + 2*a.lid_span + T_UNW + a.flat_t + a.settle) if a.unbox else \
        (T_SET + T_DOWN + a.press_hold + a.press_off + T_LID + a.settle) if (a.carton and a.press > 0) else \
        (T_SET + 8.0 + a.settle) if (a.carton and a.close_lid) else \
        (T_SET + a.settle) if a.carton else \
        (T_SET + T_DOWN + a.press_hold + a.press_off) if a.press > 0 else \
        (T_SET + len(WORDER)*SPAN_W + a.settle) if (a.wrapsim or a.stage2) else (T_SET + 2*(T_SW + T_HOLD + T_OFF) + a.settle)
T_FREE = T_SET + 2*(T_SW + T_HOLD + T_OFF) + 0.5
ss = lambda u: (lambda v: v*v*(3-2*v))(min(max(u, 0.), 1.))


NACT = {}
RELEASED = {}      # 每一邊已放掉幾個錨點(--release_after)


def wrap_arc_from(side, u, cur, lay=0):
    """★ 使用者 2026-09-25:「施力的『邊』只剩一點」。
    實測 wrap2 跑完,+x 那條邊 35 個點只剩 18 個(51%)還貼地,而且已經不是直線
    (y 被拉到 -73~+57),另一半被前兩折帶到 96mm 高。
    所以後兩折**不能再用攤平座標當起點** —— 每個錨點從它**當下的實際位置**起弧:
      繞底部折線把它轉到正上方 → 再繞杯頂折線蓋過去。
    半徑取該點當下到折線的距離,所以一樣不拉伸布。"""
    ax = 0 if side in ("xp", "xn") else 1
    sgn = 1.0 if side in ("xp", "yp") else -1.0
    C = CX if ax == 0 else CY
    Hm = ME[2]
    a0 = sgn*cur[ax] - C                  # 當下離折線多遠(沿折疊方向)
    z0 = cur[2] - PLAT_Z
    R = float(np.hypot(max(a0, 1e-6), z0)) # 當下半徑 = 折邊剩下的長度
    th0 = float(np.arctan2(z0, max(a0, 1e-6)))
    if u <= 0.5:
        th = th0 + (np.pi/2 - th0)*(u/0.5)
        along = C + R*np.cos(th); z = PLAT_Z + R*np.sin(th)
    else:
        # ★ 使用者 2026-09-25:「折完的錨點需要有,只要存在在杯子上方就好」。
        #   所以第二段的終點直接訂在**杯子中心線正上方**(along = 0),高度 = 杯頂 + 疊層,
        #   不再用 arm = R - Hm 去算(那個會讓折邊只到杯子側邊,壓不到上面)。
        #   從「立直」旋到那個點:角度與半徑同時內插 ⇒ 半徑全程 <= R,布不會被拉長。
        H0 = np.array([0.0, R - Hm])                     # 立直時,相對杯頂折線的向量
        # ★ z 分層:第 lay 折的終點比第 0 折高 lay*layer_mm。
        #   xy 照樣重疊(使用者說可以),只把 z 分開 —— 這樣第二片是**疊在**第一片上面,
        #   而不是被拉到第一片的內部。
        HE = np.array([-C - a.tip_over_mm/1000.0, LZ_HOLD + lay*a.layer_mm/1000.0])   # 終點:杯子正上方(可越過中線),第 lay 層
        w = (u - 0.5)/0.5
        a0_ = np.arctan2(H0[0], H0[1]); aE_ = np.arctan2(HE[0], HE[1])
        r0_ = np.linalg.norm(H0); rE_ = np.linalg.norm(HE)
        an = a0_ + (aE_ - a0_)*w; rr = r0_ + (rE_ - r0_)*w
        along = C + rr*np.sin(an); z = PLAT_Z + Hm + rr*np.cos(an)
    p = np.zeros(3); p[ax] = sgn*along; p[1 - ax] = cur[1 - ax]; p[2] = z
    return p


def wrap_arc(side, u, off=0.0):
    """兩段等距旋轉,完全不拉伸布(半徑固定 = 折邊長,所以錨點走圓弧):
       A 段 繞**底部折線**轉 90°   → 折邊從平鋪立起來,貼著杯側
       B 段 繞**杯頂那條折線**轉 90° → 折邊蓋過杯頂
    使用者最早就講過「因為向上拉,所以軌跡會變成一個圓弧形,而不是直直向上」。"""
    ax = 0 if side in ("xp", "xn") else 1
    sgn = 1.0 if side in ("xp", "yp") else -1.0
    C = CX if ax == 0 else CY
    R = (WX/2 if ax == 0 else WY/2) - C          # 折邊長
    Hm = ME[2]
    if u <= 0.5:
        th = np.radians(90.0*(u/0.5))
        along = C + R*np.cos(th); z = PLAT_Z + R*np.sin(th)
    else:
        th = np.radians(90.0*((u-0.5)/0.5))
        arm = max(0.0, R - Hm)
        along = C - arm*np.sin(th); z = PLAT_Z + Hm + arm*np.cos(th)
    p = np.zeros(3); p[ax] = sgn*along; p[1 - ax] = off; p[2] = z
    return p

def lid_pose(L, deg):
    """繞鉸鏈轉 deg 度,0 = USD 生成時的姿態。
    ★ 2026-10-02 訂正舊註解(原寫「0=平躺全開,180=向內蓋住」,是舊紙箱的慣例):
      定版紙箱 USD 預設 = **關**,所以 0=關、180=開;正角度先把蓋子抬到正上方(90°)再翻出去。
      方向不再信註解:建 LIDS 時用 USD 量 ±90° 的蓋中心 z,L["sgn"] 讓「正角度 = 往上開」恆成立
      (定版紙箱四片量到都是 +,sgn=1,行為與舊版相同)。"""
    h = Gf.Vec3d(*[float(x) for x in L["h"]])
    M = (Gf.Matrix4d().SetTranslate(-h)
         * Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(*[float(x) for x in L["ax"]]),
                                               float(deg)*L.get("sgn", 1.0)))
         * Gf.Matrix4d().SetTranslate(h))
    W = L["T0"] * M
    q = W.ExtractRotationQuat()
    return (np.array([float(x) for x in W.ExtractTranslation()]),
            np.array([float(q.GetReal()), *[float(x) for x in q.GetImaginary()]]))


def drive(t):
    if MOVE is not None:
        move_box(t)
        return
    if a.lift_mug > 0:
        u = ss(max(0.0, t - a.lift_wait)/a.lift_t)
        mugx.set_world_pose(position=MUGP0 + np.array([0.0, 0.0, a.lift_mug*u]),
                            orientation=MUGQ0)
        return
    if a.unbox:
        # 上層 fy 先開、下層 fx 後開(關蓋的反序);角度 0(關)→ 180(開)
        SPANL = a.lid_span
        for L in LIDS:
            k_ = 0 if L["nm"] in ("fyp", "fyn") else 1      # fy 先
            u = ss((t - T_SET - k_*SPANL)/SPANL)
            p_, o_ = lid_pose(L, 180.0*u)
            L["prim"].set_world_pose(position=p_, orientation=o_)
        # ★ 蓋子全開之後,把包材**逆著當初折的順序**打開:
        #   折序是 FOLD_ORDER(xp → xn → yp → yn),開序 UORDER 是它的反序(yn → yp → xn → xp),定義在檔頭。
        #   每一組都用它當初的那批錨點(後折的邊只有貼地那段、先折的邊是整條),不是整圈一起。
        t0 = T_SET + 2*SPANL
        span = T_UNW/len(UORDER)
        tF = t0 + T_UNW                       # 完整攤平開始
        for p_ in PULLS:
            sd = p_["side"]
            k_ = UORDER.index(sd) if sd in UORDER else 0
            c0 = p_["c0"]
            ax = 0 if sd in ("xp", "xn") else 1
            sg = 1.0 if sd in ("xp", "yp") else -1.0
            mid = c0.copy()
            if p_["infold"]:
                mid[ax] = c0[ax] + sg*a.unbox_out
                mid[2] = c0[2] + a.unbox_up
            if t < tF:
                # 逆向打開:只有當初折疊用的錨點動
                uw = ss((t - t0 - k_*span)/span) if p_["infold"] else 0.0
                pos = c0 + (mid - c0)*uw
            else:
                # ★ 完整攤平:把包材拿出箱子、攤在**地板上**。
                #   2026-09-26:上一版把外緣拉到 z=0.22 的攤平座標,但布的內部還留在箱底,
                #   外緣被釘在零鬆弛的 586×586 上、內部要垂 200mm → 只能靠拉長布來達成
                #   (實測邊長中位 1.117、z 跨 226mm)。懸空水平薄片只釘外緣,重力必然拉伸。
                #   改成攤在地上:內部由地板支撐,就不需要拉伸。
                uf = ss((t - tF)/a.flat_t)
                flz = p_["c1"][2] + THICK/2.0                     # 貼地
                fl = np.array([p_["c1"][0] + a.flat_x, p_["c1"][1], flz])
                pos = mid + (fl - mid)*uf
                # 拱形路徑:中途抬到 a.flat_z,讓吊在下面的布袋底越過打開的紙蓋
                pos[2] += 4.0*uf*(1.0 - uf)*max(0.0, a.flat_z - 0.5*(mid[2] + flz))
            p_["prim"].set_world_pose(position=pos, orientation=np.array([1., 0, 0, 0]))
        return
    if P6 is not None:
        # 五片板(四側 + 頂)從 open 收到目標;底面用地板。
        tgt = {"top": P6["h"] + P6["t"], "xp": P6["w"] + P6["t"], "xn": P6["w"] + P6["t"],
               "yp": P6["l"] + P6["t"], "yn": P6["l"] + P6["t"]}
        if t < T_SET:                              u = 0.0
        elif t < T_SET + T_DOWN:                   u = ss((t - T_SET)/T_DOWN)
        elif t < T_SET + T_DOWN + a.press_hold:    u = 1.0
        else:                                      u = 0.0      # 放開,量回彈
        for q in P6["plates"]:
            d = P6["open"] + (tgt[q["nm"]] - P6["open"])*u
            pos = [0.0, 0.0, 0.0]
            pos[q["ax"]] = q["sgn"]*d
            if q["nm"] != "top": pos[2] = P6["h"]/2
            q["prim"].set_world_pose(position=np.array(pos), orientation=np.array([1., 0, 0, 0]))
        return
    if a.carton and a.close_lid:
        SPANL = a.lid_span
        for L in LIDS:
            t0 = T_SET + L["order"]*SPANL
            u = ss((t - t0)/SPANL)
            if a.lid_dynamic:
                L["target"] = float(np.radians(180.0*(1.0 - u)))
                continue
            p, o = lid_pose(L, 180.0*(1.0 - u))      # 180=開 → 0=關
            L["prim"].set_world_pose(position=p, orientation=o)
        return
    if a.carton and a.press <= 0: return
    if a.press > 0:
        z0, z1 = CDZ + 0.35, CDZ + PLATE["target"] + PLATE["half"]
        T_OFF0 = T_SET + T_DOWN + a.press_hold          # 平板抬走的時刻
        if t < T_SET:                       z = z0
        elif t < T_SET + T_DOWN:            z = z0 + (z1 - z0)*ss((t - T_SET)/T_DOWN)
        elif t < T_OFF0:                    z = z1
        else:                               z = z0      # 抬走,看回彈
        PLATE["prim"].set_world_pose(position=np.array([0., 0., z]),
                                     orientation=np.array([1., 0, 0, 0]))
        # ★ 壓完之後接著關蓋 —— 這是使用者要的完整序列:入箱 → 壓平 → 蓋上
        if a.close_lid and LIDS:
            SPANL = 4.0
            t_lid = T_SET + T_DOWN + a.press_hold + a.press_off
            for L in LIDS:
                u = ss((t - t_lid - L["order"]*SPANL)/SPANL)
                p, o = lid_pose(L, 180.0*(1.0 - u))   # 180=開 → 0=關
                L["prim"].set_world_pose(position=p, orientation=o)
        return
    if a.wrapsim or a.stage2:
        # ★ 一次只折一邊;前一邊折好就留在原地,下一邊蓋上去 —— 疊層是物理疊出來的
        SPTS = np.array(UsdGeom.Mesh(sp).GetPointsAttr().Get())
        for p_ in PULLS:
            if p_["side"] == "hold":
                # 停在杯子正上方,全程壓著不動 —— 這是唯一還在施力的「前兩折殘留」
                p_["prim"].set_world_pose(position=p_["c0"], orientation=np.array([1., 0, 0, 0]))
                continue
            k_ = WORDER.index(p_["side"])
            t0 = T_SET + k_*SPAN_W
            cur = SPTS[p_["vi"]]
            if t < t0:
                # 還沒輪到:錨點貼著布自己的頂點走 ⇒ 約束力 ~ 0,不干擾前面的折。
                # ★ 這裡**不要**做一階外推。2026-09-25 試過 pos = cur + (cur-prev),
                #   結果是正回饋:錨點超前 → 把頂點拉更遠 → 下一格差更大,
                #   布被甩到 463mm 高、bbox 670mm(比布本身 586mm 還大)。直接跟就好。
                p_["prim"].set_world_pose(position=cur, orientation=np.array([1., 0, 0, 0]))
                continue
            if p_["c_start"] is None:
                # 輪到的那一刻:記下實際位置,並決定這個錨點要不要真的施力。
                # ★ 後兩折只驅動**還貼在地板上**的那條邊;已經被前兩折帶上去的,
                #   繼續跟著布走(施力 ~ 0),不去硬拽壓在下面的布。先折的兩邊(FOLD_ORDER[:2])一律施力。
                p_["c_start"] = cur.copy()
                p_["act"] = True if (a.stage2 or FLOORE is not None or p_["side"] in FOLD_ORDER[:2]) else (cur[2] < Z_FLOOR)
                NACT[p_["side"]] = NACT.get(p_["side"], 0) + int(p_["act"])
                if p_["side"] in ("xp", "xn") and NACT.get(p_["side"] + "_n", 0) == 0:
                    pass
            if not p_["act"]:
                p_["prim"].set_world_pose(position=cur, orientation=np.array([1., 0, 0, 0]))
                continue
            u = ss((t - t0)/(SPAN_W*0.85))
            if a.release_after >= 0 and t >= t0 + SPAN_W*0.85 + a.release_after:
                # ★ 放手:刪掉 attachment Scope(連子 prim),方塊收到地下免得變成布的碰撞體。
                #   probe_detach.py mode 1 實測:當步生效、其他錨點不受影響、布不重 cook。
                if not p_.get("released"):
                    st.RemovePrim(Sdf.Path("/World/attach/" + p_["nm"]))
                    # ★ 2026-09-30 t_c1 實測:方塊若改成「收到 z=-5」,33 顆 kinematic 方塊一步掃過
                    #   底下鋪在地板上的布,speculative contact 把整排頂點踢飛(bbox z 衝到 2343mm)。
                    #   所以方塊也直接刪掉,不搬。
                    st.RemovePrim(Sdf.Path(p_["path"]))
                    p_["released"] = True
                    _n = RELEASED.get(p_["side"], 0) + 1; RELEASED[p_["side"]] = _n
                    if _n == 1: P("  [t=%.2f] %s 這一折拉到位,開始放掉錨點" % (t, p_["side"]))
                continue
            p_["prim"].set_world_pose(position=wrap_arc_from(p_["side"], u, p_["c_start"],
                                                             lay=(2 if a.stage2 else 0) + WORDER.index(p_["side"])),
                                      orientation=np.array([1., 0, 0, 0]))
        return
    if a.unfold:
        # ★ 一次只攤開一邊(使用者 2026-09-24)。攤開 = 打開,順序照 PPT 前後先、左右後 = 折序的反序 UORDER
        #   (舊字面值 ["yp","yn","xp","xn"] 的軸序 y→x 跟 UORDER 相同,只是同一軸內正負對調)
        ORDER = UORDER
        span = max(0.1, (T_END - T_SET - 3.0) / len(ORDER))
        for p_ in PULLS:
            k_ = ORDER.index(p_["side"])
            u = ss((t - T_SET - k_*span)/span)
            p_["prim"].set_world_pose(position=p_["c0"] + (p_["c1"] - p_["c0"])*u,
                                      orientation=np.array([1., 0, 0, 0]))
        return
    if a.no_push or a.fold_init: return
    for b in BARS:
        t0 = T_SET + b["phase"]*(T_SW + T_HOLD + T_OFF)
        if t < t0: u = 0.0
        elif t < t0 + T_SW: u = ss((t-t0)/T_SW)
        elif t < t0 + T_SW + T_HOLD: u = 1.0
        else:
            if not b["gone"]:
                for s_ in b["segs"]:
                    s_["prim"].set_world_pose(position=np.array([s_["off"], 0., -5.]),
                                              orientation=np.array([1., 0, 0, 0]))
                b["gone"] = True; P("  [t=%.2f] 收掉 %s 掃桿" % (t, b["nm"]))
            continue
        # 從 -90°(折邊垂下)掃到 +sweep°(蓋過杯頂)。半徑固定 = 折邊長 ⇒ 布不被拉伸
        th = np.radians(-90.0 + (a.sweep + 90.0) * u)
        r = b["flap"] * 0.92
        along = b["crease"] + r*np.cos(th); z = PLAT_Z + r*np.sin(th)
        for s_ in b["segs"]:
            p = (np.array([s_["off"], b["sgn"]*along, z]) if b["axis"] == 0
                 else np.array([b["sgn"]*along, s_["off"], z]))
            s_["prim"].set_world_pose(position=p, orientation=np.array([1., 0, 0, 0]))

CREASE = None
if a.lid_dynamic and LIDS:
    import torch
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from crease_physics import ElastoplasticCrease
    from isaacsim.core.prims import RigidPrim
    LIDVIEW = RigidPrim(prim_paths_expr="/World/Box/f[xy][pn]", name="lidview")
    try: LIDVIEW.initialize()
    except Exception as e: P("  lidview.initialize: %s" % str(e)[:60])
    CREASE = ElastoplasticCrease(len(LIDS), "cpu", k=3.2, my0=0.60, h=0.85, c=0.33, clip=3.0)
    CREASE.reset(torch.arange(len(LIDS)), torch.zeros(len(LIDS)))
    for L in LIDS:
        L["q0"] = None
    P("  ★ 摺痕模型:k=3.2 my0=0.60 H=0.85 c=0.33 clip=3.0(定版係數)")

if a.lid_dynamic and LIDS:
    # 動態蓋子的初始姿態是生成器的「關上」,布會一開始就被夾住。
    # 先把它們擺到 180°(開),drive 再把它們關回來。
    for L in LIDS:
        p_, o_ = lid_pose(L, 180.0)
        L["prim"].set_world_pose(position=p_, orientation=o_)
    P("  ★ 蓋子初始擺到 180°(開),再由 drive 關回 0°")

try: FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 17)
except Exception: FONT = ImageFont.load_default()
L1 = ("sheet %.0fx%.0f res %d | mug %.0fx%.0fx%.0f | placeholder %.0fx%.0fx%.0f | flap y%.0f x%.0f"
      % (WX*1e3, WY*1e3, a.res, *(ME*1e3), A*1e3, B*1e3, HC*1e3, FLAPY*1e3, FLAPX*1e3))
L2 = ("init=%s | E=%.0e bend=%.0e solver=%d | thick=%.0f cont=%.1f rest=%.2f layer=%.0f hold=%.0f tip=%.0f anchor=%s rel=%s | fold=%s"
      % ("FOLDED" if a.fold_init else "flat", YOUNGS, BEND, a.solver, THICK*1e3, CONT*1e3, REST*1e3, a.layer_mm,
         a.hold_mm, a.tip_over_mm, "none" if a.no_anchor else "on",
         ("%.1fs" % a.release_after) if a.release_after >= 0 else "no", "off" if a.no_push else "on"))
if MOVE is not None:
    L2 = "move=%g,%g,%g | " % tuple(MOVE) + L2      # 放最前面:L2 太長,接在尾巴會被裁掉(mb_x30 實測)

def stamp(rgb, t, ph_):
    im = Image.fromarray(rgb[:, :, :3]); d = ImageDraw.Draw(im); W, Hh = im.size
    d.rectangle([0, Hh-58, W, Hh], fill=(16, 16, 18))
    d.text((10, Hh-54), L1, fill=(235,)*3, font=FONT)
    d.text((10, Hh-30), L2, fill=(170, 200, 230), font=FONT)
    d.text((W-260, 10), "t=%.2fs  %s" % (t, ph_), fill=(255,)*3, font=FONT)
    return np.array(im)

kin = st.GetPrimAtPath("/World/mug").GetAttribute("physics:kinematicEnabled")
S = {"froze": False, "free": False, "phgone": False}
PRESS_H = {}
MUGP0 = MUGQ0 = LIFT0 = None
if a.lift_mug > 0:
    _p0, _q0 = mugx.get_world_pose()
    MUGP0, MUGQ0 = np.array(_p0, float), np.array(_q0, float)
    P("★ 提杯測試:靜置 %.1fs 後,把杯子從 z=%.1fmm 垂直提到 %.1fmm(%.1fs)。"
      "布不建任何錨點,完全靠包覆撐住;布摩擦 %.2f"
      % (a.lift_wait, MUGP0[2]*1e3, (MUGP0[2]+a.lift_mug)*1e3, a.lift_t, FRIC))
    _SH0 = np.array(UsdGeom.Mesh(sp).GetPointsAttr().Get())
    LIFT0 = dict(mug=MUGP0.copy(), sc=_SH0.mean(0).copy(), smin=float(_SH0[:,2].min()))
PENLOG = []          # (t, phase, 自穿模次數)
TRAJ_T, TRAJ_PH, TRAJ_S, TRAJ_M = [], [], [], []   # 軌跡:時間 / 階段 / 布頂點 / 杯子姿態(pos+quat)
frames = []
if MOVE is not None:
    S["froze"] = S["free"] = True        # 杯子全程動態,不走「T_SET 固定」那套
MVLOG = []           # (t, 箱底中心, 布質心, 杯心)
def lid_cz():
    """四片蓋中心目前的 z(mm),用 USD 姿態(kinematic 蓋 = 物理姿態)。"""
    return [UsdGeom.Xformable(st.GetPrimAtPath("/World/Box/" + L["nm"]))
            .ComputeLocalToWorldTransform(Usd.TimeCode.Default()).Transform(L["c_loc"])[2]*1e3
            for L in LIDS]
for k in range(int(T_END*FPS)):
    t = k/FPS
    if LIDS and (a.close_lid or MOVE is not None) and k % FPS == 0:
        P("  [lid] t=%5.2f 蓋中心 z %s mm(鉸鏈 下 %.1f / 上 %.1f)"
          % (t, " ".join("%s=%.1f" % (L["nm"], z) for L, z in zip(LIDS, lid_cz())),
             CBOX["hz_lo"]*1e3, CBOX["hz_up"]*1e3))
    if MOVE is not None and k % (FPS//2) == 0:
        _S = np.array(UsdGeom.Mesh(sp).GetPointsAttr().Get()); _mp = np.array(mugx.get_world_pose()[0], float)
        _bc = BOXC0 + box_off()
        _sc = _S.mean(0)
        MVLOG.append((t, _bc, _sc, _mp))
        _gap = _S[:, 2] - _bc[2]          # 布頂點離箱底內面的高度
        P("  [move] t=%5.2f 箱底中心 (%6.1f,%6.1f,%6.1f) 布質心 (%6.1f,%6.1f,%6.1f) 杯心 (%6.1f,%6.1f,%6.1f)"
          " | 布−箱 xy (%+6.1f,%+6.1f) 杯−箱 xy (%+6.1f,%+6.1f) mm"
          " | 底接觸:布最低−箱底內面 %+.1f mm,離底 <%.0fmm 的頂點 %d"
          % (t, *(_bc*1e3), *(_sc*1e3), *(_mp*1e3), *((_sc - _bc)[:2]*1e3), *((_mp - _bc)[:2]*1e3),
             _gap.min()*1e3, CONT*1e3, int((_gap < CONT).sum())))
    if (not S["froze"]) and t >= T_SET:
        kin.Set(True); S["froze"] = True; P("  [t=%.2f] 杯子固定%s" % (t, "(全程)" if a.hold_mug else "(折疊期間)"))
    if (not S["free"]) and t >= T_FREE and not a.hold_mug:
        kin.Set(False); S["free"] = True; P("  [t=%.2f] 放開杯子,自然落到布上" % t)
    drive(t)
    for _ in range(4):
        if CREASE is not None:
            import torch
            _p, _q = LIDVIEW.get_world_poses()
            _w = LIDVIEW.get_angular_velocities()
            _tau = np.zeros((len(LIDS), 3))
            _qs, _qds = [], []
            for _i, L in enumerate(LIDS):
                ax = L["ax"]/np.linalg.norm(L["ax"])
                qq = np.array(_q[_i])                       # (w,x,y,z)
                if L["q0"] is None: L["q0"] = qq.copy()
                q0 = L["q0"]
                # 相對旋轉 = q * conj(q0);取繞 ax 的角度
                c0 = np.array([q0[0], -q0[1], -q0[2], -q0[3]])
                r = np.array([qq[0]*c0[0]-qq[1]*c0[1]-qq[2]*c0[2]-qq[3]*c0[3],
                              qq[0]*c0[1]+qq[1]*c0[0]+qq[2]*c0[3]-qq[3]*c0[2],
                              qq[0]*c0[2]-qq[1]*c0[3]+qq[2]*c0[0]+qq[3]*c0[1],
                              qq[0]*c0[3]+qq[1]*c0[2]-qq[2]*c0[1]+qq[3]*c0[0]])
                ang = 2.0*np.arctan2(np.linalg.norm(r[1:]), abs(r[0]))
                if np.dot(r[1:], ax) < 0: ang = -ang
                qd = float(np.dot(np.array(_w[_i]), ax))
                _qs.append(ang); _qds.append(qd)
            _tq = CREASE.step(torch.tensor(_qs, dtype=torch.float32),
                              torch.tensor(_qds, dtype=torch.float32)).numpy()
            for _i, L in enumerate(LIDS):
                ax = L["ax"]/np.linalg.norm(L["ax"])
                # 摺痕力矩 + 把蓋子帶向目標角度的關蓋力矩
                kp, kd = 1.2, 0.25
                close = kp*(L.get("target", 0.0) - _qs[_i]) - kd*_qds[_i]
                _tau[_i] = ax*float(np.clip(_tq[_i] + close, -3.0, 3.0))
            LIDVIEW.apply_forces_and_torques_at_pos(torques=_tau, is_global=True)
        if MOVE is not None:
            move_box(t + _/(5.0*FPS))       # 每個物理步都更新 kinematic 目標,不要一格才跳一次
        world.step(render=False)
    if MOVE is not None:
        move_box(t + 4.0/(5.0*FPS))
    world.step(render=True)
    if MOVE is not None:
        ph_ = ("settle" if t < a.move_wait else
               "move" if t < a.move_wait + a.move_t else
               "settled" if (not a.move_open or t < a.move_wait + a.move_t + a.settle) else "open lids")
        if "pre" not in S and t + 1.0/FPS >= a.move_wait:
            S["pre"] = True
            _S0 = np.array(UsdGeom.Mesh(sp).GetPointsAttr().Get())
            _mp, _mq = mugx.get_world_pose()
            MOVE_PRE = dict(S=_S0, mp=np.array(_mp, float), mq=np.array(_mq, float),
                            bc=BOXC0 + box_off())
    elif a.unbox:
        ph_ = ("packed" if t < T_SET else
               "open upper flaps" if t < T_SET + a.lid_span else
               "open lower flaps" if t < T_SET + 2*a.lid_span else
               "unwrap (reverse)" if t < T_SET + 2*a.lid_span + T_UNW else
               "flatten" if t < T_SET + 2*a.lid_span + T_UNW + a.flat_t else "flat")
    elif P6 is not None:
        ph_ = ("settle" if t < T_SET else
               "6-face press" if t < T_SET + T_DOWN else
               "hold" if t < T_SET + T_DOWN + a.press_hold else "released")
        _hz6 = np.array(UsdGeom.Mesh(sp).GetPointsAttr().Get())
        _e6 = (_hz6.max(0) - _hz6.min(0))*1e3
        if ph_ == "settle": PRESS_H["before"] = _e6
        elif ph_ == "hold": PRESS_H["held"] = _e6
        elif ph_ == "released": PRESS_H["after"] = _e6
    elif a.carton and a.press > 0:
        ph_ = ("settle in box" if t < T_SET else
               "press in box" if t < T_SET + T_DOWN else
               "hold %.0fmm" % a.press if t < T_SET + T_DOWN + a.press_hold else
               "plate off" if t < T_SET + T_DOWN + a.press_hold + a.press_off else
               "close lower" if t < T_SET + T_DOWN + a.press_hold + a.press_off + 4.0 else
               "close upper" if t < T_SET + T_DOWN + a.press_hold + a.press_off + 8.0 else "closed")
        _hz = float(np.array(UsdGeom.Mesh(sp).GetPointsAttr().Get())[:, 2].max())*1e3
        if ph_ == "settle in box": PRESS_H["before"] = _hz
        elif ph_.startswith("hold"): PRESS_H["held"] = _hz
        elif ph_ == "plate off": PRESS_H["after"] = _hz
    elif a.carton and a.close_lid:
        ph_ = ("settle in box" if t < T_SET else
               "close lower flaps" if t < T_SET + a.lid_span else
               "close upper flaps" if t < T_SET + 2*a.lid_span else "settle closed")
    elif a.carton:
        ph_ = "settle in box"
    elif a.press > 0:
        ph_ = ("settle" if t < T_SET else
               "press down" if t < T_SET + T_DOWN else
               "hold %.0fmm" % a.press if t < T_SET + T_DOWN + a.press_hold else
               "plate off" if t < T_SET + T_DOWN + a.press_hold + a.press_off else
               "close lower" if t < T_SET + T_DOWN + a.press_hold + a.press_off + 4.0 else
               "close upper" if t < T_SET + T_DOWN + a.press_hold + a.press_off + 8.0 else "closed")
        _hz = float(np.array(UsdGeom.Mesh(sp).GetPointsAttr().Get())[:, 2].max())*1e3
        if ph_ == "settle":                            PRESS_H["before"] = _hz
        elif ph_.startswith("hold"):                   PRESS_H["held"] = _hz
        elif ph_ == "plate off":                       PRESS_H["after"] = _hz
    elif a.wrapsim or a.stage2:
        _n = len(WORDER)
        _k = int(max(0, min(_n - 1, (t - T_SET)//SPAN_W)))
        ph_ = "settle" if t < T_SET else ("wrap " + WORDER[_k] if t < T_SET + _n*SPAN_W else "settle")
        if NACT and not S.get("pr_" + WORDER[_k]):
            S["pr_" + WORDER[_k]] = True
            P("  [t=%.2f] %s 這一折,整條邊 %d 個錨點中**還貼地(z<%.0fmm)因此真的施力**的有 %d 個"
              % (t, WORDER[_k], sum(1 for q in PULLS if q["side"] == WORDER[_k]),
                 Z_FLOOR*1e3, NACT.get(WORDER[_k], 0)))
    elif a.unfold:
        _ORD = UORDER                        # 字幕的階段名,與 drive() 的 --unfold 順序同源
        _sp = max(0.1, (T_END - T_SET - 3.0)/4)
        _k = int(max(0, min(3, (t - T_SET)//_sp)))
        ph_ = "settle" if t < T_SET else ("unfold " + _ORD[_k] if t < T_SET + 4*_sp else "done")
    else:
        p2 = T_SET + T_SW + T_HOLD + T_OFF
        ph_ = ("settle" if t < T_SET else "fold +-y" if t < p2 else
               "fold +-x" if t < p2 + T_SW + T_HOLD + T_OFF else "release")
    if a.pentrack > 0 and (k % max(1, int(a.pentrack*FPS)) == 0):
        _S = np.array(UsdGeom.Mesh(sp).GetPointsAttr().Get())
        _np_ = self_pen(_S, _TRI0)[0]
        PENLOG.append((t, ph_, _np_))
        P("  [pen] t=%5.2f %-18s 自穿模 %5d" % (t, ph_, _np_))
        # ★ 使用者 2026-09-26:「測一個從折疊到入箱整段,杯子有沒穿模」。
        #   杯子是剛體 ⇒ 只存它的姿態,離線用 V(靜止頂點)重建世界座標。
        #   布穿杯要用**邊**級別才測得到(頂點全在外面也可能整條邊穿過杯壁),
        #   而那需要 trimesh,所以這裡只存軌跡,判讀放到 CPU 端離線做。
        _mp, _mq = mugx.get_world_pose()
        TRAJ_T.append(t); TRAJ_PH.append(ph_)
        TRAJ_S.append(_S.astype(np.float32))
        TRAJ_M.append(np.concatenate([np.array(_mp, float), np.array(_mq, float)]))
    rgb = cam.get_rgba()
    if rgb is not None and rgb.size: frames.append(stamp(rgb, t, ph_))
    if k % 25 == 0:
        S_ = np.array(UsdGeom.Mesh(sp).GetPointsAttr().Get())
        mp = mugx.get_world_pose()[0]
        P("  t=%5.2f %-9s 布 bbox %3.0f x %3.0f x %3.0f ;杯心 (%.0f, %.0f, %.0f) mm"
          % (t, ph_, *((S_.max(0)-S_.min(0))*1e3), *(np.array(mp)*1e3)))

imageio.mimwrite(os.path.join(a.out, "wrap.mp4"), frames, fps=FPS, quality=7, macro_block_size=1)
P("影格 %d → %s/wrap.mp4" % (len(frames), a.out))

if TRAJ_T:
    # 杯子靜止頂點 V 也一起存,離線才能重建世界座標的杯子網格
    np.savez_compressed(os.path.join(a.out, "traj.npz"),
                        t=np.array(TRAJ_T), phase=np.array(TRAJ_PH),
                        sheet=np.array(TRAJ_S), mugpose=np.array(TRAJ_M),
                        mugrest=np.asarray(V, np.float32))
    P("軌跡 %d 個取樣 → %s/traj.npz(布頂點 + 杯子姿態,離線判讀布穿杯用)" % (len(TRAJ_T), a.out))

# ── 判讀:俯視遮蔽 / 貼合 / 圍蔽 ──────────────────────────────────────
SP = np.array(UsdGeom.Mesh(sp).GetPointsAttr().Get())
mp_, mq_ = mugx.get_world_pose()
w_, x_, y_, z_ = [float(v) for v in mq_]
Rm = np.array([[1-2*(y_*y_+z_*z_), 2*(x_*y_-z_*w_), 2*(x_*z_+y_*w_)],
               [2*(x_*y_+z_*w_), 1-2*(x_*x_+z_*z_), 2*(y_*z_-x_*w_)],
               [2*(x_*z_-y_*w_), 2*(y_*z_+x_*w_), 1-2*(x_*x_+y_*y_)]])
MW = V @ Rm.T + np.array(mp_, float)
TRI = np.array(tris, int)
V0, V1, V2 = SP[TRI[:, 0]], SP[TRI[:, 1]], SP[TRI[:, 2]]
E1, E2 = V1 - V0, V2 - V0
rs = np.random.RandomState(0)
samp = MW[rs.choice(len(MW), min(300, len(MW)), replace=False)]
dn = np.sqrt(((samp[:, None, :] - SP[None, :, :])**2).sum(-1)).min(1)

def hit(o, d, tmin):
    pv = np.cross(d, E2); det = (E1*pv).sum(1)
    okm = np.abs(det) > 1e-12
    inv = np.where(okm, 1.0/np.where(okm, det, 1.0), 0.0)
    tv = o - V0; u = (tv*pv).sum(1)*inv
    qv = np.cross(tv, E1); v = (d*qv).sum(1)*inv; tt = (E2*qv).sum(1)*inv
    return bool(np.any(okm & (u >= 0) & (u <= 1) & (v >= 0) & (u+v <= 1) & (tt > tmin)))

top = np.array([hit(samp[i] + np.array([0, 0, .002]), np.array([0., 0, 1.]), 0.) for i in range(len(samp))])
ctr = MW.mean(0); dirs = samp - ctr; rad = np.linalg.norm(dirs, axis=1); dirs /= rad[:, None]
blk = np.array([hit(ctr, dirs[i], rad[i] + .002) for i in range(len(samp))])
up, dn_ = dirs[:, 2] > .5, dirs[:, 2] < -.5; side = ~up & ~dn_
if P6 is not None:
    P("\n===== 六面壓實判讀(目標 %s mm)=====" % a.press6)
    for k, lab in (("before", "壓之前"), ("held", "壓住時"), ("after", "放開後")):
        v = PRESS_H.get(k)
        P("  %s  bbox %s" % (lab, ("%.0f x %.0f x %.0f mm" % tuple(v)) if v is not None else "-"))
if a.press > 0:
    P("\n===== 壓平判讀(剛性平板壓到 %.0fmm)=====" % a.press)
    P("  壓之前  布最高 %6.0f mm" % PRESS_H.get("before", -1))
    P("  壓住時  布最高 %6.0f mm(平板底面在 %.0f mm)" % (PRESS_H.get("held", -1), a.press))
    P("  抬走後  布最高 %6.0f mm  ← 回彈 %.0f mm"
      % (PRESS_H.get("after", -1), PRESS_H.get("after", 0) - PRESS_H.get("held", 0)))
    P("  ⇒ 塞得進 100mm 內高的紙箱?%s"
      % ("要靠蓋子壓住(抬走就彈回 %.0fmm)" % PRESS_H.get("after", -1)
         if PRESS_H.get("after", 999) > 100 else "可以,抬走也維持在 100mm 以內"))
if a.carton:
    # ★ 使用者 2026-09-25:「你要怎麼確定真的入箱子了 你不能相信視覺」。
    #   所以不看畫面,直接拿每一個頂點去比紙箱內腔。
    #   內腔由 carton meta 的 derived 給:wall_inner_x / wall_inner_y / wall_top_z
    IX, IY = (CBOX["ix"], CBOX["iy"]) if CBOX else (0.132, 0.112)
    # ★ 不要寫死 0.100 —— 130mm 的箱子就會用錯上限(2026-09-25 踩到)。
    #   用實際量到的箱子 bbox 最高點。
    _bbz = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
    ZLO = CDZ
    ZHI = float(_bbz.ComputeWorldBound(st.GetPrimAtPath("/World/Box"))
                .ComputeAlignedRange().GetMax()[2])
    # --movebox:箱子搬走了 ⇒ 用箱子**當下**的位移當原點(_OFF),內腔與箱口高度都跟著平移
    _OFF = box_off() if MOVE is not None else np.zeros(3)
    if MOVE is not None:
        ZHI = BOXZHI0          # 搬之前量的箱口高度(箱子是相對座標比對;ktarget 模式 USD 不一定同步)
    _OFFQ = [np.zeros(3)]
    def inbox(nm, Q):
        Q = Q - _OFFQ[0]
        ox = np.abs(Q[:, 0]) > IX; oy = np.abs(Q[:, 1]) > IY
        olo = Q[:, 2] < ZLO - 0.0005; ohi = Q[:, 2] > ZHI
        bad = ox | oy | olo | ohi
        P("  %-4s %6d 點;超出內腔 %5d 個(%.1f%%)| x 超 %d / y 超 %d / 低於底 %d / 高於口 %d"
          % (nm, len(Q), int(bad.sum()), bad.mean()*100,
             int(ox.sum()), int(oy.sum()), int(olo.sum()), int(ohi.sum())))
        P("       x %7.1f~%7.1f (限 ±%.0f) | y %7.1f~%7.1f (限 ±%.0f) | z %7.1f~%7.1f (限 %.0f~%.0f)"
          % (Q[:, 0].min()*1e3, Q[:, 0].max()*1e3, IX*1e3,
             Q[:, 1].min()*1e3, Q[:, 1].max()*1e3, IY*1e3,
             Q[:, 2].min()*1e3, Q[:, 2].max()*1e3, ZLO*1e3, ZHI*1e3))
        P("       z 分位 %s" % " ".join("%d%%=%.0f" % (p, np.percentile(Q[:, 2], p)*1e3)
                                        for p in (50, 95, 99, 99.9)))
        return int(bad.sum()), dict(x=int(ox.sum()), y=int(oy.sum()),
                                    lo=int(olo.sum()), hi=int(ohi.sum()))
    if MOVE is not None and "pre" in S:
        _w, _x, _y, _z = [float(v) for v in MOVE_PRE["mq"]]
        _Rp = np.array([[1-2*(_y*_y+_z*_z), 2*(_x*_y-_z*_w), 2*(_x*_z+_y*_w)],
                        [2*(_x*_y+_z*_w), 1-2*(_x*_x+_z*_z), 2*(_y*_z-_x*_w)],
                        [2*(_x*_z-_y*_w), 2*(_y*_z+_x*_w), 1-2*(_x*_x+_y*_y)]])
        P("\n===== 真的入箱了嗎 —— 搬之前(t=%.2f,箱子在原位)=====" % (a.move_wait - 1.0/FPS))
        nb0_s, _ = inbox("布", MOVE_PRE["S"]); nb0_m, _ = inbox("杯子", V @ _Rp.T + MOVE_PRE["mp"])
    _OFFQ[0] = _OFF
    P("\n===== 真的入箱了嗎(逐頂點比對內腔,不看畫面)%s=====" %
      ("—— 搬之後,原點 = 箱子最終位置(位移 %.1f, %.1f, %.1f mm)" % tuple(_OFF*1e3) if MOVE is not None else ""))
    nb_s, w_s = inbox("布", SP); nb_m, _w_m = inbox("杯子", MW)
    if MOVE is not None and "pre" in S:
        _bcF = BOXC0 + _OFF
        _rel0 = MOVE_PRE["S"].mean(0) - MOVE_PRE["bc"]; _rel1 = SP.mean(0) - _bcF
        _mr0 = MOVE_PRE["mp"] - MOVE_PRE["bc"]; _mr1 = np.array(mp_, float) - _bcF
        _D = np.linalg.norm(_rel1 - _rel0)*1e3; _Dm = np.linalg.norm(_mr1 - _mr0)*1e3
        P("\n===== 搬箱判讀 =====")
        P("  箱子實際位移 (%.1f, %.1f, %.1f) mm(指令 %.0f, %.0f, %.0f)" % (*(_OFF*1e3), *(MOVE*1e3)))
        P("  布質心相對箱底中心:搬前 (%+.1f,%+.1f,%+.1f) → 搬後 (%+.1f,%+.1f,%+.1f) mm"
          % (*(_rel0*1e3), *(_rel1*1e3)))
        P("  杯心  相對箱底中心:搬前 (%+.1f,%+.1f,%+.1f) → 搬後 (%+.1f,%+.1f,%+.1f) mm"
          % (*(_mr0*1e3), *(_mr1*1e3)))
        P("  ⇒ 結論:包裹(布質心)相對箱子位移 D=%.1f mm(杯心 %.1f mm);"
          "搬前超出 N0=%d(布 %d + 杯 %d)、搬後 N1=%d(布 %d + 杯 %d)"
          % (_D, _Dm, nb0_s + nb0_m, nb0_s, nb0_m, nb_s + nb_m, nb_s, nb_m))
    # ★ 2026-09-26:原本這裡寫死「主要是高過箱口 ⇒ 蓋子蓋不上」,但實際超出的方向
    #   不一定是往上 —— w131 那一輪超出的其實是**低於箱底**,結論就講反了。
    #   改成照實際的超出方向講。
    if nb_s == 0 and nb_m == 0:
        P("  ⇒ 兩者都完全在箱內 ✅")
    elif nb_m:
        P("  ⇒ 杯子就沒進去,場景不成立")
    else:
        _dir = max(("高過箱口", w_s["hi"]), ("低於箱底", w_s["lo"]),
                   ("穿出 x 牆", w_s["x"]), ("穿出 y 牆", w_s["y"]), key=lambda kv: kv[1])
        P("  ⇒ 杯子在箱內,但**布有 %d 個頂點超出**,最多的是「%s」%d 個"
          % (nb_s, _dir[0], _dir[1]))
if PENLOG:
    P("\n===== 自穿模時間序(從置放的第 0 格開始量)=====")
    P("  %-8s %-20s %8s %8s" % ("t(s)", "階段", "自穿模", "增量"))
    prev = None
    worst = (0, "", 0)
    for (tt_, ph2_, n_) in PENLOG:
        d_ = "" if prev is None else "%+d" % (n_ - prev)
        if prev is not None and (n_ - prev) > worst[2]: worst = (tt_, ph2_, n_ - prev)
        P("  %-8.2f %-20s %8d %8s" % (tt_, ph2_, n_, d_))
        prev = n_
    P("  ⇒ 單步增加最多的是 t=%.2f「%s」,一口氣 +%d" % worst)
if LIFT0 is not None:
    _mp2 = np.array(mugx.get_world_pose()[0], float)
    _dm = (_mp2[2] - LIFT0["mug"][2])
    _dc = (SP.mean(0)[2] - LIFT0["sc"][2])
    P("\n===== 提杯判讀(包材有沒有跟著上來)=====")
    P("  杯子上升      %7.1f mm" % (_dm*1e3))
    P("  布質心上升    %7.1f mm" % (_dc*1e3))
    P("  L1 跟隨比 = 布/杯 = %.3f   ⇒ %s"
      % (_dc/max(_dm, 1e-9),
         "包材跟著走,包住了 ✅" if _dc/max(_dm,1e-9) > 0.8 else
         "部分跟隨(滑動/部分脫落)" if _dc/max(_dm,1e-9) > 0.2 else "布留在原地 ⇒ 沒包住 ❌"))
    P("  L2 布最低點   %7.1f mm(起點 %.1f mm)⇒ %s"
      % (SP[:,2].min()*1e3, LIFT0["smin"]*1e3,
         "整包離地 ✅" if SP[:,2].min() > 0.020 else "還拖在地上"))
    P("  L4 布 bbox    %.0f x %.0f x %.0f mm" % tuple((SP.max(0)-SP.min(0))*1e3))
P("\n===== 包覆判讀 =====")
P("W1 俯視遮蔽(主判準)      %.0f%%   (門檻 >60%%)" % (top.mean()*100))
if a.unfold:
    _fl = np.array([[-WX/2 + i2*WX/nx, -WY/2 + j2*WY/ny, PLAT_Z]
                    for j2 in range(ny+1) for i2 in range(nx+1)])
    _b = np.where((np.abs(_fl[:,0]) > WX/2-1e-6) | (np.abs(_fl[:,1]) > WY/2-1e-6))[0]
    _d = np.linalg.norm(SP[_b,:2] - _fl[_b,:2], axis=1)*1e3
    _e = SP.max(0)-SP.min(0)
    P("U1 攤開後 bbox %.0f x %.0f mm(布本身 %.0f x %.0f)" % (_e[0]*1e3, _e[1]*1e3, WX*1e3, WY*1e3))
    P("U2 長寬比 %.3f(1.000 = 正方形)" % (_e[0]/_e[1]))
    P("U3 外緣每點離「應該在的位置」:中位 %.0f mm、最大 %.0f mm" % (np.median(_d), _d.max()))
P("W2 貼合 ≤12mm             %.0f%%   (門檻 >40%%);中位距離 %.0f mm" % ((dn <= .012).mean()*100, np.median(dn)*1e3))
P("W3 圍蔽 全部 %.0f%% | 上 %.0f%% | 側 %.0f%% | 下 %.0f%%"
  % (blk.mean()*100, blk[up].mean()*100 if up.any() else -1,
     blk[side].mean()*100 if side.any() else -1, blk[dn_].mean()*100 if dn_.any() else -1))
P("W4 杯心 (%.0f, %.0f, %.0f) mm(起點 0,0,%.0f);位移 %.0f mm"
  % (*(np.array(mp_)*1e3), MZ*1e3, np.linalg.norm(np.array(mp_) - np.array([0,0,MZ]))*1e3))
# W5:杯子有幾成在布的 xy 範圍內 **且** 低於布的頂面 —— 擋掉「布懸在上方」的假陽性
lo, hi = SP.min(0), SP.max(0)
inside = ((samp[:,0] > lo[0]) & (samp[:,0] < hi[0]) &
          (samp[:,1] > lo[1]) & (samp[:,1] < hi[1]) & (samp[:,2] < hi[2]))
P("W5 杯子落在布的包絡內的比例 %.0f%%  ← 擋掉「布懸在杯子上方」的假陽性" % (inside.mean()*100))
# ★ 證明「這真的是同一張布」:量每條邊相對攤平時的長度變化。
#   布不可伸長 ⇒ 邊長幾乎不變。若是我拼出來的盒子,邊長會亂掉。
_flat = np.array([[-WX/2 + i*WX/nx, -WY/2 + j*WY/ny, 0.0]
                  for j in range(ny+1) for i in range(nx+1)])
_e = set()
for _t in tris:
    for _a2, _b2 in ((_t[0],_t[1]), (_t[1],_t[2]), (_t[2],_t[0])):
        _e.add((min(_a2,_b2), max(_a2,_b2)))
_e = np.array(sorted(_e))
_L0 = np.linalg.norm(_flat[_e[:,0]] - _flat[_e[:,1]], axis=1)
_L1 = np.linalg.norm(SP[_e[:,0]] - SP[_e[:,1]], axis=1)
_r = _L1/_L0
_sp_n, _sp_e, _sp_t = self_pen(SP, np.array(tris, int))
P("S1 自穿模:布的邊穿過布的面 **%d** 次(%d 邊 x %d 面,已排除相鄰);selfCollision=%s"
  % (_sp_n, _sp_e, _sp_t, "ON" if a.selfcol else "OFF"))
P("★ 是不是同一張布:%d 條邊,長度/攤平時 中位 %.3f、5%%~95%% 分位 %.3f~%.3f、最大 %.3f"
  % (len(_e), np.median(_r), np.percentile(_r,5), np.percentile(_r,95), _r.max()))
P("  (布不可伸長 ⇒ 比值應該接近 1。拼出來的盒子不會有這個性質)")
np.savez(os.path.join(a.out, "wrap.npz"), sheet=SP, mug=MW, top=top, dn=dn, blk=blk)
LOG.close(); sim.close()
