# PLASTIC:runtime 改 rest shape 模擬塑性(2026-10-21)— **定位:備案**(主線改走材料係數 matsweep)

## 結論
- **runtime 改 rest 可行、回彈真的消掉**:PhysX 107.3 volume deformable 只寫 `omniphysics:restShapePoints` **不生效**(回彈 43.6° 照舊);寫完把 body prim `SetActive(False)` → `SetActive(True)` 讓 PhysX 以新 rest 重建(points = 當下)→ 探針**回彈 43.6° → 0.5°**;刪掉重建同一塊板也行(0.2°)。tensor API 沒有 set rest。重建時掛在板上的 attachment 會跟著回來。
- **(A) 折好後烘焙**(`--plastic_on_fold 1`,關蓋放錨前):搬箱 + 開蓋後杯頂覆蓋 99% → **100%**(對照 99% → 88%);去掉整包剛體運動後各片形狀變化中位 **7~9 mm**(對照 10~25 mm)→ 「包嚴實」兩個判準都過。
- **致命副作用:重建後這塊布的自碰撞失效**(PhysX 行為,試過 7 種重建 / 濾距 / 重開旗標都一樣;開場就用折好 rest 建也一樣)。wrap 裡烘焙那一步自穿 20 → 171~252(四角收耳區被蓋子壓進下層),之後一直 ~130;穿杯 0、和杯 / 箱 / 夾爪的碰撞照常。判準「自穿 0」**不過**。
- **(B) 放手前烘焙**(`--plastic_on_release 1`):**沒拿到有效結果**。fast 精度 + `--edamp 0.02` 的布在掀之前整體邊長比就有 2.64~2.77(B5/B6/C3/C4;edamp 0 的 C2 只有 1.67),`--guard_yn 2.6` 在弧線一開始就觸發放手 → yn、yp 都沒掀起(越線 0%)、烘焙沒執行。改 `--guard 3.5` 重跑的 3 次(B8/B9/B0 對照)因 GPU 讓給 matsweep 未開跑。
- 另:`--plastic_how frame` + `--edamp 0.02` + `--jaw_collide 1` 烘焙後下一步 segfault(B1、C1);`--plastic_how step` 正常 → 預設改 step。夾爪 agent 的 `--jaw_collide 1 --extract 0` 在 wrap_vol 1964 行 NameError `H3F`(取杯指只在 extract 1 時定義),B3 因此中止。
- **(A2) 2026-10-21 晚:自碰撞失效已找到原因並修好**(見 §6):PhysX 以 **rest 形狀**判定哪些點對不互撞,門檻實測 ≈ 2·contactOffset(cont 2 mm → 層距 < ~4 mm 被濾掉);「rest 層間距 30 mm」那次是上層掉 30 mm 穿隧(放手 0.15 s 內就穿,不是濾除)。`--plastic_spread_mm 8`:搬 + 開蓋後覆蓋 97~98%、自穿全程最大 = 對照。**但 final 整鏈 yn 掀開被守衛中止(越線 1%)→ 還不能併入**。
- 替代路線(若要「放手仍開」又不能有自穿):(1) 材料係數(matsweep,主線);(2) 鉸線窄帶低 E 分段材料 —— 107.3 一個 volume body 只能一個材料,要拆成兩個 body + attachment 縫合;(3) 只在「最後一段、不再有層疊接觸」時才烘焙(例如取杯完成後),讓自碰撞失效不影響畫面。

## 改的檔與旗標(預設 = 舊行為;備份 `wrap_vol.py.before_plastic`,我的 diff 約 40 行)
- `--plastic_on_fold 0|1`:關蓋完成、放錨點前全片 rest ← 當下。
- `--plastic_on_release 0|1`:yn / yp 第一隻手放手前 `--plastic_pre`(0.2)秒改 rest(手仍綁著才做);`--plastic_region all|side`(side = 本片 + 鉸線內 30 mm)。
- `--plastic_how step|frame`(預設 step)、`--plastic_filter_mm`(重建時改 selfCollisionFilterDistance,實測無效)。
- `--release_watch 1`:放手後 0.5 / 2 / 10 s 印 `[plastic] 放手後 Ns:越線 / 壁外 / 質心 / 自穿 / 穿杯 / 杯位移`(plastic_on_release 時自動開)。
- `--grasp_tail_s`:抓取段後多觀察幾秒(讓 yp 也有放手後 10 s)。
- log:`★ t=.. [plastic] …:rest ← 當下形狀 N 點(全片 2592)| 彈性能(StVK)改前 X J → 改後 ~0 J | SetActive 重建(step)`。
- 新檔:`plastic/probe_rest_runtime.py`、`plastic/probe_selfcoll.py`、`plastic/run.sh`(JAW 正式旗標改 hand2 off / hand2_keep 0 / hold_yp 0)、`plastic/fold_stats.py`、`plastic/apply_patch.py`、`plastic/gpuwait.sh`、`plastic/probe_all.sh`、`plastic/sc.sh`。`../publish_sim_forge.sh` EXC 加 `--exclude 'plastic/*/'`。

