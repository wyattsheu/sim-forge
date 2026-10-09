---
id: L0003
title: 用到 trimesh / pxr / omni 的工具用 Isaac 的 python 跑,純 numpy 工具才用系統 python3
status: active
severity: low
confidence: observed
domains: [env]
tags: [python.sh, trimesh, pxr, usdenv.sh, ImportError]
triggers: [執行量測或分析腳本, 寫一支新的離線工具]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #12, tools/usdenv.sh, README.md「環境」]
related: []
observed: 2026-09-30
---

## 人話

**問題**:電腦上有兩個 Python:系統的和 Isaac 附的。有些分析工具需要的套件只裝在 Isaac 那個,用錯就會「找不到模組」。

**做法**:要讀 USD 或用到 trimesh 的工具用 Isaac 的 Python 跑;只用 numpy 的小工具用系統 Python 就好。新工具在檔頭註明用哪個。

## 現象

`python3 chain_pen.py ...` → `ImportError: No module named trimesh`;同樣 `check_place.py`。

## 根因

trimesh、pxr 只裝在 Isaac 的 python 環境。

## 做法

- 有 trimesh / pxr / omni:`/isaac-sim/python.sh tool.py`。
- 只要讀 USD、不需要 Isaac runtime:`source tools/usdenv.sh && $PY tool.py`(sim-forge 根 README)。
- 純 numpy(`layer_gap.py`、`edge_report.py`、`collect_runs.py`、`tests/`):系統 `python3`。
- 新工具在 docstring 第一段寫明直譯器。

## 證據

`sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md` #12;`sims/fr3_bubblewrap_pack_20261007/README.md`「環境」。
