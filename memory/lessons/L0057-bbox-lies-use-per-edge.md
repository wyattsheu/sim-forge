---
id: L0057
title: 判斷布有沒有折好、疊幾層,不要看整片 bbox,用逐邊與疊層量測
status: active
severity: high
confidence: measured
domains: [measure, surface]
tags: [bbox, edge_report.py, layer_gap.py, fold check, layers]
triggers: [判斷包材折疊是否成功, 報告包裹尺寸或層數]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #3, sims/fr3_bubblewrap_pack_20261007/work/edge_report.py, sims/fr3_bubblewrap_pack_20261007/work/layer_gap.py]
related: [L0058, L0059]
observed: 2026-09-30
---

## 人話

**問題**:只看包裹的外框大小,看起來「包好了」,其實某一邊翻回地上或根本沒折到,外框看不出來。

**做法**:檢查每一條邊各自在哪裡、杯頂上疊了幾層;這兩個數字都對才算折好。

## 現象

bbox 看起來包好了,實際某條邊翻回地上或沒折到(例如 `t_c2` 寬 363 mm:+x 折翻回地上)。

## 根因

bbox 只有 6 個數,看不出哪條邊在哪。

## 做法

- 折疊:`edge_report.py`(逐邊,四邊各自收到哪裡)。
- 疊層:`python3 layer_gap.py <run>/wrap.npz --shrink_mm 25`(杯頂上方層數 / 層間距 / 疊層總厚;只算 35×35 網格)。
- 驗收:`tests/run_checks.py` 的 `layers`(≥ 2)、`edge_ratio`(中位 0.95~1.05)。

## 證據

PITFALLS #3。
