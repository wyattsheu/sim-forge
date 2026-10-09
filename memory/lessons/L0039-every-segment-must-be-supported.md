---
id: L0039
title: 包材的每一段都要有東西撐著,自立或懸空的部分在重力下一定會倒或攤開
status: active
severity: high
confidence: measured
domains: [surface, geometry]
tags: [support, gravity, freestanding, tunnel profile, cross cutout, box wall, rest shape]
triggers: [設計包材的初始形狀或 rest shape, 包材靜置後攤開或往外倒]
versions: Isaac Sim 5.1.0-rc.19
scope: [sims/wrapped_mug, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §7、§8、§13, sims/fr3_bubblewrap_pack_handoff_20261007/README.md §8.6]
related: [L0034, L0041]
observed: 2026-09
---

## 人話

**問題**:就算把包材的「原始形狀」設成包好的樣子,只要有一段是懸空或自己立著的,重力還是會把它拉開或推倒,杯子就露出來。

**做法**:設計包法時讓每一段都靠在杯子、箱底或箱壁上;往上折的部分要貼著箱壁、不能高過箱緣。

## 現象

- 捲成 336° 筒狀包住杯子(rest = 筒,零彎曲能量):上緣懸空,300 步後 y ±50 mm 攤成 −98..+84 mm,杯子整個露出。
- 改「隧道」剖面(腳掌平貼箱底 → 垂直上升 → 頂部順杯子輪廓跨過 → 下降 → 腳掌):靜置漂移 74 mm → **7.6 mm**。
- 十字裁片的臂:臂根離牆 51 mm → 倒到箱外 43 mm;臂爬到 104.5 mm 而箱壁 87 mm → 整片被拖出箱外,漂移 297 mm。
- 四個角留料 → 高斯曲率衝突(會皺、會撐開)。

## 根因

rest shape 只消除彎曲回彈,不消除重力;沒有支撐的板一定倒。

## 做法

- 剖面每一段都要有支撐(杯子、箱底、箱壁),兩端最好被自己的重量壓住。
- 平面裁片折立體:四角不留料。
- 往上折的臂要靠牆爬,而且不超過箱緣;臂根圓角會再往外走 `corner_r`,`B + corner_r` 要留在內壁裡。
- 折角小於 90° 時尖端一邊往內一邊爬升,會超出箱緣 —— 要折過水平(約 100°)才會往下壓。

## 證據

`FINDINGS.md` §7、§8、§13;handoff README §8.6「the rest shape removes the bending spring-back but not gravity」。
