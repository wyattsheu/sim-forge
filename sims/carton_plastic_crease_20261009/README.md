# 紙箱:彈塑性摺痕(drive 版)—— 存檔

> 這是 `fr3_bubblewrap_pack_handoff_20261007` 在 **2026-10-09 ~ 2026-10-13** 用的紙箱蓋模型。
> 2026-10-14 起,交付包改用 co7b 的紙箱(`sim/crease_co7b.py`,見交付包 README),這個模型存在這裡,
> 特性、參數、驗證數字和報告簡報都保留。交付包裡仍可用 `LID_MODE=plastic` 切回這個模型。

完整的力學說明、文獻、驗證結果:[docs/CREASE_MECHANICS.md](docs/CREASE_MECHANICS.md)
報告簡報(ACM Lab 範本,內嵌影片):[docs/slides/2026-10-10-Carton-Crease.pptx](docs/slides/2026-10-10-Carton-Crease.pptx)

## 1. 這個紙箱是什麼

- 幾何:跟交付包同一個紙箱(Box B,`make_carton_P.py` 產生),四片蓋子 `fxp / fxn`(下層,左右)、`fyp / fyn`(上層,前後)。
  紙箱幾何、包材、杯子都在交付包的 `scene_final_phys.usd`,這裡不另存一份。
- 摺痕:**彈性－塑性(加軟化、帶小黏性)**,和 parcel-forge `carton_v1` 的 `crease_model.advance` 同一條定律。
- 實作:**USD 關節的 angular drive 就是彈性部分**(剛性 k、目標角 = 塑性角 θp),
  `sim/crease_plastic.py` 每個物理步更新 θp 寫回 drive 目標角。角度連續展開,可以超過 180°。

```
彈性彎矩      M_c = k (θ − θp)
目前降伏彎矩   M_y,now = M_y · max(0.5, exp(−s · κ))      κ = 累積塑性轉角
塑性流動      |k(θ − θp)| > M_y,now 時  Δθp = sign · (|k(θ − θp)| − M_y,now) · Δt / (η + k Δt),  η = k · t_visc
```

## 2. 參數

| 參數 | 值 | 來源 |
|---|---|---|
| 降伏 / 平台彎矩 M_y | 0.25 N·m/m × 摺痕寬度(上層蓋 0.066、下層蓋 0.055 N·m) | Nagasawa 2019(紙板 Mp1 0.244 N·m/m);**瓦楞未校準** |
| 回彈角 M_y / k | 45° | Nagasawa 2019:摺到 90° 放手回到 43–46° |
| 彈性剛性 k | M_y / 45°(上層蓋 0.083 N·m/rad) | 由上兩項推出 |
| 軟化率 s | 0.15 /rad,下限 0.5 M_y | carton_v1 |
| 塑性黏性時間 t_visc | 0.02 s | 數值穩定 |
| drive 阻尼 | 臨界阻尼 × 0.5 | 數值穩定 |
| armature | 2e-4 kg·m² | 數值穩定 |
| 蓋子質量 / 慣量 | 由幾何、密度 200 kg/m³ 計算(上層蓋 17.4 g) | 幾何 |
| 關節限位 | −275° … +5°(開為負);紙箱是 articulation | 270° = 摺到箱壁外側 |
| 環境變數 | `CREASE_MY_PER_M`、`CREASE_SOFTENING`、`CREASE_MIN_YIELD`、`CREASE_VISC_TIME` | `crease_plastic.py` |

蓋子參數由 `sim/build_phys_scene.py` 寫進 USD(`crease:yieldMoment`、`crease:width`、drive 剛性),`crease_plastic.py` 從關節讀。

## 3. 實測特性(Isaac Sim 6.0,詳見 CREASE_MECHANICS.md §4)

| 情境 | 結果 |
|---|---|
| 摺到 90° 放手(空箱 / 有包材) | 停在 45.3°,回彈 44.7° |
| 摺到 270° | 260.8° 碰到箱壁;放手停在 240° |
| 重複摺 90° 三次 | 回彈 44.7 → 44.6 → 44.5°(變軟) |
| 手臂式往上拉蓋子邊緣(test P,4 s 加到 3 N) | 0.29 N → 10°、0.64 N → 30°、1.43 N → 60°;3 N 到 76.5°;放手停在 30.6° |
| 滑鼠拉上層蓋(pickingForce 70) | 拉到 80° / 76°,放手停在 34° / 30° |
| 靜置 8 s(test A) | 上層蓋 2.6°、下層蓋 6.9°(被包材頂起),不動 |
| 搬運(test B) | 上層蓋被頂開約 15° 並留著 |
| 甩動 1.5 m/s(test S) | 穿出側牆頂點最多 10;一片上層蓋被甩開到 73°,停在 26° |

和 co7b 紙箱的差別(2026-10-14 換掉的原因):co7b 的雙臂開箱流程(推到 165° 放手停在 ~122°)是用 co7b 的摺痕
(力矩式、k 3.2 / My0 0.60 / H 0.85 / c 0.33 ×0.1、蓋子預開 50° / 60°)調出來的,交付包要跟手臂流程用同一個紙箱。

## 4. 檔案

```
carton_plastic_crease_20261009/
├── README.md
├── docs/
│   ├── CREASE_MECHANICS.md          力學、文獻、模型、驗證(從交付包搬來,含歷史)
│   ├── img/                         文件用圖(plot_crease.py 產生)
│   └── slides/                      2026-10-10 報告簡報 + make_figs.py + outline.json
└── sim/
    ├── crease_plastic.py            ★ 摺痕模型(drive 版)
    ├── crease_test.py               摺痕試驗(模仿文獻的摺疊試驗機)
    ├── plot_crease.py               CREASE_MECHANICS.md 的圖
    ├── run_crease_matrix.sh         整組測試(SCENE=<場景>,預設交付包的 scene_final_phys.usd;PY=<python>)
    ├── verify_phys_scene.py         場景測試 A / B / Bm / C / P / S(預設 --lid_model plastic)
    ├── lid_test.py                  滑鼠拉蓋子
    ├── lid_latch.py、crease_hold_ui.py   更早的蓋子模型(閂鎖、力矩式彈塑性),crease_test / lid_test 的對照組
    ├── build_phys_scene.py          產生帶這組摺痕參數的物理場景(讀交付包的 scene_final_ui.usd,輸出到本目錄)
    └── find_isaac.sh                找 Isaac Sim
```

## 5. 怎麼重跑

```bash
cd sims/carton_plastic_crease_20261009/sim
S=../../fr3_bubblewrap_pack_handoff_20261007/scene_final_phys.usd
/isaac-sim/python.sh crease_test.py $S --lid fyp --track 90 --empty     # 摺到 90° 放手
/isaac-sim/python.sh verify_phys_scene.py $S --test P --pull_lid fyp --pull_max 3
./run_crease_matrix.sh                                                  # 全部(依序跑,GPU 跟別人共用)
```

注意:CREASE_MECHANICS.md 的數字是在「新參數重建的場景」上量的(§7 第 5 點:交付包的 `scene_final_phys.usd`
還沒用新參數重建)。要完全重現,先在 Isaac Sim 5.1 上 `python.sh build_phys_scene.py`(輸出到本目錄的
`scene_final_phys.usd`),再用 `SCENE=../scene_final_phys.usd ./run_crease_matrix.sh`。
