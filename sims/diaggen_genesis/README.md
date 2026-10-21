# DiagGen / Genesis 實驗

[最新進度](progress/) · [執行環境預檢](preflight/latest.json) · [官方圖片總覽](demo_inputs_preview.jpg) · [圖片來源紀錄](demo_image_sources.json) · [排程清單](batch_plan.json)

使用 DiagGen 內附的 **Genesis 1.2.0**，開啟 Genesis 診斷，排程 9 張圖片的完整生成流程。

- 生成與診斷：**GPT-6 Luna，Max reasoning**；各階段子代理沿用相同設定。
- 論文對應設定為 GPT-5.6 Luna、Max；本次依要求改用同系列新版，並保留差異紀錄。
- 8 張官方 demo 圖片擷取自影片的輸入照片區，解析度受影片限制，未放大；另外 1 張水豚玩偶照片由使用者提供。總覽圖片只包含 8 張官方擷取圖。
- 模型權重、第三方環境與完整工作檔保留在伺服器。此目錄的程式負責等待、整理和進度發布；實際 pipeline 由原專案的 Codex skill 執行。

## 背景執行

`queue/wait_and_run.sh` 在伺服器的 `tmux` session `diaggen-genesis-wait` 執行。每 **15 秒**檢查顯存，只要某張 GPU 至少有 **24576 MiB（24 GiB）** 可用就可啟動；允許和既有運算工作共用，不要求 GPU 利用率低或完全閒置。每張 GPU 同時最多一個本批次工作，整批最多兩個工作並行。水豚曾在 OmniPart mesh decoder 發生 OOM，下一次單獨改用 **49152 MiB（48 GiB）** 試跑；其餘仍為 24 GiB。進入 OmniPart 前，該階段子代理還必須在原綁定 GPU 上重新等待相同門檻。顯存檢查不會保留容量，無法保證其他程序稍後不增加用量。

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

先保留 GPT-6 Luna Max 完成基準試跑，再依錯誤類型比較更強模型；目前沒有本批結果，不能保證九件都達標。若零件語義、材料推斷或診斷修正反覆失敗，可選代表案例改用更強模型做同條件比較。[OpenAI Docs](https://developers.openai.com/api/docs/guides/model-selection)建議按實測選擇達標的模型。更多 reasoning 預算和模型本身能力是不同因素。

更換 LLM 不會自動更換 SAM3、OmniPart 或貼圖工具；清楚原圖、實際尺寸、材料資料與真實互動對照仍然重要。

## 執行前預檢

本次必要檢查 **71 項通過、0 項失敗、0 項未測**；非必要 CMake 未安裝，另標為 optional skip。完整結果摘要見 [preflight/latest.json](preflight/latest.json)。這是環境與小型 fixture 測試，不是九件物品已生成完成。

| 範圍 | 實際測試 | 必要檢查 |
| --- | --- | --- |
| 主機／SAM3 | 9 圖片解碼和雜湊、5 環境、所有 stage／MCP 匯入、權重 CPU mmap、EXR、命令與磁碟讀寫 | 21 通過 |
| 網格／材料 | 原生實心／空心處理、四面體化、材料配置、序列化、4 張實際渲染、壞資料拒絕與物理匯出契約 | 12 通過 |
| OmniPart／貼圖 | 離線權重、FlashAttention、spconv、scatter、nvdiffrast 編譯／渲染／取樣、Gaussian、UV 和 GLB | 13 通過 |
| Genesis | 實際 CUDA FEM、live API、幾何讀回、三視角／零件標記渲染、捕捉影格 MP4 編解碼、程序收尾 | 25 通過 |

已查核[官方 GitHub](https://github.com/diaggen/diaggen/tree/3d2d3779613b9253109f63e1ff345b11c9097b70)及全部狀態的 Issues／PRs／Releases，沒有找到更新的修復版。確認兩項需本地修復：

- 官方診斷呼叫 `scripts/generate_simulation_mp4.sh`，但發佈目錄缺檔。新增相容入口，使用實際擷取影格編碼，檢查影格連續、尺寸、幀率與解碼數量；缺少影格時拒絕，不能拿舊 MP4 當新成果。
- 官方技能要求完整材料標籤覆蓋，原版程式卻只警告；已用一行可重現補丁改為嚴格失敗，保留元件修復的 subset 行為。補丁有原始碼前後 SHA256，遇到不同上游版本會停止套用。

新環境先執行 `bash tools/setup_diaggen_runtime_support.sh` 還原這兩項本地支援。各 probe 位於 `preflight/probe_*.py`，必須使用對應的專案 Python、全新 `tools/diaggen/outputs/preflight/` 子目錄，GPU probe 另需明確 UUID；硬體探針以 `queue/preflight_gpu.lock` 序列執行。

完整報告通過後，`preflight/readiness.py` 產生本機檢查紀錄。每件工作開始前，會比對輸入、必要來源檔、原生 Python／CUDA 程式、五個環境套件及執行檔；缺少或變更會建立 HOLD，先擋住新工作。只有圖片雜湊、套件列表或設定存在，不能代替實際功能預檢。

預檢未量測完整推論的峰值顯存，未宣稱整個 1024² 貼圖重烘焙或含外觀的最終資產包已跑通；雲端模型與 imagegen 可用性採用既有成功執行的明確紀錄。本機完整原始報告、測試影格與影片留在 `tools/diaggen/outputs/preflight/`。

## 來源

- [DiagGen 專案](https://diaggen.github.io/)
- [DiagGen 程式碼](https://github.com/diaggen/diaggen)
- [官方擷取圖片來源與授權](inputs/demo_gallery/ATTRIBUTION.txt)

詳細的本機操作與路徑見 [README.txt](README.txt)。
