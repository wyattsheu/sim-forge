---
id: L0077
title: 前人的「做不到 / 無效」結論先用最小探針重驗再接受;程式存在不代表跑過
status: active
severity: high
confidence: measured
domains: [workflow, measure]
tags: [prior conclusion, probe, measurement artifact, handoff, STATE.md, evidence]
triggers: [交接文件或程式註解說某件事做不到, 接手一個專案要判斷進度, 打算根據前人結論放棄一個做法]
versions: 與版本無關
scope: [sims/fr3_bubblewrap_pack_20261007, tools/parcel-forge]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/REPORT_20260930.md §1 結論 2、§4, tools/parcel-forge/docs/DECISIONS.md D016→D018, tools/parcel-forge/CLAUDE.md]
related: [L0050, L0051, L0061]
observed: 2026-09-30
---

## 人話

**問題**:接手時常看到「這個方法試過了,沒用」或「這個功能已經做好了」。這些說法有時是當時量錯,有時程式其實從來沒跑過。全盤照收,會放棄掉其實可行的路,或以為做好了其實沒有。

**做法**:對會影響方向的結論,先寫一個很小的測試重驗一次再接受;判斷進度看實際的執行紀錄和數字,不要看程式有沒有寫、不要靠之前的對話印象。

## 現象

- 「attachment 跑到一半改無效」:實際是量測假象(L0050 推翻 L0051)。
- parcel-forge D016「PhysX 從不寫回 USD」:被 D018 更正為「看路徑」。
- 交付包缺口:`TASK_INTERN.md` 說 `--movebox` 已寫好,實際不存在;CHECKLIST 三個 ✅ 屬於一個不在包裡的較新 `wrap_sim.py`;`selfcheck` 找的 meta 檔名跟包裡的不同。

## 根因

前人的結論是在特定條件下量的(或沒量);文件跟程式不同步。

## 做法

- 影響決策的「無效 / 不可能」:寫最小探針(單一變因 + 對照組)重驗,例 `probe_detach.py` 7 種做法逐一試。
- 進度以 `STATE.md` / `RUNS.csv` / runs 目錄裡的證據為準;沒跑過的程式寫「未執行」。
- 開工前先列交付包缺口(REPORT_20260930 §4 的格式)。
- 推翻時照記憶的寫入規程開新條目並標 superseded。

## 證據

REPORT_20260930 §1 結論 2(原作者 09-25 結論是量測假象)、§4 交付包缺口;parcel-forge D018;parcel-forge CLAUDE.md「do not infer that code which exists has ever been executed」。
