---
id: L0076
title: 驗證腳本和量測工具要收進 repo,scratchpad / /tmp 不會長存
status: active
severity: medium
confidence: observed
domains: [workflow]
tags: [scratchpad, /tmp, reproducibility, verification scripts]
triggers: [在暫存目錄寫了驗證或量測腳本, 報告引用一支暫存腳本]
versions: 與版本無關
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/FOLDORDER_NOTES.md §3、§7]
related: [L0075]
observed: 2026-09-30
---

## 人話

**問題**:AI 常把驗證用的小程式寫在暫存資料夾,報告裡引用了它,但那個資料夾過幾天就會被清掉,之後沒人能重現。

**做法**:被報告引用、或之後還會用到的腳本,一律搬進專案資料夾並一起存進版本控制。

## 現象

`verify_mug_pose.py`、`selfcheck_C.py`、`test_foldorder_logic.py` 都放在 `/tmp/claude-0/.../scratchpad/`,文件引用了這些路徑;FOLDORDER_NOTES 自己寫「scratchpad 不保證長存,要留的話複製到 scripts/」。

## 根因

暫存目錄是 session 層級的。

## 做法

結論依賴的腳本放進 `<sim>/scripts/` 或 `tests/`,commit;文件引用 repo 內路徑。

## 證據

FOLDORDER_NOTES §3 量測腳本路徑與 §7 最後一點。
