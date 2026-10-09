---
id: L0022
title: 相機用驗證過的 look-at 工具,俯視要稍微偏一點,近距離要調 near clip
status: active
severity: low
confidence: observed
domains: [render]
tags: [camera, SetLookAt, gimbal, look-at, clipping range, near clip]
triggers: [設定錄影或截圖的相機位置, 截圖是空白或只拍到地板]
versions: Isaac Sim 5.1.0
scope: [sims/wrapped_mug, sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §16, sims/fr3_bubblewrap_pack_20261007/vol/grip_common.py look(), sims/fr3_bubblewrap_pack_20261007/vol/grip/gutil.py ~164]
related: [L0021]
observed: 2026-09
---

## 人話

**問題**:相機位置設錯很常見:正上方往下看時算出來的方向會壞掉變成空白圖;自己手寫旋轉常常一律拍到地板;太近的東西會被切掉。

**做法**:用專案裡已經驗證過的相機工具;俯視時相機稍微偏一點點;拍近距離物體時把最近可視距離調小。

## 現象

- `Gf.Matrix4d().SetLookAt(eye, target, up)` 視線與 up 平行 → 退化矩陣 → 空白圖。
- 手刻旋轉矩陣 → 一律拍到地板。
- 1 m 內的物體被切掉。

## 根因

look-at 在視線 ∥ up 時無解;相機光軸慣例(local +X 或 −Z)容易搞錯;預設 near clip 太大。

## 做法

- 用 `grip_common.look()` / `cam_quat()`(euler look-at,相機光軸 local +X)這種已驗證的工具。
- 俯視時 eye 留一點水平偏移。
- `cam.set_clipping_range(0.01, 100.0)`。

## 證據

`FINDINGS.md` §16;`grip_common.py` `look()` docstring;`gutil.py`「預設 near clip 會把 <~1m 的東西切掉」。
