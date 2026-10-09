---
id: L0002
title: Isaac Sim 5.1 和 6.0 的 API 與物理行為不同,程式和資產不要跨版本直接搬
status: active
severity: high
confidence: measured
domains: [env, usd, rigid]
tags: [Isaac Sim 6.0, Isaac Sim 5.1, isaacsim.core.api, World, SimulationManager, invertFilteredGroups, enableDeformableBeta, pip]
triggers: [在另一台機器或另一個 Isaac 版本上跑既有腳本, 把 sims 的程式搬進 tools/parcel-forge 或反過來, 重建 scene_final_phys.usd]
versions: Isaac Sim 5.1.0 (binary, sims) / 6.0.0-rc.22 (pip, portable 分支) / 6.0.1.0 (pip, parcel-forge)
scope: [sims/fr3_bubblewrap_pack_handoff_20261007, tools/parcel-forge]
evidence: [tools/parcel-forge/docs/ENVIRONMENT.md「API shape on this version」, tools/parcel-forge/docs/DECISIONS.md D002, sim-forge 分支 portable-isaac-launch commit 59eb65d、c3a974e(CHANGELOG 與 build_phys_scene.py 註解)]
related: [L0029, L0007]
observed: 2026-10-07
---

## 人話

**問題**:實驗室同時有 5.1 和 6.0 兩種 Isaac Sim。同一支程式或同一份場景檔換版本跑,可能直接報錯,也可能「能跑但結果不一樣」,後者最難發現。

**做法**:每支腳本和每個交付檔都寫明在哪個版本驗證過;換版本時先跑一次驗收測試比對數字,不要直接沿用舊結果。

## 現象

- 6.0 沒有 `isaacsim.core.api`(4.x/5.x 的 `World`、`DynamicCuboid`、`SimulationContext`),import 直接失敗;parcel-forge 改用 `isaacsim.core.simulation_manager.SimulationManager` 與 `isaacsim.core.experimental.prims`。
- 6.0 的 tensors view 需要 `stage_id` + `omni.physx.tensors`。
- 6.x 預設就開 deformable beta,`SETTING_ENABLE_DEFORMABLE_BETA` 要加防護,不然存取會出錯。
- 6.0 **不吃 `invertFilteredGroups`**:墊片原本「只跟包材碰撞」,在 6.0 變成撞到桌子。
- 同一支 `build_phys_scene.py` 在 6.0 重建,馬克杯沉降後的姿態跟 5.1 交付版差約 90°,所以 portable 分支**沒有**用 6.0 重建 `scene_final_phys.usd`。
- pip 版 Isaac 第一次啟動要編譯 shader / extension,約 5 分鐘才 READY。

## 根因

6.0 重整了 core API,PhysX 版本也不同;沉降結果對接觸細節敏感,換 solver 版本就會落到不同的穩定姿態。

## 做法

1. 腳本 / README 寫「Tested on Isaac Sim X.Y.Z」。
2. 用 `sim/find_isaac.sh`(portable 分支)這種偵測腳本,不要寫死 `/isaac-sim/python.sh`;支援 binary / Docker / pip。
3. 碰撞過濾不要靠 `invertFilteredGroups`;改成「對一個明確列出成員的 group 過濾」或逐對 `FilteredPairsAPI`。
4. 烘焙(settle 後寫回)的資產,換版本要重跑驗收,不要假設跟舊版一樣。
5. pip 版第一次啟動等 5 分鐘再判斷是否卡住。

## 驗證方法

換版本後跑既有驗收(例如 `verify_phys_scene.py --test A/B/C`),把數字和交付版的表格並排比。

## 證據

- `tools/parcel-forge/docs/ENVIRONMENT.md`:「Isaac Sim 6.0 does not ship isaacsim.core.api」。
- portable 分支 CHANGELOG:「Isaac Sim 6.0 compat: SETTING_ENABLE_DEFORMABLE_BETA guarded (default in 6.x); tensors view needs stage_id + omni.physx.tensors」「scene_final_phys.usd NOT rebuilt here: a 6.0 build settles the mug ~90 deg differently from the delivered 5.1 build」。
- portable 分支 `sim/build_phys_scene.py`:「invertFilteredGroups is not honoured by Isaac Sim 6.0 (pads hit the table)」。
