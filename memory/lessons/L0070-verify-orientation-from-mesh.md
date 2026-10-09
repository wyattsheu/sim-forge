---
id: L0070
title: 物體方位要從網格本身量(杯口是環、底是盤),不要只驗旋轉矩陣代數
status: active
severity: high
confidence: measured
domains: [geometry, measure]
tags: [orientation, rotation matrix, _Rm, mug, STL, ring disk method, selfcheck]
triggers: [改物體的擺放方向, 寫方位相關的自我檢查, 照別人寫的「原始網格朝向」假設做旋轉]
versions: Isaac Sim 5.1.0(純 numpy 量測,與版本無關)
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/FOLDORDER_NOTES.md §3, sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/CHANGES_TO_VERIFY.md B2, sims/fr3_bubblewrap_pack_20261007/work/CHANGES_wrap_sim.md 杯子方位]
related: [L0061, L0069]
observed: 2026-09-30
---

## 人話

**問題**:檢查程式只確認旋轉矩陣的數學沒錯,但它根據的「原始模型朝哪個方向」的假設是錯的,結果檢查全部通過,杯口卻朝向錯誤的方向。

**做法**:直接從模型的形狀量方向(杯口是一圈環、杯底是實心盤、杯耳是凸出去的那一塊),用量到的結果決定怎麼轉;最後在模擬結果上再量一次。

## 現象

| 轉法 | 杯軸 | 杯口 | 杯耳 |
|---|---|---|---|
| raw STL | z | +z | +x(直立杯,建模慣例) |
| 原檔 `Ry(−90)·Rx(90)` | x | −x | −y |
| 原檔 · `_Rm`(任務字面作法) | x | **+x ❌** | −y |
| 原檔 · `Rz(−90)` · `_Rm`(採用) | y | +y ✅ | +x ✅ |

selfcheck 寫死「原始 = 杯口 +y / 杯耳 −x」,在原檔轉法下不成立;照字面套 `_Rm` 會讓 selfcheck 全過、杯口卻在 +x。

## 根因

檢查只驗矩陣(det、正交、向量映射),不碰網格。

## 做法

- 判杯軸 / 杯口:三軸各取兩端 3 mm 薄片,算端面點到中心的徑向距離 r_min / r_max;環(r_min ≈ r_max)是杯口或底足,盤(r_min ≈ 0)是封底;杯口環比底足大。
- 判杯耳:橫截面上超出杯身半徑 1.08 倍的點的平均方向。
- 在最終 npz 的 `mug` 上用同一套方法再量一次(B2 要求)。
- 副作用要跟著處理:長邊從 y 轉到 x,`--press6` 要重訂(L0044)。

## 證據

FOLDORDER_NOTES §3 表格與量測方法;CHANGES_TO_VERIFY B2「程式的旋轉矩陣對 ≠ 模擬完還是對」。
