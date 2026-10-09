---
id: L0047
title: 載入折好狀態的 volume 板時,restShapePoints 要設成那個快照形狀,否則第一步就彈開
status: active
severity: high
confidence: measured
domains: [volume]
tags: [restShapePoints, rest_npz, snapshot, volume deformable, springback, TetMesh]
triggers: [從 npz 載入已折好或已入箱的 volume 包材繼續模擬, 載入後第一步布就彈開]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/vol/grip/probe_g3.py 檔頭, sims/fr3_bubblewrap_pack_20261007/vol/wrap_vol.py --rest_npz]
related: [L0034, L0046]
observed: 2026-10-07
---

## 人話

**問題**:把一個已經折好的有厚度包材存起來、下次接著模擬時,如果它的「原始形狀」還是平的,一開始就會彈開,因為原本壓住它的東西沒辦法一模一樣重建。

**做法**:接著模擬時把原始形狀設成存下來的那個樣子。代價是它不會再有回彈力,會比真的更服貼,結論要註明這點。

## 現象

rest = 平板、points = 折疊狀態 → 第 1 步就彈開:最大位移 71 mm、自穿 114。

## 根因

在 `wrap_vol.py` 裡把板壓住的接觸(杯子凸分解、蓋子、層間)在新模擬裡無法 1:1 重建。

## 做法

`--rest snap` / `--rest_npz`:restShapePoints = 快照形狀,points 也是快照。在結果裡標明「布沒有回彈力,比真的更服貼」。

## 證據

`vol/grip/probe_g3.py` 檔頭 ★ 註解。
