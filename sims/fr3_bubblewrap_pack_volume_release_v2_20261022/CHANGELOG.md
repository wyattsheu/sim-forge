# CHANGELOG

Newest first. Times are UTC. `git log --date=iso -- sims/fr3_bubblewrap_pack_volume_release_v2_20261022` shows the same history.
最新的在最上面。時間是 UTC。

---

## 2026-10-22 — v2 release / v2 交付版

**What it is / 是什麼**
- Release of the **v2.1** flow from `docs/V2_FLOW.md` ("整鏈驗證(v2.1)"). Code = `sims/fr3_bubblewrap_pack_20261007/vol/` at commit `6fcd916`
  (identical to the development folder at that time), plus the `[release]` edits below.
  交付 `docs/V2_FLOW.md`「整鏈驗證(v2.1)」那一版。程式 = repo commit `6fcd916` 的 `vol/`(當時和開發目錄相同)+ 下面的 `[release]` 修改。

**v1 → v2 differences / v1 → v2 差異**

| | v1 (`volume_release_20261021`) | v2 (this folder) |
|---|---|---|
| Unpacking place / 在哪裡掀 | Inside the opened carton / 開蓋後在箱內 | Hand 2 takes the whole package out onto the table first / 手 2 先把整包拿到桌面 |
| Flaps opened / 掀哪幾片 | yn, yp | yn, yp, xn, xp |
| After release / 放手後 | Flap flips back → demo defined as "peel **and keep holding**" (hand 2 holds yn, hand 1 holds yp) | Flap stays flat on the table by itself (+10 s angle 0 – 20° in V21T/2) |
| Holding / 夾持 | Two-finger grippers, **bind vertices on close** (`--grasp_attach 1`) | **Friction only**, 150 mm wide fingers (yn / yp) and 300 mm (xn / xp) (`--grasp_attach 0 --pick_mode wide --wide_mm_x 300`) |
| Fingers / 指頭 | Collision fingers (`--jaw_collide 1`) | Collision fingers (`--jaw_collide 1`) |
| Hands / 手 | Hand 1, hand 2 + a third extraction hand | Two hands: hand 1 peels; hand 2 takes the package out, holds the mug during x flaps (lets go while a flap is gripped), takes the mug away |
| Fold anchors / 錨點 | Released after the lids close | Kept as **tape** that follows the mug through boxing / carry / take-out (`--tape_follow 1`); a flap's tape is cut the moment that flap is gripped |
| Official flags / 正式旗標 | `--quality final --edamp 0.02` + JAW.md gripper set | `v2/run.sh` base + `--quality final --edamp 0.02 --ut_release_up 1 --v2_xmode tapegrip --v2_h2_free 1 --wide_mm 150 --wide_mm_x 300 --v2_xrel_slide 2` |
| Validation / 驗證 | gripper version: one fast run with collision fingers | final whole chain ×2: V21T/2 passes all, V21T/1 fails only xn (87°) |
| Runner / 執行 | `run_release.sh` waits for GPU < 26000 MiB | `run_release.sh` goes through `run3.sh` (launch lock, GPU gate, silent-failure watchdog + restart) |
| Save / resume / 存檔續跑 | — | `--save_state … --at xflaps` / `--load_state` (SPEEDUP, V2_FLOW) |
| Sim time / 模擬長度 | 130.5 s | 195.3 s |

**Added / 新增**
- `sim/run_release.sh` — `final` / `fast` one-command v2.1 chain; `UNTIL=fold|box|move` drops the take-out / x-flap / extraction flags
  (`--takeout 1` asserts `--until all` in wrap_vol.py); extra args go to wrap_vol.py (save / resume).
  一條指令跑 v2.1 整鏈;設 `UNTIL` 時拿掉取出 / x 片 / 取杯旗標;多給的參數傳給 wrap_vol.py(存檔續跑)。
- `sim/run3.sh` (+ `table3.py`), `sim/v2/` (run.sh, runx.sh, table.py, rigid.py, tablex*.py, cut_*.sh, raw TABLE*.md), `sim/table/` (unwrap on the table), `sim/pgrasp/cut_short.sh`.
- `make_videos.sh` — default (v2.1 final → VOL_v2_full + DEMO_v2_short), `--fast`, `--table`, `--pgrasp`, `--x2`, `--variants`, `--montage DEV`.
- `videos/` (in git, 103 MB): VOL_v2_full, DEMO_v2_short, VOL_v2x2_compare, DEMO_unwrap_table_short, VOL_unwrap_table_yp, VOL_pgrasp, DEMO_pgrasp_short, VARIANTS_grid, DEMO_ALL + DEMO_1 … 6 (v1).
- `docs/`: V2_FLOW, TABLE_UNWRAP, PGRASP, SPEEDUP, PLASTIC, MATSWEEP, CREASE, FINAL_PLAN, RELEASE; `docs/smoke_check/` (smoke run of this folder).
- `scene/` = v1 (unchanged). `sim/carton.usd` = v1 (md5 `f58eb371…`).

**Changed vs the development copy / 與開發版的差異(都標 `[release]`)**
- `sim/wrap_vol.py` line 28: default `--carton carton.usd` (was `carton_w131.usd`; byte-identical files). Same edit as v1.
- `sim/run3.sh`: `cd` to its own folder (unchanged), lock default `./.run3_launch.lock` (was `speed2/.run3_launch.lock`), interpreter `$ISAAC` (default `/isaac-sim/python.sh`),
  table command `$TABLE` (default `python3 table3.py`, was `speed2/table3.py`), `LOADCHK=0` switch — i.e. the development `v2/run3x.sh` merged in; `v2/run3x.sh` removed.
- `sim/v2/run.sh`, `sim/v2/runx.sh`, `sim/table/run.sh`: `cd "$(dirname "$0")/.."` instead of the absolute development path; `runx.sh` calls `./run3.sh`.

**Smoke test / 冒煙測試** (2026-10-21 20:30 UTC)
- `UNTIL=fold ./run_release.sh fast SMOKE` from this folder (run3.sh lock shared with the development runs): EXIT 0, 50 s; fold bbox 254 × 239 × 124 mm, out of cavity 0 / 0,
  self-penetration max 31, mug penetration 0, inversions 0. `docs/smoke_check/`.
  在本資料夾跑 `--quality fast --until fold`:通過。

**Open / 待辦**
- x-flap corner fold-back (README §10 #1): 1 of 2 final whole runs pass all. Fix candidates in V2_FLOW "已知限制".
- Whole chain with the v2.1 flags in fast mode has not been run (only final ×2).
