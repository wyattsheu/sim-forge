---
id: L0043
title: 布上掛剛體泡泡時,間距用折好後的位置檢查,並過濾泡泡和它腳下那塊布的碰撞
status: active
severity: medium
confidence: measured
domains: [surface, attach]
tags: [bubbles, rigid bubble, element_filter, vtx_xform_attachment, spacing]
triggers: [在 deformable 上附掛剛體小物件, 布一開始就炸開]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~790-800、~834-840]
related: [L0049]
observed: 2026-09-24
---

## 人話

**問題**:在布上貼一顆顆小泡泡(剛體)時,如果依攤平時的位置排,折好後很多泡泡會擠在一起互相推開,把布炸飛;泡泡跟自己黏著的那塊布也會互相排斥。

**做法**:用折好之後的位置檢查泡泡間距;每顆泡泡都要設定「不跟自己腳下那塊布碰撞」。

## 現象

- 照攤平座標鋪:折疊後泡泡重疊、剛體互斥 → bbox 衝到 1121 × 1304 mm。
- 只寫 `vtx_xform_attachment`:每顆泡泡跟黏著的布互斥 → bbox 1624 × 1189 mm。

## 根因

別人的範例是鋪在平的布上,沒有這個問題;折疊把頂點擠在一起。原存檔每個 attachment 都有 `vtx_xform_attachment` **和** `element_filter_0` 兩個子 prim。

## 做法

- 間距檢查用折好後的頂點位置(`_FD`),< 2.2 r 就跳過。
- 每個 attachment 同時寫 element filter,過濾泡泡與附近(< 22 mm)的布三角形。

## 證據

`wrap_sim.py` 兩段 ★ 註解(實測 bbox 數字)。
