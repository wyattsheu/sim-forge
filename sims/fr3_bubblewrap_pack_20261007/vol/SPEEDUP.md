# SPEEDUP：volume 包材線的開發迭代加速（2026-10-21）

目標是把開發迭代從約 20 分鐘壓到約 2 分鐘。這次做了三件事：(1) 存檔續跑、(2) 抓取規劃停頓、(3) 一條指令跑三次分布。
改到的程式有 `wrap_vol.py`（備份 `wrap_vol.py.before_speed`，diff 83 行，都標了 `[speed2]`）、`grasp_plan.py`（備份 `grasp_plan.py.before_speed`），另外新增 `run3.sh` 和 `speed2/` 底下的幾支腳本。
所有新旗標的預設值都等於舊行為。

## 結論
| 項目 | 結果 |
|---|---|
| 抓取規劃停頓 | 舊版離線單執行緒量：yn 221 s、yp 190 s（實跑 log「算了」：extract6/X2 是 209 / 163 s，C3f 是 242 / 216 s）。新版離線量 8 個快照 × 2 片 = 16 次規劃，每次 **1.3~2.7 s**；實跑 log「算了」**1.7~2.5 s**（speed2/A、R、Ryn、T 共 13 次模擬）。候選排序 16/16 相同，見 §2 |
| 存檔續跑結果 | 從 A/1 的存檔續跑 3 次（R）：yn 綁點 23~24、越線 96%、放手後 94~95%，yp 越線 91~93%，穿杯 0，落地布被帶起 35.4~37.2%。存檔來源 A/1 整鏈跑的是 97 / 96%、yp 92%、36.9%，其他數字也都在整鏈 3 次（A）的範圍內或差 1 點以內，見 §1 |
| 續跑牆鐘 | 只續跑掀開 yn 段（`--until yn`）：**170~250 s**。續跑整段（掀 yn + 掀 yp + 取杯）：**361~660 s**。整鏈：480~2041 s（GPU 負載差很多）。**「≤ 整鏈 1/4」沒達到：同負載下 yn 段續跑 0.35、整段續跑 0.74**（對舊整鏈 829 s 則是 0.21 / 0.44），原因見 §1.3 |
| 三次分布 | `./run3.sh NAME 旗標...` 跑完自動產生 `NAME/TABLE.md`。實測時會撞到 GPU 顯存不夠，PhysX **不報錯、也不模擬布**；所以加了凍結偵測、自動重開，以及跨批次的啟動鎖 |

## 用法
```
cd vol
# 整鏈跑，順便在掀開段開始前（TG0 = 46.9 s，開蓋 hold + settle 都完成）存檔
/isaac-sim/python.sh wrap_vol.py <旗標> --quality fast --save_state speed2/S.npz [--at grasp|opened|秒數] [--save_exit 1] --out xxx
# 從存檔續跑：掀開 / 取杯段的旗標可以改（log 會印出跟存檔不同的旗標），折 / 蓋 / 搬的時間表要相同（不同就 assert）
/isaac-sim/python.sh wrap_vol.py <旗標> --quality fast --load_state speed2/S.npz [--until yn] --out yyy
# 一條指令跑三次並出表（@x4 = extract4 旗標；@demo = 夾爪 demo 正式旗標；{k} 會換成 1/2/3）
./run3.sh speed2/A @x4 --quality fast --save_state 'speed2/A/S{k}.npz'
./run3.sh speed2/R @x4 --quality fast --load_state speed2/A/S1.npz
./run3.sh speed2/Ryn @x4 --quality fast --load_state speed2/A/S1.npz --until yn     # 調掀開參數時用這個，約 3 分鐘
python3 speed2/table3.py speed2/A speed2/R          # 多組並排
```
- `--until yn`：跑到 yn 片結束為止，等於 `--second 0 --extract 0`。yn 段的物理和時間表都不變。
- `--at`：`grasp`（預設，TG0）、`opened`（T_END_ALL，開蓋 hold 結束），或一個秒數（要在放錨點之後、TG0 之前）。抓取段中途（例如 yp 開始前）不能存，因為夾爪軌跡是 closure、手 2 有綁定，沒有序列化。
- run3.sh 的環境變數：`N=3`、`KS="2"`（只補跑某幾次）、`MAXPAR=3`、`GPU_MAX=29500`、`HEAD=3000`、`TRIES=6`、`STARTUP_S=240`。

