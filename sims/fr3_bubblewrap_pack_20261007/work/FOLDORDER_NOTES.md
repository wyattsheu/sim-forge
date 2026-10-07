# FOLDORDER_NOTES — `wrap_sim.py` 折序單一來源 + 杯子方位矩陣 patch 說明

2026-09-30。**只產 patch,沒有套用到 `work/wrap_sim.py`**(該檔正被多個模擬 agent 使用)。

| 檔案 | 說明 |
|---|---|
| `work/foldorder.patch` | `diff -u wrap_sim.py <改過的副本>`,14 個 hunk,+81/−33 行(含註解) |
| `work/FOLDORDER_NOTES.md` | 本檔 |
| patch 的基準 | `work/wrap_sim.py` **md5 `8b8dfa3e5da80b7eb46bebe3fce158a9`**(mtime 2026-09-30 02:50:46,1627 行)。含當天新加的 `--cont --rest --self_filter --pair_freq --col_iter_mult --ccd --hold_mm --no_anchor --tip_over_mm`,以及 02:44 / 02:50 另一位 agent 剛加的 `--release_after --no_hold`(含 02:50 把放手的錨點方塊改成直接 `RemovePrim`);**這些旗標與相關程式碼一行都沒動** |

> 基準在我工作期間被改過兩次:第一版 patch 是對 02:13 版(md5 `0894780f…`)做的;02:44 另一位 agent 加了 `--release_after` / `--no_hold`(6 個 hunk),其中 `if a.no_hold:` 兩行剛好插在我 stage2 hunk 的上下文裡,所以我把全部修改 rebase 到 02:44 版;02:50 同一區塊又改了 2 行(放手的方塊改成 `RemovePrim`),只讓我的 hunk 13/14 位移 2 行,再 rebase 一次到 02:50 版重新產 patch、重跑全部驗證(§5)。**這支檔案顯然還在被改**:套用前先 `md5sum` + `--dry-run`;`patch` 對純位移有容忍,每個 hunk 都很小,真失敗的那個照 §2 手動重放即可。

套用方式(等其他 agent 的對照實驗跑完再做,或先套到副本):

```bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/work
md5sum wrap_sim.py                          # 期望 8b8dfa3e5da80b7eb46bebe3fce158a9(不同就先看 --dry-run 有沒有 FAILED)
patch -p0 --dry-run < foldorder.patch && patch -p0 < foldorder.patch
# 或套到副本:cp wrap_sim.py wrap_sim_fo.py && patch wrap_sim_fo.py < foldorder.patch
python3 ../scripts/selfcheck.py            # C 段應全 PASS(selfcheck 讀的是 scripts/wrap_sim.py,交付時記得同步)
```

---

## 1. 目標與結論

需求(`TASK_INTERN.md`、`ORIENTATION_AND_SIZE.md`):前=+y、後=−y、右=+x、左=−x。PPT 開箱是**前後(±y)先開、左右(±x)後開**,先開的一定是外層,所以包材外層必須是 ±y ⇒ **先折 ±x、後折 ±y**。杯子橫放中央、**杯口朝 +y、杯耳朝 +x**。

patch 做了三件事:

1. **折序只剩一個來源** `FOLD_ORDER = ["xp", "xn", "yp", "yn"]`(檔頭),`STAGE2_SIDES`、`WORDER`、`ORD_`、`UORDER`、`ORDER`、`_ORD` 全部由它衍生;三個 `assert` 守住 UORDER 反序、四邊各一次、前後兩折各自同軸。
2. **stage2 抓「還貼地的邊」不再寫死 x 軸**,改由 `STAGE2_SIDES` 決定軸(`_s2ax`);另加 `floor_edges.json` 鍵名守衛(舊折序量的 json 會被直接擋下,不會再安靜地讓 y 邊沒折到)。
3. **杯子方位矩陣 `_Rm`**(純旋轉 det=+1),讓最終杯口 +y、杯耳 +x。**這一項我沒有照任務字面做**,原因見 §3 —— 從 `mug.stl` 網格實測,selfcheck 註解假設的「原始 = 杯口 +y / 杯耳 −x」在這支檔案的轉法下**不成立**,照字面套會得到杯口 +x。

