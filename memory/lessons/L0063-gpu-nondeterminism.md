---
id: L0063
title: GPU deformable 不是決定性的:差 6 mm 內當噪音,關鍵結論跑兩次,A/B 要餵同一個起點
status: active
severity: high
confidence: measured
domains: [measure, surface, pipeline]
tags: [nondeterminism, GPU, noise, reproducibility, init_npz, A/B test, states npz]
triggers: [比較兩組參數的結果, 重跑一次結果不同, 交付時要給參考數字]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #5, sims/fr3_bubblewrap_pack_20261007/work/README.md, sims/fr3_bubblewrap_pack_handoff_20261007/README.md §8.4, sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/ADAPTING.md §5]
related: [L0046]
observed: 2026-09-30
---

## 人話

**問題**:同樣的設定跑兩次,軟物體的結果會差幾公釐,偶爾某一折還會滑開。拿單次結果比較兩組參數,可能只是在比運氣。

**做法**:差距在 6 mm 以內當成誤差;重要結論至少跑兩次;比較兩組參數時一定從同一個存檔起跑;交付時用存下來的狀態檔當標準答案。

## 現象

- 同一組旗標兩次 bbox 差數 mm(約 6 mm);偶發一折滑開。
- DEMO 重跑:長度一樣 62.2 s,但入箱後布頂點平均差 24.8 mm、最大 130 mm,杯子剛性偏 11.5 mm;搬箱後包材相對箱子 2.5 / 9.1 / 4.3 mm(三次)。
- volume 版重現 ≤ 2 mm。

## 根因

推測:GPU 解算非決定性 + 接觸敏感(未查實)。

## 做法

- 差 < 6 mm 當噪音;關鍵結論至少兩次;影片要看。
- A/B 一定餵同一個 `--init_npz`;確認方法:第 0 格 bbox 相同(平移不改變 bbox 尺寸)。
- 交付以 `states/*.npz` 為參考,不以重跑為準;`scene_final.usd` 用交付的 `states/box.npz`。

## 證據

PITFALLS #5;handoff README §8.4 重現性表;ADAPTING §5。