## 重現
```
cd vol
/isaac-sim/python.sh plastic/probe_rest_runtime.py --mode 0   # 對照;--mode 3 / 4 / 6 有效;--grav 1 有重力
/isaac-sim/python.sh plastic/probe_selfcoll.py --bake 0       # 自碰撞對照;--bake 1 失效
plastic/run.sh A1 --grasp 0 --extract 0 --quality fast --plastic_on_fold 1      # A0 = --plastic_on_fold 0
python3 plastic/fold_stats.py plastic/A0 plastic/A1 plastic/A2
plastic/run.sh B8 --quality fast --extract 0 --peel_t 8 --edamp 0.02 --grasp_tail_s 8.5 --guard_yn 3.5 --guard_yp 3.5 --guard_n 2 --plastic_on_release 1   # 未跑
grep -h "plastic\]\|守衛" plastic/B*/stdout.txt
```

## 影片(都是 fast 960x540,沒有達標 → 沒複製到 videos/)
| 次 | 內容 | 路徑 |
|---|---|---|
| A0 | 折 → 入箱 → 搬 → 開蓋,不烘焙(對照,覆蓋 99 → 88%)| `vol/plastic/A0/wrap.mp4` |
| A1 | 同上 + 關蓋時烘焙(覆蓋 100%,自穿 191)| `vol/plastic/A1/wrap.mp4` |
| A2 | A1 + filter 0.1 mm | `vol/plastic/A2/wrap.mp4` |
| B5 | 掀 yn/yp(edamp 0.02、guard 2.6)→ 守衛一開始就放手,沒烘焙 | `vol/plastic/B5/wrap.mp4` |
| B6 | 同 B5(yn 段後中止)| `vol/plastic/B6/wrap.mp4`(不完整)|
| C2/C3/C4 | 烘焙 segfault 隔離(到 move 前)| `vol/plastic/C{2,3,4}/wrap.mp4` |

## 1. 探針 `plastic/probe_rest_runtime.py`(200×100×4 板,根部 8 mm 夾持,尖端桿彎 90°,放手前 0.2 s 改 rest,無重力,E 2e3)
`grep -h RESULT plastic/logs/probe_m*_g0_*.log`
| mode | 做法 | 放手前彎角 | 放手後 5 s | 回彈 |
|---|---|---|---|---|
| 0 | 不改(對照) | 81.9° | 38.4° | 43.6° |
| 1 | 只寫 USD `omniphysics:restShapePoints` | 81.9° | 38.4° | 43.6°(不生效)|
| 2 | 1 + USD points ← 當下 | 81.9° | 38.4° | 43.6°(不生效)|
| 3 | 1 + `SetActive(False)` → step → `SetActive(True)` | 82.4° | 81.9° | **0.5°** |
| 4 | 刪掉整塊板、同路徑重建(points = rest = 當下)+ 重建夾持 | 82.1° | 81.8° | **0.2°** |
| 5 | 1 + RemoveAPI / ApplyAPI `OmniPhysicsDeformableBodyAPI`(中間 step)| 82.4° | 81.9° | 0.5°(中間那步 attachment 報 invalid actors)|
| 6 | 1 + 同一幀 `SetActive(False)` → `SetActive(True)`(不多走一步)| — | — | 有重力版與 3 完全相同 |
- 改 rest 前後 StVK 彈性能 2.19e-5 J → ~0(log「★ t=2.20」);放手後 5 s 能量 6e-8 J(只剩數值雜訊)。
- 有重力(`--grav 1`):E 2e3、192 mm 懸臂本身撐不住自重(自重屈曲長度 ~47 mm),0 / 3 / 6 放手後都垂下(-31° / -23.5° / -23.5°),但都還吊在根部夾持上 → 重建後 attachment 仍有效。塑性只消掉「彈回」,不會讓板變硬。
- wrap_vol 預設 `--plastic_how step`(= mode 3);`frame` = mode 6(見 segfault)。

