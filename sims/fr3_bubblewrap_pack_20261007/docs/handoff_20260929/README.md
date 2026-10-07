# 氣泡布包材 — 包裝 / 入箱 / 開箱 模擬包

用 Isaac Sim 的 **surface deformable**(布)把一個馬克杯包起來、壓實、放進瓦楞紙箱、關上蓋子,
並且能反過來播放開箱。所有幾何都是模擬出來的,不是把布擺到定位。

- 環境:Isaac Sim **5.1**(需要開啟 deformable beta),單張 GPU,headless 離線算圖
- 一次完整流程約 8 分鐘

---

## 1. 目錄

```
README.md        這份:是什麼、怎麼跑、實測結果、已知限制
CHANGELOG.md     ★ 版本紀錄:每個資產改了什麼/為什麼/用什麼驗的/驗出來的數字
ADAPTING.md      ★ 怎麼改成別的尺寸/別的物品,以及改完要重驗哪幾項
scripts/         模擬與檢查腳本(見 §4)
carton/          紙箱 USD + 參數 + 產生器;superseded/ 是被取代的舊箱
states/          各階段的布頂點狀態(.npz),可以從中間接續
assets/          泡泡布法線貼圖、馬克杯 STL、施力點索引表
videos/          成果影片(1→4 是流程順序)
scene_fixed.usd  組好的完整場景(機械手臂 + 桌子 + 紙箱 + 包裹在箱內 + 杯子)
```

`states/` 的四個狀態,依流程順序:

| 檔案 | 是什麼 |
|---|---|
| `folded_4sides.npz` | 四折包好,還沒壓實 |
| `packed_pressed.npz` | 六面壓實之後的成品包裹(**最常用的接續點**) |
| `packed_in_box.npz` | 放進紙箱、四片蓋關好 |
| `lifted.npz` | 提杯測試結束、整包懸在空中 |

## 2. 影片

| 檔案 | 內容 |
|---|---|
| `videos/1_wrap_and_press.mp4` | 從攤平的布開始:四折包住杯子 → 六面壓實 |
| `videos/2_pack_into_carton_FIXED.mp4` | 放進紙箱 → 關上四片蓋(**修正後**的版本) |
| `videos/3_lift_by_mug_TEST.mp4` | 驗證用:包好之後直接把杯子提起 200mm,看包材跟不跟 |
| `videos/4_unbox_and_flatten.mp4` | 反過來:開蓋 → 逆著折序掀開包材 → 拿出箱外攤在地上 |
| `videos/full_pipeline.mp4` | 含機械手臂的完整場景 |

影片底部固定壓著該次跑的**參數字串**(布尺寸、材料模數、solver 迭代數等)。
要重現某支影片,直接讀那一行,不要憑印象帶預設值。

## 3. 怎麼跑

把 `scripts/`、`assets/`、`carton/` 的內容放在同一個工作目錄下,然後:

```bash
# (a) 包起來:從攤平的布四折包住杯子(分兩段,後兩折的施力點不同)
/isaac-sim/python.sh wrap_sim.py --tex bubble_normal.png --wrapsim \
    --wrap_edge --wrap_n 2 --layer_mm 8 --young 2e4 --bend 4 --out out_c1

/isaac-sim/python.sh wrap_sim.py --tex bubble_normal.png --wrapsim --stage2 \
    --init_npz out_c1/wrap.npz --layer_mm 8 --young 2e4 --bend 4 --out out_c2

# (b) 六面壓實成長方體
/isaac-sim/python.sh wrap_sim.py --tex bubble_normal.png --wrapsim \
    --init_npz out_c2/wrap.npz --layer_mm 12 --young 2e4 --bend 4 \
    --press6 250,210,115 --out out_c3

# (c) 入箱 + 關蓋
/isaac-sim/python.sh wrap_sim.py --tex bubble_normal.png --wrapsim \
    --init_npz out_c3/wrap.npz --carton carton_w131.usd --close_lid \
    --layer_mm 12 --young 2e4 --bend 4 --out out_box

# (d) 開箱 + 完整攤平(反過來播)
/isaac-sim/python.sh wrap_sim.py --tex bubble_normal.png --wrapsim \
    --init_npz packed_in_box.npz --carton carton_w131.usd \
    --floor_edges floor_edges.json --young 2e4 --bend 4 --unbox --out out_unbox

# (e) 驗證:包好之後把杯子提起來,看包材跟不跟
/isaac-sim/python.sh wrap_sim.py --tex bubble_normal.png --wrapsim \
    --init_npz packed_pressed.npz --young 2e4 --bend 4 \
    --lift_mug 0.20 --lift_t 6 --lift_wait 3 --out out_lift
```

