---
id: L0010
title: 匯出 USD 前設 defaultPrim,並把 PhysicsScene 放在 defaultPrim 底下
status: active
severity: high
confidence: measured
domains: [usd, rigid]
tags: [defaultPrim, Export, reference, PhysicsScene, DefaultPrimChecker, usd validator]
triggers: [把模擬中的 stage 匯出成 USD 交付, 交付的 USD 會被別人用 reference 載入, 跑 NVIDIA USD validator]
versions: Isaac Sim 6.0.1(parcel-forge)
scope: [tools/parcel-forge]
evidence: [tools/parcel-forge/docs/DECISIONS.md D013、D015、D053, tools/parcel-forge/tests/test_export_defaultprim.py]
related: [L0011]
observed: 2026-09-16
---

## 人話

**問題**:很多檢視工具是用「參照」的方式載入場景檔。如果檔案沒指定主要物件,參照進來會是空的;物理設定如果放在主要物件外面,參照進來就沒有物理,東西掛在空中不會掉。

**做法**:存檔前指定主要物件(通常是 `/World`),並把物理場景設定搬到它底下;用別人的檢視工具實際載一次確認。

## 現象

- 使用者的 WebRTC viewer 載入匯出的場景:「1 prims, 0 meshes, bbox size 0」,只看到 viewer 自己的地板;USD log「Unresolved reference prim path … <defaultPrim>」。
- 補了 defaultPrim 之後物體看得到了,但 3 秒後 probe 仍停在 z=0.47000(沒有物理)。

## 根因

- 沒有限定路徑的 reference 靠目標 layer 的 `defaultPrim` 解析;`Stage.Export()` 不會自動設。
- Isaac 把物理場景建在 `/PhysicsScene`(`/World` 的兄弟),reference 只會拉 defaultPrim 的子樹,物理場景被丟掉;viewer 事後補建的 PhysicsScene 也救不回已經參照進來的剛體。
- NVIDIA 官方 DefaultPrimChecker 也會拒絕 defaultPrim 指到巢狀路徑(`/World/Carton`)。

## 做法

```python
if not stage.GetDefaultPrim():
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))   # root 層級的 prim
# 匯出後處理:把 /PhysicsScene 複製到 /World/PhysicsScene,刪掉 root 層級原本那個(避免直接開檔時有兩個)
stage.Export(path)
```

## 驗證方法

用**跟使用者一樣的方式**載入(新 stage + `GetReferences().AddReference(path)`),檢查 prim 數 > 1、找得到 PhysicsScene、跑幾步物體有動。parcel-forge 的測試先用 pxr 重現失敗再證明修好。

## 證據

parcel-forge D013(defaultPrim)、D015(PhysicsScene 位置,修後 reference 載入看到 `['/World/Model/PhysicsScene']`)、D053(root defaultPrim)。
