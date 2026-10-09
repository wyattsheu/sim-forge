---
id: L0015
title: 用 FixedJoint 固定物體要設 localPos0/1,否則物體會被拽到世界原點
status: active
severity: medium
confidence: observed
domains: [rigid]
tags: [FixedJoint, localPos0, localPos1, world anchor]
triggers: [要把一個剛體釘在世界上, 想用 joint 把箱子固定在桌上]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/make_carton_P.py --anchor help]
related: [L0061, L0028]
observed: 2026-08
---

## 人話

**問題**:用固定接頭把物體釘在世界上時,如果沒指定接頭的位置,物體會被拉到世界的原點去。

**做法**:要固定就把物體設成「不受力的固定物體」(kinematic);真的要用接頭,兩端的位置都要明確填。也要注意固定之後有些測試會變成永遠通過(見 L0061)。

## 現象

FixedJoint 連 body 與 world,沒設 `localPos0` → 箱子被往世界原點拽。

## 根因

joint frame 預設在原點;約束會把兩個 frame 對齊。

## 做法

- 要固定:優先 `kinematicEnabled=True`(行為誠實,見 L0061)。
- 一定要 FixedJoint:設 `physics:localPos0`(body 端)與 `physics:localPos1`(world 端 = body 目前世界位置)。

## 證據

`make_carton_P.py` `--anchor` 說明:「也不要用 FixedJoint:若不設 localPos0,它會把箱子往世界原點拽(踩過)」。
