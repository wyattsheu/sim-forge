# 包裝方法開發(wrap_method_dev)

用氣泡布 / 薄膜把物件包好、放進紙箱的模擬。這個資料夾的目的是**開發新的包法**:
給定「被包物」、「紙箱大小(包好後要放得進的範圍)」、「包材」,決定怎麼包,再用現有的包材模型模擬、驗收。

目前只有**一種寫死的包法**(四片對折包,§3)。被包物和紙箱已經可以從設定檔換(§2),但包法本身還沒有依物件 / 紙箱調整。

程式來自 [`fr3_bubblewrap_pack_handoff_20261007`](../fr3_bubblewrap_pack_handoff_20261007)(交付版)和
[`fr3_bubblewrap_pack_20261007`](../fr3_bubblewrap_pack_20261007)(開發紀錄),是**複製**過來的,原資料夾沒動。改了哪些見 §10。

---

## 0. 快速開始

```bash
cd sims/wrap_method_dev
./run_wrap.sh --check                  # 確認找得到 Isaac Sim、GPU
./run_wrap.sh                          # 跑一次:預設 case(馬克杯 + 270×230×131 紙箱),volume 包材,到入箱關蓋為止
./run_wrap.sh --live                   # 同上,但用 WebRTC 即時看(§5)
./run_wrap.sh --stop                   # 停掉 --live
```

輸出在 `out/<case>_<engine>/`:`wrap.mp4`(影片)、`wrap.npz`(布和杯子的頂點)、`wrap_vol.log`(結尾有驗收表,§7)。

---

## 1. 資料夾內容

