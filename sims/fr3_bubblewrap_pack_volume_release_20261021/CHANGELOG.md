# CHANGELOG

Newest first. Times are UTC. Each entry = one git commit on `sims/fr3_bubblewrap_pack_volume_release_20261021`
(`git log --date=iso -- sims/fr3_bubblewrap_pack_volume_release_20261021` shows the same history).
最新的在最上面。時間是 UTC。每一條對應一個 git commit。

---

## 2026-10-21 — first volume release / volume 包材第一版交付

**What it is / 是什麼**
- The official wrap is now the 4 mm **volume** deformable (FINAL_PLAN §1). The previous handoff (surface wrap) was renamed
  `sims/fr3_bubblewrap_pack_surface_handoff_20261007` in the commit before this one.
  正式包材改為 4 mm **volume** deformable(FINAL_PLAN §1)。上一版(surface 包材)在前一個 commit 改名為
  `sims/fr3_bubblewrap_pack_surface_handoff_20261007`。
- Code = `sims/fr3_bubblewrap_pack_20261007/vol/` as pushed in `09ad54d` (the development folder was not copied live).
  程式 = repo 已推送的 `sims/fr3_bubblewrap_pack_20261007/vol/`(`09ad54d`),不是從開發目錄現場複製。

**Added / 新增**
- `sim/run_release.sh` — one command, `final` (`--quality final --edamp 0.02`) or `fast` (`--quality fast --edamp 0`);
  official flags = JAW.md gripper version + `--jaw_collide 1` (collision fingers, bind on close); `UNTIL=box` for the fold/box part only.
  一條指令跑 `final` 或 `fast`;正式旗標 = JAW.md 夾爪版 + `--jaw_collide 1`(碰撞體指頭、合指才綁);`UNTIL=box` 只跑到入箱。
- `sim/run_checks.sh` + `sim/checks/` — volume grading from `work/tests` (run_checks.py, collect_runs.py, README with thresholds) and tool selftests.
  volume 版自動判讀(取自 `work/tests`)與工具自測。
- `make_videos.sh` — regenerates the videos (default / `--fast` / `--damped` / `--variants` / `--montage DEV`).
- `videos/` — **in git this time** (user request): DEMO_1~6, DEMO_ALL, VOL_twohand_extract, DEMO_twohand_extract_short, VARIANTS_grid, VOL_damped (84 MB).
  影片**這次進 git**(使用者要求)。
- `scene/` — dual-arm workstation USD, `scene_final.usd`, and `arm/` (INTERFACE.md, robot_model.py, peel_traj_v2/v3.py, data/ incl. `iface.json/npz`).
- `docs/` — RELEASE.md, FINAL_PLAN.md, all `vol/*.md` conclusions, VARIANTS.csv, deck 2026-10-14.

**Changed vs the development copy / 與開發版的差異(都標 `[release]`)**
- `sim/wrap_vol.py` line 28: default `--carton carton.usd` (was `carton_w131.usd`; the two files are byte-identical).
- `sim/checks/run_checks.py`: imports `collect_runs.py` from its own folder.
- `scene/arm/peel_traj_v2.py`: default `--scene` = `scene/scene_final.usd` (was an absolute path on the dev machine);
  `peel_traj_v3.py`: reads `iface.npz/json` from `arm/data/` when present (was `vol/soft/s2/`).

**Carton / 紙箱**
- `sim/carton.usd` + `carton.meta.json` copied from the surface handoff (co7b carton). Compatibility run with
  `--quality fast --until box --edamp 0` + official gripper flags: **pass** — 0 / 0 wrap / mug vertices out of the cavity
  before boxing and after closing, lids at the closed pose (README §4.5, `docs/carton_check/`). The file is byte-identical to `vol/carton_w131.usd`.
  紙箱取自 surface 交付版(co7b);相容測試**通過**:入箱前與關蓋後布 / 杯超出內腔 0 / 0,蓋子關到位(README §4.5)。與 `vol/carton_w131.usd` 位元組相同。

**Found / 發現**
- `wrap_vol.py --until box` + `--extract 1`: the extraction hand is not gated by `--until` and drags the mug out of the box
  during the carry. `run_release.sh` drops the extraction flags when `UNTIL` is set (README §11 #13). wrap_vol.py itself not changed.
  `--until box` 加 `--extract 1` 時取杯段不受 `--until` 控制,搬箱途中把杯子拖出去;`run_release.sh` 設了 `UNTIL` 就拿掉取杯旗標。

**Open / 待辦**
- TODO: when `docs/vol/MATSWEEP.md` (over-wall 60 + softer material) concludes and is usable, update the official flags
  (`run_release.sh` MATERIAL / GRASP, README §9.1, §11 #1).
- The collision-finger version has one fast validation run (JAW C3f); three final runs still to do.
