---
id: L0031
title: 推布用的 kinematic 物體要放慢、每個 physics step 更新;要看真接觸就改成動態加 drive
status: active
severity: high
confidence: measured
domains: [rigid, surface, measure]
tags: [kinematic, lid_span, press_down, drive, set_world_pose, kinematic target, deformable contact]
triggers: [用 kinematic 蓋子、壓板、夾爪去推 deformable, 布被掃穿箱壁, 判斷布到底有沒有被頂住]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py --lid_span、--press_down、--close_lid help、~1653]
related: [L0044, L0061]
observed: 2026-09-26
---

## 人話

**問題**:用「不受力、照指定路徑走」的物體去推布時,它不管布擋不擋都會走到底:動太快會把布掃穿箱壁;而且量到的穿模是被硬壓進去的,不代表布真的擋得住。

**做法**:推的動作放慢;位置每一個物理步都更新;要知道布有沒有真的頂住東西時,把推的物體改成會受力的,用馬達帶動。

## 現象

- 蓋子 4 秒轉 180°(kinematic)→ 布被掃穿箱壁 315 點、箱底 108 點。
- 壓板 4 秒降 230 mm → 同樣穿出去。
- kinematic 蓋子量到 2.1 mm 穿模:那是「硬壓進去」,不是「被頂住」。

## 根因

kinematic 物體無限質量、照軌跡走;速度太快時 solver 來不及解 deformable 接觸。

## 做法

- 放慢(`--lid_span`、`--press_down` 調大),這是唯一不改物理的旋鈕。
- `move_box(t + i/(5*FPS))`:每個 physics substep 都更新 kinematic 目標,不要一格才跳一次。
- 要看真接觸:蓋子改成動態剛體 + 關節 drive;布頂得住,蓋子就會停在那裡。

## 證據

`wrap_sim.py` 各旗標 help 的實測數字(315 / 108 點)與使用者 2026-09-26 指示。
