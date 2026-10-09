---
id: L0041
title: 懸空的水平布只釘外緣一定被重力拉長,攤開時要攤在地板上
status: active
severity: medium
confidence: measured
domains: [surface, geometry]
tags: [unbox, flat_ground, stretch, edge ratio, hanging sheet]
triggers: [做開箱或攤平包材的動作, 邊長比中位大於 1.05]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~1393-1400, sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/CHANGES_TO_VERIFY.md B10]
related: [L0039]
observed: 2026-09-26
---

## 人話

**問題**:把布從箱子拿出來攤開時,如果只抓住四邊、讓中間懸空,布會被自己的重量拉長變形。

**做法**:攤開時讓布放在地板上,讓地板撐住中間。

## 現象

外緣拉到 z=0.22 的攤平座標、內部還在箱底 → 外緣釘在零鬆弛的 586×586 上、內部要垂 200 mm → 邊長中位 1.117、z 跨 226 mm。改攤在地上後仍有 1.070(B10,未完全解)。

## 根因

懸空水平薄片只釘外緣,重力必然拉伸。

## 做法

`--flat_ground`:內部由地板支撐。驗收看「是不是同一張布」的邊長比中位 0.95~1.05。

## 證據

`wrap_sim.py`「懸空水平薄片只釘外緣,重力必然拉伸」;CHANGES_TO_VERIFY B10。
