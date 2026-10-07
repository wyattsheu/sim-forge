# work/ —— 包材(surface deformable 布)模擬工作區入口

2026-09-29 ~ 10-02 的實驗都在這裡。數字一律來自 `RUNS.csv`(由 `collect_runs.py` 從各 run 的 `wrap_sim.log` 抽),
同參數跑兩次會差 ~6mm,**差 < 6mm 當噪音**。下一階段(volume deformable,真厚度)在 **`../vol/`**,不在這裡。

## 現況(TASK_INTERN 六個目標)
| # | 目標 | 狀態 | 證據(run_id → RUNS.csv) |
|---|---|---|---|
| 1 | 包裹待在紙箱裡 | ✅ 布 0 / 杯 0 超出 | `fincam_box`、`finB_box`、`dm_box`;⚠ 有六面壓實的 `fin_box` 布 24 點穿 y 牆 |
| 2 | 前後(±y)在外層、杯口 +y 杯耳 +x | ✅ `FOLD_ORDER=[xp,xn,yp,yn]`,杯子 `Rz(−90)+_Rm` | `fincam_*`(新折序);`dm_*` 是舊折序 |
| 3 | 一支流程影片 | ✅ | `videos/DEMO_new_order_sheet400.mp4` |
| 4 | 搬箱子影片 | ⚠ 杯 0 超出;布相對箱子 2.5mm;布 6 點「低於箱底」(搬前就 6) | `fincam_mb_open` |
| 5 | 壓更小 | ❌ 物理底線:層間距 4.3~5.6mm/層,包裹 122~130mm(杯 93);體積 3.1× 杯 | `REPORT_THICKNESS.md`;口徑 A/B 待使用者定 |
| 6 | 降伏影片 | 已重剪(10/02),本次整理未重驗 | `yield/`、`videos/by_run/yield_*.mp4` |

## 定案參數(新折序、sheet 400、四折後直接入箱;所有段共用 C)
```bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/work; P=/isaac-sim/python.sh
C="--tex bubble_normal.png --wrapsim --young 2e4 --bend 4 --thick 0.004 --sheet_mm 400 --layer_mm 5 --hold_mm 6 --tip_over_mm 0 --cam_ref 0.586"
$P wrap_sim.py $C --wrap_edge --wrap_n 2                                   --out X_c1
$P wrap_sim.py $C --stage2 --init_npz X_c1/wrap.npz                        --out X_c2
$P wrap_sim.py $C --init_npz X_c2/wrap.npz --carton carton_w131.usd --close_lid --lid_span 4 --no_anchor --out X_box
$P wrap_sim.py $C --init_npz X_box/wrap.npz --carton carton_w131.usd --no_anchor --in_box_already \
   --no_ground_collision --base_collider_pad 0.02 --movebox 0,0.20,0.10 --move_t 6 --move_wait 2 --settle 3 --move_open --lid_span 3 --out X_mb_open
```
不跑 c3(六面壓實):新折序壓完放開 y 彈到 248~250 > 內腔 224,入箱 24 點穿牆(`fin_c3`→`fin_box`)。
跑完把 `X_*` 與 `X_*.stdout` 搬進 `runs/NN_xxx/`,再 `python3 collect_runs.py`、`python3 tests/run_checks.py runs/NN_xxx/X_box`。

## 兩支 DEMO 怎麼串的
| 影片 | 段 | 腳本 |
|---|---|---|
| `videos/DEMO_new_order_sheet400.mp4` | `fincam_c1 → fincam_c2 → fincam_box → fincam_mb_open`(各段 `trim.mp4`,去掉前 0.5s 暖機)| `wrap_sim.py`(新折序)|
| `videos/DEMO_old_order_sheet400_v2.mp4` | `dm_c1 → dm_c2 → dm_c3 → dm_box → dm_mb_open` | `archive_src/wrap_sim_old.py`(舊折序)|

清單在 `videos/lists/final_ok_list.txt`、`videos/lists/demo_old_list.txt`(路徑已改成 `runs/…`;原檔在 `lists/orig/`)。
`DEMO_old_order_sheet400.mp4`(v1, 07:26)沒有留清單,來源不明(時間上接近 `sh400_*`),不要引用。
重現舊 DEMO:`archive_src/run_demo_old.sh` 寫死 `S=wrap_sim_old.py` 且在 work/ 根目錄跑 →
先 `ln -s archive_src/wrap_sim_old.py .`,跑完再把 `dm_*` 搬回 `runs/11_final/`(腳本會 `rm -rf dm_*` 根目錄同名目錄)。

## 目錄導覽
```
README.md / EXPERIMENTS.md / PITFALLS.md / CHANGES_wrap_sim.md    文件(先看這四份)
RUNS.csv          每次模擬一列(100 列);collect_runs.py 重產
MOVED.txt         這次整理的 舊路徑 → 新路徑(舊文件裡的 out_c1/… 照這張表找)
tests/            自動判讀:run_checks.py / test_golden.py / run_tool_selftests.sh
runs/01_baseline … 11_final   各批次的 run 目錄 + 它們的 *.stdout;_stdout_scratchpad/ 是從 scratchpad 複製的 stdout
runs/probes_logs/ 探針 log(attachment 放手、摺痕定型、摩擦)
runs/99_misc/     phys_scene*(scene_final.usd 的物理檢查,不是 wrap_sim)
archive_src/      舊版 wrap_sim、patch、run_demo_old.sh
videos/           DEMO_* 在最上層;by_run/ 各批次影片;lists/ 串接清單
yield/            降伏影片(目標 6),未動
REPORT_20260930.md / REPORT_THICKNESS.md / HOW_TO_VIEW.md / FOLDORDER_NOTES.md / PROMPT_*.md   原報告(路徑是搬家前的)
```
根目錄的腳本與素材(`wrap_sim.py grip_common.py carton*.usd carton*.meta.json floor_edges*.json mug.stl …`)
被別的腳本用相對路徑找,**不要搬**。量測工具:`layer_gap.py`(層數/層間距)、`edge_report.py`(逐邊)、
`chain_pen.py`(布穿杯,邊級別,要 `/isaac-sim/python.sh`)、`check_place.py`。

## 下一步
- volume deformable(真厚度、手臂掀包材)在 `../vol/`,不要在 work/ 開新實驗。
- 口徑 A(泡泡紙,122~130mm 合理)/ B(薄膜 <100mm,要換物理)等使用者決定。
