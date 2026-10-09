---
id: L0036
title: 布不動時先檢查 sleep / settling 參數和 bend 值;量回彈一律關 sleep
status: active
severity: high
confidence: measured
domains: [surface, measure]
tags: [sleepThreshold, settlingThreshold, settlingDamping, sleepy, no_sleepy, surfaceBendStiffness, bend 2e3]
triggers: [套用別人 USD 的 deformable 參數, 布在模擬中停住不動, 量測壓實後的回彈]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~746, sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/ADAPTING.md §3, sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #2, sims/fr3_bubblewrap_pack_20261007/work/EXPERIMENTS.md 03_anchor]
related: [L0035]
observed: 2026-09-24
---

## 人話

**問題**:布在模擬中「睡著」就不會再動:折疊做了等於沒做;壓實後量回彈,也會因為布睡著而以為沒有回彈。

**做法**:模擬折疊和量回彈時關掉讓布睡著的設定;抗彎參數用 4,不要用預設的 2000。

## 現象

- 套 `tex_bubble_mug.usd` 的 settling/sleep 三參數:布在 t=0.83 s 後 16 秒 bbox 一動也不動,折疊階段等於沒跑。
- `--bend` 預設 2e3 同樣讓布睡死。
- 壓住 = 放開(`v4a_c3` 114/114、`v1_c3` 132/132);加 `--no_sleepy` 後 `v4a_c3_nosleep` 放開 127。

## 根因

`settlingDamping=10`、`settlingThreshold=0.10`、`sleepThreshold=0.05` 讓布很快進入睡眠;很大的 bend 讓布幾乎不動也觸發睡眠。

## 做法

- 折疊與壓實段:`--no_sleepy`(不套那三個參數)。
- `--bend 4`(這條 pipeline 用的值);`--no_sleepy` 對 bend 2e3 幫助不大,真正原因是 bend。
- 量回彈必須關 sleep,否則數字不可信。

## 驗證方法

log 每秒印 bbox;連續數秒 bbox 完全不變而外力還在作用 → 布睡著了。

## 證據

`wrap_sim.py`「2026-09-24 實測:這三個一起上,布在 t=0.83s 後 16 秒 bbox 一動也不動」;ADAPTING §3「--bend 的預設值是 2e3,那會讓布直接睡死」;PITFALLS #2。
