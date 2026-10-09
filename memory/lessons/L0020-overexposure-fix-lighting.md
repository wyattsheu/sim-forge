---
id: L0020
title: 顏色看起來不對時先量照度,過曝要降燈光,不要去改材質顏色
status: active
severity: medium
confidence: measured
domains: [render]
tags: [lighting, DomeLight, exposure, diffuse, color calibration, headlight]
triggers: [使用者說顏色怪, 淺色物體一片死白, 調材質顏色調不準]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007, sims/wrapped_mug]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~335-350、~1243, sims/wrapped_mug/docs/FINDINGS.md §10]
related: [L0019]
observed: 2026-09-25
---

## 人話

**問題**:畫面顏色跟設定的不一樣時,常見的直覺是一直改材質顏色,其實是燈太亮,所有顏色都被沖淡甚至變全白。

**做法**:先用「設成純紅看出來是什麼顏色」判斷是不是燈光問題;是的話把燈調暗,顏色就一次全對了。

## 現象

- 指定杯子 diffuse (0.30, 0.40, 0.56) → 渲出 (0.86, 0.90, 0.93),背景地板同樣偏亮。
- Dome 900 把淺色膜打成一片死白。

## 根因

場景照度約 **3.7 倍**:diffuse 0.195 × 3.7 = 0.73(實測 0.73);純紅 1.0 × 3.7 被截到 1.0(實測 0.95)⇒ diffuse > 0.27 就一律爆白。材質本身綁定正確(純紅測試 G/B 為 0)。

## 做法

1. 判別:材質設純紅 → 若渲出 (≈1, 0, 0) 代表材質有效、沒有環境加色;比例過高代表過曝。
2. 修照度(headlight / dome 降到 1 倍;膜場景 Dome 900 → 260),不要把 diffuse 除以一個係數去湊。
3. 照度修正後才用像素量測做最後微調(本案再乘 (0.894, 0.931, 1.0))。

## 試過但無效

第一輪用「diffuse ÷ 2.9」反推顏色 —— 治標,換場景就又錯。

## 證據

`wrap_sim.py` 2026-09-25 照度註解;`FINDINGS.md` §10(Dome 900 → 260)。
