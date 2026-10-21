# CREASE:surface 布「折痕記憶(塑性)」探針(2026-10-21,Isaac Sim 5.1 / omni.physx 107.3.26)

## 結論(一句)
**`omniphysics:restBendAngles` / `restAdjTriPairs` 在 PhysX 107.3 完全不被讀取**(runtime、重建、整場重載、重套 schema、建立時寫,兩種正負號,全部 = 對照);**能做出折痕記憶的唯一寫法是 `restShapePoints ← 折好的形狀 + restBendAnglesDefault = restShapeDefault` 再把 sim mesh `SetActive(False)→step→SetActive(True)` 重建**(回彈 48° → 0°)。surface 布重建後自碰撞**還在**(與 volume 線不同),但**只在 rest 裡層與層相距 > 2·restOffset(2 mm)時**;壓住時烘焙(rest 層距 1.65 mm)自穿 0 → 108。把 rest 用 `yieldrule.solve` 解成「角 = 目標、邊長 = 原長、疊層撐開 ≥ 3 mm」再寫回 → 壓住時烘焙自穿 0。
**可行性:技術上可行(降伏規則原型跑通、自碰撞可保住),但對 wrap_sim 現行材料(bend 4)沒有實際用處**:bend 4 的布本來就幾乎沒有彎曲回彈(無重力放手 4 s 只回 0.3°),有重力時不論有沒有折痕記憶翻片都直接倒下(bend 4 / 100 / 2000 都一樣);壓實後的 13~17 mm 回彈是自碰撞距離(EXPERIMENTS 08),不是彎曲。只有把 bend 調高(≥ 100)時折痕記憶才看得到差別。

## 檔案(腳本與輸出在 `work/crease/`)
| 檔 | 內容 |
|---|---|
| `ccommon.py` | 共用:wrap_sim 同款布(E 2e4、bend 4、surfaceThickness 4 mm、cont/rest 5/1 mm、selfCollision on、ldamp 0.2、edamp/bdamp 0.3、solver 64)、kinematic 桿、VtxXformAttachment(wrap_sim 結構)、二面角、S1(wrap_sim 同定義:邊穿面次數)|
| `probe_bend.py` | 探針 1:200×100 mm 布(5 mm 格),根部 10 mm 夾住,尖端桿沿 1/4 圓弧彎 90°(實際 75~88°),放手前 0.2 s 做 `--mode`,放手後量彎角 |
| `probe_sc.py` | 探針 2:200×100 mm 布對折、上層落在下層上、放手 1 s 後壓板壓到「上層頂 − 3 mm」;`--bake_at press` = 壓住時改 rest、再多壓 3 mm |
| `yieldrule.py` | 降伏規則 + rest 嵌入解算(scipy least_squares,稀疏 Jacobian,1089 點 0.5~2 s)|
| `probe_yield.py` | 探針 3:160×160 mm 四折(A 折 x、B 折 y)→ 放手觀察 2 s → 把最上片掀回 90° → 放手觀察 2 s |
| `render.py` | 錄下的頂點(`rec/*.npz`)→ mp4(斜視 3D + x-z 側視,多個並排)|
| `queue.sh` / `gpuwait.sh` | 依序跑、GPU < 27000 MiB 連續 30 s 才開、PhysX OOM 自動重跑 |
| `logs/*.log`、`rec/*.npz`、`videos/*.mp4` | 輸出(publish 時排除 `crease/*/`)|

## 1. 寫法與回彈角(`probe_bend.py`)
回彈 = 放手前彎角 − 放手後 4 s 彎角。彎角 = 尖端 20 mm 切線 − 根部 10 mm 切線(中線 y=0)。`grep -h RESULT crease/logs/bend_*.log`