```
wrap_method_dev/
├── README.md
├── run_wrap.sh                ★ 跑包裝模擬(讀 case 檔;--live = WebRTC 即時看)
├── open_in_webrtc.sh          ★ 用 WebRTC 開「場景 USD」看(雙臂工作站 + 紙箱 + 包裹,可以滑鼠拖)
├── open_in_ui.sh              同上,本機 GUI 版(要有螢幕)
├── find_isaac.sh              自動找 Isaac Sim(二進位版 / Docker / pip 版)
├── cases/                     ★ 一個檔 = 被包物 + 紙箱 + 包材參數 + 包法參數
│   └── mug_270x230x131.env      目前的定案組合
├── assets/
│   ├── items/                   ★ 被包物 STL(mug.stl:躺平 133 × 107 × 93 mm)
│   ├── cartons/                 ★ 紙箱 USD + 同名 .meta.json(carton_270x230x131 = 定版紙箱)
│   └── textures/                bubble_normal.png(泡泡布外觀)
├── methods/                   ← 新的包法寫在這裡(目前空的,見 §8)
├── volume/                    包材 B:volume deformable 薄板(4 mm 實體厚度)—— run_wrap.sh 預設用這個
│   ├── wrap_vol.py              主程式:折 → 收耳 → 入箱 → 關蓋 → 搬箱 → 開蓋,一次模擬跑完(標記 VPACK-1~13)
│   ├── volcommon.py、vol_pen.py  建板、材質、量測
│   ├── layer_order.py、layer_gap.py   最外層是哪片、層間距
│   ├── fold_variants.py、VARIANTS.csv  批次跑多種折序 + 結果(24 種折序 + 12 組隨機)
│   ├── grasp_plan.py、cloth_iface.py、grip/   掀包材(抓取段)用,wrap_vol.py 會 import
│   ├── probe_vol_*.py、probe_plastic.py        單項探針(建板、折疊放手、疊層、回彈)
│   └── mug.stl、carton_w131.usd …   → symlink 到 ../assets(腳本的預設檔名)
├── surface/                   包材 A:surface deformable 薄膜(交付場景裡那包是用這個做的)
│   ├── wrap_sim.py              主程式(標記 PACK-1~9);要分四段模擬接力
│   ├── run_demo.sh              原版四段指令(固定素材;run_wrap.sh --engine surface 是讀 case 的版本)
│   ├── grip_common.py、crease_physics.py
│   ├── floor_edges.json         ⚠ 只對「馬克杯 + 400 布」有效;run_wrap.sh 不用它
│   └── layer_gap.py、chain_pen.py、edge_report.py、selfcheck.py   量測 / 一致性檢查
├── carton/                    紙箱:生成器 + 蓋子摺痕物理
│   ├── make_carton.sh           ★ 任意尺寸紙箱:./make_carton.sh <外長> <外寬> <高>(mm)
│   ├── make_carton_P.py         紙箱生成器本體
│   ├── make_definitive.sh       定版紙箱的原始指令(寫死 /isaac-sim/python.sh,留作紀錄)
│   ├── carton_sweep.py          檢查蓋子 0~180° 不穿箱壁(純 numpy)
│   ├── crease_co7b.py           ★ 目前用的蓋子摺痕(力矩式彈塑性);open_in_webrtc.sh 會自動載入
│   ├── crease_physics.py        摺痕模型 library
│   ├── crease_plastic.py、crease_hold_ui.py、lid_latch.py   舊版蓋子模型(LID_MODE=plastic / latch)
│   └── co7b_check.py、lid_test.py   蓋子測試
├── physics/                   完整場景(雙臂工作站)的建置與物理測試
│   ├── build_full_scene.py      包裹 npz + 紙箱 + 杯子 → 放進雙臂場景
│   ├── build_phys_scene.py      加物理:包材 deformable、杯子剛體、PhysicsScene
│   ├── patch_scene.py           牆 / 蓋墊片、蓋子慣量修正
│   ├── verify_phys_scene.py     場景測試 A 靜置 / B 搬運 / Bm 滑鼠拖 / C 壓蓋
│   └── scene_physics_check.py、ui_path_check.py
├── viewer/                    串流 / GUI 用的開機腳本
│   ├── live_run.py              --live 用:不改包裝腳本,把它的 SimulationApp 換成會開 WebRTC 的版本
│   ├── webrtc_boot.py、ui_boot.py   open_in_webrtc.sh / open_in_ui.sh 的開機腳本
│   └── click_to_ros.py、ros_click_listener.py   Ctrl + 點擊 → 3D 點 → ROS 2
└── docs/
    ├── FOLD_DIVERSITY.md        ★ 24 種折序哪些過、為什麼掛
    ├── PITFALLS.md              踩過的坑(先讀)
    ├── CREASE_MECHANICS.md      紙箱摺痕力學
    ├── ARM_INTERFACE.md         手臂端 ↔ 包材端的座標與交換資料
    └── SPEED.md、DAMPING.md      模擬加速、阻尼調參
```

---

## 2. 換被包物、換紙箱(擴展性)

**被包物和紙箱都不寫在程式裡,寫在 case 檔。** 新增一個組合 = 新增一個 case 檔,程式不用動。

```bash
cp cases/mug_270x230x131.env cases/bowl_320x260x160.env
# 編輯:ITEM=assets/items/bowl.stl、CARTON=assets/cartons/carton_320x260x160.usd、VOL_ARGS=...
./run_wrap.sh --case cases/bowl_320x260x160.env
```

case 檔的欄位(`cases/mug_270x230x131.env` 有註解):

| 欄位 | 意義 |
|---|---|
| `ITEM` | 被包物 STL(mm 或 m 自動判斷) |
| `CARTON` | 紙箱 USD;旁邊要有同名 `.meta.json`(內腔、牆高、鉸鏈高度全部從這裡讀,程式不寫死) |
| `TEX` | 包材外觀貼圖 |
| `ENGINE` | `volume`(預設)或 `surface` |
| `VOL_ARGS` | 給 `volume/wrap_vol.py` 的包材 + 包法旗標(§4) |
| `SURF_ARGS` | 給 `surface/wrap_sim.py` 的旗標 |

### 2.1 新的紙箱尺寸

```bash
cd carton
./make_carton.sh 320 260 160          # 外長 × 外寬 × 高(mm),長邊沿 x → ../assets/cartons/carton_320x260x160.usd + .meta.json
./make_carton.sh 320 260 160 120      # 指定下層蓋長度 120 mm(預設跟定版同比例)
python3 carton_sweep.py ../assets/cartons/carton_320x260x160.meta.json   # 蓋子不穿牆,要 0/361
```

