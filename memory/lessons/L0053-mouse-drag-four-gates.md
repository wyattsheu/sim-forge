---
id: L0053
title: 滑鼠拖不動物體時,依序檢查四道閘門:physx.ui 在跑、timeline 在播、Shift 或 override、沒有 gizmo 搶手勢
status: active
severity: high
confidence: measured
domains: [ui]
tags: [mouse drag, omni.physx.ui, timeline play, Shift, mouse_interaction_override_toggle, gizmo, on_mouse_shift_drag_start, input actions]
triggers: [使用者說滑鼠拖不動, 寫給人互動用的 viewer 或啟動腳本, 想用 headless 測滑鼠互動]
versions: Isaac Sim 5.1.0-rc.19(sims)/ 6.0.1 omni.physx.ui 110.1.13(parcel-forge)
scope: [sims/wrapped_mug, sims/fr3_bubblewrap_pack_handoff_20261007, tools/parcel-forge]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §12, tools/parcel-forge/docs/DECISIONS.md D020、D057、D063、D064, sims/wrapped_mug/viewer/viewer_boot.py ~32]
related: [L0054, L0005]
observed: 2026-09
---

## 人話

**問題**:在畫面上用滑鼠拖物體,要同時滿足四個條件才會有反應,少一個就完全沒動靜,也不會有錯誤訊息。把拖拉力道調再大也沒用。

**做法**:照順序檢查:用完整版的 Isaac 介面啟動、按下播放、按住 Shift(或用腳本免按)、先取消選取避免移動工具搶走滑鼠。沒有畫面的自動測試測不了這件事,要請人實際試。

## 現象

- `pickingForce` 調到 1000 仍然拖不動。
- 使用者自己的 viewer 物理在跑,但永遠拖不動。

## 根因

`omni.physx.ui` 的 `on_mouse_shift_drag_start` 依序擋:
1. `omni.physx.ui` 有在跑且持有 viewport overlay → 要 full streaming app,不是 headless standalone(standalone 預設沒載這個 extension);
2. timeline 正在播放 → 物理拖拉的 input action 只在 timeline **PLAY 事件**時註冊;直接呼叫 `simulate()` 推物理的 viewer 永遠不會觸發;`endTimeCode=0` 會讓 play 一按就停;
3. 全程按住 Shift → 或 `get_physicsui_instance().mouse_interaction_override_toggle(ENABLED)` 免除(注意是 `get_physicsui_instance`,不是 physxui);
4. 沒有其他 gesture / hover → 選取後的移動 gizmo 會搶走。

## 做法

啟動腳本:載 `omni.physx.ui`(或用 full streaming app)、`timeline.play()`、override toggle 免 Shift、開場清空 selection。
點擊推(push)不受第 4 道影響,而且預設 `mousePush` 1000 vs `pickingForce` 1.0 —— 「推得動但拖不動」通常就是這裡。

## 驗證方法

headless 只能做唯讀診斷(四道閘門各自狀態),拖曳本身標 `not_tested` / `blocked`,不要報 PASS(parcel-forge D063)。

## 證據

`FINDINGS.md` §12;parcel-forge D020(input actions 只在 PLAY 註冊)、D063(四道閘門)、D064(push vs drag)。