## 2. (A) 折好後烘焙 `--plastic_on_fold 1`(關蓋完成、放錨點前,全片)
`plastic/run.sh A1 --grasp 0 --extract 0 --quality fast --plastic_on_fold 1`(A0 = 0 對照,A2 加 `--plastic_filter_mm 0.1`);`python3 plastic/fold_stats.py plastic/A0 plastic/A1 plastic/A2`
| 次 | 烘焙 | 杯頂覆蓋 放錨前 → 搬前 → 搬後 → 開蓋後 | 下降 | 各片形狀變化(剛體對齊後)中位/p90 mm | 各片相對箱位移 中位 mm | 布 bbox 放錨前 → 開蓋後 | 自穿 全程最大 / 結束 | 穿杯 |
|---|---|---|---|---|---|---|---|---|
| A0 | 0 | 99 → 89 → 88 → 88% | 11 | yn 11/18 yp 10/23 xp 25/34 xn 16/20 | yn 17 yp 15 xp 32 xn 23 | 258×223×122 → 263×223×124 | 29 / 1 | 0 |
| A1 | 1 | 99 → 100 → 100 → 100% | -1 | yn 8/16 yp 7/15 xp 8/16 xn 9/16 | yn 22 yp 19 xp 22 xn 20 | 257×223×122 → 261×223×110 | 191 / 131 | 0 |
| A2 | 1 + filter 0.1 mm | 99 → 100 → 98 → 99% | 0 | yn 8/15 yp 6/10 xp 7/12 xn 9/16 | yn 21 yp 15 xp 13 xn 18 | 259×223×123 → 259×223×115 | 185 / – | 0 |
- 「相對箱位移」~20 mm 是整包(杯 + 布)在箱裡一起滑:杯相對箱 21~22 mm、杯轉 25°,兩組一樣,不是布鬆開。判準「各片 <10 mm」用剛體對齊後的形狀變化:A1/A2 中位 6~9 mm 過,對照 xp 25、xn 16 不過。
- 覆蓋率判準(下降 <10 點):A1 -1、A2 0 過;對照 11 不過。
- 自穿:烘焙那一步 20 → 191,位置在布四角(flat |x|≈221、|y|≈207 mm = 收耳區),bbox 高 121 → 116(那一刻往下塌 5 mm)。`--plastic_filter_mm 0.1`(自碰撞濾距)沒改善 → 不是 rest 濾距。調查中:`plastic/probe_selfcoll.py`。

## 3. 副作用:重建後自碰撞失效(`plastic/probe_selfcoll.py`)
200×100×4 板(自碰撞 on、filter 1 mm,同 wrap_vol)對折,上層蓋在下層上方(表面間距 --gap_mm),放手 1 s 後 kinematic 壓板往下壓 3 mm。`grep -h RESULT plastic/logs/probe_sc*.log`
| 做法 | 自穿(結束)| 上下層 z 差 中位 / 最小 mm |
|---|---|---|
| 不烘焙(對照)| **0** | 5.74 / 0.88 |
| 烘焙(rest ← 當下 + SetActive 同幀重建)| 750 | 1.23 / -3.04 |
| 烘焙 + filter 0 mm | 749 | 1.17 / -3.04 |
| 烘焙,rest 層間距 30 mm(壓 30 mm)| 849 | 1.10 / -5.69 |
| 烘焙改「刪掉重建」| 750 | 1.22 / -3.05 |
| 烘焙改「release_physics_objects + force_load_physics_from_usd」整場重載 | 754 | 1.21 / -3.35 |
| 烘焙後 runtime 把 selfCollision 關→開 / 重寫 True + filter | 764 / 749 | 1.26 / -3.04 |
| **只 SetActive 重建、rest 不改(平)**| 225 | 6.19 / -4.80 |
| 開場就建成對折形狀(points = rest = U 形,不在 runtime 改)| 992 | 0.74 / -6.40 |
- 結論:PhysX 107.3 volume deformable 的**自碰撞在 rest ≠ 平板、或 body 在模擬中途重建後就不作用**(各種重建方式、濾距、重開旗標都一樣)。所以「改 rest 模擬塑性」= 回彈消掉,但這塊布之後層與層之間互相穿過(杯子、箱子、夾爪等**其他物體的碰撞照常**,穿杯 0)。
- wrap 裡:(A) 在關蓋放錨前烘焙 → 之後全程沒有自碰撞,自穿 20 → 130~190(四角收耳區被蓋子壓進下層)。
- 另:B1(`--plastic_on_fold 1 --plastic_on_release 1 --edamp 0.02 --jaw_collide 1`,frame 重建)在烘焙後下一步 segfault(libcarb.tasking);同旗標 `--until box` 短跑 C1 重現,C2(edamp 0)、C3(jaw_collide 0)、C4(`--plastic_how step`)都正常 → 之後用 `--plastic_how step`。

