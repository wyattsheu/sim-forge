---
id: L0068
title: 續跑別人的 run 時從 log 開頭和影片標籤反查指令,不要憑記憶拼;搬家後留路徑對照表
status: active
severity: medium
confidence: measured
domains: [pipeline, workflow]
tags: [reproduce, log header, video label, MOVED.txt, grep, NameError SIDE2]
triggers: [接手別人跑過的模擬, 舊文件裡的路徑找不到, 重現一支舊影片]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/ADAPTING.md §6, sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #18, sims/fr3_bubblewrap_pack_20261007/work/README.md 兩支 DEMO]
related: [L0066, L0067, L0064]
observed: 2026-10-02
---

## 人話

**問題**:接手別人的模擬時,憑印象拼出來的指令常常漏參數,結果不一樣甚至直接報錯;資料夾整理過之後,舊文件寫的路徑也會找不到。

**做法**:從紀錄檔開頭和影片上的參數標籤把指令反查回來;整理資料夾時留一份「舊路徑 → 新路徑」對照表。

## 現象

- 漏掉 `--floor_edges` → `NameError: SIDE2 is not defined`;同時給 `--unbox --stage2` 也 NameError(已補守衛)。
- 2026-10-02 整理成 `runs/NN_*/` 後,REPORT / HOW_TO_VIEW 寫的 `out_c1/wrap.npz` 失效。
- `DEMO_old_order_sheet400.mp4`(v1)沒留清單,來源不明。

## 根因

指令沒有被完整保存;路徑寫死在文件裡。

## 做法

- 兩個可靠來源:影片底部參數標籤(`E=2e+04 bend=4e+00 solver=64`)與 `wrap_sim.log` 開頭 30 行(每個啟用的旗標各印一行)。
- 反查:拿 log 的某行訊息去 grep 腳本,就知道是哪個旗標(例:`★ 第二段:布以第一段的結果出生` → `--init_npz`)。
- 每個 run 存 `X.stdout`(含完整指令列);影片保留串接清單 `lists/*.txt`;沒清單的影片不要引用。
- 搬家留 `MOVED.txt`。

## 證據

ADAPTING §6 對照表;PITFALLS #18;work/README DEMO 段。
