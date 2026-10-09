---
id: L0033
title: 搬箱時布會穿過薄底板被地板摩擦拖住,要加厚底板碰撞並關掉地板碰撞
status: active
severity: high
confidence: measured
domains: [surface, rigid]
tags: [base_collider_pad, no_ground_collision, movebox, friction, thin floor, carry]
triggers: [搬動裝著 deformable 的箱子, 包裹相對箱子滑動]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #9, sims/fr3_bubblewrap_pack_20261007/work/EXPERIMENTS.md 10_box_move、探針 probe_fric_a~g]
related: [L0029, L0024]
observed: 2026-09-30
---

## 人話

**問題**:搬箱子時,箱裡的包裹會往後滑好幾公分。原因不是箱底太滑,而是包材被杯子壓得穿過很薄的箱底,碰到下面的地板,被地板的摩擦力拉住。

**做法**:箱底下面加一層看不見、比較厚的碰撞層,讓包材穿不過去;搬箱時把用不到的地板碰撞關掉。

## 現象

| run | 設定 | 包裹相對箱子滑動 |
|---|---|---|
| `mb2_x30` | 預設 | 35.3 mm |
| `mb4_x30` | 地板降 2 cm | 7.7 mm |
| `mb5_x30` | 只加厚底板 | 17.1 mm |
| `mb6_x30` | 加厚 + 關地板碰撞 | 7.3 mm |
| `fincam_mb_x30` | 定案鏈 | 1.7 mm |

摩擦探針:kinematic 板平移 300 mm,布質心相對板只差 0~5.8 mm —— 板子帶得動布。

## 根因

3 mm 底板被布頂點壓穿 → 頂點碰到地板 → 被地板摩擦留住。

## 做法

`--base_collider_pad 0.02 --no_ground_collision`(視覺地板保留,只關碰撞)。物理交付版同理:20 mm 隱形墊片,但要記得過濾它跟桌子(L0029)。

## 試過但無效

`--move_mode ktarget`(PhysX kinematic target)34.7 mm;放慢搬運 36.1 mm。

## 證據

PITFALLS #9;EXPERIMENTS 10_box_move。
