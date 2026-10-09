---
id: L0064
title: 抽不到資料就判 SKIP 並寫原因,不能當 PASS;文件數字對不上時兩個都列出來
status: active
severity: medium
confidence: measured
domains: [measure, pipeline]
tags: [SKIP, run_checks.py, RUNS.csv, inconsistency, source of truth]
triggers: [寫自動判讀或驗收腳本, 整理報告時發現兩份文件數字不同]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/tests/README.md, sims/fr3_bubblewrap_pack_20261007/work/EXPERIMENTS.md 開頭與 ⚠ 不一致 各條]
related: [L0061, L0068]
observed: 2026-10-02
---

## 人話

**問題**:自動檢查如果「找不到資料就算通過」,壞掉的結果會被當成好的;不同文件寫的數字對不上時,隨便挑一個也會傳錯。

**做法**:找不到資料就標「跳過」並寫原因;數字以紀錄總表為準,兩份文件不一致時兩個都寫出來,不要自己挑。

## 現象

- 舊 log 沒有 SUMMARY 段,某些項目抽不到。
- `HOW_TO_VIEW.md` 寫「基準四折疊層總厚 43 mm」,RUNS.csv 是 54.26 / 60.18 / 47.96。

## 根因

判讀程式對缺資料的預設行為;報告各自手抄數字。

## 做法

- `run_checks.py`:每項 PASS / WARN / FAIL / SKIP / INFO,**抽不到 = SKIP 並寫原因**,`vol_missing` 列出。
- 數字以 `RUNS.csv`(`collect_runs.py` 從 log 抽)為準;不一致標 **⚠ 不一致** 並列兩個數字。
- 所有門檻常數集中在 `run_checks.py` 開頭並註明來源(使用者口徑 / CHECKLIST / 報告)。

## 證據

tests/README「抽不到資料 = SKIP 並寫原因,不當 PASS」;EXPERIMENTS 開頭規則與各條 ⚠。