## 4. (B) 放手前烘焙(fast)
`grep -h "plastic\]\|守衛" plastic/B5/stdout.txt plastic/B6/stdout.txt`
| 次 | 旗標差異 | 掀之前全布邊長比 | yn 守衛 | yn 放手後 2 s / 10 s 越線(全片)/ 壁外 | yp 守衛 | yp 放手後 10 s 越線(全片)/ 壁外 | 自穿 全程最大 | 穿杯 | 杯位移 |
|---|---|---|---|---|---|---|---|---|---|
| B5 | release 烘焙、step、edamp 0.02、guard 2.6、peel_t 8 | 2.64 | t=57.03 放(2.669,弧線第 1 格)| 0 / 0%(44 / 43%)/ 0% | t=97.03 放(2.677)| 0%(46%)/ 0% | 9 | 0 | 0.1 mm |
| B6 | 同 B5 | 2.73 | t=57.03 放(2.754)| 0 / 0%(44 / 44%)/ 0% | (中止)| – | – | 0 | 0.3 mm |
| B1 | + fold 烘焙 + jaw_collide 1、frame | – | – | segfault @26.9 烘焙後 | – | – | – | – | – |
| B3 | release 烘焙 + jaw_collide 1 + extract 0 | – | – | NameError H3F(jaw3 程式)| – | – | – | – | – |
- 守衛觸發時手已不在 → `pl["att"]["on"]` 為假 → 烘焙不執行(設計如此,避免把翻回的形狀烘進去)。所以 (B) 這幾次量到的是「沒掀起來」,不是塑性失效。
- 夾爪碰撞體指-布最小距離:沒有跑到 jaw_collide 1 的有效掀開段(B1 segfault、B3 NameError),無資料。

## 5. 烘焙 segfault 隔離(`--until box` 短跑,fold 烘焙)
| 次 | edamp | jaw_collide | how | 結果 | 烘焙前彈性能 | 自穿 全程最大 | 邊長比最大 | 反轉 |
|---|---|---|---|---|---|---|---|---|
| C1 | 0.02 | 1 | frame | **segfault** | 0.266 J | – | – | – |
| C2 | 0 | 1 | frame | OK | 0.069 J | 171 | 1.666 | 0 |
| C3 | 0.02 | 0 | frame | OK | 0.275 J | 236 | 2.772 | 46 |
| C4 | 0.02 | 1 | step | OK | 0.273 J | 252 | 2.701 | 58 |
- fast 精度下 `--edamp 0.02` 讓折好的布能量 4 倍、邊長比 1.67 → 2.7、反轉 0 → 46~58 —— 這也是 B5/B6 守衛一開始就觸發的原因(fast + edamp 0.02 不適合拿 guard 2.6 判)。

## 6. (A2) 撐開 rest(`--plastic_spread_mm d`,2026-10-21 晚)
**結論:rest 疊層撐開 8 mm 再重建 → fold 烘焙後自碰撞保住(fast 3 次:開蓋後覆蓋 97~98%、自穿全程最大 28~31 = 對照 27~30、穿杯 0、反轉 0);但 final 整鏈 1 次 yn 掀開被守衛中止(越線 1%,對照 X2 91%)、取杯時布被帶起 62%(對照 22~35%)→ 掀開段受影響,不標「候選併入 v1.1」。**

