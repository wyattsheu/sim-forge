---
id: L0071
title: 搬移物體用 bbox 中心當位置,布和杯子當成一整包用同一個向量搬
status: active
severity: high
confidence: measured
domains: [geometry, pipeline]
tags: [placement, bbox center, vertex mean, rigid package, in_box_already, CDZ, centering]
triggers: [把上一段的結果搬進箱子或新位置, 換階段時物體位置跳一下]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007, sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~625-655, sims/fr3_bubblewrap_pack_20261007/work/CHANGES_wrap_sim.md 杯子入箱平移, sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/CHANGES_TO_VERIFY.md B1]
related: [L0060]
observed: 2026-09-26
---

## 人話

**問題**:把包好的包裹搬進箱子時,布和杯子如果分開算位置、或用「所有頂點的平均」當中心,兩者會錯開一公分,布就陷進杯子裡;包裹沒置中也會有一邊穿出箱壁。

**做法**:用外框的正中心當位置;布和杯子當成一整包,用同一個位移一起搬;搬之前先在水平方向置中。

## 現象

- 包裹 bbox 中心在 (0.3, −21.4) mm,整包往 −y 偏 21 mm → 14 個頂點穿出箱壁(牆在 ±112)。
- 舊版只搬布的 xy、杯子留原地還另加 CDZ → 布相對杯子錯開 (2.4, −3.4, −3.0) mm,入箱第 0 格 94 條邊陷進杯面。
- 杯子用頂點平均當平移 → 平均在 (−8.8, −5.5) mm,杯子被多搬一次,跟布錯開約 10 mm。
- `--in_box_already` 時沒扣 CDZ → 多墊 +2 mm 再被杯子壓進底板。

## 根因

杯子靜止頂點是 bbox 置中(`V -= (max+min)/2`),不是平均置中;非對稱網格兩者不同。

## 做法

```python
_c = (SP0[:, :2].min(0) + SP0[:, :2].max(0)) / 2.0     # 布 xy bbox 中心
_dz = CDZ - float(SP0[:, 2].min())                      # 整包坐到箱底內面
_sh = np.array([-_c[0], -_c[1], _dz])                   # 布和杯子同一個向量
_mq = np.load(init_npz)["mug"]; _mp0 = (_mq.min(0) + _mq.max(0)) / 2.0
```
已在箱內(`--in_box_already`)時淨位移必須為 0。

## 驗證方法

入箱第 0 格:`chain_pen` 0 條、杯子與布都在內腔內(B1:4 → 0)。

## 證據

`wrap_sim.py` 2026-09-25 / 09-26 / 10-02 三段註解。
