---
id: L0075
title: 別的 agent 正在改的檔案不要直接改,產 patch 並記錄基準 md5,套用前 dry-run
status: active
severity: high
confidence: measured
domains: [workflow]
tags: [multi-agent, concurrent edit, patch, md5, dry-run, rebase]
triggers: [多個 agent 同時在同一個資料夾工作, 要修改一支正在被其他實驗使用的腳本]
versions: 與版本無關
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/FOLDORDER_NOTES.md 開頭與 §5]
related: [L0076]
observed: 2026-09-30
---

## 人話

**問題**:好幾個 AI 同時在同一個資料夾工作時,如果直接改別人正在用的程式,會打斷對方正在跑的實驗,兩邊的修改也會互相覆蓋。

**做法**:不要直接改,把修改做成一份「補丁檔」,記下改之前那個檔案的指紋;等對方跑完再套用,套用前先試套一次確認沒衝突。

## 現象

`work/wrap_sim.py` 在工作期間被另一位 agent 改了兩次(02:44 加 `--release_after/--no_hold`、02:50 改放手方塊),patch 要 rebase 兩次;rebase 時一度漏重放 `ORD_` 一處,邏輯測試抓到(selfcheck 11/12)。

## 根因

共用檔案被多方同時修改。

## 做法

```bash
md5sum wrap_sim.py                       # 記錄基準
diff -u wrap_sim.py wrap_sim_mine.py > foldorder.patch
patch -p0 --dry-run < foldorder.patch && patch -p0 < foldorder.patch
```
- 文件寫明基準 md5、每個 hunk 的理由、「別人的程式碼一行都沒動」。
- rebase 後驗證:「我的檔(舊基準)→ 我的檔(新基準)」的 diff 恰好只有對方的 hunk。
- 用從檔案**抽出真正程式片段**的邏輯測試驗證,而不是重寫一份邏輯來測。

## 證據

FOLDORDER_NOTES 開頭(md5 `8b8dfa3e…`)與 §5 驗證表。
