# DiagGen / Genesis 實驗

[最新進度](progress/) · [卡住原因與改善驗證](analysis/STALL_AUDIT_20261022.md) · [執行環境預檢](preflight/latest.json) · [官方圖片總覽](demo_inputs_preview.jpg) · [圖片來源紀錄](demo_image_sources.json) · [排程清單](batch_plan.json)

使用 DiagGen 內附的 **Genesis 1.2.0**，開啟 Genesis 診斷，排程 9 張圖片的完整生成流程。

**2026-10-22 18:55：5／9 件通過 Genesis strict accept 並完成匯出：電捲棒、樹懶、USB Hub、棒球帽、醬料盒。** 另有球鞋完成原生 snapshot 的 `exported_unaccepted` 匯出，診斷仍為 revise，不能算物理通過。龍仍執行中；料理夾在原生修正次數上限停止，水豚受 spconv int32 限制阻擋。即時狀態見 [progress/](progress/)，驗收見 [醬料盒](analysis/sauce_keeper_completed_validation.json)、[球鞋（未通過）](analysis/sneaker_completed_validation.json)、[棒球帽](analysis/baseball_cap_completed_validation.json)、[USB](analysis/usb_hub_completed_validation.json) 與 [樹懶](analysis/sloth_completed_validation.json)。

- 生成與診斷：**GPT-6 Luna，Max reasoning**；各階段子代理沿用相同設定。
- 論文對應設定為 GPT-5.6 Luna、Max；本次依要求改用同系列新版，並保留差異紀錄。
- 8 張官方 demo 圖片擷取自影片的輸入照片區，解析度受影片限制，未放大；另外 1 張水豚玩偶照片由使用者提供。總覽圖片只包含 8 張官方擷取圖。
- 模型權重、第三方環境與完整工作檔保留在伺服器。此目錄的程式負責等待、整理和進度發布；實際 pipeline 由原專案的 Codex skill 執行。

## 復現原則與差異

依使用者 2026-10-22 的要求，本次以忠實復現論文與官方技能流程為準，不自行加入新的生成、分割、物理或診斷方法。現況須稱為 **官方 commit `3d2d377` 加本機執行修補的復現**，不能稱為完全未修改的原版。模型從論文 GPT-5.6 Luna Max 改為 GPT-6 Luna Max，是使用者先前允許的版本差異。

八份原生補丁涉及七個官方檔案，差異如下：

| 補丁 | 實際影響 |
| --- | --- |
| `diagnostic_history_settlement` | 合法關閉的歷史 session 可在 owner 失效後重新驗證；不允許舊 owner 建立新 close。 |
| `diagnostic_retry_reset` | 依原有 archive/reset 流程歸檔並清空逐次量測歷史，讓新的診斷執行符合原 fresh 驗證。 |
| `anchor_preview_recovery`、`anchor_preview_index` | 修正兩份 SKILL 的重編譯指令，使用原 revise 工具已回傳的修改結果；不改錨點演算法或試驗上限。 |
| `probe_preview_recovery` | 修正 probe-targeting SKILL：revise 已自動編譯並記錄唯一預覽，應讀取回傳的 PNG 與識別碼；再次 preview 會被原有唯一預覽驗證拒絕。沒有修改原生 Python、重疊檢查或 reflection 驗收。 |
| `snapshot_export_inputs` | 換 output tag 時複製既有四張材質檢查 PNG 並記錄來源，沒有重算物理參數。四圖完整性是本機工程要求；低階原生匯出 API 將其列為 optional，不能說是論文必要條件。 |
| `strict_material_coverage` | 正常網格路徑缺少材料標籤從 warning 改成 failure，符合官方 SKILL 的 exact 要求，但確實改動了原程式的接受條件。 |
| `segmentation_raw_prediction_guard` | 拒絕沒有原始 SAM3 預測、只剩 foreground-fill 的結果；符合官方 SKILL 的原始預測要求，但比原程式的實作更嚴格，須列為差異。 |