另外修了一個新順序才會咬到的潛在 bug(角落頂點分邊不一致,§2.4)。

---

## 2. 改了哪些行、為什麼

行號寫法:「02:13 版 / 02:44 版 → patch 後」。02:44 版相對 02:13 版的位移:≥189 行 +8、≥616 行 +9、≥751 行 +11、≥1031 行 +12、≥1230 行 +23、≥1293 行 +24;**02:50 版(現行)= 02:44 版在 ≥1244 行再 +2**。「patch 後」行號以 02:50 版基準為準。

### 2.1 檔頭:折序單一來源(196 / 204 行之後 → patch 後 206~218)

```python
FOLD_ORDER = ["xp", "xn", "yp", "yn"]
STAGE2_SIDES = FOLD_ORDER[2:]                 # 第二段(--stage2)折的是後兩折
UORDER = ["yn", "yp", "xn", "xp"]             # = FOLD_ORDER 反序(selfcheck 用 regex 抓字面值,所以寫死、由下一行守住)
assert UORDER == list(reversed(FOLD_ORDER))
assert sorted(FOLD_ORDER) == ["xn", "xp", "yn", "yp"]
assert FOLD_ORDER[0][0] == FOLD_ORDER[1][0] and FOLD_ORDER[2][0] == FOLD_ORDER[3][0]
```

放在 `parse_known_args()` 之後、`from isaacsim import SimulationApp` 之前:純設定,不需要 Isaac,而且第一次用到它的地方(錨點挑選)在後面。`UORDER` 寫成字面值是因為 selfcheck 用 `UORDER = \[([^\]]+)\]` 抓;`assert` 保證改了 `FOLD_ORDER` 忘了改它會在啟動時就炸,而不是靜靜地開錯順序。

### 2.2 杯子躺平 + `_Rm`(296~306 / 304~314 → patch 後 318~341)

```python
Rz = lambda t: ...
V = V @ Ry(-np.pi/2).T @ Rx(np.pi/2).T @ Rz(-np.pi/2).T      # 基準姿態:杯口 +y、杯耳 −x
_Rm = np.array([[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]])
V = V @ _Rm.T
V -= (V.max(0) + V.min(0)) / 2.0          # 置中在所有旋轉之後
ME = V.max(0) - V.min(0); ...
```

- 套在 `ME = V.max(0) - V.min(0)` 之前,所以佔位塊 A/B、折線 CX/CY、折邊長全部自動跟著新方位算。
- `_Rm` 寫成一行、`np.array([[` 開頭、`]])` 結尾,selfcheck 的 `re.S` 非貪婪 regex 才抓得乾淨(後面若加 `dtype=` 會讓它一路吃到檔案後段的 `]])`)。
- 多了一步 `Rz(-90)`:見 §3。

### 2.3 `--init_npz` 路徑(526~527 / 534~535 → patch 後 561~565,只加註解)

`_mp0 = np.load(a.init_npz)["mug"].mean(0)` 只拿 npz 裡 `mug`(世界座標頂點 `V @ Rm.T + 平移`)的**平均當平移量**;杯子 prim 沒有 rotate op,方位完全由每一段各自在載入 STL 時套 `_Rm` 到 `V` 決定 ⇒ **不會轉兩次**。`traj.npz` 存的 `mugrest=V` 也是套過 `_Rm` 的靜止頂點,配 `mugpose`(單位四元數 + 平移)離線重建仍一致。代價:**patch 前產生的所有 npz 都不能再餵 `--init_npz`**(那時的布是包在 杯口 −x / 杯耳 −y 的杯子外面)。

### 2.4 錨點挑選(722~800 / 731~811 → patch 後 768~853)

