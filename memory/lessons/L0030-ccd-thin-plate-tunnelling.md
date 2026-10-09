---
id: L0030
title: 薄板防穿透要用 dt 掃描驗證;CCD 要場景和物體都開,而且開了不代表有生效
status: active
severity: high
confidence: measured
domains: [rigid, measure]
tags: [CCD, enableCCD, tunnelling, dt, kinematic, disableGravity, GPU pipeline]
triggers: [快速物體掉進或撞上薄板, 調整 physics dt, 用 kinematic 暫時抓住一個開了 CCD 的物體]
versions: Isaac Sim 6.0.1
scope: [tools/parcel-forge]
evidence: [tools/parcel-forge/docs/DECISIONS.md D017(含 resolution)、D023、D035]
related: [L0024]
observed: 2026-09-16
---

## 人話

**問題**:物體掉得快、板子又薄時,模擬的時間步一放大,物體就會直接穿過板子。打開防穿透功能也不保證有用:要兩個地方都開,而且某些設定下會被系統悄悄關掉。

**做法**:防穿透的驗收要在好幾種時間步下都跑一次;要暫時抓住物體時用「關掉重力」而不是「設成固定」,因為後者會讓防穿透失效。

## 現象

- 同場景 dt=1/60:probe 穿過 5 mm 底板停在世界地板 z=0.020;dt=1/240 正常停在箱內 z=0.225。probe 接觸前約 2.2 m/s,1/60 時每步 3.7 cm。
- 用 kinematic 抓住 probe → PhysX:「kinematic bodies with CCD enabled are not supported! CCD will be ignored.」
- GPU pipeline 的 log 顯示 suppress readback 會關掉 CCD,即使 scene 屬性是 true。

## 根因

離散碰撞每個 substep 只取樣一次位置;CCD 要 `PhysxRigidBodyAPI.enableCCD` **且** `PhysxSceneAPI.enableCCD`。

## 做法

- 兩處都開 CCD。
- 暫時 hold:`PhysxRigidBodyAPI.disableGravity=True`,body 保持 dynamic(還能被滑鼠推)。
- 加一個永久的 dt 掃描回歸測試(1/60、1/120、1/240 結果一致到 5 位小數才算過)。
- 紀錄 CCD 的**有效**狀態;成功的包覆是「在測過的設定下實測成立」,不是「CCD 證明有效」。
- 不接受「把 dt 調小直到通過」當作解法。

## 證據

parcel-forge D017(dt-sweep 修後三個 dt 都 0.02500)、D023、D035。