### 1a. runtime 寫法(無重力,bend 2000 放大彈性才量得出差別)
| mode | 放手前 0.2 s 的動作 | 放手前 | 0.5 s | 2 s | 4 s | **回彈** | 生效? |
|---|---|---|---|---|---|---|---|
| 0 | 對照(不改)| 75.4° | 46.7° | 36.4° | 27.3° | **48.1°** | — |
| 1 | USD 寫 `restAdjTriPairs`(2340 對,int2 三角形索引)+ `restBendAngles`(度,= 當下二面角)| 75.4° | 46.7° | 36.5° | 27.2° | 48.2° | ✗ |
| 1 (sign −1) | 同上,角度 × −1 | 75.4° | 46.7° | 36.4° | 27.3° | 48.1° | ✗ |
| 2 | 1 + SetActive(False)→step→SetActive(True) | 75.3° | 46.7° | 36.4° | 27.2° | 48.1° | ✗ |
| 3 | 1 + `release_physics_objects()` + `force_load_physics_from_usd()` | 75.4° | 46.7° | 36.2° | 27.4° | 48.0° | ✗ |
| 9 | 1 + Remove/AddAppliedSchema `OmniPhysicsSurfaceDeformableSimAPI`(中間 step)| 75.4° | 46.7° | 36.2° | 27.4° | 48.0° | ✗ |
| 5 | `restShapePoints ← 當下` + `restBendAnglesDefault = restShapeDefault`,只寫 USD | 75.4° | 46.7° | 36.5° | 27.2° | 48.2° | ✗ |
| 6 | 只 SetActive 重建(rest 不改)| 75.4° | 46.8° | 36.5° | 27.5° | 47.9° | (重建本身無影響)|
| **4** | **5 + SetActive 重建** | 75.4° | 75.4° | 75.4° | 75.4° | **0.0°** | **✓** |
| 10 / 11 | disjoint rest(`restTriVtxIndices` 每三角形各 3 點;11 = 各三角形留在攤平原位只轉法線)+ 重建 | 75.4° | 75.4° | 75.4° | 75.4° | 0.0° | **✗ 假象**:PhysX 建不起 body(log `attachment ... cannot have 2 invalid actors`),頂點凍住;有重力版也一動不動 |
- bend 100 無重力:對照回彈 21.1°(79.6 → 58.5°),mode 4 **0.0°**。
- **bend 4(wrap_sim 現行值)無重力:對照只回彈 0.3°**(82.5 → 82.2°),mode 1 0.2° → 現行材料根本沒有可消的彎曲回彈。

### 1b. 建立時寫(不用桿,只有根部夾住,無重力,目標 90°)
| mode | 建立時 | bend 2000 | bend 4 |
|---|---|---|---|
| 7 | `restAdjTriPairs/restBendAngles` = 解析 1/4 圓的二面角(sign ±1)| 0.0° / 0.0°(平的;有重力版會下垂到 −50.7° ⇒ body 活著,陣列被忽略)| 0.0° |
| 8 | `restShapePoints` = 解析 1/4 圓 + `restShapeDefault` | 59.8°(自己彎起來)| 2.6° |

### 1c. 有重力(真實情況)
| bend | 對照 放手前 → 4 s | mode 4(折痕記憶)放手前 → 4 s |
|---|---|---|
| 4 | 85.8° → −0.6°(倒下)| 88.6° → −0.5°(一樣倒下)|
| 100 | 82.2° → −10.3° | 87.0° → −8.1° |
| 2000 | 75.1° → −48.8° | 77.1° → −42.8° |
⇒ 190 mm 懸臂:折痕記憶只消掉「彈回去」,撐不住自重;bend ≤ 2000 的布有沒有記憶都倒。

**屬性名 / 陣列**:`uniform token omniphysics:restBendAnglesDefault`(flatDefault / restShapeDefault)、`int2[] omniphysics:restAdjTriPairs`(相鄰三角形索引對,三角形順序 = faceVertexIndices)、`float[] omniphysics:restBendAngles`(度,[-180,180),長度 = pairs)、`point3f[] omniphysics:restShapePoints`、`int3[] omniphysics:restTriVtxIndices`。後兩者 + restShapeDefault 有效(但只在重建時讀,`restTriVtxIndices` 不能是 disjoint),前兩者 107.3 實測沒有任何作用。09-30 舊探針 `work/probe_crease.py`(m2/m4/m7 無效、m8 部分有效)結論一致。

