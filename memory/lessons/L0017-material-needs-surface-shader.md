---
id: L0017
title: 只有 physics MaterialAPI 的材質也要接一個 surface shader,不然整個物體渲成黑色
status: active
severity: medium
confidence: measured
domains: [render, usd]
tags: [UsdShade, MaterialAPI, surface output, OmniPBR, black render, materialPurpose]
triggers: [建一個物理材質(摩擦/彈性)並綁到可見物體, 物體渲染成全黑]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/make_carton_P.py ~135-150]
related: [L0018]
observed: 2026-08-17
---

## 人話

**問題**:為了設定摩擦力建立的材質,如果沒有同時設定顏色,渲染器會把整個物體畫成全黑。

**做法**:物理材質裡也放一個顏色設定(用 Omniverse 的標準材質);或者物理材質只綁到「物理用途」,不影響外觀。

## 現象

九箱影片第一版九顆紙箱全黑,外包裝完全看不到(貼圖路徑其實是對的)。

## 根因

`cardMat` 只有 physics `MaterialAPI`、沒有 surface shader;RTX 把它當可視材質解析時得到「沒有 surface」→ 純黑。

## 做法

在同一個 Material 下補 OmniPBR shader 並接 surface / displacement / volume output,顏色設成紙板色;
或綁定時用 `materialPurpose="physics"`,讓可視材質另外綁。

```python
sh = UsdShade.Shader.Define(stage, mat + "/Shader")
sh.SetSourceAsset("OmniPBR.mdl", "mdl"); sh.SetSourceAssetSubIdentifier("OmniPBR", "mdl")
sh.CreateInput("diffuse_color_constant", Sdf.ValueTypeNames.Color3f).Set(CARD)
m.CreateSurfaceOutput("mdl").ConnectToSource(sh.ConnectableAPI(), "out")
```

## 證據

`make_carton_P.py`:「cardMat 原本只有 physics MaterialAPI、沒有 surface shader … 整個箱子渲染成純黑」。
