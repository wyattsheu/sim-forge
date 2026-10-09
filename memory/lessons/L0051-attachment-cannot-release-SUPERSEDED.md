---
id: L0051
title: (已推翻)attachment 在模擬中途改無效,要放手只能把模擬拆成兩段
status: superseded
severity: medium
confidence: observed
domains: [attach, surface]
tags: [attachmentEnabled, stiffness, release, init_npz, stage2]
triggers: [讀到 wrap_sim.py 檔頭「不用 attachment」或 --init_npz help「跑到一半放力做不到」]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py 檔頭 docstring、--init_npz help(probe_release.py 2026-09-25)]
related: [L0050, L0077]
superseded_by: L0050
observed: 2026-09-25
---

## 人話

**問題**:這是一條**已經被推翻**的舊結論:「釘住布的點建立後就放不掉,只能把模擬拆兩段」。程式碼的註解裡還寫著這句話。

**做法**:不要照這條做,改看 L0050。看到程式註解這樣寫,知道它已過時即可。

## 現象

2026-09-25 `probe_release.py`:鬆手後頂點還是一路跟到底。

## 根因

(當時的判斷)attachmentEnabled / stiffness 在跑的途中改完全無效。
(後來查明)量測假象:三個同邊錨點一起升、被鄰居撐住;而且 stiffness 本來就無效。見 L0050。

## 做法

不適用 —— 見 L0050。拆兩段(`--init_npz` 第二段出生)這個流程本身仍可用,只是不再是「唯一辦法」。

## 證據

`wrap_sim.py` 檔頭「★ 不用 attachment」與 `--init_npz` help 的 2026-09-25 註解(仍留在程式中);推翻證據見 L0050。
