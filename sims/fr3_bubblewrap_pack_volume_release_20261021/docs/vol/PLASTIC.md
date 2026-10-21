# PLASTIC:runtime 改 rest shape 模擬塑性(2026-10-21)— **定位:備案**(主線改走材料係數 matsweep)

## 結論
- **runtime 改 rest 可行、回彈真的消掉**:PhysX 107.3 volume deformable 只寫 `omniphysics:restShapePoints` **不生效**(回彈 43.6° 照舊);寫完把 body prim `SetActive(False)` → `SetActive(True)` 讓 PhysX 以新 rest 重建(points = 當下)→ 探針**回彈 43.6° → 0.5°**;刪掉重建同一塊板也行(0.2°)。tensor API 沒有 set rest。重建時掛在板上的 attachment 會跟著回來。
- **(A) 折好後烘焙**(`--plastic_on_fold 1`,關蓋放錨前):搬箱 + 開蓋後杯頂覆蓋 99% → **100%**(對照 99% → 88%);去掉整包剛體運動後各片形狀變化中位 **7~9 mm**(對照 10~25 mm)→ 「包嚴實」兩個判準都過。
- **致命副作用:重建後這塊布的自碰撞失效**(PhysX 行為,試過 7 種重建 / 濾距 / 重開旗標都一樣;開場就用折好 rest 建也一樣)。wrap 裡烘焙那一步自穿 20 → 171~252(四角收耳區被蓋子壓進下層),之後一直 ~130;穿杯 0、和杯 / 箱 / 夾爪的碰撞照常。判準「自穿 0」**不過**。
- **(B) 放手前烘焙**(`--plastic_on_release 1`):**沒拿到有效結果**。fast 精度 + `--edamp 0.02` 的布在掀之前整體邊長比就有 2.64~2.77(B5/B6/C3/C4;edamp 0 的 C2 只有 1.67),`--guard_yn 2.6` 在弧線一開始就觸發放手 → yn、yp 都沒掀起(越線 0%)、烘焙沒執行。改 `--guard 3.5` 重跑的 3 次(B8/B9/B0 對照)因 GPU 讓給 matsweep 未開跑。
- 另:`--plastic_how frame` + `--edamp 0.02` + `--jaw_collide 1` 烘焙後下一步 segfault(B1、C1);`--plastic_how step` 正常 → 預設改 step。夾爪 agent 的 `--jaw_collide 1 --extract 0` 在 wrap_vol 1964 行 NameError `H3F`(取杯指只在 extract 1 時定義),B3 因此中止。
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
