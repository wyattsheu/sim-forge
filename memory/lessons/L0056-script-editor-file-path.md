---
id: L0056
title: Script Editor 用 File→Open 跑的腳本拿不到自己的路徑,用 exec(compile(open(p).read(), p, "exec")) 一行載入
status: active
severity: low
confidence: observed
domains: [ui]
tags: [Script Editor, __file__, exec compile, SIM_DIR_OVERRIDE, Content panel, reference]
triggers: [寫要在 UI Script Editor 執行、又需要 import 同資料夾模組的腳本, 教使用者在 UI 裡開場景]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/README.md §3.1、§3.4、§10 #8]
related: [L0001]
observed: 2026-10-07
---

## 人話

**問題**:在 Isaac 的腳本視窗裡打開腳本執行時,腳本不知道自己放在哪個資料夾,所以找不到旁邊的其他檔案。另外,把場景檔拖進畫面不是「打開」,而是「加進目前場景」。

**做法**:用一行指令載入腳本(會順便告訴它自己的路徑);開場景用選單的「開啟」或在檔案面板雙擊。

## 現象

`crease_hold_ui.py` 從 Script Editor File → Open 執行,import `crease_physics` 失敗(交付包不在預設路徑時)。

## 根因

Script Editor 執行時沒有設定 `__file__`。

## 做法

```python
p = "/your/path/sim/crease_hold_ui.py"; exec(compile(open(p).read(), p, "exec"))
```
並在腳本留一個 `SIM_DIR_OVERRIDE = ""` 的後備,失敗時印出清楚的錯誤。
開場景:File → Open 或 Content 面板雙擊;**不要**把 USD 拖進 viewport(那是加 reference)。

## 證據

handoff README §3.4 兩種執行方式、§10 #8、§3.1 開檔說明。
