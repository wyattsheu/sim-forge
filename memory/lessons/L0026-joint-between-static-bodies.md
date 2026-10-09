---
id: L0026
title: 兩端都是 kinematic/static 的 joint 要設 jointEnabled=False,切回動態時再打開
status: active
severity: low
confidence: measured
domains: [rigid]
tags: [joint, jointEnabled, kinematic, static bodies, crease joint]
triggers: [把兩個用 joint 連著的剛體都設成 kinematic, log 出現 cannot create a joint between static bodies]
versions: Isaac Sim 5.1.0-rc.19
scope: [sims/wrapped_mug]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §15]
related: []
observed: 2026-09
---

## 人話

**問題**:兩個都被固定住的物體之間如果還有接頭,Isaac 會一直噴錯誤。

**做法**:暫時固定時把那個接頭關掉;恢復成會動的時候記得再打開。

## 現象

把紙箱四片耳朵設成 kinematic 固定開啟姿態時(箱體本身也是 kinematic),四個 crease 鉸鏈噴 `cannot create a joint between static bodies`。

## 根因

PhysX 不能在兩個 static/kinematic body 之間建 joint。

## 做法

`joint.GetPrim().GetAttribute("physics:jointEnabled").Set(False)`;切回自由鉸鏈時設回 True。

附帶:耳朵開啟角度用數值搜尋(繞鉸鏈軸每 4° 試,取往外最遠、最低、不穿桌面的角),不要手算四組不同的旋轉慣例。

## 證據

`FINDINGS.md` §15。