## 1. 存檔續跑（`--save_state` / `--at` / `--save_exit` / `--load_state`）
存檔內容（npz）：
- 布：`pts`（sim mesh 就是 collision mesh，同一個 TetMesh）和 `vel`（PhysX 會把速度寫回 USD，讀得到）。
- `meta`（pickle）：t、步數、幀號、ST（inbox / released / OFF_IN / pads_gone）、杯子位置與四元數、箱底和 4 片蓋的世界姿態、SNAP、EV、LOGR、軌跡、np.random 狀態、args、相機。

載入時分兩步：
1. **reset 前**直接寫進 USD：移除 `/World/attach`（錨點綁定）、杯子設成 dynamic 並放到存檔姿態、箱子和蓋子放到存檔姿態、側板放到 z = -3、關掉地板碰撞、設定燈光。這樣 PhysX 一建立就是存檔狀態，不會有 kinematic 物件以高速掃過布。
2. **reset 後**才寫布的 points 和 velocities。布 body 仍然照整鏈的方式用平板建立，**rest 保持平板**，自碰撞過濾也和整鏈相同（PLASTIC.md 量過：rest 不是平板、或中途重建 body，自碰撞就會失效）。

驗證續跑真的有接上：log 會印 `[load] 續跑第 1 幀 max|布 - 存檔|`，實測 1.4~2.6 mm，是一幀內的正常運動。自穿和整鏈一樣都很低。

### 1.1 踩到的坑（都已修正並寫進程式註解）
- **速度歸零會讓布一載入就睡著。** smokeR 第 1 版把速度設成 0，結果續跑 5 s 內每筆量測逐字相同，布凍住不動。改成寫回存檔速度（最大 0.17~0.20 m/s）後就正常了。任務原本說「速度歸零可接受」，實際上不行。
- tensor API（`create_volume_deformable_body_view`）在這個版本對這塊布回傳 0 個節點，沒辦法拿來設位置（`speed2/probe_load.py --mode tensor`）。反而是 reset 後寫 USD points 有效（`--mode usd`：寫入後板子從新位置開始掉）。

### 1.2 驗證表（`--quality fast`、@x4 旗標，`python3 speed2/table3.py speed2/A speed2/R speed2/Ryn`）
| 指標 | 整鏈 A1 / A2 / A3 | 整鏈 平均 [範圍] | 續跑 R1 / R2 / R3（從 A1 的存檔） | 只續跑 yn：Ryn1 / Ryn2 / Ryn3 |
|---|---|---|---|---|
| yn 綁點 | 22 / 24 / 21 | 22.3 [21, 24] | 24 / 23 / 23 | 23 / 23 / 23 |
| yn 越線 % | 97 / 96 / 78 | 90.3 [78, 97] | 96 / 96 / 96 | 96 / 96 / 96 |
| yn 放手後 % | 96 / 95 / 77 | 89.3 [77, 96] | 95 / 95 / 94 | 95 / 95 / 95 |
| yn 他片 % | 19.9 / 10.6 / 14.6 | 15.0 [10.6, 19.9] | 20.2 / 21.0 / 20.0 | 20.5 / 20.4 / 20.4 |
| yn 杯位移 mm | 1.4 / 1.6 / 2.8 | 1.9 [1.4, 2.8] | 1.9 / 1.9 / 2.1 | 2.3 / 2.2 / 1.4 |
| 手 2 綁點 / yn lift+2 越線 | 43 / 50 / 49 ; 96 / 96 / 77% | | 46 / 49 / 51 ; 95 / 95 / 94% | 48 / 49 / 51 ; 96 / 95 / 96% |
| yp 綁點 | 19 / 19 / 21 | 19.7 [19, 21] | 18 / 19 / 18 | — |
| yp 越線 % / 放手後 % | 92 / 91 / 77 ; 93 / 92 / 77 | 86.7 ; 87.3 | 91 / 93 / 91 ; 92 / 93 / 93 | — |
| 守衛 | 都沒觸發 | | 都沒觸發 | 都沒觸發 |
| 穿杯（yn / yp / 取杯） | 0 / 0 / 0 | | 0 / 0 / 0 | 0 |
| 杯位移（yn 段） | 見上 | | 見上 | 見上 |
| 布被帶起（抬起 / 落地 %） | 33.1 / 30.8 / 36.0 ; 36.9 / 37.2 / 35.6 | 33.3 ; 36.6 | 34.8 / 30.9 / 31.4 ; 36.5 / 37.2 / 35.4 | — |
| 規劃停頓 yn / yp（s） | 1.9/1.8, 1.9/1.8, 2.5/2.4 | | 2.1/1.8, 2.2/1.8, 2.1/1.7 | 2.2, 2.2, 2.3 |
| 總牆鐘 s（含啟動） | 480 / 870 / 2041 | | 660 / 590 / 650 | 250 / 180 / 180 |
| 迴圈 wall/sim | 3.54 / 6.53 / 15.6 | | 7.76 / 6.95 / 7.60 | 6.58 / 4.42 / 4.48 |

