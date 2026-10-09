---
id: L0065
title: 必要輸入找不到就直接中止,不要安靜地用預設值繼續跑
status: active
severity: high
confidence: measured
domains: [pipeline, measure]
tags: [silent fallback, carton meta, floor_edges.json, SystemExit, guard, meta_guard]
triggers: [寫讀取設定檔或中間檔的程式, 加一個「找不到就用預設」的分支, 階段名稱照印但畫面沒變]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #1、#17, sims/fr3_bubblewrap_pack_20261007/work/REPORT_20260930.md §1 結論 7, sims/fr3_bubblewrap_pack_20261007/work/FOLDORDER_NOTES.md §2.5, sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~508]
related: [L0014, L0066]
observed: 2026-09-30
---

## 人話

**問題**:程式找不到需要的設定檔時,如果只是印個警告就用預設值繼續跑,整段模擬看起來正常完成,其實結果是錯的。曾經入箱這一段「從來沒真正跑過」,蓋子根本沒動,但 log 照樣印「關蓋」。

**做法**:必要的檔案找不到就讓程式直接停下來並說明原因;檢查腳本也要把這種警告當成失敗。

## 現象

- `--carton X.usd` 用檔名推 `X.meta.json`;找不到 → `LIDS` 空、內腔用整箱 bbox 猜 → log 照印 close lower/upper flaps,影片蓋子沒動,`out_bl_box` 布 148 點高於口。
- 舊折序量的 `floor_edges.json`(鍵 xp/xn)配新折序 → `FLOORE.get("yp", [])` 全空 → 後兩折一個錨點都不建,y 邊安靜地沒折到。

## 根因

「找不到就猜」的 fallback 把錯誤變成錯的結果。

## 做法

```python
if set(FLOORE) != set(STAGE2_SIDES):
    raise SystemExit("★ %s 的鍵 %s 不是後兩折 %s —— 這份是舊折序量的,要重量" % ...)
```
- meta 找不到:印 `⚠ 找不到 … —— 沒有 meta 就不要猜鉸鏈位置`,而且 `tests/run_checks.py` 的 `meta_guard` 直接 FAIL。
- 需要的 symlink(`carton_w131.meta.json`)保留在工作目錄。

## 證據

PITFALLS #1、#17;REPORT_20260930 §1 結論 7「入箱段從來沒有真正跑過」;FOLDORDER_NOTES §2.5。
