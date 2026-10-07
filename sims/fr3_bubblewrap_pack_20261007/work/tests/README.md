# tests/ —— 自動判讀測試集(純 CPU)

```bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/work
python3 tests/run_checks.py runs/11_final/fincam_box               # 單一 run;exit 0 = 沒有 FAIL
python3 tests/run_checks.py <run_dir> --stage box --json out.json  # 指定段、輸出 JSON
python3 tests/run_checks.py <run_dir> --isaac                      # 沒有 chain_pen 輸出時用 /isaac-sim/python.sh 跑(慢,數分鐘~數十分鐘)
bash    tests/run_tool_selftests.sh                                # 工具自測彙總(含 ../vol/vol_pen.py --selftest,系統 python3 即可)
python3 tests/test_golden.py                                       # 測試集自己的測試
python3 tests/run_checks.py ../vol/soft/s2                         # volume 版(自動 --kind vol),見下方 vol 一節
```

段(stage)沒給就從 stdout 的指令列推(`--movebox`=mb、`--unbox`、`--close_lid`=box、`--press6`=c3、`--stage2`=c2、`--wrap_n 2`=c1),
沒有 stdout 就從 log 推。每項 PASS / WARN / FAIL / SKIP / INFO;**抽不到資料 = SKIP 並寫原因,不當 PASS**。

## 門檻來源
- **CHECKLIST S0/S2/S3/S5**:交付包 CHECKLIST 包材各段原文。
- **PITFALLS / REPORT**:交付包 PITFALLS、REPORT、REPORT_THICKNESS。
- **使用者 10-02 口徑**:入箱「允許少量,但不能掉出來」;箱壁/底板厚 3mm —— 頂點超過內腔**內面**但沒超過**外面** = 陷進板子(WARN,標「陷進牆板 X.X mm」),超過外面或高過**關著的**蓋 = FAIL;低於箱底同理(底板 3mm)。板厚從 log 的整箱 bbox − 內腔推,推不到用 3mm。
- **使用者 10-07 口徑**:(a) surface 自穿模 S1 改相對門檻(同段基準 ×1.5 WARN、×3 FAIL;基準 c1 13 / c2 257 / c3 512 / box 513,`run_checks.py` 的 `SELF_PEN_BASE` dict 可調;mb 沒給基準,沿用 box 513);(b) vol 自互穿 0 PASS / 1~20 WARN / >20 FAIL;(c) 搬箱段(mb)杯頂層數不足只 WARN(搬完布重新分布);(d) 邊長比最大不當 FAIL(夾爪/折角網格粗,局部 1.6 可接受),只報數,> 2.0 才 WARN;(e) vol PASS 口徑:互穿 0、穿杯 0、反轉 0、超出照 10-02、開蓋後布頂 z < 箱口(131)、俯視覆蓋 ≥ 90%(< 90 WARN、< 70 FAIL)。
- **協調者 10-02**:W1/W3 ≥ 95%、層數 ≥ 2。

所有門檻常數集中在 `run_checks.py` 開頭(`SELF_PEN_BASE`、`VOL_PEN_FAIL`、`WALL_MM_DEFAULT`、`EDGE_MAX_WARN`、`COVER_*`、`RIM_Z_DEFAULT`、`VOL_BBOX_X`)。