| 02:13 / 02:44 行號 | 原本 | 改成 | 理由 |
|---|---|---|---|
| 722 / 731 之後 | — | `SIDEPICK = {}` | 記下挑點時每個頂點被分到哪一邊(見下) |
| 726~727 / 735~736 | 註解「第一個打開的是最後折的 x 邊…第二個是先折的 y 邊」 | 改寫成 `FOLD_ORDER[2:]` / `FOLD_ORDER[:2]` | 註解也寫死了順序 |
| 734~741 / 743~750 | `if sd_ in ("yp","yn"): 整條不含角落 / else: 只留 FLOORE` | `if sd_ in FOLD_ORDER[:2]: 整條不含角落 / else: 只留 FLOORE`,外圈判斷泛化成 `FLAT[vi_][ax_]` | 「y 整條、x 只抓貼地段」其實是「**先折**整條、**後折**只抓貼地段」,是順序語意 |
| 752 / 763 | `abs(abs(FLAT[v, 0]) - WX/2) < 1e-6` | `_s2ax = 0 if STAGE2_SIDES[0] in ("xp","xn") else 1; _s2w = WX if _s2ax == 0 else WY;` `abs(abs(FLAT[v, _s2ax]) - _s2w/2) < 1e-6` | stage2 寫死抓 x 外圈;新順序後兩折是 y |
| 755 / 766 | `SIDE2[v] = "xp" if FLAT[v,0] > 0 else "xn"` | `"xy"[_s2ax] + ("p" if FLAT[v,_s2ax] > 0 else "n")` + `assert ⊆ STAGE2_SIDES` | 同上 |
| 757~759 / 768~770 | log「還貼地的那條邊」 | 印出 `yp/yn` | 看 log 就知道抓的是哪一軸 |
| 764 / 775 | `ORD_ = ["yp","yn","xp","xn"][:…]` | `ORD_ = FOLD_ORDER[:max(1, min(4, a.wrap_n))]` | 順序 |
| 783~786 / 794~797 | `if ax_ == 1 and 角落: continue` / `if ax_ == 0 and FLOORE…: continue` | `if sd_ in FOLD_ORDER[:2] and 角落` / `if sd_ in FOLD_ORDER[2:] and FLOORE…` | 「y 邊不含角落(角落被兩折同時牽動)」是**先折**的規則;「x 邊只留貼地段」是**後折**的規則。都是順序語意,不是軸 |
| 787、799 / 798、810 | `keep.append(...)` / `pick.append(...)` | 同時 `SIDEPICK[vi] = sd_` | 見下 |

**角落分邊不一致(新幾何才會咬到的 bug)**:挑點時用「超出折線多少」分邊(`sd_`,角落歸折線較近的那一軸),但原 848~849 / 859~860 行建 `PULLS` 時又用 `|x| >= |y|` 重分一次(角落一律判 x)。舊幾何 ME=(107,133) ⇒ CX=71.5 < CY=84.6,角落被 `sd_` 分到 x、剛好也是後折邊,兩種分法一致;**杯子轉正後 ME=(133,107) ⇒ CX=84.6 > CY=71.5,角落被分到後折的 y 邊,卻在 PULLS 被改判成 x**,錨點就跟著 x 那一折走(第一折)、還一律施力。改法:PULLS 分邊時 `elif int(vi) in SIDEPICK: _side = SIDEPICK[vi]`(844~849 / 855~860 → patch 後 897~909),`--unfold`/`anchors==4` 等沒經過挑點的路徑維持原本的 `|x|>=|y|`,行為不變。

### 2.5 `floor_edges.json` 守衛(707~710 / 716~719 → patch 後 745~754,新增)

```python
if set(FLOORE) != set(STAGE2_SIDES):
    raise SystemExit("★ %s 的鍵 %s 不是後兩折 %s —— 這份是舊折序量的,要重量" % ...)
```

沒有這段,舊 json(鍵 `xp`/`xn`)配新折序會讓 `FLOORE.get("yp", [])` 全空 ⇒ 後兩折**一個錨點都不建**,y 邊安靜地沒折到 —— 正是 selfcheck 註解記的歷史事故。

### 2.6 `WORDER`(1012~1013 / 1023~1024 → patch 後 1072~1073)