## 2. 自碰撞(`probe_sc.py`,bend 4,有重力)
對折後上層自然落在下層上(層距 2.12 mm ≈ 2·restOffset),放手 1 s 後壓板壓到上層頂 − 3 mm。S1 = 布邊穿布面次數(wrap_sim 定義);「穿過頂點」= 下層頂點正上方最近的上層頂點 z 差 < 0 的數量(貼地時雜訊大,以 S1 為準)。`grep -h RESULT crease/logs/sc_*.log`

| 何時改 | mode | 改前層距 | S1 改後最大 / 結束 | 結束層距 中位 / 最小 | 自碰撞 |
|---|---|---|---|---|---|
| 放手前 0.2 s(層剛疊上)| 0 對照 | 2.12 mm | 2 / 0 | 1.65 / −0.38 mm | ✓ |
| 〃 | 1 restBendAngles(無效)| 2.12 | 0 / 0 | 1.64 / 1.59 | ✓(什麼都沒改)|
| 〃 | 6 只重建 | 2.12 | 2 / 2 | 1.63 / 1.21 | ✓ |
| 〃 | **4 restShapePoints + 重建** | 2.12 | **0 / 0** | 1.66 / 1.55 | **✓** |
| 〃 | 12 rest = yieldrule 解(疊層撐開 3 mm)+ 重建 | 2.12 | 9 / 9 | 1.66 / −0.34 | ✓(略差)|
| 壓住時(層距 1.65 mm)再多壓 3 mm | 0 對照 | 1.65 | 0 / 0 | 2.31 / 1.37 | ✓ |
| 〃 | **4 restShapePoints + 重建** | 1.65 | **108 / 82** | 1.77 / −0.56 | **✗** |
| 〃 | **12 rest = yieldrule 解(撐開 ≥ 3 mm)+ 重建** | 1.65 | **0 / 0** | 2.17 / 0.88 | **✓** |
- 機制:`physxDeformableBody:selfCollisionFilterDistance`(預設 −inf = 模擬自選,下限 2·restOffset = 2 mm)以 **rest 形狀**的距離決定哪些頂點/三角形不互撞。rest 裡兩層 < 2 mm → 那些對被過濾 → 互穿。volume 線(PLASTIC.md)重建後自碰撞全失效;surface 線**重建本身不會**(mode 6、probe_yield `--yield 2` 45 次重建 S1 全 0)。
- 所以「改 rest」的安全做法 = rest 層距必須 > 2·restOffset;實際布疊起來剛好停在 2·restOffset(2.1 mm),一壓就低於 → 一定要在解 rest 時把層撐開(`yieldrule.solve(sep=3 mm)`)。

## 3. 降伏規則原型(`probe_yield.py`)
規則:每 0.25 s 掃 3136 條內部邊,|當下角 − 靜止角| > 20° 的邊 靜止角 += 0.5 ×(當下 − 靜止);有邊降伏 → 解 rest 嵌入(邊長殘差權重 10、角度、疊層撐開 ≥ sep,`commit` 把靜止角改成解出來實際做得到的角)→ 寫 `restShapePoints + restShapeDefault` → SetActive 重建(桿的 attachment 會跟著重建,但**剛建 attachment 的那一步不能重建**,否則該 attachment 永久 invalid —— v2 的 C 段就是這樣掀不起來)。
`grep -h RESULT crease/logs/yield_*_f6.log`

