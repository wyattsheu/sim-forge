---
id: L0079
title: 續跑前用失敗快照驗證完整重試轉移,不能只驗環境與輸入
status: active
severity: high
confidence: measured
domains: [pipeline, workflow, measure]
tags: [retry, checkpoint, state machine, successor, preflight, native transition]
triggers: [從失敗的診斷或生成工作續跑, 環境預檢全過卻仍反覆失敗, 重試時看到磁碟與記憶體狀態不一致]
versions: DiagGen 3d2d377 with bundled Genesis 1.2.0
scope: [sims/diaggen_genesis, tools/diaggen]
evidence: [tools/diaggen_support/diagnostic_retry_reset.patch, sims/diaggen_genesis/tests/test_diagnostic_retry_reset.py, tools/diaggen_support/check_diagnostic_retry.py, tools/diaggen/outputs/preflight/diagnostic_retry_reset_baseline_20261022/manifest.json]
related: [L0061, L0065, L0066, L0068, L0077]
supersedes: []
superseded_by:
observed: 2026-10-22
---

## 人話

**問題**:依賴套件、檔案與模擬小測試都正常，不代表失敗工作能重新啟動。重試可能先在記憶體轉換狀態，轉換本身又違反下一步的驗證規則；直接重排只會重現同一個錯誤。

**做法**:保存失敗快照，先在副本上走與正式重試相同的原生轉移和驗證。修復後再用真實工作確認已進入下一階段；保留舊證據，不能靠刪除失敗紀錄或放寬驗證來通過。

## 現象

2026-10-21 的環境預檢 71 項通過；晚間整合測試 190 項通過。但球鞋、樹懶夜間續跑仍失敗。球鞋 fresh child attach 回報缺少 v2 診斷計畫，磁碟 state 卻保留完整計畫。樹懶另曾被同一 planned region 只能擁有一個 episode 的規則擋住。

2026-10-22 對兩個正式失敗快照做唯讀重現：重試轉移保留了 3／10 筆 grounding measurement，fresh validator 只接受最多一筆。修復前兩者皆失敗；修復後兩者皆通過 fresh successor 驗證。失敗快照雜湊記錄於本機 manifest，測試操作 deepcopy，正式 state 位元組不變。

## 根因

原生 MCP attach 先呼叫 `archive_and_reset_diagnostic_execution_attempt`，清空執行中的計畫、episode 與事件，卻把逐次量測歷史歸類為可保留輸入。接著 `require_v2_session_state(..., allow_fresh_unplanned=True)` 認為這個沒有計畫、帶多筆歷史量測的候選狀態不是 fresh，立即拒絕；錯誤發生在 save 前，因此磁碟仍保有舊計畫。這是轉移契約缺口，與 GPU 顯存或檔案遺失無關。

## 做法

把逐次量測歷史與所屬 execution 一起歸檔，再從新 execution 清空；保留 immutable grounding context。維持原本 fresh、owner、計畫不可改寫與 episode 唯一性驗證。

重排前，用 `check_diagnostic_retry.py` 在 deepcopy 上執行與 MCP 相同的 typed recovery metadata、archive/reset 和 fresh schema 檢查。只檢查舊 owner 已關閉、上游檔案存在，不足以證明下一次 attach 可成功。

## 驗證方法

`test_diagnostic_retry_reset.py` 以已驗證的修復前／後來源載入暫存模組；16 個測試包含兩個固定正式快照、歸檔完整性、舊 evidence 不可重用、錯誤 owner／事件、不可改寫計畫及 fresh schema 負向對照。執行中的正式工作不能直接當可變測試 fixture，先保存不可變的本機副本；含 session 私有資料的原始 state 不發布。

## 試過但無效

等待 owner lease 到期、只建立新 child 或只提高顯存，都不會修復這個確定性的狀態轉移錯誤。只驗證函式可匯入或批次 admission 通過，也沒有走到出錯的 successor 轉移。

## 證據

`tools/diaggen_support/diagnostic_retry_reset.{patch,json}`；`tools/diaggen_support/check_diagnostic_retry.py`；`sims/diaggen_genesis/tests/test_diagnostic_retry_reset.py`；本機 `tools/diaggen/outputs/preflight/diagnostic_retry_reset_baseline_20261022/{manifest,sneaker,sloth}.json`。16 項測試證明的是轉移修復與驗證契約，不能據此宣稱兩個物件已完成完整診斷或匯出。
