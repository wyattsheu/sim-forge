# memory/ —— 踩坑記憶庫

做 Isaac Sim 模擬時,每次踩到的坑和解法都記在這裡。分兩種讀法:

| 你是 | 讀哪份 | 內容 |
|---|---|---|
| **人** | [`HANDBOOK.md`](HANDBOOK.md) 踩坑手冊 | 每條只講「碰到什麼問題」和「該怎麼做」,用人話 |
| **AI agent** | [`AGENTS.md`](AGENTS.md) → [`INDEX.md`](INDEX.md) → `lessons/` | 讀取 / 寫入規程、索引、每條的完整細節(數字、程式碼、證據) |

兩份內容來自同一個地方(`lessons/` 裡每條教訓的檔案),手冊是自動產生的,所以不會兩邊各寫各的、越差越多。

---

## 怎麼叫 AI 用這份記憶

開始一個新任務時,把這段貼給 agent:

> 動手前先讀 `memory/AGENTS.md`,照「讀取規程」讀 `memory/INDEX.md` 和跟這次任務相關的教訓,
> 在計畫裡列出你會遵守的條目編號。做完之後照「寫入規程」把這次新踩到的坑寫進 `memory/`,
> 跑 `python3 memory/memtool.py build && python3 memory/memtool.py check`。

只想要它查某件事:

> 先用 `python3 memory/memtool.py find <關鍵字>` 查記憶裡有沒有相關的坑。

## 自己查

```bash
python3 memory/memtool.py find 滑鼠              # 關鍵字
python3 memory/memtool.py find --domain surface  # 某個領域全部
python3 memory/memtool.py show L0024             # 一條的全文
```

## 自己加一條

最簡單:跟 AI 說「把剛才這個問題照 memory 的寫入規程記下來」。

手動:

```bash
python3 memory/memtool.py new --domain rigid --title "薄板的 contactOffset 要小於板厚" --slug thin-plate-offset
# 打開產生的 lessons/L00xx-*.md 照模板填,然後
python3 memory/memtool.py build && python3 memory/memtool.py check
```

規則只有幾條:

- 一條教訓一個檔;**有數字就寫出處**(哪個 run、哪個 log)。
- 「人話」段寫給沒碰過 Isaac 的人看:問題一兩句,做法一到三點。
- **不刪舊的**。舊結論被推翻時,開新的一條,把舊的標成「已推翻」—— 因為舊程式註解可能還寫著舊結論,讀的人需要知道。
- `HANDBOOK.md`、`INDEX.md` 是產生出來的,不要手改。

## 資料夾內容

```
memory/
  README.md        這份(給人)
  HANDBOOK.md      踩坑手冊(給人,自動產生)
  AGENTS.md        AI 讀寫規程
  INDEX.md         AI 索引(自動產生)
  lessons/         每條教訓的詳細版(單一來源)
  templates/       新教訓模板
  memtool.py       查詢 / 新增 / 產生 / 檢查
```

## 為什麼這樣設計

參考了 NASA 的 Lessons Learned 系統、軟體業的 ADR(架構決策紀錄)、Google SRE 的事後檢討,
以及近年 AI agent 經驗記憶的做法(ACE、ExpeL)。重點有三個:
**固定欄位**才好比對和搜尋;**不刪除只推翻**才不會讓舊錯誤復活;**短索引先讀、細節按需打開**,AI 才不會被一大坨文字淹沒。
細節見 [`AGENTS.md`](AGENTS.md) 第四節。
