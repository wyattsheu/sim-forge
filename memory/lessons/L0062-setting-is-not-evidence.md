---
id: L0062
title:「我設了選項」不是證據,要觀察到效果(port 在聽、READY、數字改變)才算生效
status: active
severity: medium
confidence: measured
domains: [measure, workflow, env]
tags: [evidence, silent ignore, config key, verification, not_tested]
triggers: [回報某個設定或服務已經生效, 改了設定但現象沒變]
versions: Isaac Sim 6.0.1 / 5.1.0
scope: [tools/parcel-forge, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [tools/parcel-forge/docs/DECISIONS.md D021、D025、D035, sims/fr3_bubblewrap_pack_handoff_20261007/README.md §4.3、§9]
related: [L0005, L0061, L0030]
observed: 2026-09-16
---

## 人話

**問題**:很多設定寫錯不會報錯,只是被安靜地忽略。如果只因為「我設了」就跟使用者說好了,使用者連上去才發現什麼都沒有。

**做法**:每個「已經開好 / 已經生效」的說法,都要附上實際看到的效果;測不到的部分直接寫「沒測」。

## 現象

- `SimulationApp({"livestream": 2})` 被忽略,使用者連到灰畫面。
- experience 與 `hide_ui` 兩個開關都要對,任一個不對都不報錯。
- CCD 屬性為 true,但 GPU pipeline 實際關掉了 CCD。

## 根因

不存在的 config key、太晚設定的 carb setting、被 runtime 覆蓋的屬性,都不會丟錯誤。

## 做法

- 服務:`ss -lnt` 看到 LISTEN + log READY。
- 物理設定:讀回 runtime 狀態或量到數字改變。
- 無法 headless 驗的(滑鼠手勢、WebRTC client 端):明寫「未測」,請使用者確認一次。

## 證據

parcel-forge D021、D025(「I set the option is not evidence; the service shows the effect is」)、D035;handoff README §4.3「client side was not tested」、§9「mouse gesture … could not be exercised headless」。
