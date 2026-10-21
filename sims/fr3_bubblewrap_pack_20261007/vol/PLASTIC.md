# PLASTIC:runtime 改 rest shape 模擬塑性(2026-10-21)

## 結論(進行中,逐階段更新)
- **runtime 改 rest 可行**:PhysX 107.3 volume deformable 只寫 `omniphysics:restShapePoints` **不生效**(回彈照舊 43.6°);寫完再把 body prim `SetActive(False)` → `SetActive(True)`(同一幀即可),PhysX 以新 rest 重建、points = 當下形狀 → **回彈 43.6° → 0.5°**。刪掉重建同一塊板(teleport)也行(0.2°)。tensor API(`DeformableBodyView`)只有 `get_rest_nodal_positions`,沒有 set。
- 重建時掛在板上的 VtxXformAttachment(根部夾持)**會跟著回來**(重力探針板仍吊在夾持上)。
- (A) 折好後烘焙(`--plastic_on_fold 1`):搬箱 + 開蓋後杯頂覆蓋 99% → **100%**(對照 99% → 88%,降 11 點);去掉整包剛體運動後各片形狀變化 中位 7~9 mm(對照 10~25 mm)。**副作用**:烘焙那一刻自穿 20 → 191(在四個角的收耳區),開蓋後仍 ~130;穿杯 0。原因調查中(見下)。

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
- wrap_vol 採 mode 6(同一幀,`--plastic_how frame`;`step` 為 mode 3)。

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
