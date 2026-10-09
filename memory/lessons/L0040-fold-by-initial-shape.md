---
id: L0040
title: 用「直接生成折好的初始形狀再鬆弛」來折布,不要用夾具推;障礙物就是物體本身
status: active
severity: high
confidence: measured
domains: [surface, geometry]
tags: [fold_init, fixture, placeholder block, flap length, wrap_plan.py, sweep bar]
triggers: [設計怎麼用模擬把布折起來, 布折不上去或俯視遮蔽 0%, 加輔助碰撞體幫忙折]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py 檔頭 docstring、--fold_init help、~416, sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/ADAPTING.md §1]
related: [L0038, L0042]
observed: 2026-09-23
---

## 人話

**問題**:用各種夾具(托、夾、壓、掃)去推平鋪的布,五種方法都折不上去;另外為了計算方便加的「佔位方塊」如果有碰撞,布會包住方塊而不是杯子。

**做法**:直接讓布一開始就是折好的形狀,再讓物理把它鬆弛到位;算尺寸用的佔位方塊只當數字,不要做成實體;布的長度要按公式算夠。

## 現象

- 9/23 四次失敗:布太短(折邊 176~276 mm 卻要爬 93 + 橫過 107)→ 俯視遮蔽 0%;杯子被布拖走 100~300 mm。
- 五種夾具(托/夾/壓/掃/架高掃)俯視遮蔽全部 0%;平鋪在地上的布任何夾具都碰不到它的邊。
- 佔位塊做成實體:布罩住佔位塊(z 230~335)而不是杯子(232~325),貼合 0%、中位距離 112 mm。

## 根因

純碰撞推布的機構不穩;佔位塊實體化後變成真正的障礙物。

## 做法

- `--fold_init`:初始頂點就生成折好的形狀,讓引擎鬆弛落定。
- 佔位塊只用來算折邊長度。
- 折邊長公式(`wrap_sim.py` ≈ 288~294,照 `wrap_plan.py`):
  `A,B,HC = ME + 2·margin`(高只加 1 個)、`CX = A/2 + wall`、`climb = hypot(wall, HC)`、`FLAP = climb + A/2 + overlap`、`WX = A + 2·wall + 2·FLAP`,取 max(WX, WY) 做正方形。腳本會印「最小需求 vs 實際採用」,`--sheet_mm` 小於最小需求就包不住。
- 折疊期間杯子 kinematic,折完放開。
- 掃桿半徑固定 = 折邊長,布才不會被拉伸。

## 證據

`wrap_sim.py` 檔頭「與 2026-09-23 四次失敗的差別」;`--fold_init` help;~416 佔位塊註解;ADAPTING §1。