## 檢查項與門檻 —— surface 版(`wrap_sim.log`)
| key | 檢查 | 門檻 | 適用段 | 來源 |
|---|---|---|---|---|
| `meta_guard` | log 沒有「⚠ 找不到 … meta」 | 出現 = FAIL | box/mb/unbox | PITFALLS #1;REPORT §1-7(守門,保留)|
| `bbox_guard` | 全程所有「布 bbox」行任一軸 ≤ 1000mm | > 1000 = FAIL | 全部 | PITFALLS #7(`t_c1_bad` z 2343)(守門,保留)|
| `mug_orient` | 本段與 `--init_npz` 來源 run 的「杯子躺平 W×D×H」相同 | 不同 = FAIL | 有起點的段 | PITFALLS #10(`sh400_mb_yz`)(守門,保留)|
| `edge_ratio` | 邊長比中位 | 0.95~1.05 | 全部 | CHECKLIST S3「是不是同一張布」 |
| `edge_max` | 邊長比最大 | 只報數(INFO);> 2.0 WARN;**不 FAIL** | 全部 | 使用者 10-07 口徑 |
| `mug_pen` | 布穿杯(邊級別)條數 | 0 | 有 chain_pen 輸出時 | CHECKLIST S2;找 `<run>/chain_pen*.txt`、`<batch>/pen_<run>.txt` |
| `box_contain` / `box_contain_mug` | 最後一個「真的入箱了嗎」區塊 | 0 PASS;只陷進牆板/底板(≤ 3mm)WARN;穿出外面 / 高過關著的蓋 FAIL;杯子 > 0 FAIL | box/mb | CHECKLIST S2(0 個)+ 使用者 10-02 口徑 |
| `lid_closed` | 最後 `[lid]` 行:fx 蓋中心 z 對下鉸鏈、fy 對上鉸鏈 | 差 < 5mm | box;mb 取 `settled` 並扣搬箱 z | 目標 1 |
| `move_rel` / `move_delta` | 搬箱結論行 D、N1 − N0 | D < 10mm;N1 − N0 ≤ 2 | mb | 目標 4;CHECKLIST S5 |
| `fold_order` | log 的 `wrap xx` 順序 = 現行 `wrap_sim.py` 的 `FOLD_ORDER[:2]`(c1)/ `[2:]`(c2) | 不同 = FAIL | c1/c2 | CHECKLIST S0「折序生效」 |
| `W1` / `W3` | 俯視遮蔽 / 圍蔽 | ≥ 95% | unbox 以外 | 協調者 10-02 |
| `layers` | layer_gap 杯頂上方層數中位(shrink 25,35×35 才算) | ≥ 2;**mb 段 < 2 = WARN** | c2/c3/box/mb | 協調者 10-02;mb 降級 = 使用者 10-07 口徑 |
| `volume` | 布 bbox 體積 ÷ 杯 bbox 體積(wrap.npz) | < 3.0 PASS / < 4.0 WARN / 其餘 FAIL | c2/c3/box/mb | REPORT_THICKNESS(真實包裝 1.5~2×)|
| `self_pen_rel` | 布自穿模 S1 ÷ 同段基準 | ≤ ×1.5 PASS / ×1.5~3 WARN / > ×3 FAIL | c1/c2/c3/box/mb | 使用者 10-07 口徑(原 CHECKLIST「沒有硬門檻」)|

注意:`fold_order` 比的是**現行**腳本,舊折序腳本跑的 run(`dm_*`、09-30 的 c1/c2)會 FAIL —— 那是「與現行版本不符」,不代表當時跑壞。
surface 的邊長比最大幾乎都 > 2.0(2.1~2.9),所以現在好的 surface run 整體多半是 WARN(只因 `edge_max`),這是使用者 10-07 口徑的預期結果。

## volume 版(`../vol/`,`wrap_vol.log`)
```bash
python3 tests/run_checks.py ../vol/soft/s2                 # 目錄有 wrap_vol.log → 自動 --kind vol
python3 tests/run_checks.py ../vol/soft/s2 --kind vol --json out.json
python3 collect_runs.py --include-vol                      # RUNS.csv 加 vol 列(kind=vol)
```
- **只讀** `vol/`(另一個 agent 在跑 `wrap_vol.py`、寫 `vol/grasp/`;`collect_runs --include-vol` 略過 `grasp/ grip/ logs/ img/ videos/`)。
- `parse_vol_log()`(在 `collect_runs.py`,`run_checks.parse_vol_log` 同一個)從結尾 **SUMMARY** 段抽:四折後/收耳後/關蓋後 bbox、體積÷杯、開蓋後布頂 z(max/99%)與箱口、俯視覆蓋、全程最大 自穿/穿杯/反轉/邊長比/體積比、wall。
  **入箱超出(關蓋/搬前/搬後/開蓋後 + x/y/底/口分項與範圍)與搬箱位移 SUMMARY 沒印**,從「真的入箱了嗎(逐頂點比對內腔)」區塊抽。
  沒有 SUMMARY 的舊 log(`out_v400* out_v500*`):自穿/穿杯/反轉/邊長比用「判讀」段「全程最大」行、覆蓋率用判讀 end 行、布頂 z 用入箱區塊「開蓋後」布 z max − 箱底內面;每項的來源印在值後面(`SUMMARY` / `判讀段` / …),RUNS.csv 的 `vol_來源` 欄也有。抽不到 = SKIP 並寫原因,`vol_missing` 列出。
- 段:`vol-all`(args `until=all`)/ `vol-fold`(`until=fold`,入箱以後的項目全 SKIP)。
- 自互穿數就是 `vol_pen.self_pen_count`(`wrap_vol.py` 每步算、log 印「自穿」),不另外重算。

