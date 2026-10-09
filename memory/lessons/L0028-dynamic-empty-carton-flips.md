---
id: L0028
title: 紙箱改成動態剛體時要放配重,不要用 FixedJoint 焊死來「解決」
status: active
severity: medium
confidence: measured
domains: [rigid]
tags: [dynamic carton, goods_kg, payload, FixedJoint, tip over]
triggers: [把紙箱 base 從 kinematic 改成 dynamic, 空箱被蓋子動作掀翻]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/make_carton_P.py --goods_kg help、meta _note(NINE_LESSONS E-4)]
related: [L0061, L0015]
observed: 2026-08
---

## 人話

**問題**:空紙箱很輕,讓它變成會動的物體之後,蓋子開關的反作用力就會把整個箱子掀翻。

**做法**:在箱子裡放一塊有重量的內容物;不要用把箱子焊在世界上的方式解決,那樣「箱子會不會被推動」的測試會變成永遠通過。

## 現象

base 改 dynamic 之後,0.3 kg 空箱被蓋子反作用力掀翻:九顆倒六顆、甩下桌。

## 根因

蓋子驅動的反作用力矩作用在很輕的箱體上。

## 做法

`--goods_kg <kg>` 在箱內放配重(對應人力評估文件「重內容物 → 箱體維持不動,單臂即可」)。要隔離摺痕物理時才用 `--anchor`(kinematic),並接受 S0 0.10「箱體位移」項**正確地 FAIL**。

## 證據

`make_carton_P.py`:「實測九顆有六顆被甩下桌」「不要改用 world FixedJoint 釘住,那會讓 S0 0.10 重新變成恆真」。
