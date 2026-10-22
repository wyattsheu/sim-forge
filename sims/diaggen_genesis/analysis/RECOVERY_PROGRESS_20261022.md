# 15:28 起的正式恢復驗證

**樹懶已於 16:49:42 完整成功。** 最終 run 為 `genesis_sloth_20261022_clean_diagnostics3`，九階段紀錄均成功、原生 strict accept、貼圖／匯出與完成驗收通過。下列保留每次失敗、修正與驗證的紀錄；前兩輪不當作成功。

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

## 15:37 中斷與 15:42:40 立即恢復

第一輪成功跨過舊快照衝突：完成材質快照登記、建立 episode、建立並綁定 Genesis live session。但 child 把自己收到的原生回應中的 session／attachment 識別碼誤判成須立即停止的洩露，因此自行結束，沒有產生 business terminal。原生 MCP 在 worker 結束時以 shutdown recovery 清理 session；沒有 token mismatch。

這是新增指令過度限制正常私有工具回應造成的問題。已釐清：原生回應在該 child 私有上下文中包含 session 識別碼是正常現象，不應視為認證失敗；仍由工具 store 取值，禁止手抄 token／handle 到新請求或公開報告。

外部 queue 新增明確的 `diagnostics-snapshot-origin` 恢復操作：只針對先前已核准的快照來源，要求目前失敗 worker 已退出、兩份 ownership ledger 的 session／attachment 均關閉、來源狀態雜湊不變，且目前沒有 accepted revision。操作保留兩個失敗 run，重新通過原生快照預檢；不改寫失敗或手動解除鎖。三項新增回歸測試驗證保留證據、拒絕尚未清理的 owner、拒絕來源變動／已接受結果。

**293 項 CPU／回歸測試全數通過，0 fail／error／skip；啟動檢查為 83 項通過。15:42:40 已由背景 watcher 在 GPU 0 啟動 `genesis_sloth_20261022_clean_diagnostics2`。** 前六個成功階段繼續保留；完成與否仍以原生診斷、貼圖、匯出與驗收結果為準。第二輪本機證據位於上述 audit 的 `round2/`。

## 第三輪：修正原生 revise 使用契約與回應解析

第二輪完成建立、綁定、reset、settling simulate 與日誌檢查；第一個互動 probe 在 dispatch 前被原生固定區／探測區正體積重疊檢查拒絕，未消耗 probe 次數。child 依規則做了 bounded relative edit，但又呼叫了一次 preview，導致同一 compile 有兩個 preview，原生 reflection 的「恰好一份」驗證因而失敗。

原生 `revise_diagnostic_probe_target` 本身已呼叫 renderer 並記錄新 compile 的 preview；官方 micro-skill 卻指示 revise 後 recompile／preview。新補丁 `probe_preview_recovery` **只修正文檔以符合既有函式**：直接保留 revise 回傳的新 compile／preview ID，使用唯讀 image viewer 查看其既有 PNG，不能再呼叫 preview。原生 Python、reflection、overlap 與 probe 次數上限均保留。

另一個實際問題是 child 自寫 formatter 只解析 `.content`，漏讀另一種 `.result` MCP envelope，後續自行拼接未取回的識別碼。自動審查正確拒絕該 reflection 提交，該寫入沒有執行，也沒有繞過。現在 forwarder 將原生兩種回應保留並正規化為 `.content`，由 `client.show(result)` 顯示原生文字／圖片；`client.lastMetadata(tool_name)` 可從該 child store 取回**原生實際回傳**的 compile、preview 與 PNG 路徑，不需另一個 runtime call，也不產生假識別碼。

新增回歸測試執行真正的 native revise／preview／reflection 函式本體，重現「額外 preview → 唯一性失敗」，並驗證「使用 revise 回傳的單一 preview → 通過該反思登記邊界」。這是 bookkeeping 契約測試，不冒充物理探測或完整 accept。

完整收集初次有 10 項失敗，原因是安裝測試的固定補丁清單仍只列七份；加入已核對的第八份補丁後，重跑完整收集，**300 項通過，0 fail／error／skip；啟動憑證 84 項通過**。第一次失敗與後續通過的報告都保留在本機 audit 的 `round3/`。第三個乾淨 run 為 `genesis_sloth_20261022_clean_diagnostics3`，仍由原始六階段成功快照啟動，尚待正式結果。

## 正式成功與獨立驗收

第三輪於 **16:18:53–16:49:42** 完成（30 分 49 秒）。這是保留六個成功上游階段後的診斷、貼圖、匯出耗時，不是從原始圖片重新生成全部幾何的時間。

- 兩個區域 `raised_arm_flex`、`face_panel_edge` 均完成 qualifying probe 與 `coverage_complete` 結算，selected-part fraction 分別為 0.9166666666666666／1.0；兩 session 正常關閉。
- 原生嚴格 `accept`，parent 正式轉移至貼圖，再執行 final export；accepted／exported revision 都是 `revision_0000`。
- 九個 stage 成功，16 個匯出產物驗證通過。獨立唯讀 validator 再次通過；包含 4912 vertices、21133 tets、五個材料標籤、單一 face-connected component，以及有效的 visual／physics 綁定。
- 兩段 H.264 triptych 影片皆為 2304×768、10 fps，分別 55 frames／5.5 秒與 28 frames／2.8 秒。
- 完整歸檔位於 `sims/diaggen_genesis/runs/genesis_sloth_20261022_clean_diagnostics3/`。核心成品在 `tools/diaggen/outputs/run_pipeline/genesis_sloth_20261022_clean_diagnostics3/`，包括 `.mesh`、異質材料 `.npz`、貼圖 `.glb` 與 `albedo.png`。

公開驗收與產物雜湊見 [sloth_completed_validation.json](sloth_completed_validation.json)。[第一段影片](../progress/media/sloth_episode_001_triptych_video.mp4)／[第二段影片](../progress/media/sloth_episode_002_triptych_video.mp4) 由背景發布器同步。外觀仍較粗糙，未宣稱與實物量測校準一致。

## 接續工作與授權範圍釐清

USB 的一次 attach 實際未成立，child 卻忽略回應後輸出成功訊息，之後才被本機憑證 guard 擋住。forwarder 現在會對 native attach error 直接拋出原始錯誤，防止這種假成功；既有 credential store 保護保留。該修改的 301 項完整回歸通過，已另建 USB 的乾淨 run。

醬料盒一次 bounded runtime-log 讀取遭自動審核拒絕，理由是直接供應 lease token。但實際 caller 使用 `client.call`，沒有手填 authentication 欄位；原生 MCP 簽名又要求該欄位。龍的 cleanup halt 也被誤套為 diagnostics 的 business-halt 禁令。這些拒絕都沒有被間接執行；已保存紀錄並整理 [原生授權與 scope 證據](NATIVE_AUTHORIZATION_SCOPE.md)，釐清 forwarder 必須傳送保留值、diagnostics 禁令與合法 non-diagnostic stage terminal 的不同範圍。

目前完整 CPU／回歸為 **302 項通過，0 fail／error／skip**。啟動憑證 **85 項通過**，新增樹懶正式成功產物核對；沿用的原生／環境證據都經來源、輸入與 binary inventory 比對，不能把這個數量當作其他物件成功。

修正已接續安排球鞋乾淨診斷快照、醬料盒新診斷、料理夾同 run 候選重驗，以及棒球帽 fresh run。每件是否完成仍依自己的 native terminal、產物與驗收判定；水豚的 spconv 大張量限制與龍的候選原始 metadata 缺口仍須獨立處理。
