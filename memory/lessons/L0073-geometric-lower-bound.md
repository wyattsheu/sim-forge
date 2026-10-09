---
id: L0073
title: 調參數前先算幾何下限:物品高 + 底板 + 包材層數 × 層厚 ≤ 箱內高,做不到就不是調參能解的
status: active
severity: medium
confidence: measured
domains: [geometry, measure]
tags: [lower bound, feasibility, carton height, wrap thickness, volume ratio, spec]
triggers: [使用者要求包得更小或箱子更小, 開始一輪調參之前]
versions: 與版本無關(幾何)
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/ADAPTING.md §2 幾何下限, sims/fr3_bubblewrap_pack_20261007/work/REPORT_THICKNESS.md §1-3, sims/fr3_bubblewrap_pack_20261007/work/學長說明_20261002.md]
related: [L0035, L0072]
observed: 2026-10-02
---

## 人話

**問題**:有些要求在幾何上根本做不到,例如杯子加上幾層包材就已經超過箱子的高度。如果沒先算,會花好幾天調參數去追一個不可能的目標。

**做法**:開始調之前先用簡單的加法算出最小可能的尺寸;做不到就直接跟負責人說明,讓他決定改規格還是換做法,並給出選項與建議。

## 現象

- 杯高 93 + 箱底板 3 + 包材兩層約 30 = 126 mm → 100 mm 的箱子幾何上不可能,130 才行。
- 目標「包起來 < 100 mm」要每層 < 1.5 mm,泡泡紙(3~4 mm / 層)做不到,是材料口徑問題。
- 寬度才是大頭:586 布每邊多 100 mm 堆在側面(體積 4.7 倍,真實包裝 1.5~2 倍)→ 縮布到 400 是最便宜的一步。

## 根因

規格與材料 / 幾何互相矛盾,不是模擬錯。

## 做法

1. 列算式(高、寬、深各一條),代入實際材料厚度。
2. 對照目前量到的值,找出差最多的那一項(本案是寬度,不是高度)。
3. 跟使用者確認口徑:給 A / B 選項、各自代價與建議(`學長說明_20261002.md` 的寫法)。

## 證據

ADAPTING §2「一個幾何下限」;REPORT_THICKNESS;學長說明。