```python
WORDER = (STAGE2_SIDES if a.stage2 else FOLD_ORDER[:max(1, min(4, a.wrap_n))])
```

原本 stage2 寫死 `["xp","xn"]` 是因為那時後兩折是 x;現在是 `FOLD_ORDER[2:]`。`lay=(2 if a.stage2 else 0) + WORDER.index(side)`(1231 / 1254 行)在新順序下 4 折 = 0,1,2,3、stage2 = 2,3,測過(§5 [1])。

### 2.7 `drive()` 內(1119~1122、1222、1236 / 1131~1134、1234、1259 → patch 後 1180~1182、1282、1310)

| 02:13 / 02:44 行號 | 改法 |
|---|---|
| 1122 / 1134 `UORDER = ["xn","xp","yn","yp"]` | 刪掉,用檔頭的 `UORDER`(反序字面值 + assert);註解改寫 |
| 1222 / 1234 `p_["side"] in ("yp","yn")` | `p_["side"] in FOLD_ORDER[:2]`(先折的兩邊一律施力;後折只驅動還貼地的) |
| 1236 / 1259 `ORDER = ["yp","yn","xp","xn"]`(`--unfold`) | `ORDER = UORDER` —— **注意這裡我選反序不是 FOLD_ORDER**:`--unfold` 是「攤開 = 打開」,原註解寫「順序照 PPT」,PPT 是前後先開 ⇒ 折序的反序。舊字面值的軸序 y→x 跟 UORDER 一樣,只是同軸內正負對調(yp,yn → yn,yp),對 fold_init 的解析折疊幾何沒有層次差別,行為幾乎不變。若你希望它跟 FOLD_ORDER 同向,改這一行即可 |

### 2.8 字幕(1413 / 1437 → patch 後 1488)

`_ORD = ["yp","yn","xp","xn"]` → `_ORD = UORDER`,與 2.7 的 `--unfold` 順序同源。

---

## 3. 杯子方位:為什麼 `_Rm` 前面多了一步 `Rz(-90)`

任務指定 `_Rm = [[-1,0,0],[0,1,0],[0,0,-1]]`(繞 y 轉 180°),依據是 selfcheck 註解「原始網格(套 _Rm 之前)是 杯口 +y / 杯耳 −x」。我用純 numpy 解析 binary STL,**照原檔 297~304 行的轉法**(`Ry(-90)·Rx(90)`)重跑,再從網格本身量:

- 判杯軸/杯口:三軸各取兩端 3 mm 薄片,端面點到中心的徑向距離 `r_min/r_max`。杯口與底足是「環」(r_min ≈ r_max),封底是「盤」(r_min ≈ 0);杯口環比底足環大。
- 判杯耳:橫截面上超出杯身半徑 1.08 倍的點的平均方向(另用 ASCII 三視圖投影目視確認)。

| 轉法 | ME (mm) | 杯軸 | 杯口 | 杯耳 |
|---|---|---|---|---|
| raw STL | 133.3 × 92.6 × 107.0 | z | +z | +x(直立杯,建模慣例) |
| A 原檔 `Ry(-90)·Rx(90)` | 107.0 × 133.3 × 92.6 | **x** | **−x**(Ø90 環) | **−y** |
| B = A·`Rz(-90)`(patch 後「套 _Rm 前」) | 133.3 × 107.0 × 92.6 | y | **+y** | **−x** ← selfcheck 註解的前提,在 B 成立 |
| C = B·`_Rm`(patch 後最終) | 133.3 × 107.0 × 92.6 | y | **+y** | **+x** ← 需求 ✅ |
| D = A·`_Rm`(任務字面作法,對照) | 107.0 × 133.3 × 92.6 | x | **+x** ❌ | −y ❌ |

