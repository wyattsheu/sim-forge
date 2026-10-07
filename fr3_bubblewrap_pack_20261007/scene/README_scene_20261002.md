# 雙臂工作站 + 氣泡布包裹馬克杯入箱 — 交付包

| | |
|---|---|
| 交付日 | 2026-10-02(場景、模擬、影片) |
| 補充 | 2026-10-07(Isaac Sim **UI** 使用方式、修正 UI 按 Play 箱子陷進桌面的問題) |
| 環境 | Isaac Sim 5.1.0、RTX 5090、driver 580;docker 內可直接開 GUI 到 host 的 `DISPLAY=:1` |

---

## 0. 三十秒上手

```bash
cd handoff_20261002
./open_in_ui.sh                 # 開 Isaac Sim GUI 並載入 scene_final_ui.usd
```
1. 按左邊工具列的 ▶ **Play**
2. **Alt + 左鍵**拖 = 轉視角、**中鍵**拖 = 平移、**滾輪** = 縮放
3. **Shift + 左鍵**拖紙箱或蓋子 = 用滑鼠抓著它動(要在 Play 狀態)

> ⚠️ 要在 UI 裡按 Play,請開 **`scene_final_ui.usd`**,不要直接開 `scene_final.usd`
> (原檔直接 Play,箱子會陷進桌面 48 mm,見 §3)。

---

## 1. 內容

```
README.md                     本文件
scene_final.usd               ★ 主交付:雙臂工作站 + 紙箱 + 箱內的氣泡布包裹 + 馬克杯(單一檔案)
scene_final_ui.usd            🆕 UI 用版本:= scene_final.usd + 摺痕關節 drive + 調好的 PhysicsScene
open_in_ui.sh                 🆕 開 GUI 並載入場景(預設 scene_final_ui.usd,可傳別的 usd 路徑)
scene_final_orbit.mp4         scene_final.usd 環繞展示
videos/
  DEMO_new_order_sheet400.mp4      成果影片:包第一對邊 → 包第二對邊 → 入箱關蓋 → 搬箱開蓋(62 s)
  scene_physics_open_lids.mp4      開箱檢查:四片蓋翻開 170°,開物理 10 s,最後從正上方看箱內
  scene_physics_crease_on.mp4      scene_final.usd 開物理 8 s,蓋子關著,有摺痕力矩
  scene_physics_crease_off.mp4     陰性對照:不加摺痕,下層蓋會掉進箱子
  scene_physics_crease_*.log       上面兩支的逐秒數字
sim/                          重現影片的模擬(平鋪目錄,直接在裡面跑)
  run_demo.sh                   一鍵跑四段 + 串影片
  wrap_sim.py                   模擬本體(Isaac Sim 5.1 surface deformable)
  grip_common.py                wrap_sim.py 的共用零件
  crease_physics.py             紙箱摺痕的彈塑性模型(降伏 + 硬化)
  crease_hold_ui.py             🆕 UI 的 Script Editor 用:摺痕力矩 + 解算器修正
  scene_physics_check.py        對 scene_final.usd 開物理(World 路徑)、錄影、量數字
  ui_path_check.py              🆕 用「跟 UI 一樣」的 Play 路徑量數字(驗證 §3 的表)
  make_carton_P.py, make_definitive.sh   紙箱產生器
  carton.usd / carton.meta.json 紙箱資產(270 x 230 x 134 mm,4 片蓋)+ 幾何參數
  mug.stl, bubble_normal.png, floor_edges.json
states/                       四段結束時的布 + 杯子頂點(c1, c2, box, mb_open),可從中間接續
build/                        重組場景用:build_full_scene.py + 原始手臂場景
```

---

## 2. Python 腳本一覽 —— 哪些可以進 UI、哪些不行

**重要:會自己建 `SimulationApp` 的腳本不能貼進 UI 的 Script Editor**(等於在已經開著的 Kit 裡再開一個 Kit → 當掉或卡死),
只能在終端機用 `/isaac-sim/python.sh` 跑。

| 檔案 | 行數 | 角色 | 怎麼用 |
|---|---|---|---|
| `sim/crease_hold_ui.py` | 91 | UI 用摺痕 + 解算器修正 | ✅ **唯一在 UI 裡載入的**,見 §4.4 |
| `sim/crease_physics.py` | 56 | 彈塑性摺痕模型(函式庫) | 不用手動載入,被其他腳本 import |
| `sim/grip_common.py` | 444 | 場景 / deformable / 夾爪共用零件(函式庫) | 不用手動載入,被 `wrap_sim.py` import |
| `sim/wrap_sim.py` | 1938 | 主模擬:包布 → 入箱 → 搬箱 | ❌ 終端機:`./run_demo.sh`(§6) |
| `sim/scene_physics_check.py` | 188 | 對 scene_final 開物理、錄影、量數字 | ❌ 終端機(§5) |
| `sim/ui_path_check.py` | 86 | UI 路徑的 Play 驗證 | ❌ 終端機(§3) |
| `sim/make_carton_P.py` | 414 | 紙箱產生器 | ❌ 終端機,由 `make_definitive.sh` 呼叫 |
| `build/build_full_scene.py` | 144 | 重組 scene_final.usd | ❌ 終端機(§7) |

