# wrapped_mug

逆物流情境的物件資產:**紙箱內用泡泡紙包覆的馬克杯**,可放進 stationary_ai 雙臂平台。

全程程序化生成。馬克杯用 NVIDIA 官方資產(`tools/fetch_assets.sh` 取得),
紙箱與包材的尺寸由馬克杯的實際 bbox 推導 —— 換杯子不用手改任何數字。

## 跑起來

```bash
tools/fetch_assets.sh                      # 一次就好

# 獨立場景(自建紙箱)
/isaac-sim/python.sh forge.py
/isaac-sim/python.sh verify_render.py

# 放進 stationary_ai 雙臂平台,用場景自己的紙箱
/isaac-sim/python.sh forge.py --rig /path/to/stationary_ai_carton_scene_flat.usd \
                              --out out/wrapped_mug_on_rig.usd
/isaac-sim/python.sh verify_render.py --usd out/wrapped_mug_on_rig.usd \
                                      --prefix /World --wide

# WebRTC 檢視 + 滑鼠拖曳
viewer/start_viewer.sh
```

## 做法

包材是 **surface deformable**。難處在於:折起來之後,膜的靜止形狀還是平的,
一放手就彈回去。PhysX 的 `restBendAngles`(顯式指定每條邊的靜止二面角)在這版沒實作,
所以改走另一條:

1. 用**曲率剖面積分**解析地折出包覆形狀 —— 沿弧長給定切線角再積分,
   保證等距映射,把平面裁片折成這個形狀不產生面內應變
2. 把這個形狀同時當作 `points` 和 `restShapePoints`,並設 `restBendAnglesDefault="restShapeDefault"`
3. 兩階段靜置:杯子 kinematic 讓膜先貼合 → 杯子轉動態一起落定
4. 把靜置結果寫回 `restShapePoints`、`velocities` 歸零

折痕成為零能量狀態,**不需要任何黏合,膜自己維持包覆**。

裁片是**十字形**:中央貼箱底,四隻臂分別往上折 —— 長邊繞杯身在杯頂合攏,
短邊立起往內壓封住前後端面。四個角不留料:平面裁片折立體時,有角料就一定產生
高斯曲率衝突。

馬克杯的碰撞體用解析形狀(圓柱 + 把手球鏈),不用網格 —— 原因見 `docs/FINDINGS.md` 第 4 條。

## 參數

全部在 `params.py`,每個值標註來源。膜的推導鏈只需要量一個數字:

```
W = 0.060 kg/m²     泡泡紙 60 GSM(文獻)
t = 0.004 m         等效殼厚 = 泡高(推導)
c = 0.034 m         彎曲長度,ASTM D1388 懸臂法  ← 唯一需要量測的,目前是假設值
D = W·g·c³                                      抗彎剛度
surfaceBendStiffness = D / t³                   官方:edge bend ∝ SBS · t³
omniphysics:mass = W × 面積                     顯式設質量,繞過 density×thickness 的歧義
```

## 檔案

| | |
| --- | --- |
| `params.py` | 所有參數與推導 |
| `wf_common.py` | 共用工具,每個函式對應一個實測踩到的坑 |
| `forge.py` | 生成 + 折疊靜置 + 烘焙 rest shape + 存檔 |
| `verify_render.py` | 重開產出的 USD、無外力播放、量漂移 + 四視角算圖 |
| `viewer/` | WebRTC 檢視器(含滑鼠拖曳的四道閘門處理) |
| `experiments/` | 定位問題用的最小實驗,每支都對應 FINDINGS 裡的一條 |
| `docs/FINDINGS.md` | **實測紀錄** —— 這份最值得先看 |

## 現況

放進 stationary_ai 平台(內部 197 × 177 × 87 mm 的紙箱)後:

| 指標 | 值 |
| --- | --- |
| 紙箱 | bbox 與原始場景一致,完全沒被擾動 |
| 馬克杯 | 停在箱底面上,無貫穿;bbox z 跨距 ≈ 杯徑,幾乎不傾斜 |
| 包材平均漂移 | 一位數 mm,收斂 |

**未完成**:包材仍有一部分會翻出箱緣。這個紙箱對杯子偏小(內高 87 mm),
餘裕很緊。下一步是把短邊臂再折低、只包到杯子腰部,不強求蓋頂。

其他已知限制:

* `bending_length = 0.034 m` 是假設值,需要拿真泡泡紙做一次 ASTM D1388 懸臂測試
* 膜目前不透明(見 FINDINGS 第 10 條)
* 場景自帶的 `crease_*` 鉸鏈沒有 drive 也沒有 limit,耳朵是自由擺盪的;
  PPT 要求「掀開後維持」的話需要補 drive,本 repo 未動它們