板厚、蓋子縫隙、密度等其他參數 = 定版值。已確認:`make_carton.sh 270 230 131` 的參數產生的 meta 跟定版紙箱 20 個衍生量完全相同。

### 2.2 新的被包物

STL 放進 `assets/items/`,case 檔 `ITEM=` 指過去。**目前要注意兩件事**:

1. **物件擺放的姿態是為 mug.stl 寫死的**(`VPACK-1` / `PACK-1`:躺平、杯口 +y、杯耳 +x)。
   別的物件套同一組旋轉不一定合理。這是第一個該改成可設定的地方(例如在 case 檔加姿態欄位)。
   volume 版目前只能額外 `--mug_yaw_deg` 繞 z 轉。
2. 參數名稱叫 `--mug`、程式裡變數叫 mug,但其實就是「被包物」,任何 STL 都可以。
   折線是用物件的 **bounding box** 算的(`VPACK-2`),不看實際形狀。

### 2.3 哪些已經跟著換、哪些還沒有

| | 換被包物 | 換紙箱 |
|---|---|---|
| 讀檔、建碰撞 | ✅ | ✅(內腔 / 鉸鏈從 meta 讀) |
| 折線、折邊長度 | ✅ 由物件 bbox 算 | — |
| 收耳的目標寬度 | — | ✅ 紙箱內腔 − 3 mm |
| 入箱位置 | ✅ 置中到箱底 | ✅ |
| 物件姿態 | ❌ 寫死給杯子 | — |
| 布的大小 | ❌ case 檔手動給 | ❌ 沒有依紙箱推算 |
| 疊層高度、尖端越線量 | ❌ 為杯子調的值 | — |
| 驗收(超出內腔) | ✅ | ✅ |

❌ 的就是要開發的部分(§8)。

---

## 3. 現在的包法:四片對折包

方布攤平,物件放中央,四邊依序往上折、蓋過物件頂面(不剪布,像包禮物),然後收耳、整包放進紙箱、關蓋。

```
 ┌───────────────┐   1. 物件躺平放在布中央                                    VPACK-1
 │      yp       │   2. 折線 = 物件 bbox 外推 margin + wall                    VPACK-2
 │   ┌───────┐   │   3. 布分成 xp / xn / yp / yn 四片(角落歸超出較多的那片)  VPACK-4
 │xn │ 物件  │ xp│   4. 依折序一次折一片;隱形的錨抓住布邊走兩段圓弧:          VPACK-3,5~9
 │   └───────┘   │        a. 繞底部折線轉 90°,布邊立起貼物件側面
 │      yn       │        b. 繞物件頂部再轉 90°,蓋過頂面;後折的疊在上面
 └───────────────┘   5. 四面隱形側板把包裹夾到紙箱內腔大小(收耳)            VPACK-10
  折序 xp→xn→yp→yn    6. 整包移進紙箱 → 關下層蓋 fx → 關上層蓋 fy             VPACK-11~12
                      7. 放開錨點,重力和摩擦接手 → 搬箱 → 開蓋;驗收          VPACK-13
```

後折的 ±y 在最外層,開箱時先開 ±y 蓋,第一眼看到、手臂先掀的就是它。

### 3.1 步驟對照表(程式位置)

標記是註解 `★[VPACK-n]` / `★[PACK-n]`,可以 `grep -n "★\[VPACK-" volume/wrap_vol.py` 找。

