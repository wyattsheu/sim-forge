# 卡住原因與改善驗證（2026-10-22）

截至 15:01（Asia/Taipei），9 件仍為完成 1、執行中 3、失敗 4、排隊 1。`running` 表示外層程序尚未結束，不代表 GPU 正在生成，也不代表診斷有前進。以下區分已重現的錯誤、觀察到的中斷，以及尚未部署的改善。

## 已確認的原因

| 問題 | 證據與影響 | 優先改善 |
|---|---|---|
| 重試狀態與磁碟快照不同步 | 球鞋、樹懶的新 attempt 沒有材質登記，但上一輪 `material_audit_authoritative/revision_0000/cleaned_source_image.png` 還在。原生登記函式拒絕同名覆寫，因此在建立 episode 前失敗。兩個保存的失敗狀態均已在臨時目錄重現。 | 新 attempt 使用獨立快照命名空間，保存舊證據；預檢走到實際快照登記，不能只驗 fresh-state schema。 |
| 子程序退出後，owner lease 尚未結束 | USB Hub 首次子程序回報 MCP 已無 current attachment；醬料盒完成一次 probe、關閉 session 後退出，沒有最終 recommendation。新 child attach 被 durable owner 擋住。兩者最初為何失去／結束有效服務，尚未從紀錄證明，不能宣稱已找到 MCP 重啟原因。 | 確認 child 是否產生合法 terminal；區分正在推理、合法等待、服務中斷。異常交由原生 watchdog／transport recovery 清理，parent 不接管 token、不手改鎖。 |
| 等待後重送不可變計畫 | USB Hub fresh attach 後重送 plan，實際收到 `diagnostic session plan is immutable and may be submitted only once`。 | 新 child 不等於新 execution。先判斷原生是否完成 typed archive/reset，若計畫仍在，不能當作未規劃狀態重送；只有合法接續或原生終止路徑才能往下。 |
| fresh 與 resume 指令混用 | 外層 `queue/run_one.sh` 對所有模式輸出要求讀 `resume.json`、找舊清理候選的段落；帽子與料理夾的本輪模式都是 fresh，對應檔案不存在。這是我們外層包裝的缺陷。 | 依 fresh／resume／diagnostics_snapshot 分別產生指令，必要 metadata 在啟動前驗證；fresh 依官方兩次 imagegen 上限執行，不自行找別輪候選。 |
| 清理驗證與選用候選被混為一件事 | 帽子與料理夾背景 RGB 253–255，嚴格背景檢查失敗。官方清理技能第 6 步允許兩次生成都語意不通過時，選較佳候選並保留失敗紀錄；選用不等於把 fail 改成 pass。料理夾的登記另被自動核准審核拒絕。 | 啟動指令準確表達官方 bounded selection 規則；保留實際驗證、生成證據與配對描述。既有拒絕不能以改寫指令或其他路徑繞過，該次操作仍未執行。 |
| OmniPart 張量超出 kernel 索引範圍 | 水豚日誌顯示 `feat=[6874752,192]`、f16 kernel、`ConvAlgo.Native`，最後是 `your data exceed int32 range`。按這個形狀與 f16 計算，單個特徵陣列為 2,639,904,768 bytes，超過 kernel 的 2,147,483,647 上限。 | 先以相同形狀在隔離環境驗證相容的官方 kernel／版本；小型 sparse convolution 通過不代表這個規模通過。更多空閒 VRAM 或換更強 LLM 都不會消除這個 assertion。 |

鎖的 3,900 秒（65 分鐘）是原生預設，也正是 episode timeout 加 300 秒 grace 的約束；工具呼叫在進入及退出時續租，包括呼叫內容拋錯的情況。因此「失敗一次 → 等 65 分鐘 → 再撞相同錯誤」是可能發生的。不能只把 timeout 任意調小就當作修復。

## 這次實際完成的改善

1. GitHub 進度觀察器增加受控異常提示：材質快照衝突、診斷紀錄超過 15 分鐘未更新且無 in-flight 呼叫、診斷鎖到期、時間／路徑資料不合法。只發布固定代碼與計數，不發布 credential、attachment ID、lease 時戳或原始錯誤。
2. 進度指紋加入 episode、tool result、probe attempt、region settlement 計數，使中途診斷證據變化可被看見。數量增加只代表產生紀錄，不等於成功；單純 heartbeat 不造成重複進度提交。
3. 新增 10 項健康提示負向對照，加上原有 32 項發布器測試，共 42 項通過。包含長時間工具呼叫不被標為 idle、已完成／已失敗不被標為等待、路徑越界與 symlink、秘密資料不外洩、觀察不改 state 或檔案。
4. 原有 runtime certificate 再驗證 81 項通過。這次未修改生成、診斷 native source、模型、物理設定、排程政策或正式 state；publisher 的新測試不冒充完整生成測試。

