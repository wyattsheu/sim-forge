---
id: L0011
title: 要給人在 UI 按 Play 的 USD,一定要自帶調好的 PhysicsScene
status: active
severity: high
confidence: measured
domains: [usd, rigid, ui]
tags: [PhysicsScene, TGS, position iterations, 120 Hz, UI Play, World defaults, sink]
triggers: [交付一個會在 UI 裡按 Play 的 USD, headless 測試都過但使用者說東西會陷下去]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/README.md §2、§8.2, sims/fr3_bubblewrap_pack_handoff_20261007/sim/ui_path_check.py]
related: [L0010, L0061]
observed: 2026-10-07
---

## 人話

**問題**:場景檔如果沒有自己的物理設定,在介面上按 Play 時 Isaac 會自動補一個很弱的預設值,紙箱會陷進桌子裡。用程式跑的測試卻不會出現,因為程式那條路用的是另一組比較好的預設值。

**做法**:交付檔一律寫入調好的物理設定;驗收要走「開檔 → 按 Play」跟使用者一樣的路徑,不能只用程式那條路。

## 現象

| 路徑 | 紙箱最大下沉 |
|---|---|
| `scene_final.usd` 在 UI 按 Play | **48.12 mm** ❌ |
| `scene_final_ui.usd`(自帶 PhysicsScene)按 Play | 0.00 mm |
| headless `scene_physics_check.py`(isaacsim.core `World`) | 0.00 mm(所以一直沒發現) |

另有 log:`foundLostAggregatePairsCapacity to 3418`。

## 根因

沒有 PhysicsScene 時 UI 自動建一個預設的:60 Hz、position iteration 1、velocity iteration 0,撐不住 3 mm 薄板上的紙箱。`isaacsim.core.World` 自己會套比較好的 solver 預設值,把問題遮掉。

## 做法

USD 內寫 `/physicsScene`:120 Hz、TGS、min position iterations 8、min velocity iterations 1、GPU found/lost aggregate pairs 8192。用 deformable 時再加 deformable contact capacity、collision stack(handoff §8.6 的值)。

## 驗證方法

用 `ui_path_check.py` 這種「開檔 → `timeline.play()` → 量」的腳本驗收,並跑一個**沒修的對照**確認它會 FAIL(48 mm)。

## 證據

`sims/fr3_bubblewrap_pack_handoff_20261007/README.md` §8.2 三路對照表、§10 已知問題 #1、#5。
