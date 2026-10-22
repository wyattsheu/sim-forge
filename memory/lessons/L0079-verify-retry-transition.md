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

2026-10-22 補充：即使 archive/reset 與 fresh schema 已通過，也必須把磁碟副作用納入下一步驗證。球鞋與樹懶的 successor 清空材質登記後，上一輪的 `material_audit_authoritative/revision_0000/cleaned_source_image.png` 仍存在；實際登記函式拒絕同名快照，因此 `define_episode` 又失敗。`sims/diaggen_genesis/analysis/reproduce_retry_artifacts.py` 對保存狀態與臨時目錄重現兩次相同錯誤；以獨立 attempt 子目錄的候選函式測試，五個來源檔均可登記且雜湊相符，舊快照保留。這只證明 registration boundary 的局部改善，尚未部署，也未證明完整 episode／probe／terminal 成功；後續驗收必須包含其他舊 artifacts 不被覆寫。證據：`sims/diaggen_genesis/analysis/retry_artifact_reproduction.json`，本機原始快照 `tools/diaggen/outputs/preflight/stall_audit_20261022/`。

同日後續正式恢復改用官方獨立 diagnostics snapshot 入口，保留六個成功上游階段與舊失敗 run。又發現 client／SKILL 邊界必須一併驗證：原生 `revise_diagnostic_probe_target` 已自動 compile 並記錄 preview，文件卻要求再次 preview；同一 compile 出現兩份預覽時，下一步 reflection 正確拒絕。`test_probe_preview_contract.py` 執行實際原生函式本體，重現舊順序失敗，驗證直接使用 revise 回傳的唯一 preview 可通過該邊界；`probe_preview_recovery.patch` 只修正 SKILL，保留原生唯一性與重疊檢查。另以 `diagnostic_credentials.js` 原樣保留 native-issued token／handle，正規化 MCP 的 result／content 封裝並保存原生識別碼；避免模型抄錯一個字元、漏讀回應後猜 ID，或把私有工具回應中的 session ID 誤當成必須中止的事件。

完整正向證據：`genesis_sloth_20261022_clean_diagnostics3` 於 2026-10-22 16:18:53–16:49:42 完成診斷快照後綴，兩個 qualifying probes 的 selected-part fraction 為 0.9166666666666666／1.0，兩區皆 `coverage_complete`、兩 session 關閉、原生 strict accept、貼圖與匯出及完成驗證全部成功。9 個 stage 均成功、16 個匯出產物、4912 vertices／21133 tets／五材料標籤，歸檔在 `sims/diaggen_genesis/runs/genesis_sloth_20261022_clean_diagnostics3/`；公開核對見 `sims/diaggen_genesis/analysis/sloth_completed_validation.json`。這才是完整成功證據；300／301／302 項 CPU 測試的通過數不能代替正式產物。

## 證據

`tools/diaggen_support/diagnostic_retry_reset.{patch,json}`；`tools/diaggen_support/check_diagnostic_retry.py`；`sims/diaggen_genesis/tests/test_diagnostic_retry_reset.py`；本機 `tools/diaggen/outputs/preflight/diagnostic_retry_reset_baseline_20261022/{manifest,sneaker,sloth}.json`。16 項測試證明的是轉移修復與驗證契約，不能據此宣稱兩個物件已完成完整診斷或匯出。

- 區分轉送器的本地參數拒絕、原生認證錯誤與自動審查拒絕：本地尚未送出的呼叫若只是多填身份欄位，應列出欄位名稱並依原契約移除；不能誤判為巢狀業務欄位被禁用、重新 attach 或繞過真正的審查。

- 修復 revision 要同時核對 global stage 成功與 owning-stage terminal 的版本：原生已提供 reset_active_revision_stage_runtime_terminals 時，先證明衝突紀錄逐欄等於 immutable base 且早於新 revision，才呼叫既有恢復函式。只認 success 的外部佇列也須辨識有 copied-prefix／來源與路徑證明的原生 reused；恢復後由 owning stage 重驗現有產物及補交 terminal，不得重做或捏造成功。
