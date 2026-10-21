# Bubble-Wrapped Mug in a Carton — Volume Wrap Release<br>氣泡布包裹馬克杯入箱 —— volume 包材交付版

> **Newer release / 新版:** [`../fr3_bubblewrap_pack_volume_release_v2_20261022`](../fr3_bubblewrap_pack_volume_release_v2_20261022) — v2: package taken out onto the table, four flaps peeled by a friction-only wide gripper and they stay open after release / v2:整包拿到桌面、寬指純摩擦依序掀開四片,放手後片自己攤在桌上。

**Language / 語言:** [English](#english) · [繁體中文](#繁體中文)

---

# English

> **This is the delivered release of the volume (4 mm thick) bubble wrap.** Clone it and you can re-run the whole
> chain — wrap → into the carton → close → carry → open → grippers peel the wrap open **and keep holding it** → take
> the mug out — with one command, check the result with numbers, generate other fold styles, and watch the videos
> (they are in git this time).
> The previous handoff used a **surface** (zero-thickness) wrap and is kept as
> [`../fr3_bubblewrap_pack_surface_handoff_20261007`](../fr3_bubblewrap_pack_surface_handoff_20261007) (interactive UI
> scene, mouse drag, click → ROS 2). Development history: [`../fr3_bubblewrap_pack_20261007`](../fr3_bubblewrap_pack_20261007).
> What changed: `CHANGELOG.md`. Every number below comes from the files in `docs/` (cited per row).

| | |
|---|---|
| **Version** | volume_release_20261021 — volume deformable wrap (FINAL_PLAN §1: volume is the official wrap), two-finger grippers with collision fingers that bind on close (JAW.md [jaw3]), dev / final quality modes (QUALITY.md), fold diversity (FOLD_DIVERSITY.md) |
| **Tested on** | Isaac Sim 5.1.0-rc.19 (Kit 107.3 / PhysX 107.3.26), RTX 5090 32 GB, NVIDIA driver 580.173.02 |
| **Get it** | git: this folder (videos included) · tarball: `handoff_volume_20261021.tgz` (same content) |

## Contents

1. [Quick start](#1-quick-start)
2. [Which file opens what](#2-which-file-opens-what)
3. [Using the Isaac Sim UI](#3-using-the-isaac-sim-ui)
4. [What the simulation does](#4-what-the-simulation-does)
5. [Videos](#5-videos)
6. [Files](#6-files)
7. [Scripts: which run where](#7-scripts-which-run-where)
8. [Pass criteria and the latest 3 runs](#8-pass-criteria-and-the-latest-3-runs)
9. [Official flags, fast mode, fold diversity](#9-official-flags-fast-mode-fold-diversity)
10. [Version and test environment](#10-version-and-test-environment)
11. [Known limitations](#11-known-limitations)

---

## 1. Quick start

```bash
cd sim
./run_release.sh fast  X1   # development run: --quality fast --edamp 0      (~14 min, 960x540)
./run_release.sh final X1   # the deliverable: --quality final --edamp 0.02  (~20-25 min, 1280x720) + 18 s short cut
./run_checks.sh ../runs/final_X1   # numbers: contained, mug penetration, inversions, carry, cover ... (PASS/WARN/FAIL)
python3 table.py ../runs/final_X1  # grasp / hold / extract row (same columns as docs/vol/JAW.md)
```

Output goes to `runs/<mode>_<name>/`: `wrap.mp4`, `wrap_vol.log` (per-0.5 s table + SUMMARY), `wrap.npz`
(sheet / mug / tets / layer indices per snapshot), `grasp.json`, `key_*.png`, `stdout.txt`.
One simulation at a time: `run_release.sh` waits until the GPU uses < `GPU_MAX` (26000 MiB) — two recordings at once run out of memory.

Only the wrap-into-the-box part (to screen a new carton or fold style, ~4-5 min):
`UNTIL=box ./run_release.sh fast K1`.

---

## 2. Which file opens what

| File | What it is | Open it with |
|---|---|---|
| `sim/wrap_vol.py` | **The simulation**: one program, whole chain, headless, records `wrap.mp4` | `sim/run_release.sh` (or `/isaac-sim/python.sh wrap_vol.py ...`, §9) |
| `sim/carton.usd` + `carton.meta.json` | The carton (270 × 230 × 131 mm, cavity 264 × 224, 4 lids) — **the same carton as the surface handoff** (§4.3) | Referenced by `wrap_vol.py --carton` (default) |
| `scene/stationary_ai_carton_scene_flat.usd` | The original dual-arm workstation (two FR3-class 6-axis arms, table), 14 MB | Isaac Sim UI (§3) |
| `scene/scene_final.usd` | Workstation + carton + wrapped mug, static meshes; the wrap mesh in it is the **surface** wrap of 10-02 — use it for placement / coordinates (arm side), not for the wrap's look | Isaac Sim UI; `scene/arm/peel_traj_v2.py --scene` (default) |
| `videos/*.mp4` | Results (§5) | Any player |
| `docs/RELEASE.md` | Three weeks of methods and conclusions in one table, the honest status | Text |

There is no interactive (press-Play) volume scene in this release: the volume wrap only exists inside `wrap_vol.py`'s own stage.
For an interactive scene with mouse dragging, use the surface handoff (`open_in_ui.sh` there).

---

## 3. Using the Isaac Sim UI

- `wrap_vol.py` runs headless (`SimulationApp({"headless": True})`) and writes the video; there is no window to watch.
  Watch `runs/.../wrap.mp4`, or the stills `key_fold_done.png`, `key_in_box.png`, `key_lids_closed.png`, `key_after_move.png`, `key_opened.png`.
- To look at the dual-arm scene: start Isaac Sim (`/isaac-sim/isaac-sim.sh`, or `OMNI_KIT_ALLOW_ROOT=1 ...` as root),
  then **File → Open** `scene/scene_final.usd` or `scene/stationary_ai_carton_scene_flat.usd`. **Alt + left-drag** orbits, **F** frames the selection.
- Do **not** paste `wrap_vol.py` (or any script that creates its own `SimulationApp`) into the Script Editor — it starts a
  second Kit inside the running one and hangs it. Run those from a terminal.
- Remote viewing / WebRTC, mouse grab settings, lid crease models: see the surface handoff README §3-§4 (same Isaac Sim, same scene files).

---

## 4. What the simulation does

### 4.1 The wrap
4 mm thick tetrahedral **volume deformable** plate, 500 × 500 mm, 35 × 35 grid (6125 tets), self-collision on,
`--young 2e3 --poisson 0.45 --areal 0.1 --fric 0.8`, contact / rest offset 2 / 0.5 mm, bubble normal map `bubble_normal.png`.
Layer spacing = plate thickness 4 mm (the surface version's 4.3-5.6 mm was fake thickness from self-collision) — RELEASE §1, FINAL_PLAN §1.

### 4.2 The chain (sim time, `--quality final`)
| t (s) | Stage |
|---|---|
| 0 - 17.5 | Lay flat, fold four sides (default order xp, xn, yp, yn → yn is the outer layer; tips cross the mug centre line by 30 mm), tuck the ears |
| 17.5 - 46.5 | Into the carton, close lids, carry the carton (+0.20 m y, +0.10 m z), open lids |
| 46.5 - 82 | **Hand 1** (two-finger gripper) picks yn by state-based site selection, closes, binds, peels it over the wall top; **hand 2** pinches the part lying on the lid and **keeps holding** |
| 82 - 117 | Hand 1 picks yp the same way and **keeps holding** it (`--hold_yp 1`) |
| 117.3 - 130.5 | **Extraction gripper** closes on the mug ends, lifts 20 mm, rises over the yn wall top + 40 mm, slides 280 mm in −y, sets it on the floor, opens |

### 4.3 Grippers: collision fingers, bind on close
Official setting `--hand1_jaw 1 --hand2 jaw --extract_grip jaw --jaw_collide 1` (docs/vol/JAW.md):
- **All fingers are kinematic colliders** (contact 1 mm / rest 0, friction `--ffric` 2.0). Hand 1 has a real lower finger
  that slides under the wrap edge before the upper finger closes to a 4 mm gap; hand 2 has two fingers that stop at the wrap top +0.5 mm (they
  touch, they don't press) and pinch to 9 mm; the extraction fingers stop 1 mm outside the mug, or 4 + 1 mm where wrap covers the mug end.
- **Holding is by binding, and binding happens only when the fingers have closed**: hand 1 binds the vertices inside the
  finger footprint (half-width 24 mm, |n| ≤ 6 mm, both layers); hand 2 binds the yn vertices between its fingers (x ±18 × y ±25 mm);
  the mug turns kinematic and follows the extraction gripper only after finger contact. Release = remove the binding.
- **Pure friction does not work** (fric/F1, F2: 0 vertices between the fingers after closing, yn peeled 1 % / 0 %; JAW.md).
  So "close then bind" is the conservative stand-in for what a gripper can do.
- In the dual-arm scene, hand 1 and hand 2 are the two arms; the extraction gripper is a third (kinematic) hand.
  `--hand2 off` gives a strictly two-hand variant — **not validated** (JAW.md [jaw3] only mentions it).

### 4.4 Demo definition (changed 2026-10-15)
The arms **peel the wrap open and keep holding it**, then the mug is taken out — the way a person unpacks with one hand
holding the wrap open. It is **not** "peel, let go, the wrap stays open by gravity": this material has no plasticity and
flips back the moment it is released (§11 #1; PEEL4, HAND2).

### 4.5 Carton
`sim/carton.usd` / `carton.meta.json` are the files from the surface handoff (the co7b carton used since 2026-10-14).
They are **byte-identical** to the development `vol/carton_w131.usd` / `.meta.json` (md5 `f58eb371…`): what made "co7b"
different is the runtime crease model `crease_co7b.py` (soft elastoplastic law, My0 0.12 N·m, 45° spring-back, preset
front 50° / back 60°), which the surface handoff loads into its interactive scene. `wrap_vol.py` makes every carton body
kinematic and poses the lids itself, so that crease model is not used here.
Compatibility run (2026-10-21, `--quality fast --until box --edamp 0` + the official gripper flags): **passes.** `wrap_vol.py` reads the carton ("meta carton.meta.json; 5 rigid bodies kinematic; bbox 270x230x134; cavity ±132 x ±112; hinges 123.0 / 129.5"); before boxing 0 / 0 out of cavity (wrap / mug); **after closing the lids 0 / 0** (wrap 2592 vertices x −131.2~128.9, y −111.5~111.5, z 3.5~125.1); lids at the closed pose (fx 123.4, fy 128.7 mm above the floor); closed-wrap bbox 260 × 223 × 122, self-penetration 18, mug penetration 0, inversions 0 at closing; before carrying 3 wrap vertices 1.3 mm into the 3 mm bottom board (WARN, the known fast-mode value, QUALITY.md). wall 144 s for 42 s sim. The "after carrying" numbers of that run are invalid: with `--until box` the extraction hand (`--extract 1`) is not gated and pulled the mug out of the moving box (§11 #13; `run_release.sh` now drops the extraction flags when `UNTIL` is set). Log and stills: `docs/carton_check/`.

---

## 5. Videos

The videos are **in git** this time (user request, 2026-10-21; 84 MB). `./make_videos.sh` regenerates them:

```bash
./make_videos.sh                  # official demo: run_release.sh final → VOL_twohand_extract + DEMO_twohand_extract_short (~25 min)
./make_videos.sh --fast           # same chain in fast mode → videos/fast/ (development only, does not overwrite)
./make_videos.sh --damped         # VOL_damped.mp4 (~20 min)
./make_videos.sh --variants       # VARIANTS_grid.mp4 (24 fold orders × --until box, ~2 h)
./make_videos.sh --montage DEV    # DEMO_1..6 + DEMO_ALL: ffmpeg montage of development sources (DEV = handoff_20260929 folder)
```

| Video | Length | Shows | Source run |
|---|---|---|---|
| `VOL_twohand_extract.mp4` | 130.5 s | ★ Whole chain: fold → box → carry → open → hand 1 peels yn, hand 2 holds it → hand 1 peels yp and holds → mug taken out and set on the floor | extract6/X2 (gripper version, `--edamp 0.02`, final quality). **Fingers in this video are visual only** (`--jaw_collide 0`, jaw2); `./make_videos.sh` regenerates it with collision fingers |
| `DEMO_twohand_extract_short.mp4` | 18.2 s | The grasp part of the above, the three finger closings at 1×, the rest 2-4× (`sim/cut_short.sh`) | extract6/X2 |
| `DEMO_ALL.mp4` | 291 s | DEMO_1 … DEMO_6 back to back, 1 s black between | — |
| `DEMO_1_surface_pipeline.mp4` | 64 s | Comparison: the surface wrap chain (fold, box, carry, open) | surface handoff DEMO |
| `DEMO_2_volume_pipeline.mp4` | 48 s | Volume wrap: four folds, tuck, box, carry, open | vol/soft (VOL_soft_best) |
| `DEMO_3_grasp_probes.mp4` | 44 s | Gripper probes: friction vs binding, surface vs volume | deck figs 11/12, grip_attach g1a / g2ab |
| `DEMO_4_arm.mp4` | 47 s | The 6-axis dual arm: dry run, with cloth, real peel v3 (Lula IK, 24 bound vertices, peeled 64 %) | arm/ |
| `DEMO_5_wrap_peel.mp4` | 56 s | Peeling the whole package, surface vs volume | SURF_grasp_attach, vol/grasp/out_ga2 |
| `DEMO_6_twohand_extract.mp4` | 26 s | Two-hand peel and hold → extract (= the short cut above) + the 24 fold orders | DEMO_twohand_extract_short, VARIANTS_grid |
| `VARIANTS_grid.mp4` | 6 s | 22 fold variants side by side (each fold compressed to 5 s, last frame before boxing), label = id, fold order, outer layer | `fold_variants.py --video` |
| `VOL_damped.mp4` | 86 s | Earlier bind-only chain with `--edamp 0.05` (shows the shake reduction; its grasp got worse — DAMPING.md) | vol/damp/full_e0.05 |

`videos/DEMO_INDEX.md` lists the segment times of the DEMO montage (its "X3" note for DEMO_6 predates the 10-21 re-cut: the short clip inside is extract6/X2).

---

## 6. Files

```
README.md                    this document (English + 繁體中文)
CHANGELOG.md                 what changed
make_videos.sh               regenerate videos/ (§5)
videos/                      result videos (in git) + DEMO_INDEX.md
sim/                         simulation — flat folder, run scripts from inside it
  run_release.sh               ★ one command → final or fast run (+ short cut); official flags live here
  wrap_vol.py                  the simulation (Isaac Sim 5.1 volume deformable, whole chain); default --carton carton.usd
  volcommon.py                 volume plate / material / tets helpers
  vol_pen.py                   penetration counts (self, wrap-through-mug, inversions); --selftest
  layer_order.py               which flap is on top (outer layer) at any snapshot
  layer_gap.py                 layer spacing above the mug; --selftest
  grasp_plan.py                live grasp-site ranking (state-based site selection)
  grip_common.py               shared scene parts (lights, ground, camera)
  cloth_iface.py               interface for the arm side: OFF, NX/CX/CY, snapshot time, lid angles (FINAL_PLAN §2)
  jitter.py                    shake metric (per-frame vertex RMS) for DAMPING
  fold_variants.py             fold diversity: list / sample / batch-run / CSV / grid video (§9.3)
  table.py                     grasp/hold/extract table from stdout.txt (JAW.md columns)
  cut_short.sh                 cut the 18 s short from a 130 s wrap.mp4
  run_checks.sh                selftests + automatic grading of a run (§8)
  checks/                      run_checks.py + collect_runs.py + README.md (thresholds and their sources)
  make_demo_videos.sh          the DEMO_1..6 montage (needs the development folder; make_videos.sh --montage)
  find_isaac.sh                locate Isaac Sim (binary or pip)
  grip/gutil.py                kinematic finger / video helpers used by wrap_vol (grasp_points.py = offline ranking it came from)
  grip_attach/                 bind-on-close module (attach_grip.py) + README with the single-sheet probe numbers
  rest/make_rest.py            analytic folded rest shape (input for the optional --rest_npz)
  carton.usd, carton.meta.json the carton (§4.5)
  mug.stl, bubble_normal.png   mug mesh, wrap normal map
scene/
  stationary_ai_carton_scene_flat.usd   dual-arm workstation (14 MB)
  scene_final.usd              workstation + carton + wrapped mug (surface wrap mesh, static), 14 MB
  build_full_scene.py, README_scene_20261002.md   how scene_final.usd was assembled
  arm/INTERFACE.md             arm ↔ wrap_vol interface: frames (box local L, vol world V, scene S), what each side outputs, bind interface (§5), arm runs r1..v3
  arm/robot_model.py           URDF + Lula descriptor from the scene USD
  arm/peel_traj_v3.py          peel trajectory v3 (Lula IK re-solve); execs peel_traj_v2.py, so both are here
  arm/data/                    left/right URDF + yaml, trajectories (json/npz), iface.json/npz (the wrap state v3 plans on)
docs/
  RELEASE.md                   the release summary: all methods tried, numbers, honest status (§4 = criteria table)
  FINAL_PLAN.md                why volume, the official flag set, fold diversity plan and results
  vol/*.md                     per-topic conclusions: JAW, QUALITY, EXTRACT/2/3, FOLD_DIVERSITY, DAMPING, PLASTIC, MATSWEEP (in progress),
                               HAND2, DRAG, ROBUST, PEEL/2/3/4, SPEED; VARIANTS.csv
  deck/2026-10-14-Report.pptx  progress report deck
  carton_check/                carton compatibility run (§4.5): wrap_vol.log, stills
```

---

## 7. Scripts: which run where

| Script | What it is | How to run it |
|---|---|---|
| `sim/run_release.sh` | Official run | Terminal, inside `sim/` (§1) |
| `sim/wrap_vol.py` | The simulation | Terminal: `/isaac-sim/python.sh wrap_vol.py <flags> --out DIR` (never in the Script Editor) |
| `sim/run_checks.sh`, `checks/run_checks.py` | Grading | Terminal, system `python3` with numpy / scipy (falls back to `/isaac-sim/python.sh`) |
| `sim/table.py` | Grasp table | `python3 table.py RUN_DIR ...` |
| `sim/fold_variants.py` | Fold diversity | `python3 fold_variants.py ...` (it starts `/isaac-sim/python.sh wrap_vol.py` per variant) |
| `sim/vol_pen.py`, `layer_gap.py`, `layer_order.py`, `jitter.py`, `cloth_iface.py` | Post-processing | `python3 X.py ...` on a `wrap.npz` |
| `sim/rest/make_rest.py` | Rest shape | `python3 rest/make_rest.py --gap_mm 10 --out rest_g10.npz` |
| `scene/arm/peel_traj_v3.py` | Arm peel trajectory | `/isaac-sim/python.sh peel_traj_v3.py --flap yn ...` (opens `scene/scene_final.usd`) |
| `scene/arm/robot_model.py` | URDF generation | Imported by peel_traj_v2/v3 |

```
wrap_vol.py ──► volcommon.py ──► vol_pen.py
            ├─► grip_common.py, layer_gap.py, layer_order.py
            ├─► grasp_plan.py ──► layer_order.py
            └─► grip/gutil.py ──► volcommon.py
run_release.sh ──► wrap_vol.py, table.py, cut_short.sh
fold_variants.py ──► wrap_vol.py (subprocess), layer_order.py
```

---

## 8. Pass criteria and the latest 3 runs

Criteria (FINAL_PLAN §2 + demo additions): contained 0 out-of-cavity vertices, mug penetration 0, edge ratio, yn crossed ≥ 80 %,
after release ≥ 50 %, other flaps dragged < 5 %; demo: yn / yp held, mug out and on the floor, wrap lifted with the mug after landing < 30 %.
GPU deformables are **not reproducible** — same flags, different result — so every criterion is judged on a distribution, never one run.
Table = docs/RELEASE.md §4 (latest three full-chain runs that have the column):

| Criterion | Latest 3 runs | Met? | Source |
|---|---|---|---|
| Contained, 0 out | SPEED full chain ×4 all 0; FOLD_DIVERSITY r7_08, r7_11 after carry / after opening 0 | Yes | SPEED, FOLD_DIVERSITY |
| Still in the box after carrying | r7_08, r7_11 0 out; carry displacement 1.0 mm (C3f) | Yes | FOLD_DIVERSITY, JAW C3f |
| Mug penetration 0 | extract4 X1-X3 all 0; EXTRACT3 X1-X3 all 0 | Yes (since v4) | EXTRACT3 |
| Edge ratio | out_ga3 [0.509, 1.625]; default order twice 1.56 / 1.66 | Threshold 0.95-1.05 never met; [0.50, 1.65] used instead (it is inside the noise) | FOLD_DIVERSITY |
| yn crossed ≥ 80 % (peeled) | PEEL4 11 / 69 / 98; ROBUST 54 / 82 / 100 | Unstable (1 of 2-3) | PEEL4, ROBUST |
| yn after release ≥ 50 % | PEEL4 0 / 0 / 100; HAND2 after hand 2 leaves 1 / 100 / 2 | **No** (no plasticity, §11 #1) | PEEL4, HAND2 |
| yn held (hold definition) | extract4 X1-X3: 76 → 76 %, 56 → 99 %, 1 → 0 %; guard never tripped | Guard yes; X3 hand 2 bound at x = 85, yn crossed only 1 % | EXTRACT3 v4 |
| yp held | extract4 X1-X3 before extraction 80 / 98 / 97 %, end 79 / 97 / 96 % | Yes 3/3 | EXTRACT3 v4 |
| Wrap lifted with mug after landing < 30 % | extract4 X1-X3 33.8 / 19.1 / 36.6 % | **1 of 3** | EXTRACT3 |
| Other flaps dragged < 5 % | DRAG base 4.9 / 1.9 / 18.8; PEEL4 22.6 / 62.0 / 70.2 | **No** (5-70 %) | DRAG, PEEL4 |
| Bound vertices ≥ 6 | extract4 yn 25 / 14 / 14 | Yes | EXTRACT3 |
| Slip < 1 mm while held | median 0.07-0.14 mm | Yes | PEEL4, ROBUST |

Gripper versions (JAW.md; same columns):

| Run | Fingers | Quality | Guard | Mug pen. | Lifted lift / leave / landed | Finger-to-wrap min while closing |
|---|---|---|---|---|---|---|
| extract6/X1 | visual (jaw2) | final, edamp 0 | none tripped | 0 | 31.7 / 31.7 / 34.8 % | — |
| extract6/X2 (in the video) | visual (jaw2) | final, edamp 0.02 | none tripped | 0 | 23.5 / 19.7 / **22.0 %** | — |
| extract6/C3f | **collision (jaw3)** | fast, edamp 0.02 | none tripped | 0 | 40.2 / 40.2 / 34.2 % | hand 1 0.9 / 0.6, hand 2 6.7 / 5.3, extraction 5.2 / **−3.4 mm** |

The collision-finger version has **one fast run** only; the three final runs planned for it have not been done (§11 #8).

`sim/run_checks.sh RUN` grades a run against the thresholds in `checks/README.md` (volume section; vol: penetration 0 PASS / 1-20 WARN / > 20 FAIL,
cover ≥ 90 % PASS, wrap top after opening < rim, carry displacement < 10 mm ...). Example on extract6/C3f: PASS 6 / WARN 4 / FAIL 2 (mug penetration 1, inversions 26 — fast mode; QUALITY.md: only trust penetration counts in final).

---

## 9. Official flags, fast mode, fold diversity

### 9.1 Official (deliverable) — `sim/run_release.sh final`
```
wrap_vol.py --young 2e3 --poisson 0.45 --thick_mm 4 --areal 0.1 --fric 0.8 --ldamp 0 \
  --sheet_mm 500 --nxy 35 --tip_over_mm 30 --tuck 1 --carton carton.usd \
  --grasp 1 --grasp_attach 1 --attach_pad_mm 24 --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 \
  --steep_deg 45 --second 1 --grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30 \
  --hand1_jaw 1 --hand2 jaw --hand2_pad_mm 15 --hand2_keep 1 --hold_yp 1 --jaw_collide 1 \
  --extract 1 --extract_grip jaw --extract_mode slide --extract_out_mm 280 --slide_clear_mm 40 --guard_yn 2.6 --guard_yp 2.6 --guard_n 2 \
  --quality final --edamp 0.02
```
`--quality final` = dt 1/240, solver 128, contact / rest 2 / 0.5 mm (FINAL_PLAN §2). `--edamp 0.02` cuts the fold shake ~40 %
(DAMPING) and is in the official gripper flags (JAW.md, FINAL_PLAN §2); with the older bind-only hand it made one of two runs trip the yn guard (EXTRACT3 v5).

> **TODO (MATSWEEP):** `docs/vol/MATSWEEP.md` (in progress) sweeps softer / heavier material (E, areal density) and
> over-the-wall 60 mm so that a released flap hangs instead of springing back. If its conclusion is usable, the official
> flags (`MATERIAL` / `GRASP` in `run_release.sh`, this section and §11 #1) must be updated.

### 9.2 Development — `sim/run_release.sh fast`
`--quality fast --edamp 0` = dt 1/120, solver 48, every 2nd frame rendered, 960 × 540 (QUALITY.md).
Whole chain wall/sim 6.1-6.4 vs final 10.5 under the same load (1.7× faster; physics segments 2.1×; the grasp planner pauses 200-240 s regardless of dt).
Trust in fast: whether the chain finishes, event times, bound-vertex counts, guard trips, mug out, inversions / NaN, the fold shape (±5 mm).
Only trust in final: self-penetration (fast 30-32 vs final 5-8), out-of-cavity before / after carrying, peel / drag / lift percentages.
Why `--edamp 0` in fast: fast + edamp 0.02 raises the folded wrap's energy ×4 and edge ratio to 2.7 so the 2.6 guard trips at the start of the peel (PLASTIC §5).
dt 1/60 is not usable (fold 13 mm narrower, self-penetration 111, 13 inversions).

### 9.3 Fold diversity — `--fold_order`, `--seed`, `fold_variants.py`
```bash
cd sim
./run_release.sh fast F1 --fold_order yp,yn,xp,xn             # one order; the last-folded flap ends up outside (22/24 orders)
./run_release.sh fast F2 --mug_off_mm=20,-10 --mug_yaw_deg 90 --seed 3   # mug offset / yaw; --seed is recorded in the log
python3 fold_variants.py --list                # the 24 orders
python3 fold_variants.py --orders              # write variants/o_<order>/cmd.sh for all 24
python3 fold_variants.py --n 12 --seed 7       # sample 12: sheet 420-560, aspect 0.8-1.25, mug offset ±30 mm, yaw 0/90/180/270 ±10°, tip 10-45, margin, wall, tuck, fold speed, E 1.5e3-3e3
python3 fold_variants.py --run --ids 'o_*'     # run each with --until box, one at a time (waits for GPU < 20000 MiB); --full = passing ones get the whole chain
python3 fold_variants.py --csv; python3 fold_variants.py --video   # variants/VARIANTS.csv, videos/VARIANTS_grid.mp4
```
Results (FOLD_DIVERSITY): all 24 orders wrap and go into the box; physical criteria pass 20/24, strict (+ edge ratio [0.50, 1.65]) 9/24.
Random 12: the 8 with `tuck=0` all stick out of the cavity in y → **use tuck=1** (the sampler still draws tuck 0/1, §11 #10);
small sheet + offset can be infeasible (marked ★ in the log). The outer layer is reported by `layer_order.py` so the arm can pick the flap on top.

---

## 10. Version and test environment

| | |
|---|---|
| Release | volume_release_20261021 (sources: `handoff_20260929/vol/` as of 2026-10-21; `wrap_vol.py` = development copy + one line: default `--carton carton.usd`) |
| Isaac Sim | 5.1.0-rc.19 (Kit 107.3, PhysX 107.3.26), binary install in `/isaac-sim` (pip install also found by `find_isaac.sh`) |
| GPU | RTX 5090 32 GB, driver 580.173.02. One wrap_vol run ≈ 5-6 GB × 2 contexts; start only if < 26000 MiB used |
| Python deps | Isaac's python: numpy, scipy, trimesh, imageio, PIL (all bundled); `run_checks.sh` / `table.py`: system python3 (+ numpy / scipy) |
| Tools | ffmpeg / ffprobe (cut_short.sh, montage) |
| Measured times | final whole chain 797-1364 s wall (6.2-10.5× real time, depends on GPU load); fast 793-829 s; `--until box` ≈ 4-5 min |

---

## 11. Known limitations

| # | Limitation | Impact | Notes / what was tried |
|---|---|---|---|
| 1 | **A released flap does not hang down by itself; it has to be held open** | "Peel and let go" fails: yn after release ≥ 50 % only 1 of 3 (PEEL4), 2/5 with hand 2 then leaving (HAND2) | The 4 mm plate standing on the wall is a balance point; no plasticity. Demo is defined as peel **and hold** (§4.4). TODO: MATSWEEP (softer material + over-wall 60) |
| 2 | Other flaps are dragged when a flap is peeled | 5-70 % (criterion < 5 %) | Binding is a hard constraint in PhysX 107.3 (finite stiffness ignored), force-limited proxy, pinning xp/xn — none worked (DRAG) |
| 3 | Finger box | Arm side: finger box 36 × 70 × 60 mm, best arm run still inserts 18 mm into the wrap; no zero-insertion solution in 210 φ×ψ×offset combos (INTERFACE §5). Sim side (jaw3): extraction finger −3.4 mm into the wrap while lifting, only in the 3-hand version where hand 1 still holds yp over the mug (JAW C3f) | Grasp points < ~30 mm from a wall hit the wall or lid |
| 4 | No plasticity | Creases don't keep their shape; every release springs back | Runtime rest-shape bake works (spring-back 43.6° → 0.5°) but **kills the wrap's self-collision** after the rebuild (self-penetration 20 → 170-250), so it is a fallback only (PLASTIC) |
| 5 | Wrap lifted with the mug after landing | 19-37 % (< 30 % in 1 of 3 final runs; gripper X2 22.0 %, C3f 34.2 %) | The mug slides out of a wrap pocket and drags the hanging yn wrap over the wall (EXTRACT2/3) |
| 6 | Not reproducible | Same flags: yn crossed 0-100 %, cover before grasp 48-91 % | Judge on ≥ 3 runs |
| 7 | Shake | edamp 0.02 cuts it ~40 % but is not free (see §9.1, §9.2) | DAMPING |
| 8 | Collision fingers (`--jaw_collide 1`) validated by one fast run only | The shipped video uses visual fingers (jaw2) | `./make_videos.sh` regenerates with collision fingers; 3 final runs still to do |
| 9 | Speed | 13-23 min per whole chain; grasp planning pauses 200-240 s (CPU) | Only render decimation and fast mode are safe; dt / solver relaxation hurts the peel (SPEED, QUALITY) |
| 10 | `fold_variants.py --n` still samples `tuck=0` | 8/8 such samples stick out of the cavity | Use tuck=1 (edit the generated `cmd.sh` or the sampler) |
| 11 | The volume wrap isn't inside the dual-arm scene | `wrap_vol.py` builds its own stage (carton + wrap + mug + kinematic hands); `scene_final.usd` has the old surface wrap mesh | Coupling with the arms is by coordinates and snapshots (`scene/arm/INTERFACE.md`, `cloth_iface.py`) |
| 12 | GPU sharing | Two recordings at once run out of memory | `run_release.sh` waits for < 26000 MiB; one run at a time |
| 13 | `wrap_vol.py --until box` / `--until move` together with `--extract 1` | The extraction hand is appended after the shortened end and pulls the mug out of the box while it is being carried (found 2026-10-21 in the carton run) | `run_release.sh` drops the extraction flags when `UNTIL` is set; calling `wrap_vol.py` directly, leave `--extract` out for partial runs |

<p align="right"><a href="#english">↑ Back to top</a> · <a href="#繁體中文">繁體中文 ↓</a></p>

---

# 繁體中文

> **這是 volume(4 mm 厚)包材的交付版。** clone 下來就能用一條指令重跑整條鏈 —— 包 → 入箱 → 關蓋 → 搬箱 → 開蓋 →
> 夾爪把包材掀開**並一直撐住** → 取杯 —— 用數字驗收、產生不同折法,影片這次直接附在 git 裡。
> 上一版交付用的是 **surface**(零厚度)包材,保留為
> [`../fr3_bubblewrap_pack_surface_handoff_20261007`](../fr3_bubblewrap_pack_surface_handoff_20261007)(可互動的 UI 場景、滑鼠拖、點擊 → ROS 2)。
> 開發過程:[`../fr3_bubblewrap_pack_20261007`](../fr3_bubblewrap_pack_20261007)。修改紀錄:`CHANGELOG.md`。以下數字都出自 `docs/`(每列註明出處)。

| | |
|---|---|
| **版本** | volume_release_20261021 —— volume deformable 包材(FINAL_PLAN §1:正式包材 = volume)、指頭是碰撞體且合指時才綁定的兩指夾爪(JAW.md [jaw3])、開發 / 正式兩種精度(QUALITY.md)、折法多樣性(FOLD_DIVERSITY.md) |
| **測試環境** | Isaac Sim 5.1.0-rc.19(Kit 107.3 / PhysX 107.3.26)、RTX 5090 32 GB、NVIDIA driver 580.173.02 |
| **取得方式** | git:這個資料夾(含影片)· 壓縮檔:`handoff_volume_20261021.tgz`(內容相同) |

## 目錄

1. [快速開始](#1-快速開始)
2. [哪個檔開什麼](#2-哪個檔開什麼)
3. [在 Isaac Sim UI 裡看](#3-在-isaac-sim-ui-裡看)
4. [模擬在做什麼](#4-模擬在做什麼)
5. [影片](#5-影片)
6. [檔案](#6-檔案)
7. [腳本:哪支在哪裡跑](#7-腳本哪支在哪裡跑)
8. [判準與最新 3 次分布](#8-判準與最新-3-次分布)
9. [正式旗標、快速模式、折法多樣性](#9-正式旗標快速模式折法多樣性)
10. [版本與測試環境](#10-版本與測試環境)
11. [已知限制](#11-已知限制)

---

## 1. 快速開始

```bash
cd sim
./run_release.sh fast  X1   # 開發用:--quality fast --edamp 0      (約 14 分鐘,960x540)
./run_release.sh final X1   # 交付版:--quality final --edamp 0.02  (約 20~25 分鐘,1280x720)+ 剪 18 秒短版
./run_checks.sh ../runs/final_X1   # 數字驗收:入箱、穿杯、反轉、搬箱、覆蓋…(PASS/WARN/FAIL)
python3 table.py ../runs/final_X1  # 抓取 / 拿住 / 取杯一列(欄位同 docs/vol/JAW.md)
```

輸出在 `runs/<mode>_<name>/`:`wrap.mp4`、`wrap_vol.log`(每 0.5 s 一列 + SUMMARY)、`wrap.npz`(各快照的布 / 杯 / 四面體 / 層索引)、
`grasp.json`、`key_*.png`、`stdout.txt`。一次只跑一個:`run_release.sh` 會等 GPU 已用量 < `GPU_MAX`(26000 MiB)才開 —— 兩個錄影同時跑會 OOM。

只跑到入箱關蓋(換紙箱、換折法先篩這段,約 4~5 分鐘):`UNTIL=box ./run_release.sh fast K1`。

---

## 2. 哪個檔開什麼

| 檔案 | 是什麼 | 用什麼開 |
|---|---|---|
| `sim/wrap_vol.py` | **模擬本體**:單程式整條鏈、headless、錄 `wrap.mp4` | `sim/run_release.sh`(或 `/isaac-sim/python.sh wrap_vol.py ...`,§9) |
| `sim/carton.usd` + `carton.meta.json` | 紙箱(270 × 230 × 131 mm,內腔 264 × 224,4 片蓋)—— **跟 surface 交付版同一個紙箱**(§4.5) | `wrap_vol.py --carton` 預設就是它 |
| `scene/stationary_ai_carton_scene_flat.usd` | 原始雙臂工作站(兩支 6 軸手臂、桌子),14 MB | Isaac Sim UI(§3) |
| `scene/scene_final.usd` | 工作站 + 紙箱 + 包好的杯子,靜態網格;裡面的包材是 10-02 的 **surface** 包材 —— 拿來看擺位 / 座標(手臂端),不是看 volume 包材外觀 | Isaac Sim UI;`scene/arm/peel_traj_v2.py --scene` 預設 |
| `videos/*.mp4` | 成果影片(§5) | 任何播放器 |
| `docs/RELEASE.md` | 三週所有方法與結論一張表、誠實現況 | 文字 |

這個交付版**沒有**可以按 Play 互動的 volume 場景:volume 包材只存在於 `wrap_vol.py` 自己建的 stage 裡。
要滑鼠互動的場景請用 surface 交付版(那邊的 `open_in_ui.sh`)。

---

## 3. 在 Isaac Sim UI 裡看

- `wrap_vol.py` 是 headless(`SimulationApp({"headless": True})`),結果寫成影片,沒有視窗可看。
  看 `runs/.../wrap.mp4` 或關鍵幀 `key_fold_done.png`、`key_in_box.png`、`key_lids_closed.png`、`key_after_move.png`、`key_opened.png`。
- 看雙臂場景:開 Isaac Sim(`/isaac-sim/isaac-sim.sh`,root 要加 `OMNI_KIT_ALLOW_ROOT=1`),**File → Open**
  `scene/scene_final.usd` 或 `scene/stationary_ai_carton_scene_flat.usd`。**Alt + 左鍵拖**轉視角,**F** 對焦選取物。
- **不要**把 `wrap_vol.py`(或任何自己建 `SimulationApp` 的腳本)貼進 Script Editor —— 會在跑著的 Kit 裡再開一個,直接卡死。從終端機跑。
- WebRTC 遠端、滑鼠抓取設定、蓋子摺痕模型:見 surface 交付版 README §3~§4(同一套 Isaac Sim、同一批場景檔)。

---

## 4. 模擬在做什麼

### 4.1 包材
4 mm 厚四面體 **volume deformable** 板,500 × 500 mm,35 × 35 網格(6125 tets),自碰撞開,
`--young 2e3 --poisson 0.45 --areal 0.1 --fric 0.8`,接觸 / 靜止偏移 2 / 0.5 mm,表面貼 `bubble_normal.png` 泡泡紋理。
層間距 = 板厚 4 mm(surface 版的 4.3~5.6 mm 是自碰撞撐出來的假厚度)—— RELEASE §1、FINAL_PLAN §1。

### 4.2 流程(模擬時間,`--quality final`)
| t(s) | 段 |
|---|---|
| 0 ~ 17.5 | 布鋪平、四折(預設 xp, xn, yp, yn → 最外層 yn;尖端越過杯中線 30 mm)、收耳 |
| 17.5 ~ 46.5 | 入箱、關蓋、搬箱(y +0.20 m、z +0.10 m)、開蓋 |
| 46.5 ~ 82 | **手 1**(兩指夾爪)依當下狀態選點夾 yn、合指、綁定、繞過箱壁頂掀出去;**手 2** 捏住躺在蓋上那段並**一直拿住** |
| 82 ~ 117 | 手 1 同樣夾 yp 並**一直拿住**(`--hold_yp 1`) |
| 117.3 ~ 130.5 | **取杯夾爪**夾杯兩端、抬 20 mm、斜升過 yn 壁頂 +40 mm、往 −y 水平滑 280 mm、放到地上、張開 |

### 4.3 夾爪:指頭是碰撞體、合指時綁定
正式設定 `--hand1_jaw 1 --hand2 jaw --extract_grip jaw --jaw_collide 1`(docs/vol/JAW.md):
- **所有指頭都是 kinematic 碰撞體**(接觸 1 mm / 靜止 0,摩擦 `--ffric` 2.0)。手 1 有實體下指,先從布邊外滑到布底下,
  上指再合到指間 4 mm;手 2 兩指停在布頂 +0.5 mm(碰到、不往下壓)再捏到 9 mm;取杯指停在杯外 1 mm,杯端有布時停在 4 + 1 mm。
- **拿住靠綁定,而且合指完成才綁**:手 1 綁指面足跡內(半寬 24 mm、|n| ≤ 6 mm、上下兩層)的頂點;手 2 綁兩指之間(x ±18 × y ±25 mm)的 yn 頂點;
  杯子在取杯指接觸之後才轉 kinematic 跟手。放手 = 移除綁定。
- **純摩擦不可行**(fric/F1、F2:合指後指間 0 個頂點,yn 越線 1% / 0%;JAW.md)。所以「合指才綁」是夾爪能做到的行為的保守替身。
- 對應雙臂場景:手 1、手 2 = 兩支手臂;取杯夾爪是第三隻(kinematic)手。`--hand2 off` 是嚴格的兩手版本 —— **沒有驗證過**(JAW.md [jaw3] 只提到)。

### 4.4 demo 定義(2026-10-15 改定)
手臂把包材**掀開並持續撐住**,在這個狀態下取杯 —— 跟真人拆包一樣一手撐開一手拿。
**不是**「掀開放手後靠重力維持開著」:這個材料沒有塑性,一放手就翻回(§11 第 1 條;PEEL4、HAND2)。

### 4.5 紙箱
`sim/carton.usd` / `carton.meta.json` 直接取自 surface 交付版(2026-10-14 起的 co7b 紙箱)。
它跟開發用的 `vol/carton_w131.usd` / `.meta.json` **位元組完全相同**(md5 `f58eb371…`):co7b 不一樣的地方是 runtime 的摺痕模型
`crease_co7b.py`(軟彈塑性律,My0 0.12 N·m、回彈 45°、前蓋 50° / 後蓋 60° 預開),那是 surface 交付版在互動場景裡掛上去的。
`wrap_vol.py` 把紙箱所有剛體設成 kinematic、蓋子自己擺角度,所以這個摺痕模型在這裡用不到。
相容測試(2026-10-21,`--quality fast --until box --edamp 0` + 正式夾爪旗標):**通過。** `wrap_vol.py` 讀得到紙箱(「meta carton.meta.json;5 剛體 kinematic;bbox 270x230x134;內腔 ±132 x ±112;鉸鏈 123.0/129.5」);入箱前超出內腔 0 / 0(布 / 杯);**關蓋後 0 / 0**(布 2592 點 x −131.2~128.9、y −111.5~111.5、z 3.5~125.1);蓋子在關閉位置(fx 123.4、fy 128.7 mm,相對箱底);關蓋後布 bbox 260 × 223 × 122、自穿 18、穿杯 0、反轉 0;搬前 3 個布點陷進 3 mm 底板 1.3 mm(WARN,fast 模式的已知值,QUALITY.md)。wall 144 s / sim 42 s。那次的「搬後」數字無效:`--until box` 時取杯手(`--extract 1`)沒有被擋掉,在搬箱途中把杯子拖出箱外(§11 第 13 條;`run_release.sh` 已改成設了 `UNTIL` 就拿掉取杯旗標)。log 與截圖:`docs/carton_check/`。

---

## 5. 影片

這次影片**放進 git**(使用者 2026-10-21 要求,共 84 MB)。`./make_videos.sh` 可以重產:

```bash
./make_videos.sh                  # 正式 demo:run_release.sh final → VOL_twohand_extract + DEMO_twohand_extract_short(約 25 分鐘)
./make_videos.sh --fast           # 同一條鏈 fast 模式 → videos/fast/(只給開發看,不覆蓋正式影片)
./make_videos.sh --damped         # VOL_damped.mp4(約 20 分鐘)
./make_videos.sh --variants       # VARIANTS_grid.mp4(24 種折序 × --until box,約 2 小時)
./make_videos.sh --montage DEV    # DEMO_1~6 + DEMO_ALL:用開發資料夾的素材 ffmpeg 剪接(DEV = handoff_20260929)
```

| 影片 | 長度 | 內容 | 來源 |
|---|---|---|---|
| `VOL_twohand_extract.mp4` | 130.5 s | ★ 整條鏈:折 → 入箱 → 搬 → 開蓋 → 手 1 掀 yn、手 2 撐住 → 手 1 掀 yp 並撐住 → 取杯放到地上 | extract6/X2(夾爪版,`--edamp 0.02`,final 精度)。**這支影片的指頭是純視覺**(`--jaw_collide 0`,jaw2);`./make_videos.sh` 會用碰撞體指頭重產 |
| `DEMO_twohand_extract_short.mp4` | 18.2 s | 上面那支的抓取段,三次合指 1 倍速、其他 2~4 倍速(`sim/cut_short.sh`) | extract6/X2 |
| `DEMO_ALL.mp4` | 291 s | DEMO_1 ~ DEMO_6 串接,段間 1 s 黑幕 | — |
| `DEMO_1_surface_pipeline.mp4` | 64 s | 對照:surface 包材整條鏈(折、入箱、搬、開蓋) | surface 交付版 DEMO |
| `DEMO_2_volume_pipeline.mp4` | 48 s | volume 包材:四折、收耳、入箱、搬、開蓋 | vol/soft(VOL_soft_best) |
| `DEMO_3_grasp_probes.mp4` | 44 s | 夾爪探針:摩擦 vs 綁定、surface vs volume | deck figs 11/12、grip_attach g1a / g2ab |
| `DEMO_4_arm.mp4` | 47 s | 6 軸雙臂:乾跑、有布、真掀 v3(Lula IK、綁 24 點、掀 64%) | arm/ |
| `DEMO_5_wrap_peel.mp4` | 56 s | 整包掀開,surface vs volume | SURF_grasp_attach、vol/grasp/out_ga2 |
| `DEMO_6_twohand_extract.mp4` | 26 s | 雙手掀開撐住 → 取杯(= 上面的短版)+ 24 種折序 | DEMO_twohand_extract_short、VARIANTS_grid |
| `VARIANTS_grid.mp4` | 6 s | 22 種折法並排(折疊段壓成 5 s,停在入箱前 1 幀),標籤 = id、折序、最外層 | `fold_variants.py --video` |
| `VOL_damped.mp4` | 86 s | 舊綁定版整鏈 + `--edamp 0.05`(看顫抖降低;抓取反而變差 —— DAMPING.md) | vol/damp/full_e0.05 |

`videos/DEMO_INDEX.md` 是 DEMO 剪接各段時間(DEMO_6 那列寫的「X3」是 10-21 重剪之前的說明,裡面的短版其實是 extract6/X2)。

---

## 6. 檔案

```
README.md                    本文件(English + 繁體中文)
CHANGELOG.md                 修改紀錄
make_videos.sh               重產 videos/(§5)
videos/                      成果影片(進 git)+ DEMO_INDEX.md
sim/                         模擬 —— 平的資料夾,在裡面執行
  run_release.sh               ★ 一條指令 → final 或 fast(+ 短版);正式旗標寫在這裡
  wrap_vol.py                  模擬本體(Isaac Sim 5.1 volume deformable,整條鏈);預設 --carton carton.usd
  volcommon.py                 volume 板 / 材料 / 四面體工具
  vol_pen.py                   穿模計數(自穿、布穿杯、反轉);--selftest
  layer_order.py               任一快照哪片在最上層(最外層)
  layer_gap.py                 杯頂上方層間距;--selftest
  grasp_plan.py                即時抓點排名(依狀態選點)
  grip_common.py               共用場景元件(燈、地面、相機)
  cloth_iface.py               給手臂端的介面:OFF、NX/CX/CY、快照時間、蓋角(FINAL_PLAN §2)
  jitter.py                    顫抖量測(每格頂點位移 RMS),DAMPING 用
  fold_variants.py             折法多樣性:列表 / 抽樣 / 批跑 / CSV / 拼格影片(§9.3)
  table.py                     從 stdout.txt 產抓取/拿住/取杯表(JAW.md 欄位)
  cut_short.sh                 從 130 s wrap.mp4 剪 18 s 短版
  run_checks.sh                自測 + 對一次 run 自動判讀(§8)
  checks/                      run_checks.py + collect_runs.py + README.md(門檻與來源)
  make_demo_videos.sh          DEMO_1~6 剪接(需要開發資料夾;make_videos.sh --montage)
  find_isaac.sh                找 Isaac Sim(binary 或 pip)
  grip/gutil.py                wrap_vol 用的 kinematic 指頭 / 錄影工具(grasp_points.py = 它的離線排名原版)
  grip_attach/                 合指綁定模組(attach_grip.py)+ README(單片探針數字)
  rest/make_rest.py            解析式折好 rest shape(選用的 --rest_npz 輸入)
  carton.usd, carton.meta.json 紙箱(§4.5)
  mug.stl, bubble_normal.png   杯子網格、包材法線貼圖
scene/
  stationary_ai_carton_scene_flat.usd   雙臂工作站(14 MB)
  scene_final.usd              工作站 + 紙箱 + 包好的杯子(surface 包材網格,靜態),14 MB
  build_full_scene.py, README_scene_20261002.md   scene_final.usd 怎麼組的
  arm/INTERFACE.md             手臂 ↔ wrap_vol 介面:座標系(箱局部 L、vol 世界 V、場景 S)、兩邊輸出什麼、綁定介面(§5)、手臂 r1~v3 數據
  arm/robot_model.py           從場景 USD 產 URDF + Lula 描述檔
  arm/peel_traj_v3.py          掀開軌跡 v3(Lula IK 重解);會 exec peel_traj_v2.py,所以兩支都附
  arm/data/                    左右臂 URDF + yaml、軌跡(json/npz)、iface.json/npz(v3 規劃用的布狀態)
docs/
  RELEASE.md                   發行版統整:試過的所有方法、數字、誠實現況(§4 = 判準表)
  FINAL_PLAN.md                為何選 volume、正式旗標、折法多樣性計畫與結果
  vol/*.md                     各主題結論:JAW、QUALITY、EXTRACT/2/3、FOLD_DIVERSITY、DAMPING、PLASTIC、MATSWEEP(進行中)、
                               HAND2、DRAG、ROBUST、PEEL/2/3/4、SPEED;VARIANTS.csv
  deck/2026-10-14-Report.pptx  進度報告簡報
  carton_check/                紙箱相容測試(§4.5):wrap_vol.log、截圖
```

---

## 7. 腳本:哪支在哪裡跑

| 腳本 | 是什麼 | 怎麼跑 |
|---|---|---|
| `sim/run_release.sh` | 正式執行 | 終端機,在 `sim/` 裡(§1) |
| `sim/wrap_vol.py` | 模擬本體 | 終端機:`/isaac-sim/python.sh wrap_vol.py <旗標> --out DIR`(不能貼進 Script Editor) |
| `sim/run_checks.sh`、`checks/run_checks.py` | 判讀 | 終端機,系統 `python3`(要 numpy / scipy,沒有就自動用 `/isaac-sim/python.sh`) |
| `sim/table.py` | 抓取表 | `python3 table.py RUN_DIR ...` |
| `sim/fold_variants.py` | 折法多樣性 | `python3 fold_variants.py ...`(每組自己開 `/isaac-sim/python.sh wrap_vol.py`) |
| `sim/vol_pen.py`、`layer_gap.py`、`layer_order.py`、`jitter.py`、`cloth_iface.py` | 後處理 | 對 `wrap.npz` 跑 `python3 X.py ...` |
| `sim/rest/make_rest.py` | rest shape | `python3 rest/make_rest.py --gap_mm 10 --out rest_g10.npz` |
| `scene/arm/peel_traj_v3.py` | 手臂掀開軌跡 | `/isaac-sim/python.sh peel_traj_v3.py --flap yn ...`(開 `scene/scene_final.usd`) |
| `scene/arm/robot_model.py` | 產 URDF | 被 peel_traj_v2/v3 匯入 |

相依關係圖見英文版 §7。

---

## 8. 判準與最新 3 次分布

判準(FINAL_PLAN §2 + demo 追加):入箱 0 超出、穿杯 0、邊長比、yn 越線 ≥ 80%、放手後 ≥ 50%、他片 < 5%;
demo:yn / yp 拿住、杯子出箱落地、落地後布被帶起 < 30%。
GPU deformable **不可重現** —— 同旗標兩次結果不同 —— 所以每項都看分布,單次不算。表 = docs/RELEASE.md §4(各項最近三次有該欄位的完整鏈):

| 判準 | 最新 3 次分布 | 是否達標 | 出處 |
|---|---|---|---|
| 入箱 0 超出 | SPEED 完整鏈 4 組全 0;FOLD_DIVERSITY r7_08、r7_11 搬後 / 開蓋後 0 | 達標 | SPEED、FOLD_DIVERSITY |
| 搬運後仍在箱內 | r7_08、r7_11 超出 0;搬箱位移 1.0 mm(C3f) | 達標 | FOLD_DIVERSITY、JAW C3f |
| 穿杯 0 | extract4 X1~X3 全 0;EXTRACT3 X1~X3 全 0 | 達標(v4 起) | EXTRACT3 |
| 邊長比 | out_ga3 [0.509, 1.625];預設折序兩次 1.56 / 1.66 | 0.95~1.05 沒有任何組達到;改用 [0.50, 1.65](門檻落在雜訊內) | FOLD_DIVERSITY |
| yn 越線 ≥ 80%(掀完) | PEEL4 11 / 69 / 98;ROBUST 54 / 82 / 100 | 不穩(2~3 次中 1 次) | PEEL4、ROBUST |
| yn 放手後 ≥ 50% | PEEL4 0 / 0 / 100;HAND2 手 2 撤走後 1 / 100 / 2 | **不達標**(無塑性,§11 第 1 條) | PEEL4、HAND2 |
| yn 拿住(持續拿住定義) | extract4 X1~X3:76 → 76%、56 → 99%、1 → 0%;守衛都沒觸發 | 守衛達標;X3 手 2 綁在 x = 85,yn 只過線 1% | EXTRACT3 v4 |
| yp 拿住 | extract4 X1~X3 取杯前 80 / 98 / 97%,結束 79 / 97 / 96% | 達標 3/3 | EXTRACT3 v4 |
| 落地後布被帶起 < 30% | extract4 X1~X3 33.8 / 19.1 / 36.6% | **1/3** | EXTRACT3 |
| 他片被拖 < 5% | DRAG 基準 4.9 / 1.9 / 18.8;PEEL4 22.6 / 62.0 / 70.2 | **不達標**(5~70%) | DRAG、PEEL4 |
| 綁點數 ≥ 6 | extract4 yn 25 / 14 / 14 | 達標 | EXTRACT3 |
| 拿住時滑動 < 1 mm | 中位 0.07~0.14 mm | 達標 | PEEL4、ROBUST |

夾爪版(JAW.md):

| 次 | 指頭 | 精度 | 守衛 | 穿杯 | 布被帶起 抬起 / 離箱 / 落地 | 合指中 指-布最小距離 |
|---|---|---|---|---|---|---|
| extract6/X1 | 純視覺(jaw2) | final、edamp 0 | 沒觸發 | 0 | 31.7 / 31.7 / 34.8% | — |
| extract6/X2(影片這次) | 純視覺(jaw2) | final、edamp 0.02 | 沒觸發 | 0 | 23.5 / 19.7 / **22.0%** | — |
| extract6/C3f | **碰撞體(jaw3)** | fast、edamp 0.02 | 沒觸發 | 0 | 40.2 / 40.2 / 34.2% | 手 1 0.9 / 0.6、手 2 6.7 / 5.3、取杯 5.2 / **−3.4 mm** |

碰撞體指頭版**只有 1 次 fast**;原定的 3 次 final 驗證還沒做(§11 第 8 條)。

`sim/run_checks.sh RUN` 依 `checks/README.md`(volume 一節)的門檻判讀:自互穿 0 PASS / 1~20 WARN / > 20 FAIL、俯視覆蓋 ≥ 90% PASS、
開蓋後布頂 < 箱口、搬箱位移 < 10 mm…。對 extract6/C3f 的結果:PASS 6 / WARN 4 / FAIL 2(穿杯 1、反轉 26 —— fast 模式;QUALITY.md:穿模數只信 final)。

---

## 9. 正式旗標、快速模式、折法多樣性

### 9.1 正式(交付)—— `sim/run_release.sh final`
完整旗標見英文版 §9.1(與 `run_release.sh` 的 MATERIAL / GEOM / GRASP / HANDS / EXTRACT 相同),重點:
- 材料 `--young 2e3 --poisson 0.45 --thick_mm 4 --areal 0.1 --fric 0.8`;幾何 `--sheet_mm 500 --nxy 35 --tip_over_mm 30 --tuck 1 --carton carton.usd`。
- 抓取 = extract4 正式旗標(狀態選點、重夾、越壁 30、守衛 2.6 連續 2 格、slide 取杯、過壁 +40、落點 280)。
- 夾爪 = JAW.md 正式夾爪版 `--hand1_jaw 1 --hand2 jaw --extract_grip jaw` + `--jaw_collide 1`。
- 精度 `--quality final`(dt 1/240、solver 128)+ `--edamp 0.02`(折疊顫抖降約 40%,DAMPING;已在 JAW / FINAL_PLAN §2 的正式夾爪旗標裡;舊綁定版加阻尼時 2 次中 1 次 yn 守衛提早放手,EXTRACT3 v5)。

> **TODO(MATSWEEP):** `docs/vol/MATSWEEP.md`(進行中)在掃更軟 / 更重的材料(E、面密度)+ 越壁 60 mm,目標是放手後片垂著不彈回。
> 結論出來後若可用,正式旗標(`run_release.sh` 的 `MATERIAL` / `GRASP`、本節、§11 第 1 條)要更新。

### 9.2 開發 —— `sim/run_release.sh fast`
`--quality fast --edamp 0` = dt 1/120、solver 48、每 2 幀渲染 1 次、960 × 540(QUALITY.md)。
整鏈 wall/sim 6.1~6.4,同負載 final 10.5(快 1.7 倍;物理段快 2.1 倍;抓點規劃每次停 200~240 s,跟 dt 無關)。
fast 可以信:流程跑不跑得完、事件時間、綁點數量級、守衛會不會觸發、杯子出不出得來、反轉 / NaN、四折外形(±5 mm)。
只能信 final:自穿數(fast 30~32 vs final 5~8)、搬前 / 搬後超出內腔、掀開 / 他片 / 帶起的百分比。
fast 為什麼用 `--edamp 0`:fast + edamp 0.02 讓折好的布能量 4 倍、邊長比到 2.7,守衛 2.6 在掀開一開始就觸發(PLASTIC §5)。
dt 1/60 不能用(四折窄 13 mm、自穿 111、反轉 13)。

### 9.3 折法多樣性 —— `--fold_order`、`--seed`、`fold_variants.py`
```bash
cd sim
./run_release.sh fast F1 --fold_order yp,yn,xp,xn             # 指定折序;最後折的那片會在最外層(22/24 種)
./run_release.sh fast F2 --mug_off_mm=20,-10 --mug_yaw_deg 90 --seed 3   # 杯子偏位 / 轉向;--seed 記在 log
python3 fold_variants.py --list                # 24 種折序
python3 fold_variants.py --orders              # 24 種各寫一個 variants/o_<序>/cmd.sh
python3 fold_variants.py --n 12 --seed 7       # 隨機抽 12 組:布 420~560、長寬比 0.8~1.25、杯偏 ±30 mm、轉向 0/90/180/270 ±10°、越線 10~45、margin、wall、tuck、折速、E 1.5e3~3e3
python3 fold_variants.py --run --ids 'o_*'     # 逐一跑 --until box(一次一個,GPU < 20000 MiB 才開);--full = 通過的再跑整鏈
python3 fold_variants.py --csv; python3 fold_variants.py --video   # variants/VARIANTS.csv、videos/VARIANTS_grid.mp4
```
結果(FOLD_DIVERSITY):24 種折序全部包得進箱;物理判準 20/24 過,嚴格(+ 邊長比 [0.50, 1.65])9/24。
隨機 12 組:`tuck=0` 的 8 組全部 y 向超出內腔 → **用 tuck=1**(抽樣程式還是會抽到 0,§11 第 10 條);布小 + 偏位可能 infeasible(log 標 ★)。
最外層片由 `layer_order.py` 標出,手臂端照它選要掀哪片。

---

## 10. 版本與測試環境

| | |
|---|---|
| 版本 | volume_release_20261021(來源:`handoff_20260929/vol/` 2026-10-21 狀態;`wrap_vol.py` = 開發版 + 1 行:預設 `--carton carton.usd`) |
| Isaac Sim | 5.1.0-rc.19(Kit 107.3、PhysX 107.3.26),binary 安裝在 `/isaac-sim`(pip 安裝 `find_isaac.sh` 也找得到) |
| GPU | RTX 5090 32 GB、driver 580.173.02。一個 wrap_vol 約 5~6 GB × 2 context;已用 < 26000 MiB 才開 |
| Python 相依 | Isaac 內建 python:numpy、scipy、trimesh、imageio、PIL;`run_checks.sh` / `table.py`:系統 python3(+ numpy / scipy) |
| 工具 | ffmpeg / ffprobe(cut_short.sh、剪接) |
| 實測時間 | final 整鏈 797~1364 s wall(6.2~10.5 倍實時,看 GPU 負載);fast 793~829 s;`--until box` 約 4~5 分鐘 |

---

## 11. 已知限制

| # | 限制 | 影響 | 說明 / 試過什麼 |
|---|---|---|---|
| 1 | **放手後片不自垂,需撐住** | 「掀開放手」不成立:yn 放手後 ≥ 50% 只有 1/3(PEEL4),手 2 撐住後撤走 2/5(HAND2) | 4 mm 板立在箱壁上是臨界平衡、材料無塑性。demo 定義為掀開**並撐住**(§4.4)。TODO:MATSWEEP(軟材料 + 越壁 60) |
| 2 | 他片拖動 | 掀一片時其他片被帶動 5~70%(判準 < 5%) | 綁定在 PhysX 107.3 是硬約束(有限剛度被忽略)、力限代理、釘住 xp/xn 都沒用(DRAG) |
| 3 | 指頭盒 | 手臂端:夾指外框 36 × 70 × 60 mm,最好的手臂 run 仍插進布 18 mm,210 組 φ×ψ×偏移沒有零插入(INTERFACE §5)。模擬端(jaw3):取杯指抬起時插進布 −3.4 mm,只發生在手 1 還拿著 yp 蓋在杯上方的三手版(JAW C3f) | 抓點離牆 < ~30 mm 會撞牆或蓋 |
| 4 | 無塑性 | 折痕不留形,一放手就回彈 | runtime 改 rest shape 有效(回彈 43.6° → 0.5°)但重建後**這塊布自碰撞失效**(自穿 20 → 170~250),只能當備案(PLASTIC) |
| 5 | 落地後布被帶起 | 19~37%(3 次 final 中 < 30% 只有 1 次;夾爪 X2 22.0%、C3f 34.2%) | 杯子從布袋裡滑出時把掛在 yn 壁上的布拖出去(EXTRACT2/3) |
| 6 | 不可重現 | 同旗標 yn 越線 0~100%,夾前覆蓋 48~91% | 一律看 ≥ 3 次 |
| 7 | 顫抖 | edamp 0.02 降約 40%,但有代價(§9.1、§9.2) | DAMPING |
| 8 | 碰撞體指頭(`--jaw_collide 1`)只驗過 1 次 fast | 附的影片是純視覺指頭(jaw2) | `./make_videos.sh` 會用碰撞體指頭重產;3 次 final 待做 |
| 9 | 速度 | 整鏈 13~23 分鐘;抓點規劃停 200~240 s(CPU) | 只有降頻渲染與 fast 模式是安全的;放寬 dt / solver 會傷掀開(SPEED、QUALITY) |
| 10 | `fold_variants.py --n` 仍會抽到 `tuck=0` | 這類樣本 8/8 超出內腔 | 用 tuck=1(改產生的 `cmd.sh` 或抽樣程式) |
| 11 | volume 包材不在雙臂場景裡 | `wrap_vol.py` 自己建 stage(紙箱 + 布 + 杯 + kinematic 手);`scene_final.usd` 裡是舊的 surface 包材網格 | 跟手臂的銜接靠座標與快照(`scene/arm/INTERFACE.md`、`cloth_iface.py`) |
| 12 | GPU 共用 | 兩個錄影同時跑會 OOM | `run_release.sh` 等 < 26000 MiB;一次一個 |
| 13 | `wrap_vol.py --until box` / `--until move` 同時給 `--extract 1` | 取杯段接在縮短後的結尾之後,搬箱途中把杯子拖出箱外(2026-10-21 紙箱測試發現) | `run_release.sh` 設了 `UNTIL` 就拿掉取杯旗標;直接呼叫 `wrap_vol.py` 只跑一段時不要給 `--extract` |

<p align="right"><a href="#繁體中文">↑ 回到頂端</a> · <a href="#english">English ↑</a></p>