所以在這支檔案上直接套 `_Rm` 會讓 selfcheck **全過、杯口卻在 +x**(selfcheck 只驗矩陣代數,不碰網格)。selfcheck 的 `_Rm` 檢查把「原始 = 杯口 +y / 杯耳 −x」寫死,能同時滿足它和物理正確的唯一作法,就是讓程式裡「套 `_Rm` 前」的姿態真的等於那個前提:躺平時多轉一步 `Rz(-90)`(B),再套 `Ry(180)`(C)。三步合成恰好 = `Rx(-90)`(直立杯 杯口 +z、杯耳 +x → 杯口 +y、杯耳 +x),自洽。

`det(_Rm) = +1.000`、`_Rm·_Rmᵀ = I`、`_Rm@(0,1,0) = (0,1,0)`、`_Rm@(-1,0,0) = (1,0,0)`。量測腳本:`/tmp/claude-0/-isaac-sim-test-scripts-manip-fr3-handoff-20260929/c7e55632-bf8d-46a1-89a0-934334fed54b/scratchpad/verify_mug_pose.py`(純 numpy,不需 Isaac/trimesh;`exit 0` 代表 B、C 都符合預期),建議收進 `scripts/`,並在最終 npz 上用同一套「環/盤」法再量一次(`CHANGES_TO_VERIFY.md` B2 要的就是這個)。

副作用:**杯子的長邊 133 mm 從 y 轉到 x**(ME 由 107×133 變 133×107)。布的邊長不變(仍 586 mm,`edge_report.py` 的 `W = 0.586` 照用),但包裹的長短邊會對調,`--press6` 要重訂(§4)。

---

## 4. 套用後要重跑 / 重量的東西(按順序)

1. **c1 兩折**(`--wrapsim --wrap_edge --wrap_n 2 …`):log 應出現 `wrap xp` → `wrap xn`;`edge_report.py` 看 ±x 邊收到 x≈0、±y 邊仍在 ±293。
2. **重量 `floor_edges.json`**(它記的是「後兩折那條邊上還貼地的頂點」,舊檔的鍵是 `xp/xn`、記的是 x 邊;新順序要記 **y 邊**,鍵 `yp/yn`,否則 §2.5 的守衛會直接把 `--unbox` / 帶 `--floor_edges` 的四折單跑擋下):

   ```python
   import numpy as np, json
   S = np.load("out_c1/wrap.npz")["sheet"]; r = int(round(len(S)**0.5))
   i, j = np.arange(len(S)) % r, np.arange(len(S)) // r
   fe = {"yp": [int(v) for v in np.where((j == r-1) & (S[:, 2] < 0.015))[0]],
         "yn": [int(v) for v in np.where((j == 0)   & (S[:, 2] < 0.015))[0]]}
   json.dump(fe, open("floor_edges.json", "w"))
   ```
   (`0.015` = `Z_FLOOR`。`--stage2` 本身不用這個檔,它直接看 `--init_npz` 的實際 z;用到的是 `--unbox` 與不分段的四折 `--wrapsim --floor_edges`。)
3. **c2 stage2**:log 應有「還貼地(z<15mm)的 **yp/yn** 邊 N 個」與 `wrap yp` → `wrap yn`。
4. **c3 六面壓實 `--press6 W,L,H`**:`W` 是 **x** 方向(板 `xp/xn`)、`L` 是 **y**(板 `yp/yn`);內腔 264(x) × 224(y)。杯子長邊現在沿 x、外層是 y 折,包裹自然 bbox 會跟舊的不同 —— 先不帶 `--press6` 跑一次(或直接讀 c2 最後的「布 bbox」),再照 `ADAPTING.md` 往下壓 10~15% 訂 W、L,確認 `W < 264 且 L < 224`、長邊沒對調(selfcheck D 段會查 `chain3.sh` 裡的值,目前 `250,210,115` 是為舊方位挑的,**不要沿用**)。
5. **入箱 + 關蓋**、**`--unbox`**(要用新的 `floor_edges.json` 和新的 `packed_in_box.npz`)、**提杯測試 `--lift_mug`**(`CHANGES_TO_VERIFY.md` B12 的 0.915 是舊折序的數字)。
6. `states/*.npz`(`folded_4sides / packed_pressed / packed_in_box / lifted`)、`videos/1~4` 全部要重產;`scripts/wrap_sim.py`(交付副本)要同步。
7. 文件:`ORIENTATION_AND_SIZE.md` §3(未驗 → 已套用並實測)/ §4(已知不符 → 已改 x 先)、`TASK_INTERN.md` 現況、`README.md` 的 press6 值、`CHECKLIST` S0/S2/S5。

