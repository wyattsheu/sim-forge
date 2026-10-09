---
id: L0019
title: 包材膜不要開 OmniPBR 的 enable_opacity,交付版用不透明材質
status: active
severity: medium
confidence: measured
domains: [render, surface]
tags: [OmniPBR, enable_opacity, film, transparent, bubble wrap]
triggers: [想讓包材或膜半透明, 膜在畫面上完全看不到]
versions: Isaac Sim 5.1.0-rc.19
scope: [sims/wrapped_mug]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §10, sims/wrapped_mug/params.py ~79]
related: [L0020]
observed: 2026-09
---

## 人話

**問題**:想讓包材看起來半透明而打開透明選項,結果包材在畫面上整片消失。

**做法**:包材用不透明材質,用顏色和凹凸貼圖表現泡泡紙的感覺。

## 現象

把 diffuse 設成鮮紅實測,畫面上一點紅都沒有 —— 膜完全不渲染。

## 根因

未查明;`enable_opacity` 在這個 deformable 膜上讓它完全不出現。

## 做法

不開 opacity;用淺色不透明 + 法線貼圖(`bubble_normal.png`)。同時注意燈光不要過曝(L0020)。

## 驗證方法

把顏色設成鮮紅跑一張圖,看得到紅色才確定材質有生效。

## 證據

`sims/wrapped_mug/docs/FINDINGS.md` §10。