相依:
```
wrap_sim.py ──► grip_common.py
            └─► crease_physics.py ◄── scene_physics_check.py
                                  ◄── crease_hold_ui.py ◄── ui_path_check.py (--crease_script)
```
全部都在 `sim/` 同一層,不用設 PYTHONPATH。

---

## 3. 在 UI 按 Play 前一定要知道的事

原本的 `scene_final.usd` **沒有 PhysicsScene**。在 UI 按 Play 時,Isaac 會自動補一個預設的
(60 Hz、TGS、**posIter=1、velIter=0**),迭代次數太少,**整個紙箱會陷進桌面約 48 mm**。
headless 的 `scene_physics_check.py` 用的是 `isaacsim.core.World`,它會套比較好的解算器設定,所以那邊量不到這個問題。

`scene_final_ui.usd` 已經把下面兩件事寫進檔案:

| 修改 | 值 |
|---|---|
| `/physicsScene` | 120 Hz、TGS、minPositionIteration 8、minVelocityIteration 1、GPU aggregate pairs 8192 |
| `/World/Packed/Box/crease_{fxp,fxn,fyp,fyn}` | angular drive:stiffness 0.056 N·m/deg、damping 0.006 N·m·s/deg、maxForce 3.0、target 0 |

drive 的數值 = 摺痕模型的彈性段(k = 3.2 N·m/rad、c = 0.33 N·m·s/rad 換成「每度」的單位;USD angular drive 的單位是度)。

**實測**(`sim/ui_path_check.py`,用 UI 路徑 Play 8 s,2026-10-07):

| 路線 | 箱底 z 位移最大 | 蓋角最大 | 判定 |
|---|---|---|---|
| A. `scene_final_ui.usd` 直接 Play | **0.00 mm** | 0.75° | ✅ |
| B. `scene_final.usd` + `crease_hold_ui.py` | **0.00 mm** | 0.08° | ✅ |
| 對照:`scene_final.usd` 直接 Play | **48.12 mm** | 2.60° | ❌ 箱子陷進桌面 |

```bash
cd sim
/isaac-sim/python.sh ui_path_check.py ../scene_final_ui.usd                 # A
/isaac-sim/python.sh ui_path_check.py ../scene_final.usd --crease_script    # B
/isaac-sim/python.sh ui_path_check.py ../scene_final.usd                    # 對照
```

---

## 4. 在 Isaac Sim UI 裡使用

### 4.1 開啟
- `./open_in_ui.sh [usd 路徑]`(預設 `scene_final_ui.usd`),或
- `/isaac-sim/isaac-sim.sh` 開空場景後,用 **File > Open** 選 usd。

以 root 執行時要先設 `OMNI_KIT_ALLOW_ROOT=1`(`open_in_ui.sh` 已經設好)。
沒有實體螢幕的機器可以改用 `/isaac-sim/isaac-sim.streaming.sh` + WebRTC client。

### 4.2 滑鼠 / 鍵盤(Kit 預設)

| 動作 | 操作 |
|---|---|
| 旋轉視角(繞焦點) | **Alt + 左鍵**拖 |
| 平移 | **中鍵**拖 |
| 縮放 | 滾輪,或 **Alt + 右鍵**拖 |
| 原地環視 | **右鍵**拖(按住右鍵 + WASD = 飛行) |
| 選取 / 對焦 | 左鍵選取,**F** = 對焦到選取的物件 |
| 移動 / 旋轉 / 縮放 gizmo | **W / E / R**(Q = 回到選取模式) |

### 4.3 用滑鼠跟物理互動(必須先按 Play)

| 操作 | 效果 |
|---|---|
| **Shift + 左鍵拖** | 抓住剛體拖著走 |
| **Shift + 左鍵雙擊** | 推一下 |

力道在 Physics 設定的 **Mouse Interaction** 區(Mouse Grab Force Coeff、Mouse Push Acceleration)。

**抓得到什麼:**

| prim | 類型 | 可以互動? |
|---|---|---|
| `/World/Packed/Box/base`(箱底 + 四面牆) | 剛體 | ✅ |
| `/World/Packed/Box/fxp, fxn, fyp, fyn`(四片蓋) | 剛體,用 crease 關節接在 base 上 | ✅ |
| `/World/Packed/Wrap`(氣泡布) | **靜態 Mesh,沒有碰撞、沒有剛體** | ❌ 抓不到,蓋子會穿過去 |
| `/World/Packed/Mug`(杯子) | **靜態 Mesh,沒有碰撞、沒有剛體** | ❌ 抓不到 |
| 手臂 `/World/stationary_ai` | articulation(有 drive) | 用 §4.5 的方式控制 |