讀法：
- **續跑應該跟它的存檔來源 A1 比。** 續跑 3 次之間的差異只來自 GPU 的非決定性，比整鏈 3 次小很多（例如 yn 越線 96 / 96 / 96，整鏈是 97 / 96 / 78）。
- A1 和續跑的差距：yn 越線 97 → 96、放手後 96 → 94~95、yp 越線 92 → 91~93、落地被帶起 36.9 → 35.4~37.2，都在「續跑 3 次自己的跳動」以內。
- 有幾格超出整鏈 3 次的範圍：yn 他片 20~21%（整鏈最高 19.9）、yp 綁 18（整鏈最低 19）、手 2 綁 51（整鏈最高 50）。這是因為整鏈只跑 3 次、樣本少，續跑值都貼近 A1 本身。
- 整鏈的 wall/sim 從 3.5 到 15.6，差這麼多是因為同時有我的 3 個模擬加上其他 agent 的模擬，GPU 被塞滿。所以牆鐘請看 §1.3 的同負載比較。

### 1.3 牆鐘：同負載對照與「1/4」
- 同一時段（另有 1~2 個其他模擬）實測：整鏈 A1 **480 s**（wall/sim 3.54）。續跑 yn 段 Tryn **170 s**（4.37），Ryn2 / Ryn3 都是 180 s。續跑整段 Trall **361 s**（4.08）。事後補跑的整鏈 Tchain **490 s**（3.61）。
- 比例（對 Tchain 490 s）：yn 段續跑 170 / 490 = **0.35**；整段續跑 361 / 490 = **0.74**。如果跟 QUALITY.md 的舊整鏈比（F3 / F4 是 829 / 793 s，含兩段 200 s 以上的規劃停頓），yn 段續跑是 **0.21**，整段是 0.44。
- **為什麼整段續跑到不了 1/4：** 存檔點 TG0 = 46.9 s，後面還有 82.7 s 的物理（yn 35.2 + yp 35.2 + 取杯 12.5），佔整鏈 130 s 物理的 64%。每 sim 秒的成本（主要是 PhysX）在續跑和整鏈是一樣的，續跑還多了約 20 s 的啟動。省下來的只有 0~47 s 的折疊 / 入箱 / 搬 / 開蓋，加上兩段規劃停頓。要再快只能 (a) 在 yp 開始前也能存檔（需要把夾爪軌跡和手 2 的綁定序列化，這次沒做），或 (b) 讓物理本身變快（QUALITY.md / SPEED.md 已說明 dt 和 solver 再放寬會傷掀開結果）。
- yn 段裡還有 8 s 是「重夾預留時間」（G_RT × grasp_retry，沒重夾時就是空等），沒有去動，因為那會改變時間表。
- 實際迭代建議：調掀 yn 的參數時，用 `--load_state ... --until yn`，約 3 分鐘一次（原本整鏈 13~20 分鐘）。調 yp / 取杯時就續跑整段，約 6 分鐘。

## 2. 抓取規劃停頓（`grasp_plan.py`）
cProfile（`speed2/prof_before.txt`、`speed2/prof_after.txt`；extract6/X2 的規劃快照，離線執行）：