另有依賴修復、私有 Xvfb、缺少的 MP4 編碼入口、同 GPU 顯存等待、單次原生函式 CLI、歸檔及 GitHub 發布。水豚使用官方 OmniPart app 已提供的 Native 後端選項；不應將後端小型探針通過宣稱為完整模型錯誤已解決。

本次忠實性核對另發現一項**尚待校正的外部限制**：`tools/diaggen_support/validate_completed_export.py` 無條件以 exact 材料覆蓋驗證最終網格；官方 mesh-processing SKILL 則允許經過原生最大連通元件處理後使用 subset 覆蓋。這個外加檢查可能拒絕官方合法結果，應依可驗證的原生 component-resolution 紀錄回到官方規則，不能把它當作論文標準。此核對沒有修改執行中程式或現有產物。

## 2026-10-22：依可用顯存共用顯卡

使用者指的是本機顯卡，沒有要求搬到其他伺服器。此前「每張卡只能掛一件 DiagGen 工作」使等待診斷鎖的工作占住排程名額，即使同卡仍有大量空餘顯存，也不能啟動下一件。

外部佇列現在允許**每張 GPU 最多兩件、全機最多四件**，不要求 GPU 使用率為零。首件仍須符合原本至少 24 GiB 的可用顯存門檻；同卡再加入一件時，以既有與新工作門檻的總和作為額外空間檢查，通常至少需要 48 GiB 當下可用顯存。大型工作的較高門檻照算，claim 在鎖內重新查詢顯存，尚未載入模型的工作也占一份額度。這只是保守排程記帳，沒有實際預約 CUDA 記憶體，也未宣稱量到完整模型峰值。

球鞋與 USB Hub 保留原工作、原 GPU UUID 和診斷紀錄；棒球帽、料理夾兩件 fresh 工作優先利用空間。各工作仍在原 GPU 上執行 OmniPart 前的即時顯存檢查。沒有修改七份原生補丁、模型、物理參數或診斷接受條件。

部署前保存來源雜湊、在副本測試並 dry-run 補丁，再於 HOLD 下原子更新外部 queue。`tools/diaggen_support/queue_gpu_sharing.patch` 與同名 JSON 記錄外部 queue 差異；續跑測試在暫存副本重放已核對的完整補丁鏈。**267 項實際 CPU／回歸測試全部通過，0 fail、0 error、0 skip**，包含共用顯存、並行 claim、未綁定 worker、門檻邊界、HOLD 與原 GPU 綁定檢查。

最新啟動憑證為 **81 項必要檢查通過**：沿用 77 項對應原生來源、輸入、環境及二進位指紋未變的證據，重跑三項測試收集檢查，另於真實排程及 GPU 快照的副本確認下一件棒球帽能進入 GPU 0。副本檢查不當作實際啟動；正式工作狀態以 [即時進度](progress/) 為準。

**13:52:07 已由原背景 watcher 實際啟動棒球帽，在 GPU 0 與球鞋共用顯存**。正式 worker 通過 81 項憑證、EXR、六視角顯示檢查及原生 initializer，已啟動真正的 Codex thread；這是啟動證據，尚非資產完成。13:52 狀態為 3 件執行中、4 件排隊、1 件完成、1 件失敗。

## 2026-10-22：修復後重新執行

已安裝可重現補丁、恢復 tmux 佇列，八件未完成工作均已重新排程。12:31 查核為 **電捲棒 1 件完成、水豚與 USB Hub 2 件執行中、其餘 6 件排隊**。這是啟動狀態，新的完整資產成功數仍以 [即時進度](progress/) 為準。

