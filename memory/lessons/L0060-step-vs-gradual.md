---
id: L0060
title: 某個量在階段交界跳一下是擺位或記帳 bug,在階段內慢慢爬才是物理
status: active
severity: high
confidence: measured
domains: [measure, pipeline]
tags: [stage boundary, step change, placement bug, bookkeeping, diagnosis]
triggers: [多段模擬某個指標突然變差, 判斷問題是座標還是物理]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/ADAPTING.md §5, sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #16, sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~625-645]
related: [L0071, L0058]
observed: 2026-09-26
---

## 人話

**問題**:模擬分好幾段跑時,數字變差有兩種可能:物理真的把東西擠壞了,或是程式在交接時把東西放錯位置。兩者修法完全不同。

**做法**:看變化的形狀:在兩段交接的那一格突然跳 → 是放置位置算錯;在一段之內慢慢變差 → 才是物理。

## 現象

- 布穿杯在入箱那一格從 0 跳到 172 → 座標 bug,不是包覆不良。
- 入箱 t=0 杯心就跳到 (−15, 33, 55)(`fin_box`)→ 杯子平移用頂點平均而非 bbox 中心,多搬約 10 mm。
- 入箱第 0 格 94 條邊陷進杯面約 2 mm,關蓋全程沒再變糟 → 階躍,坐實是搬移造成。

## 根因

交界的搬移 / 置中是純座標運算;物理不會在一格內產生大跳躍。

## 做法

每段第 0 格就記錄關鍵量(穿模、杯心、bbox),跟上一段最後一格比。跳一階 → 查擺位程式(L0071)。

## 證據

ADAPTING §5;PITFALLS #16;`wrap_sim.py` 2026-09-26 註解。
