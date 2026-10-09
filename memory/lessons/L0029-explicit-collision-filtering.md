---
id: L0029
title: 碰撞過濾要明確列出對象並實測推得動,不要靠 bbox 自動判斷或 invertFilteredGroups
status: active
severity: high
confidence: measured
domains: [rigid, usd]
tags: [FilteredPairsAPI, CollisionGroup, invertFilteredGroups, pad collider, tabletop_link, frame_link]
triggers: [加一個隱形輔助碰撞體(墊片、加厚板), 設定 collision group, 物體突然拖不動]
versions: Isaac Sim 5.1.0(墊片 bug)/ 6.0(invertFilteredGroups)
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/CHANGELOG.md 2026-10-07 下午, sim-forge 分支 portable-isaac-launch commit 59eb65d sim/build_phys_scene.py]
related: [L0013, L0002, L0033]
observed: 2026-10-07
---

## 人話

**問題**:為了防止包材穿過箱底,在箱底下加了一塊看不見的墊片。墊片剛好埋在桌面裡,又沒有設定「不要跟桌子碰撞」,箱子就被死死卡在桌上,怎麼拉都不動。

**做法**:加輔助碰撞體時,明確寫出它不該跟誰碰撞;加完一定做一次「施力看推不推得動」的測試。

## 現象

- `scene_final_phys.usd` 紙箱完全拖不動:施 50 N 一秒 → 0.00 mm。
- 6.0 上「只跟包材碰撞」的墊片撞到桌子。

## 根因

- 過濾對象是靠 bbox 自動找「重疊的碰撞體」決定的,但碰撞 mesh 是 guide purpose,bbox 為空 → 一個都沒過濾(L0013)。
- Isaac 6.0 不吃 `invertFilteredGroups`(L0002)。

## 做法

- 明確列名:墊片對 `tabletop_link`、`frame_link` 加 `UsdPhysics.FilteredPairsAPI`。
- 「只跟 X 碰撞」:建一個「除了 X 和墊片以外的所有東西」的 group,過濾墊片對它;不要用 invert。
- log 印出實際過濾了哪些 prim 路徑。

## 驗證方法

推力測試:修前 50 N 一秒 0.00 mm,修後 20 N 一秒 225 mm。

## 證據

handoff CHANGELOG 2026-10-07 下午第一條;portable 分支 `build_phys_scene.py`「invertFilteredGroups is not honoured by Isaac Sim 6.0 (pads hit the table)」。
