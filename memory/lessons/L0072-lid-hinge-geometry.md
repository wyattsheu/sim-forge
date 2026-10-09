---
id: L0072
title: 紙箱蓋子的鉸鏈軸、轉向、角度約定要自檢;reset 前先擺到開的姿態;牆高 = 鉸鏈 − 2t
status: active
severity: high
confidence: measured
domains: [geometry, rigid]
tags: [lid, hinge, rotation axis, sgn, lid_pose, world.reset, wall height, carton_sweep.py, 270 deg]
triggers: [寫開關紙箱蓋的程式, 改紙箱生成器的牆或蓋, 模擬開始第一格包裹被壓扁]
versions: Isaac Sim 5.1.0 / 6.0.1
scope: [sims/fr3_bubblewrap_pack_handoff_20261007, sims/fr3_bubblewrap_pack_20261007, tools/parcel-forge]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py ~515-532, sims/fr3_bubblewrap_pack_20261007/work/CHANGES_wrap_sim.md 修正, sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #8, sims/fr3_bubblewrap_pack_handoff_20261007/sim/make_carton_P.py ~225-235, tools/parcel-forge/docs/DECISIONS.md D066、D067]
related: [L0014, L0073]
observed: 2026-09-25
---

## 人話

**問題**:紙箱蓋子的轉軸位置、轉的方向、幾度算「關」,只要一個搞反,蓋子就會往箱子裡面掃,把包材擠爆;場景存檔時蓋子是關的,模擬一開始會先把包裹壓扁;箱壁如果跟轉軸一樣高,蓋子轉動時會穿過箱壁。

**做法**:轉軸高度從參數檔讀;程式開頭自己驗證「正角度 = 往上開」;開始模擬前先把蓋子擺到打開的位置;箱壁高度做成比轉軸低兩個板厚。

## 現象

- 轉軸方向反了(fxp 繞 −y):蓋子往箱內下方掃,布被擠成 x 145 mm、高度爆到 255 mm。
- 角度約定反了:生成器產出的姿態是**蓋住**(0° = 關、180° = 開)。
- 定版紙箱 USD 預設是關;`world.reset()` 時蓋子在關的姿態,第一格 drive 才甩開 → `out_bl_boxmeta` t=0 包裹被壓扁到 117。
- 牆頂 = 鉸鏈 z:0~180° 掃掠 180/361 重疊;牆頂 = 鉸鏈 z − 2t:0/361。
- parcel-forge:以為 179° 就是蓋子貼平在牆外側,實際上 180° 是水平朝外像架子,**270°** 才是垂在牆外。

## 根因

折邊從鉸鏈往**箱內**延伸;R(+y, 90°)(−x̂) = +ẑ 才是往上掀。蓋子是 2t 厚的板,傾斜時外上角會掃進箱壁那 2t 的帶子。

## 做法

- 建 LIDS 時從 USD 量蓋子中心轉 ±90° 後的 z,算出 `sgn` 保證「正角度 = 往上開」,順便判 `rest_closed`。
- reset 前把蓋子 USD 姿態擺到 180°(開),再 drive 180° → 0° 關蓋;log 印「reset 前先擺到 180°」。
- 生成器:`WTOP_X = Z_IN − 2t`、`WTOP_Y = Z_OUT − 2t`;改完跑 `carton_sweep.py`(解析掃掠、純 CPU)要 0/361。
- 完全打開 = 270°,不是 180°。

## 證據

`wrap_sim.py` 2026-09-25 三個訂正;PITFALLS #8;`make_carton_P.py` 2026-09-26 牆高註解;parcel-forge D067。
