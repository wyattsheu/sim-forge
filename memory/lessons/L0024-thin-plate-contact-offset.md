---
id: L0024
title: 薄板的 contactOffset 必須小於板厚,而且要明確設定
status: active
severity: high
confidence: measured
domains: [rigid]
tags: [contactOffset, restOffset, thin plate, carton wall, 3 mm, PhysxCollisionAPI]
triggers: [新增或修改薄板碰撞體(紙箱板、蓋子、托盤), 東西沉進薄板, 箱子自己彈飛]
versions: Isaac Sim 5.1.0-rc.19 / PhysX 107.3.26
scope: [sims/wrapped_mug]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §5, sims/wrapped_mug/forge.py ~536-547]
related: [L0035, L0030]
observed: 2026-09
---

## 人話

**問題**:很薄的板子(像 3 mm 紙箱板)如果沒設碰撞距離,東西會沉進去;但碰撞距離設太大(超過板厚),相鄰的箱壁會互相推擠,整個箱子會自己撐爆飛出桌面。

**做法**:薄板一律明確設碰撞距離,而且要小於板厚。3 mm 板用「接觸 2.5 mm、靜止 0.5 mm」。

## 現象

- 場景自帶的紙箱板 3 mm 厚且沒設 offset → 東西沉進去。
- 第一次補 offset 給 10 mm → 相鄰箱壁互相排斥,整個箱子被自己撐爆飛出桌面(base z 掉到 −23.8 mm)。

## 根因

contactOffset 大於板厚時,同一個箱子相鄰的板在靜止時就已進入彼此的接觸帶,solver 把它們推開。

## 做法

對每片薄板的 collider:

```python
pc = PhysxSchema.PhysxCollisionAPI.Apply(prim)
pc.CreateRestOffsetAttr(0.0005)      # 0.5 mm
pc.CreateContactOffsetAttr(0.0025)   # 2.5 mm < 3 mm 板厚
```

同一個物體的板之間若仍互斥,改用碰撞過濾(L0029)。

## 驗證方法

空箱靜置數秒,箱體 min z 不變、不飛;再放一個物體進去,停在板面上方 < 1 mm。

## 證據

`sims/wrapped_mug/docs/FINDINGS.md` §5;`forge.py`「實測用 10 mm 時箱子直接飛出桌面」。
