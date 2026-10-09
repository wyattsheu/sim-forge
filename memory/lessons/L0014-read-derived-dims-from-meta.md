---
id: L0014
title: 紙箱尺寸、鉸鏈高度、內腔一律從生成器輸出的 meta 讀,不要寫死也不要自己重算
status: active
severity: high
confidence: measured
domains: [geometry, usd, pipeline]
tags: [carton.meta.json, derived, wall_top_x, wall_top_y, wall_top_z, hinge_z, make_carton_P.py]
triggers: [程式裡需要箱子的任何尺寸, 換一個紙箱尺寸, 寫讀取 carton 的新腳本]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/ADAPTING.md §2, sims/fr3_bubblewrap_pack_handoff_20261007/sim/make_carton_P.py ~337-349, sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~515-532、~1807]
related: [L0065, L0072]
observed: 2026-09-25
---

## 人話

**問題**:箱子的尺寸只要在程式裡寫死一次,換一個箱子就會用錯。曾經把舊箱子的轉軸高度套到新箱子上,蓋子從箱子中間掃過去,把包材掀飛。

**做法**:箱子由生成器產生時,就把所有推導出來的尺寸一起寫進參數檔;模擬程式只從那裡讀,讀不到就停下來報錯。

## 現象

- 鉸鏈高度寫死成 100 mm 箱的 0.092 / 0.0985,套到 130 mm 箱 → 蓋子繞著低 80 mm 的軸轉,布從 139 mm 爆到 273 mm。
- 入箱判定的上限寫死 0.100,130 mm 的箱子就用錯上限。
- 有消費端讀 `wall_top_z` 當牆高,但它現在只是 `--height` 參數本身,不等於任何一面牆的實際高度。

## 根因

尺寸有推導關係(牆高 = 鉸鏈 − 2t、內壁 = hx − t …),消費端自己重算或寫死就會跟生成器分岔。

## 做法

- 生成器(`make_carton_P.py`)把衍生量寫進 `<name>.meta.json` 的 `derived`,附 `_note:「消費端讀這裡,不要自己算公式」`。
- 消費端讀 `wall_inner_x/y`、`lower/upper_hinge_z`、`wall_top_x/y`;**不要讀 `wall_top_z`**。
- meta 找不到 → 停下來報錯(L0065),不要猜。
- 要改尺寸用生成器重產(`ADAPTING.md` §2),不要手改 USD。

## 驗證方法

log 印出從 meta 讀到的內腔、鉸鏈、牆高;換箱子後這幾行要跟著變。

## 證據

`ADAPTING.md` §2「wrap_sim.py 一律從那裡讀,不寫死」;`wrap_sim.py` 2026-09-25 訂正註解(實測布 139 → 273 mm)。
