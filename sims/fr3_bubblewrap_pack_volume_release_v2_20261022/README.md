# Bubble-Wrapped Mug in a Carton — Volume Wrap Release v2<br>氣泡布包裹馬克杯入箱 —— volume 包材交付版 v2

**Language / 語言:** [English](#english) · [繁體中文](#繁體中文)

---

# English

> **v2 changes the unpacking.** The package is taped shut and boxed; after the carry and opening, a hand takes the
> **whole package out onto the table**, and a wide two-finger gripper peels the four flaps open **by friction only**
> (no vertex binding) in the order yn → yp → xn → xp. **Each flap stays open on the table after it is released**, and
> then the mug is taken away. One command runs the whole chain; the videos are in git.
> v1 (peel inside the box and keep holding the flap open, bind-on-close grippers) is kept as
> [`../fr3_bubblewrap_pack_volume_release_20261021`](../fr3_bubblewrap_pack_volume_release_20261021).
> What changed v1 → v2: `CHANGELOG.md`. Every number below comes from a file in `docs/` (cited per row).

| | |
|---|---|
| **Version** | volume_release_v2_20261022 = the **v2.1** flag set of `docs/V2_FLOW.md` ("整鏈驗證(v2.1)"), also recorded in `docs/FINAL_PLAN.md` §2 |
| **Tested on** | Isaac Sim 5.1.0-rc.19 (Kit 107.3 / PhysX 107.3.26), RTX 5090 32 GB, NVIDIA driver 580.173.02 |
| **Get it** | git: this folder (videos included) · tarball: `handoff_volume_v2_20261022.tgz` (same content) |

## Contents

1. [Quick start](#1-quick-start)
2. [What the simulation does](#2-what-the-simulation-does)
3. [Why the flaps are opened on the table, not in the box](#3-why-the-flaps-are-opened-on-the-table-not-in-the-box)
4. [Results (final, whole chain ×2)](#4-results-final-whole-chain-2)
5. [Flags: official, fast, save / resume, run3.sh](#5-flags-official-fast-save--resume-run3sh)
6. [Videos](#6-videos)
7. [Files](#7-files)
8. [Scripts: which run where](#8-scripts-which-run-where)
9. [Version and test environment](#9-version-and-test-environment)
10. [Known limitations](#10-known-limitations)

---

## 1. Quick start

```bash
cd sim
./run_release.sh final X1   # the deliverable (v2.1): --quality final --edamp 0.02, ~32 min, 1280x720, 195 s + 24 s short cut
./run_release.sh fast  X1   # development:           --quality fast  --edamp 0,    ~15 min, 960x540
UNTIL=fold ./run_release.sh fast K1   # only the four folds (~1 min) — the smoke test of this release (§9)
UNTIL=box  ./run_release.sh fast K2   # folds + tape + into the box + lids closed
```

Output: `runs/<mode>_<NAME>/1/` — `wrap.mp4`, `wrap_vol.log` (one row per 0.5 s + SUMMARY), `wrap.npz` (cloth / mug /
tets / layer indices per snapshot), `grasp.json`, `v2.json`, `key_*.png`, `stdout.txt`. After a whole-chain run
`runs/<mode>_<NAME>/TABLE.md` holds the two tables of §4 (`v2/table.py`) and the rigid-rotation split (`v2/rigid.py`);
a final run also gets `short.mp4` (`v2/cut_short2.sh`).

**One simulation at a time.** `run_release.sh` goes through `run3.sh`: a launch lock (one start at a time), wait until GPU
memory < `GPU_MAX` (29500 MiB), and a watchdog that kills and restarts a run whose cloth is not being simulated
(near-full GPU makes PhysX fail **silently**, §10 #6). To share the lock with other `run3.sh` users set `LOCK=/path/.run3_launch.lock`.

To look at the scene files in the Isaac Sim UI: same as v1 (`scene/`, File → Open; do not paste `wrap_vol.py` into the
Script Editor — it creates its own `SimulationApp`). `wrap_vol.py` is headless; watch `wrap.mp4` and `key_*.png`.

---

## 2. What the simulation does

### 2.1 The wrap (unchanged from v1)
4 mm thick tetrahedral **volume deformable** plate, 500 × 500 mm, 35 × 35 grid (2592 points, 6125 tets), self-collision on,
`--young 2e3 --poisson 0.45 --areal 0.1 --fric 0.8`, contact / rest offset 2 / 0.5 mm (FINAL_PLAN §1-§2).
Carton = the v1 / surface-handoff carton (270 × 230 × 131 mm, cavity 264 × 224), byte-identical, all bodies kinematic.

### 2.2 The chain (sim time, s; fast and final share the timeline — V2_FLOW "時序" + "整鏈驗證(v2.1)")
| t (s) | Stage |
|---|---|
| 0.5 – 14.5 | Four folds: xp @0.5, xn @4.0, yp @7.5, yn @11.0 (3 s each, 0.5 s hold); yn ends up outside |
| 14.5 – 17.5 | Tuck the ears (side plates push the four corners to cavity − 3 mm) |
| 17.5 – 26.5 | Into the carton, lower lids 18.5 – 22.5, upper lids 22.5 – 26.5 |
| 26.9 | **Tape**: the fold anchors are **kept** as tape (26 anchors, 88 vertices); every step their kinematic target = mug pose × their pose relative to the mug at this instant (`--tape_follow 1`). Mug turns dynamic |
| 28.9 – 34.9 | Carry the carton +200 mm y, +100 mm z |
| 36.9 – 45.9 | Open upper lids, then lower lids, hold 3 s |
| 45.9 – 59.6 | **Hand 2 takes the whole package out**: down, close, lift (actually 169 – 171 mm), move 400 mm in −y to the table, put down. At 56.2 the mug turns dynamic again and the tape anchors **stop following** (they stay where they are) |
| 60.6 – 91.3 | **Hand 1 peels yn**: 150 mm wide fingers, lower finger slides under the free edge, upper finger closes; **the yn tape is cut the moment the grip is closed**; lift 40 mm, flip 180° about the hinge on the table (8 s), hold 2 s, release (open 2 mm, slide out along the flap, `--v2_xrel_slide 2`), watch 10 s |
| 91.3 – 122.0 | Hand 1 peels yp the same way |
| 122.0 – 183.4 | x flaps: hand 2 holds the mug; hand 1 switches to a second pair of **300 mm** fingers (`--wide_mm_x 300`) and peels xn, then xp, like the y flaps (grip first, cut that flap's tape on close — `--v2_xmode tapegrip`). The moment an x flap is gripped, **hand 2 opens and lifts 60 mm** (mug dynamic) so its fingers don't pin the flap's corner (`--v2_h2_free 1`); 2.3 s before the next stage it re-grips the mug at a position whose open-to-close sweep keeps > 2 mm from the cloth (20 candidates) |
| 184.4 – 195.3 | Hand 2 lifts the mug 150 mm, moves it +380 mm in x, sets it on the table, opens |

### 2.3 Two hands, no binding
- **Hand 1** (orange) peels all four flaps. Its fingers are kinematic **colliders** (`--jaw_collide 1`), 150 × 40 × 6 mm for yn / yp and 300 × 40 × 6 mm for xn / xp,
  friction 2.0, closed gap = thickness − 1 mm (squeeze 1 mm). Holding is **friction only** (`--grasp_attach 0 --pick_mode wide`; PGRASP.md: 17 – 55 vertices between the fingers, nothing dropped while peeling).
- **Hand 2** (purple) takes the package out, holds the mug during the x flaps, and takes the mug away (`--extract_mode lift --extract_out_mm 380`).
  Its mug grip uses collider fingers and then the mug follows the hand kinematically (as in v1). **The whole-package take-out is not a friction grip** — see §10 #2.
- Binding is no longer used anywhere: v1 bound the vertices inside the closed fingers; v2 does not.
- Tape is the fold anchors left in place. Cutting a flap's tape = removing that flap's anchors.

---

## 3. Why the flaps are opened on the table, not in the box

**Geometry.** In the box the flap's hinge (fold line, |y| = 71.5 mm) sits on the box floor about 40 mm from the inner wall (cavity half-width 112 mm),
and the wall is about 131 mm high. The flap is about 157 mm long from its hinge (material length L, TABLE_UNWRAP) — most of it is used up just climbing the wall,
so its centre of mass cannot get past the wall: at the over-the-wall pose the yn centroid is at y = −73 … −90 mm with the bind grip (MATSWEEP) and
−89 … −102 mm with the wide friction grip (PGRASP), never past the wall's outer face at −113.5 mm. Pulling 60 mm further over the wall does not help
(centroid −73 / −84 MATSWEEP, −100.1 PGRASP): the material stretches (edge ratio 1.57 – 3.5) instead of rotating. On release only 1 – 17 % of the flap is outside the wall,
and 10 s later 0 % — the flap falls back into the box. **On the table** the hinge lies on the table and the flap can lie flat:
10 s after release the flap angle is 0 – 4°, 100 % crossed, centroid 81 – 85 mm outside the hinge and 1 – 2 mm above the table (TABLE_UNWRAP: bind 3/3, wide friction 3/3, second flap yp 1/1).

**Why material coefficients are not the way (MATSWEEP).** 9 combinations of E 0.5 / 1 / 2 × 10³ Pa × areal density 0.1 / 0.2 / 0.3 kg/m², plus 2 with 60 mm over the wall:
**10 s after release 0 % of the flap is outside the wall in all 11**; the best "crossed" is 25 % (E 2e3, 0.3) and that one's mug-top cover after opening drops to 68 %.
Softer material stretches more and is held by fewer vertices (peeled 79 % → 23 – 48 %); heavier material loosens the package (cover after opening 90 → 68 %, 78 → 51 %);
E 5e2 with density ≥ 0.2 breaks the package (fold bbox 416 × 282 / 466 × 333 mm instead of 245 – 255 × 240 – 256). Recommendation kept: E 2e3, 0.1.

**Why plasticity is not the way (PLASTIC §6, CREASE).** PhysX 107.3 has no plastic deformable. Writing the folded shape into the rest shape and rebuilding the body does remove the
spring-back (probe 43.6° → 0.5°) but it **switches off self-collision** for layers that are closer than ≈ 2 × contact offset in the rest shape (self-penetration 20 → 171 – 252).
Spreading the rest layers by 8 mm fixes that (fast ×3: cover after opening 97 – 98 %, self-penetration max 28 – 31 vs control 27 – 30) but in the **final whole chain** the baked wrap
could not be peeled: the yn guard tripped (edge ratio 3.97 > 2.6, crossed 1 %), the wrap was lifted with the mug 62 % (control 22 – 35 %), volume ratio 0.98 → 0.91.
And on the table a baked wrap flips back after release (0.5 / 2 / 10 s: 46° / 81° / 138°, TABLE_UNWRAP plastic control, 1 run with a poor grip — qualitative): crease memory works **against** unwrapping.
For the surface wrap, `restBendAngles` is not read by PhysX 107.3 at all; the rest-shape rebuild works there but has no practical effect on the bend-4 material (CREASE).

---

## 4. Results (final, whole chain ×2)

Criteria (V2_FLOW): tape points move < 3 mm relative to the mug during the carry; take-out: mug-top cover ≥ 90 % and package shape change (after best rigid alignment) median < 15 mm;
each flap 10 s after release: flap angle < 45° (0° = flat outward, 90° = upright, ≥ 180° = back on the mug) and crossed ≥ 80 %;
mug-top cover before extraction ≤ 10 %; extraction OK (mug moved > 150 mm, out of the cavity, 0 cloth vertices in the mug after lifting); wrap lifted with the mug (max while lifting / final) < 15 %.
Runs: `V21T/1`, `V21T/2` = `run_release.sh final` flags, both run at the same time (`docs/V2_FLOW.md` "整鏈驗證(v2.1)"; raw table `sim/v2/TABLE_V21T.md`).

**Table 1 — per stage**

| Run | Out of cavity: closed / before carry / after carry / opened (vertices) | Tape vs mug after carry, median / max mm | Edge ratio max while carrying | Take-out lift mm / cover after | Shape change after take-out, median / p90 mm | Take-out | Cover before extraction | Extraction (after lift) | Wrap lifted max / final | Self-pen. / mug-pen. max (whole run) | Pass | Wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V21T/1 | 0 / 3 / 4 / 5 | 0.01 / 0.36 | 1.82 | 171 / 99 % | 4.5 / 9.4 | ✓ | 1 % | OK | 0.3 % / 0.0 % | 33 / 17 | ✗ (xn 87° at +10 s) | 1921 |
| **V21T/2** | 0 / 4 / 3 / 3 | 0.02 / 0.39 | 1.87 | 170 / 99 % | 6.2 / 11.5 | ✓ | 1 % | OK | 2.8 % / 5.4 % | 14 / 6 | **✓** | 1911 |

**Table 2 — per flap**

| Run | Flap | Vertices between fingers when closed | Before release: angle / crossed | +2 s angle | +10 s angle / crossed | Other flaps moved > 10 mm (10 s) | Pass |
|---|---|---|---|---|---|---|---|
| V21T/1 | yn | 41 | 1° / 100 % | 4° | 6° / 100 % | 44.8 % | ✓ |
| V21T/1 | yp | 27 | 1° / 100 % | 0° | 0° / 100 % | 32.8 % | ✓ |
| V21T/1 | xn | 37 | 0° / 99 % | 63° | **87°** / 94 % | 20.7 % | ✗ |
| V21T/1 | xp | 33 | 1° / 98 % | 33° | 41° / 96 % | 23.6 % | ✓ |
| V21T/2 | yn | 31 | 1° / 100 % | 0° | 0° / 100 % | 22.7 % | ✓ |
| V21T/2 | yp | 41 | 1° / 96 % | 112° | 20° / 96 % | 45.5 % | ✓ |
| V21T/2 | xn | 34 | 1° / 99 % | 22° | 9° / 100 % | 24.3 % | ✓ |
| V21T/2 | xp | 35 | 1° / 100 % | 4° | 8° / 100 % | 17.8 % | ✓ |

**1 of 2 whole-chain runs passes everything (V21T/2; it is the run in `VOL_v2_full.mp4`)**; V21T/1 fails only xn (87°: 0.5 s after release it was −0.2°, within 1.5 s it rose to 63°
while hand 1's fingers were 38 – 67 mm away — the corner fold-back of §10 #1). While hand 2 lets go, the mug is dragged 2 – 3 mm; while a y flap is gripped the mug is pushed 15 – 22 mm (no wall on the table).

Earlier v2.0 runs that fix the tape / take-out numbers (V2_FLOW "結論", fast ×3 + final ×2, older x-flap method): **tape 5/5** (tape points vs mug after carry median 0.01 – 0.16 mm,
max 0.09 – 1.63 mm; control with fixed anchors: 173 / 209 mm off, edge ratio 7.1, self-penetration 297, 360 vertices out of the cavity); **take-out 5/5** (cover 99 – 100 %,
shape change median 3.4 – 11.7 mm, mug penetration 0); **yn / yp on the table 10/10** (+10 s angle −2 … 3°, 100 % crossed).
GPU deformables are not reproducible: same flags, different outcome — judge on several runs.

---

## 5. Flags: official, fast, save / resume, run3.sh

### 5.1 Official (v2.1) — `sim/run_release.sh final`
= `v2/run.sh` base flags (run3.sh `@demo` + table unwrap + wide friction grip + v2 flow) + the v2.1 line (V2_FLOW "整鏈驗證(v2.1)", FINAL_PLAN §2):
```
@demo     --sheet_mm 500 --grasp 1 ... --hand1_jaw 1 --extract_grip jaw --edamp 0.02        (run3.sh, FINAL_PLAN §2 gripper version)
v2 base   --hand2 off --hand2_keep 0 --hold_yp 0 --second 1 --guard_yn 3.5 --guard_n 2 --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --release_watch 1 --grasp_tail_s 1
wide      --grasp_attach 0 --pick_mode wide --wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 1 --clear_mm 2 --pick_mm 0
flow      --tape_follow 1 --takeout 1 --v2_xflaps 1 --v2_hold_cup 1 --extract 1 --extract_mode lift --extract_out_mm 380
v2.1      --quality final --edamp 0.02 --ut_release_up 1 --v2_xmode tapegrip --v2_h2_free 1 --wide_mm 150 --wide_mm_x 300 --v2_xrel_slide 2
```
Later flags override earlier ones (argparse keeps the last). Extra arguments to `run_release.sh` are appended. The same run in the development layout:
`vol/v2/run.sh V21T --quality final --edamp 0.02 --ut_release_up 1 --v2_xmode tapegrip --v2_h2_free 1 --wide_mm 150 --wide_mm_x 300 --v2_xrel_slide 2` (= `sim/v2/run.sh` here).

### 5.2 Development — `sim/run_release.sh fast`
`--quality fast --edamp 0` (dt 1/120, solver 48, every 2nd frame rendered, 960 × 540). **Use it to check that the chain runs, timings and grip counts; do not judge the x flaps or
package integrity on it**: in fast the mug turns 17 – 22° inside the soft package in the box and rolls another 12 – 20° on the table (final 5 – 9°, V2_FLOW `rigid.py` table),
and freshly un-taped x flaps spring open by themselves in fast (5 of 6 crossed ≥ 60 %) but not in final (0 – 41 %), so fast cannot tell x-flap methods apart (V2_FLOW "x 片").
The whole chain with the v2.1 flags has been run in final only (V21T ×2); fast was run with v2.0 flags (B ×3: 861 – 890 s wall, two at once).

### 5.3 Save / resume (`--save_state` / `--at` / `--load_state`, SPEEDUP.md, V2_FLOW "存檔續跑")
```bash
cd sim
./run_release.sh final S1 --save_state ../runs/final_S1/S.npz --at xflaps --save_exit 1   # run to t = 122.0 (yn, yp done) and stop: final ~1077 s, fast ~494 s
LOADCHK=0 ./run_release.sh final R1 --load_state ../runs/final_S1/S.npz                    # resume x flaps + extraction (73 s physics): final 720 – 1000 s, fast 330 – 480 s
LOADCHK=0 ./run_release.sh final R2 --load_state ../runs/final_S1/S.npz --v2_xmode sweep   # flags of the x-flap / extraction stages may change; the fold / box / carry timeline must not (assert)
```
`--at xflaps` also saves tape anchor poses, finger stop points, table collision state and the y-flap plans. Resumed first frame differs from the save by max 0.83 mm.
`LOADCHK=0` is needed because the cloth is at rest at the save point and `run3.sh` would otherwise take three identical measurements as "frozen".
Other save points (`--at grasp|opened|<seconds>`) are for the v1 in-box chain (SPEEDUP.md).

### 5.4 `run3.sh` — several runs and the GPU gate
```bash
cd sim
N=2 v2/run.sh F --quality final --edamp 0.02 --ut_release_up 1 --v2_xmode tapegrip --v2_h2_free 1 --wide_mm 150 --wide_mm_x 300 --v2_xrel_slide 2   # 2 final runs → v2/F/{1,2}
python3 v2/table.py v2/F;  python3 v2/rigid.py v2/F
N=1 v2/runx.sh S_final --quality final --edamp 0.02 --ut_release_up 1 --save_state 'v2/x/S_final/S{k}.npz' --at xflaps --save_exit 1   # x-flap experiments (V2_FLOW)
N=1 table/run.sh W wide                     # no carton: fold, tape, unwrap yn on the table (TABLE_UNWRAP)
```
`./run3.sh NAME [flags]` starts N runs (default 3, `MAXPAR` at once), replaces `{k}` with the run index and `@demo` with the FINAL_PLAN §2 gripper flags.
Environment: `N`, `KS`, `MAXPAR`, `GPU_MAX` (29500), `HEAD`, `TRIES`, `STARTUP_S`, `LOCK` (default `sim/.run3_launch.lock`), `ISAAC`, `TABLE` (table command, empty = none), `LOADCHK`.
Measured (SPEEDUP §3): near-full GPU gives `PxCudaContextManager out-of-memory`, `Scene state is corrupted`, or **no error and no cloth simulation** (edge ratio stays [1.000, 1.000]) with EXIT 0;
run3 kills such a run and restarts it when memory < GPU_MAX − HEAD (up to 6 times). Two runs launched together go out of memory together, hence the launch lock.

---

## 6. Videos

In git (103 MB). `./make_videos.sh [option]` regenerates each one (§8).

| Video | Length | Shows | Source run | Regenerate |
|---|---|---|---|---|
| `VOL_v2_full.mp4` | 195.3 s, 1280×720 | ★ The v2.1 chain: fold, tape, box, carry, open, take out to the table, peel yn / yp (150 mm fingers), switch to 300 mm and peel xn / xp (hand 2 lets go and re-grips), take the mug away | V21T/2 (passes all) | `./make_videos.sh` |
| `DEMO_v2_short.mp4` | 23.8 s | Short cut of the above: lids ×8, carry ×6, open ×6, take-out ×4, yn ×6, yp ×6, xn ×8, xp ×8, re-grip + extraction ×4 | V21T/2 (`v2/cut_short2.sh`) | `./make_videos.sh` |
| `VOL_v2x2_compare.mp4` | 17.3 s, 6 panes | x flaps + extraction (t 124 – 193 s, ×4), resumed from one final save: D (hand 2 keeps holding), E (hand 2 lets go), F (+300 mm), G (+press root), H (+slide release), GH | V2_FLOW "x 片 第二輪" | `./make_videos.sh --x2` |
| `DEMO_unwrap_table_short.mp4` | 14.8 s | No carton: fold, tape, wide fingers slide under yn, flip 180°, the flap stays flat after release | TABLE_UNWRAP W/2 | `./make_videos.sh --table` |
| `VOL_unwrap_table_yp.mp4` | 99.8 s | No carton: yn then yp opened on the table (bind version), both stay flat | TABLE_UNWRAP Y/1 | `./make_videos.sh --table` |
| `VOL_pgrasp.mp4` | 86.6 s | In the box: wide friction grip holds yn all the way over the wall, released → falls back into the box (why §3) | PGRASP C150 | `./make_videos.sh --pgrasp` |
| `DEMO_pgrasp_short.mp4` | 11.2 s | Short cut of the above | PGRASP C150 (`pgrasp/cut_short.sh`) | `./make_videos.sh --pgrasp` |
| `VARIANTS_grid.mp4` | 6 s | 22 fold orders side by side (fold diversity, v1) | `fold_variants.py --video` | `./make_videos.sh --variants` |
| `DEMO_ALL.mp4` + `DEMO_1` … `DEMO_6` | 291 s | v1 montage: surface pipeline, volume pipeline, grasp probes, dual arm, wrap peel, two-hand peel-and-hold extraction (`DEMO_INDEX.md`) | v1 | `./make_videos.sh --montage DEV` |

---

## 7. Files

```
README.md, CHANGELOG.md      this document; v1 → v2 changes
make_videos.sh               regenerate videos/ (§6)
videos/                      result videos (in git) + DEMO_INDEX.md (v1 montage index)
sim/                         the simulation — run everything from inside sim/
  run_release.sh               ★ one command: final | fast (v2.1 flags), UNTIL=fold|box|move, save / resume via extra flags
  wrap_vol.py                  the simulation (Isaac Sim 5.1 volume deformable, whole chain); default --carton carton.usd
  volcommon.py, vol_pen.py, layer_order.py, layer_gap.py, grasp_plan.py, grip_common.py, grip/gutil.py   imported by wrap_vol.py
  run3.sh                      N runs + launch lock + GPU gate + frozen-run restart (dev run3.sh + run3x.sh merged)
  table3.py                    run3.sh's default per-metric table (v1 chain columns)
  v2/run.sh                    v2 flow base flags → run3.sh (output v2/NAME/k)
  v2/runx.sh                   same flags, output v2/x/NAME/k (x-flap experiments, save / resume)
  v2/table.py, v2/rigid.py     the two v2 tables; rigid rotation of the package vs mug rotation
  v2/tablex.py, v2/tablex2.py  x-flap round 1 / round 2 tables
  v2/cut_short2.sh             v2.1 short cut (24 s); v2/cut_short.sh = v2.0 short cut; v2/cut_x.sh = side-by-side x-flap video
  v2/TABLE*.md                 raw tables from the development runs (V21T = §4)
  table/run.sh, table.py, cut_short.sh, TABLE.md   unwrap on the table without a carton (TABLE_UNWRAP)
  pgrasp/cut_short.sh          short cut for VOL_pgrasp
  cloth_iface.py, jitter.py, fold_variants.py, rest/make_rest.py, grip/grasp_points.py, grip_attach/   as in v1
  make_demo_videos.sh          v1 montage (make_videos.sh --montage)
  find_isaac.sh                locate Isaac Sim
  carton.usd, carton.meta.json, mug.stl, bubble_normal.png   carton (= v1), mug, wrap normal map
scene/                       = v1: dual-arm workstation USD, scene_final.usd, arm/ (INTERFACE.md, peel trajectories, URDF)
docs/
  V2_FLOW.md                   ★ v2 flow, flags, all v2 runs, x-flap rounds 1-2, v2.1 validation, known limitations
  TABLE_UNWRAP.md              unwrap on the table: flaps stay flat (6/6 + 1/1); tape needed; plastic control flips back
  PGRASP.md                    pure friction wide grip: holds, but the flap cannot get over the wall
  MATSWEEP.md                  material sweep: no E / density keeps a released flap outside the wall
  PLASTIC.md                   runtime rest-shape bake (plasticity): works, kills self-collision; §6 spread rest
  CREASE.md                    surface-wrap crease memory probe (restBendAngles not read by PhysX 107.3)
  SPEEDUP.md                   save / resume, grasp-planner speed-up, run3.sh
  FINAL_PLAN.md                why volume, the official flag sets (§2 includes v2.1)
  RELEASE.md                   three weeks of methods and conclusions (v1-era summary)
  smoke_check/                 the smoke run of this folder (§9): stdout.txt, run3.log, key_fold_done.png
```

---

## 8. Scripts: which run where

| Script | What | How |
|---|---|---|
| `sim/run_release.sh` | Official run | Terminal, `cd sim` (§1) |
| `sim/wrap_vol.py` | The simulation | Terminal: `/isaac-sim/python.sh wrap_vol.py <flags> --out DIR` (never in the Script Editor) |
| `sim/run3.sh`, `v2/run.sh`, `v2/runx.sh`, `table/run.sh` | Batches with the GPU gate | Terminal, from `sim/` |
| `sim/v2/table.py`, `rigid.py`, `tablex*.py`, `table/table.py`, `table3.py` | Tables | system `python3` (numpy, scipy) |
| `sim/v2/cut_*.sh`, `table/cut_short.sh`, `pgrasp/cut_short.sh` | Short cuts | ffmpeg |
| `make_videos.sh` | Regenerate videos | Terminal, from this folder |
| `sim/fold_variants.py` | Fold diversity (v1) | `python3 fold_variants.py ...` |

```
run_release.sh ─► run3.sh ─► wrap_vol.py ─► volcommon, vol_pen, grip_common, layer_gap, grasp_plan(→ layer_order), grip/gutil
               ├─► v2/table.py, v2/rigid.py
               └─► v2/cut_short2.sh (final, whole chain)
```

---

## 9. Version and test environment

| | |
|---|---|
| Release | volume_release_v2_20261022. Code = `sims/fr3_bubblewrap_pack_20261007/vol/` at repo commit `6fcd916` (identical to the development folder at that time) + the `[release]` edits listed in CHANGELOG |
| Isaac Sim | 5.1.0-rc.19 (Kit 107.3, PhysX 107.3.26), binary install in `/isaac-sim` (pip install also found by `find_isaac.sh`) |
| GPU | RTX 5090 32 GB, driver 580.173.02. One run ≈ 5-6 GB × 2 contexts |
| Python deps | Isaac's python: numpy, scipy, trimesh, imageio, PIL (bundled); tables: system python3 + numpy / scipy; ffmpeg / ffprobe |
| Measured times | final whole chain 1911 – 1921 s wall (two at once); fast v2.0 chain 861 – 890 s (two at once); `--until fold` 50 s |
| **Smoke test of this folder** (2026-10-21) | `UNTIL=fold ./run_release.sh fast SMOKE` from this folder's `sim/`: EXIT 0, no Traceback; 18.1 s sim in 36 s loop / 50 s total; carton.usd read (5 kinematic bodies, cavity ±132 × ±112); fold bbox 254 × 239 × 124 mm; out of cavity before boxing 0 / 0 (cloth / mug); self-penetration max 31 (fast, QUALITY.md: fast 30-32), mug penetration 0, inversions 0. Log: `docs/smoke_check/` |

---

## 10. Known limitations

| # | Limitation | Numbers | Notes |
|---|---|---|---|
| 1 | **x-flap corner folds back** | Whole chain: V21T/1 xn +10 s 87° (V21T/2 fine) → **1 of 2** whole runs pass all. Resumed H runs: xp 48 – 60° | A folded corner near the yp root (flat x 179 – 221, y 136 – 221 mm, already folded back z 26 – 31 before the grip) pulls half of the free edge up and back after release. Not fixed: a separate grip on that corner (+15 – 20 s slot), or carrying the x corners out while flipping yp (V2_FLOW "已知限制") |
| 2 | **Whole-package take-out is not a friction grip** | — | The mug turns kinematic and follows hand 2, the tape follows the mug; hand 2's fingers are visual for this stage. A friction grip is impossible here: the package (~260 × 223 mm) fills the 264 × 224 mm cavity, ~3 mm per side for the fingers |
| 3 | After boxing, 2 – 6 boundary vertices touch the wall | V21T: before carry / after carry / opened 3 – 4 / 3 – 4 / 3 – 5; all < 2.5 mm beyond the cavity (within contact thickness) | The verdict marks FAIL when ≥ 1 vertex is outside in x / y; v1 extract6/X2 had 1 – 2 |
| 4 | fast precision: the mug rotates inside the package | fast: +17 – 22° in the box, +12 – 20° rolling on the table; final 5 – 9° | Use final numbers or the "shape change" column for package integrity (§5.2) |
| 5 | fast and final differ on the x flaps | Un-taped x flaps: fast 5/6 open by themselves, final 0 – 41 % | Judge x-flap methods in final only |
| 6 | **PhysX fails silently when the GPU is nearly full** | No error, cloth not simulated, EXIT 0 (SPEEDUP §3) | Run through `run_release.sh` / `run3.sh` (watchdog + restart); one simulation at a time |
| 7 | Mug pushed while a y flap is gripped | 15 – 22 mm (V21T); x flaps 2 – 7 mm | No carton wall on the table; the mug is dynamic during y flaps |
| 8 | Other flaps moved > 10 mm while peeling | 17.8 – 45.5 % (V21T) | Mostly the ear corners of xp / xn next to yn (TABLE_UNWRAP) |
| 9 | Mug penetration while the lower finger slides under | whole-run max 17 / 6 (V21T); 5 – 10 when gripping yp, 0 – 5 after lift (v2.0); 40 – 60 inverted tets for a moment in final, recovered | After lifting the mug: 0 |
| 10 | Not reproducible | Same flags: V21T/1 vs /2 above | Judge on ≥ 2-3 runs |
| 11 | Take-out lifts 169 – 171 mm, not 150 | lift = max(`--tk_lift_mm`, package bottom 40 mm above the box rim) | 150 mm leaves ~19 mm to the open lid |
| 12 | `--takeout 1` needs `--until all` | assert in wrap_vol.py | `run_release.sh` drops take-out / x-flap / extraction flags when `UNTIL` is set |
| 13 | Speed | final whole chain ~32 min | Use save / resume (§5.3) to iterate on the later stages |
| 14 | The volume wrap is not in the dual-arm scene | as v1 | Coupling by coordinates and snapshots (`scene/arm/INTERFACE.md`, `cloth_iface.py`) |

<p align="right"><a href="#english">↑ Back to top</a> · <a href="#繁體中文">繁體中文 ↓</a></p>

---

# 繁體中文

> **v2 改了拆包的方式。** 包好後先用膠帶封住再入箱;搬箱、開蓋之後,手 2 把**整包拿出來放到桌面**,
> 手 1 用寬指兩指夾爪**純摩擦**(不綁頂點)依序掀開 yn → yp → xn → xp,**每一片放手後自己攤在桌上**,最後取走杯子。
> 一條指令跑完整鏈,影片附在 git 裡。
> v1(在箱內掀開並一直撐住、合指才綁定的夾爪)保留在
> [`../fr3_bubblewrap_pack_volume_release_20261021`](../fr3_bubblewrap_pack_volume_release_20261021)。
> v1 → v2 改了什麼:`CHANGELOG.md`。以下數字都出自 `docs/` 的檔案(每列註明出處)。

| | |
|---|---|
| **版本** | volume_release_v2_20261022 = `docs/V2_FLOW.md`「整鏈驗證(v2.1)」那組旗標,`docs/FINAL_PLAN.md` §2 也有記 |
| **測試環境** | Isaac Sim 5.1.0-rc.19(Kit 107.3 / PhysX 107.3.26)、RTX 5090 32 GB、NVIDIA driver 580.173.02 |
| **取得方式** | git:這個資料夾(含影片)· 壓縮檔:`handoff_volume_v2_20261022.tgz`(內容相同) |

## 目錄

1. [快速開始](#1-快速開始)
2. [模擬在做什麼](#2-模擬在做什麼)
3. [為什麼搬到桌面上掀,不在箱內掀](#3-為什麼搬到桌面上掀不在箱內掀)
4. [結果(final 整鏈 2 次)](#4-結果final-整鏈-2-次)
5. [旗標:正式、fast、存檔續跑、run3.sh](#5-旗標正式fast存檔續跑run3sh)
6. [影片](#6-影片)
7. [檔案](#7-檔案)
8. [腳本:哪支在哪裡跑](#8-腳本哪支在哪裡跑)
9. [版本與測試環境](#9-版本與測試環境)
10. [已知限制](#10-已知限制)

---

## 1. 快速開始

```bash
cd sim
./run_release.sh final X1   # 交付版(v2.1):--quality final --edamp 0.02,約 32 分鐘,1280x720,195 s + 剪 24 s 短版
./run_release.sh fast  X1   # 開發用:       --quality fast  --edamp 0,   約 15 分鐘,960x540
UNTIL=fold ./run_release.sh fast K1   # 只跑四折(約 1 分鐘)—— 本交付版的冒煙測試就是這條(§9)
UNTIL=box  ./run_release.sh fast K2   # 四折 + 膠帶 + 入箱 + 關蓋
```

輸出在 `runs/<mode>_<NAME>/1/`:`wrap.mp4`、`wrap_vol.log`(每 0.5 s 一列 + SUMMARY)、`wrap.npz`(各快照的布 / 杯 / 四面體 / 層索引)、
`grasp.json`、`v2.json`、`key_*.png`、`stdout.txt`。整鏈跑完會在 `runs/<mode>_<NAME>/TABLE.md` 寫 §4 的兩張表(`v2/table.py`)和
整包剛體轉動 vs 杯自轉(`v2/rigid.py`);final 另外剪 `short.mp4`(`v2/cut_short2.sh`)。

**一次只跑一個模擬。** `run_release.sh` 經過 `run3.sh` 開跑:啟動鎖(一次只開一個)、等 GPU 顯存 < `GPU_MAX`(29500 MiB)、
偵測「布沒在模擬」就殺掉重開(GPU 快滿時 PhysX 會**靜默失敗**,§10 #6)。要跟別的 `run3.sh` 共用同一把鎖時設 `LOCK=/path/.run3_launch.lock`。

在 Isaac Sim UI 看場景檔:和 v1 相同(`scene/`,File → Open;不要把 `wrap_vol.py` 貼進 Script Editor —— 它會自己建 `SimulationApp`)。
`wrap_vol.py` 是 headless,看 `wrap.mp4` 和 `key_*.png`。

---

## 2. 模擬在做什麼

### 2.1 包材(和 v1 相同)
4 mm 厚四面體 **volume deformable** 板,500 × 500 mm,35 × 35 網格(2592 點、6125 tets),自碰撞開,
`--young 2e3 --poisson 0.45 --areal 0.1 --fric 0.8`,接觸 / 靜止偏移 2 / 0.5 mm(FINAL_PLAN §1~§2)。
紙箱 = v1 / surface 交付版那個(270 × 230 × 131 mm,內腔 264 × 224),位元組相同,所有剛體 kinematic。

### 2.2 流程(模擬時間 s;fast 和 final 時間表相同 —— V2_FLOW「時序」+「整鏈驗證(v2.1)」)
| t (s) | 段 |
|---|---|
| 0.5 – 14.5 | 四折:xp @0.5、xn @4.0、yp @7.5、yn @11.0(每折 3 s、停 0.5 s);yn 在最外層 |
| 14.5 – 17.5 | 收耳(側板把四角收到內腔 − 3 mm) |
| 17.5 – 26.5 | 入箱;18.5 – 22.5 關下蓋、22.5 – 26.5 關上蓋 |
| 26.9 | **膠帶**:折疊錨點**不移除、當膠帶**(26 個錨、88 頂點);之後每一步錨點的 kinematic 目標 = 杯子姿態 × 這一刻錨點相對杯子的位姿(`--tape_follow 1`)。杯子轉 dynamic |
| 28.9 – 34.9 | 搬箱 +y 200、+z 100 mm |
| 36.9 – 45.9 | 開上蓋、再開下蓋、停 3 s |
| 45.9 – 59.6 | **手 2 取出整包**:下降、合指、抬起(實際 169 ~ 171 mm)、往 −y 平移 400 mm 到桌面、放下。56.2 杯子轉回 dynamic,膠帶錨點**停在當下位置不再跟杯** |
| 60.6 – 91.3 | **手 1 掀 yn**:寬指 150 mm,下指從自由邊下面滑進去、上指合;**夾好那一刻才拆 yn 的膠帶**;抬 40 mm、繞桌面上的鉸點翻 180°(8 s)、停 2 s、放手(張開 2 mm 後沿片的方向抽出,`--v2_xrel_slide 2`)、觀察 10 s |
| 91.3 – 122.0 | 手 1 同樣掀 yp |
| 122.0 – 183.4 | x 片:手 2 扶住杯;手 1 換成第二組 **300 mm** 寬指(`--wide_mm_x 300`),依序掀 xn、xp,做法和 y 片相同(先夾、夾好才拆該片膠帶 —— `--v2_xmode tapegrip`)。x 片夾好的那一刻,**手 2 張開、抬 60 mm**(杯轉 dynamic),免得指頭把片角夾在指與杯之間(`--v2_h2_free 1`);下一段開始前 2.3 s 回來重夾,夾位選「張開 → 合的掃掠盒離布 > 2 mm」的(20 個候選) |
| 184.4 – 195.3 | 手 2 抬杯 150 mm、往 +x 移 380 mm、放到桌面、張開 |

### 2.3 兩隻手、不綁定
- **手 1**(橘)負責掀四片。指頭是 kinematic **碰撞體**(`--jaw_collide 1`),yn / yp 用 150 × 40 × 6 mm、xn / xp 用 300 × 40 × 6 mm,
  摩擦 2.0,合指間距 = 板厚 − 1 mm(壓 1 mm)。**純摩擦夾持**(`--grasp_attach 0 --pick_mode wide`;PGRASP.md:指間 17 ~ 55 個頂點,整段掀開沒有掉)。
- **手 2**(紫)負責取出整包、x 片時扶杯、最後取杯(`--extract_mode lift --extract_out_mm 380`)。夾杯用碰撞體指頭,夾好後杯子 kinematic 跟手(同 v1)。
  **整包取出不是摩擦夾** —— 見 §10 #2。
- 全程不再用綁定:v1 把合指範圍內的頂點綁到指上,v2 沒有。
- 膠帶 = 留在原處的折疊錨點。拆某片的膠帶 = 移除那一片的錨點。

---

## 3. 為什麼搬到桌面上掀,不在箱內掀

**幾何。** 在箱內,片的鉸點(折線 |y| = 71.5 mm)在箱底,離內壁約 40 mm(內腔半寬 112 mm),箱壁高約 131 mm。
片從鉸點量起約 157 mm 長(材料長 L,TABLE_UNWRAP)—— 大部分長度光是爬上箱壁就用掉了,片的質心過不了牆:
越壁到位時 yn 片質心在 y = −73 ~ −90 mm(綁定夾,MATSWEEP)、−89 ~ −102 mm(寬指純摩擦,PGRASP),都沒過箱壁外緣 −113.5 mm。
多拉 60 mm 也沒用(質心 −73 / −84 MATSWEEP、−100.1 PGRASP):材料被拉長(邊長比 1.57 ~ 3.5)而不是整片翻過去。
放手瞬間只有 1 ~ 17% 的片在壁外,10 s 後 0% —— 片倒回箱內。**放在桌面上**,鉸點貼著桌面,片可以整片平躺:
放手後 10 s 翻片角 0 ~ 4°、越線 100%、片質心在鉸線外 81 ~ 85 mm、離桌面 1 ~ 2 mm(TABLE_UNWRAP:綁定 3/3、寬指純摩擦 3/3、第二片 yp 1/1)。

**為什麼調材料係數不是出路(MATSWEEP)。** E 0.5 / 1 / 2 × 10³ Pa × 面密度 0.1 / 0.2 / 0.3 kg/m² 共 9 組,加上越壁 60 mm 2 組:
**11 組放手後 10 s 壁外都是 0%**;越線最高的是 E 2e3、0.3 的 25%,但它開蓋後杯頂覆蓋掉到 68%。
材料越軟越容易被拉長、夾到的頂點越少(掀完越線 79% → 23 ~ 48%);越重包裝越鬆(開蓋後覆蓋 90 → 68%、78 → 51%);
E 5e2 加面密度 ≥ 0.2 連包裝都壞了(四折 bbox 416 × 282 / 466 × 333 mm,正常是 245 ~ 255 × 240 ~ 256)。建議維持 E 2e3、0.1。

**為什麼塑性不是出路(PLASTIC §6、CREASE)。** PhysX 107.3 沒有塑性 deformable。把折好的形狀寫進 rest shape 再重建 body,回彈確實消掉
(探針 43.6° → 0.5°),但 rest 形狀裡層距小於約 2 × contact offset 的點對會**不再互撞**(自穿 20 → 171 ~ 252)。
rest 層間撐開 8 mm 可以保住自碰撞(fast 3 次:開蓋後覆蓋 97 ~ 98%,自穿最大 28 ~ 31,對照 27 ~ 30),但 **final 整鏈**裡烘焙過的布掀不開:
yn 守衛觸發(邊長比 3.97 > 2.6,越線 1%),取杯時布被帶起 62%(對照 22 ~ 35%),體積比 0.98 → 0.91。
而且在桌面上,烘焙過的布放手後會翻回去(0.5 / 2 / 10 s:46° / 81° / 138°,TABLE_UNWRAP 塑性對照,只跑 1 次且夾得很差,當定性結果)—— 折痕記憶反而**妨礙**攤開。
surface 包材的 `restBendAngles` PhysX 107.3 完全不讀;rest shape 重建在那邊可行,但對 bend 4 的材料沒有實際效果(CREASE)。

---

## 4. 結果(final 整鏈 2 次)

判準(V2_FLOW):搬箱時膠帶點相對杯子位移 < 3 mm;取出:杯頂覆蓋 ≥ 90% 且包裹形狀變化(剛體對齊後)中位數 < 15 mm;
每片放手後 10 s:翻片角 < 45°(0° = 平躺往外、90° = 直立、≥ 180° = 蓋回杯上)且越線 ≥ 80%;
取杯前杯頂覆蓋 ≤ 10%;取杯 OK(抬起後杯移動 > 150 mm、離開內腔、布穿杯 0);布被帶起(抬起時最大 / 最終)< 15%。
`V21T/1`、`V21T/2` = `run_release.sh final` 的旗標,兩次同時跑(`docs/V2_FLOW.md`「整鏈驗證(v2.1)」;原表 `sim/v2/TABLE_V21T.md`)。

**表 1:各段**

| run | 超出內腔 關蓋 / 搬前 / 搬後 / 開蓋(頂點) | 膠帶點相對杯 搬後 中位 / 最大 mm | 搬運中 邊長比 max | 取出 抬 mm / 取出後覆蓋 | 取出後 形狀變化 中位 / p90 mm | 取出 | 取杯前 杯頂覆蓋 | 取杯(抬起後) | 布被帶起 最大 / 最終 | 全程 自穿 / 穿杯 max | 達標 | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V21T/1 | 0 / 3 / 4 / 5 | 0.01 / 0.36 | 1.82 | 171 / 99% | 4.5 / 9.4 | ✓ | 1% | OK | 0.3% / 0.0% | 33 / 17 | ✗(xn +10 s 87°) | 1921 |
| **V21T/2** | 0 / 4 / 3 / 3 | 0.02 / 0.39 | 1.87 | 170 / 99% | 6.2 / 11.5 | ✓ | 1% | OK | 2.8% / 5.4% | 14 / 6 | **✓** | 1911 |

**表 2:每一片**

| run | 片 | 夾好 指間頂點 | 放手前 翻片角 / 越線 | +2 s 翻片角 | +10 s 翻片角 / 越線 | 他片 >10 mm(10 s) | 達標 |
|---|---|---|---|---|---|---|---|
| V21T/1 | yn | 41 | 1° / 100% | 4° | 6° / 100% | 44.8% | ✓ |
| V21T/1 | yp | 27 | 1° / 100% | 0° | 0° / 100% | 32.8% | ✓ |
| V21T/1 | xn | 37 | 0° / 99% | 63° | **87°** / 94% | 20.7% | ✗ |
| V21T/1 | xp | 33 | 1° / 98% | 33° | 41° / 96% | 23.6% | ✓ |
| V21T/2 | yn | 31 | 1° / 100% | 0° | 0° / 100% | 22.7% | ✓ |
| V21T/2 | yp | 41 | 1° / 96% | 112° | 20° / 96% | 45.5% | ✓ |
| V21T/2 | xn | 34 | 1° / 99% | 22° | 9° / 100% | 24.3% | ✓ |
| V21T/2 | xp | 35 | 1° / 100% | 4° | 8° / 100% | 17.8% | ✓ |

**整鏈 2 次裡 1 次全部過關(V21T/2,就是 `VOL_v2_full.mp4` 那次)**;V21T/1 只有 xn 沒過(87°:放手後 0.5 s 還是 −0.2°,1.5 s 內翹到 63°,
那段期間手 1 的指離布 38 ~ 67 mm —— 是 §10 #1 的角折回)。手 2 鬆手期間杯被拖 2 ~ 3 mm;夾 y 片時杯被推 15 ~ 22 mm(桌面上沒有箱壁擋)。

膠帶與取出的數字來自更早的 v2.0 正式 5 次(V2_FLOW「結論」,fast 3 + final 2,x 片是舊做法):**膠帶 5/5**(搬後膠帶點相對杯 中位 0.01 ~ 0.16 mm、
最大 0.09 ~ 1.63 mm;對照組錨點固定不動:離杯 173 / 209 mm、邊長比 7.1、自穿 297、360 點超出內腔);**整包取出 5/5**(覆蓋 99 ~ 100%、
形狀變化中位 3.4 ~ 11.7 mm、穿杯 0);**桌面掀 yn / yp 10/10**(+10 s 翻片角 −2° ~ 3°、越線 100%)。
GPU deformable 不可重現:同旗標結果不同,要看多次。

---

## 5. 旗標:正式、fast、存檔續跑、run3.sh

### 5.1 正式(v2.1)—— `sim/run_release.sh final`
= `v2/run.sh` 的基礎旗標(run3.sh `@demo` + 桌面掀法 + 寬指純摩擦 + v2 流程)+ v2.1 那一行(V2_FLOW「整鏈驗證(v2.1)」、FINAL_PLAN §2):
```
@demo     --sheet_mm 500 --grasp 1 ... --hand1_jaw 1 --extract_grip jaw --edamp 0.02        (run3.sh,FINAL_PLAN §2 夾爪版)
v2 基礎   --hand2 off --hand2_keep 0 --hold_yp 0 --second 1 --guard_yn 3.5 --guard_n 2 --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --release_watch 1 --grasp_tail_s 1
寬指      --grasp_attach 0 --pick_mode wide --wide_squeeze_mm 1.0 --wide_depth_mm 40 --pick_in_mm 45 --ffric 2.0 --chord 1 --clear_mm 2 --pick_mm 0
流程      --tape_follow 1 --takeout 1 --v2_xflaps 1 --v2_hold_cup 1 --extract 1 --extract_mode lift --extract_out_mm 380
v2.1      --quality final --edamp 0.02 --ut_release_up 1 --v2_xmode tapegrip --v2_h2_free 1 --wide_mm 150 --wide_mm_x 300 --v2_xrel_slide 2
```
後面的旗標覆蓋前面的(argparse 取最後一次);`run_release.sh` 後面多給的參數接在最後。開發目錄裡的同一條:
`vol/v2/run.sh V21T --quality final --edamp 0.02 --ut_release_up 1 --v2_xmode tapegrip --v2_h2_free 1 --wide_mm 150 --wide_mm_x 300 --v2_xrel_slide 2`(= 這裡的 `sim/v2/run.sh`)。

### 5.2 開發 —— `sim/run_release.sh fast`
`--quality fast --edamp 0`(dt 1/120、solver 48、每 2 幀渲染、960 × 540)。**拿來確認流程跑得完、時間點、夾到幾個點;不要拿來判斷 x 片和包裹完整度**:
fast 下杯子在軟包裹裡會自轉 —— 箱內多轉 17 ~ 22°,放到桌面又滾 12 ~ 20°(final 5 ~ 9°,V2_FLOW `rigid.py` 表);
拆了膠帶的 x 片 fast 會自己彈開(6 片裡 5 片越線 ≥ 60%),final 不會(0 ~ 41%),所以 fast 分不出 x 片做法的好壞(V2_FLOW「x 片」)。
v2.1 旗標的整鏈只跑過 final(V21T 2 次);fast 跑的是 v2.0 旗標(B 3 次:wall 861 ~ 890 s,兩個同時跑)。

### 5.3 存檔續跑(`--save_state` / `--at` / `--load_state`,SPEEDUP.md、V2_FLOW「存檔續跑」)
```bash
cd sim
./run_release.sh final S1 --save_state ../runs/final_S1/S.npz --at xflaps --save_exit 1   # 跑到 t = 122.0(yn、yp 掀完)存檔就停:final 約 1077 s、fast 約 494 s
LOADCHK=0 ./run_release.sh final R1 --load_state ../runs/final_S1/S.npz                    # 續跑 x 片 + 取杯(73 s 物理):final 720 ~ 1000 s、fast 330 ~ 480 s
LOADCHK=0 ./run_release.sh final R2 --load_state ../runs/final_S1/S.npz --v2_xmode sweep   # x 片 / 取杯段的旗標可以改;折 / 入箱 / 搬的時間表不能改(assert)
```
`--at xflaps` 另外存膠帶錨點姿態、指的停點、桌面碰撞狀態、y 片的規劃。續跑第 1 幀和存檔差最多 0.83 mm。
要 `LOADCHK=0`:存檔點布是靜止的,`run3.sh` 否則會把「前 3 筆量測一樣」當成凍住。
其他存檔點(`--at grasp|opened|秒數`)是給 v1 的箱內流程用的(SPEEDUP.md)。

### 5.4 `run3.sh` —— 多次執行與 GPU 門檻
```bash
cd sim
N=2 v2/run.sh F --quality final --edamp 0.02 --ut_release_up 1 --v2_xmode tapegrip --v2_h2_free 1 --wide_mm 150 --wide_mm_x 300 --v2_xrel_slide 2   # final 2 次 → v2/F/{1,2}
python3 v2/table.py v2/F;  python3 v2/rigid.py v2/F
N=1 v2/runx.sh S_final --quality final --edamp 0.02 --ut_release_up 1 --save_state 'v2/x/S_final/S{k}.npz' --at xflaps --save_exit 1   # x 片實驗(V2_FLOW)
N=1 table/run.sh W wide                     # 不入箱:四折、膠帶、在桌面掀 yn(TABLE_UNWRAP)
```
`./run3.sh NAME [旗標]` 開 N 次(預設 3,同時最多 `MAXPAR`),`{k}` 換成第幾次、`@demo` 換成 FINAL_PLAN §2 夾爪版旗標。
環境變數:`N`、`KS`、`MAXPAR`、`GPU_MAX`(29500)、`HEAD`、`TRIES`、`STARTUP_S`、`LOCK`(預設 `sim/.run3_launch.lock`)、`ISAAC`、`TABLE`(出表指令,空 = 不出)、`LOADCHK`。
實測(SPEEDUP §3):GPU 快滿時會出現 `PxCudaContextManager out-of-memory`、`Scene state is corrupted`,或**不報錯、也不模擬布**(邊長比一直 [1.000, 1.000]),
程式照樣 EXIT 0;run3 會殺掉這次、等顯存 < GPU_MAX − HEAD 再重開(最多 6 次)。兩個同時開會一起 OOM,所以有啟動鎖。

---

## 6. 影片

在 git 裡(103 MB)。`./make_videos.sh [選項]` 重產(§8)。

| 影片 | 長度 | 內容 | 來源 | 重產 |
|---|---|---|---|---|
| `VOL_v2_full.mp4` | 195.3 s,1280×720 | ★ v2.1 整鏈:四折、膠帶、入箱、搬、開蓋、整包取出到桌面、掀 yn / yp(寬指 150)、換寬指 300 掀 xn / xp(手 2 鬆手再重夾)、取走杯子 | V21T/2(全部過關) | `./make_videos.sh` |
| `DEMO_v2_short.mp4` | 23.8 s | 上面的短版:關蓋 ×8、搬 ×6、開蓋 ×6、取出 ×4、yn ×6、yp ×6、xn ×8、xp ×8、重夾 + 取杯 ×4 | V21T/2(`v2/cut_short2.sh`) | `./make_videos.sh` |
| `VOL_v2x2_compare.mp4` | 17.3 s,6 格 | x 片 + 取杯段(t 124 ~ 193 s,×4),同一個 final 存檔續跑:D(手 2 一直扶)、E(手 2 鬆手)、F(+300 mm)、G(+壓根部)、H(+抽指放手)、GH | V2_FLOW「x 片 第二輪」 | `./make_videos.sh --x2` |
| `DEMO_unwrap_table_short.mp4` | 14.8 s | 不入箱:四折、膠帶、寬指滑到 yn 下、翻 180°、放手後片平躺不動 | TABLE_UNWRAP W/2 | `./make_videos.sh --table` |
| `VOL_unwrap_table_yp.mp4` | 99.8 s | 不入箱:yn、yp 依序在桌面攤開(綁定版),兩片都留住 | TABLE_UNWRAP Y/1 | `./make_videos.sh --table` |
| `VOL_pgrasp.mp4` | 86.6 s | 箱內:寬指純摩擦把 yn 一路拿過箱壁,放手 → 倒回箱內(§3 的證據) | PGRASP C150 | `./make_videos.sh --pgrasp` |
| `DEMO_pgrasp_short.mp4` | 11.2 s | 上面的短版 | PGRASP C150(`pgrasp/cut_short.sh`) | `./make_videos.sh --pgrasp` |
| `VARIANTS_grid.mp4` | 6 s | 22 種折序並排(折法多樣性,v1) | `fold_variants.py --video` | `./make_videos.sh --variants` |
| `DEMO_ALL.mp4` + `DEMO_1` ~ `DEMO_6` | 291 s | v1 的剪輯:surface 流程、volume 流程、夾持探針、雙臂、掀包材、雙手掀開撐住取杯(`DEMO_INDEX.md`) | v1 | `./make_videos.sh --montage DEV` |

---

## 7. 檔案

```
README.md、CHANGELOG.md      本文件;v1 → v2 改了什麼
make_videos.sh               重產 videos/(§6)
videos/                      成果影片(進 git)+ DEMO_INDEX.md(v1 剪輯索引)
sim/                         模擬 —— 一律在 sim/ 裡面執行
  run_release.sh               ★ 一條指令:final | fast(v2.1 旗標)、UNTIL=fold|box|move、多給旗標做存檔續跑
  wrap_vol.py                  模擬本體(Isaac Sim 5.1 volume deformable,整鏈);預設 --carton carton.usd
  volcommon.py、vol_pen.py、layer_order.py、layer_gap.py、grasp_plan.py、grip_common.py、grip/gutil.py   wrap_vol.py 會 import
  run3.sh                      N 次 + 啟動鎖 + GPU 門檻 + 凍住重開(開發版 run3.sh + run3x.sh 合併)
  table3.py                    run3.sh 預設的逐項表(v1 流程的欄位)
  v2/run.sh                    v2 流程基礎旗標 → run3.sh(輸出 v2/NAME/k)
  v2/runx.sh                   同一組旗標,輸出 v2/x/NAME/k(x 片實驗、存檔續跑)
  v2/table.py、v2/rigid.py     v2 兩張表;整包剛體轉動 vs 杯自轉
  v2/tablex.py、v2/tablex2.py  x 片第一輪 / 第二輪的表
  v2/cut_short2.sh             v2.1 短版(24 s);v2/cut_short.sh = v2.0 短版;v2/cut_x.sh = x 片並排影片
  v2/TABLE*.md                 開發時的原始表(V21T = §4)
  table/run.sh、table.py、cut_short.sh、TABLE.md   不入箱、直接在桌面掀(TABLE_UNWRAP)
  pgrasp/cut_short.sh          VOL_pgrasp 的短版剪法
  cloth_iface.py、jitter.py、fold_variants.py、rest/make_rest.py、grip/grasp_points.py、grip_attach/   同 v1
  make_demo_videos.sh          v1 剪輯(make_videos.sh --montage)
  find_isaac.sh                找 Isaac Sim
  carton.usd、carton.meta.json、mug.stl、bubble_normal.png   紙箱(= v1)、杯子、泡泡紋理
scene/                       = v1:雙臂工作站 USD、scene_final.usd、arm/(INTERFACE.md、掀開軌跡、URDF)
docs/
  V2_FLOW.md                   ★ v2 流程、旗標、所有 v2 實驗、x 片第一 / 二輪、v2.1 整鏈驗證、已知限制
  TABLE_UNWRAP.md              桌面掀:片攤平留住(3/3 + 3/3 + 1/1);需要膠帶;塑性對照會翻回
  PGRASP.md                    寬指純摩擦:夾得住,但片翻不過箱壁
  MATSWEEP.md                  材料係數掃描:沒有任何 E / 面密度能讓放手的片留在壁外
  PLASTIC.md                   runtime 烘焙 rest shape(塑性):有效但自碰撞失效;§6 撐開 rest
  CREASE.md                    surface 包材折痕記憶探針(PhysX 107.3 不讀 restBendAngles)
  SPEEDUP.md                   存檔續跑、抓點規劃加速、run3.sh
  FINAL_PLAN.md                為什麼用 volume、正式旗標(§2 含 v2.1)
  RELEASE.md                   三週方法與結論總表(v1 時期)
  smoke_check/                 本資料夾的冒煙測試(§9):stdout.txt、run3.log、key_fold_done.png
```

---

## 8. 腳本:哪支在哪裡跑

| 腳本 | 做什麼 | 怎麼跑 |
|---|---|---|
| `sim/run_release.sh` | 正式執行 | 終端機,`cd sim`(§1) |
| `sim/wrap_vol.py` | 模擬本體 | 終端機:`/isaac-sim/python.sh wrap_vol.py <旗標> --out DIR`(不要貼進 Script Editor) |
| `sim/run3.sh`、`v2/run.sh`、`v2/runx.sh`、`table/run.sh` | 批次 + GPU 門檻 | 終端機,在 `sim/` 下 |
| `sim/v2/table.py`、`rigid.py`、`tablex*.py`、`table/table.py`、`table3.py` | 出表 | 系統 `python3`(numpy、scipy) |
| `sim/v2/cut_*.sh`、`table/cut_short.sh`、`pgrasp/cut_short.sh` | 剪短版 | ffmpeg |
| `make_videos.sh` | 重產影片 | 終端機,在本資料夾 |
| `sim/fold_variants.py` | 折法多樣性(v1) | `python3 fold_variants.py ...` |

---

## 9. 版本與測試環境

| | |
|---|---|
| 版本 | volume_release_v2_20261022。程式 = repo commit `6fcd916` 的 `sims/fr3_bubblewrap_pack_20261007/vol/`(當時和開發目錄相同)+ CHANGELOG 列出的 `[release]` 修改 |
| Isaac Sim | 5.1.0-rc.19(Kit 107.3、PhysX 107.3.26),binary 安裝在 `/isaac-sim`(pip 安裝也找得到,`find_isaac.sh`) |
| GPU | RTX 5090 32 GB,driver 580.173.02。一次模擬約 5~6 GB × 2 個 context |
| Python 相依 | Isaac 的 python:numpy、scipy、trimesh、imageio、PIL(內附);出表:系統 python3 + numpy / scipy;ffmpeg / ffprobe |
| 實測時間 | final 整鏈 1911 ~ 1921 s(兩個同時跑);fast v2.0 整鏈 861 ~ 890 s(兩個同時跑);`--until fold` 50 s |
| **本資料夾冒煙測試**(2026-10-21) | 在本資料夾的 `sim/` 跑 `UNTIL=fold ./run_release.sh fast SMOKE`:EXIT 0、沒有 Traceback;18.1 s 模擬,迴圈 36 s / 總共 50 s;讀到 carton.usd(5 個 kinematic 剛體、內腔 ±132 × ±112);四折 bbox 254 × 239 × 124 mm;入箱前超出內腔 0 / 0(布 / 杯);自穿最大 31(fast,QUALITY.md:fast 30~32)、穿杯 0、反轉 0。log:`docs/smoke_check/` |

---

## 10. 已知限制

| # | 限制 | 數字 | 說明 |
|---|---|---|---|
| 1 | **x 片的角折回** | 整鏈:V21T/1 xn +10 s 87°(V21T/2 沒事)→ 整鏈 **2 次只有 1 次**全過。續跑的 H 做法:xp 48 ~ 60° | yp 根部附近有一個折起來的角(flat x 179 ~ 221、y 136 ~ 221 mm,夾之前就已經折回 z 26 ~ 31),放手後把自由邊的半邊往上、往回拉。還沒修:另外夾這個角往外拉(多 15 ~ 20 s 時間槽),或翻 yp 時順便把 x 片的角帶出來(V2_FLOW「已知限制」) |
| 2 | **整包取出不是摩擦夾** | — | 杯子 kinematic 跟著手 2 走,膠帶跟著杯子;這一段手 2 的指只是視覺。摩擦夾在這裡做不到:包裹約 260 × 223 mm 塞在 264 × 224 mm 的內腔裡,兩側只有約 3 mm 給手指 |
| 3 | 入箱後 2 ~ 6 個邊界頂點貼著箱壁 | V21T 搬前 / 搬後 / 開蓋 3~4 / 3~4 / 3~5;都超出內腔 < 2.5 mm(在接觸厚度以內) | x / y 有 ≥ 1 點超出時 verdict 會標 FAIL;v1 extract6/X2 也是 1 ~ 2 點 |
| 4 | fast 精度下杯子在包裹裡自轉 | fast:箱內多轉 17 ~ 22°、桌面上再滾 12 ~ 20°;final 5 ~ 9° | 看包裹完整度用 final 的數字或「形狀變化」欄(§5.2) |
| 5 | x 片 fast 和 final 不一樣 | 拆膠帶後:fast 6 片有 5 片自己攤開,final 0 ~ 41% | x 片做法只能在 final 判斷 |
| 6 | **GPU 快滿時 PhysX 靜默失敗** | 不報錯、布不模擬、EXIT 0(SPEEDUP §3) | 一律經 `run_release.sh` / `run3.sh` 跑(監看 + 重開);一次一個 |
| 7 | 夾 y 片時杯被推 | 15 ~ 22 mm(V21T);x 片 2 ~ 7 mm | 桌面上沒有箱壁擋;y 片段杯子是 dynamic |
| 8 | 掀開時他片被帶動 > 10 mm | 17.8 ~ 45.5%(V21T) | 大多是 yn 那一側 xp / xn 的耳角(TABLE_UNWRAP) |
| 9 | 下指滑到布下時穿杯 | 全程最大 17 / 6(V21T);v2.0 夾 yp 時 5 ~ 10 點、抬起後 0 ~ 5;final 有 40 ~ 60 個四面體短暫反轉、之後恢復 | 抬杯之後:0 |
| 10 | 不可重現 | 同旗標:上面的 V21T/1 vs /2 | 至少看 2~3 次 |
| 11 | 取出抬了 169 ~ 171 mm,不是 150 | 抬高 = max(`--tk_lift_mm`, 包裹底高過箱口 40 mm) | 只抬 150 mm 時離打開的蓋子只剩約 19 mm |
| 12 | `--takeout 1` 要 `--until all` | wrap_vol.py 裡 assert | `run_release.sh` 設了 `UNTIL` 就拿掉取出 / x 片 / 取杯旗標 |
| 13 | 速度 | final 整鏈約 32 分鐘 | 後段用存檔續跑來迭代(§5.3) |
| 14 | volume 包材不在雙臂場景裡 | 同 v1 | 靠座標與快照銜接(`scene/arm/INTERFACE.md`、`cloth_iface.py`) |

<p align="right"><a href="#繁體中文">↑ 回到頂端</a> · <a href="#english">English ↑</a></p>
