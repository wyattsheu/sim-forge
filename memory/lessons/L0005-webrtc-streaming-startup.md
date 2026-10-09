---
id: L0005
title: WebRTC 串流要在建 SimulationApp 前用 Kit 參數開啟,並以「port 有在聽 + READY」確認
status: active
severity: high
confidence: measured
domains: [env, ui, measure]
tags: [WebRTC, livestream, omni.kit.livestream.app, hide_ui, isaacsim.exp.full.streaming, port 49100, publicEndpointAddress]
triggers: [寫或修改 WebRTC 串流啟動腳本, 使用者說連上去是灰畫面或只有 viewport]
versions: Isaac Sim 6.0.1(parcel-forge)/ 5.1.0(sims open_in_webrtc.sh)
scope: [tools/parcel-forge, sims/fr3_bubblewrap_pack_handoff_20261007, sims/wrapped_mug]
evidence: [tools/parcel-forge/docs/DECISIONS.md D021、D024、D025, sims/fr3_bubblewrap_pack_handoff_20261007/README.md §4, sims/wrapped_mug/viewer/start_viewer.sh]
related: [L0053, L0062]
observed: 2026-09-16
---

## 人話

**問題**:遠端串流常常「看起來啟動了」,但其實根本沒開,或只開了一個沒有任何視窗的畫面。程式不會報錯,使用者連上去只看到灰畫面。

**做法**:用正確的啟動參數開串流;開完一定實際檢查連接埠有沒有在聽、log 有沒有出現 READY,才跟使用者說可以連。

## 現象

- `SimulationApp({"livestream": 2})`:沒有錯誤,但沒有任何 port 被綁定,client 連上去是灰畫面。
- 串流起來了但只有一個空 viewport,沒有 stage 樹、屬性面板、工具列。

## 根因

- `SimulationApp` 根本沒有 `livestream` 這個 key,被**安靜地忽略**;啟動後再改 carb setting 也太晚(extension 啟動時就讀設定)。
- 沒有 UI:預設 experience 是極簡的 `isaacsim.exp.base.python.kit`;而且 `headless=True` 時 UI 預設隱藏,要再加 `hide_ui=False`。兩個開關都要對,任一個不對都不報錯。
- 沒有 `--enable omni.physx.ui` 就沒有滑鼠拖曳(見 L0053)。

## 做法

在建 `SimulationApp` **之前**把參數加進 `sys.argv`:

```
--/exts/omni.kit.livestream.app/primaryStream/signalPort=49100
--/exts/omni.kit.livestream.app/primaryStream/streamPort=47998
--/exts/omni.kit.livestream.app/primaryStream/allowDynamicResize=false
--/exts/omni.kit.livestream.app/primaryStream/streamType=webrtc
--enable omni.kit.livestream.app
--enable omni.physx.ui
```

要完整 UI:experience 用 `isaacsim.exp.full.streaming.kit`,並設 `hide_ui=False`。
或者直接用 Isaac 的 full streaming app(sims 的 `open_in_webrtc.sh` / `wrapped_mug/viewer/start_viewer.sh` 走這條)。
對外 IP:`--/app/livestream/publicEndpointAddress=<IP>`;防火牆開 TCP 49100、UDP 47998。

## 驗證方法

`ss -lnt | grep 49100` 看到 LISTEN,**而且** log 出現 READY,才算開好。client 端沒測過就寫「client 端未測」。

## 證據

`tools/parcel-forge/docs/DECISIONS.md` D021(livestream key 被忽略)、D024(experience 決定有沒有 UI)、D025(`hide_ui=False`)。`sims/fr3_bubblewrap_pack_handoff_20261007/README.md` §4.3 測試紀錄。
