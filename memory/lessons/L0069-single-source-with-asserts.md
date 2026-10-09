---
id: L0069
title: 順序或設定只留一個來源,其他全部衍生,並在啟動時用 assert 守住
status: active
severity: medium
confidence: measured
domains: [pipeline, geometry]
tags: [FOLD_ORDER, single source of truth, assert, derived tables, SIDEPICK, regex selfcheck]
triggers: [同一個順序或常數在程式裡出現好幾次, 改折序或改方位]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/work/FOLDORDER_NOTES.md §1、§2、§6, sims/fr3_bubblewrap_pack_20261007/work/CHANGES_wrap_sim.md 修正]
related: [L0066, L0070]
observed: 2026-09-30
---

## 人話

**問題**:同一個「先折哪邊、後折哪邊」的順序在程式裡寫了六個地方,改了一處忘了其他處,就會一部分照新順序、一部分照舊順序,而且不會報錯。連註解裡也寫死了順序。

**做法**:順序只在一個地方定義,其他地方都從它算出來;程式一啟動就檢查衍生出來的東西是否一致,不一致就直接停。

## 現象

- `STAGE2_SIDES`、`WORDER`、`ORD_`、`UORDER`、`ORDER`、`_ORD` 各自寫死字面值;stage2 寫死抓 x 外圈 → 改折序後第二段 0 個錨點,y 永遠沒折(修後 0 → 40)。
- 角落頂點:挑點用「超出折線多少」分邊,建 PULLS 又用 `|x| >= |y|` 重分 —— 舊幾何剛好一致,杯子轉正後角落被改判到錯的那一折。

## 根因

順序語意散落各處(包括「y 整條、x 只抓貼地段」其實是「先折整條、後折只抓貼地段」)。

## 做法

```python
FOLD_ORDER = ["xp", "xn", "yp", "yn"]
STAGE2_SIDES = FOLD_ORDER[2:]
UORDER = ["yn", "yp", "xn", "xp"]            # selfcheck 用 regex 抓字面值,所以寫死、由下一行守住
assert UORDER == list(reversed(FOLD_ORDER))
assert sorted(FOLD_ORDER) == ["xn", "xp", "yn", "yp"]
assert FOLD_ORDER[0][0] == FOLD_ORDER[1][0] and FOLD_ORDER[2][0] == FOLD_ORDER[3][0]
```
- 分類結果記下來沿用(`SIDEPICK`),不要在後面用另一套規則重算。
- 改這類常數前,全檔 grep 每個字面值逐一判定「順序語意 / 軸語意 / 正負」(FOLDORDER_NOTES §6 的做法)。

## 證據

FOLDORDER_NOTES §2.1、§2.4、§6;CHANGES_TO_VERIFY B4(0 → 40)。
