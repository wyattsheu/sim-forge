---
id: L0035
title: 布疊層每層約 5 mm 是碰撞距離造成的,縮小 contactOffset 只會互穿,不是變薄
status: active
severity: high
confidence: measured
domains: [surface, measure]
tags: [contactOffset, restOffset, layer gap, self collision, interpenetration, springback, surfaceThickness, layer_gap.py]
triggers: [想把包裹壓薄或壓小, 布疊層太厚, 調 cont/rest/thick/solver 參數, 解釋回彈的原因]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/EXPERIMENTS.md 02_offsets、04_press_isolate、08_crease, sims/fr3_bubblewrap_pack_20261007/work/REPORT_THICKNESS.md §2, sims/fr3_bubblewrap_pack_20261007/work/學長說明_20261002.md, sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #13]
related: [L0034, L0042, L0057]
observed: 2026-09-30
---

## 人話

**問題**:包好的包裹壓不扁:壓下去一放手就彈回來。原因不是布本身有彈性,而是模擬裡「布碰到布」會保持一個最小距離,大約每層 5 mm。把這個距離調小,布會直接互相穿過去,看起來變薄其實是假的。

**做法**:維持原本的碰撞距離。每層 5 mm 跟真實小泡泡紙差不多,可以接受;如果規格要求很薄的膜,那要換一套物理做法,不是調參數。

## 現象

- 杯子高 93 mm,包完 122~130 mm;杯頂上 4~5 層布,每層 4.3~5.6 mm。
- 壓到 117 mm,放開彈回約 130。
- contactOffset 5 → 2 mm:層間距 5.46 → 5.44(沒變),自穿模 13 → 400~3700(互穿)。
- 只縮 restOffset 1 → 0.2:層間距減半(8.81 → 4.07),但自穿模翻倍。
- bend 4 → 1:回彈更大(放開 152)。solver 128 + 碰撞迭代 ×2:救不回互穿。surfaceThickness 10 → 4:層間距沒變(4.37 vs 4.20)。
- 把 rest shape 設成壓扁的形狀:照樣彈回 134 → 撐開層的不是彎曲。

## 根因

布對布自碰撞的靜止距離(由 contact/rest offset 決定)把層撐開。真實小泡泡紙一層 3~4 mm,所以這個數字物理上不離譜。

## 做法

- **維持 `--cont 0.005 --rest 0.001`**。
- 任何縮 offset 的結果標「互穿,高度不可信」,不採用。
- 規格要求 < 100 mm(每層 < 1.5 mm)= 換材料口徑(薄膜物理),要另開一條路並處理互穿;先跟使用者確認口徑(A 泡泡紙 / B 薄膜)。
- 能真正改善的是幾何:讓兩片真的疊起來(`--tip_over_mm`,L0042)、縮小布(`--sheet_mm 400`)。

## 驗證方法

每次調參同時看 `layer_gap.py`(層數 / 層間距)與自穿模 S1;層變薄但 S1 暴增 = 互穿。

## 證據

EXPERIMENTS 02 / 04 / 08;REPORT_THICKNESS §2;PITFALLS #13。