---

## 5. 驗證結果(全部純 CPU,不開 Isaac;rebase 到 02:50 版之後全部重跑)

| 項目 | 結果 |
|---|---|
| `python3 -c "import ast; ast.parse(...)"` | OK |
| `pyflakes 3.2.0` | 0 warnings(基準檔也是 0) |
| selfcheck C 段(`scripts/selfcheck.py` 77~124 行逐字抽出,對改過的檔跑;腳本 `…/scratchpad/selfcheck_C.py`) | **12 PASS / 0 FAIL**;對基準檔跑是 2 PASS / 8 FAIL(對照) |
| selfcheck 三個 regex(`FOLD_ORDER = [`、`UORDER = [`、`_Rm = np.array([[`) | 各恰好命中 1 次,第一筆就是定義行(patch 後 212 / 214 / 336 行) |
| `_Rm`:det、正交、兩向量 | det=+1.000、`_Rm·_Rmᵀ=I`、(0,1,0)→(0,1,0)、(−1,0,0)→(1,0,0) |
| 杯子方位從 STL 實測(§3 表) | B:杯口 +y/杯耳 −x ✅;C:杯口 +y/杯耳 +x ✅;D(字面作法):杯口 +x ❌ |
| 邏輯測試(`…/scratchpad/test_foldorder_logic.py`:從改過的檔**抽出真正的程式片段** exec,用新 ME 幾何跑) | 6 段 25 項全 PASS:衍生表/WORDER/lay;c1 只建 x 兩邊 66 點不含角落;四折單跑 136/136 外緣、角落歸 y 且 PULLS 分邊 = 挑點分邊(對照:舊 `|x|>=|y|` 會判成 x);stage2 `_s2ax=1`、貼地邊 = y 外圈 70 點、hold 只來自杯頂上方;unbox INFOLD = x 外圈−角落 ∪ floor_edges;舊 json `{xp,xn}` 被 SystemExit 擋下、新 json 接受。**這組測試在 rebase 時抓到一次真錯**(失敗的 hunk 6 其實橫跨 stage2 與 `ORD_` 兩處,我只重放了前者,`ORD_` 一度變回字面值 → selfcheck 11/12、測試 [2] 兩項 FAIL;補回後全過) |
| rebase 完整性 | 「我的檔(02:13 基準)」→「我的檔(02:44 基準)」的 diff 恰好只有另一位 agent 的 6 個 hunk,我改的行零差異;02:44 → 02:50 同樣只有對方那 2 行 |
| patch | 14 hunk(+81/−33),對 02:50 版副本 `patch -p0` 零位移套上,實套後與改過的檔逐 byte 相同;`work/wrap_sim.py` 本體我沒動過(md5 變化來自另一位 agent) |

---

## 6. 全檔 `"yp"/"yn"/"xp"/"xn"` 出現處逐一判定

行號欄:02:13 版 / 02:44 版;02:50 版(現行)在 ≥1244 行再 +2,受影響的列在括號另標。

