---
id: L0038
title: 折疊的布開自碰撞時,selfCollisionFilterPose 要指向攤平佈局
status: active
severity: high
confidence: measured
domains: [surface]
tags: [selfCollision, selfCollisionFilterPose, OmniPhysicsDeformablePoseAPI, folded layout, interpenetration]
triggers: [布的初始形狀已經是折疊或重疊的, 開 selfCollision 後各片仍互相穿透]
versions: Isaac Sim 5.1.0-rc.19
scope: [sims/wrapped_mug]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §9]
related: [L0040]
observed: 2026-09
---

## 人話

**問題**:布一開始就是折好、互相重疊的狀態時,物理引擎會以為「這些部分本來就疊在一起」,把它們之間的碰撞關掉,結果各片互相穿透。

**做法**:告訴引擎用「攤平時的樣子」來判斷哪些部分本來就相鄰,折起來的部分才會互相碰撞。

## 現象

十字裁片四隻臂折起來互相蓋住,開 `selfCollision` 後臂彼此穿透。

## 根因

PhysX 預設拿「當下(已經重疊)」的點做自碰撞過濾,把互相蓋住的臂判成本來就重疊而排除。

## 做法

用 `OmniPhysicsDeformablePoseAPI` 把 `selfCollisionFilterPose` 指向**攤平的材料佈局**(flat layout 的 points)。

## 證據

`FINDINGS.md` §9。
