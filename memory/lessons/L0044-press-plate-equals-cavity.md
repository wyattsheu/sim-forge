---
id: L0044
title: 六面壓實的平板要剛好等於箱內尺寸,只壓頂面布會往旁邊攤
status: active
severity: medium
confidence: measured
domains: [surface, geometry]
tags: [press6, press plate, cavity, compaction, kinematic plate]
triggers: [用壓板壓實包裹, 設定 --press6 目標]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007, sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py --press6 help、~1057-1060, sims/fr3_bubblewrap_pack_20261007/work/REPORT_THICKNESS.md §3, sims/fr3_bubblewrap_pack_20261007/work/README.md「不跑 c3」]
related: [L0031, L0035]
observed: 2026-09-25
---

## 人話

**問題**:只從上面壓包裹,布會往旁邊攤開;壓板比箱子小一點,布就從縫擠出去,越壓越高。另外壓實目標是照箱子訂的,不是照杯子訂的,側面其實沒被壓到。

**做法**:壓板做得跟箱子內部一樣大;換物品或換折法時,壓實目標重新從「不壓時的自然大小再小 10~15%」來訂。

## 現象

- 只壓頂面:239×233 攤成 284×270,撐破箱壁。
- 平板 240×200(比內腔小)→ 布從 12 mm 縫擠出去,越壓越高(165 → 189、211 → 258)。
- 新折序壓完放開 y 彈到 248~250 > 內腔 224 → 入箱 24 點穿牆,所以定案鏈**不跑 c3 壓實**,四折後直接入箱。

## 根因

kinematic 平板與箱壁彼此不解算,可以齊平;有縫布就無處可逃以外的地方可逃。

## 做法

- 平板 = 內腔(264×224);`--press6 W,L,H` 的 W 沿 x、L 沿 y。
- 訂法:先不壓跑一次讀自然 bbox,再往下 10~15%;確認 W < 264、L < 224、長邊沒對調。
- 舊的 `250,210,115` 是舊方位挑的,不要沿用。

## 證據

`wrap_sim.py` 註解數字;REPORT_THICKNESS §3;work/README「不跑 c3」。