| 行號 | 原句(節錄) | 改/不改 | 理由 |
|---|---|---|---|
| 75, 77~79 / 同 | help:「下層 fx 先關、上層 fy 後蓋上」/「上層 fy 先、下層 fx 後」 | 不改 | 紙箱**蓋子**的開關順序(上蓋 ±y 外層先開),本來就符合 PPT,與包材折序無關 |
| 733 / 742 | `sd_ = ("yp" if fy_ > 0 else "yn") if sy_ >= sx_ else ("xp" …)`(unbox) | 不改(結果存入 `SIDEPICK`) | 方向語意:依超出折線多少決定頂點屬於哪一邊 |
| 734 / 743 | `if sd_ in ("yp", "yn"):` | **改** → `if sd_ in FOLD_ORDER[:2]:` | 順序語意(先折整條 / 後折只抓貼地段) |
| 735, 739 / 744, 748 | `abs(abs(FLAT[vi_][1]) - WY/2)` / `abs(abs(FLAT[vi_][0]) - WX/2)` | **改**(合併成 `FLAT[vi_][ax_]`) | 軸語意,但綁在順序分支裡,泛化後兩支共用 |
| 752 / 763 | `abs(abs(FLAT[v, 0]) - WX/2) < 1e-6`(stage2) | **改** → `FLAT[v, _s2ax]`、`_s2w/2` | 順序語意:抓「後兩折那一軸」 |
| 755 / 766 | `SIDE2[int(v)] = "xp" if FLAT[v, 0] > 0 else "xn"` | **改** → `"xy"[_s2ax] + p/n` | 同上 |
| 764 / 775 | `ORD_ = ["yp", "yn", "xp", "xn"][:…]` | **改** → `FOLD_ORDER[:…]` | 順序 |
| 769 / 780 | `sd_ = …`(wrapsim) | 不改(結果存入 `SIDEPICK`) | 方向語意 |
| 774 / 785 | `ax_ = 1 if sd_ in ("yp", "yn") else 0` | 不改 | 軸語意 |
| 783 / 794 | `if ax_ == 1 and abs(FLAT[vi_][0]) > WX/2 - 1e-6: continue  # y 邊不含角落` | **改** → `if sd_ in FOLD_ORDER[:2] and abs(FLAT[vi_][1-ax_]) > …` | 順序語意:**先折**的邊不含角落 |
| 785 / 796 | `if ax_ == 0 and FLOORE is not None and … not in FLOORE.get(sd_)` | **改** → `if sd_ in FOLD_ORDER[2:] and FLOORE …` | 順序語意:**後折**的邊只留貼地段 |
| 795~796 / 806~807 | `ax_ = 1 if sd_ in ("yp","yn")`;`sg_ = 1 if sd_ in ("yp","xp")` | 不改 | 軸 / 正負 |
| 848~849 / 859~860 | `if abs(_fx) >= abs(_fy): _side = "xp"/"xn" else "yp"/"yn"` | 字面不改,前面插入 `elif int(vi) in SIDEPICK` | 方向語意;但角落與挑點分邊不一致,新幾何會咬到(§2.4) |
| 850 / 861 | `_axs = 1 if _side in ("yp", "yn") else 0` | 不改 | 軸 |
| 866~867 / 877~878 | press6 五片板 `("xp", 0, +1), ("xn", 0, -1), ("yp", 1, +1), ("yn", 1, -1)` | 不改 | 軸語意(板名 = 軸) |
| 1012~1013 / 1023~1024 | `WORDER = (["xp","xn"] if a.stage2 else ["yp","yn","xp","xn"][:…])` | **改** → `STAGE2_SIDES if a.stage2 else FOLD_ORDER[:…]` | 順序;stage2 那半原本寫死 x 是因為當時後兩折是 x |
| 1041~1042 / 1053~1054 | `wrap_arc_from`:`ax = 0 if side in ("xp","xn")`;`sgn = … ("xp","yp")` | 不改 | 軸 / 正負 |
| 1076~1077 / 1088~1089 | `wrap_arc`:同上 | 不改 | 軸 / 正負 |
| 1115 / 1127 | `k_ = 0 if L["nm"] in ("fyp", "fyn") else 1  # fy 先` | 不改 | 紙箱蓋子(字串是 fyp/fyn),上蓋先開,正確 |
| 1120~1122 / 1132~1134 | 註解 + `UORDER = ["xn", "xp", "yn", "yp"]` | **改**:刪除區域變數,改用檔頭 `UORDER`(反序字面值 + assert);註解改寫 | 順序 = 折序反序 |
| 1130~1131 / 1142~1143 | `ax = 0 if sd in ("xp","xn")`;`sg = 1.0 if sd in ("xp","yp")` | 不改 | 軸 / 正負 |
| 1156~1157 / 1168~1169 | P6 `tgt = {"top":…, "xp": w, "xn": w, "yp": l, "yn": l}` | 不改 | 軸語意(W→x、L→y) |
| 1222 / 1234 | `p_["side"] in ("yp", "yn")`(決定 act) | **改** → `in FOLD_ORDER[:2]` | 順序語意:「前兩折一律施力」 |
| 1224~1225 / 1236~1237 | `if p_["side"] in ("xp","xn") and NACT.get(side+"_n", 0) == 0: pass` | 不改 | 空殼:`pass`,`_n` 鍵從未被寫入,沒有行為;留待日後清理(改它只增加 diff 噪音) |
| 1231 / 1254(02:50 版 1256)| `lay=(2 if a.stage2 else 0) + WORDER.index(p_["side"])` | 不改 | 新順序下 4 折 0..3、stage2 2..3(測試 [1] 驗過) |
| 1236 / 1259(02:50 版 1261)| `ORDER = ["yp", "yn", "xp", "xn"]`(`--unfold`) | **改** → `ORDER = UORDER` | 順序語意;攤開 = 打開,照 PPT 前後先 ⇒ 折序反序(§2.7 有說明,可改 FOLD_ORDER) |
| 1413 / 1437(02:50 版 1439)| `_ORD = ["yp", "yn", "xp", "xn"]`(字幕) | **改** → `_ORD = UORDER` | 與 1236 同源 |
| 1419~1420 / 1443~1444(02:50 版 1445~1446)| `"fold +-y" … "fold +-x"`(BARS 掃桿舊模式的字幕) | 不改 | 死碼:`BARS` 永遠是空 list,掃桿模式早已不走,標籤不影響任何行為 |

