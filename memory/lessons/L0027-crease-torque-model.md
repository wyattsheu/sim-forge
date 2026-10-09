---
id: L0027
title: 摺痕力矩是每步外加的,要設等效慣量、阻尼係數不超過 0.4,係數一律明確傳入
status: active
severity: high
confidence: measured
domains: [rigid, usd]
tags: [crease, ElastoplasticCrease, crease_physics.py, armature, inertia, damping, explicit damping stability, yield]
triggers: [用 crease_physics.py 或自己寫摺痕力矩, 蓋子抖動或發散, 想把摺痕行為存進 USD]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/make_carton_P.py ~246-249, sims/fr3_bubblewrap_pack_handoff_20261007/README.md §8.1、§10 #3]
related: [L0055]
observed: 2026-09
---

## 人話

**問題**:紙箱摺痕「折過頭就停在那裡」的行為是程式每一步自己施加的力,存不進場景檔。這個力如果沒搭配適當的轉動慣量,蓋子會越抖越大;另外程式的預設係數跟實際用的不一樣,用預設值會重現不出結果。

**做法**:用到摺痕的地方每一步都要掛上這段程式;蓋子設好轉動慣量;係數每次都明確寫出來,不要靠預設值。

## 現象

- 不設慣量 → 力矩每步正負跳、發散。
- `crease_physics.py` 預設 (k=3.5, My0=0.85, H=0.55, c=0.28, clip=3.6) ≠ 實際使用 (k=3.2, My0=0.60, H=0.85, c=0.33, clip=3.0),用預設值重現不了影片與數字。
- c > 0.4 數值發散。

## 根因

- 摺痕當**外加剛體力矩**時繞過 joint armature;顯式阻尼穩定條件 `c·dt/I < 2`,I 太小就破功。
- 彈塑性(降伏 + 硬化)是 runtime 狀態,USD 沒有對應 schema。

## 做法

- 蓋子 `MassAPI.diagonalInertia = (0.006, 0.006, 0.006)`(= 定版 armature),principalAxes 單位四元數。
- `ElastoplasticCrease(k=3.2, My0=0.60, H=0.85, c=0.33, clip=3.0)` 明確傳;c ≤ 0.4。
- 每個 physics step 對 `/World/Packed/Box/crease_{fxp,fxn,fyp,fyn}` 呼叫 `step()`,蓋子 +τ、箱體 −τ(`scene_physics_check.py` 是最短範例)。
- UI 裡要摺痕:`crease_hold_ui.py`;它會暫時把 USD 的彈簧 drive 歸零,不要跟 `lid_latch.py` 同時用。

## 證據

`make_carton_P.py`「不設這個的話顯式阻尼穩定條件 c*dt/I < 2 破功 → 力矩每步正負跳、發散(踩過)」;handoff README §10 #3。