### 6.1 原因(探針 `plastic/probe_spread.py`)
- 和 surface 線(work/CREASE.md)同一個機制:**rest 形狀裡距離小於門檻的點對不互撞**。門檻不是 USD 的 `physxDeformableBody:selfCollisionFilterDistance`(實際值 = 建立時寫的 0.001,重建後也是 0.001,印在 `★ 重建後屬性`),**實測 ≈ 2·contactOffset**:cont 2 mm 時 rest 表面間距 3 mm 失效、4 mm 部分(301)、5 mm 17、6 mm 9、8 mm 0;**cont 1 mm 時 3 mm 就 0**。
- `OmniPhysicsDeformablePoseAPI` 的 `selfCollisionFilterPose`(schema 說「濾除用的姿態,沒給就用 points」):volume 107.3 **沒作用** —— 設成平板(fpose flat)照樣 1130;d=5 時設不設都 17。濾除看的是 restShapePoints。
- 舊的「rest 層間距 30 mm 仍失敗」:那次放手後 0.15 s(還沒壓)自穿就 331 —— E 2e3 撐不住 30 mm 高的上層,自由落下 ~0.8 m/s = 每步 6.4 mm > 板厚 4 mm 穿隧,不是濾除。舊的「開場就建成 U 形」(gap 3 mm < 4 mm)也被濾掉,一致。

### 6.2 探針表(200×100×4 板、E 2e3、filter 1 mm、cont 2 / rest 0.5 mm;對折、壓板壓到 10 mm(兩層貼合)時烘焙,再多壓 1 mm 到 9 mm)
`grep -h RESULT plastic/spread/*_q1_*.log`;撐開 = `plastic/spread_rest.py`(邊長 = 當下、疊層中面距 ≥ T+d、四面體體積 ≥ 0.3× 當下,scipy least_squares 稀疏解析 Jacobian,2652 點 6~9 s)
| rest | cont | 烘焙前 自穿 / 中面層距 | 烘焙後 自穿 最大 / 結束 | 結束中面層距 中位 / 最小 mm |
|---|---|---|---|---|
| 不烘焙(對照)| 2 | 0 / 5.00 | 0 / 0 | 4.26 / 4.18 |
| 當下(舊 A)| 2 | 0 / 5.00 | 1118 / 1114(重建後 2 步就整層掉進下層)| 0.84 / 0.01 |
| 撐開 3 mm | 2 | 0 / 5.00 | 1111 / 1111 | 1.01 / 0.99 |
| 撐開 4 mm | 2 | 0 / 5.00 | 303 / 301 | 4.26 / 3.06 |
| 撐開 5 mm | 2 | 0 / 5.00 | 17 / 17 | 4.26 / 4.17 |
| 撐開 5 mm + filterPose = 平板 | 2 | 0 / 5.00 | 17 / 17 | 4.26 / 4.18 |
| 撐開 6 mm | 2 | 0 / 5.00 | 9 / 9 | 4.26 / 4.16 |
| **撐開 8 mm** | 2 | 0 / 5.00 | **0 / 0** | 4.26 / 4.16 |
| 撐開 3 mm | **1** | 0 / 5.00 | **0 / 0** | 4.26 / 4.17 |
| 撐開 5 mm,層還沒貼上時烘焙(pre,層距 3 mm)| 2 | 0 / 5.80 | 0 / 0 | 4.99 / 4.89 |
| 當下 + filterPose 平板(第 1 批,壓到 8 mm)| 2 | 0 / 5.00 | 1131 | 0.98 |
- 第 1 批壓到 8 mm(超過兩層實厚,對照也 308)不當判準,只看重建後到過壓前:3 mm(rest 或 none)立刻 1100+;5 / 8 mm 重建後 0、過壓才和對照一樣穿。
- ⇒ wrap(cont 2 mm)用 **d = 8**;若 cont 改 1 mm,d = 3 就夠。