| | 舊版（單執行緒） | 新版 |
|---|---|---|
| yn：rank + 候選 + gap | 217.1 + 4.1 = **221.2 s** | **2.5~3.3 s** |
| yp | 185.6 + 4.0 = **189.6 s** | **1.8~2.6 s** |
| 熱點 | `mugm.contains`（杯子 49664 面，斜射線 rtree 候選上萬）**355 s / 411 s**；他層 `closest_point` 44 s；`gap_below` 射線 11 s；每次重建 rtree | `near_count` 1.3~2.6 s、`contains_v` 1~2 s |

改了什麼（都標 `[speed2]`；函式介面不變，`wrap_vol.py` 不用改）：
1. **杯子 Trimesh 依 MUGl 內容快取。** 舊版 `gap_below` 沒傳 mugm 時，每次都重建 49664 面的 rtree。
2. **`contains_v`：杯子 contains 改用垂直射線（±z）。** 候選三角形用 2D 格（xy AABB 含點，pad 1e-5，是 rtree 的超集），交點數學沿用 trimesh 同一套（`planes_lines` / `points_to_barycentric` / `forward > -1e-6` / `unique_rows` / 正反向要一致）。離杯面不到 20 µm、或正反向不一致的點，改回原本的 `mesh.contains`。
3. **`near_count`：他層距離 < 2.5 mm 的點數。** 三角形用「形心 KD-tree，半徑 = 門檻 + 該三角形形心到頂點距離」挑候選（這是精確超集），逐對用 trimesh 同一個 `triangles.closest_point`。某頂點距離 < 門檻 − 20 µm 的點直接計入。離門檻 20 µm 內的點改用 trimesh 的 `closest_point`：trimesh 在兩面等距時會換面，回報的距離差約 1e-6，這是為了跟它逐點一致。
4. **`ray_first`（gap_below 的射線）**：不建 rtree，先用每條射線自己的線段 AABB 剔除三角形，再用同一套交點數學取第一個交點。
5. **`blas1`：rank / site_candidates 執行期間把 OpenBLAS 改成單執行緒。** numpy 預設 32 執行緒，對 (N,3)@(3,3) 這種小矩陣只會空轉：X2 yn 從 **4.6 s wall / 106 s CPU 變成 2.5 s / 2.5 s**。舊版本來也會搶同一台機器上模擬的 CPU。逐元素結果不變，因為 k 維只有 3、不會被切。

### 2.1 結果不變（`speed2/val.sh`：舊版 vs 新版，8 個 npz 快照 × yn / yp，逐欄比對 rank 60 列 + 候選 13 個）
| 快照 | 舊版 yn / yp rank s | 新版 合計 s | 排序（rows / 候選） | 不同欄位 |
|---|---|---|---|---|
| extract4/X1 plan | 74.9 / 327.5 | 1.9 / 1.9 | 相同 / 相同 | 0 |
| extract4/X3 plan | 23.4 / 339.7 | 1.3 / 2.2 | 相同 / 相同 | 0 |
| extract6/C3f plan | 195.0 / 164.5 | 2.6 / 2.3 | 相同 / 相同 | 1（候選 who） |
| extract6/X2 grip | 195.9 / 157.0 | 2.6 / 1.9 | 相同 / 相同 | 1（b 杯 12 → 13） |
| peel4/L1 plan | 9.3 / 109.6 | 1.5 / 2.0 | 相同 / 相同 | 0 |
| quality/F3 plan | 141.8 / 136.4 | 2.3 / 2.1 | 相同 / 相同 | 1（b 杯 149 → 150） |
| quality/Q1 plan | 25.8 / 147.0 | 1.7 / 2.7 | 相同 / 相同 | 0 |
| robust/r3 plan | 22.3 / 160.9 | 1.9 / 2.1 | 相同 / 相同 | 3（who ×2、b 杯 264 → 265） |

