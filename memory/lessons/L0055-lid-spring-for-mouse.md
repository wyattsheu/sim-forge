---
id: L0055
title: 給滑鼠開的蓋子,摺痕彈簧要夠軟(0.012 N·m/deg)並加開關閂鎖;先開上層蓋
status: active
severity: medium
confidence: measured
domains: [ui, rigid]
tags: [crease drive, stiffness, lid_latch.py, crease_hold_ui.py, yield, lid order, fyp, fyn]
triggers: [讓使用者在 UI 裡用滑鼠開關紙箱蓋, 蓋子拉不開或放手就彈回]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/CHANGELOG.md 2026-10-07 下午, sims/fr3_bubblewrap_pack_handoff_20261007/README.md §3.4、§8.6 lid_test 表、§10 #2e]
related: [L0027, L0054]
observed: 2026-10-07
---

## 人話

**問題**:模擬紙箱蓋子的彈簧如果照真實紙板設,滑鼠只拉得開十幾度;改成真實的「折過頭就停住」模型時,滑鼠力道又不太夠,蓋子只停在二十幾度。

**做法**:給人用滑鼠操作的版本,用比較軟的彈簧加上「拉過一個角度就自動翻開停住」的機制;要精確的紙板行為時再換成摺痕模型,用手臂去推。下層蓋被上層蓋壓著,要先開上層。

## 現象

| 模式 | 拉著時 | 放手 2 s 後 |
|---|---|---|
| 彈簧 0.056 N·m/deg(原值) | 只到 15° | — |
| 彈簧 0.012 + `lid_latch.py` | fyp 74°、fyn 72° | 172°(翻開停住) |
| 只有彈簧 0.012 | 37° | 0°(彈回) |
| `crease_hold_ui.py`(彈塑性) | 42° / 37° | 25° / 20° |

## 根因

滑鼠力矩只比 0.6 N·m 的降伏值大一點點;原彈簧對滑鼠太硬。

## 做法

- `build_phys_scene.py`:`--lid_stiff 0.012`(重力下垂約 1°),箱底阻尼 2/2。
- `lid_latch.py`:拉過 25° 翻開、壓回 12° 以下關上;程式可呼叫 `lids_open()` / `lids_close()`。
- 不要跟 `crease_hold_ui.py` 同時載入(後者會把彈簧 drive 歸零)。
- 先開上層(fyp / fyn),下層(fxp / fxn)在底下拉不動。

## 證據

handoff CHANGELOG;README §8.6 `lid_test.py` 表。
