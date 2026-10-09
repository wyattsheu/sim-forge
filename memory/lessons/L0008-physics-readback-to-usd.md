---
id: L0008
title: 讀模擬結果前先確認走的路徑會不會寫回 USD;deformable 要開 updateToUsd
status: active
severity: high
confidence: measured
domains: [env, usd, measure]
tags: [updateToUsd, Fabric, GetPointsAttr, SimulationManager, fetch_results, tensor API, readback]
triggers: [從 USD 讀模擬後的頂點或姿態, 模擬「看起來沒動」, 寫匯出最終狀態的程式]
versions: Isaac Sim 5.1.0-rc.19(sims)/ 6.0.1(parcel-forge)
scope: [sims/wrapped_mug, tools/parcel-forge]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §2, sims/wrapped_mug/wf_common.py enable_deformable_runtime, tools/parcel-forge/docs/DECISIONS.md D016、D018]
related: [L0007]
observed: 2026-09-16
---

## 人話

**問題**:物理模擬的結果不一定會寫回場景檔。如果直接從場景檔讀,看到的可能永遠是一開始的位置,以為模擬沒動,其實有在跑。

**做法**:讀頂點前先打開「寫回場景」的設定;要存最終狀態就用實際量到的數字另外寫一份檔。

## 現象

- deformable:`mesh.GetPointsAttr().Get()` 永遠回傳作者時的點,模擬其實有跑。
- parcel-forge:跑 3 秒後 tensor API 說 probe 在 z=0.225,USD 還是 0.470。

## 根因

PhysX 的結果透過 Fabric / tensor API 發佈,**不一定**寫回 USD,看走哪條路徑:
- `SimulationManager.step()`(parcel-forge 用的):**不**寫回 USD。
- `omni.physx` 的 `simulate()` + `fetch_results()`(使用者的 WebRTC viewer 用的):**會**寫回 USD。
- deformable 頂點要 `/physics/updateToUsd=true` 才寫回。

歷史:parcel-forge D016 原本寫「PhysX 從不寫回 USD」,D018 更正為「看路徑」。看到 D016 的舊說法要以 D018 為準。

## 做法

- deformable 場景啟動時帶 `--/physics/updateToUsd=true`(或在程式裡設),`wf_common.enable_deformable_runtime()` 一併處理。
- 剛體姿態用 tensor API / prim view 讀,不要從 USD 讀。
- 要交付「看得到最終狀態」的檔:用量到的最終姿態另外寫 `scene_final.usda`,並註明數字來源。

## 驗證方法

跑幾步後,同時從 USD 和 tensor/view 讀同一個物體,兩者應一致;不一致就是沒寫回。

## 證據

`sims/wrapped_mug/docs/FINDINGS.md` §2;parcel-forge D016(量測:tensor 0.22500 vs USD 0.47000)與 D018(更正)。
