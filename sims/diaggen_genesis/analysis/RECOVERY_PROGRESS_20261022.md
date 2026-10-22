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


## 17:00 USB 證據參數誤判與 17:14 批次恢復

USB `clean_diagnostics2` 的 cable 探測、放開與沉降已完成，session 也已關閉，但子代理在 `client.call("record_diagnostic_evidence", ...)` 內又手填了 `run_root` 與 `agent_invocation_id`。轉送器正確在發送前拒絕；後續子代理誤把錯誤歸因於普通的 `evidence.next_action`，因此沒有提交必要證據。這次不是 MCP 認證失敗，也不是自動審查拒絕，沒有放寬原生 evidence schema。

新增錯誤訊息會列出確切的冗餘欄位名稱，明示尚未送出 native request，要求移除頂層身份欄位、仍由同一 client 轉送；普通的巢狀 evidence 不變。使用真實 JS 來源的回歸測試重現拒絕，再證明 `{evidence}` 原封不動轉送成功。完整 **303 項 CPU 測試通過，0 fail／error／skip**；85 項憑證通過。原生程式、輸入、環境與 binary inventory 完全未變，只有 JS 錯誤訊息及說明更新。舊 child／session 由原生 shutdown 清理，USB `genesis_usb_hub_20261022_clean_diagnostics3` 重新由原始成功六階段快照排隊。

上一批全部進入 terminal 後，watcher 於 17:00 正常退出，後來新排的工作尚未被 claim。17:14 已重新啟動原 tmux watcher；棒球帽、料理夾、球鞋均已真正啟動，醬料盒及 USB 等待本批次 GPU 名額與顯存。完成數仍是電捲棒、樹懶兩件。

Dragon 的原始 cleanup 子代理紀錄也已找到：兩次真實 built-in imagegen 呼叫、完整 prompt、工具回報的原始圖路徑，且兩張候選逐 byte 雜湊均與 generator 原檔一致。這只恢復生成來源，沒有偽造驗證或描述。已將私人來源證據放入歷史並連結到新的 same-run resume metadata；owning cleanup child 仍須重看原圖與兩張候選，確認完整配對資料，依原規則選擇或保留真正的 stage halt，不得生成第三張。


## 17:25 顯卡共用名額

依既有「有空就塞」要求，外部排程設定允許每張 GPU 最多三件、整批仍最多四件，不改 native、模型、精度或 24 GiB 門檻。三件的最低合計 73728 MiB 才准進場，73727 MiB 拒絕；已有三件時即使大量空閒也拒絕第四件。實際 admission 函式與當下 GPU 快照均已驗證。當時 GPU 0 因 OmniPart 載入後只剩 62155 MiB，第三件仍須等顯存，未假稱已啟動。

啟動憑證增加為 **86 項通過**。只有 `batch_plan.json` 設定改變，所有程式、輸入、環境與 binary inventory 均未改；303 項 CPU 測試證據來自前一輪相同程式，這次另跑上述排程邊界與真實快照核對。這是排程記帳，無法保留 CUDA 顯存。


## USB Hub 於 17:50:18 完整成功

`genesis_usb_hub_20261022_clean_diagnostics3` 於 17:26:00 啟動，17:50:18 完整成功，共 **24 分 18 秒**。這是重用六個成功上游階段的 diagnostics-snapshot 後綴時間，不是原圖完整生成耗時。

- 九階段成功；兩個區域均 `coverage_complete`，兩次合格探測的 selected-part fraction 均為 1.0。原生 strict accept，session 正常關閉，parent 套用 accept，再完成貼圖及匯出。
- completion validator 與額外唯讀驗收皆通過，最終 state SHA-256 相同。1417 個頂點、5174 個四面體，材料標籤 0／1／2，一個 face-connected component，16 個 canonical 檔案。物理／視覺綁定與貼圖驗證均有效。
- 兩段 H.264 影片均為 2304×768、10 fps，長度 2.4 秒及 2.5 秒。完整成品與 670 檔 trace 歸檔於 `sims/diaggen_genesis/runs/genesis_usb_hub_20261022_clean_diagnostics3/`；核心成品在其中 `asset/`。
- [公開驗收](usb_hub_completed_validation.json) 與 [成功這次模型用量](usb_hub_token_usage.json) 不含先前失敗嘗試、互動除錯、imagegen 額外費用或 GPU 計算費用。

現在已完成三件。棒球帽正在 Genesis 診斷；球鞋與料理夾依原生 revise／transition 建立 `revision_0001`，分別處理 shell 邊界、U 形回彎的分割修復，沒有修改覆蓋或探測門檻。醬料盒與 Dragon 繼續由同一 tmux queue 安排。水豚的 int32 限制仍未修復；隔離的分批解碼候選未通過比較，沒有部署。


## 棒球帽於 18:05:25 完整成功

`genesis_baseball_cap_20261022_fresh3` 於 17:14:36 從原圖啟動，18:05:25 全流程成功，**50 分 49 秒**。這次包含新生成的 cleanup、SAM3、OmniPart、材料推論與網格，後續兩個區域完整覆蓋、原生 strict accept、貼圖及匯出；不是上游快照後綴。

