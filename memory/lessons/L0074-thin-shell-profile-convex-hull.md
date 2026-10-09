---
id: L0074
title: 開口薄殼(杯子)的徑向剖面要取投影凸包,逐角度取最大半徑會被內壁騙
status: active
severity: medium
confidence: measured
domains: [geometry]
tags: [convex hull, radial profile, thin shell, mug, arc length, wrap length]
triggers: [從網格量物體的外輪廓或周長, 算包材要多長]
versions: 與版本無關(幾何)
scope: [sims/wrapped_mug]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §14]
related: [L0012]
observed: 2026-09
---

## 人話

**問題**:杯子是空心的,模型包含內壁。從杯子中心往外量半徑時,有些角度只量到內壁,算出來的輪廓變成鋸齒,周長被多算了好幾倍。

**做法**:先把杯子投影成外框輪廓(凸包)再量,這也正好是包材實際的樣子:包材會跨過把手和杯身之間的凹處,不會鑽進去。

## 現象

某些角度只取樣到內表面(量到 17.3 mm,杯半徑 31.4)→ 剖面鋸齒,弧長灌水 3.5 倍(146 mm 半周長算成 412 mm)。

## 根因

網格包含內壁;逐角度取樣點太稀時某些角度沒有外壁點。

## 做法

投影凸包:乾淨、平滑,而且符合泡泡紙行為(跨過凹角)。

## 證據

`FINDINGS.md` §14。
