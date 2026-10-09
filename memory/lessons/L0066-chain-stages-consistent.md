---
id: L0066
title: 多段模擬鏈的每一段要用同一版腳本、帶完整的共用參數,接續前比對 log 第一行
status: active
severity: high
confidence: measured
domains: [pipeline]
tags: [init_npz, shared params, script version, mug orientation, sheet_mm, mug_orient, chain]
triggers: [用上一段的 npz 接著跑下一段, 改了腳本後接舊的中間結果, 手打每段的指令]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #6、#10, sims/fr3_bubblewrap_pack_20261007/work/FOLDORDER_NOTES.md §2.3, sims/fr3_bubblewrap_pack_20261007/README.md 第一節 C=…]
related: [L0065, L0067, L0068]
observed: 2026-10-02
---

## 人話

**問題**:模擬分好幾段接著跑時,如果中間改過程式,或某一段漏打一個共用參數,接起來的結果會錯但不會報錯。例如杯子方向跟包材對不上,或用錯布的尺寸算長度。

**做法**:共用參數寫成一個變數,每段都帶;同一條鏈用同一版程式;接續前比對上一段 log 開頭記的關鍵資訊。

## 現象

- c3 漏 `--sheet_mm` → 邊長比中位 0.769 / 0.688,log 寫布 586(用預設布算攤平長度)。
- `sh400_mb_yz`:杯子方位跟包裹不合 —— `--init_npz` 只拿杯子平移,方位由**當下腳本**的 `_Rm` 決定,舊折序包裹配新腳本就錯。
- patch 前產生的所有 npz 都不能再餵 `--init_npz`(那時布包在 杯口 −x / 杯耳 −y 的杯子外面)。

## 根因

npz 只存頂點位置;方位與幾何參數由執行當下的腳本與旗標決定。

## 做法

- `C="--tex … --sheet_mm 400 --layer_mm 5 …"`,每段 `$P wrap_sim.py $C <段落旗標>`。
- 同一條鏈同一版腳本;腳本改了就從頭重跑。
- log 第一行「杯子躺平 W x D x H」要跟起點 run 一致;`run_checks.py` 的 `mug_orient` 會比、`edge_ratio` 會抓漏參數。

## 證據

PITFALLS #6、#10;FOLDORDER_NOTES §2.3。
