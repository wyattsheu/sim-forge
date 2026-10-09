---
id: L0007
title: 用到 deformable 的場景,Isaac 啟動時就要開 enableDeformableBeta
status: active
severity: high
confidence: measured
domains: [env, surface, volume]
tags: [enableDeformableBeta, persistent, Preferences, Extra Args, scene_final_phys.usd]
triggers: [開啟含 deformable 的 USD, 寫啟動腳本或交付說明, 包材在 UI 裡不動]
versions: Isaac Sim 5.1.0(6.x 預設已開,見 L0002)
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/README.md §2、§3.1、§10 #2a]
related: [L0002, L0008]
observed: 2026-10-07
---

## 人話

**問題**:布、膜這類軟物體要先在 Isaac Sim 的設定裡打開才會動,而且要在啟動時就打開。沒開的話場景照樣打得開,但包材就是一動也不動,看起來像模擬壞了。

**做法**:啟動腳本一律帶上開啟參數;交付說明寫清楚「用其他方式開要先到設定裡勾選再重開」。

## 現象

直接用 UI 開 `scene_final_phys.usd` 按 Play,包材不模擬;用 `open_in_ui.sh` 開就正常。

## 根因

5.1 的 deformable schema 是 beta,要在 Kit 啟動時就啟用;執行中才改沒有用。

## 做法

- 命令列:`--/persistent/physics/enableDeformableBeta=true --/physics/updateToUsd=true`
- standalone:`SimulationApp({"headless": True, "extra_args": ["--/persistent/physics/enableDeformableBeta=true"]})`
- UI:Edit → Preferences → Physics → 勾 Enable Deformable Schema Beta (Requires Restart) → 重開。
- 交付 README 的「該開哪個檔」表格旁邊放警告。

## 證據

`sims/fr3_bubblewrap_pack_handoff_20261007/README.md` §2 警告框、§3.1 步驟 0、§10 已知問題 #2a。