提示是觀察，**不會自動宣告失敗、解除鎖、重排或接受資產**。15 分鐘沒有 ledger 更新也可能是較長的模型推理，需要配合 child 與工具紀錄判讀。此版本尚未加入自動停止重複失敗的機制，也沒有自動修復原生流程。

## 可重現的快照修正實驗

[`reproduce_retry_artifacts.py`](reproduce_retry_artifacts.py) 在臨時目錄複製材質快照，對保存的球鞋／樹懶狀態各執行一次原生登記函式，重現同名路徑錯誤。接著只在記憶體中的候選函式加入已驗證 attempt ID 的子目錄，再驗證：

- 五個 authoritative artifacts 全部登記，來源與快照 SHA-256 相符。
- 同一輪再次取得登記不改寫紀錄。
- 上一輪快照位元組保留，正式 state 與來源證據未改動。

結果見 [`retry_artifact_reproduction.json`](retry_artifact_reproduction.json)。本機保存的原始狀態在 `tools/diaggen/outputs/preflight/stall_audit_20261022/`，含私有 ownership 資料，不發布。

```bash
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES='' \
  tools/diaggen/.conda/hag4r/bin/python \
  sims/diaggen_genesis/analysis/reproduce_retry_artifacts.py \
  --state-json tools/diaggen/outputs/preflight/stall_audit_20261022/3_state.json
```

這是**尚未部署的局部修正實驗**，只驗證 registration boundary；尚未驗證完整 `define_episode → create → bind → probe → close → terminal`。正式修補前仍須驗證其他 episode、grounding、preview 的舊證據隔離，以及所有引用與雜湊檢查，避免修掉第一個碰撞卻覆寫後面的舊資料。正在執行的 worker 沒有被熱改。

## 後續修復順序與驗收

1. **先修重試轉移與檔案生命週期。** 用保存的兩個失敗快照走完整原生 episode 邊界，測不同 attempt、同 attempt 重入、舊證據保留與拒絕錯誤 lineage；通過後才受控部署。
2. **再修啟動指令與重試預算。** 三種模式要有不同的 prompt／metadata 前置條件；同一個確定性錯誤應暫停自動重試並報告，不要每 65 分鐘再花一次模型用量。停止機制須只管理本 queue 的 worker，讓原生 MCP 完成清理，不能粗暴刪鎖或停別人的程序。
3. **補「中斷後的下一步」測試。** 目前環境通過卻卡住，顯示缺的是狀態轉移覆蓋。測 attach 後 schema 失敗、plan 已存在、session 已關但 terminal 未提交、MCP 中斷，以及 disk artifact 已存在的組合。每條測試要走到下一個合法事件，不能只檢查 import／檔案存在。
4. **最後處理水豚的大張量 kernel。** 目前尚未找到已驗證且保持原生成設定的官方修復。先驗相同規模與模型環境，再決定是否升級隔離依賴；不採用略過 assertion、裁剪部件或偷偷降低解析度來宣稱復現成功。

## 官方查詢

- [DiagGen 官方倉庫](https://github.com/diaggen/diaggen)：查詢時最新 commit 仍是 `3d2d3779613b9253109f63e1ff345b11c9097b70`；GitHub issues API 的公開列表為空，沒有找到現成修復。
- [官方清理規則](https://github.com/diaggen/diaggen/blob/master/.agents/skills/run-diaggen-pipeline/image-cleanup/SKILL.md)：兩次生成上限、兩個語意失敗候選仍可按規則選較佳者，驗證結果必須如實保留。
- [官方 MCP lifecycle](https://github.com/diaggen/diaggen/blob/master/hag4r/agentic/diagnostic_mcp_server.py)：owner lease、最小 timeout、過期 recovery 與 typed transport recovery 是不同狀態，不能混用。
- [OmniPart 官方 app](https://github.com/HKU-MMLab/OmniPart/blob/main/app.py) 確實使用 `SPCONV_ALGO=native`；水豚本輪已使用而仍失敗，不能再稱換 native 已修好。
- spconv 官方倉庫的 [#706](https://github.com/traveller59/spconv/issues/706)、[#656](https://github.com/traveller59/spconv/issues/656) 有同類 int32 錯誤。後者留言提到非官方略過限制的方法，並有渲染異常回報；本次沒有採用，也未把它當作官方修復。