| 問題 | 已驗證修正與安排 |
| --- | --- |
| 球鞋／樹懶重試無法 attach | 把逐次量測與所屬執行一起歸檔並清空，保留 immutable context；原 fresh／ownership／計畫不可改寫驗證維持不變。兩個真實失敗快照都已通過修復後 successor 檢查，沿原 run、原 GPU 續跑。 |
| USB Hub／醬料盒固定點反覆失敗 | 修正 SKILL 中「修改後重新 compile」會丟掉修改的指令；直接使用 revise 回傳的新 compile 與預覽。說明相對原始框的編輯語意與幾何 hint 限制，保留三次試驗上限及語意反思。由舊網格建立新的診斷 snapshot run，舊 halt 不變。 |
| Snapshot 最後匯出可能缺檔 | 官方 initializer 更換 output tag 時漏複製四張材質檢查圖；補上 byte-identical 複製與來源雜湊。兩個真實 public initializer 測試的必需輸入、六項輔助檔、路徑與 lineage 驗證皆通過。 |
| 水豚 spconv int32 assertion | 新 run 使用[官方 OmniPart app](https://github.com/HKU-MMLab/OmniPart/blob/main/app.py)的 `SPCONV_ALGO=native`，保留 48 GiB 門檻與原模型品質。小型 GPU 解析解與 backend 對照通過，完整模型是否避開大張量錯誤仍由本輪驗證。 |
| 料理夾空 SAM3 預測被誤收 | 原生 wrapper 現在檢查實際 NPZ 遮罩、框、分數及保留下來的 SAM3 證據；補洞不能單獨當分割成功。失敗可在既有嘗試預算內重寫概念提示，再用新 run 執行。 |
| 龍與棒球帽清理註冊 | 龍續用既有兩張圖與原 imagegen 呼叫證據，由新 child 重做完整視覺驗證後註冊，禁止第三張；棒球帽用新 run，遇到第一張通過即停止生成。 |

啟動前的必要檢查共 **80 項通過**：重跑主機 21 項及 Genesis 25 項，沿用未變更的網格／OmniPart kernel 25 項，再加測試收集、真實電捲棒匯出、四件原生恢復契約及小型 spconv Native 對照。其內部實際執行 **256 個 CPU／回歸測試，0 fail、0 error、0 skip**，並比對執行前後來源雜湊；80 與 256 是不同層級，不能相加。未宣稱完整水豚峰值顯存或新診斷結果已通過。

`tools/diaggen_support/native_patches.json` 是七份原生補丁的安裝順序。`bash tools/setup_diaggen_runtime_support.sh` 先在暫存副本逆序還原及順序重放每條補丁鏈，核對所有中間 SHA256，全部通過才以原子寫入安裝；未知來源、竄改與 fuzz 都會拒絕。只在 DiagGen 工作停止時執行。八件舊失敗、日誌與歸檔保留在 history；Python 僅做確定性工具及外部工作記帳，pipeline 仍由 GPT-6 Luna Max Codex 與同模型子代理執行。

## 2026-10-22：夜間續跑結果

12:06 查核時，**1 件完成、8 件失敗、0 件執行中、0 件排隊**。前一輪佇列於 02:39 結束；GitHub 進度發布仍在背景執行。當時電捲棒是唯一完整通過診斷、貼圖和匯出的資產。

| 夜間續跑 | 本輪實際進展與停止原因 |
| --- | --- |
| USB Hub | 22:03–22:58 執行，前進至材料與體積網格（5,174 個四面體）及 Genesis；固定點三次預覽仍無法定位到線材／外殼交界，診斷 business halt。沒有最終貼圖或匯出。 |
| 樹懶 | 23:39–02:35 執行，幾何、材料、網格皆完成；診斷重試被已定義過的 planned region／episode 限制擋住，未產生業務推薦。原生服務已清理，仍需修復受支援的 retry 路徑。 |
| 球鞋 | 02:35–02:39 執行，保留所有成功上游；fresh child attach 回報缺少 v2 診斷計畫，而本機 ledger 仍有 v2 計畫，需查明 retry/schema 不一致。沒有最終推薦或匯出。 |

上述兩件 operational retry 不會因單純重新排隊就保證恢復，尚未再盲目重排；USB Hub 的 business halt 亦未改成成功。中午兩張 GPU 已有可用顯存，當前停止原因是流程失敗。前述 190 項測試通過並未涵蓋這兩個夜間暴露的診斷 retry 問題。

唯讀重現已確認目前阻擋球鞋、樹懶 attach 的共同原因：`archive_and_reset_diagnostic_execution_attempt` 清空下一次執行的計畫，卻保留多筆 grounding measurement；fresh validator 只容許最多一筆。兩件分別保留 3／10 筆，因此在記憶體被判為「沒有 v2 plan 的非 fresh 狀態」，而尚未寫回的磁碟仍有舊 plan。對原 ledger 的歷史 coverage 驗證均成功，先前歷史 close 修補仍有效。重現僅操作 deepcopy，正式 state 雜湊未變；此 reset/fresh 契約仍待修復與測試，沒有直接刪除計畫或證據來繞過。

## 2026-10-21 晚間：首件完整匯出與流程修復

**電捲棒已完成 9 個階段並歸檔**：`runs/genesis_curling_iron_20261021_exr_retry1/`。獨立驗證確認 16 個 canonical 匯出檔、1,178 個頂點、4,171 個四面體、兩種材料標籤與單一面連通區；原生物理契約、外觀 GLB、外觀與物理綁定、來源及匯出 SHA256 均通過。兩支診斷 MP4 分別為 31／43 幀、10 fps（3.1／4.3 秒）。這代表生成與診斷流程通過，實物物性仍須測量對照。

此 run 先前已完成原生匯出，但父流程漏掉最後完成狀態，導致外部 queue 誤判失敗。新增 `tools/diaggen_support/validate_completed_export.py`，預設唯讀；只有 `--settle` 通過完整驗證後才用原生 bookkeeping 記錄結案。`queue/reconcile_export.py` 先保存舊失敗紀錄，重新歸檔並核對所有雜湊，才修正外部 queue；未重跑任何生成階段，也未改寫 stage terminal。

其他工作已查明的問題如下，不能把等待當成仍在推論：

| 物件 | 實際卡點 |
| --- | --- |
| 球鞋 | 前段網格已完成；診斷錯誤拒絕已關閉的歷史 session 紀錄，反覆重開 child 仍會重現。已透過原生 MCP shutdown 完成清理，保留可重試狀態。 |
| USB Hub、樹懶 | 前段產物可保留；child 未正確呼叫原生工具，或抄錯顯存 guard 路徑。 |
| 龍 | 清理候選圖已存在，但未完成原生註冊。 |
| 棒球帽 | 已成功清理後又生成第二次候選，原生規則拒絕繼續。 |
| 水豚 | 提高顯存後遇到 spconv/cumm int32 assertion；此輪不是 OOM，仍需驗證對應 backend 修復。 |
| 廚房夾 | SAM3 原始預測為空；原生 fallback 與技能接受條件不一致。 |
| 醬料盒 | 已進 Genesis；三次固定點設定均不合格，留下真實 business halt，尚無最終貼圖或匯出。 |

新增單次原生工具入口 `tools/diaggen_support/stage_tool.py --list`，列出 30 個非診斷工具及真實參數；每次只呼叫指定函式，不自動排程、提交或重試。OmniPart 入口內建同 UUID 的顯存檢查，避免 child 手抄路徑。診斷仍由 MCP 與其 child 擁有。

歷史 session 修補僅允許重新驗證已存在、唯一、已關閉且身份／時間快照完全一致的 settlement；不授權舊 owner 建立新的 close。補丁與前後 SHA256 保留在 `tools/diaggen_support/diagnostic_history_settlement.*`。14 項回歸測試包含原版必定失敗的對照，以及錯誤 owner、重開 session、偽造紀錄等拒絕案例。

`batch_control.py resume JOB RESUME_ID REASON` 可在 HOLD 下安排已停止且符合條件的原 run 續跑。它檢查成功階段的產物、原圖雜湊、原 GPU 綁定與診斷清理狀態；日誌和舊歸檔移至 history 後，才重新排隊。啟動時再次核對 state 雜湊，跳過 initializer 與已成功階段。新一輪 GPU claim 仍須符合原門檻；診斷由全新 child 自行 attach。已 halt 的階段及已有業務推薦的診斷不會被這個入口重開。18 項續跑測試包含實際執行 wrapper 的假引擎測試；這不等同三件續跑已完成。

本輪已將球鞋、USB Hub、樹懶以相同 run ID 重新排隊，恢復 tmux 等待。三件沿用原 GPU UUID，滿足 24 GiB 門檻後依清單順序續跑；其他五件仍保留失敗狀態。啟動前檢查紀錄已更新並再次比對通過。

先前 71 項預檢涵蓋環境與小型 fixture，沒有涵蓋這些完整流程接線、歷史紀錄與最終結案錯誤；不能將預檢通過解讀為九件均可完成。即時數量與續跑狀態以 [progress/](progress/) 為準。

## 背景執行

`queue/wait_and_run.sh` 在伺服器的 `tmux` session `diaggen-genesis-wait` 執行。每 **15 秒**檢查顯存，只要某張 GPU 至少有 **24576 MiB（24 GiB）** 可用就可啟動；允許和既有運算工作共用，不要求 GPU 利用率低或完全閒置。每張 GPU 同時最多三個本批次工作，整批最多四個工作並行；共用時會以既有工作加新工作之門檻總和核對目前空閒顯存。水豚曾在 OmniPart mesh decoder 發生 OOM，下一次單獨改用 **49152 MiB（48 GiB）** 試跑；其餘仍為 24 GiB。進入 OmniPart 前，該階段子代理還必須在原綁定 GPU 上重新等待相同門檻。顯存檢查不會保留容量，無法保證其他程序稍後不增加用量。

24 GiB 是尚未量測 OmniPart 實際峰值前的積極試跑門檻，不能保證避免記憶體不足。失敗會如實保留紀錄，不覆蓋既有 run。修復共通環境問題後，可明確安排新 run ID 重試；舊 run 與日誌會保留。SSH 斷線不影響 tmux；伺服器重開機會中斷。

9 個工作與輸入雜湊記錄於 `batch_plan.json`。README 與授權文字不會成為工作。依清單順序選取符合目前顯存的工作；水豚的較高門檻不會擋住其餘圖片。

每個工作使用獨立 run ID、GPU UUID、Genesis cache、日誌及歸檔目錄。原始工作檔寫在 `tools/diaggen/outputs/`；結束後整理到本機 `sims/diaggen_genesis/runs/<run_id>/`，並標記 `simulator: Genesis`。部分失敗工作可能只有中間產物。

## GitHub 進度

`queue/publish_progress.sh` 在獨立 tmux session 中每 15 秒讀取真實 ledger。各工作階段或修復版本改變時更新 `progress/`，推送至 `diaggen-genesis-progress` 分支。單純等待及時間戳更新不會反覆產生 commit。網路失敗會在本機記錄並重試。

發布使用專用 worktree，不修改主工作目錄的 index。報告只發布階段狀態與限定的預覽媒體；完整 state、執行日誌與診斷 session 資料留在本機。所有 commit 使用一般作者設定，沒有額外共同作者註記。

## 2026-10-21：分割環境修復

首批 USB Hub、水豚、棒球帽與電捲棒完成清理後，均因 OpenCV 5.0 未編入 OpenEXR 而停在 SAM3 輸出。專案內的分割環境已改回原專案指定的 `opencv-python==4.13.0.92`，用實際 float32 RGB EXR 遮罩確認寫入、讀回和數值完全一致。環境建置腳本已固定版本，各工作啟動前也會執行同一檢查；檢查失敗會暫停新件。

原生流程沒有重開已 halt 分割階段的恢復入口，因此採用新 run ID 從原圖重跑；失敗 run、部分產物與原始日誌均保留，未改寫成成功。執行次數記錄在本機 batch ledger，9 個物件維持 9 個排程項目。

## 2026-10-21：OmniPart 渲染與顯存修復

USB Hub 重跑已通過 SAM3 並產生中間 combined mesh；原生程式因缺少 Xvfb 跳過六視角零件預覽，故資產驗證正確停止。已將固定版本的 Xvfb 解開到專案私有目錄，並用真實中間網格完成六視角 CPU 測試。每個新工作都啟動自己的動態顯示號，在啟動前確認六張非空測試圖，退出時只關閉自己建立的 X server。沒有修改系統套件；測試預覽不當作原生階段成功。

水豚重跑通過 SAM3 後，在 OmniPart mesh decoder 發生 CUDA OOM。它的下一次試跑門檻改成 48 GiB，其他物件維持 24 GiB；這不是量測出的保證峰值。記憶體等待工具只查詢原 GPU，不切換 GPU、不終止其他工作，也不降低推理或輸出品質。

這兩件均保留既有失敗 run，再以新 run ID 重跑；原生 halt terminal 未被刪除或改寫。私有顯示環境可用 `bash tools/setup_diaggen_xvfb.sh` 重建。

## 完成後會得到什麼

每件成功完成的 `runs/<run_id>/asset/` 是可重用的 Genesis FEM 資產包，主要檔案如下。實際出現的檔案以 manifest 與階段成功狀態為準。

| 檔案 | 用途 |
| --- | --- |
| `final_mesh.mesh` | 四面體體積網格，供物理模擬 |
| `heterogeneous_params.npz` | 各四面體的剛度、泊松比、密度與零件標記 |
| `inferred_params.json` | 零件語義及推定的材料參數 |
| `volume_topology.json`、`metric_mesh_scaling.json` | 拓樸與物理尺寸換算 |
| `final_export_manifest.json` | 匯出清單與雜湊 |
| `appearance/visual_mesh.glb`、`albedo.png` | 可瀏覽的外觀模型與貼圖 |
| `appearance/visual_to_physics.npz` | 外觀與物理網格對應 |

`trace/state.json` 及 `trace/revisions/` 保留清理圖、分割、零件幾何、材料推估、網格處理與修正歷史。各 revision 的 `sim_diagnostics/` 保留診斷摘要、報告、各 episode 的截圖及可用 MP4。未執行到該階段的工作不會有相應產物；最終資產和診斷影片用途不同。

## 如何檢查物理性質

啟用中的 Genesis 診斷會選取有意義的區域進行固定、擾動、放開與回復觀察，檢查軟硬、連接、空腔、尺度及網格問題，再決定接受或修正。這能檢查模擬是否合理，單張照片不足以唯一辨識真實物性。

要驗證真實性，可先量物件尺寸與重量，核對尺度與總質量；再固定施力位置與大小，比較力—位移、放開後形狀、回彈與滑動摩擦，並以相同鏡位的實物操作影片對照。只看影片覺得像，不能視為剛度或摩擦已量準。此批排程包含生成和 Genesis 診斷；[論文](https://diaggen.github.io/static/DiagGen_pub-release_26-09-19-14-27.pdf)中的獨立 PMSC／PAIP 評分尚未另外排程。

## 如何互動

[官網](https://diaggen.github.io/#method)的資產瀏覽器可旋轉、縮放、平移、切換圖層；`visual_mesh.glb` 可供同類外觀瀏覽。影片中的捏拉、扭轉及機器人操作還需要 Genesis 場景、控制器與操作任務。

現有原生診斷採用 headless 執行，沒有通用的滑鼠捏拉介面。若要從 SSH 連線的電腦即時操作，需要另加 Genesis GUI 配合遠端桌面，或建立瀏覽器影像串流與控制介面；單靠 port forwarding 不會產生操作 UI。尚未建立或驗證此批資產的互動介面。

## 模型選擇

先保留 GPT-6 Luna Max 完成基準試跑，再依錯誤類型比較更強模型；目前電捲棒已完成，尚不能保證九件都達標。若零件語義、材料推斷或診斷修正反覆失敗，可選代表案例改用更強模型做同條件比較。[OpenAI Docs](https://developers.openai.com/api/docs/guides/model-selection)建議按實測選擇達標的模型。更多 reasoning 預算和模型本身能力是不同因素。

更換 LLM 不會自動更換 SAM3、OmniPart 或貼圖工具；清楚原圖、實際尺寸、材料資料與真實互動對照仍然重要。

## 執行前預檢

初次環境預檢 **71 項通過、0 項失敗、0 項未測**；非必要 CMake 未安裝，另標為 optional skip。下表列出這次環境測試範圍。這是環境與小型 fixture 測試，不是九件物品已生成完成。

晚間修復後的 [最新驗證](preflight/latest.json) 共 **75 個必要檢查項目通過**：沿用未變更的主機／網格／OmniPart 46 項基準，重新執行 Genesis 25 項，再加三項測試收集檢查與一項真實電捲棒完整匯出驗證。測試收集實際執行 **190 個 CPU／回歸測試，0 fail、0 error、0 skip**，並核對執行前後來源雜湊；75 是檢查項目數，190 是其內部測試數，不能相加。新報告明確保留沿用與重測的區別。

| 範圍 | 實際測試 | 必要檢查 |
| --- | --- | --- |
| 主機／SAM3 | 9 圖片解碼和雜湊、5 環境、所有 stage／MCP 匯入、權重 CPU mmap、EXR、命令與磁碟讀寫 | 21 通過 |
| 網格／材料 | 原生實心／空心處理、四面體化、材料配置、序列化、4 張實際渲染、壞資料拒絕與物理匯出契約 | 12 通過 |
| OmniPart／貼圖 | 離線權重、FlashAttention、spconv、scatter、nvdiffrast 編譯／渲染／取樣、Gaussian、UV 和 GLB | 13 通過 |
| Genesis | 實際 CUDA FEM、live API、幾何讀回、三視角／零件標記渲染、捕捉影格 MP4 編解碼、程序收尾 | 25 通過 |

已查核[官方 GitHub](https://github.com/diaggen/diaggen/tree/3d2d3779613b9253109f63e1ff345b11c9097b70)及全部狀態的 Issues／PRs／Releases，沒有找到更新的修復版。確認兩項需本地修復：

- 官方診斷呼叫 `scripts/generate_simulation_mp4.sh`，但發佈目錄缺檔。新增相容入口，使用實際擷取影格編碼，檢查影格連續、尺寸、幀率與解碼數量；缺少影格時拒絕，不能拿舊 MP4 當新成果。
- 官方技能要求完整材料標籤覆蓋，原版程式卻只警告；已用一行可重現補丁改為嚴格失敗，保留元件修復的 subset 行為。補丁有原始碼前後 SHA256，遇到不同上游版本會停止套用。

新環境在所有 DiagGen 工作停止後，執行 `bash tools/setup_diaggen_runtime_support.sh` 還原編碼入口及兩份已驗證補丁（含上述歷史 session 修補）。各 probe 位於 `preflight/probe_*.py`，必須使用對應的專案 Python、全新 `tools/diaggen/outputs/preflight/` 子目錄，GPU probe 另需明確 UUID；硬體探針以 `queue/preflight_gpu.lock` 序列執行。

完整報告通過後，`preflight/readiness.py` 產生本機檢查紀錄。每件工作開始前，會比對輸入、必要來源檔、原生 Python／CUDA 程式、五個環境套件及執行檔；缺少或變更會建立 HOLD，先擋住新工作。只有圖片雜湊、套件列表或設定存在，不能代替實際功能預檢。

預檢未量測完整推論的峰值顯存，未宣稱整個 1024² 貼圖重烘焙或含外觀的最終資產包已跑通；雲端模型與 imagegen 可用性採用既有成功執行的明確紀錄。本機完整原始報告、測試影格與影片留在 `tools/diaggen/outputs/preflight/`。

## 來源

- [DiagGen 專案](https://diaggen.github.io/)
- [DiagGen 程式碼](https://github.com/diaggen/diaggen)
- [官方擷取圖片來源與授權](inputs/demo_gallery/ATTRIBUTION.txt)

詳細的本機操作與路徑見 [README.txt](README.txt)。
