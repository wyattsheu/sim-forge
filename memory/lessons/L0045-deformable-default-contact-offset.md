---
id: L0045
title: deformable 自己的 contactOffset 預設約 2 cm,做夾取前要在 deformable prim 上設小
status: active
severity: medium
confidence: observed
domains: [surface, volume, attach]
tags: [contactOffset, restOffset, physxCollision, gripper, deformable prim]
triggers: [用夾爪或手指去夾 deformable, 夾爪還沒碰到物體就把它推開]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/vol/grip_common.py 檔頭設計要點]
related: [L0052, L0024]
observed: 2026-10
---

## 人話

**問題**:軟物體預設的碰撞距離很大(約 2 公分),夾爪還沒真的碰到,就已經把它推開了。

**做法**:在軟物體本身上把碰撞距離設小(約 3 mm),靜止距離設 0。

## 現象

夾爪靠近時 deformable 被推開,還沒接觸就分離。

## 根因

deformable prim 的 `physxCollision:contactOffset` 預設約 2 cm(在 deformable 上設,不是在夾爪上設)。

## 做法

在 deformable 的 prim 上:`physxCollision:contactOffset = 0.003`、`restOffset = 0`。

注意:這是夾取實驗(`grip_common.py`)的設定;包覆模擬(`wrap_sim.py`)為了防布互穿用 5 mm / 1 mm(L0035)。兩種用途要分開設。

## 證據

`vol/grip_common.py` 設計要點:「deformable 自己的 physxCollision:contactOffset 預設 ~2cm → 夾爪還沒碰到就被推開;一定要在 deformable 的 prim 上設小 (0.003), restOffset 0」。