### 6.3 wrap 3 次(fast,`--grasp 0 --extract 0`,plastic/run.sh 旗標,搬 + 開蓋;run3.sh MAXPAR 1)
`python3 plastic/spread_stats.py plastic/spread/W8/{1,2,3} plastic/spread/W0/{1,2,3}`
| 次 | 烘焙 | 杯頂覆蓋 放錨前 → 搬前 → 搬後 → 開蓋後 | 下降 | 形狀變化(剛體對齊)中位/p90 mm yn yp xp xn | bbox 高 放錨前 → 結束 | 自穿 全程最大 / 結束 | 穿杯 | 反轉 最大 |
|---|---|---|---|---|---|---|---|---|
| W8/1 | d=8 | 99 → 98 → 97 → 98% | 1 | 6/10 6/12 10/15 11/14 | 122 → 114 | 31 / 17 | 0 | 0 |
| W8/2 | d=8 | 99 → 96 → 96 → 98% | 1 | 8/15 7/15 9/16 9/17 | 122 → 109 | 28 / 11 | 0 | 0 |
| W8/3 | d=8 | 99 → 98 → 98 → 97% | 2 | 7/13 6/13 10/16 9/14 | 123 → 112 | 29 / 1 | 0 | 0 |
| W0/1 | 否 | 99 → 88 → 90 → 88% | 11 | 9/16 9/26 22/34 19/26 | 122 → 124 | 27 / 1 | 0 | 0 |
| W0/2 | 否 | 99 → 89 → 88 → 87% | 12 | 10/17 9/34 23/35 23/38 | 123 → 125 | 30 / 1 | 0 | 0 |
| W0/3 | 否 | 99 → 91 → 89 → 90% | 9 | 9/14 10/29 23/35 19/28 | 123 → 117 | 27 / 3 | 0 | 0 |
| (舊 A1)| d=0 | 99 → 100 → 100 → 100% | -1 | 8/16 7/15 8/16 9/16 | 122 → 110 | 191 / 131 | 0 | 0 |
- 判準:覆蓋 ≥ 95% **過**(97~98);自穿全程最大 ≤ 對照 + 5 **過**(28~31 vs 27~30;都是關蓋壓住時、烘焙前的值);穿杯 0 **過**。
- 結束自穿 17 / 11 / 1(對照 1~3):殘留點都是**布邊界頂點**(邊列 / 四角)關蓋時被壓進別層,烘焙把形狀「固定」後搬動不再鬆開(對照的布會回彈把它擠出來);rest 本身(X)自穿 0~1,不是濾除。有向撐開(沿 b 片法線、鄰對投票)試過反而變差(rest 自穿 7~37),沒採用。
- 烘焙一步 15~21 s(CPU 解 rest,2592 點、疊層對 330~380、外迴圈 3 次);彈性能 6.9e-2 → 2.0e-2 J(撐開的部分有應變)。
- 第 1 版解算(沒有體積障礙)W8/1_v1:rest 有 2 個反轉四面體 → 模擬反轉 2;加體積 ≥ 0.3× 當下的障礙後 0(W8/1~3 都是新版)。

### 6.4 final 整鏈 1 次(`./run3.sh plastic/spread/FIN @demo --quality final --plastic_on_fold 1 --plastic_spread_mm 8`;對照 = extract6/X1、X2,同 @demo 旗標、final 物理、不烘焙)
| | FIN(烘焙 d=8)| X2 | X1 |
|---|---|---|---|
| 開蓋後杯頂覆蓋 | 98%(99 → 99 → 99 → 98)| – | – |
| yn 綁點 / 越線 / 放手後 | 29 / **1% / 0%** | 18 / 91 / 88% | 12 / – |
| 守衛 | **yn@62.03(邊長比 3.97 > 2.6)** | 沒觸發 | 沒觸發 |
| yp 綁點 / 越線 / 放手後 | 13 / 95 / 95% | 19 / 74 / 75% | 15 / 69 / 71% |
| 他片 yn / yp | 15 / 9.1% | 30.7 / 14.8% | 22.6 / 11.5% |
| 手2 綁點 | 0(yn 已放手)| 27 | 32 |
| 布被帶起 抬起 / 落地 | **59.3 / 62.4%** | 23.5 / 22.0% | 31.7 / 34.8% |
| 自穿 全程最大 | 14(t=53.5 yn 合指)| 0 | 4 |
| 穿杯 全程 / 取杯 | 0 / 0 | 0 / 0 | 0 / 0 |
| 反轉 全程最大 | 13(烘焙前 0~2,烘焙後 4~8)| – | – |
| 體積比 | 0.98 → **0.91**(烘焙那一步,之後不變)| – | – |
- 掀開段**受影響**:yn 掀到 2/3 弧線時邊長比 1.85 → 3.97(t=59.5~62.0)→ 守衛放手、yn 沒掀起;布 rest 是折好 + 撐開的形狀,夾點附近要拉很長才翻得動。yp 反而 95%(高於對照)。
- 取杯帶起 62%:折好形狀被「固定」,整包跟杯子一起被拉出來。
- edamp 0.02 + final:烘焙後體積比 0.98 → 0.91、反轉 4~8 —— 撐開 8 mm 的 rest 在關著的箱裡放不下(杯頂 3~4 層要多 ~24 mm),被蓋子壓縮。

