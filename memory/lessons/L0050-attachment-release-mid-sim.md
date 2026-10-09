---
id: L0050
title: attachment 可以在模擬中放手:刪掉 attachment Scope(連同錨點方塊),改 stiffness 沒用
status: active
severity: high
confidence: measured
domains: [attach, surface]
tags: [RemovePrim, attachmentEnabled, SetActive, release, release_after, probe_detach.py, anchor cube]
triggers: [折完想讓布自然落下, 想在一次模擬裡放開夾爪或錨點, 讀到「attachment 跑到一半改無效」的舊註解]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/probe_detach.py, sims/fr3_bubblewrap_pack_20261007/work/EXPERIMENTS.md 探針 detach_m1~m7、06_release, sims/fr3_bubblewrap_pack_20261007/work/REPORT_20260930.md §1 結論 2, sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~192、~1484-1495, sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #7]
related: [L0049, L0042, L0077]
supersedes: [L0051]
observed: 2026-09-30
---

## 人話

**問題**:之前以為釘住布的點一旦建立就放不掉,只能把模擬拆成兩段。後來實測發現可以放,只是要用「刪掉」的方式;之前的結論是量錯造成的。放手時連帶的那些小方塊也要刪,移走它們會把布掃飛。

**做法**:要放手就把那組綁定整個刪掉,連同拉布用的方塊;不要用改強度的方式。

## 現象

`probe_detach.py` 7 種做法:
- 有效(當步生效、頂點立刻自由落下,放掉後 1 s 掉 0.298 m;其他錨點不受影響、布不重 cook):`stage.RemovePrim(Scope)`、`attachmentEnabled=False`、`SetActive(False)`。
- 無效:改 stiffness、清 relationship。
- 放手時把 33 顆 kinematic 錨點方塊「收到 z=−5」→ 一步掃過鋪在地上的布,speculative contact 把整排頂點踢飛(bbox z 2343 mm、自穿模 19864,`t_c1_bad`)。

## 根因

- attachment 本來就能停用;stiffness/damping 在這版無效(L0037),所以「改強度」看不出效果。
- 原作者 09-25「改了無效」:探針裡三個同邊錨點一起升、被鄰居撐住 —— 量測假象。
- 移動 kinematic 方塊 = 一個高速掃過布的碰撞體。

## 做法

```python
st.RemovePrim(Sdf.Path("/World/attach/" + name))   # attachment Scope(含子 prim)
st.RemovePrim(Sdf.Path(anchor_cube_path))          # 方塊也刪,不要搬
```
`--release_after <秒>`;注意 bend 4 + `--no_hold` 時後折邊會翻回地上,第二段要保留 hold。

## 驗證方法

放手後 bbox z 應在 90~130 mm;`tests/run_checks.py` 的 `bbox_guard`(任一軸 > 1000 mm = FAIL)會抓到掃飛。

## 證據

EXPERIMENTS 探針段與 06_release;REPORT_20260930 §1 結論 2;`wrap_sim.py` 2026-09-30 兩段註解;PITFALLS #7。
