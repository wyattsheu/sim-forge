---
id: L0018
title: 貼圖在 RTX 下用 OmniPBR,diffuse_color_constant 設白,網格要有 st,貼片保持小尺寸
status: active
severity: medium
confidence: measured
domains: [render, usd]
tags: [OmniPBR, UsdPreviewSurface, UsdUVTexture, diffuse_color_constant, st primvar, UsdGeom.Cube, decal, opacity cutout]
triggers: [給物體加貼圖或貼紙, 貼圖渲染成黑色方塊或很暗]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/make_carton_P.py ~60、~155-175、~300-315]
related: [L0017]
observed: 2026-08-17
---

## 人話

**問題**:在 Isaac 裡貼圖很容易變成黑色方塊或變得很暗,原因有好幾種,而且都不會報錯。

**做法**:材質一律用 Omniverse 的標準材質,底色設白色;要貼圖的物體要有貼圖座標;貼紙保持小尺寸;去背圖要打開透明裁切。

## 現象(各自的原因與做法見表)

| 現象 | 原因 | 做法 |
|---|---|---|
| 貼花整片渲成黑方塊(st 有、路徑對) | `UsdPreviewSurface` + `UsdUVTexture` 在 Isaac RTX 下讀不進貼圖 | 改用 `OmniPBR.mdl` |
| 貼圖整體變暗(mean 196 的標籤幾乎看不清、中灰牛皮紋變全黑) | OmniPBR `diffuse_color_constant` 預設 0.2 灰,與貼圖相乘 | `diffuse_color_constant` 與 `diffuse_tint` 設 (1,1,1) |
| 去背貼紙周圍一圈黑框 | alpha=0 區域用 RGB(=0)渲染 | `enable_opacity=True`、`opacity_texture`=同一張圖、`opacity_mode=0`、`opacity_threshold=0.35` |
| 箱體用貼圖整片黑 | `UsdGeom.Cube` 沒有 `st` primvar | 不用貼圖改平面色,或用自己建、有 st 的 Mesh |
| 大張標籤(0.30 m)、大箱貼紙(0.136 m)一律黑;小貼紙(0.087 m)正常 | **未查明**(推測 OmniPBR 用某種世界尺度 UV) | 貼片固定實體尺寸(0.075 m),不隨箱子放大 |

## 根因

見上表;最後一列 confidence 只有 observed。

## 做法

見上表。試過對大張標籤無效的五種做法:UsdPreviewSurface→OmniPBR、相對→絕對路徑、底色設白、RGB→RGBA、開 cutout。

## 證據

`make_carton_P.py` 2026-08-17、2026-08-18 註解。
