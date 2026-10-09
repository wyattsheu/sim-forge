---
id: L0001
title: 會自己建 SimulationApp 的腳本只能在終端機跑,不能貼進 Script Editor
status: active
severity: high
confidence: observed
domains: [env, ui]
tags: [SimulationApp, Script Editor, python.sh, kit]
triggers: [要在 Isaac Sim UI 的 Script Editor 執行一支腳本, 寫一支要同時給 UI 和終端機用的腳本]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/README.md §7]
related: [L0056]
observed: 2026-10-07
---

## 人話

**問題**:有些腳本一開頭就自己啟動一個 Isaac Sim。把它貼進已經開著的 Isaac Sim 的腳本視窗裡跑,等於在 Isaac 裡面再開一個 Isaac,整個程式會卡死或當掉。

**做法**:開頭有 `SimulationApp(...)` 的腳本一律在終端機用 `/isaac-sim/python.sh` 跑;要在 UI 裡跑的腳本另外寫,不建 app、直接拿現有的 stage。

## 現象

把 `wrap_sim.py`、`scene_physics_check.py` 這類 standalone 腳本貼進 Window → Script Editor 執行 → Kit 卡住或崩潰。

## 根因

`SimulationApp` 會啟動一個新的 Kit 實例;在已經運行中的 Kit 裡呼叫,會在同一個程序內再起第二個 Kit。

## 做法

- 檔案分兩類,並在檔頭寫清楚:
  - **standalone**(`from isaacsim import SimulationApp` 在最上面)→ 終端機 `/isaac-sim/python.sh x.py`;
  - **UI 內**(`omni.usd.get_context().get_stage()` 拿現有 stage、用 physics step callback)→ Script Editor 或 `kit --exec`。
- README 放一張「哪支腳本在哪裡跑」的表(handoff README §7 的格式)。

## 驗證方法

grep 腳本開頭:有 `SimulationApp(` 的就不該出現在「UI 內執行」的說明裡。

## 證據

`sims/fr3_bubblewrap_pack_handoff_20261007/README.md` §7「Never paste a script that creates its own SimulationApp into the Script Editor」與腳本分類表。
