---
id: L0058
title: 判斷布有沒有穿進物體要用邊級別檢查,只測頂點會漏
status: active
severity: high
confidence: measured
domains: [measure, surface]
tags: [penetration, chain_pen.py, trimesh.contains, edge sampling, vertex check]
triggers: [檢查布穿杯或穿箱, 驗收報告寫「穿模 0」之前]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/ADAPTING.md §4, sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/CHANGES_TO_VERIFY.md C2, sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~635]
related: [L0057, L0060]
observed: 2026-09-26
---

## 人話

**問題**:只檢查布的頂點有沒有在杯子裡面,會說「沒穿」;但頂點之間的布面其實已經切進杯子。

**做法**:每條邊上取多個點一起檢查,用專案裡的邊級別工具。

## 現象

同一個狀態:頂點判定 0 條、邊判定 14 條;另一次入箱第 0 格頂點判定 0、邊判定 94 條陷進杯面約 2 mm。

## 根因

網格邊長(約 17 mm)比穿入深度大很多,頂點可以都在外面而邊穿過去。

## 做法

`/isaac-sim/python.sh chain_pen.py mug.stl c1/traj.npz c2/traj.npz`:每條邊取 19 個內點做 `trimesh.contains`。工具自驗:同狀態邊級別必須比頂點級別多抓到(C2)。

## 證據

ADAPTING §4「頂點判定說 0 條、邊判定說 14 條」;`wrap_sim.py` 入箱註解。
