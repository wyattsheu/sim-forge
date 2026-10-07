# Bubble-Wrapped Mug in a Carton — Dual-Arm Workstation (Handoff)<br>氣泡布包裹馬克杯入箱 —— 雙臂工作站(交付版)

**Language / 語言:** [English](#english) · [繁體中文](#繁體中文)

---

# English

> **This is the delivered handoff.** Clone it and you can open the scene, press Play, interact with the mouse,
> re-run the simulation, and regenerate every video.
> **New:** in `scene_final_phys.usd` the bubble wrap and the mug have real physics (§2, §8.6).
> The development history (experiments, 122 logged runs, volume-deformable work, tests) lives in
> [`sims/fr3_bubblewrap_pack_20261007`](../fr3_bubblewrap_pack_20261007). You don't need it to use this package.

| | |
|---|---|
| **Version** | handoff_20261007 — scene and simulation from 2026-10-02; added 2026-10-07: UI / WebRTC usage, a Play fix, and a physics version of the package (`scene_final_phys.usd`) |
| **Tested on** | Isaac Sim 5.1.0, RTX 5090, NVIDIA driver 580 |
| **Get it** | git: this folder (videos excluded — run `./make_videos.sh`) · tarball: `handoff_20261007.tgz` (videos included) |

## Contents

1. [Quick start](#1-quick-start)
2. [Which scene file to open](#2-which-scene-file-to-open)
3. [Using the Isaac Sim UI](#3-using-the-isaac-sim-ui)
4. [Remote viewing over WebRTC](#4-remote-viewing-over-webrtc)
5. [Videos](#5-videos)
6. [Files](#6-files)
7. [Scripts: which run where](#7-scripts-which-run-where)
8. [Technical reference](#8-technical-reference)
9. [Known issues](#9-known-issues)

---

## 1. Quick start

```bash
./open_in_ui.sh        # local desktop: open Isaac Sim with scene_final_phys.usd loaded
./open_in_webrtc.sh    # remote: stream it, connect with the WebRTC Streaming Client (§4)
./make_videos.sh       # regenerate the verification videos; add --demo for the 62 s result video
```

Once the viewport is up:

1. Press **▶ Play** (left toolbar).
2. **Alt + left-drag** to orbit the camera.
3. **Shift + left-drag** on the carton or a lid to pull it around.

---

## 2. Which scene file to open

| File | Wrap and mug | Use it for | What happens on Play |
|---|---|---|---|
| **`scene_final_phys.usd`** | **Real physics:** wrap = surface deformable, mug = rigid body | **Default for both launch scripts.** Interaction with the package | Carton 0.12 mm, wrap settles within 3 s (max 13.3 mm, mean 4.3 mm), mug 0.13 mm (§8.6) |
| `scene_final_ui.usd` | Static meshes (no physics) | The most stable interactive scene; carton and lids only | Carton 0.00 mm, lids ≤ 0.75° |
| `scene_final.usd` | Static meshes (no physics) | The canonical deliverable; headless scripts; the elastoplastic crease (§3.4) | ⚠️ Pressed directly in the UI, **the carton sinks 48 mm into the table** |

> ⚠️ **`scene_final_phys.usd` needs deformables enabled when Isaac Sim starts.** The two launch scripts do this for you.
> If you start Isaac Sim any other way, enable it first (§3.1) — otherwise the wrap doesn't simulate.

**Why `scene_final.usd` sinks:** it has no PhysicsScene, so the UI creates a default one
(60 Hz, 1 position iteration, 0 velocity iterations), which is too weak to hold the carton up.
`scene_final_ui.usd` is the same scene with a properly tuned PhysicsScene and spring drives on the four lid creases.
Details and measurements: [§8.2](#82-the-play-fix-in-scene_final_uiusd).

---

## 3. Using the Isaac Sim UI

### 3.1 Open the scene

**From the command line**

```bash
./open_in_ui.sh                    # opens scene_final_ui.usd
./open_in_ui.sh scene_final.usd    # or any other USD
```
`open_in_ui.sh` opens `scene_final_phys.usd` by default and starts Isaac Sim with
`--/persistent/physics/enableDeformableBeta=true --/physics/updateToUsd=true`.

**From the UI**

0. **Once per machine (needed for `scene_final_phys.usd`):** in Isaac Sim, **Edit → Preferences → Physics** →
   tick **Enable Deformable Schema Beta (Requires Restart)** → close and restart Isaac Sim.
   (Or put `--/persistent/physics/enableDeformableBeta=true --/physics/updateToUsd=true` in the App Selector's **Extra Args**.)
1. Start Isaac Sim, either way:
   - run `/isaac-sim/isaac-sim.sh` (as root, `export OMNI_KIT_ALLOW_ROOT=1` first), or
   - run `/isaac-sim/isaac-sim.selector.sh` → choose **Isaac Sim Full** → **START**.
2. Open the file, either way:
   - **File → Open** → pick `scene_final_phys.usd` (or `scene_final_ui.usd`), or
   - in the **Content** panel, paste this folder's path into the address bar and **double-click** the USD.
     (Don't drag the USD into the viewport — that adds it as a reference instead of opening it.)
   - Next time: **File → Open Recent**.
3. Press **▶ Play**.

### 3.2 Camera and selection

| Action | Input |
|---|---|
| Orbit | **Alt + left-drag** |
| Pan | **Middle-drag** |
| Zoom | **Scroll wheel**, or **Alt + right-drag** |
| Look around / fly | **Right-drag** (hold right button + **WASD** to fly) |
| Select / frame selection | **Left-click** / **F** |
| Move / rotate / scale gizmo | **W / E / R** (**Q** returns to select) |

### 3.3 Interacting with physics (while playing)

| Input | Effect |
|---|---|
| **Shift + left-drag** | Grab a rigid body and drag it |
| **Shift + left double-click** | Push it |

Grab strength is under the Physics settings → **Mouse Interaction** (Grab Force Coeff, Push Acceleration).

| Object | Prim | Can you grab it? |
|---|---|---|
| Carton body (floor + 4 walls) | `/World/Packed/Box/base` | ✅ rigid body |
| Four lids | `/World/Packed/Box/{fxp,fxn,fyp,fyn}` | ✅ rigid bodies, hinged to the base by crease joints |
| Bubble wrap | `/World/Packed/Wrap` | `scene_final_phys.usd`: surface deformable — collides with the carton, lids and mug; grabbing the wrap itself is not yet tested · other scenes: ❌ static mesh (lids pass through it) |
| Mug | `/World/Packed/Mug` | `scene_final_phys.usd`: ✅ rigid body (0.32 kg) · other scenes: ❌ static mesh |
| Arms | `/World/stationary_ai` | Drive the joints instead (§3.5) |

In `scene_final_ui.usd` and `scene_final.usd` the wrap and mug are the simulation result baked into fixed geometry.
`scene_final_phys.usd` keeps the same shape but gives them physics (§8.6).

### 3.4 Real elastoplastic creases (lids stay where you bend them)

In `scene_final_ui.usd` the creases are springs: bend a lid open and it springs back to 0°.
To get the real behaviour — bend past the yield moment and the lid stays at its new angle —
open **`scene_final.usd`** and run `sim/crease_hold_ui.py`:

**Point-and-click**

1. **Window → Script Editor**
2. In the Script Editor: **File → Open** (Alt + O) → `sim/crease_hold_ui.py`
3. If this package is **not** at `/isaac-sim/test_scripts/manip_fr3/handoff_20261002/`,
   set line 16, `SIM_DIR_OVERRIDE = ""`, to the full path of your `sim/` folder.
4. Click **Run** (Ctrl + Enter).

**Or paste one line** (finds its own folder; no editing needed)

```python
p = "/your/path/sim/crease_hold_ui.py"; exec(compile(open(p).read(), p, "exec"))
```

Then press Play. The script

- tunes the PhysicsScene (same values as `scene_final_ui.usd`), so the carton doesn't sink, and
- applies `ElastoplasticCrease.step()` to all four lids on every physics step
  (k = 3.2, My0 = 0.60, H = 0.85, c = 0.33, clip = 3.0 — same as `wrap_sim.py`), with +τ on each lid and −τ on the base.

Run `crease_stop()` to detach it. Don't run it on `scene_final_ui.usd` — the spring drives and crease torques would add up.

### 3.5 Moving the arms

Both arms are one articulation (root `/World/stationary_ai/root_joint`). Every joint already has a drive (target 0).
While playing:

| Joint | Prim (under `/World/stationary_ai/joints/`) | Drive |
|---|---|---|
| 6-axis arm | `follower_{left,right}_joint_0` … `_5` | angular; stiffness 664–738 (joints 0–2), 33–62 (joints 3–5) |
| Gripper | `follower_{left,right}_left_carriage_joint` | linear, target in metres (`right_carriage_joint` has no drive) |

- One joint: select it in the Stage panel → **Property → Drive → Target Position** (degrees).
- All joints with sliders: **Window → Physics Inspector**.

---

## 4. Remote viewing over WebRTC

The server streams the full Isaac Sim UI; you watch and control it from another computer with the
**Isaac Sim WebRTC Streaming Client** (desktop app from NVIDIA's Isaac Sim download page).
Everything in §3 works the same in the stream.

### 4.1 From the command line (recommended)

The script opens the scene, sets the camera, enables mouse dragging, and presses Play for you.

```bash
./open_in_webrtc.sh                              # scene_final_ui.usd
./open_in_webrtc.sh scene_final.usd --crease     # original scene + elastoplastic creases (§3.4)
WEBRTC_IP=<public IP> WEBRTC_PORT=49110 ./open_in_webrtc.sh
WEBRTC_NO_PLAY=1 ./open_in_webrtc.sh             # load, but don't press Play
./open_in_webrtc.sh --stop                       # stop the stream
```

- Wait for `[handoff] READY` in `logs/webrtc.log` (about 20 s), then connect.
- **In this mode you don't need Shift** — a plain left-drag grabs the carton or a lid.
- Defaults: IP `140.96.68.42` (this server), signalling port 49100. **On another machine, set `WEBRTC_IP`.**

### 4.2 From the UI

1. On the server desktop, run `/isaac-sim/isaac-sim.selector.sh` (App Selector).
2. Choose **Isaac Sim Full Streaming**.
3. If the public IP isn't the default, put `--/app/livestream/publicEndpointAddress=<public IP>` in **Extra Args**.
4. Click **START**.
   For `scene_final_phys.usd` also add `--/persistent/physics/enableDeformableBeta=true --/physics/updateToUsd=true`.
5. Connect with the Streaming Client, then **File → Open** `scene_final_phys.usd` and press Play
   (here physics dragging needs **Shift + left-drag**).

### 4.3 Connecting

- Streaming Client → enter the server IP → **Connect**.
- Firewall: open **TCP 49100** (signalling) and **UDP 47998** (media).

Tested 2026-10-07: both command-line modes reached READY in about 20 s (591–592 prims loaded, port 49100 listening, physics running),
and `--stop` shut them down cleanly. The client side was not tested — there was no client on the server.

---

## 5. Videos

Videos are **not in git**. One command regenerates all of them into `videos/`:

```bash
./make_videos.sh                  # the first four videos below
./make_videos.sh --demo           # plus the 62 s DEMO (needs GPU)
VIDEO_DIR=/tmp/v ./make_videos.sh # write somewhere else
```

| Video | Shows | Make it alone (run inside `sim/`) |
|---|---|---|
| `scene_physics_crease_on.mp4` | 8 s of physics, lids closed, crease torques on | `python.sh scene_physics_check.py ../scene_final.usd --out phys --secs 8` |
| `scene_physics_crease_off.mp4` | Control: no crease — the lower lids fall into the box | `python.sh scene_physics_check.py ../scene_final.usd --out phys_nc --secs 8 --no_crease` |
| `scene_physics_open_lids.mp4` | Lids opened 170°, 10 s of physics, ends looking down into the box | `python.sh scene_physics_check.py ../scene_final.usd --out phys_open --secs 10 --open_deg 170` |
| `scene_final_orbit.mp4` | 12 s orbit around the scene (render only, no physics) | `python.sh orbit_video.py ../scene_final.usd orbit.mp4` |
| `DEMO_new_order_sheet400.mp4` | Result: wrap first pair of sides → second pair → into the box, lids closed → move the box, open lids (62 s) | `./run_demo.sh` (writes `sim/DEMO.mp4`) |

`python.sh` means `/isaac-sim/python.sh`. Each physics video gets a matching `.log` with per-second numbers.

**How long it takes:** a full `./make_videos.sh --demo` run was measured on 2026-10-07 on a GPU shared with other jobs —
physics videos about 3 min, orbit about 25 min, DEMO about 6 min, **about 32 min in total**. Expect less on an idle GPU.

---

## 6. Files

```
README.md                       this document (English + 繁體中文)
scene_final.usd                 ★ the deliverable: dual-arm workstation + carton + wrapped mug (single file, 14 MB)
scene_final_ui.usd              same scene + tuned PhysicsScene + lid spring drives, for the UI (§2)
scene_final_phys.usd            scene_final_ui.usd + physics on the wrap (deformable) and mug (rigid body) (§8.6)
open_in_ui.sh                   open in the local Isaac Sim UI
open_in_webrtc.sh               open over WebRTC (--stop to stop)
make_videos.sh                  regenerate videos/
videos/                         videos (tarball only; regenerate with make_videos.sh)
sim/                            simulation and tools — flat folder, run scripts from inside it
  wrap_sim.py                     the simulation (Isaac Sim 5.1 surface deformable)
  grip_common.py                  shared parts for wrap_sim.py
  crease_physics.py               elastoplastic crease model (yield + hardening)
  crease_hold_ui.py               for the UI Script Editor: crease torques + PhysicsScene fix (§3.4)
  webrtc_boot.py                  boot script for open_in_webrtc.sh (kit --exec)
  scene_physics_check.py          physics check + video, through isaacsim.core World
  ui_path_check.py                physics check through the same Play path the UI uses (§8.2)
  build_phys_scene.py             build scene_final_phys.usd from scene_final_ui.usd (§8.6)
  verify_phys_scene.py            tests A / B / Bm / C for scene_final_phys.usd (§8.6)
  orbit_video.py                  orbit video (render only)
  run_demo.sh                     run the four simulation stages and stitch DEMO.mp4
  make_carton_P.py, make_definitive.sh   carton generator
  carton.usd, carton.meta.json    carton asset (270 × 230 × 134 mm, 4 lids) and its geometry parameters
  mug.stl, bubble_normal.png, floor_edges.json
states/                         cloth + mug vertices at the end of each stage (c1, c2, box, mb_open); resume from any of them
build/
  build_full_scene.py             rebuild scene_final.usd (§8.5)
  stationary_ai_carton_scene_flat.usd   the original dual-arm scene (14 MB)
```

---

## 7. Scripts: which run where

> **Never paste a script that creates its own `SimulationApp` into the Script Editor.**
> That starts a second Kit inside the running one and hangs or crashes it. Run those from a terminal with `/isaac-sim/python.sh`.

| Script | What it is | How to run it |
|---|---|---|
| `sim/crease_hold_ui.py` | Crease torques + PhysicsScene fix | ✅ **The only one you run inside the UI** (§3.4) |
| `sim/webrtc_boot.py` | WebRTC boot script | Started by `open_in_webrtc.sh` via `kit --exec` |
| `sim/crease_physics.py` | Crease model (library) | Imported by the other scripts |
| `sim/grip_common.py` | Shared simulation parts (library) | Imported by `wrap_sim.py` |
| `sim/wrap_sim.py` | Wrap → box → move simulation | Terminal: `sim/run_demo.sh` or `./make_videos.sh --demo` |
| `sim/scene_physics_check.py` | Physics check + video | Terminal (§5, §8.3) |
| `sim/ui_path_check.py` | UI-path Play check | Terminal (§8.2) |
| `sim/build_phys_scene.py` | Build `scene_final_phys.usd` | Terminal (§8.6) |
| `sim/verify_phys_scene.py` | Physics-package tests | Terminal (§8.6) |
| `sim/orbit_video.py` | Orbit video | Terminal (§5) |
| `sim/make_carton_P.py` | Carton generator | Terminal, called by `make_definitive.sh` |
| `build/build_full_scene.py` | Rebuild the scene | Terminal (§8.5) |

```
wrap_sim.py ──► grip_common.py
            └─► crease_physics.py ◄── scene_physics_check.py
                                  ◄── crease_hold_ui.py ◄── ui_path_check.py --crease_script
                                                        ◄── webrtc_boot.py (open_in_webrtc.sh --crease)
```

Everything sits in `sim/`; no PYTHONPATH setup is needed.

---

## 8. Technical reference

### 8.1 Scene layout (`scene_final.usd`)

| Item | Value |
|---|---|
| Arm scene | `build/stationary_ai_carton_scene_flat.usd`; arms and table **unchanged** |
| Original `/World/Carton` | Removed; replaced by `/World/Packed` (Box + Wrap + Mug) |
| Placement | Aligned with the original carton: centre (x, y) = (−20, 0) mm, carton floor z = 20 mm (= table top) |
| Orientation | Rotated 90° about z; the 270 mm side runs along y (between the arms) |
| Carton bounding box (world) | x −135…95, y −135…135, z 20…154 mm |
| Clearance to grippers | 68.7 mm in y for all four gripper fingers |
| Wrap and mug | From the end of simulation stage 3 (`states/box.npz`); every vertex checked inside the carton cavity |
| Lids | All four closed (USD default angle = end of simulation) |
| External dependencies | Carton flattened into the file; only the two NVIDIA cloud MDL materials the arm scene already used |
| Units / axes | Z-up, metersPerUnit = 1 |

The crease joints are passive (±185°, no drive). The elastoplastic crease (`crease_physics.py`) is a torque applied every physics step
at run time, so it cannot live in USD. In your own code, apply `ElastoplasticCrease.step()` to
`/World/Packed/Box/crease_{fxp,fxn,fyp,fyn}` every step — see `scene_physics_check.py` for the shortest example.

### 8.2 The Play fix in `scene_final_ui.usd`

| Change | Value |
|---|---|
| `/physicsScene` | 120 Hz, TGS, min position iterations 8, min velocity iterations 1, GPU aggregate pairs 8192 |
| `/World/Packed/Box/crease_{fxp,fxn,fyp,fyn}` | angular drive: stiffness 0.056 N·m/deg, damping 0.006 N·m·s/deg, max force 3.0, target 0 |

The drive values are the elastic part of the crease model (k = 3.2 N·m/rad, c = 0.33 N·m·s/rad), converted to the per-degree units USD angular drives use.

Measured with `sim/ui_path_check.py` (opens the file and presses Play exactly like the UI does; 8 s; 2026-10-07):

| Route | Max carton z drift | Max lid angle | |
|---|---|---|---|
| A. `scene_final_ui.usd`, Play | **0.00 mm** | 0.75° | ✅ |
| B. `scene_final.usd` + `crease_hold_ui.py` | **0.00 mm** | 0.08° | ✅ |
| Control: `scene_final.usd`, Play | **48.12 mm** | 2.60° | ❌ carton sinks into the table |

```bash
cd sim
/isaac-sim/python.sh ui_path_check.py ../scene_final_ui.usd                 # A
/isaac-sim/python.sh ui_path_check.py ../scene_final.usd --crease_script    # B
/isaac-sim/python.sh ui_path_check.py ../scene_final.usd                    # control
```

The headless `scene_physics_check.py` never showed the sinking because `isaacsim.core.World` applies better solver defaults.

### 8.3 Physics check through `World` (`scene_physics_check.py`)

Re-run on 2026-10-07 with `make_videos.sh`; identical to the 2026-10-02 numbers.

| Check | Lids closed + crease | Lids opened 170° + crease | Lids closed, no crease (control) |
|---|---|---|---|
| Carton displacement | 0.00 mm | 0.00 mm | 0.00 mm |
| Carton floor − table top | 0.00 mm | 0.00 mm | 0.00 mm |
| Lower lids fxp / fxn, max angle | 0.3° / 0.3° | 0.3° / 0.3° | **91.7° / 91.7° (fall into the box)** |
| Upper lids fyp / fyn, max angle | 0.3° / 0.3° | 0.3° / 0.3° | 4.1° / 4.1° |
| Arm joint drift, max | 0.07° | 0.07° | 0.07° |

Angle = rotation about the hinge relative to the starting pose (0.3° is gravity sag). `--open_deg` changes only that run's stage, never the USD file.

### 8.4 DEMO reproducibility

GPU deformables are not deterministic. A re-run gives a video of the same length (62.2 s), but not bit-identical results:

| Check | Delivered (`states/`) | Re-run 2026-10-02 | Re-run 2026-10-07 |
|---|---|---|---|
| In the box: cloth / mug vertices outside the cavity | 0 / 0 | 0 / 0 | 0 / 0 |
| Mug position difference after boxing | — | 11.5 mm (rigid shift) | — |
| Cloth vertex difference after boxing | — | mean 24.8 mm, max 130 mm | — |
| After moving the box: wrap displacement relative to box | 2.5 mm | 9.1 mm | 4.3 mm |
| After moving the box: vertices outside the cavity | 6 | 6 | 4 (cloth, slightly below the floor) |

`scene_final.usd` uses the delivered `states/box.npz`, not a re-run.

### 8.5 Rebuilding the scene

```bash
/isaac-sim/python.sh build/build_full_scene.py \
    --scene build/stationary_ai_carton_scene_flat.usd \
    --carton sim/carton.usd --wrap states/box.npz --mug sim/mug.stl \
    --out scene_final.usd     # --place x,y,z to choose a position; default "auto" aligns with the original carton
```

The rebuilt file again has **no** PhysicsScene and no crease drives. For UI use, follow §3.4 or add the §8.2 values yourself.

### 8.6 The physics package (`scene_final_phys.usd`)

Built by `sim/build_phys_scene.py` from `scene_final_ui.usd`. Everything else (arms, carton, crease drives, 120 Hz TGS solver) is unchanged.

| Part | How it is modelled |
|---|---|
| Wrap `/World/Packed/Wrap` | **Surface deformable** (1225 vertices, 2312 triangles). Rest shape = the wrapped shape (`restShapePoints` = points, `restBendAnglesDefault = restShapeDefault`), so the folds don't spring open. Material: Young's modulus 2e4 Pa, Poisson 0.45, thickness 4 mm, bend stiffness 4, friction 0.8, density 100 (≈ 65 g). Self-collision on, 64 solver iterations, contact / rest offset 5 / 1 mm, sleep settings as in `wrap_sim.py` |
| Mug `/World/Packed/Mug` | **Dynamic rigid body**, 0.32 kg, friction 0.9. Collider = stacked convex frusta following the outer profile + 13 spheres (r = 10 mm) along the handle |
| Carton | Unchanged, plus an invisible 20 mm pad collider under the 3 mm floor (child of the base), so wrap vertices can't poke through the floor |
| PhysicsScene | GPU dynamics + GPU broadphase, deformable contact capacity 4 M, collision stack 128 MB |
| Bake | Settled in the file before saving: 2 s with the mug held still, then 4 s free; the settled shape was written into both points and rest shape, velocities zeroed |

Why this works: a surface deformable's rest shape must be authored before Play (changing it during Play has no effect),
and the rest shape removes the bending spring-back but not gravity — every part of the wrap has to be supported, here by the mug and the carton floor.

**Tests** (UI path: open the file → Play; numbers in `sim/logs/verify_scene_final_phys_<test>.txt`):

```bash
cd sim
/isaac-sim/python.sh verify_phys_scene.py ../scene_final_phys.usd --test A    # rest 8 s, nothing touched
/isaac-sim/python.sh verify_phys_scene.py ../scene_final_phys.usd --test B    # carry: carton moved +0.20 m y / +0.10 m z over 3 s, hold 2 s
/isaac-sim/python.sh verify_phys_scene.py ../scene_final_phys.usd --test Bm   # same carry, done with a simulated mouse drag
/isaac-sim/python.sh verify_phys_scene.py ../scene_final_phys.usd --test C    # 3 N pressing lid fxn down onto the wrap for 3 s
```

Test A on the shipped file (2026-10-07):

| Measure | Result |
|---|---|
| Carton displacement / tilt | 0.12 mm / 0.07° |
| Wrap relative to carton | max 13.3 mm, mean 4.3 mm — **reached by 3 s, then no further change** |
| Mug relative to carton | 0.13 mm |
| Vertices outside the cavity (1 mm tolerance) | wrap 4 / 1225 (same as at the start), mug 0 |
| NaN / explosion | none |
| Lid angles | ≤ 2.1° |

Tests B, Bm and C have not been run on this file yet.

**Rebuild** (≈ 2 min; the defaults reproduce the shipped file — GPU deformables are not deterministic, so numbers vary slightly):

```bash
cd sim && /isaac-sim/python.sh build_phys_scene.py     # writes ../scene_final_phys.usd, log in ../logs/build_phys.log
```

---

## 9. Known issues

| # | Issue | Impact | What to do |
|---|---|---|---|
| 1 | `scene_final.usd` has no PhysicsScene; the UI's default is too weak | Carton sinks 48 mm on Play in the UI | Use `scene_final_ui.usd` or `crease_hold_ui.py` (§2, §8.2) |
| 2 | In `scene_final_ui.usd` / `scene_final.usd` the wrap and mug are static meshes | Can't be grabbed; dragging the carton leaves them behind; lids pass through | Use `scene_final_phys.usd` (§8.6) |
| 2a | `scene_final_phys.usd` needs deformables enabled at startup | Opened without it, the wrap doesn't simulate | Use the launch scripts, or §3.1 step 0 |
| 2b | `scene_final_phys.usd`: only the rest test (A) has been measured | Carrying the carton (B / Bm), pressing a lid onto the wrap (C) and mouse-dragging the wrap are not yet verified | Run `verify_phys_scene.py --test B / Bm / C` (§8.6) |
| 2c | Lids reported hard to pull open with the mouse | Not yet diagnosed | Open the upper lids (fyp / fyn) before the lower ones; report what you see |
| 3 | `crease_physics.py` **defaults** (k=3.5, My0=0.85, H=0.55, c=0.28, clip=3.6) differ from the values actually used (k=3.2, My0=0.60, H=0.85, c=0.33, clip=3.0) | Using the defaults won't reproduce the videos or numbers | Always pass the coefficients to `ElastoplasticCrease(...)` explicitly; keep c ≤ 0.4 (higher blows up numerically) |
| 4 | Log on Play: `angle limit ... clamped to ±180 degrees` (crease_*) | None | USD says ±185°, PhysX D6 caps at ±180°; the lids only move a few degrees |
| 5 | Log on Play: `PhysX error: ... foundLostAggregatePairsCapacity to 3418` | May miss contacts with default settings | `scene_final_ui.usd` and `crease_hold_ui.py` raise it to 8192; the error no longer appears |
| 6 | `make_definitive.sh` tells you to run `carton_sweep.py`, `gap.py`, `qa_carton.py`, which are **not in this package** | Carton QA can't be re-run as instructed | The carton itself still generates. Originals: `manip_fr3/carton/{gap,qa_carton}.py`, `manip_fr3/handoff_20260929/scripts/carton_sweep.py` |
| 7 | GPU deformables are non-deterministic | DEMO numbers vary between runs (§8.4) | Treat `states/*.npz` as the reference |
| 8 | Run from the Script Editor's File → Open, `crease_hold_ui.py` can't see its own path | Import fails if the package isn't at the default path (with a clear error message) | Set `SIM_DIR_OVERRIDE` on line 16, or use the one-liner in §3.4 |
| 9 | WebRTC default IP is `140.96.68.42` | Can't connect on another machine | Set `WEBRTC_IP=<public IP>` |

<p align="right"><a href="#english">↑ Back to top</a> · <a href="#繁體中文">繁體中文 ↓</a></p>

---

# 繁體中文

> **這是交出去的 handoff。** clone 下來就能開場景、按 Play、用滑鼠互動、重跑模擬、重新產生所有影片。
> **新增:** `scene_final_phys.usd` 裡的氣泡布和杯子有真正的物理(§2、§8.6)。
> 開發過程(實驗、122 次模擬紀錄、volume deformable、測試集)在
> [`sims/fr3_bubblewrap_pack_20261007`](../fr3_bubblewrap_pack_20261007),使用這份交付包不需要看那邊。

| | |
|---|---|
| **版本** | handoff_20261007 —— 2026-10-02 的場景與模擬;2026-10-07 新增:UI / WebRTC 用法、按 Play 的修正、有物理的包裹版本(`scene_final_phys.usd`) |
| **測試環境** | Isaac Sim 5.1.0、RTX 5090、NVIDIA driver 580 |
| **取得方式** | git:這個資料夾(不含影片,執行 `./make_videos.sh` 產生)· 壓縮檔:`handoff_20261007.tgz`(含影片) |

## 目錄

1. [快速開始](#1-快速開始)
2. [該開哪個場景檔](#2-該開哪個場景檔)
3. [在 Isaac Sim UI 裡使用](#3-在-isaac-sim-ui-裡使用)
4. [用 WebRTC 遠端看](#4-用-webrtc-遠端看)
5. [影片](#5-影片)
6. [檔案](#6-檔案)
7. [腳本:哪支在哪裡跑](#7-腳本哪支在哪裡跑)
8. [技術參考](#8-技術參考)
9. [已知問題](#9-已知問題)

---

## 1. 快速開始

```bash
./open_in_ui.sh        # 本機有螢幕:開 Isaac Sim 並載入 scene_final_phys.usd
./open_in_webrtc.sh    # 遠端:開串流,用 WebRTC Streaming Client 連線(§4)
./make_videos.sh       # 重新產生驗證影片;加 --demo 會連 62 秒的成果影片一起產生
```

畫面出來後:

1. 按 **▶ Play**(左側工具列)。
2. **Alt + 左鍵拖曳**:旋轉視角。
3. **Shift + 左鍵拖曳**:抓住紙箱或蓋子拖動。

---

## 2. 該開哪個場景檔

| 檔案 | 包材與杯子 | 用途 | 按 Play 的結果 |
|---|---|---|---|
| **`scene_final_phys.usd`** | **有物理:** 包材是 surface deformable、杯子是剛體 | **兩支啟動腳本的預設值。** 要跟包裹互動就用這個 | 紙箱 0.12 mm,包材 3 秒內穩定(最大 13.3 mm、平均 4.3 mm),杯子 0.13 mm(§8.6) |
| `scene_final_ui.usd` | 靜態 mesh(沒有物理) | 最穩的互動場景;只動紙箱和蓋子 | 紙箱 0.00 mm,蓋子 ≤ 0.75° |
| `scene_final.usd` | 靜態 mesh(沒有物理) | 正式交付檔;給 headless 腳本用;彈塑性摺痕(§3.4) | ⚠️ 在 UI 直接按 Play,**紙箱會陷進桌面 48 mm** |

> ⚠️ **`scene_final_phys.usd` 需要在 Isaac Sim 啟動時就開啟 deformable。** 兩支啟動腳本會自動處理。
> 用其他方式啟動的話,請先照 §3.1 開啟,否則包材不會有物理。

**`scene_final.usd` 會下陷的原因:** 它沒有 PhysicsScene,UI 會自動補一個預設的
(60 Hz、位置迭代 1 次、速度迭代 0 次),強度不夠,撐不住紙箱。
`scene_final_ui.usd` 是同一個場景,只多了調好的 PhysicsScene,以及四片蓋子摺痕上的彈簧 drive。
細節與實測數字見 [§8.2](#82-scene_final_uiusd-的修正)。

---

## 3. 在 Isaac Sim UI 裡使用

### 3.1 開啟場景

**用指令**

```bash
./open_in_ui.sh                    # 開 scene_final_ui.usd
./open_in_ui.sh scene_final.usd    # 或指定其他 USD
```
`open_in_ui.sh` 預設開 `scene_final_phys.usd`,並用
`--/persistent/physics/enableDeformableBeta=true --/physics/updateToUsd=true` 啟動 Isaac Sim。

**從 UI 開**

0. **每台機器做一次(`scene_final_phys.usd` 需要):** 在 Isaac Sim 裡 **Edit → Preferences → Physics** →
   勾選 **Enable Deformable Schema Beta (Requires Restart)** → 關掉 Isaac Sim 再重開。
   (或在 App Selector 的 **Extra Args** 填 `--/persistent/physics/enableDeformableBeta=true --/physics/updateToUsd=true`。)
1. 啟動 Isaac Sim,任選一種:
   - 執行 `/isaac-sim/isaac-sim.sh`(以 root 執行時,先 `export OMNI_KIT_ALLOW_ROOT=1`),或
   - 執行 `/isaac-sim/isaac-sim.selector.sh` → 選 **Isaac Sim Full** → **START**。
2. 開檔,任選一種:
   - **File → Open** → 選 `scene_final_phys.usd`(或 `scene_final_ui.usd`),或
   - 在下方 **Content** 面板的路徑列貼上這個資料夾的路徑,**雙擊** USD 檔。
     (不要把 USD 拖進 viewport —— 那是把它當 reference 加進目前的場景,不是開檔。)
   - 之後可以從 **File → Open Recent** 直接開。
3. 按 **▶ Play**。

### 3.2 視角與選取

| 動作 | 操作 |
|---|---|
| 旋轉視角 | **Alt + 左鍵拖曳** |
| 平移 | **中鍵拖曳** |
| 縮放 | **滾輪**,或 **Alt + 右鍵拖曳** |
| 原地環視 / 飛行 | **右鍵拖曳**(按住右鍵 + **WASD** 飛行) |
| 選取 / 對焦到選取物 | **左鍵** / **F** |
| 移動 / 旋轉 / 縮放 gizmo | **W / E / R**(**Q** 回到選取) |

### 3.3 跟物理互動(播放中)

| 操作 | 效果 |
|---|---|
| **Shift + 左鍵拖曳** | 抓住剛體拖動 |
| **Shift + 左鍵雙擊** | 推一下 |

抓取力道在 Physics 設定 → **Mouse Interaction**(Grab Force Coeff、Push Acceleration)。

| 物件 | Prim | 抓得到嗎 |
|---|---|---|
| 紙箱本體(箱底 + 四面牆) | `/World/Packed/Box/base` | ✅ 剛體 |
| 四片蓋子 | `/World/Packed/Box/{fxp,fxn,fyp,fyn}` | ✅ 剛體,用摺痕關節接在箱體上 |
| 氣泡布 | `/World/Packed/Wrap` | `scene_final_phys.usd`:surface deformable,會跟紙箱、蓋子、杯子碰撞;直接抓包材還沒測過 · 其他場景:❌ 靜態 mesh(蓋子會穿過去) |
| 馬克杯 | `/World/Packed/Mug` | `scene_final_phys.usd`:✅ 剛體(0.32 kg)· 其他場景:❌ 靜態 mesh |
| 手臂 | `/World/stationary_ai` | 改用關節 drive 控制(§3.5) |

在 `scene_final_ui.usd` 和 `scene_final.usd` 裡,包材和杯子是把模擬結果烘成的固定幾何。
`scene_final_phys.usd` 保留同樣的形狀,但讓它們有物理(§8.6)。

### 3.4 真正的彈塑性摺痕(蓋子折到哪就停在哪)

`scene_final_ui.usd` 裡的摺痕是彈簧:把蓋子拉開,放手後會彈回 0°。
要真實的行為(超過降伏力矩後,蓋子停在新的角度),
請開 **`scene_final.usd`**,再執行 `sim/crease_hold_ui.py`:

**用滑鼠點選**

1. **Window → Script Editor**
2. 在 Script Editor 裡:**File → Open**(Alt + O)→ 選 `sim/crease_hold_ui.py`
3. 如果交付包**不在** `/isaac-sim/test_scripts/manip_fr3/handoff_20261002/`,
   把第 16 行的 `SIM_DIR_OVERRIDE = ""` 改成你的 `sim/` 完整路徑。
4. 按 **Run**(Ctrl + Enter)。

**或貼一行**(會自己找到資料夾,不用改第 16 行)

```python
p = "/你的路徑/sim/crease_hold_ui.py"; exec(compile(open(p).read(), p, "exec"))
```

接著按 Play。這支腳本會:

- 調整 PhysicsScene(數值同 `scene_final_ui.usd`),紙箱不會下陷;
- 每個物理步對四片蓋子套用 `ElastoplasticCrease.step()`
  (k = 3.2、My0 = 0.60、H = 0.85、c = 0.33、clip = 3.0,同 `wrap_sim.py`),蓋子受 +τ、箱體受 −τ。

執行 `crease_stop()` 可以停掉。不要在 `scene_final_ui.usd` 上跑這支 —— 彈簧 drive 和摺痕力矩會疊在一起。

### 3.5 控制手臂

兩支手臂是同一個 articulation(root:`/World/stationary_ai/root_joint`),每個關節都已經有 drive(target 0)。
播放中:

| 關節 | Prim(在 `/World/stationary_ai/joints/` 底下) | Drive |
|---|---|---|
| 6 軸手臂 | `follower_{left,right}_joint_0` … `_5` | angular;stiffness 664–738(關節 0–2)、33–62(關節 3–5) |
| 夾爪 | `follower_{left,right}_left_carriage_joint` | linear,target 單位是公尺(`right_carriage_joint` 沒有 drive) |

- 單一關節:在 Stage 面板選取 → **Property → Drive → Target Position**(單位:度)。
- 所有關節的滑桿:**Window → Physics Inspector**。

---

## 4. 用 WebRTC 遠端看

伺服器串流完整的 Isaac Sim UI,你在另一台電腦上用
**Isaac Sim WebRTC Streaming Client**(NVIDIA Isaac Sim 下載頁的桌面程式)觀看和操作。
§3 的所有操作在串流畫面裡都一樣能用。

### 4.1 用指令(推薦)

腳本會幫你開場景、調視角、打開滑鼠拖曳,並自動按 Play。

```bash
./open_in_webrtc.sh                              # scene_final_ui.usd
./open_in_webrtc.sh scene_final.usd --crease     # 原檔 + 彈塑性摺痕(§3.4)
WEBRTC_IP=<對外 IP> WEBRTC_PORT=49110 ./open_in_webrtc.sh
WEBRTC_NO_PLAY=1 ./open_in_webrtc.sh             # 載入但不自動 Play
./open_in_webrtc.sh --stop                       # 停止串流
```

- 等 `logs/webrtc.log` 出現 `[handoff] READY`(約 20 秒)再連線。
- **這個模式不用按 Shift**,直接左鍵拖曳就能抓紙箱或蓋子。
- 預設 IP `140.96.68.42`(這台伺服器)、signaling port 49100。**換機器時請設定 `WEBRTC_IP`。**

### 4.2 從 UI 啟動

1. 在伺服器桌面執行 `/isaac-sim/isaac-sim.selector.sh`(App Selector)。
2. 選 **Isaac Sim Full Streaming**。
3. 對外 IP 不是預設值時,在 **Extra Args** 填 `--/app/livestream/publicEndpointAddress=<對外 IP>`。
4. 按 **START**。
   要開 `scene_final_phys.usd` 的話,再加上 `--/persistent/physics/enableDeformableBeta=true --/physics/updateToUsd=true`。
5. 用 Streaming Client 連進去,**File → Open** `scene_final_phys.usd`,按 Play
   (這個模式下,物理拖曳要 **Shift + 左鍵拖曳**)。

### 4.3 連線

- Streaming Client → 輸入伺服器 IP → **Connect**。
- 防火牆要開 **TCP 49100**(signaling)和 **UDP 47998**(影音)。

2026-10-07 實測:兩種指令模式都在約 20 秒內出現 READY(載入 591–592 個 prim、port 49100 有在監聽、物理有在跑),
`--stop` 能正常關閉。Client 端沒有測 —— 伺服器上沒有 client。

---

## 5. 影片

影片**不進 git**。一個指令就能把全部影片重新產生到 `videos/`:

```bash
./make_videos.sh                  # 下表前四支
./make_videos.sh --demo           # 再加 62 秒的 DEMO(需要 GPU)
VIDEO_DIR=/tmp/v ./make_videos.sh # 輸出到別的地方
```

| 影片 | 內容 | 單獨產生(在 `sim/` 裡執行) |
|---|---|---|
| `scene_physics_crease_on.mp4` | 開物理 8 秒,蓋子關著,有摺痕力矩 | `python.sh scene_physics_check.py ../scene_final.usd --out phys --secs 8` |
| `scene_physics_crease_off.mp4` | 對照組:沒有摺痕,下層蓋掉進箱子 | `python.sh scene_physics_check.py ../scene_final.usd --out phys_nc --secs 8 --no_crease` |
| `scene_physics_open_lids.mp4` | 蓋子翻開 170°,開物理 10 秒,最後從正上方看箱內 | `python.sh scene_physics_check.py ../scene_final.usd --out phys_open --secs 10 --open_deg 170` |
| `scene_final_orbit.mp4` | 繞場景一圈 12 秒(只算圖,不跑物理) | `python.sh orbit_video.py ../scene_final.usd orbit.mp4` |
| `DEMO_new_order_sheet400.mp4` | 成果:包第一對邊 → 第二對邊 → 入箱關蓋 → 搬箱開蓋(62 秒) | `./run_demo.sh`(產出 `sim/DEMO.mp4`) |

`python.sh` 指 `/isaac-sim/python.sh`。每支物理影片旁邊會有同名 `.log`,記錄逐秒的數字。

**要跑多久:** 2026-10-07 在 GPU 被其他工作共用的情況下實測 `./make_videos.sh --demo`:
物理影片約 3 分鐘、環繞影片約 25 分鐘、DEMO 約 6 分鐘,**總共約 32 分鐘**。GPU 空閒時會比較快。

---

## 6. 檔案

```
README.md                       本文件(English + 繁體中文)
scene_final.usd                 ★ 交付檔:雙臂工作站 + 紙箱 + 包好的馬克杯(單一檔案,14 MB)
scene_final_ui.usd              同一場景 + 調好的 PhysicsScene + 蓋子彈簧 drive,給 UI 用(§2)
scene_final_phys.usd            scene_final_ui.usd + 包材(deformable)與杯子(剛體)的物理(§8.6)
open_in_ui.sh                   在本機 Isaac Sim UI 開啟
open_in_webrtc.sh               用 WebRTC 開啟(--stop 停止)
make_videos.sh                  重新產生 videos/
videos/                         影片(只在壓縮檔裡;用 make_videos.sh 產生)
sim/                            模擬與工具 —— 平鋪資料夾,在裡面執行腳本
  wrap_sim.py                     模擬本體(Isaac Sim 5.1 surface deformable)
  grip_common.py                  wrap_sim.py 的共用零件
  crease_physics.py               彈塑性摺痕模型(降伏 + 硬化)
  crease_hold_ui.py               UI 的 Script Editor 用:摺痕力矩 + PhysicsScene 修正(§3.4)
  webrtc_boot.py                  open_in_webrtc.sh 的開機腳本(kit --exec)
  scene_physics_check.py          物理驗證 + 影片(走 isaacsim.core World)
  ui_path_check.py                物理驗證(走跟 UI 一樣的 Play 路徑,§8.2)
  build_phys_scene.py             從 scene_final_ui.usd 建出 scene_final_phys.usd(§8.6)
  verify_phys_scene.py            scene_final_phys.usd 的測試 A / B / Bm / C(§8.6)
  orbit_video.py                  環繞影片(只算圖)
  run_demo.sh                     跑四段模擬並串成 DEMO.mp4
  make_carton_P.py, make_definitive.sh   紙箱產生器
  carton.usd, carton.meta.json    紙箱資產(270 × 230 × 134 mm,4 片蓋)及幾何參數
  mug.stl, bubble_normal.png, floor_edges.json
states/                         每段模擬結束時布 + 杯子的頂點(c1, c2, box, mb_open),可以從任一段接著跑
build/
  build_full_scene.py             重組 scene_final.usd(§8.5)
  stationary_ai_carton_scene_flat.usd   原始雙臂場景(14 MB)
```

---

## 7. 腳本:哪支在哪裡跑

> **會自己建 `SimulationApp` 的腳本,絕對不要貼進 Script Editor。**
> 那會在執行中的 Kit 裡再開一個 Kit,結果是卡死或當掉。這類腳本要在終端機用 `/isaac-sim/python.sh` 執行。

| 腳本 | 是什麼 | 怎麼執行 |
|---|---|---|
| `sim/crease_hold_ui.py` | 摺痕力矩 + PhysicsScene 修正 | ✅ **唯一在 UI 裡執行的**(§3.4) |
| `sim/webrtc_boot.py` | WebRTC 開機腳本 | 由 `open_in_webrtc.sh` 透過 `kit --exec` 啟動 |
| `sim/crease_physics.py` | 摺痕模型(函式庫) | 被其他腳本 import |
| `sim/grip_common.py` | 共用模擬零件(函式庫) | 被 `wrap_sim.py` import |
| `sim/wrap_sim.py` | 包布 → 入箱 → 搬箱模擬 | 終端機:`sim/run_demo.sh` 或 `./make_videos.sh --demo` |
| `sim/scene_physics_check.py` | 物理驗證 + 影片 | 終端機(§5、§8.3) |
| `sim/ui_path_check.py` | UI 路徑的 Play 驗證 | 終端機(§8.2) |
| `sim/build_phys_scene.py` | 建出 `scene_final_phys.usd` | 終端機(§8.6) |
| `sim/verify_phys_scene.py` | 物理包裹的測試 | 終端機(§8.6) |
| `sim/orbit_video.py` | 環繞影片 | 終端機(§5) |
| `sim/make_carton_P.py` | 紙箱產生器 | 終端機,由 `make_definitive.sh` 呼叫 |
| `build/build_full_scene.py` | 重組場景 | 終端機(§8.5) |

```
wrap_sim.py ──► grip_common.py
            └─► crease_physics.py ◄── scene_physics_check.py
                                  ◄── crease_hold_ui.py ◄── ui_path_check.py --crease_script
                                                        ◄── webrtc_boot.py(open_in_webrtc.sh --crease)
```

全部都在 `sim/` 裡,不需要設定 PYTHONPATH。

---

## 8. 技術參考

### 8.1 場景配置(`scene_final.usd`)

| 項目 | 值 |
|---|---|
| 手臂場景 | `build/stationary_ai_carton_scene_flat.usd`;手臂與桌子**完全沒動** |
| 原本的 `/World/Carton` | 已移除,換成 `/World/Packed`(Box + Wrap + Mug) |
| 擺放 | 對齊原本的紙箱:中心 (x, y) = (−20, 0) mm,箱底 z = 20 mm(= 桌面) |
| 方向 | 繞 z 轉 90°;270 mm 長邊沿 y(兩支手臂之間的方向) |
| 紙箱世界座標 bbox | x −135…95、y −135…135、z 20…154 mm |
| 與夾爪的距離 | 四根夾爪指在 y 方向都離紙箱 68.7 mm |
| 包材與杯子 | 取自模擬第 3 段結束(`states/box.npz`);每個頂點都檢查過在箱內 |
| 蓋子 | 四片都關著(USD 預設角度 = 模擬結束時的角度) |
| 外部依賴 | 紙箱已攤平寫進檔案;只剩手臂場景原本就用的兩個 NVIDIA 雲端 MDL 材質 |
| 單位 / 座標軸 | Z-up,metersPerUnit = 1 |

摺痕關節是被動的(±185°,沒有 drive)。彈塑性摺痕(`crease_physics.py`)是執行時每個物理步額外施加的力矩,
所以存不進 USD。在自己的程式裡,要每一步對 `/World/Packed/Box/crease_{fxp,fxn,fyp,fyn}`
套用 `ElastoplasticCrease.step()` —— 最短的範例是 `scene_physics_check.py`。

### 8.2 `scene_final_ui.usd` 的修正

| 修改 | 值 |
|---|---|
| `/physicsScene` | 120 Hz、TGS、最少位置迭代 8、最少速度迭代 1、GPU aggregate pairs 8192 |
| `/World/Packed/Box/crease_{fxp,fxn,fyp,fyn}` | angular drive:stiffness 0.056 N·m/deg、damping 0.006 N·m·s/deg、max force 3.0、target 0 |

drive 的值取自摺痕模型的彈性段(k = 3.2 N·m/rad、c = 0.33 N·m·s/rad),換算成 USD angular drive 使用的「每度」單位。

用 `sim/ui_path_check.py` 實測(開檔、按 Play 的方式跟 UI 完全一樣;8 秒;2026-10-07):

| 路線 | 紙箱 z 最大位移 | 蓋子最大角度 | |
|---|---|---|---|
| A. `scene_final_ui.usd` 直接 Play | **0.00 mm** | 0.75° | ✅ |
| B. `scene_final.usd` + `crease_hold_ui.py` | **0.00 mm** | 0.08° | ✅ |
| 對照:`scene_final.usd` 直接 Play | **48.12 mm** | 2.60° | ❌ 紙箱陷進桌面 |

```bash
cd sim
/isaac-sim/python.sh ui_path_check.py ../scene_final_ui.usd                 # A
/isaac-sim/python.sh ui_path_check.py ../scene_final.usd --crease_script    # B
/isaac-sim/python.sh ui_path_check.py ../scene_final.usd                    # 對照
```

headless 的 `scene_physics_check.py` 從來沒量到下陷,因為 `isaacsim.core.World` 會套用比較好的解算器預設值。

### 8.3 走 `World` 的物理驗證(`scene_physics_check.py`)

2026-10-07 用 `make_videos.sh` 重跑,數字與 2026-10-02 完全相同。

| 檢查 | 蓋子關 + 摺痕 | 蓋子翻開 170° + 摺痕 | 蓋子關、無摺痕(對照) |
|---|---|---|---|
| 紙箱位移 | 0.00 mm | 0.00 mm | 0.00 mm |
| 箱底 − 桌面 | 0.00 mm | 0.00 mm | 0.00 mm |
| 下層蓋 fxp / fxn 最大角度 | 0.3° / 0.3° | 0.3° / 0.3° | **91.7° / 91.7°(掉進箱子)** |
| 上層蓋 fyp / fyn 最大角度 | 0.3° / 0.3° | 0.3° / 0.3° | 4.1° / 4.1° |
| 手臂關節最大漂移 | 0.07° | 0.07° | 0.07° |

角度 = 蓋子相對起始姿態繞鉸鏈轉了多少(0.3° 是重力造成的下垂)。`--open_deg` 只改那次執行的 stage,不會改到 USD 檔。

### 8.4 DEMO 的重現性

GPU deformable 不是確定性的。重跑的影片長度相同(62.2 秒),但結果不會逐位元相同:

| 檢查 | 交付版(`states/`) | 2026-10-02 重跑 | 2026-10-07 重跑 |
|---|---|---|---|
| 入箱:布 / 杯子超出內腔的頂點 | 0 / 0 | 0 / 0 | 0 / 0 |
| 入箱後杯子位置差 | — | 11.5 mm(整體平移) | — |
| 入箱後布頂點差 | — | 平均 24.8 mm、最大 130 mm | — |
| 搬箱後:包裹相對紙箱的位移 | 2.5 mm | 9.1 mm | 4.3 mm |
| 搬箱後:超出內腔的頂點 | 6 | 6 | 4(布,略低於箱底) |

`scene_final.usd` 用的是交付版的 `states/box.npz`,不是重跑的結果。

### 8.5 重組場景

```bash
/isaac-sim/python.sh build/build_full_scene.py \
    --scene build/stationary_ai_carton_scene_flat.usd \
    --carton sim/carton.usd --wrap states/box.npz --mug sim/mug.stl \
    --out scene_final.usd     # --place x,y,z 指定位置;預設 "auto" 對齊原本的紙箱
```

重組出來的檔案一樣**沒有** PhysicsScene,也沒有摺痕 drive。要在 UI 用,照 §3.4 做,或自己加上 §8.2 的值。

### 8.6 有物理的包裹(`scene_final_phys.usd`)

由 `sim/build_phys_scene.py` 從 `scene_final_ui.usd` 建出。其他部分(手臂、紙箱、摺痕 drive、120 Hz TGS 解算器)都沒動。

| 部分 | 怎麼建模 |
|---|---|
| 包材 `/World/Packed/Wrap` | **Surface deformable**(1225 個頂點、2312 個三角形)。靜止形狀 = 包好的形狀(`restShapePoints` = points,`restBendAnglesDefault = restShapeDefault`),所以摺痕不會彈開。材質:楊氏模數 2e4 Pa、Poisson 0.45、厚度 4 mm、彎曲剛性 4、摩擦 0.8、密度 100(約 65 g)。自碰撞開、解算迭代 64 次、contact / rest offset 5 / 1 mm、睡眠參數同 `wrap_sim.py` |
| 杯子 `/World/Packed/Mug` | **動態剛體**,0.32 kg,摩擦 0.9。碰撞體 = 沿外型疊起來的凸台 + 把手上 13 顆球(半徑 10 mm) |
| 紙箱 | 不變,另外在 3 mm 箱底下面加一塊看不見的 20 mm 墊片碰撞體(掛在箱底下),包材頂點才不會穿出箱底 |
| PhysicsScene | GPU dynamics + GPU broadphase,deformable 接觸容量 4 M,碰撞堆疊 128 MB |
| 沉降 | 存檔前先在檔案裡沉降:杯子固定 2 秒,再放開 4 秒;沉降後的形狀同時寫進 points 和靜止形狀,速度歸零 |

為什麼這樣可行:surface deformable 的靜止形狀要在 Play 之前寫好(Play 中途改沒有作用);
靜止形狀只消除摺痕的回彈,擋不住重力 —— 包材每個部分都要有東西撐著,這裡是杯子和箱底。

**測試**(走 UI 路徑:開檔 → Play;數字寫在 `sim/logs/verify_scene_final_phys_<測試>.txt`):

```bash
cd sim
/isaac-sim/python.sh verify_phys_scene.py ../scene_final_phys.usd --test A    # 靜置 8 秒,不碰任何東西
/isaac-sim/python.sh verify_phys_scene.py ../scene_final_phys.usd --test B    # 搬箱:3 秒內把紙箱往 y +0.20 m、z +0.10 m 移動,再停 2 秒
/isaac-sim/python.sh verify_phys_scene.py ../scene_final_phys.usd --test Bm   # 同樣的搬箱,改用模擬的滑鼠拖曳
/isaac-sim/python.sh verify_phys_scene.py ../scene_final_phys.usd --test C    # 用 3 N 把下層蓋 fxn 往下壓在包材上 3 秒
```

出貨檔的測試 A(2026-10-07):

| 項目 | 結果 |
|---|---|
| 紙箱位移 / 傾斜 | 0.12 mm / 0.07° |
| 包材相對紙箱 | 最大 13.3 mm、平均 4.3 mm —— **3 秒時就停住,之後不再變化** |
| 杯子相對紙箱 | 0.13 mm |
| 跑出內腔的頂點(容差 1 mm) | 包材 4 / 1225(跟一開始一樣)、杯子 0 |
| NaN / 爆炸 | 無 |
| 蓋子角度 | ≤ 2.1° |

測試 B、Bm、C 還沒在這個檔上跑過。

**重建**(約 2 分鐘;預設參數就會做出出貨的這個檔 —— GPU deformable 不是確定性的,數字會略有差異):

```bash
cd sim && /isaac-sim/python.sh build_phys_scene.py     # 寫出 ../scene_final_phys.usd,log 在 ../logs/build_phys.log
```

---

## 9. 已知問題

| # | 問題 | 影響 | 怎麼處理 |
|---|---|---|---|
| 1 | `scene_final.usd` 沒有 PhysicsScene;UI 的預設值太弱 | UI 按 Play 時紙箱陷 48 mm | 用 `scene_final_ui.usd` 或 `crease_hold_ui.py`(§2、§8.2) |
| 2 | `scene_final_ui.usd` / `scene_final.usd` 的包材與杯子是靜態 mesh | 抓不到;拖紙箱時它們留在原地;蓋子會穿過去 | 改用 `scene_final_phys.usd`(§8.6) |
| 2a | `scene_final_phys.usd` 需要在啟動時開啟 deformable | 沒開的話包材不會有物理 | 用啟動腳本,或照 §3.1 第 0 步 |
| 2b | `scene_final_phys.usd` 目前只量過靜置測試(A) | 搬紙箱(B / Bm)、蓋子壓包材(C)、用滑鼠直接拖包材都還沒驗證 | 執行 `verify_phys_scene.py --test B / Bm / C`(§8.6) |
| 2c | 有人回報蓋子用滑鼠很難拉開 | 還沒查出原因 | 先開上層蓋(fyp / fyn)再開下層蓋;遇到請回報狀況 |
| 3 | `crease_physics.py` 的**預設係數**(k=3.5、My0=0.85、H=0.55、c=0.28、clip=3.6)跟實際使用的(k=3.2、My0=0.60、H=0.85、c=0.33、clip=3.0)不一樣 | 用預設值會對不上影片和數字 | 建 `ElastoplasticCrease(...)` 時一律明確傳入係數;c 不要超過 0.4(會數值爆炸) |
| 4 | Play 時 log 出現 `angle limit ... clamped to ±180 degrees`(crease_*) | 無 | USD 設 ±185°,PhysX D6 上限 ±180°;蓋子實際只動幾度 |
| 5 | Play 時 log 出現 `PhysX error: ... foundLostAggregatePairsCapacity to 3418` | 預設設定下可能漏接觸 | `scene_final_ui.usd` 和 `crease_hold_ui.py` 已調到 8192;實測不再出現 |
| 6 | `make_definitive.sh` 提示要跑 `carton_sweep.py`、`gap.py`、`qa_carton.py`,但**不在交付包裡** | 沒辦法照提示重跑紙箱 QA | 紙箱本身照常能產生。原始位置:`manip_fr3/carton/{gap,qa_carton}.py`、`manip_fr3/handoff_20260929/scripts/carton_sweep.py` |
| 7 | GPU deformable 不是確定性的 | 每次跑 DEMO 數字會有差異(§8.4) | 以 `states/*.npz` 為準 |
| 8 | 從 Script Editor 的 File → Open 執行時,`crease_hold_ui.py` 拿不到自己的路徑 | 交付包不在預設路徑時 import 會失敗(有清楚的錯誤訊息) | 設第 16 行的 `SIM_DIR_OVERRIDE`,或用 §3.4 的一行指令 |
| 9 | WebRTC 預設 IP 是 `140.96.68.42` | 換機器就連不上 | 設 `WEBRTC_IP=<對外 IP>` |

<p align="right"><a href="#繁體中文">↑ 回到中文開頭</a> · <a href="#english">English ↑</a></p>
