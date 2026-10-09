---
id: L0034
title: surface deformable 的折痕要把「折好的形狀」寫成 restShapePoints,restBendAngles 在 5.1 被忽略
status: active
severity: high
confidence: measured
domains: [surface]
tags: [restShapePoints, restBendAnglesDefault, restShapeDefault, restBendAngles, restAdjTriPairs, flatDefault, crease]
triggers: [想讓布或膜保持折痕, 想讓包好的包材不要彈開, 讀到官方文件說可以設 restBendAngles]
versions: Isaac Sim 5.1.0-rc.19 / PhysX 107.3.26
scope: [sims/wrapped_mug, sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §1、§11, sims/wrapped_mug/experiments/p0b_crease_matrix.py, sims/fr3_bubblewrap_pack_20261007/work/EXPERIMENTS.md 08_crease, sims/fr3_bubblewrap_pack_handoff_20261007/README.md §8.6]
related: [L0035, L0037, L0047]
observed: 2026-09
---

## 人話

**問題**:想讓包材「記住」折痕,官方文件寫可以直接指定每條折線的角度,實際上這個設定完全沒作用。

**做法**:把「已經折好的樣子」直接設成包材的原始形狀,它就會維持那個形狀;這個原始形狀只能在開始模擬前設好,模擬中改沒用,所以要先離線算好再跑第二趟。

## 現象

三條懸臂膜條同場,只差靜止組態設法:

| 組 | 設法 | total_turn |
|---|---|---|
| C 對照 | 平的 rest,`flatDefault` | 156.5° |
| A | `restAdjTriPairs` + `restBendAngles` = 45° | 156.4°(與對照無異) |
| B | `restShapePoints` 折成 V + `restBendAnglesDefault="restShapeDefault"` | 247.2° |

fr3 的 08_crease 在 runtime 寫 `restBendAngles`:壓之前寫 → 放開 130、壓住時寫 → 134、對照 134 —— 一樣彈回。

## 根因

這版 PhysX 實作忽略 `restAdjTriPairs` / `restBendAngles`;官方文件與限制清單都沒寫(甚至舉了褲管摺線 75° 的例子)。另外官方限制:模擬中不能改 rest shape。

## 做法

```python
sa(prim, "omniphysics:restShapePoints", folded_points)           # 折好的形狀
sa(prim, "omniphysics:restBendAnglesDefault", "restShapeDefault", Sdf.ValueTypeNames.Token)
```
- 折痕要離線烘焙:第一趟模擬得到形狀 → 寫成 rest → 第二趟。
- 交付的物理包材(`scene_final_phys.usd`):沉降後的形狀同時寫進 points 與 restShapePoints,速度歸零。
- rest shape 只移除彎曲回彈,不移除重力 —— 每一段仍要有支撐(L0039)。

## 證據

`FINDINGS.md` §1 表格;EXPERIMENTS 08_crease;handoff README §8.6「a surface deformable's rest shape must be authored before Play」。