包材和杯子是把模擬結果烘成固定幾何(「包好的樣子」);surface deformable 的狀態 USD 帶不走。

### 4.4 真正的彈塑性摺痕(蓋子折開後會保持住)
`scene_final_ui.usd` 的 drive 是彈簧,把蓋子拉開放手後會彈回 0°。
要原本的塑性行為(拉過降伏力矩之後停在新角度),請**開原本的 `scene_final.usd`**,然後
**Window > Script Editor**,貼上並執行:

```python
exec(open("/isaac-sim/test_scripts/manip_fr3/handoff_20261002/sim/crease_hold_ui.py").read())
```
它會做兩件事:
1. 修正 PhysicsScene(同 §3 的值),避免箱子下陷;
2. 在每一個物理步對四片蓋套用 `ElastoplasticCrease.step()`(係數同 `wrap_sim.py`:k=3.2、My0=0.60、H=0.85、c=0.33、clip=3.0),蓋子受 +τ、箱底受 −τ。

然後按 Play。要停掉摺痕就執行 `crease_stop()`。
- **不要**在 `scene_final_ui.usd` 上再跑這支(drive 和摺痕力矩會疊在一起)。
- 交付包換位置的話,要改 `crease_hold_ui.py` 第 10 行的 `SIM_DIR`。

### 4.5 控制手臂
兩支手臂是同一個 articulation(root:`/World/stationary_ai/root_joint`),每個關節都已經有 drive(target 0)。按 Play 後:

| 關節 | prim(在 `/World/stationary_ai/joints/` 底下) | drive |
|---|---|---|
| 手臂 6 軸 | `follower_{left,right}_joint_0` … `_5` | angular;stiffness:joint_0~2 為 664~738,joint_3~5 為 33~62 |
| 夾爪 | `follower_{left,right}_left_carriage_joint` | linear,target 單位是公尺(`right_carriage_joint` 沒有 drive) |

- 單一關節:在 Stage 選該關節,到 Property > **Drive > Target Position**(角度,單位是度)改值。
- 全部關節的滑桿:Window 選單裡的 **Physics Inspector**。

---

## 5. scene_final.usd 規格與物理驗證

| 項目 | 值 |
|---|---|
| 手臂場景 | `stationary_ai_carton_scene_flat.usd`,手臂與桌子**完全沒動** |
| 原本的 `/World/Carton` | 已移除,換成 `/World/Packed`(Box + Wrap + Mug) |
| 擺放 | 對齊原本紙箱:中心 (x, y) = (-20, 0) mm,箱底 z = 20 mm(= 桌面) |
| 方向 | 繞 z 轉 90°,270 mm 長邊沿 y(左右手臂方向) |
| 箱子世界座標 bbox | x -135~95 / y -135~135 / z 20~154 mm |
| 與夾爪距離 | 四個夾爪指在 y 方向都離箱子 68.7 mm,沒有干涉 |
| 包材 / 杯子 | 取自影片第 3 段結束(`states/box.npz`),逐頂點檢查 100% 在內腔內 |
| 蓋子 | 四片關閉(= USD 預設角度,與模擬結束時一致) |
| 外部依賴 | 紙箱已攤平寫進檔案;只剩手臂場景原本就有的兩個 NVIDIA 雲端 MDL 材質 |
| 座標 | Z-up,metersPerUnit = 1 |

紙箱的摺痕關節是被動的(±185°、沒有 drive);彈塑性摺痕(`crease_physics.py`)是執行期每一步外加的力矩,USD 存不了。
程式裡要動態模擬的話,對 `/World/Packed/Box/crease_{fxp,fxn,fyp,fyn}` 每一步套用 `ElastoplasticCrease.step()`,
寫法見 `scene_physics_check.py`(最短)或 `wrap_sim.py`。

**World 路徑驗證**(`sim/scene_physics_check.py`,2026-10-02 實跑):

```bash
cd sim && /isaac-sim/python.sh scene_physics_check.py ../scene_final.usd --out phys --secs 8
/isaac-sim/python.sh scene_physics_check.py ../scene_final.usd --out phys_nc --no_crease               # 對照組
/isaac-sim/python.sh scene_physics_check.py ../scene_final.usd --out phys_open --secs 10 --open_deg 170 # 開箱檢查
```

