---
id: L0012
title: 帶 xformOp:scale 的資產不要用網格碰撞體,改用解析形狀組合
status: active
severity: high
confidence: measured
domains: [rigid, usd]
tags: [xformOp:scale, sdf, convexHull, mesh collider, cooking, primitive collider, mug]
triggers: [匯入外部資產當剛體, 物體靜止後沉進地板或箱底]
versions: Isaac Sim 5.1.0-rc.19 / PhysX 107.3.26
scope: [sims/wrapped_mug]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §4, sims/wrapped_mug/experiments/drop_test.py, sims/wrapped_mug/forge.py ~388]
related: [L0074]
observed: 2026-09
---

## 人話

**問題**:外部模型如果帶縮放(例如原始單位是公分,用 0.01 倍縮成公尺),Isaac 幫它算出來的碰撞外形會跑掉,杯子放到地上會整個沉下去好幾公分。

**做法**:這種模型的碰撞外形不要用原始網格,改用圓柱、球這類簡單形狀拼出來;擺好後做一次「掉到地上量最低點」的測試。

## 現象

同一顆杯子掉到地板,靜止後最低點:

| 碰撞體 | 最低點 |
|---|---|
| 對照方塊 | +0.00 mm |
| sdf(res 256) | −38.84 mm |
| convexHull | −38.62 mm |
| 頂點烘進自己網格 + sdf | −38.84 mm |
| 網格直接掛剛體下 + sdf | −38.84 mm |

## 根因

資產 `/RootNode` 帶 `xformOp:scale=(0.01,0.01,0.01)`,原始頂點是 9 單位級。四種 cooking 全部一樣沉 38.8 mm,判定為帶 scale 資產的 cooking 問題(確切機制未查明)。

## 做法

用解析形狀:杯身圓柱 + 把手一圈球(從實際頂點依角度分箱量出半徑與位置)。primitive 在 PhysX 最穩,還保留把手的孔。handoff 的杯子用「沿外輪廓堆疊的凸台 + 13 顆 r=10 mm 球」也是同一思路。

## 驗證方法

`drop_test.py` 形式:同場放一個對照方塊,比較靜止後最低點;對照 0.00、目標物差 < 1 mm 才算過。改完杯子停在箱底面上方 0.6 mm。

## 證據

`sims/wrapped_mug/docs/FINDINGS.md` §4 表格。
