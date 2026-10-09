---
id: L0032
title: Play 時的 PhysX 警告要分辨:aggregate pairs 容量不足要調大,D6 角度限制 ±180 可忽略
status: active
severity: low
confidence: measured
domains: [rigid]
tags: [foundLostAggregatePairsCapacity, gpuFoundLostAggregatePairsCapacity, angle limit clamped, D6]
triggers: [Play 後 log 出現 PhysX error 或 warning]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/README.md §10 #4、#5]
related: [L0011]
observed: 2026-10-07
---

## 人話

**問題**:按 Play 之後常跳出物理引擎的錯誤訊息,有的會讓碰撞漏算,有的完全沒影響,分不清就會浪費時間。

**做法**:看到「容量不足」類的訊息就把對應容量調大;看到「角度限制被截成正負 180 度」可以忽略。

## 現象

- `PhysX error: ... foundLostAggregatePairsCapacity to 3418`
- `angle limit ... clamped to ±180 degrees`(crease_*)

## 根因

- 預設 GPU found/lost aggregate pairs 容量不夠 → 可能漏接觸。
- USD 寫 ±185°,PhysX D6 上限 ±180°。

## 做法

- PhysicsScene 設 GPU found/lost aggregate pairs 8192(`scene_final_ui.usd`、`crease_hold_ui.py` 都這樣做,錯誤就消失)。
- 角度限制警告:蓋子只動幾度時無影響;若真的需要 > 180° 的鉸鏈,要另外查(關節會在 ±180 處折返)。

## 證據

handoff README §10 已知問題 #4、#5。
