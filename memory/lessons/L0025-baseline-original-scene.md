---
id: L0025
title: 改別人的場景前先跑一次原封不動的基準測試,不要擅自改 kinematic 設定
status: active
severity: high
confidence: measured
domains: [rigid, workflow, measure]
tags: [baseline, kinematicEnabled, rig_baseline, regression, third-party scene]
triggers: [拿到別人的場景要加東西進去, 場景行為怪怪的不知道是誰造成的]
versions: Isaac Sim 5.1.0-rc.19
scope: [sims/wrapped_mug]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §6, sims/wrapped_mug/experiments/rig_baseline.py, sims/wrapped_mug/forge.py ~963]
related: [L0061]
observed: 2026-09
---

## 人話

**問題**:接手別人做好的場景時,一改出問題就分不清是原本就這樣、還是自己改壞的。曾經把一個本來固定不動的箱底改成會動,結果箱子每次都掉下桌。

**做法**:動手前先什麼都不加、直接播放一次,記下原本的行為當基準;別人刻意設成固定的東西不要擅自改,真的要改先問。

## 現象

`stationary_ai_carton_scene_flat.usd` 的 `/World/Carton/base` 原本 `kinematicEnabled=True`(只有耳朵是 dynamic)。烘焙流程尾端把它轉成 dynamic → 箱子每次都掉下桌(min z −31 mm)。

## 根因

自己的流程改了原場景的設定;沒有基準可比,一開始以為是別的原因。

## 做法

1. 寫 `rig_baseline.py` 這種基準:原場景不加任何東西純播放,記錄關鍵量(這裡是箱子 min z 全程 20.0 mm 不動)。
2. 每次改完跟基準比;偏離就是自己改的。
3. 原場景的 kinematic / drive 設定保留原樣;需求要改(例如「箱子要能被手臂推動」)時,交給場景擁有者決定。

## 證據

`FINDINGS.md` §6;`forge.py`「會讓整個箱子掉下桌(實測 min z 掉到 -31 mm)…再由手臂團隊決定要不要轉動態」。