另外三處不是 side 字串但屬於本次範圍:296~306 / 304~314 杯子轉法(改,§2.2)、526~527 / 534~535 init_npz(加註解,§2.3)、707~710 / 716~719 FLOORE(加守衛,§2.5)。

---

## 7. 沒動的東西 / 已知限制

- 當天新加的 `--cont --rest --self_filter --pair_freq --col_iter_mult --ccd --hold_mm --no_anchor --tip_over_mm` 及其相關行(`CONT, REST = a.cont, a.rest`、`LZ_HOLD`、`HE = …tip_over_mm`、`L2` 字串、`not a.no_anchor`)一行都沒碰。
- 02:44 / 02:50 另一位 agent 加的 `--release_after` / `--no_hold`(`RELEASED = {}`、drive() 內刪 attachment Scope 與錨點方塊的放手區塊、stage2 的 `if a.no_hold: hold = …`)也一行沒碰,且與本 patch 相容:`no_hold` 只清空 `hold`,在我的 `_s2ax` 程式之前;放手區塊只用 `p_["side"]`,位在我的 `p_["act"]` 判斷之後、`wrap_arc_from` 之前。邏輯測試的 namespace 已補 `no_hold=False`。
- `selfcheck.py` 沒改。它讀的是 `scripts/wrap_sim.py`,交付時要把套好 patch 的檔同步過去 C 段才會 PASS。
- selfcheck 的 `_Rm` 檢查只驗矩陣代數;§3 的網格量測建議另外收進 selfcheck(或 `edge_report.py`),用 npz 的 `mug` 直接量最終姿態。
- 本次驗證全在 CPU 上做(語法、regex、片段 exec、STL 量測);**沒有**開 Isaac 跑模擬。§4 的重跑清單就是實機驗收要做的事。
- 驗證腳本都在 `/tmp/claude-0/-isaac-sim-test-scripts-manip-fr3-handoff-20260929/c7e55632-bf8d-46a1-89a0-934334fed54b/scratchpad/`(`verify_mug_pose.py`、`selfcheck_C.py`、`test_foldorder_logic.py`、改好的 `wrap_sim_foldorder.py`);scratchpad 不保證長存,要留的話複製到 `scripts/`。
