# DiagGen / Genesis 實驗

[最新進度](progress/) · [測試圖片總覽](demo_inputs_preview.jpg) · [圖片來源紀錄](demo_image_sources.json)

本實驗先在 DiagGen 內附的 **Genesis 1.2.0** 跑通單張圖到可變形資產的完整流程，開啟 Genesis 診斷。首次輸入選用 USB Hub。

- 生成與診斷：**GPT-6 Luna，Max reasoning**；各階段子代理沿用相同設定。
- 論文對應設定為 GPT-5.6 Luna、Max；本次依要求改用同系列新版，並保留差異紀錄。
- 8 張 demo 圖片擷取自官方影片的輸入照片區，解析度受影片限制，未放大；完整原始手機照片未包含在取得的公開素材包內。
- 模型權重、第三方環境與完整工作檔保留在伺服器。此目錄的程式是等待、整理和進度發布工具，不能代替原專案的 pipeline skill。

## 背景執行

`queue/wait_and_run.sh` 在伺服器的 `tmux` session `diaggen-genesis-wait` 等待圖片及 GPU。每 60 秒檢查一次，等同一張 GPU 無運算程序且至少 65536 MiB 空閒，連續兩次符合才啟動。SSH 斷線不影響已啟動的 tmux session；伺服器重開機會中斷。

原始工作檔寫在 `tools/diaggen/outputs/`；完成或失敗後，現有產物整理到本機 `sims/diaggen_genesis/runs/genesis_first_20261021/`，並標記 `simulator: Genesis`。

## GitHub 進度

`queue/publish_progress.sh` 在獨立的 tmux session 中讀取實際 ledger，每個執行階段或修復版本發生變化時，更新 `progress/` 並推送至 `diaggen-genesis-progress` 分支。等待中的時間更新不會重複產生 commit。網路失敗會在本機記錄並重試。

發布使用專用 worktree，不修改主工作目錄的 index。報告只選取階段狀態與限定的預覽媒體；完整 state、執行日誌、診斷 lease／session 資料留在本機。所有 commit 使用一般作者設定，沒有額外共同作者註記。

## 來源

- [DiagGen 專案](https://diaggen.github.io/)
- [DiagGen 程式碼](https://github.com/diaggen/diaggen)
- [測試圖片來源與授權](inputs/demo_gallery/ATTRIBUTION.txt)

詳細的本機操作與路徑見 [README.txt](README.txt)。
