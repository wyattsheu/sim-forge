---
id: L0016
title: prim 名稱不能有小數點,用數值當名字時先轉成整數
status: active
severity: low
confidence: observed
domains: [usd]
tags: [prim path, Sdf.Path, naming]
triggers: [用參數值組 prim 名稱(例如材質摩擦係數)]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/vol/grip_common.py ~355]
related: []
observed: 2026-10
---

## 人話

**問題**:場景裡的物件名稱不能有小數點。用數字(例如摩擦係數 0.8)當名字會建不起來。

**做法**:把數字換成整數再放進名字,例如摩擦 0.8 → `_rigidFric_80`。

## 現象

`/World/_rigidFric_0.8` 建立失敗。

## 根因

USD prim 名稱只能是識別字(字母、數字、底線)。

## 做法

`"/World/_rigidFric_%d" % int(round(friction * 100))`。

## 證據

`vol/grip_common.py`:「★ prim 名不能有小數點」。