| key | 檢查 | 門檻 | 來源 |
|---|---|---|---|
| `meta_guard` | 「★ 紙箱 …(meta …)」行存在、沒有「找不到 … meta」 | 出現 = FAIL | PITFALLS #1(守門,保留)|
| `bbox_guard` | 全程 `t=` 行與判讀段的布 bbox 任一軸 | > 板子最大邊 ×1.2 或 > 1000 = FAIL | PITFALLS #7 延伸(vol 的板子 400~500,1000 抓不到 `out_v500_restfold` t=0 的 661)|
| `mug_orient` | args 有 `init_npz` 才比(現有 vol run 都是攤平起步 → SKIP)| 不同 = FAIL | PITFALLS #10(守門,保留)|
| `edge_ratio` | — | SKIP(vol log 只有 [min,max],沒有中位)| — |
| `edge_max` | SUMMARY 邊長比最大 | INFO;> 2.0 WARN | 使用者 10-07 |
| `mug_pen` | 布穿杯全程最大 | 0 | 使用者 10-07(vol PASS 口徑)|
| `inversion` | 四面體反轉全程最大 | 0 | 使用者 10-07 |
| `self_pen_vol` | 自互穿頂點數全程最大 | 0 PASS / 1~20 WARN / > 20 FAIL | 使用者 10-07 |
| `box_contain` / `box_contain_mug` | 關蓋、搬前、搬後三個時刻取最差 | 同 surface(陷進板 ≤ 3mm WARN、穿出外面 / 高過關著的蓋 FAIL、杯 > 0 FAIL)| CHECKLIST S2 + 使用者 10-02 |
| `box_contain_end` | 開蓋後(蓋開著,口不計)| 只報數 | — |
| `move_rel` / `move_delta` | 布質心相對箱 搬前→搬後 差;搬後 − 搬前超出 | < 10mm;≤ 2 | 目標 4;CHECKLIST S5 |
| `top_z` | 開蓋後 3s 布頂 z max(相對箱底內面)| < 箱口(log 值 130.9,預設 131)| 使用者 10-07 |
| `cover` | 開蓋後杯頂俯視覆蓋 | ≥ 90 PASS / < 90 WARN / < 70 FAIL | 使用者 10-07 |
| `volume`、`bbox_stages`、`vol_ratio`、`wall` | 體積÷杯、各階段 bbox、四面體體積比、wall time | 只報數(vol 包裹貼箱 ~5×,surface 的 < 3.0 不適用)| — |
| `lid_closed`、`layers` | — | SKIP(vol log 沒有關蓋中的蓋 z;npz 不是 35×35 `sheet`)| — |

2026-10-07 全部 vol run 跑一遍:只有 `soft/s2` 沒有 FAIL(WARN:自互穿 8、搬前/搬後 1 點陷進 x 牆 1.2/0.2mm)。其餘多半是 `top_z`(開蓋後布彈出箱口)或 `cover` FAIL。

## golden(`tests/golden/`)
symlink 指到 `runs/` 或 `../vol/`,不複製大檔;預期寫在 `golden/golden.json`。bad 可列 `expect_fail`(必須 FAIL)與 `expect_warn`(必須 WARN)。
- good(整體須 PASS/WARN):`fincam_c1 fincam_c2 fincam_box fincam_mb_open dm_box vol_s2`
- bad:`t_c1_bad`→bbox_guard、`out_bl_box`→meta_guard、`sh400_mb_yz`→mug_orient、`fin_box`→box_contain、`v1_c3`→**self_pen_rel**、
  `vol_s6`→inversion FAIL + edge_max/cover WARN、`vol_s5`→inversion/cover/top_z、`vol_r3`→cover、`vol_out_v500_restfold`→bbox_guard

2026-10-07 結果:**15/15 符合**。10-02 的兩個 MISS 已依使用者口徑解決(不是調門檻去湊):
`fincam_mb_open` 的 `layers` 在 mb 段改 WARN;`v1_c3` 由 `self_pen_rel`(S1 2403 ÷ c3 基準 512 = ×4.7)抓到。
附帶:`fincam_c1` S1 26 = c1 基準 13 的 ×2.0 → `self_pen_rel` WARN。

加新 golden:`ln -s ../../runs/NN_xxx/<run> tests/golden/<run>`(vol:`ln -s ../../../vol/<sub>/<run> tests/golden/vol_<run>`),在 `golden.json` 的 good 或 bad 加一筆,跑 `test_golden.py`。

## 建議的自動化流程
```
跑模擬(--out X)→ mv X X.stdout runs/NN_xxx/ → python3 collect_runs.py → python3 tests/run_checks.py runs/NN_xxx/X --json …
  → 有 FAIL 就停,不要把這個 run 當下一段的 --init_npz;改了 run_checks / 門檻就先跑 test_golden.py
```