| 檢查 | 關蓋 + 摺痕 | 開蓋 170° + 摺痕 | 關蓋、無摺痕(對照) |
|---|---|---|---|
| 箱子位移 | 0.00 mm | 0.00 mm | 0.00 mm |
| 箱底面 − 桌面 | 0.00 mm | 0.00 mm | 0.00 mm |
| 下層蓋 fxp / fxn 最大偏角 | 0.3° / 0.3° | 0.3° / 0.3° | **91.7° / 91.7°(掉進箱子)** |
| 上層蓋 fyp / fyn 最大偏角 | 0.3° / 0.3° | 0.3° / 0.3° | 4.1° / 4.1° |
| 手臂關節最大漂移 | 0.07° | 0.07° | 0.07° |

偏角 = 蓋子相對起始姿態繞鉸鏈轉了多少(0.3° 是重力造成的下垂)。`--open_deg` 只改這次模擬的 stage,不會存回 USD。

---

## 6. 重現影片

```bash
cd sim && ./run_demo.sh          # ISAAC=/path/to/python.sh ./run_demo.sh 可以換 Isaac 路徑
```
四段依序跑:c1 包第一對邊 → c2 包第二對邊 → box 入箱關蓋 → mb_open 搬箱開蓋。
每段約 2~3 分鐘(需要 GPU),產出 `sim/DEMO.mp4`,最後印出入箱檢查的結果。

2026-10-02 在乾淨目錄實跑一次(RTX 5090,約 10 分鐘),影片長度相同(62.2 s),但**結果不是逐位元相同**
(GPU deformable 不是確定性的):

| 檢查 | 交付版(states/) | 重跑 |
|---|---|---|
| 入箱:布 / 杯子超出內腔的頂點 | 0 / 0 | 0 / 0 |
| 入箱後杯子位置差 | — | 11.5 mm(整體平移) |
| 入箱後布頂點差 | — | 平均 24.8 mm、最大 130 mm |
| 搬箱:包裹相對箱子位移 | 2.5 mm | 9.1 mm |
| 搬箱後超出內腔的頂點 | 6 | 6 |

`scene_final.usd` 用的是交付版的 `states/box.npz`,不是重跑的結果。

---

## 7. 重組場景(換位置 / 換包裹狀態)

```bash
/isaac-sim/python.sh build/build_full_scene.py \
    --scene build/stationary_ai_carton_scene_flat.usd \
    --carton sim/carton.usd --wrap states/box.npz --mug sim/mug.stl \
    --out scene_final.usd            # --place x,y,z 可以手動指定位置;預設 auto = 對齊原本的紙箱
```
重組出來的檔案一樣**沒有** PhysicsScene 和 crease drive;要在 UI 用的話,請用 §4.4 的 Script Editor 路線,
或參考 §3 的值自己加上去。

---

## 8. 已知問題 / 交接注意

| # | 問題 | 影響 | 狀態 / 做法 |
|---|---|---|---|
| 1 | `scene_final.usd` 沒有 PhysicsScene,UI 的預設設定太弱 | UI 按 Play 箱子陷 48 mm | 用 `scene_final_ui.usd` 或 `crease_hold_ui.py`(§3) |
| 2 | Wrap / Mug 是靜態 Mesh | 滑鼠抓不到、不會碰撞 | 設計如此。要互動:杯子可以加凸包碰撞體 + 剛體;布只能做成靜態三角網格碰撞體,要能變形得回到 deformable(Phase-2) |
| 3 | `crease_physics.py` 檔案裡的**預設係數**(k=3.5、My0=0.85、H=0.55、c=0.28、clip=3.6)≠ 實際使用的係數(k=3.2、My0=0.60、H=0.85、c=0.33、clip=3.0) | 直接用預設值,結果會和影片、驗證數字不同 | 建立 `ElastoplasticCrease(...)` 時一律明確傳入係數;c 不要超過 0.4(數值會爆) |
| 4 | Play 時 log 出現 `angle limit ... clamped to ±180 degrees`(crease_*) | 無 | USD 設 ±185°,PhysX D6 上限 ±180°;蓋子實際只動幾度 |
| 5 | Play 時 log 出現 `PhysX error: ... foundLostAggregatePairsCapacity to 3418` | 預設設定下可能漏掉碰撞 | `scene_final_ui.usd` / `crease_hold_ui.py` 已經把容量設成 8192,實測不再出現 |
| 6 | `make_definitive.sh` 最後提示要跑 `carton_sweep.py`、`gap.py`、`qa_carton.py`,但這三支**不在包裡** | 紙箱 QA 無法照提示重跑 | 紙箱本身可以照常產生;QA 腳本要另外向原作者索取 |
| 7 | GPU deformable 不是確定性的 | 重跑影片數字會有差異(§6) | 以 `states/*.npz` 為準 |
| 8 | `crease_hold_ui.py` 的 `SIM_DIR` 是絕對路徑 | 交付包搬位置後會 import 失敗 | 改第 10 行 |
