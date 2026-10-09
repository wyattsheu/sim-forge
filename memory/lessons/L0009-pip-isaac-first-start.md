---
id: L0009
title: pip 版 Isaac Sim 第一次啟動要編譯約 5 分鐘,不要當成當機
status: active
severity: low
confidence: observed
domains: [env]
tags: [pip, shader cache, extscache, first start, READY]
triggers: [在新機器或新 venv 第一次啟動 Isaac, 啟動腳本設定逾時]
versions: Isaac Sim 6.0.0-rc.22(pip)
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sim-forge 分支 portable-isaac-launch commit a8800e9(open_in_webrtc.sh 與 README)]
related: [L0002]
observed: 2026-10-07
---

## 人話

**問題**:用 pip 裝的 Isaac Sim 第一次打開要先編譯一堆東西,大概五分鐘沒反應,很容易被誤以為卡死而被關掉。

**做法**:第一次啟動耐心等 READY 出現;啟動腳本的逾時至少給 5 分鐘以上,並在畫面印提示。

## 現象

pip 版第一次啟動,log 長時間停在載入 extension,約 5 分鐘後才出現 `[handoff] READY`。

## 根因

第一次啟動要編譯 shader 與 extension 快取。

## 做法

啟動腳本印出「first start of a pip install can take ~5 min」;逾時判斷不要短於這個值。

## 證據

portable-isaac-launch 分支 `open_in_webrtc.sh`:「connect once you see [handoff] READY (first start of a pip install can take ~5 min)」。
