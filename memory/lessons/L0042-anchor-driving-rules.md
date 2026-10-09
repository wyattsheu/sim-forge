---
id: L0042
title: 錨點的終點幾何決定包裹高度;驅動錨點時直接跟隨、不要外推,後折只驅動還貼地的邊
status: active
severity: high
confidence: measured
domains: [surface, attach]
tags: [anchor, hold_mm, tip_over_mm, LZ_HOLD, extrapolation, floor_edges, stage2, set_world_pose]
triggers: [寫或調整用錨點折布的程式, 包裹疊得太高, 布被甩飛]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/REPORT_20260930.md §1, sims/fr3_bubblewrap_pack_20261007/work/EXPERIMENTS.md 03_anchor、05_tipover_thin, sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~1462-1480、--floor_edges help]
related: [L0035, L0050, L0040]
observed: 2026-09-25
---

## 人話

**問題**:包裹疊得很高,不是因為碰撞參數,而是拉布的「錨點」最後停的位置把布吊在半空;兩片布只在中線碰頭,沒有真的疊起來。另外,讓錨點預測下一步位置會越拉越遠,把布甩飛。

**做法**:錨點終點壓低、讓兩片布越過中線重疊;錨點直接跟著布走,不要預測;已經被前面折起來的部分不要再硬拉。

## 現象

- 每折尖端被釘在 杯頂 + 12 mm + 第幾折 × layer_mm(+12/+20/+28/+36),第二段再用 100 個 hold 錨釘死前兩折,壓實段還建 4 個錨把邊中點釘在起始高度 → 布是被吊著不是疊著。
- 兩片在中線對接只重疊 20 mm 寬,`layer_gap` 中位 1 層。
- `--tip_over_mm 40`:中位 2 層,自穿模 三段 2 / 55 / 144(基準 13 / 257 / 512),壓實放開 133(基準 163)—— **唯一乾淨的改善**。
- 錨點一階外推 `pos = cur + (cur - prev)`:正回饋,布被甩到 463 mm 高、bbox 670 mm(比布本身 586 mm 還大)。

## 根因

無窮硬 attachment 的終點幾何直接決定布的位置;外推讓錨點超前 → 拉更遠 → 差更大。

## 做法

- `--hold_mm`(≥ thick + 2 mm,定案 6)、壓實 / 入箱 / 搬箱段 `--no_anchor`。
- 要疊就讓尖端越線 `--tip_over_mm`(實驗 40;定案鏈 0 是因為改了布尺寸與折序,見 EXPERIMENTS 11)。
- 還沒輪到的錨點:`set_world_pose(position=cur)` 直接貼著頂點走(約束力 ≈ 0),不要外推。
- 後兩折只驅動「兩折版實測仍貼地」的那條邊(`floor_edges.json`);已被前兩折帶上去的繼續跟著布走。

## 證據

REPORT_20260930 §1 結論 1、4;EXPERIMENTS 03、05;`wrap_sim.py` 2026-09-25 外推註解。