### 6.5 下一步(建議)
1. **掀開前「解烘焙」**:開蓋 hold 結束、挑角前把 rest 改回平板(FLAT)再重建 → 掀開 / 取杯回到對照的物理(rest 平板時濾除只排除相鄰點,不會失效);(A) 的目的(搬 + 開蓋覆蓋)在那之前已達成。要先用探針確認「folded points + flat rest 重建」自碰撞正常(舊探針 bake 2 有 225,但那次是 E 2e3 回彈太猛,待查)。
2. 若要 d 小一點(箱內放得下):contactOffset 2 → 1 mm 時 d = 3 就夠(探針),但 cont 是正式物理參數,要另驗。
3. 結束自穿殘留(邊界頂點):烘焙前先把邊界列頂點沿法線退出別層(或不把邊界列寫進 rest,保留當下 rest)。

### 6.6 改的檔與旗標(預設 = 舊行為)
- `wrap_vol.py`(備份 `wrap_vol.py.before_spread`,diff 6 行,標 `[spread]`):`--plastic_spread_mm d`(預設 0 = rest ← 當下);>0 且全片烘焙(`--plastic_on_fold 1`)時 rest = `plastic/spread_rest.solve(當下, FLAT, TETS, T, d)`,log `★ t=.. [spread] rest 撐開 ..`。`--plastic_on_release` 的 side 區域烘焙不撐開。
- 新檔:`plastic/spread_rest.py`(解算,`python3 plastic/spread_rest.py` = U 形自測)、`plastic/probe_spread.py`(探針;`--spread_mm --fpose none|flat|rest|cur --bake_at pre|press --press2_mm --cont_mm`)、`plastic/spq.sh`(探針佇列:共用 run3 啟動鎖、GPU < 29500、OOM 偵測重跑)、`plastic/spread_stats.py`(3 次表)。
- volcommon.py 沒改。輸出在 `plastic/spread/`(publish 排除 `plastic/*/`)。

### 6.7 影片(沒達標 → 沒複製到 videos/)
| 次 | 內容 | 路徑 |
|---|---|---|
| W8/1 | fast:折 → 關蓋烘焙(撐開 8 mm)→ 搬 → 開蓋(覆蓋 98%,自穿 31 / 17)| `vol/plastic/spread/W8/1/wrap.mp4` |
| W0/1 | 同上不烘焙(對照,覆蓋 88%)| `vol/plastic/spread/W0/1/wrap.mp4` |
| FIN | final 整鏈 + 烘焙:yn 守衛放手、yp 95%、取杯帶起 62% | `vol/plastic/spread/FIN/1/wrap.mp4` |

### 6.8 重現
```
cd vol
plastic/spq.sh "--bake 0" "--bake 1 --spread_mm 0" "--bake 1 --spread_mm 8" "--bake 1 --spread_mm 3 --cont_mm 1"
grep -h RESULT plastic/spread/*_q1_*.log
BASE=$(cat plastic/spread/BASE_FLAGS.txt)
MAXPAR=1 ./run3.sh plastic/spread/W8 $BASE --grasp 0 --extract 0 --quality fast --plastic_on_fold 1 --plastic_spread_mm 8
MAXPAR=1 ./run3.sh plastic/spread/W0 $BASE --grasp 0 --extract 0 --quality fast --plastic_on_fold 0
python3 plastic/spread_stats.py plastic/spread/W8/{1,2,3} plastic/spread/W0/{1,2,3}
N=1 ./run3.sh plastic/spread/FIN @demo --quality final --plastic_on_fold 1 --plastic_spread_mm 8
```