剩下的差異都是**舊版自己的不確定性**，已經驗證：
- 「b 杯」是掃掠取樣點落在杯子 STL 表面 < 1 µm 內時，trimesh 的 `contains` 會把正反向不一致的點改用 `np.random` 方向重測，所以每次跑結果不一樣。r3 那一點對同一輸入連跑 8 次舊版 `mugm.contains`，得到 True / True / False / False / False / False / True / False（`speed2/dbg2.py`）。舊版跑兩次 F3，yp v1187 也得到 149 和 150（`speed2/val/oldrerun_F3.txt`）。
- 「who」是 `max(set(wh), key=wh.count)` 遇到平手時，取決於 set 的走訪順序（字串 hash 每個行程都不同）。舊版跑兩次 r3，同樣兩欄也不同（`speed2/val/oldrerun_r3.txt`）。
- 這兩種欄位只影響 log 裡印出的 b 計數（b 本來就 > 0，ok_b 不變）和候選表的「壓住者」字樣，**排序和選點都不受影響**。

## 3. 三次分布：`run3.sh`
- `./run3.sh NAME [旗標...]` 會開 N 個模擬（預設 3 個），輸出到 `NAME/1..3`，跑完自動執行 `speed2/table3.py NAME > NAME/TABLE.md`。表的每一列是一個指標，欄位是 3 次的值加「平均 [範圍]」。
- 指標：yn / yp 綁點、越線、放手後、他片、杯位移、穿杯，手 2 綁點 / lift+2，守衛，全程自穿 / 穿杯，取杯穿杯，布被帶起（抬起 / 落地），迴圈 wall、sim 段長、wall/sim，總牆鐘（含啟動），規劃停頓，EXIT。
- **GPU 門檻 29500 MiB 照用，但實測不夠用：** 顯存快滿時開模擬，PhysX 會出現 `PxCudaContextManager out-of-memory` 或 `Scene state is corrupted`，或者乾脆不報錯也不模擬布（量測一直是平板，邊長比 [1.000,1.000]）。程式還是照跑完、EXIT 0，第一版 run3 有兩次就是這樣「跑完」的（`speed2/A_failed2`）。所以 run3 現在會：
  1. 監看 log：出現 out of memory / Scene state is corrupted、前 3 筆量測顯示布沒在動、或啟動 240 s 還沒有量測，就殺掉那一個模擬（只殺自己開的），等顯存降到 GPU_MAX − HEAD 以下再從頭重開，最多 6 次。
  2. 用跨批次共用的啟動鎖 `speed2/.run3_launch.lock`：一次只開一個，要等確認布在動才放鎖。原本兩個 run3 同時看到顯存還夠，一起開，結果一起 OOM。
- 實測（A、R、Ryn、T 共 4 批）：凍結被抓到並自動重開 10 次以上，最後 A、R、Ryn 各 3 次和 T 的 3 個單次都是正常的模擬。

## 改的檔
- `wrap_vol.py`（備份 `.before_speed`）：
  - `--save_state` / `--at` / `--save_exit` / `--load_state` / `--until yn`
  - `state_save()`；reset 前寫入其他物件狀態的 `_xf_set`、reset 後寫布
  - 主迴圈從 FR0 開始；入箱時記下相機（CAMS）
- `grasp_plan.py`（備份 `.before_speed`）：`mug_mesh`、`contains_v`、`_near_surface`、`near_count`、`ray_first`、`blas1`；rank / site_candidates 包一層 `blas1`。
- 新檔：
  - `run3.sh`
  - `speed2/table3.py`、`speed2/prof_plan.py`（離線重現規劃、cProfile、逐欄比對）、`speed2/val.sh`、`speed2/dbg2.py`、`speed2/probe_load.py`
  - `speed2/prof_before.txt`、`speed2/prof_after.txt`
- `../publish_sim_forge.sh`（備份 `.before_speed2`）：EXC 加 `--exclude 'speed2/*/' --exclude 'dev/'`。
- 開發時在 vol/dev/ 的副本做（當時交付打包 agent 在用 vol/），交付完成後套回 vol/。套回前 vol/ 沒有別人新改的內容，套回後已刪除 dev/。
- 注意：07:59 物理夾持 agent（pgrasp）在本版 wrap_vol.py 上又加了 `--pick_mode wide`（備份 `wrap_vol.py.before_pgrasp`，裡面已經有 [speed2] 的改動），所以兩邊的改動都還在。08:05 之後開的驗證模擬（A2、Ryn、T）跑的是含 pgrasp 改動的版本，它的預設值等於舊行為。