completion validator 與獨立唯讀驗收都通過：6405 個頂點、22287 個四面體、材料標籤 0／1／2、一個 face-connected component、16 個 canonical 檔案；空心體積拓撲，目標最大尺寸 0.25 m。兩段 H.264 診斷影片均為 2304×768、10 fps、3.6 秒。完整成品在 `sims/diaggen_genesis/runs/genesis_baseball_cap_20261022_fresh3/asset/`。

見 [棒球帽驗收](baseball_cap_completed_validation.json) 與 [這次完整嘗試的模型用量](baseball_cap_token_usage.json)。[USB 完整取景預覽](media/usb_hub_full_asset_preview.png)／[棒球帽完整取景預覽](media/baseball_cap_full_asset_preview_light.png) 由既有 GLB 與貼圖另行渲染；軟體 renderer、留白邊界與來源雜湊均有 JSON 證明。原生 QA 截圖、GLB、貼圖及物理資產均未修改，這些額外預覽不是新的物理驗收。

## 修復版本的既有提交紀錄與官方恢復函式

料理夾進入 `revision_0001` 後，分割及 OmniPart 成功生成，獨立 submit 卻被 `stage ... already terminalized` 拒絕。唯讀比對證實四筆衝突 terminal 都逐欄等於 immutable revision_0000 snapshot，時間也早於 revision_0001 建立時間。官方已有 `reset_active_revision_stage_runtime_terminals`，但目前 reroute 沒有自動呼叫；本輪 **沒有修改 native Python**。

新增 `tools/diaggen_support/prepare_repair_stage_runtime.py` 只保護並呼叫這一個既有函式：要求真正的相鄰修復版本、已關閉的診斷 owner、未 accepted/exported，且所有受影響 terminal 都與 base 一致並早於新版本。拒絕刪除新版本 terminal、halt、活躍診斷或已完成資產。實際已在停止的料理夾 worker 上使用；四筆舊提交恢復，base snapshot SHA-256 維持 `28df487a7fe824f43b9eb10f341334f27c9c703584afad712dc3fea6c2c3c1c4`，第二版已生成產物與 stage 紀錄均保留。見 [恢復驗證](native_repair_stage_runtime_recovery.json)。

另一個外部佇列問題是原先只認 `success`，官方複用階段實際標成 `reused`。現在只在 active repair、相鄰 base、原生 route 的 copied prefix、兩份 reused_from_revision 與 active-revision 產物位置皆相符時接受。也支援官方明確 opt-in 的 reroute-and-export snapshot 修復續跑，仍拒絕 stage-only snapshot；未修改原生狀態來迎合佇列。

新 parent 在每次建立修復版本後、委派 replacement stage 前，明確執行上述原生函式保護入口。料理夾已重新排隊：先由 segmentation／OmniPart owning agents 重驗現有輸出、保留「U 回彎仍與兩臂合併」的限制並補正式 submit 或真正需要的 halt，再處理後續材料與網格；不重做成功生成，也不假稱三區目標已達成。

最後完整收集 **320 項 CPU 測試通過，0 fail／error／skip**，其中 11 項實際 native terminal recovery 測試、6 項 copied-prefix／snapshot admission 控制。啟動憑證 **90 項通過**，納入 USB／棒球帽的實際成功驗收與料理夾的恢復、admission 證據。已比對 native code、輸入、環境與 binary inventory 均未變；HOLD 已解除。舊活躍 worker 保留原 prompt，新的 worker 才會先準備 repair terminal。


## 18:55：原生 final-revise 匯出政策與醬料盒驗收

醬料盒完成 strict accept、貼圖與 16 個匯出檔，獨立驗證通過；58,382 個四面體超過建議預算，沿用原生 warning，沒有自行加上硬性上限。

原外部驗收器無條件要求 accept，錯拒官方允許的 diagnostics snapshot 最後一輪 revise 匯出。現在直接使用原生 `_is_final_revise_export_policy` 驗證完整政策；球鞋 accepted_revision 保持 null、exported revision 為 revision_0001、metadata 保持 exported_unaccepted。只恢復外部匯出完成記帳，不寫入物理 accept。原 stage submit 錯誤與失敗驗收紀錄保留；當前 revision 沒有新的 live episode，舊影片保留在 trace。

333 項 CPU／回歸測試全通過，0 fail/error/skip。92 項啟動檢查包含未變更 runtime 的既有硬體證據、最新測試與兩件實際匯出驗證；原生程式、環境、模型與診斷門檻未修改。料理夾已正確續跑到原生 revision budget exhausted，不能把此 halt 直接改為成功或清除預算。


## 19:58：監看誤認官方 profiler，修正後自動續跑 Dragon

Dragon 19:10 的診斷 bind 回傳 Error，原生 server 後續清理完成並留下未形成業務推薦的可恢復終端。外部監看將只負責 profiling 的官方 detached sampler 視為殘留運算，造成約 48 分鐘未接續。現在嚴格核對 sampler 的 module/argv、run-root、interpreter、cwd 和 lock PID 後排除此程序，未殺任何程序、未改原生診斷或修正預算。

原生唯讀 successor admission 通過，353 項測試及 95 項啟動檢查通過。排程於 19:58:21 實際沿原 run/GPU 接續，新的 Codex thread 已啟動，前六個成功階段保留。Dragon 仍未完成；其餘五件 accept、一件 exported_unaccepted 與兩件既有 blocker 均保留原結果。
