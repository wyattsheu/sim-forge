---
id: L0059
title: 取樣式指標(射線圍蔽率)100% 不代表沒有縫,要配合邊級別量測和畫面
status: active
severity: medium
confidence: measured
domains: [measure]
tags: [W1, W3, ray casting, enclosure, coverage, sampling]
triggers: [用覆蓋率或圍蔽率判斷包得好不好]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #4]
related: [L0057, L0058]
observed: 2026-09-30
---

## 人話

**問題**:「包覆率 100%」是從杯子中心往外射幾百條線算的,線和線之間、斜著看的縫隙都算不到,所以數字滿分但打開蓋子還是看得到杯身。

**做法**:這種數字只當參考,要搭配逐邊檢查和實際畫面一起判斷;數字優先,但不能只看一個數字。

## 現象

log W1 / W3 100%,開蓋後畫面看得到杯身。

## 根因

W3 只從杯心沿 300 條射線(穿過 300 個隨機杯子頂點)打布三角形;射線之間、斜看的縫不會被算到。

## 做法

不單看 W1/W3;配合 `chain_pen.py` 與畫面。報告寫明指標的取樣方式。

## 證據

PITFALLS #4。