| 次 | bend | 規則 | 四折放手 → +2 s 位移 RMS / max | 頂高 放手 → +2 s | 四折 bbox | 掀到 90° 放手 → 2 s 後 flap 角 | S1 全程最大 | 重建 / 解算 |
|---|---|---|---|---|---|---|---|---|
| y0 | 4 | 對照(B/C 抓取時刻早 0.05 s,其餘同)| 3.40 / 8.69 mm | 18.6 → 19.5 mm | 86×82×17.6 | 89.9° → **6.8°**(倒向攤平)| 0 | 0 |
| y2 | 4 | 只重建(rest 不改)| 3.50 / 9.40 | 19.8 → 19.7 | 86×84×18.8 | 88.9° → 4.5° | 0 | 45 / – |
| y1 | 4 | 20°、λ 0.5、sep 3 | 2.09 / 9.18 | 22.3 → 21.9 | 84×80×21.3 | 91.8° → **149.8°**(倒回蓋上)| **32** | 42 / 62 s |
| y1 | 4 | 20°、λ 0.5、sep 5 | 2.14 / 7.70 | 18.6 → 17.9 | 86×85×17.6 | 89.7° → 39.3° | **2** | 43 / 81 s |
| y0 | 2000 | 對照 | **12.81 / 33.51** | 41.0 → 37.8 | **175×115×49.6**(撐開)| 87.4° → 57.9° | 38 | 0 |
| y1 | 2000 | 20°、λ 0.5、sep 3 | **5.17 / 24.74** | 30.8 → 36.2 | **105×93×30.1** | 76.5° → **168.6°**(倒回蓋上)| 11 | 24 / 67 s |
| y1 | 2000 | 20°、λ 0.5、sep 5 | 5.64 / 23.25 | 30.5 → 33.9 | 105×94×29.7 | 80.9° → 168.2° | 11 | 31 / 84 s |
| y1 | 2000 | 8°、λ 0.5、sep 3 | 5.76 / 27.27 | 27.7 → 29.9 | 92×92×26.7 | 84.8° → 171.0° | 16 | 38 / 84 s |
- **bend 2000 才看得到塑性**:對照四折完會自己撐開成 175×115×50 mm(彈性要回平),規則版維持 ~105×93×30 mm、放手後位移 RMS 12.8 → 5.2 mm。
- bend 4:對照本來就不彈(位移 RMS 3.4 mm,主要是重力攤平),規則版差異小(2.1 mm)。
- **掀開放手後「垂不垂著」**:都不會直立(bend ≤ 2000 撐不住 80 mm 雙層片),差別在倒向:對照倒向攤平(5~58°),規則版倒回原本折起的那側(150~171°)= 原折痕記憶還在、掀開那 1.5 s 的新彎曲沒有被吃掉。原因:新彎曲分散在多條邊上,單邊角度變化不超過降伏角(20°、甚至 8° 也一樣)→「逐邊角度」降伏規則對解析度敏感,應改用曲率(角 / 邊長)或沿折線累積角。
- 自碰撞:sep 5 mm 時 S1 2(≈ 對照 0);sep 3 mm 時 32(bend 4)/ 11(bend 2000,對照本身 38)。
- 代價:每次重建速度歸零(y2 顯示對形狀影響小);解 rest 1~2 s / 次 → 0.25 s 週期約慢 2 倍(wall 56 → 115~136 s)。

## 4. 要看起來 4 mm 厚(不用實作)
surface 布是零厚度中面,`surfaceThickness` 只進彎曲/質量,碰撞厚度是 `restOffset`(層與層停在 2·restOffset)。外觀做法:
1. **視覺殼(offset mesh)**:另建一個只渲染的 Mesh(不掛物理),每幀從 sim mesh 頂點 `x` 與面積加權頂點法線 `n` 生成上殼 `x + n·t/2`、下殼 `x − n·t/2`,邊界邊補一圈側條(quad strip)封口;拓樸固定只更新 points(Python 每幀 `Vt.Vec3fArray`,或 Warp kernel / OmniGraph 寫 Fabric 更快)。原 sim mesh 設 invisible(或 purpose=guide)。
2. 折痕處內殼會自交(曲率半徑 < t/2):offset 量用 `min(t/2, 0.9·局部曲率半徑)` 夾住,或內側殼改用「頂點 → 兩層中點」的距離限制。
3. 層與層之間要看起來不穿:視覺厚度要 ≤ 實際層距 = 2·restOffset。現行 rest 1 mm → 層距 2.1 mm,要顯示 4 mm 就得把 restOffset 調到 ~2 mm(contactOffset > restOffset,例如 3 mm),否則兩層殼會互相插入。
4. 便宜替代:只用材質(雙面 + 邊緣法線貼圖)假裝厚度,不改幾何;遠景夠用、近看折邊會穿幫。

