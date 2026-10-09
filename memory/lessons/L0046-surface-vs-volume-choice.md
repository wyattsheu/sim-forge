---
id: L0046
title: 選 surface 或 volume deformable 前,先用「夾得住、外觀、物理、速度」四軸比較
status: active
severity: medium
confidence: measured
domains: [surface, volume]
tags: [surface deformable, volume deformable, decision, tetrahedral, grasp, self penetration, determinism]
triggers: [開始一個新的包材或布料模擬, 決定要不要從 surface 換成 volume]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/PLAN_phase3_20261007.md, sims/fr3_bubblewrap_pack_20261007/README.md 第二節, sims/fr3_bubblewrap_pack_20261007/work/tests/README.md vol 一節]
related: [L0047, L0052, L0063]
observed: 2026-10-07
---

## 人話

**問題**:軟包材有兩種做法:沒有厚度的「膜」和有厚度的「薄板」。兩種各有強弱,選錯會在後面才發現夾不住或外觀不對。

**做法**:開工前照下面四個面向比較;需要穩定重現和少穿模就偏向有厚度的,需要包得密、角落自然就偏向膜。

## 現象 / 2026-10-07 的比較

| 軸 | surface(零厚度膜) | volume(4 mm 四面體板) |
|---|---|---|
| 夾得住 | 間隙 1.5~2 mm(= 2 × rest)可夾,滑動 0.3~0.5;懸出邊會垂直垂下,接近方式要改(L0052) | 間隙 2~5 mm 可夾;整包只夾到 3 點(網格粗) |
| 外觀 | 包得密、角落皺褶自然;開蓋後布彈起、頂面小洞 | 角落翹耳要側板;撐滿內腔;開蓋後 93% 覆蓋 |
| 物理 | 自穿模 97~156;穿杯 0;同參數兩次差 6 mm | 自互穿 ≤ 8;穿杯 0;重現 ≤ 2 mm;純彈性無塑性 |
| 速度 | 2~3 分 / 段 | 4 分全程(約 5× 實時) |

volume 定案材料:E 2e3、ν 0.45、板厚 4 mm、面密度 0.1 kg/m²、manual 35×35×1 四面體(5-tet 鏡像)、contact 2 / rest 0.5 mm、solver 128、dt 1/240、布 500×500。

## 根因

surface 靠碰撞 offset 撐厚度(L0035)、非決定性較大;volume 有真實厚度、但網格粗且無塑性。

## 做法

用上表判斷;決定寫進 `DECISION_*.md` 並附這張表的最新數字。驗收門檻兩者不同(`tests/README.md`:surface 自穿模用相對門檻、vol 自互穿 0 / 1~20 / > 20)。

## 證據

`work/PLAN_phase3_20261007.md` 待決表;fr3 README 第二節定案材料。
