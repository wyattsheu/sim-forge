# 15:28 起的正式恢復驗證

使用者要求先跑通一件新物件，遇到錯誤立即分析再繼續。這次的實際目標是樹懶的新 run `genesis_sloth_20261022_clean_diagnostics1` 完成原生診斷、貼圖與最終匯出驗收；啟動和測試通過均不當作完成。

## 新查明：USB Hub 最近一次中斷是憑證抄寫錯誤

對最新成功 attach 的診斷 child 做唯讀紀錄比對，共 50 個明文帶入 owner token 的呼叫。前 49 個使用相同 token；最後一個（2026-10-22 07:12:26.717 UTC）長度仍為 43 字元，但與前一個差 1 字元。接著原生 MCP 回報 `diagnostic owner lease token does not match`。比對沒有輸出或發布 token、attachment ID、live handle 或原始 session 紀錄。

因此，這次不能再推測成「MCP 自己遺失了 token」。模型重抄不透明字串的錯誤，接上原生正確的拒絕與 65 分鐘 lease 保護，造成再次長等。更早一次 `no diagnostic attachment is current` 的來源仍未證實，兩個事件不混為一談。

## 已部署到新 worker 的修正

- `tools/diaggen_support/diagnostic_credentials.js` 只轉送單次原生 MCP 呼叫。由 diagnostic child 在自己的工具 store 保留 attach 回傳的完整憑證與 create 回傳的 handle，後續直接取值傳送；拒絕模型手填這些欄位。沒有自動規劃、探測、重試、關閉或決策，parent 不接觸該 store。
- `run_one.sh` 依 fresh、resume、diagnostics_snapshot 分別產生正確的 metadata 指令，fresh 和 snapshot 不再被指示讀不存在的 resume metadata。
- 新 worker 若 diagnostic child 沒有合法 terminal 就退出，會立即保留錯誤結束此次 orchestration，由互動監督流程分析；不再自行反覆生成子程序、逐分鐘消耗模型用量等鎖。
- 憑證來源／使用說明納入 runtime fingerprint；launcher 差異與修改前／後 SHA-256 記錄於 `queue_verified_diagnostics.patch` 和同名 JSON。既有 worker 保留原 shell inode 與舊 prompt；未對其熱改。

## 快照衝突的正式處理

本次使用官方公開的 `--diagnostics_revision_snapshot_dir --diagnostics-reroute-and-export --require-new-run-root` 入口，從樹懶完整的六階段成功前綴建立獨立 run。原生 initializer 會在新 run 清除複製而來的診斷目錄，再產生全新診斷狀態；舊 run、其 business halt、既有證據與失敗歸檔全部保留。

這是官方既有的恢復入口。先前「attempt 子目錄」的候選 native 修補仍未部署；原生同 run transport retry 的快照衝突也未宣稱修好。本次避開該路徑，先驗證乾淨的官方診斷流程。

## 驗證與實際啟動

- 12 項 JS 憑證傳遞負向／正向測試通過，包含連續 50 次取用精確 token、不同 child store 隔離、錯誤身份、手填憑證、工具缺失、terminal 後停止。
- 完整 CPU／回歸收集 **290 項通過，0 fail、0 error、0 skip**；包含實際執行 shell 的模式與 metadata 檢查。
- 新 runtime certificate **82 項通過**。78 項原生／環境證據在 native source、輸入、套件 inventory 與二進位指紋完全相同後沿用；重跑三項 orchestration 收集檢查，新增樹懶 snapshot admission。
- JS 測試使用假的 MCP endpoint，故不算正式 MCP 驗證；正式工作仍須實際成功。
- **15:28:04（Asia/Taipei）由既有背景 watcher 啟動樹懶，GPU 0。** 實際通過 runtime、EXR、六視角顯示檢查，完成 native snapshot initializer；新 ledger 中六個上游 stage 成功，診斷尚待執行。

本機可稽核證據位於 `tools/diaggen/outputs/preflight/verified_diagnostics_20261022/`，包含舊 launcher、舊 certificate、完整測試紀錄與來源差異。原始私人 ledger 不發布。接下來的實際階段與產物以 [動態進度](../progress/) 為準。