`states/` 裡的 `.npz` 可以直接餵給 `--init_npz`,跳過前面的階段。

**三個容易漏掉的旗標**

- `--young 2e4 --bend 4` — 腳本預設是 `5e4 / 2e3`,**不是**這組。
  尤其 `bend` 預設 2e3 會讓布直接睡死(實測折疊等於沒跑)。
- `--floor_edges floor_edges.json` — `--unbox` 需要,漏掉直接 `NameError: SIDE2`。
- `--tex bubble_normal.png` — 沒有它就沒有泡泡外觀。

## 4. 腳本

**模擬**

| 檔案 | 用途 |
|---|---|
| `wrap_sim.py` | 主程式:折、壓、入箱、關蓋、開箱、提杯測試,全部在這一支 |
| `build_full_scene.py` | 組完整場景(手臂 + 桌子 + 紙箱 + 包裹 + 杯子) |
| `crease_physics.py` | 紙板摺痕的彈塑性模型(蓋子折過會留角度,不會彈回全開) |
| `foam_pack.py` | 另一種包材:volume FEM 泡棉殼(對照組) |
| `shot_full.py` / `make_full_video.py` | 出圖、出影片 |

**檢查 —— 全部純 CPU,不需要 GPU**

| 檔案 | 檢查什麼 |
|---|---|
| `carton_sweep.py` | **蓋子會不會穿箱壁**。解析掃掠 0~180°,每 0.5° 一格 |
| `chain_pen.py` | **布會不會穿物品**。吃 `traj.npz`,邊級別判定 |
| `check_place.py` | 布 / 物品有沒有超出紙箱內腔 |
| `check_flap.py` | 布和四片蓋子各自的 bbox 有沒有重疊 |
| `fold_pen.py` | **布自己的自穿模**(Möller–Trumbore 線段對三角形) |
| `insp_carton.py` / `insp_scene.py` | 印出每片蓋的鉸鏈位置與姿態、場景座標方向 |

> **只測頂點會漏。** 布穿物品必須用**邊級別**判定 ——
> 實測過同一個狀態:頂點判定說 0 條、邊判定說 14 條。`chain_pen.py` 用的是邊級別。

## 5. 紙箱

`carton/make_carton_P.py` 產生瓦楞紙箱 USD:四片蓋(下層 ±x、上層 ±y)、真實板厚、
每片蓋有自己的鉸鏈關節。`*.meta.json` 記錄實際幾何,模擬腳本一律**從 meta 讀**,不寫死。

| USD | 說明 |
|---|---|
| `carton_w131.usd` | **定版**。外 270 × 230,箱高參數 131 mm |
| `superseded/carton_flush.usd` | 舊版,蓋子會穿箱壁(留作對照) |
| `superseded/carton_ppt130.usd` | 更舊,上蓋沒齊邊 |

定版的幾何:

```
內壁       ±132 (x) × ±112 (y)
下鉸鏈     z = 123.0        上鉸鏈  z = 129.5
±x 牆頂    z = 120.0        ±y 牆頂 z = 126.5     ← 四面牆不等高,見下
上蓋半寬   131.0(左右各留 1.0 mm)
下蓋伸長   130.5(兩片之間縫隙 3.0 mm)
```

**四面牆為什麼不等高**:鉸鏈放在箱壁內面,但蓋子是 2t = 3 mm 厚的板。
蓋子一旦傾斜,外上角就掃進箱壁那 3 mm 的帶子。舊版 **360/361 個角度都重疊,最深 1.50 mm**。
修法是該面牆頂降到「鉸鏈 z − 2t」,實測 0~180° 全程 **0/361**。用 `carton_sweep.py` 可複驗。

> ⚠ 讀 meta 要讀 `wall_top_x` / `wall_top_y`。`wall_top_z` 現在只是 `--height` 參數本身,
> **不等於任何一面牆的實際高度**。
>
> ⚠ `lever_arm`(目前 1.0 mm)/ `force_cap_torque_Nm_at_30N` 尚未在齊邊之後重新校正。
>
> ⚠ **下蓋兩片之間的 3.0 mm 縫隙是生成器預設值,不是照實物量的。** PPT 沒有記錄這個數字。

## 6. 實測結果

