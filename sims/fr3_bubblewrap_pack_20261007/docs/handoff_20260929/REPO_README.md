# fr3_bubblewrap_pack_20261007 —— 逆物流 Demo:泡泡紙包馬克杯 → 入紙箱 → 搬箱 → 開蓋 → 掀包材(開發中)

Isaac Sim 5.1 / PhysX。這個資料夾是 2026-09-30 ~ 10-07 這段開發的**可重現快照**:腳本、素材、USD、文件、測試。
**模擬輸出(影片、npz、log)不在 repo 裡**,照下面的指令跑就會產生。

## 內容

| 資料夾 | 內容 |
|---|---|
| `work/` | **surface deformable 版**主程式 `wrap_sim.py`(折 / 壓 / 入箱 / 關蓋 / 搬箱 / 開蓋)、量測工具、文件、`tests/` 自動檢查、`RUNS.csv`(122 次模擬紀錄) |
| `vol/` | **volume deformable 版**(有真實厚度的薄板)`wrap_vol.py` 全程單次模擬;探針 `probe_vol_*.py`;互穿量測 `vol_pen.py`;`grip/` 夾爪探針;`rest/` 解析 rest shape |
| `arm/` | FR3 雙臂場景盤點、IK 可達性、掀蓋/掀包材軌跡(開發中) |
| `scene/` | `scene_final.usd`(雙臂 + 定版紙箱 + 包裹,flatten)、`stationary_ai_carton_scene_flat.usd`(原始雙臂場景)、`build_full_scene.py` |
| `docs/handoff_20260929/` | 原始交接文件(TASK_INTERN、ORIENTATION_AND_SIZE、CHECKLIST…) |

先讀 `work/README.md`(現況、定案參數)、`work/EXPERIMENTS.md`(每一批實驗的假設與結果)、`work/PITFALLS.md`(踩過的坑)、`work/HOW_TO_VIEW.md`(怎麼看輸出)。

## 環境

- Isaac Sim 5.1,路徑 `/isaac-sim`,用 `/isaac-sim/python.sh` 跑(有 numpy / trimesh / imageio)。系統 `python3` 只能跑純 CPU 工具(`layer_gap.py`、`edge_report.py`、`tests/`)。
- GPU:每段模擬約 5~8 GB 顯存、2~5 分鐘。
- 所有腳本假設**在它所在的資料夾裡執行**(素材用相對路徑)。

## 一、surface 版(`work/`)

定案參數(2026-10-02):布 400×400、`--thick 0.004 --hold_mm 6 --tip_over_mm 0 --layer_mm 5 --young 2e4 --bend 4`、折序 x→y(前後在外層)、四折後**不壓實直接入箱**、壓實/入箱段 `--no_anchor`。

```bash
cd work
P=/isaac-sim/python.sh
C="--tex bubble_normal.png --wrapsim --young 2e4 --bend 4 --thick 0.004 --sheet_mm 400 --layer_mm 5 --hold_mm 6 --tip_over_mm 0 --cam_ref 0.586"
$P wrap_sim.py $C --wrap_edge --wrap_n 2 --out c1                                  # 折左右
$P wrap_sim.py $C --stage2 --init_npz c1/wrap.npz --out c2                          # 折前後
$P wrap_sim.py $C --init_npz c2/wrap.npz --carton carton_w131.usd --close_lid --lid_span 4 --no_anchor --out box   # 入箱關蓋
$P wrap_sim.py $C --init_npz box/wrap.npz --carton carton_w131.usd --no_anchor --in_box_already \
   --no_ground_collision --base_collider_pad 0.02 --movebox 0,0.20,0.10 --move_t 6 --move_wait 2 --settle 3 --move_open --lid_span 3 --out mb   # 搬箱 + 開蓋
# 串成 demo 影片(每段裁掉 0.5s 渲染暖機)
for d in c1 c2 box mb; do ffmpeg -y -loglevel error -ss 0.5 -i $d/wrap.mp4 -c:v libx264 -pix_fmt yuv420p -crf 20 $d/trim.mp4; echo "file '$PWD/$d/trim.mp4'"; done > list.txt
ffmpeg -y -f concat -safe 0 -i list.txt -c copy DEMO_surface.mp4
```
每段輸出 `wrap.mp4 / wrap.npz / traj.npz / wrap_sim.log`。檢查:`python3 tests/run_checks.py box`、`python3 collect_runs.py`。
量測:`python3 layer_gap.py box/wrap.npz --shrink_mm 25`、`$P chain_pen.py mug.stl c1/traj.npz c2/traj.npz`。

## 二、volume 版(`vol/`)

定案材料(2026-10-07):E 2e3、ν 0.45、板厚 4 mm、面密度 0.1 kg/m²、manual 35×35×1 四面體、contact 2 / rest 0.5 mm、solver 128、dt 1/240、布 500×500。全程一次模擬(四折 → 收耳 → 入箱 → 關蓋 → 放錨 → 搬箱 → 開蓋):

```bash
cd vol
/isaac-sim/python.sh wrap_vol.py --sheet_mm 500 --young 2e3 --tuck 1 --out out_demo     # 約 4 分鐘,輸出 out_demo/wrap.mp4
/isaac-sim/python.sh wrap_vol.py --sheet_mm 500 --young 2e3 --tuck 1 --grasp 1 --out out_grasp   # 加夾爪掀包材段(開發中)
python3 vol_pen.py --selftest
```
探針:`probe_vol_sheet.py`(薄板建法/穩定性)、`probe_vol_fold.py`(折 + 放手)、`probe_vol_stack.py`(疊層壓實互穿)、`probe_plastic.py`(回彈/塑性)、`grip/probe_grip.py`、`grip/probe_peel.py`。

## 三、場景與手臂(`scene/`、`arm/`)

```bash
cd scene && /isaac-sim/python.sh build_full_scene.py --place auto      # 從包裹 npz 重建 scene_final.usd
cd arm   && /isaac-sim/python.sh inspect_scene.py && /isaac-sim/python.sh reach.py     # 雙臂盤點、IK 可達性
```

## 四、測試

```bash
cd work/tests && bash run_tool_selftests.sh && python3 test_golden.py
```
`run_checks.py <run目錄>` 對單次模擬判 PASS/WARN/FAIL(門檻與來源見 `tests/README.md`)。golden 案例指向 `work/runs/`,**那些模擬輸出不在 repo**,要先照第一節跑出對應目錄或改 `golden.json`。

## 現況(2026-10-07)

| 目標 | 狀態 |
|---|---|
| 1 入箱 0 超出 | surface ✅(400 布)/ volume ✅(s2) |
| 2 折序前後在外層 | ✅ |
| 3 完整流程影片 | ✅ 兩版各一支(照上面指令產出) |
| 4 搬箱不掉出 | ✅ 相對位移 1~3 mm |
| 5 壓小 | 高度 ✅(93 → 122~125,約杯子 + 5 層 × 5 mm);體積 3.1~5.1 倍,受材料無塑性限制 |
| 6 降伏影片 | ✅ `work/yield/` |
| 夾爪掀包材 | 探針成立(單片 / 疊層),整包上開發中 |
| FR3 手臂 | 可達性開發中 |

細節與數字:`work/REPORT_20260930.md`、`work/REPORT_THICKNESS.md`、`work/EXPERIMENTS.md`。
