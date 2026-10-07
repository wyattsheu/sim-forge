# Bubble-Wrapped Mug in a Carton — Dual-Arm Workstation (Handoff)

**English** | [繁體中文](README.zh-TW.md)

> **This is the delivered handoff.** Clone it and you can open the scene, press Play, interact with the mouse,
> re-run the simulation, and regenerate every video.
> The development history (experiments, 122 logged runs, volume-deformable work, tests) lives in
> [`sims/fr3_bubblewrap_pack_20261007`](../fr3_bubblewrap_pack_20261007). You don't need it to use this package.

| | |
|---|---|
| **Version** | handoff_20261007 — scene and simulation from 2026-10-02, plus UI / WebRTC usage and a Play fix added 2026-10-07 |
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
./open_in_ui.sh        # local desktop: open Isaac Sim with the scene loaded
./open_in_webrtc.sh    # remote: stream it, connect with the WebRTC Streaming Client (§4)
./make_videos.sh       # regenerate the verification videos; add --demo for the 62 s result video
```

Once the viewport is up:

1. Press **▶ Play** (left toolbar).
2. **Alt + left-drag** to orbit the camera.
3. **Shift + left-drag** on the carton or a lid to pull it around.

---

## 2. Which scene file to open

| File | Use it for | What happens on Play |
|---|---|---|
| **`scene_final_ui.usd`** | **Interactive use in the UI** (the default for both launch scripts) | Carton stays put (0.00 mm), lids hold (≤ 0.75°) |
| `scene_final.usd` | The canonical deliverable; headless scripts; the elastoplastic crease (§3.4) | ⚠️ Pressed directly in the UI, **the carton sinks 48 mm into the table** |

**Why:** `scene_final.usd` has no PhysicsScene, so the UI creates a default one
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

**From the UI**

1. Start Isaac Sim, either way:
   - run `/isaac-sim/isaac-sim.sh` (as root, `export OMNI_KIT_ALLOW_ROOT=1` first), or
   - run `/isaac-sim/isaac-sim.selector.sh` → choose **Isaac Sim Full** → **START**.
2. Open the file, either way:
   - **File → Open** → pick `scene_final_ui.usd`, or
   - in the **Content** panel, paste this folder's path into the address bar and **double-click** `scene_final_ui.usd`.
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
| Bubble wrap | `/World/Packed/Wrap` | ❌ static mesh — no collider, no rigid body (lids pass through it) |
| Mug | `/World/Packed/Mug` | ❌ static mesh — no collider, no rigid body |
| Arms | `/World/stationary_ai` | Drive the joints instead (§3.5) |

The wrap and mug are the simulation result baked into fixed geometry ("the packed state").
Surface-deformable state cannot be stored in USD.

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
5. Connect with the Streaming Client, then **File → Open** `scene_final_ui.usd` and press Play
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
README.md / README.zh-TW.md     this document (English / 繁體中文)
scene_final.usd                 ★ the deliverable: dual-arm workstation + carton + wrapped mug (single file, 14 MB)
scene_final_ui.usd              same scene + tuned PhysicsScene + lid spring drives, for the UI (§2)
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

---

## 9. Known issues

| # | Issue | Impact | What to do |
|---|---|---|---|
| 1 | `scene_final.usd` has no PhysicsScene; the UI's default is too weak | Carton sinks 48 mm on Play in the UI | Use `scene_final_ui.usd` or `crease_hold_ui.py` (§2, §8.2) |
| 2 | Wrap and mug are static meshes | Can't be grabbed; nothing collides with them | By design. To make them interactive: give the mug a convex-hull collider + rigid body; the cloth can only become a static triangle-mesh collider; deforming it again means going back to deformables (see the development folder) |
| 3 | `crease_physics.py` **defaults** (k=3.5, My0=0.85, H=0.55, c=0.28, clip=3.6) differ from the values actually used (k=3.2, My0=0.60, H=0.85, c=0.33, clip=3.0) | Using the defaults won't reproduce the videos or numbers | Always pass the coefficients to `ElastoplasticCrease(...)` explicitly; keep c ≤ 0.4 (higher blows up numerically) |
| 4 | Log on Play: `angle limit ... clamped to ±180 degrees` (crease_*) | None | USD says ±185°, PhysX D6 caps at ±180°; the lids only move a few degrees |
| 5 | Log on Play: `PhysX error: ... foundLostAggregatePairsCapacity to 3418` | May miss contacts with default settings | `scene_final_ui.usd` and `crease_hold_ui.py` raise it to 8192; the error no longer appears |
| 6 | `make_definitive.sh` tells you to run `carton_sweep.py`, `gap.py`, `qa_carton.py`, which are **not in this package** | Carton QA can't be re-run as instructed | The carton itself still generates. Originals: `manip_fr3/carton/{gap,qa_carton}.py`, `manip_fr3/handoff_20260929/scripts/carton_sweep.py` |
| 7 | GPU deformables are non-deterministic | DEMO numbers vary between runs (§8.4) | Treat `states/*.npz` as the reference |
| 8 | Run from the Script Editor's File → Open, `crease_hold_ui.py` can't see its own path | Import fails if the package isn't at the default path (with a clear error message) | Set `SIM_DIR_OVERRIDE` on line 16, or use the one-liner in §3.4 |
| 9 | WebRTC default IP is `140.96.68.42` | Can't connect on another machine | Set `WEBRTC_IP=<public IP>` |