| 步驟 | volume `wrap_vol.py` | surface `wrap_sim.py` |
|---|---|---|
| 物件姿態(⚠ 寫死給杯子) | `VPACK-1` [L253](volume/wrap_vol.py#L253) | `PACK-1` [L365](surface/wrap_sim.py#L365) |
| 折線、折邊長、需要的布大小 | `VPACK-2` [L262](volume/wrap_vol.py#L262) | `PACK-2` [L378](surface/wrap_sim.py#L378) |
| 折序 | `VPACK-3` [L162](volume/wrap_vol.py#L162)(`--fold_order`) | `PACK-3` [L235](surface/wrap_sim.py#L235)(寫死) |
| 布分片 | `VPACK-4` [L343](volume/wrap_vol.py#L343) | `PACK-4` [L930](surface/wrap_sim.py#L930) |
| 錨點挑選:先折的軸抓整條邊;後折的軸只抓還貼地那段 | `VPACK-5` [L349](volume/wrap_vol.py#L349) | `PACK-4` |
| 每片終點高度:物件頂 + 已疊層數 × 層厚;布不夠長會標 `★ infeasible` | `VPACK-6` [L373](volume/wrap_vol.py#L373) | `PACK-5`(`--layer_mm`、`--hold_mm`) |
| 錨點軌跡(兩段圓弧,半徑 = 材料長,不拉伸布) | `VPACK-7/8/9` [L408](volume/wrap_vol.py#L408) | `PACK-5` [L1290](surface/wrap_sim.py#L1290) |
| 收耳 | `VPACK-10` [L490](volume/wrap_vol.py#L490) | 無 |
| 全程時間表 | `VPACK-11` [L700](volume/wrap_vol.py#L700) | `PACK-6` [L1462](surface/wrap_sim.py#L1462) |
| 入箱(剛性移動,不是「放」的動作) | `box_off()`(VPACK-11 下方) | `PACK-7` [L643](surface/wrap_sim.py#L643) |
| 關蓋:下層 fx 先、上層 fy 後 | `VPACK-12` [L791](volume/wrap_vol.py#L791) | `PACK-8/9` [L534](surface/wrap_sim.py#L534)、[L1431](surface/wrap_sim.py#L1431) |
| 驗收:逐頂點比紙箱內腔 | `VPACK-13` [L836](volume/wrap_vol.py#L836) | log「真的入箱了嗎」 |

### 3.2 兩種包材模型

| | volume(預設) | surface |
|---|---|---|
| 模型 | 四面體薄板,真實 4 mm 厚 | 三角網格薄殼,厚度只是碰撞參數 |
| 流程 | 一次模擬跑完 | 四段模擬用 npz 接力(c1 折左右 → c2 折前後 → box 入箱關蓋 → mb_open 搬箱開蓋) |
| 可調的包法參數 | 多(§4) | 少,折序寫死 |
| 用在 | 掀包材(手臂)開發 | 交付場景 `scene_final.usd` 裡那包 |

新方法建議以 volume 版為執行器。

---

## 4. 在哪裡調整包法

### 4.1 不改程式:case 檔的 `VOL_ARGS`(或 `./run_wrap.sh -- <旗標>` 臨時加)

| 想調的 | 旗標 | 目前值 | 影響的步驟 |
|---|---|---|---|
| 布大小 | `--sheet_mm`,或長方形 `--sheet_x_mm` `--sheet_y_mm` | 500 | VPACK-2、6(太小 → infeasible) |
| 折序 | `--fold_order xp,xn,yp,yn`(四片任意排列) | xp,xn,yp,yn | VPACK-3、5;結果見 `docs/FOLD_DIVERSITY.md` |
| 折線離物件多遠 | `--margin`(bbox 外擴)、`--wall`(再外推) | 0.012、0.006 m | VPACK-2 |
| 尖端越過中線多少 | `--tip_over_mm` | 30 | VPACK-6、7 |
| 層與層的高度 | `--tip_extra yp:2`(某片終點加高) | 0 | VPACK-6 |
| 收耳 | `--tuck 0/1`、`--squeeze_mm`、`--squeeze_t` | 1、3、2.5 | VPACK-10 |
| 每片折多快 | `--fold_span`、`--fold_hold`、`--slow yp:1.5` | 3.0、0.5 s | VPACK-11 |
| 物件在布上的位置 / 轉向 | `--mug_off_mm dx,dy`、`--mug_yaw_deg` | 0,0、0 | VPACK-1、2 |
| 關蓋速度 | `--lid_span`、`--open_span` | 4、3 s | VPACK-11 |
| 跑到哪 | `./run_wrap.sh --until fold / box / move / all` | box | — |
| 包材 | `--young`、`--poisson`、`--thick_mm`、`--areal`、`--fric` | 2e3、0.45、4、0.1、0.8 | — |

全部旗標:`volume/wrap_vol.py` 開頭的 argparse(一行一個,有說明)。

### 4.2 要改程式

| 想做的 | 改哪裡 |
|---|---|
| 物件姿態可設定 | `VPACK-1`(和 `PACK-1`) |
| 折線不平行 bbox(對角包等) | `VPACK-2`、`VPACK-4`(分片規則)、`VPACK-7/8`(軌跡的旋轉軸) |
| 不是四片(只折兩片、捲包、多層布) | `VPACK-4/5`(分片、錨點)、`VPACK-6`(終點)、`VPACK-11`(時間表) |
| 依紙箱自動決定布大小 / 收耳量 | 在 `methods/` 算好,輸出成 §4.1 的旗標(建議做法,見 §8) |
| 真的「放」進箱子 | `VPACK-11` 的 into box 段、`box_off()` |

---

## 5. 跑起來看(WebRTC)

有兩種「看」:

| 想看什麼 | 指令 |
|---|---|
| **包裝過程**(布怎麼折、怎麼入箱) | `./run_wrap.sh --live [--case ...] [--until ...]` |
| **做好的場景**(雙臂工作站 + 紙箱 + 包裹,可以滑鼠拖箱子、掀蓋子) | `./open_in_webrtc.sh [場景.usd]`(預設:交付包的 `scene_final_phys.usd`) |

### 5.1 看包裝過程:`run_wrap.sh --live`

```bash
./run_wrap.sh --live --check                       # 先看偵測結果:Isaac Sim、要連的 IP、port、GPU
./run_wrap.sh --live                               # 背景執行,印出要連的 IP / port 和 log 位置
tail -f out/mug_270x230x131_volume/live.log        # 等到出現 [live] STREAMING 再連(第一次啟動可能要幾分鐘)
./run_wrap.sh --stop                               # 停
```

- 用 **Isaac Sim WebRTC Streaming Client**(NVIDIA Isaac Sim 下載頁的桌面程式)輸入印出來的 IP → Connect。
- 畫面切到模擬自己的相機 `/World/cam`(跟輸出的 wrap.mp4 同一個視角);在 client 裡可以換相機、轉視角。
- 模擬速度比真實時間慢(每一格都要算布),畫面會是慢動作。
- **跑完後物理暫停、畫面保留**,可以繼續轉視角看結果,直到 `--stop`。`LIVE_HOLD=0` 則跑完就關。
- 腳本出錯時串流會直接關,錯誤在 `live.log`。
- surface 版(`--engine surface --live`)是四段各自啟動,每段之間串流會斷,要重新連;建議用 volume 版看。
- 包裝腳本本身沒有改:`viewer/live_run.py` 在執行前把 `SimulationApp` 換成會開串流的版本。

### 5.2 看做好的場景:`open_in_webrtc.sh`

```bash
./open_in_webrtc.sh --check                        # 偵測結果
./open_in_webrtc.sh                                # 交付包的 scene_final_phys.usd
./open_in_webrtc.sh path/to/your_scene.usd         # 自己做的場景(§6.4)
./open_in_webrtc.sh --stop
```

log 在 `logs/webrtc.log`,等 `[handoff] READY` 再連。左鍵直接拖箱子 / 蓋子;Ctrl + 點擊會把 3D 點發佈到 ROS 2 `/clicked_point`。
蓋子模型預設 co7b(`carton/crease_co7b.py`);`LID_MODE=plastic` / `latch` / `spring` 換舊版。詳細操作見交付包 README §3、§4。
本機有螢幕的話可以用 `./open_in_ui.sh` 開 GUI。

### 5.3 共通設定

| 環境變數 | 用途 |
|---|---|
| `WEBRTC_IP` | client 連的 IP。沒設 = 本機第一個非內網 IPv4(內網 / VPN 要自己設) |
| `WEBRTC_PORT` | signaling TCP port,預設 49100,被占用自動往上找 |
| `CUDA_VISIBLE_DEVICES` | 指定 GPU(機器共用時) |
| `ISAAC_SIM_PATH` / `ISAAC_SIM_PIP_ENV` | 找不到 Isaac Sim 時手動指定(見 `find_isaac.sh`) |

防火牆要開 **TCP signaling port**(49100 起)和 **UDP 47998**(media)。同時只能有一個串流用同一組 port;`--check` 會印出實際要用的 port。

---

## 6. 資源

### 6.1 包材參數(定案值)

| | volume 薄板 | surface 薄膜 |
|---|---|---|
| 楊氏模數 / Poisson | 2e3 Pa / 0.45 | 2e4 Pa / 0.45 |
| 厚度 | 4 mm | 4 mm(碰撞厚度) |
| 彎曲 | 由厚度決定 | `--bend 4` |
| 密度 | 面密度 0.1 kg/m² | 100 kg/m³(400 布 ≈ 65 g) |
| 網格 | 35 × 35 × 1 六面體 → 四面體 | 35 × 35 頂點 |
| 摩擦 / contact / rest offset | 0.8 / 2 mm / 0.5 mm | 0.8 / 5 mm / 1 mm |
| solver iterations / dt | 128 / 1/240 s | 64 / 1/120 s |
| 布 | 500 × 500 mm | 400 × 400 mm |

調參紀錄:`docs/DAMPING.md`、`docs/SPEED.md`、`../fr3_bubblewrap_pack_20261007/work/REPORT_THICKNESS.md`、`EXPERIMENTS.md`。

### 6.2 被包物

`assets/items/mug.stl`:馬克杯,躺平後 133 × 107 × 93 mm。包裝模擬時固定不動(kinematic),入箱後才變成動態剛體。

### 6.3 紙箱

- 定版 `assets/cartons/carton_270x230x131`:外徑 270 × 230 × 131 mm、板厚 3 mm、內腔 ±132 × ±112 mm;
  四片蓋:下層 fxp / fxn(長 115 mm,鉸鏈 z 123 mm)、上層 fyp / fyn(鉸鏈 z 129.5 mm);密度 200 kg/m³,箱體是動態剛體。
- 其他尺寸:`carton/make_carton.sh`(§2.1)。
- 蓋子摺痕物理:包裝模擬裡蓋子是 kinematic(照角度轉);放到場景裡才用 `carton/crease_co7b.py` 的彈塑性摺痕。
  力學與參數見 `docs/CREASE_MECHANICS.md` 和交付包 README §3.4。

### 6.4 把包好的結果做成場景

`physics/` 的腳本預設讀「上一層的 `scene_final_*.usd`」,在這裡要給交付包的路徑:

```bash
cd physics
HO=../../fr3_bubblewrap_pack_handoff_20261007
$ISAAC_PYTHON build_full_scene.py --scene $HO/build/stationary_ai_carton_scene_flat.usd \
    --carton ../assets/cartons/carton_270x230x131.usd --wrap <surface 版的 wrap.npz> \
    --mug ../assets/items/mug.stl --out ../out/scene/scene_final.usd
$ISAAC_PYTHON build_phys_scene.py --scene $HO/scene_final_ui.usd --out ../out/scene/scene_final_phys.usd
$ISAAC_PYTHON verify_phys_scene.py $HO/scene_final_phys.usd --test A        # A / B / Bm / C
```

(`$ISAAC_PYTHON`:`source ../find_isaac.sh && find_isaac` 之後就有。)
⚠ `build_full_scene.py` 吃的是 **surface 版**的 npz(`sheet` 頂點,35×35);volume 版的輸出格式不同,還沒有轉換工具。
各測試的意義與目前數字:交付包 README §8。

### 6.5 已有的實驗數據

- `volume/VARIANTS.csv` + `docs/FOLD_DIVERSITY.md`:24 種折序嚴格通過 9 種、物理通過 20 種;不收耳的隨機組全部 y 向超出紙箱。
  **建議新方法的評估沿用這個 CSV 的欄位。**
- `../fr3_bubblewrap_pack_20261007/work/RUNS.csv`:surface 版 122 次模擬紀錄。

---

## 7. 驗收指標

在 `wrap_vol.log` 結尾,批次跑時 `fold_variants.py` 會整理進 CSV。

| 指標 | CSV 欄位 | 及格 |
|---|---|---|
| 布 / 物件超出紙箱內腔的頂點數 | `out`(x / y / 箱口分開) | 0 |
| 布穿進物件 | `mugpen_max` | 0 |
| 布自己互穿峰值 | `self_max` | < 20 |
| 四面體反轉 | `inv_max` | 0 |
| 邊長比(布被拉長 / 壓縮多少) | `edge_lo`、`edge_hi` | 0.50 ~ 1.65 |
| 布搆不到物件頂 | log `★ infeasible` | 不出現 |
| 最外層是哪片 | `outer_layer` | 手臂要掀的那片 |
| 搬箱後 | `--until all` 後的超出點數、布相對箱子的位移 | 0、幾 mm |

---

## 8. 建議的開發方向

現在「決定怎麼包」和「模擬」混在一支 2000 行的腳本裡。建議把**決定怎麼包**拆出來(純幾何,不用 GPU,秒級,可以寫單元測試):

```
case 檔(被包物、紙箱、包材)
        │
        ▼
methods/<包法>.py ──► 包裝計畫 plan.json(布大小、物件位置姿態、每片折線 / 折序 / 終點、收耳…)
        │
        ▼
執行器:先把計畫翻成 wrap_vol.py 的旗標(§4.1);旗標表達不了的再擴充 wrap_vol.py
        │
        ▼
wrap.npz / log ──► 評估(§7)──► CSV(沿用 VARIANTS.csv 欄位)
```

建議順序:

1. 跑一次 `./run_wrap.sh` 和 `./run_wrap.sh --live`,讀 §3、`docs/PITFALLS.md`、`docs/FOLD_DIVERSITY.md`。
2. 把**現在的包法寫成第一個方法**:從 STL + 紙箱 meta 算出計畫,要能重現現在的數字
   (mug.stl、margin 12 / wall 6 mm → 折線 CX 84.63、CY 71.5 mm,見 `VARIANTS.csv`),並自動選出夠用的最小布。
3. **可行性檢查**(不用模擬):布夠不夠長、包好的外框進不進得了紙箱內腔、疊幾層、會不會超出箱口。
4. **物件姿態可設定**(§2.2),換 2~3 種物件、2~3 種紙箱(`make_carton.sh`)測試。
5. **新包法**:依物件形狀 / 紙箱大小選包法、選折序、選布大小。
6. **批次評估**:仿 `volume/fold_variants.py`。

規則:新程式放 `methods/`(或自己開子資料夾)。`volume/`、`surface/`、`carton/`、`physics/` 是參考實作,要改先討論。
新增被包物放 `assets/items/`、紙箱放 `assets/cartons/`、組合寫成 `cases/*.env`。

---

## 9. 環境

- Isaac Sim:`find_isaac.sh` 會自動找(`/isaac-sim` 等二進位版、Docker 內、pip venv)。所有腳本都透過它,不寫死路徑。
  原本的開發與定案數字是在 **Isaac Sim 5.1** 上量的;這台主機(acm-803-1)目前偵測到的是 pip 版 **6.0**(`/mnt/HDD4/wyattsheu/env_isaaclab`),
  學生容器是 6.1(見 `~/ISAAC_SIM_SETUP_RTX_PRO_6000.md`)。
- **在 6.0 上實測過(2026-10-15)**:`./run_wrap.sh --live --until fold`(volume)串流開得起來、viewport 切到模擬相機、跑完停在最後畫面;
  折 + 收耳 + 入箱的結果:布 / 杯超出內腔 0、布穿杯 0、自穿峰值 6、邊長比 0.56~1.65,跟 5.1 的紀錄(`VARIANTS.csv`)同一個範圍。
  `./run_wrap.sh --engine surface --until box`(c1 → c2 → box,約 5 分鐘):布 / 杯超出內腔 0。
  log 裡大量的 `PxRigidDynamic::setLinearVelocity: Body must be non-kinematic` 是對 kinematic 錨設速度的警告,不影響結果。
  `./run_wrap.sh --until all`(volume 全程,約 10 分鐘):關蓋後、搬前、搬後 布 / 杯超出內腔都是 0,布穿杯 0,邊長比 0.44~1.59;
  **開蓋後**有 33 個布頂點高於箱口(最高 153 mm,箱口 134)—— 蓋子打開後包材沒有塑性、會彈起來,這是目前包材模型的已知現象。
  `./open_in_webrtc.sh`(交付包場景):開檔、載入 co7b 蓋子模型、`[handoff] READY`。
  沒在 6.x 上跑過的:`fold_variants.py` 批次、`physics/` 的場景重建(交付包 CHANGELOG 記錄過 6.0 重建出來的杯子姿態跟 5.1 版不同)。
  WebRTC client 端沒有實測(伺服器上沒有 client)。
- GPU:每次模擬約 5~8 GB 顯存、2~5 分鐘。GPU deformable **不是決定性的**,同參數重跑會差幾 mm。
- 腳本都假設**在自己的資料夾裡執行**;`run_wrap.sh` 會自己切過去。
- 系統 `python3`(不用 Isaac)可以跑:`carton/carton_sweep.py`、`volume/vol_pen.py --selftest`、`layer_gap.py`、`edge_report.py`。

---

## 10. 來源與修改紀錄

| 這裡 | 來自 |
|---|---|
| `surface/`、`carton/`、`physics/`、`viewer/`(部分)、`open_in_*.sh`、`find_isaac.sh` | `fr3_bubblewrap_pack_handoff_20261007/` |
| `volume/`、`docs/FOLD_DIVERSITY.md`、`SPEED.md`、`DAMPING.md` | `fr3_bubblewrap_pack_20261007/vol/` |
| `surface/` 量測工具、`carton/carton_sweep.py`、`docs/PITFALLS.md` | `fr3_bubblewrap_pack_20261007/work/` |
| `docs/ARM_INTERFACE.md` | `fr3_bubblewrap_pack_20261007/arm/INTERFACE.md` |
| `docs/CREASE_MECHANICS.md` | `carton_plastic_crease_20261009/docs/` |

複製後改過的地方(其餘與原檔相同):

- `volume/wrap_vol.py`、`surface/wrap_sim.py`:加 `★[VPACK-n]` / `★[PACK-n]` 註解行。
- `volume/wrap_vol.py`、`probe_*.py`:`SETTING_ENABLE_DEFORMABLE_BETA` 加 `hasattr` 判斷(6.x 沒有這個設定),跟 `surface/wrap_sim.py` 原本的寫法一樣。
- `volume/wrap_vol.py`、`surface/wrap_sim.py`:`V.ptp(0)` → `np.ptp(V, axis=0)`(Isaac Sim 6.x 帶的 NumPy 2 拿掉了 `ndarray.ptp`)。
- `carton/make_carton_P.py`:補 `--reach_lower`(下層蓋長度)。repo 裡的生成器原本沒有這個參數,但定版紙箱是用它做的;預設值 = 舊行為。
- `viewer/webrtc_boot.py`、`ui_boot.py`:蓋子摺痕腳本改從 `carton/` 載入(`WRAPDEV_CARTON_DIR`)。
- `open_in_webrtc.sh`、`open_in_ui.sh`:路徑改到本資料夾;加 Isaac Sim 6.x 的串流 port 設定。
- 新增:`run_wrap.sh`、`cases/`、`carton/make_carton.sh`、`viewer/live_run.py`。
- 素材改放 `assets/{items,cartons,textures}/`;`surface/`、`volume/` 裡用 symlink 保留原本的預設檔名。
