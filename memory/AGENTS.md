# memory/ —— 給 AI agent 的讀寫規程

這裡是 sim-forge 的**經驗記憶**:每一條都是某次實作真的踩到、而且查清楚(或標明沒查清楚)的問題與解法。
目的只有一個:**同樣的坑不要踩第二次**。適用於 `sims/` 底下所有模擬,也適用於 `tools/`(含 `tools/parcel-forge`)。

```
memory/
  AGENTS.md        ← 你正在讀:讀取規程 + 寫入規程 + 格式規格
  INDEX.md         ← 一行一條的索引,依領域分組(自動產生)—— 每次動手前讀這份
  lessons/         ← 單一來源:一條教訓一個檔,詳細版(現象/根因/做法/驗證/證據)
  HANDBOOK.md      ← 給人看的踩坑手冊(自動從 lessons 的「人話」段產生),你不需要讀
  README.md        ← 給人看的說明
  templates/       ← 新教訓模板
  memtool.py       ← find / show / new / build / check(系統 python3 即可)
```

---

## 一、讀取規程(動手實作之前,必做)

1. **讀完整份 `INDEX.md`**(約 150 行)。開頭的交叉表列出每個領域的主條目與相關條目(粗體 = 嚴重度高),
   後面每行一條規則加上「何時想起」。
2. **判斷這次任務碰到哪些領域**(`env usd render rigid surface volume attach ui measure pipeline geometry workflow`),
   把這些領域裡 **嚴重度「高」的全部打開讀**,另外打開「何時想起」跟你這次要做的事對得上的。
   找不到時用關鍵字查:`python3 memory/memtool.py find <關鍵字>`(英文 API 名稱通常最準,例如 `contactOffset`、`restShapePoints`)。
3. **對版本**。每條有 `versions`。你的 Isaac Sim / PhysX 版本不同時,這條只能當**假設**:先用最小探針重驗,再決定照不照做。
   (sims 主要是 5.1.0;`tools/parcel-forge` 是 6.0.1;兩者 API 不一樣,見 L0002。)
4. **在計畫裡寫出你會遵守的條目**,格式:`遵守記憶:L0024(薄板 offset)、L0035(層間距不是彎曲)…`。
   使用者看得到你讀了哪些、漏了哪些。
5. **衝突時以記憶為準**。程式註解、舊報告、舊交接文件可能寫著已被推翻的結論(INDEX 最後一節「已推翻」)。
   看到舊註解跟記憶矛盾,照記憶做,並在回報裡指出那個舊註解。記憶本身若跟你的實測矛盾 → 照第二節把它標成 `disputed`。

> 不要把整個 `lessons/` 一次讀完 —— 浪費 context。INDEX → 相關的幾條,就夠了。

---

## 二、寫入規程(做完之後 / 卡住解開之後)

### 什麼時候要寫

符合任一條就寫:

- 花掉 **≥ 30 分鐘** 或 **一整段模擬** 才查出來的問題;
- **結果是錯的但沒有報錯**(安靜地失敗、假 PASS、數字好看但無效);
- 官方文件 / API 名稱 / 程式註解 / 前人結論說 A,**實測是 B**;
- 修正或推翻既有的教訓。

不要寫:打錯字、看程式就知道的事、一次性的環境意外、沒有任何證據的猜測。

### 怎麼寫

1. **先查重**:`memtool.py find <關鍵字>`。已經有類似的 → **改那一條**(補證據、補版本、補「試過但無效」),不要開新的。
2. 開新的:`python3 memory/memtool.py new --domain <主領域> --title "<一句祈使句規則>" --slug <英文短名>`,照模板填。
3. **數字要有出處**:run 目錄、log、`檔案:行號`、commit。數字照抄,不要四捨五入成「大約」。
4. **信心照實標**(沿用 sim-forge `params.py` 的精神):
   - `measured`:有對照組 / 前後數字的實測;
   - `observed`:看到過、可重現,但沒做對照;
   - `inferred`:推測,沒驗證 —— 根因段要寫「推測」兩個字。
5. **不刪除,只推翻**(照 ADR 的做法):
   新開一條寫正確的結論,`supersedes: [舊編號]`;舊的那條改 `status: superseded`、`superseded_by: 新編號`,內文不動。
   證據互相矛盾、還沒定論 → `status: disputed`,兩邊證據都列。
6. **增量修改**:只改你有新證據的那幾行。不要整條重寫別人的教訓,也不要把好幾條「濃縮」成一條 —— 細節被壓掉就是記憶失真的開始。
7. 寫「人話」段:**問題** 一兩句、**做法** 一到三點,不放數字與 API 名稱堆疊,讓沒碰過 Isaac 的人也看得懂。
8. 跑 `python3 memory/memtool.py build && python3 memory/memtool.py check`,兩個都要過。
9. commit 訊息用 `memory: L00xx <規則>`,跟程式修改分開 commit。

---

## 三、格式規格

檔名 `lessons/L<四位數>-<英文短名>.md`。frontmatter 欄位:

| 欄位 | 必填 | 說明 |
|---|---|---|
| `id` | ✓ | `L0001` 起,不重用 |
| `title` | ✓ | 一句**祈使句**規則(「薄板的 contactOffset 要小於板厚」,不是「contactOffset 問題」) |
| `status` | ✓ | `active` / `superseded` / `disputed` |
| `severity` | ✓ | `high` 結果錯或整段白跑 · `medium` 浪費時間 · `low` 小麻煩 |
| `confidence` | ✓ | `measured` / `observed` / `inferred` |
| `domains` | ✓ | 第一個是主領域(決定 HANDBOOK 放哪一章),其餘是次領域 |
| `tags` | | 檢索用關鍵字,API 名稱、旗標名 |
| `triggers` | ✓ | **何時該想起這條**:「要做什麼事之前」。這是檢索的關鍵欄位,寫具體動作 |
| `versions` | ✓ | 在哪個 Isaac Sim / PhysX 版本驗證過 |
| `scope` | | 在哪個 sim / tool 碰到的 |
| `evidence` | ✓ | 檔案路徑、run id、commit |
| `related` / `supersedes` / `superseded_by` | | 互相引用,`check` 會驗 |
| `observed` | ✓ | 第一次碰到的日期 `YYYY-MM-DD`(或 `YYYY-MM`) |

清單可寫 `[a, b]`(項目內不要有半形逗號,改用「、」)或換行 `  - item`。

內文段落:`## 人話`(含 `**問題**:` 與 `**做法**:`)、`## 現象`、`## 根因`、`## 做法`、`## 證據` 必填;
`## 驗證方法`、`## 試過但無效` 選填但強烈建議。

---

## 四、這套結構參考了誰

- **NASA Lessons Learned(LLIS)/ ITIL 已知錯誤資料庫**:固定欄位「現象 → 根因 → 做法 → 證據」,能被比對、能被搜尋。
- **ADR(Architecture Decision Records)**:紀錄不刪除,推翻時用 `superseded_by` 串起來 —— 舊程式註解還在,讀的人才知道它已過時。
- **Google SRE 的無究責事後檢討**:寫「怎麼驗證、怎麼防」,不寫是誰的錯。
- **ACE(Agentic Context Engineering, 2025)/ ExpeL**:agent 的經驗記憶要「一條一條、增量更新」,
  整份重寫或過度摘要會讓細節流失(context collapse);每條附觸發情境方便檢索。
- **分層載入(Claude Code memory、Agent Skills 的 progressive disclosure)**:短索引永遠先讀,詳細內容按需打開。
- **AGENTS.md 慣例**:資料夾裡 `AGENTS.md` 給 agent、`README.md` 給人。
