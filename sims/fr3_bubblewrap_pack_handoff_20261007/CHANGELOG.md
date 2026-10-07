# CHANGELOG

Newest first. Times are UTC. Each entry = one git commit on `sims/fr3_bubblewrap_pack_handoff_20261007`
(`git log --date=iso -- sims/fr3_bubblewrap_pack_handoff_20261007` shows the same history).
最新的在最上面。時間是 UTC。每一條對應一個 git commit。

---

## 2026-10-07 (afternoon) — physics package fixed, mouse drag that works, click → ROS 2
## 2026-10-07(下午)—— 物理版修好、滑鼠真的拖得動、點擊 → ROS 2 座標

**Fixed / 修正**
- `scene_final_phys.usd` could not be dragged at all: the 20 mm pad collider under the carton floor sat inside the
  table-top collider and `build_phys_scene.py` filtered it against nothing (collision meshes have purpose `guide`, so
  their bounding boxes came back empty). Fixed in `build_phys_scene.py`; the pad is now filtered against
  `tabletop_link` and `frame_link`. Before: 50 N for 1 s → 0.00 mm. After: 20 N for 1 s → 225 mm.
  紙箱完全拉不動:箱底下方的 20 mm 墊片碰撞體埋在桌面碰撞體裡,而且 `build_phys_scene.py` 沒有把它過濾掉
  (碰撞 mesh 的 purpose 是 `guide`,bbox 算出來是空的)。已修;墊片現在對 `tabletop_link`、`frame_link` 不碰撞。
  修前:施 50 N 一秒 → 0.00 mm。修後:20 N 一秒 → 225 mm。
