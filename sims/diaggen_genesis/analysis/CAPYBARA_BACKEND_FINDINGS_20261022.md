# 水豚的 spconv 大張量限制

2026-10-22 查核：目前仍未修復，未重新盲排同樣的工作。其餘物件繼續執行。

正式 run `genesis_capybara_plush_toy_20261022_native_retry3` 已通過顯存門檻：可用 65,296 MiB，要求 49,152 MiB；SAM3 產生五個部件。OmniPart 在 mesh decoder 的 spconv 張量 `[6874752, 192]`、fp16 路徑失敗。該張量為 2,639,904,768 bytes，超過此次 kernel 檢查的 2,147,483,647 bytes。這不是該次記憶體不足；提高顯存門檻或更換推理語言模型，不能單獨移除這個 kernel 限制。

本機套件為 PyTorch `2.7.0+cu128`、spconv-cu126 `2.3.8`、cumm-cu126 `0.7.11`。先前的小型 native／implicit 數值比較成功，只能證明小張量相容，不能證明這個尺寸可用。

## 上游查核

- [spconv issue 706](https://github.com/traveller59/spconv/issues/706) 仍開啟，回報相同的 int32 range 失敗。留言中的改用 int64 上限或略過檢查並非正式維護者修補；不能把移除斷言當作完整數值正確性的證據。
- [cumm GEMM 程式](https://github.com/FindDefinition/cumm/blob/d971d02a0b29b7e6da46186564f37bde77b99dcc/cumm/gemm/nvrtc_code.py) 與 [convolution 程式](https://github.com/FindDefinition/cumm/blob/d971d02a0b29b7e6da46186564f37bde77b99dcc/cumm/conv/nvrtc_code.py) 本次透過 GitHub API 核對預設 main 分支 commit `d971d02a0b29b7e6da46186564f37bde77b99dcc`，來源仍包含 int32 位元組範圍檢查。因此，錯誤文字說「會在 2.2／2.3 修復」，不等於目前安裝的 2.3.8 已修好。
- [OmniPart 官方 sparse backend 設定](https://github.com/HKU-MMLab/OmniPart/blob/ceb1a4ff2d279a57a673d0f65954735c6bf8231c/modules/part_synthesis/modules/sparse/__init__.py) 確實列出 `spconv` 與 `torchsparse`，但本機尚未安裝 TorchSparse，未驗證相同預訓練權重可直接載入另一個 backend。
- [官方模型載入器](https://github.com/HKU-MMLab/OmniPart/blob/ceb1a4ff2d279a57a673d0f65954735c6bf8231c/modules/part_synthesis/models/__init__.py) 使用 `strict=False`；因此即使另一 backend 沒有拋出載入錯誤，也必須另查 missing／unexpected keys 與完整權重對應，不能把部分未載入的模型視為復現。

目前沒有修改 spconv／cumm、略過原生檢查、降低解析度或精度，也沒有切換 production backend。若後續採用替代 backend 或正式上游修補，須在隔離環境驗證相同權重、完整大張量與實際水豚產物，再安排新 run；不能用小型 smoke test 宣稱解決。

DiagGen 官方預設 master 分支本次仍為 `3d2d3779613b9253109f63e1ff345b11c9097b70`，與本機復現基準相同；沒有查到新的 DiagGen commit 可直接取代目前基準來解決此限制。


## 未部署的分批解碼實驗

另做隔離 GPU 比較：相同原生 mesh decoder、相同預訓練權重（`strict=True` 完整載入）、fp16 與 64 解析度，同一組兩個 sparse batch member 同時計算或各自計算。輸出 sparse 座標一致，但 decoder features 在事先固定的 `rtol=0.001, atol=0.00001` 比較中有 212842／349056（61.0%）元素不符，最大絕對差 0.0796557665。第一個 seed 的 mesh 比較即失敗；未執行 Gaussian、RF、第二個 seed，也未據此宣稱成品網格必然不同。

這不足以保證分批計算等價，**候選做法未部署**。正式來源、權重、精度、解析度及驗收規則均未修改。不能只因分批可能省顯存，就把它當成水豚已修好。公開結果見 [decoder_batch_equivalence_failed.json](decoder_batch_equivalence_failed.json)；本機原始測試程式與紀錄保留於 `tools/diaggen/outputs/preflight/decoder_batch_equivalence_20261022/`。