## 可行 / 不可行
| 項目 | 結果 |
|---|---|
| `restBendAngles` 陣列(任何時機、任何重建方式)| **不可行**(PhysX 107.3 不讀)|
| `restShapePoints + restShapeDefault + SetActive 重建` 做折痕記憶 | **可行**(回彈 48° → 0°,attachment 與剛體碰撞照常)|
| disjoint rest(`restTriVtxIndices` 3T 點)| **不可行**(body 建不起來)|
| 改 rest 後自碰撞 | **有條件可行**:rest 裡層距 > 2·restOffset;用 `yieldrule.solve(sep ≥ 3~5 mm)` 撐開 |
| 降伏規則(逐邊,0.25 s)| **原型可跑**;bend 2000 時四折形狀保持明顯變好;bend 4 時沒差;逐邊閾值對分散彎曲不敏感 |
| 對現行 wrap(bend 4)壓實回彈 13~17 mm | **不會改善**(回彈來源是自碰撞距離,不是彎曲)|

## 若要接回包材流程(下一步)
1. 先決定材料:要折痕記憶有意義,bend 至少 ~100(本探針 100 已有 21° 回彈可消);bend 4 不需要這套。
2. 事件式烘焙(比週期式便宜):wrap_sim 每一折的 hold 錨放手前呼叫一次 `YieldRule.step + solve(sep=0.003~0.005)` → 寫 rest → SetActive 重建;放手 step 要和建 attachment 的 step 錯開 ≥ 3 步。
3. 量:每次烘焙前後 S1、`selfCollisionFilterDistance` 明確設 2·restOffset;烘焙後 0.5 / 2 s 層距;杯子 / 箱子(剛體)接觸在重建那一步會失去一步,要看杯子位移。
4. 降伏規則改用「曲率」(二面角 / 對邊高)或「沿折線累積角」當判準,並把 λ、閾值掃一輪(本探針只跑 20° / 8°、λ 0.5)。
5. volume 正式線(FINAL_PLAN)不受影響;本結果只對 surface 線成立。

## 重現 / 影片
```
cd work
crease/queue.sh "probe_bend.py --mode 0 --bend 2000" "probe_bend.py --mode 4 --bend 2000"   # 其餘 mode 見表
crease/queue.sh "probe_sc.py --mode 4 --bake_at press --press2_mm 3" "probe_sc.py --mode 12 --bake_at press --press2_mm 3"
crease/queue.sh "probe_yield.py --yield 0 --bend 2000" "probe_yield.py --yield 1 --bend 2000"
grep -h RESULT crease/logs/*.log
# 影片(CPU,matplotlib):
python3 crease/render.py crease/rec/bend_m0_g0_s+1_b2000.npz crease/rec/bend_m1_g0_s+1_b2000.npz crease/rec/bend_m2_g0_s+1_b2000.npz crease/rec/bend_m4_g0_s+1_b2000.npz --out crease/videos/p1_bend2000_m0_m1_m2_m4.mp4 --every 2
```
| 影片(`work/crease/videos/`)| 內容 |
|---|---|
| `p1_bend2000_m0_m1_m2_m4.mp4` | 探針 1:對照 / restBendAngles / restBendAngles+重建 / restShapePoints+重建(只有第 4 格不回彈)|
| `p1_bend4_g0ctrl_g1ctrl_g1m4.mp4` | bend 4:無重力對照不回彈;有重力對照、有記憶都倒下 |
| `p1_bend2000_gravity_m0_vs_m4.mp4` | bend 2000 有重力:有沒有記憶都倒 |
| `p1_create_m7_rb_vs_m8_restshape.mp4` | 建立時:restBendAngles 平的 / restShapePoints 自己彎起 |
| `p2_selfcoll_m0_m4_m6.mp4` | 層剛疊上時改 rest:三者都不穿 |
| `p2_selfcoll_bake_while_pressed_m0_m4_m12.mp4` | 壓住時改 rest:對照 0 / restShapePoints 108 / 撐開 rest 0 |
| `p3_yield_bend4_ctrl_y1s3_y1s5_rebuildonly.mp4` | 四折 + 掀開,bend 4:對照 / 規則 sep3 / 規則 sep5 / 只重建 |
| `p3_yield_bend2000_ctrl_vs_y1.mp4` | 四折 + 掀開,bend 2000:對照撐開 vs 規則保持 |