- Mouse grab was in joint mode (`/physics/forceGrab=false`), which moves a 0.35 kg body only ~14 mm for a 150 mm drag
  whatever `pickingForce` is. Switched to force mode with `pickingForce=70` (sliding 150 mm → ~140 mm; lifting the carton by a wall
  tips it ≈ 26° but doesn't flip it — 100 flips it, 400 is unstable). Applied in `webrtc_boot.py` and the new `ui_boot.py`.
  滑鼠抓取原本是關節式(`/physics/forceGrab=false`),不管 `pickingForce` 多大,拖 15 cm 只動 1.4 cm。改成力量式、
  `pickingForce=70`(桌上推 15 cm 約 14 cm;抓箱壁提起來翹約 26° 但不翻 —— 100 會翻,400 不穩)。`webrtc_boot.py` 和新的 `ui_boot.py` 都套用。
- `crease_hold_ui.py` now zeroes the lid spring drives while attached (and restores them on `crease_stop()`), so it can be
  used on `scene_final_phys.usd` / `scene_final_ui.usd` too.
  `crease_hold_ui.py` 掛上時會先把蓋子的彈簧 drive 歸零(`crease_stop()` 時還原),所以也能用在 `scene_final_phys.usd` / `scene_final_ui.usd`。
- `verify_phys_scene.py` carry tests (B / Bm) moved the carton +0.20 m in y, straight into the gripper fingers 69 mm away;
  default is now `--move 0.10,0,0.10` (+x and up). Bm uses force-mode grab.
  `verify_phys_scene.py` 的搬箱測試(B / Bm)原本往 +y 移 20 cm,會撞到 69 mm 外的夾爪;預設改成 `--move 0.10,0,0.10`(+x 並抬高)。Bm 改用力量式抓取。

- Lids could not be opened with the mouse: crease spring stiffness 0.056 N·m/deg let the mouse reach only 15°. `build_phys_scene.py` now
  authors 0.012 N·m/deg (gravity sag ≈ 1°) and the carton base gets linear / angular damping 2 / 2 (`--lid_stiff`, `--lid_damp`, `--base_damp`).
  蓋子用滑鼠拉不開:摺痕彈簧剛性 0.056 N·m/deg,滑鼠只拉得到 15°。`build_phys_scene.py` 現在寫 0.012 N·m/deg(重力下垂約 1°),
  箱底加線性 / 角阻尼 2 / 2(`--lid_stiff`、`--lid_damp`、`--base_damp`)。

**Added / 新增**
- `sim/lid_latch.py` — bistable lid latch: drag a lid past 25° and it flips open and stays; push it back below 12° and it closes.
  Loaded by both launchers (`LID_LATCH=0` disables; not used in `--crease` mode). `lids_open()` / `lids_close()` for scripts.
  `sim/lid_latch.py` —— 蓋子雙穩態閂鎖:拉超過 25° 就翻開並停住,壓回 12° 以下就關上。兩支啟動腳本都會載入
  (`LID_LATCH=0` 關閉;`--crease` 模式不用)。程式可呼叫 `lids_open()` / `lids_close()`。
- `sim/click_to_ros.py` — **Ctrl + left-click** anywhere in the viewport (local window or WebRTC) publishes the 3D world
  point to ROS 2: `/clicked_point` (`geometry_msgs/msg/PointStamped`, `frame_id=world`) and `/clicked_prim`
  (`std_msgs/msg/String`, the prim that was hit). Transient-local QoS, so a late subscriber gets the last point. A red marker
  sphere shows where you clicked. Loaded automatically by both launch scripts (`CLICK_TO_ROS=0` disables).
  `sim/click_to_ros.py` —— 在 viewport(本機視窗或 WebRTC)裡 **Ctrl + 左鍵**點任何地方,3D 世界座標會發佈到 ROS 2:
  `/clicked_point`(`geometry_msgs/msg/PointStamped`,`frame_id=world`)和 `/clicked_prim`(`std_msgs/msg/String`,點到的 prim)。
  QoS 是 transient-local,晚點才訂閱也會拿到最後一個點。紅色小球標出點的位置。兩支啟動腳本都會自動載入(`CLICK_TO_ROS=0` 關閉)。
- `sim/ros_click_listener.py` — receiver example for the arm side (`ros2 topic echo /clicked_point` also works).
  `sim/ros_click_listener.py` —— 手臂那端的接收範例(用 `ros2 topic echo /clicked_point` 也可以)。
- `sim/ui_boot.py` — boot script for `open_in_ui.sh`: opens the scene, sets force-mode mouse grab, no-Shift dragging, loads click_to_ros.
  `sim/ui_boot.py` —— `open_in_ui.sh` 的開機腳本:開場景、設定力量式滑鼠抓取、免 Shift 拖曳、載入 click_to_ros。
- Both launch scripts set up ROS 2 for Kit: Isaac's internal jazzy libs + rclpy (python 3.11); the system `/opt/ros`
  (python 3.12) is removed from `PYTHONPATH` / `LD_LIBRARY_PATH` because mixing them made rclpy fail inside Kit.
  兩支啟動腳本會幫 Kit 設定 ROS 2:用 Isaac 內建的 jazzy 函式庫與 rclpy(python 3.11);系統的 `/opt/ros`(python 3.12)
  會從 `PYTHONPATH` / `LD_LIBRARY_PATH` 拿掉,因為混在一起 Kit 裡的 rclpy 會載入失敗。
- This CHANGELOG. / 這份 CHANGELOG。

**Measured / 實測** — see README §8.6 (numbers of this build) / 見 README §8.6(這一版的數字)。

---

## 2026-10-07 03:48 — `679eb23` open_in_webrtc.sh --stop waits until Kit has exited
`--stop` returned before Kit had actually quit, so an immediate restart was refused as "already running". Now waits up to 30 s, then force-kills.
`--stop` 以前送出訊號就回來,Kit 還沒真的關掉,緊接著重開會被擋成「已經在跑」。現在最多等 30 秒,還沒關就強制關閉。

## 2026-10-07 03:47 — `03b70fc` physics version of the package (scene_final_phys.usd)
Wrap = surface deformable whose rest shape is the wrapped shape, mug = dynamic rigid body, 20 mm floor pad, settled and baked.
Launch scripts open it by default with `enableDeformableBeta`. `build_phys_scene.py`, `verify_phys_scene.py` added. Rest test A: carton 0.12 mm, wrap max 13.3 mm, mug 0.13 mm.
(The pad bug above was in this version — the carton could not be dragged.)
包材改成 surface deformable(靜止形狀 = 包好的形狀)、杯子改成剛體、箱底加 20 mm 墊片、沉降後烘進檔案。啟動腳本預設開它。
新增 `build_phys_scene.py`、`verify_phys_scene.py`。靜置測試 A:紙箱 0.12 mm、包材最大 13.3 mm、杯子 0.13 mm。(上面的墊片 bug 就是這一版的 —— 紙箱拉不動。)

## 2026-10-07 02:46 — `b4aae21` English and 繁體中文 in one README.md
GitHub only renders README.md, so both languages live there (English first, then Chinese, language switch at the top).
GitHub 只會顯示 README.md,所以兩種語言都放進去(先英文、後中文,最上面可切換)。

## 2026-10-07 02:43 — `63250b9` bilingual README, restructured
Usage first (quick start, which scene, UI, WebRTC, videos), reference after. Measured `make_videos.sh` timings and the 2026-10-07 DEMO re-run numbers added.
先講怎麼用(快速開始、該開哪個檔、UI、WebRTC、影片),技術細節放後面。加上 `make_videos.sh` 實測時間與 10-07 重跑 DEMO 的數字。

## 2026-10-07 02:26 — `edb867d` 交付版 handoff (first push)
Dual-arm workstation + carton + wrapped mug, clone-and-run: `scene_final.usd`, `scene_final_ui.usd` (fixes the 48 mm carton sink on Play in the UI),
arm scene, carton, `mug.stl`, `open_in_ui.sh`, `open_in_webrtc.sh`, `crease_hold_ui.py`, `make_videos.sh` (videos are not in git).
雙臂工作站 + 紙箱 + 包好的馬克杯,clone 下來就能用:`scene_final.usd`、`scene_final_ui.usd`(修正 UI 按 Play 紙箱陷 48 mm)、
手臂場景、紙箱、`mug.stl`、`open_in_ui.sh`、`open_in_webrtc.sh`、`crease_hold_ui.py`、`make_videos.sh`(影片不進 git)。

## 2026-10-02 — original delivery (`handoff_20261002.tgz`, not in git)
`scene_final.usd`, four-stage simulation (`wrap_sim.py`, `run_demo.sh`), physics verification videos, states, carton generator.
原始交付:`scene_final.usd`、四段模擬(`wrap_sim.py`、`run_demo.sh`)、物理驗證影片、states、紙箱產生器。
