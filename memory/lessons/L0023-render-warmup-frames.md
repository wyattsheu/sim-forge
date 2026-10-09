---
id: L0023
title: 影片第 0 格和 replicator 第一次 step 是暖機,串接或量測前要丟掉
status: active
severity: low
confidence: observed
domains: [render, pipeline]
tags: [warmup, ffmpeg, trim, replicator, orchestrator.step, frame 0]
triggers: [串接多段模擬影片, 從影片抽格量測, 用 replicator writer 存圖]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007, sims/wrapped_mug]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #14, sims/wrapped_mug/docs/FINDINGS.md §16, sims/fr3_bubblewrap_pack_20261007/README.md 第一節串接指令]
related: []
observed: 2026-09-30
---

## 人話

**問題**:每段影片的第一格是渲染器還沒準備好時拍的,串起來每段開頭會閃一下黑畫面或舊畫面;存圖工具第一次也可能只寫了資料沒有圖。

**做法**:串接前每段剪掉開頭半秒;抽格量測不要用第一格;存圖前先空跑一次。

## 現象

串接影片每段開頭閃一格舊畫面 / 黑畫面;replicator writer 第一次 `orchestrator.step()` 只寫 metadata。

## 根因

第 0 格在 renderer 暖機時抓的。

## 做法

```bash
ffmpeg -y -ss 0.5 -i seg/wrap.mp4 -c:v libx264 -pix_fmt yuv420p -crf 20 seg/trim.mp4
```
replicator:先跑一次 `orchestrator.step()` 暖機,再算正式那張。

## 證據

PITFALLS #14;FINDINGS §16。
