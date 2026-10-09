---
id: L0052
title: 夾 surface 布的懸出邊要在一開始就合指,懸出段不到 1 秒就垂直下垂
status: active
severity: medium
confidence: measured
domains: [attach, surface]
tags: [grip, gripper, overhang, drape, bend 4, probe_grip_surf.py, close early]
triggers: [設計夾爪夾 surface 布邊的時間表, 照 volume 版的夾取流程套到 surface 版]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/vol/grip_surface/probe_grip_surf.py ~40, sims/fr3_bubblewrap_pack_20261007/vol/grip_surface/probe_peel_surf.py ~9]
related: [L0046, L0045]
observed: 2026-10-07
---

## 人話

**問題**:零厚度的布邊懸在外面時很軟,不到一秒就垂下來。照有厚度版本的節奏慢慢靠近再夾,手指到的時候布已經不在那裡了。

**做法**:夾膜時手指一開始就合在布邊上;或者改從下垂後的方向接近。

## 現象

bend 4 的布 30 mm 懸出段 0.8 s 內垂成近乎垂直(邊緣 z −26.5 mm、x 最大只剩 3.6 mm);指面投影內 0 個頂點 → 照 volume 時間表夾不到。

## 根因

surface 膜抗彎很弱(edge bend ∝ SBS · thickness³,L0037)。

## 做法

指面 t=0 就合在上片伸出段(`probe_*_surf.py` 預設先合);或改接近方式。計畫中的下一步是 attachment 式夾持(夾合時綁指間頂點、張開時 RemovePrim,L0050)。

## 證據

`probe_grip_surf.py` 參數 help 的 2026-10-07 實測。
