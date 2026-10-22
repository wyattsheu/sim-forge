# 每個物件的模型 token 用量

這是唯讀統計，不改 DiagGen 的模型、流程、物理方法或排程。

## 已核對案例：電捲棒

成功執行 `genesis_curling_iron_20261021_exr_retry1`，包含主代理與 8 個階段子代理，共 501 筆模型請求：

| 類別 | Tokens |
| --- | ---: |
| 輸入總量 | 31,449,195 |
| 其中快取輸入 | 30,705,152 |
| 非快取輸入 | 744,043 |
| 輸出總量 | 180,258 |
| 其中推理輸出 | 105,079 |
| 輸入＋輸出 | **31,629,453** |

輸入快取比例為 **97.63%**。快取已包含在輸入中，推理已包含在輸出中，不再重複加總。這是所有請求的累積用量，並非單次上下文長度，也不能視為全數以一般輸入單價計費。

範圍僅限這次成功執行的 Codex 模型請求；不含先前失敗嘗試、這個互動對話的除錯與開發、影像生成工具的獨立費用，以及本機 GPU 計算。尚無跨多個成功物件的可靠平均。

## 重算方式

從專案根目錄執行：

```bash
python3 sims/diaggen_genesis/analysis/count_tokens.py \
  --events sims/diaggen_genesis/queue/jobs/curling_iron/codex_events.jsonl \
  --output sims/diaggen_genesis/analysis/curling_iron_token_usage.json
```

改換其他物件的 `--events` 路徑即可。資料來源是本機 Codex 的唯讀 session 索引及其逐筆用量紀錄；原始 session、對話、請求識別碼與憑證不發布。

統計方法：

1. 從該次執行的 `thread.started` 定位主代理，依 `thread_spawn_edges` 找齊子代理。
2. 僅讀取各代理自己的 `token_usage_record.payload.usage`，以代理及 response 識別碼去重，再加總逐筆用量。
3. 比對各代理加總與最後一筆 `thread_token_usage`；缺資料或不一致就報錯。
4. 不將每次累積狀態再次相加，也不把主代理自己的用量誤當成全體用量。

本次另查到診斷代理的一筆上下文壓縮請求用了 174,400 tokens，未包含在 `event_msg.token_count` 的最終數值中；結構化逐筆紀錄及其最後累積值則有包含。因此只讀取簡易事件或資料庫 `tokens_used` 會低估這次用量。

OpenAI 官方說明：[Codex JSON 事件](https://learn.chatgpt.com/docs/non-interactive-mode)、[推理 token](https://developers.openai.com/api/docs/guides/reasoning)、[輸入快取](https://developers.openai.com/api/docs/guides/prompt-caching)。這份統計沒有將 token 換算為訂閱額度或實際帳單金額。
