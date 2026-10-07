# 氣泡布包裹馬克杯入箱 —— 雙臂工作站(交付版 Handoff)

[English](README.md) | **繁體中文**

> **這是交出去的 handoff。** clone 下來就能開場景、按 Play、用滑鼠互動、重跑模擬、重新產生所有影片。
> 開發過程(實驗、122 次模擬紀錄、volume deformable、測試集)在
> [`sims/fr3_bubblewrap_pack_20261007`](../fr3_bubblewrap_pack_20261007),使用這份交付包不需要看那邊。

| | |
|---|---|
| **版本** | handoff_20261007 —— 2026-10-02 的場景與模擬,2026-10-07 補上 UI / WebRTC 用法並修正按 Play 的問題 |
| **測試環境** | Isaac Sim 5.1.0、RTX 5090、NVIDIA driver 580 |
| **取得方式** | git:這個資料夾(不含影片,執行 `./make_videos.sh` 產生)· 壓縮檔:`handoff_20261007.tgz`(含影片) |

## 目錄

1. [快速開始](#1-快速開始)
2. [該開哪個場景檔](#2-該開哪個場景檔)
3. [在 Isaac Sim UI 裡使用](#3-在-isaac-sim-ui-裡使用)
4. [用 WebRTC 遠端看](#4-用-webrtc-遠端看)
5. [影片](#5-影片)
6. [檔案](#6-檔案)
7. [腳本:哪支在哪裡跑](#7-腳本哪支在哪裡跑)
8. [技術參考](#8-技術參考)
9. [已知問題](#9-已知問題)

---

## 1. 快速開始

```bash
./open_in_ui.sh        # 本機有螢幕:開 Isaac Sim 並載入場景
./open_in_webrtc.sh    # 遠端:開串流,用 WebRTC Streaming Client 連線(§4)
./make_videos.sh       # 重新產生驗證影片;加 --demo 會連 62 秒的成果影片一起產生
```

畫面出來後:

1. 按 **▶ Play**(左側工具列)。
2. **Alt + 左鍵拖曳**:旋轉視角。
3. **Shift + 左鍵拖曳**:抓住紙箱或蓋子拖動。

---

## 2. 該開哪個場景檔

| 檔案 | 用途 | 按 Play 的結果 |
|---|---|---|
| **`scene_final_ui.usd`** | **在 UI 裡互動**(兩支啟動腳本的預設值) | 紙箱不動(0.00 mm),蓋子撐住(≤ 0.75°) |
| `scene_final.usd` | 正式交付檔;給 headless 腳本用;彈塑性摺痕(§3.4) | ⚠️ 在 UI 直接按 Play,**紙箱會陷進桌面 48 mm** |

**原因:** `scene_final.usd` 沒有 PhysicsScene,UI 會自動補一個預設的
(60 Hz、位置迭代 1 次、速度迭代 0 次),強度不夠,撐不住紙箱。
`scene_final_ui.usd` 是同一個場景,只多了調好的 PhysicsScene,以及四片蓋子摺痕上的彈簧 drive。
細節與實測數字見 [§8.2](#82-scene_final_uiusd-的修正)。

---

## 3. 在 Isaac Sim UI 裡使用

### 3.1 開啟場景

**用指令**

```bash
./open_in_ui.sh                    # 開 scene_final_ui.usd
./open_in_ui.sh scene_final.usd    # 或指定其他 USD
```

**從 UI 開**

1. 啟動 Isaac Sim,任選一種:
   - 執行 `/isaac-sim/isaac-sim.sh`(以 root 執行時,先 `export OMNI_KIT_ALLOW_ROOT=1`),或
   - 執行 `/isaac-sim/isaac-sim.selector.sh` → 選 **Isaac Sim Full** → **START**。
2. 開檔,任選一種:
   - **File → Open** → 選 `scene_final_ui.usd`,或
   - 在下方 **Content** 面板的路徑列貼上這個資料夾的路徑,**雙擊** `scene_final_ui.usd`。
     (不要把 USD 拖進 viewport —— 那是把它當 reference 加進目前的場景,不是開檔。)
   - 之後可以從 **File → Open Recent** 直接開。
3. 按 **▶ Play**。

### 3.2 視角與選取

| 動作 | 操作 |
|---|---|
| 旋轉視角 | **Alt + 左鍵拖曳** |
| 平移 | **中鍵拖曳** |
| 縮放 | **滾輪**,或 **Alt + 右鍵拖曳** |
| 原地環視 / 飛行 | **右鍵拖曳**(按住右鍵 + **WASD** 飛行) |
| 選取 / 對焦到選取物 | **左鍵** / **F** |
| 移動 / 旋轉 / 縮放 gizmo | **W / E / R**(**Q** 回到選取) |

### 3.3 跟物理互動(播放中)

| 操作 | 效果 |
|---|---|
| **Shift + 左鍵拖曳** | 抓住剛體拖動 |
| **Shift + 左鍵雙擊** | 推一下 |

抓取力道在 Physics 設定 → **Mouse Interaction**(Grab Force Coeff、Push Acceleration)。

| 物件 | Prim | 抓得到嗎 |
|---|---|---|
| 紙箱本體(箱底 + 四面牆) | `/World/Packed/Box/base` | ✅ 剛體 |
| 四片蓋子 | `/World/Packed/Box/{fxp,fxn,fyp,fyn}` | ✅ 剛體,用摺痕關節接在箱體上 |
| 氣泡布 | `/World/Packed/Wrap` | ❌ 靜態 mesh,沒有碰撞、沒有剛體(蓋子會穿過去) |
| 馬克杯 | `/World/Packed/Mug` | ❌ 靜態 mesh,沒有碰撞、沒有剛體 |
| 手臂 | `/World/stationary_ai` | 改用關節 drive 控制(§3.5) |

包材和杯子是把模擬結果烘成固定幾何(呈現「包好的樣子」)。
surface deformable 的狀態沒辦法存進 USD。

### 3.4 真正的彈塑性摺痕(蓋子折到哪就停在哪)

`scene_final_ui.usd` 裡的摺痕是彈簧:把蓋子拉開,放手後會彈回 0°。
要真實的行為(超過降伏力矩後,蓋子停在新的角度),
請開 **`scene_final.usd`**,再執行 `sim/crease_hold_ui.py`:

**用滑鼠點選**

1. **Window → Script Editor**
2. 在 Script Editor 裡:**File → Open**(Alt + O)→ 選 `sim/crease_hold_ui.py`
3. 如果交付包**不在** `/isaac-sim/test_scripts/manip_fr3/handoff_20261002/`,
   把第 16 行的 `SIM_DIR_OVERRIDE = ""` 改成你的 `sim/` 完整路徑。
4. 按 **Run**(Ctrl + Enter)。

**或貼一行**(會自己找到資料夾,不用改第 16 行)

```python
p = "/你的路徑/sim/crease_hold_ui.py"; exec(compile(open(p).read(), p, "exec"))
```

接著按 Play。這支腳本會:

- 調整 PhysicsScene(數值同 `scene_final_ui.usd`),紙箱不會下陷;
- 每個物理步對四片蓋子套用 `ElastoplasticCrease.step()`
  (k = 3.2、My0 = 0.60、H = 0.85、c = 0.33、clip = 3.0,同 `wrap_sim.py`),蓋子受 +τ、箱體受 −τ。

執行 `crease_stop()` 可以停掉。不要在 `scene_final_ui.usd` 上跑這支 —— 彈簧 drive 和摺痕力矩會疊在一起。

### 3.5 控制手臂

兩支手臂是同一個 articulation(root:`/World/stationary_ai/root_joint`),每個關節都已經有 drive(target 0)。
播放中:

| 關節 | Prim(在 `/World/stationary_ai/joints/` 底下) | Drive |
|---|---|---|
| 6 軸手臂 | `follower_{left,right}_joint_0` … `_5` | angular;stiffness 664–738(關節 0–2)、33–62(關節 3–5) |
| 夾爪 | `follower_{left,right}_left_carriage_joint` | linear,target 單位是公尺(`right_carriage_joint` 沒有 drive) |

- 單一關節:在 Stage 面板選取 → **Property → Drive → Target Position**(單位:度)。
- 所有關節的滑桿:**Window → Physics Inspector**。

---

## 4. 用 WebRTC 遠端看

伺服器串流完整的 Isaac Sim UI,你在另一台電腦上用
**Isaac Sim WebRTC Streaming Client**(NVIDIA Isaac Sim 下載頁的桌面程式)觀看和操作。
§3 的所有操作在串流畫面裡都一樣能用。

### 4.1 用指令(推薦)

腳本會幫你開場景、調視角、打開滑鼠拖曳,並自動按 Play。

```bash
./open_in_webrtc.sh                              # scene_final_ui.usd
./open_in_webrtc.sh scene_final.usd --crease     # 原檔 + 彈塑性摺痕(§3.4)
WEBRTC_IP=<對外 IP> WEBRTC_PORT=49110 ./open_in_webrtc.sh
WEBRTC_NO_PLAY=1 ./open_in_webrtc.sh             # 載入但不自動 Play
./open_in_webrtc.sh --stop                       # 停止串流
```

- 等 `logs/webrtc.log` 出現 `[handoff] READY`(約 20 秒)再連線。
- **這個模式不用按 Shift**,直接左鍵拖曳就能抓紙箱或蓋子。
- 預設 IP `140.96.68.42`(這台伺服器)、signaling port 49100。**換機器時請設定 `WEBRTC_IP`。**

### 4.2 從 UI 啟動

1. 在伺服器桌面執行 `/isaac-sim/isaac-sim.selector.sh`(App Selector)。
2. 選 **Isaac Sim Full Streaming**。
3. 對外 IP 不是預設值時,在 **Extra Args** 填 `--/app/livestream/publicEndpointAddress=<對外 IP>`。
4. 按 **START**。
5. 用 Streaming Client 連進去,**File → Open** `scene_final_ui.usd`,按 Play
   (這個模式下,物理拖曳要 **Shift + 左鍵拖曳**)。

### 4.3 連線

- Streaming Client → 輸入伺服器 IP → **Connect**。
- 防火牆要開 **TCP 49100**(signaling)和 **UDP 47998**(影音)。

2026-10-07 實測:兩種指令模式都在約 20 秒內出現 READY(載入 591–592 個 prim、port 49100 有在監聽、物理有在跑),
`--stop` 能正常關閉。Client 端沒有測 —— 伺服器上沒有 client。

---

## 5. 影片

影片**不進 git**。一個指令就能把全部影片重新產生到 `videos/`:

```bash
./make_videos.sh                  # 下表前四支
./make_videos.sh --demo           # 再加 62 秒的 DEMO(需要 GPU)
VIDEO_DIR=/tmp/v ./make_videos.sh # 輸出到別的地方
```

| 影片 | 內容 | 單獨產生(在 `sim/` 裡執行) |
|---|---|---|
| `scene_physics_crease_on.mp4` | 開物理 8 秒,蓋子關著,有摺痕力矩 | `python.sh scene_physics_check.py ../scene_final.usd --out phys --secs 8` |
| `scene_physics_crease_off.mp4` | 對照組:沒有摺痕,下層蓋掉進箱子 | `python.sh scene_physics_check.py ../scene_final.usd --out phys_nc --secs 8 --no_crease` |
| `scene_physics_open_lids.mp4` | 蓋子翻開 170°,開物理 10 秒,最後從正上方看箱內 | `python.sh scene_physics_check.py ../scene_final.usd --out phys_open --secs 10 --open_deg 170` |
| `scene_final_orbit.mp4` | 繞場景一圈 12 秒(只算圖,不跑物理) | `python.sh orbit_video.py ../scene_final.usd orbit.mp4` |
| `DEMO_new_order_sheet400.mp4` | 成果:包第一對邊 → 第二對邊 → 入箱關蓋 → 搬箱開蓋(62 秒) | `./run_demo.sh`(產出 `sim/DEMO.mp4`) |

`python.sh` 指 `/isaac-sim/python.sh`。每支物理影片旁邊會有同名 `.log`,記錄逐秒的數字。

**要跑多久:** 2026-10-07 在 GPU 被其他工作共用的情況下實測 `./make_videos.sh --demo`:
物理影片約 3 分鐘、環繞影片約 25 分鐘、DEMO 約 6 分鐘,**總共約 32 分鐘**。GPU 空閒時會比較快。

---

## 6. 檔案

```
README.md / README.zh-TW.md     本文件(English / 繁體中文)
scene_final.usd                 ★ 交付檔:雙臂工作站 + 紙箱 + 包好的馬克杯(單一檔案,14 MB)
scene_final_ui.usd              同一場景 + 調好的 PhysicsScene + 蓋子彈簧 drive,給 UI 用(§2)
open_in_ui.sh                   在本機 Isaac Sim UI 開啟
open_in_webrtc.sh               用 WebRTC 開啟(--stop 停止)
make_videos.sh                  重新產生 videos/
videos/                         影片(只在壓縮檔裡;用 make_videos.sh 產生)
sim/                            模擬與工具 —— 平鋪資料夾,在裡面執行腳本
  wrap_sim.py                     模擬本體(Isaac Sim 5.1 surface deformable)
  grip_common.py                  wrap_sim.py 的共用零件
  crease_physics.py               彈塑性摺痕模型(降伏 + 硬化)
  crease_hold_ui.py               UI 的 Script Editor 用:摺痕力矩 + PhysicsScene 修正(§3.4)
  webrtc_boot.py                  open_in_webrtc.sh 的開機腳本(kit --exec)
  scene_physics_check.py          物理驗證 + 影片(走 isaacsim.core World)
  ui_path_check.py                物理驗證(走跟 UI 一樣的 Play 路徑,§8.2)
  orbit_video.py                  環繞影片(只算圖)
  run_demo.sh                     跑四段模擬並串成 DEMO.mp4
  make_carton_P.py, make_definitive.sh   紙箱產生器
  carton.usd, carton.meta.json    紙箱資產(270 × 230 × 134 mm,4 片蓋)及幾何參數
  mug.stl, bubble_normal.png, floor_edges.json
states/                         每段模擬結束時布 + 杯子的頂點(c1, c2, box, mb_open),可以從任一段接著跑
build/
  build_full_scene.py             重組 scene_final.usd(§8.5)
  stationary_ai_carton_scene_flat.usd   原始雙臂場景(14 MB)
```

---

## 7. 腳本:哪支在哪裡跑

> **會自己建 `SimulationApp` 的腳本,絕對不要貼進 Script Editor。**
> 那會在執行中的 Kit 裡再開一個 Kit,結果是卡死或當掉。這類腳本要在終端機用 `/isaac-sim/python.sh` 執行。

| 腳本 | 是什麼 | 怎麼執行 |
|---|---|---|
| `sim/crease_hold_ui.py` | 摺痕力矩 + PhysicsScene 修正 | ✅ **唯一在 UI 裡執行的**(§3.4) |
| `sim/webrtc_boot.py` | WebRTC 開機腳本 | 由 `open_in_webrtc.sh` 透過 `kit --exec` 啟動 |
| `sim/crease_physics.py` | 摺痕模型(函式庫) | 被其他腳本 import |
| `sim/grip_common.py` | 共用模擬零件(函式庫) | 被 `wrap_sim.py` import |
| `sim/wrap_sim.py` | 包布 → 入箱 → 搬箱模擬 | 終端機:`sim/run_demo.sh` 或 `./make_videos.sh --demo` |
| `sim/scene_physics_check.py` | 物理驗證 + 影片 | 終端機(§5、§8.3) |
| `sim/ui_path_check.py` | UI 路徑的 Play 驗證 | 終端機(§8.2) |
| `sim/orbit_video.py` | 環繞影片 | 終端機(§5) |
| `sim/make_carton_P.py` | 紙箱產生器 | 終端機,由 `make_definitive.sh` 呼叫 |
| `build/build_full_scene.py` | 重組場景 | 終端機(§8.5) |

```
wrap_sim.py ──► grip_common.py
            └─► crease_physics.py ◄── scene_physics_check.py
                                  ◄── crease_hold_ui.py ◄── ui_path_check.py --crease_script
                                                        ◄── webrtc_boot.py(open_in_webrtc.sh --crease)
```

全部都在 `sim/` 裡,不需要設定 PYTHONPATH。

---

## 8. 技術參考

### 8.1 場景配置(`scene_final.usd`)

| 項目 | 值 |
|---|---|
| 手臂場景 | `build/stationary_ai_carton_scene_flat.usd`;手臂與桌子**完全沒動** |
| 原本的 `/World/Carton` | 已移除,換成 `/World/Packed`(Box + Wrap + Mug) |
| 擺放 | 對齊原本的紙箱:中心 (x, y) = (−20, 0) mm,箱底 z = 20 mm(= 桌面) |
| 方向 | 繞 z 轉 90°;270 mm 長邊沿 y(兩支手臂之間的方向) |
| 紙箱世界座標 bbox | x −135…95、y −135…135、z 20…154 mm |
| 與夾爪的距離 | 四根夾爪指在 y 方向都離紙箱 68.7 mm |
| 包材與杯子 | 取自模擬第 3 段結束(`states/box.npz`);每個頂點都檢查過在箱內 |
| 蓋子 | 四片都關著(USD 預設角度 = 模擬結束時的角度) |
| 外部依賴 | 紙箱已攤平寫進檔案;只剩手臂場景原本就用的兩個 NVIDIA 雲端 MDL 材質 |
| 單位 / 座標軸 | Z-up,metersPerUnit = 1 |

摺痕關節是被動的(±185°,沒有 drive)。彈塑性摺痕(`crease_physics.py`)是執行時每個物理步額外施加的力矩,
所以存不進 USD。在自己的程式裡,要每一步對 `/World/Packed/Box/crease_{fxp,fxn,fyp,fyn}`
套用 `ElastoplasticCrease.step()` —— 最短的範例是 `scene_physics_check.py`。

### 8.2 `scene_final_ui.usd` 的修正

| 修改 | 值 |
|---|---|
| `/physicsScene` | 120 Hz、TGS、最少位置迭代 8、最少速度迭代 1、GPU aggregate pairs 8192 |
| `/World/Packed/Box/crease_{fxp,fxn,fyp,fyn}` | angular drive:stiffness 0.056 N·m/deg、damping 0.006 N·m·s/deg、max force 3.0、target 0 |

drive 的值取自摺痕模型的彈性段(k = 3.2 N·m/rad、c = 0.33 N·m·s/rad),換算成 USD angular drive 使用的「每度」單位。

用 `sim/ui_path_check.py` 實測(開檔、按 Play 的方式跟 UI 完全一樣;8 秒;2026-10-07):

| 路線 | 紙箱 z 最大位移 | 蓋子最大角度 | |
|---|---|---|---|
| A. `scene_final_ui.usd` 直接 Play | **0.00 mm** | 0.75° | ✅ |
| B. `scene_final.usd` + `crease_hold_ui.py` | **0.00 mm** | 0.08° | ✅ |
| 對照:`scene_final.usd` 直接 Play | **48.12 mm** | 2.60° | ❌ 紙箱陷進桌面 |

```bash
cd sim
/isaac-sim/python.sh ui_path_check.py ../scene_final_ui.usd                 # A
/isaac-sim/python.sh ui_path_check.py ../scene_final.usd --crease_script    # B
/isaac-sim/python.sh ui_path_check.py ../scene_final.usd                    # 對照
```

headless 的 `scene_physics_check.py` 從來沒量到下陷,因為 `isaacsim.core.World` 會套用比較好的解算器預設值。

### 8.3 走 `World` 的物理驗證(`scene_physics_check.py`)

2026-10-07 用 `make_videos.sh` 重跑,數字與 2026-10-02 完全相同。

| 檢查 | 蓋子關 + 摺痕 | 蓋子翻開 170° + 摺痕 | 蓋子關、無摺痕(對照) |
|---|---|---|---|
| 紙箱位移 | 0.00 mm | 0.00 mm | 0.00 mm |
| 箱底 − 桌面 | 0.00 mm | 0.00 mm | 0.00 mm |
| 下層蓋 fxp / fxn 最大角度 | 0.3° / 0.3° | 0.3° / 0.3° | **91.7° / 91.7°(掉進箱子)** |
| 上層蓋 fyp / fyn 最大角度 | 0.3° / 0.3° | 0.3° / 0.3° | 4.1° / 4.1° |
| 手臂關節最大漂移 | 0.07° | 0.07° | 0.07° |

角度 = 蓋子相對起始姿態繞鉸鏈轉了多少(0.3° 是重力造成的下垂)。`--open_deg` 只改那次執行的 stage,不會改到 USD 檔。

### 8.4 DEMO 的重現性

GPU deformable 不是確定性的。重跑的影片長度相同(62.2 秒),但結果不會逐位元相同:

| 檢查 | 交付版(`states/`) | 2026-10-02 重跑 | 2026-10-07 重跑 |
|---|---|---|---|
| 入箱:布 / 杯子超出內腔的頂點 | 0 / 0 | 0 / 0 | 0 / 0 |
| 入箱後杯子位置差 | — | 11.5 mm(整體平移) | — |
| 入箱後布頂點差 | — | 平均 24.8 mm、最大 130 mm | — |
| 搬箱後:包裹相對紙箱的位移 | 2.5 mm | 9.1 mm | 4.3 mm |
| 搬箱後:超出內腔的頂點 | 6 | 6 | 4(布,略低於箱底) |

`scene_final.usd` 用的是交付版的 `states/box.npz`,不是重跑的結果。

### 8.5 重組場景

```bash
/isaac-sim/python.sh build/build_full_scene.py \
    --scene build/stationary_ai_carton_scene_flat.usd \
    --carton sim/carton.usd --wrap states/box.npz --mug sim/mug.stl \
    --out scene_final.usd     # --place x,y,z 指定位置;預設 "auto" 對齊原本的紙箱
```

重組出來的檔案一樣**沒有** PhysicsScene,也沒有摺痕 drive。要在 UI 用,照 §3.4 做,或自己加上 §8.2 的值。

---

## 9. 已知問題

| # | 問題 | 影響 | 怎麼處理 |
|---|---|---|---|
| 1 | `scene_final.usd` 沒有 PhysicsScene;UI 的預設值太弱 | UI 按 Play 時紙箱陷 48 mm | 用 `scene_final_ui.usd` 或 `crease_hold_ui.py`(§2、§8.2) |
| 2 | 包材與杯子是靜態 mesh | 抓不到,也不會跟任何東西碰撞 | 設計如此。要能互動:杯子加凸包碰撞體 + 剛體;布只能做成靜態三角網格碰撞體;要能再變形就得回到 deformable(見開發資料夾) |
| 3 | `crease_physics.py` 的**預設係數**(k=3.5、My0=0.85、H=0.55、c=0.28、clip=3.6)跟實際使用的(k=3.2、My0=0.60、H=0.85、c=0.33、clip=3.0)不一樣 | 用預設值會對不上影片和數字 | 建 `ElastoplasticCrease(...)` 時一律明確傳入係數;c 不要超過 0.4(會數值爆炸) |
| 4 | Play 時 log 出現 `angle limit ... clamped to ±180 degrees`(crease_*) | 無 | USD 設 ±185°,PhysX D6 上限 ±180°;蓋子實際只動幾度 |
| 5 | Play 時 log 出現 `PhysX error: ... foundLostAggregatePairsCapacity to 3418` | 預設設定下可能漏接觸 | `scene_final_ui.usd` 和 `crease_hold_ui.py` 已調到 8192;實測不再出現 |
| 6 | `make_definitive.sh` 提示要跑 `carton_sweep.py`、`gap.py`、`qa_carton.py`,但**不在交付包裡** | 沒辦法照提示重跑紙箱 QA | 紙箱本身照常能產生。原始位置:`manip_fr3/carton/{gap,qa_carton}.py`、`manip_fr3/handoff_20260929/scripts/carton_sweep.py` |
| 7 | GPU deformable 不是確定性的 | 每次跑 DEMO 數字會有差異(§8.4) | 以 `states/*.npz` 為準 |
| 8 | 從 Script Editor 的 File → Open 執行時,`crease_hold_ui.py` 拿不到自己的路徑 | 交付包不在預設路徑時 import 會失敗(有清楚的錯誤訊息) | 設第 16 行的 `SIM_DIR_OVERRIDE`,或用 §3.4 的一行指令 |
| 9 | WebRTC 預設 IP 是 `140.96.68.42` | 換機器就連不上 | 設 `WEBRTC_IP=<對外 IP>` |
