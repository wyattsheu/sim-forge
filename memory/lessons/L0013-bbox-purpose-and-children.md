---
id: L0013
title: 用 BBoxCache 算位置前,確認它包含哪些子物件和哪些 purpose
status: active
severity: high
confidence: measured
domains: [usd, rigid, geometry]
tags: [BBoxCache, purpose, guide, render, ComputeWorldBound, collision mesh, pad collider]
triggers: [用 bbox 算箱底高度或擺放位置, 用 bbox 判斷碰撞體重疊來決定過濾]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~453, sims/fr3_bubblewrap_pack_handoff_20261007/CHANGELOG.md 2026-10-07 下午第一條]
related: [L0029]
observed: 2026-09-25
---

## 人話

**問題**:用「外框」算位置時,外框可能把子物件也包進來(箱子的外框上緣其實是箱口,不是箱底),也可能漏掉被標成輔助用途的碰撞體而算出空的。兩種都不會報錯,只會讓東西擺錯位置。

**做法**:算外框前確認要包含哪些物件、哪些用途;箱底這種量從生成器的參數檔讀,不要用外框推。

## 現象

- 用 `/Box/base` 的 bbox 上緣當箱底 → 上緣是 100 mm(箱口),第一次跑就把包裹墊到箱子**上面**。
- `build_phys_scene.py` 用 bbox 找「跟墊片重疊的碰撞體」來過濾:碰撞 mesh 的 purpose 是 `guide`,bbox 算出來是空的 → 什麼都沒過濾 → 20 mm 墊片埋在桌面碰撞體裡,紙箱完全拉不動(50 N 一秒位移 0.00 mm)。

## 根因

- `ComputeWorldBound` 對 prim 取的是整個子樹;base 底下有牆。
- `BBoxCache(time, ["default", "render"])` 不含 `guide` purpose;碰撞 mesh 常被標成 guide。

## 做法

- 箱底內面 = 整箱最低點 + 板厚,或直接讀 carton meta 的 derived 值(L0014)。
- 要算碰撞體的範圍:includedPurposes 加 `guide`,或直接讀碰撞 prim 的 extent / 幾何參數。
- 過濾規則不要依賴「算出來有重疊」:明確列出要過濾的對象(墊片對 `tabletop_link`、`frame_link`)。

## 驗證方法

印出 bbox 的實際數值並與已知尺寸比對;過濾後做一個推力測試(修後 20 N 一秒 → 225 mm)。

## 證據

`wrap_sim.py`「不要拿 /Box/base 的 bbox 上緣當箱底」註解;handoff CHANGELOG「collision meshes have purpose guide, so their bounding boxes came back empty」。