全部逐頂點/逐邊量,不是看畫面。

**布會不會穿過杯子** —— 從杯子擺到包材上那一刻起,全鏈路 132 格:

| 階段 | 邊穿杯 |
|---|---|
| 杯子剛放到攤平的布上 | **0** |
| 四折包覆(yp → yn → xp → xn) | **0** 全程 |
| 六面壓實到 115 mm + 放開回彈 | **0** 全程 |
| 入箱 + 關四片蓋 | **0**(修正後) |

修正前入箱那一格會憑空跳出 172 條,之後衰減到穩定 4 條 / 1.4 mm。
真因是入箱只搬布、不搬杯子(見 §7 第 1 項),修正後穩定值 **0**。

**包材是不是真的包住杯子** —— 提杯測試(`videos/3_lift_by_mug_TEST.mp4`):

```
杯子上升 200.0 mm   布質心上升 183.1 mm   跟隨比 0.915
布最低點 148.7 mm(起點 1.0)⇒ 整包離地
布 bbox  255×212×131 → 233×217×182(縱向拉長 = 被拎著)
全程邊穿杯 0 條
```

「掛得住」和「不穿過」同時成立才有意義:布若掉下去,不穿模可能只是因為沒接觸。

**入箱 + 關蓋**

```
布    1225 點;超出內腔 4 個(低於箱底,z 最低 0.7 mm vs 箱底內面 3 mm)
杯子 24832 點;超出內腔 0 個
最終包裹 bbox 238 × 211 × 125 mm,下鉸鏈 123 mm
```

**是不是同一張布**

```
3536 條邊,長度 / 攤平時:中位 1.002,5%~95% 分位 0.834~1.224
```

中位 1.002 = 沒有被拉伸,折疊是等距的。布上另外印了 8×8 棋盤格(依**攤平座標**),
折起來看格子變形就知道是同一張布。

## 7. 已知限制

1. **~~入箱只搬布不搬杯子~~ —— 已修。** 記在這裡是因為它示範了一個重要的判讀法:
   那個穿模在階段交界**階躍** +172 然後衰減,而不是在階段內漸增 ——
   階躍 ⇒ 擺位/記帳問題;漸增 ⇒ 真的被物理擠出來。
2. **布和布之間會自穿模,約 1900 次,未解。**
   四折之後角落有多餘的布堆在一起,需要加一個**角落三角摺**才能消掉。
   這是折法本身的限制,不是參數調得出來的。
3. **完整攤平時布會被拉長 7%。** 攤平是把外緣 136 個錨點**無限剛性**釘在攤平座標上 ——
   只要布還有一處沒打開的疊層吃掉長度,剩下的料就得拉長才撐得到那個釘死的外框。
   實測是平衡態:放慢 2.5 倍反而更差(1.070 → 1.084)。要解得換攤平機制。
4. **100 mm 高的紙箱放不下。** 杯子躺平 93 + 箱底 3,只剩 4 mm 給包材,幾何上不可能。
5. **`lever_arm` / 力上限未重新校正**;**下蓋縫隙 3.0 mm 沒有實物依據**(見 §5)。
6. **PhysX 自己的接觸回報能不能用在 surface deformable,仍然未知。**
   `PhysxContactReportAPI` 和 `separation` 欄位都在,但三次獨立場景的探針都沒能把
   deformable 做活(自檢顯示布完全沒動),所以這題沒有答案。
   本包所有「穿模」數字都是 `trimesh` 幾何判定,不是引擎訊號。

## 8. 座標約定

- 紙箱長邊平行 **y**,杯口朝向**垂直 y**(杯子躺平 107 × 133 × 93 mm)
- 地板 z = 0;紙箱底板內面 z = 3 mm
- 下層蓋在 ±x(鉸鏈 z = 123),上層蓋在 ±y(鉸鏈 z = 129.5)
- 蓋子角度:**0° = 關上,180° = 全開**
- 碰撞容差:`contactOffset = 5 mm`、`restOffset = 1 mm`(判斷「算不算穿模」要拿這兩個當尺)

---

## 9. 這一包沒做到的事

- **`scene_fixed.usd` 的定裝照沒生出來。** `shot_full.py` 對這個場景會 segfault
  (GPU 是空的,不是資源問題)。USD 本身已建好且座標驗過:
  轉 90° 後包材 211×238×125、杯子 133×107×93、紙箱內腔 224×264,x/y 都對。
  要看畫面請自行開啟 `scene_fixed.usd`。
