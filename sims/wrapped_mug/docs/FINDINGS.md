# 實測紀錄

Isaac Sim 5.1.0-rc.19 / PhysX 107.3.26。每一條都有對應的實驗腳本與數字。

## 1. 折痕:顯式角度陣列沒實作,要走 restShapePoints

`experiments/p0b_crease_matrix.py` —— 三條懸臂膜條同場,只差靜止組態的設法:

| 組 | 設法 | total_turn |
| --- | --- | --- |
| C 對照 | 平的 rest,`flatDefault` | 156.5° |
| A | `restAdjTriPairs` + `restBendAngles` = 45° | 156.4°(與對照無異) |
| B | `restShapePoints` 折成 V + `restBendAnglesDefault="restShapeDefault"` | 247.2° |

**結論**:`restAdjTriPairs` / `restBendAngles` 在這版被完全忽略;`restShapeDefault` 有效。
折痕要靠「把折好的形狀當成靜止形狀」達成,不是靠指定角度。

官方文件把 restBendAngles 寫得像可用(還舉了褲管摺線 75° 的例子),
限制清單裡也沒列它 —— 所以只能實測。

## 2. `/physics/updateToUsd` 不開,讀回來的永遠是作者時的值

`mesh.GetPointsAttr().Get()` 會回傳授權時的點,模擬其實有跑但看起來完全沒動。
`wf_common.enable_deformable_runtime()` 一併處理。

## 3. `create_auto_deformable_attachment()` 在 headless 是空的

回傳 `True`、子 prim(`vtx_xform_attachment`)也建好了,但 `vtxIndicesSrc0` 長度是 **0** ——
負責填頂點的 attachment authoring 掛在 UI 側,headless 不會跑。pump `app.update()` 也沒用。

解法:自己算重疊頂點、直接寫低階 `OmniPhysicsVtxXformAttachment`
(`wf_common.attach_verts_to_xform`)。改完錨點頂點 0 → 2,被錨住的頂點位移 0.00000 m。

## 4. 帶 scale 的資產,網格碰撞體 cook 不出正確結果

`experiments/drop_test.py` —— 同一顆杯子掉到地板上:

| 碰撞體 | 靜止後最低點 |
| --- | --- |
| 對照方塊 | **+0.00 mm** |
| `sdf`(res 256) | −38.84 mm |
| `convexHull` | −38.62 mm |
| 頂點烘進自己網格 + `sdf` | −38.84 mm |
| 網格直接掛剛體下(無中間 xform)+ `sdf` | −38.84 mm |

四種全部一樣沉 38.8 mm。該資產的 `/RootNode` 帶 `xformOp:scale = (0.01,0.01,0.01)`,
原始頂點是 9 單位級。

解法:改用解析形狀 —— 杯身圓柱 + 把手一圈球(從實際頂點依角度分箱量出來)。
primitive 碰撞在 PhysX 最穩,而且保留把手的孔。改完杯子停在箱底面上方 0.6 mm。

## 5. 薄板的 contact offset 必須小於板厚

場景自帶的紙箱板只有 3 mm 厚且沒設 offset,東西會沉進去。
補 offset 時第一次給 10 mm —— 相鄰箱壁互相排斥,**整個箱子被自己撐爆飛出桌面**
(base z 掉到 −23.8 mm)。改成 rest 0.5 / contact 2.5 mm 才對。

## 6. 不要擅自改別人場景的 kinematic 設定

`stationary_ai_carton_scene_flat.usd` 的 `/World/Carton/base` 本來就是
`kinematicEnabled = True`(耳朵才是 dynamic)。烘焙流程尾端把它轉成 dynamic,
箱子每次都掉下桌(min z −31 mm)。

`experiments/rig_baseline.py` 是基準測試:不加任何東西純播放,確認原始場景的行為。
原始箱子 min z 全程 20.0 mm 不動 —— 這才定位出是我改壞的。

## 7. 平面裁片折立體,四個角不能留料

十字(plus)裁片:中央貼箱底,四隻臂分別往上折,四角不留料。
有角料就一定產生高斯曲率衝突(會皺、會撐開)。

## 8. 臂要靠著箱壁爬,而且不能超過箱緣

* 臂根離牆太遠 → 變成自立的板子,一定往外倒(實測離牆 51 mm 時倒到箱外 43 mm)
* 臂爬升超過箱壁高度 → 超出部分沒東西撐,往外翻並把整片拖出箱外
  (爬到 104.5 mm 而箱壁 87 mm,漂移 297 mm)
* 臂根的圓角會再往外走 `corner_r`,`B + corner_r` 必須留在內壁裡面
* 折角小於 90° 時尖端往內走的同時還在爬升,會超出箱緣 —— 要折過水平(100°)才會往下壓

## 9. 自碰撞過濾姿態要指向攤平佈局

四隻臂折起來會互相蓋住。開 `selfCollision` 時,PhysX 預設拿「當下(已經重疊)」的點
做過濾,會把互相蓋住的臂判成本來就重疊而排除自碰撞 → 臂會彼此穿透。
要用 `OmniPhysicsDeformablePoseAPI` 把 `selfCollisionFilterPose` 指向**攤平的材料佈局**。

## 10. OmniPBR 的 `enable_opacity` 會讓膜完全不渲染

把 diffuse 設成鮮紅實測,畫面上一點紅都沒有。交付版走不透明。
另外燈光過曝(Dome 900)會把淺色膜打成一片死白,降到 260。

## 11. 官方限制清單裡對本案有影響的幾條

* 模擬時不能改 rest shape → 折痕必須離線烘焙,分兩趟
* `kinematicEnabled` 對 surface deformable 無效 → 膜無法凍結
* attachment 的 stiffness / damping 無效 → 綁定一律是硬約束,沒有「弱黏」
* 兩個 surface deformable 之間不能 attach、也不能做碰撞過濾 → 左右兩片必須是同一張膜
* `surfaceStretchStiffness` / `surfaceShearStiffness` 完全不支援
* `surfaceBendStiffness` 是唯一的抗彎控制,edge bend 正比於 `SBS · thickness³`
* `staticFriction` 對 deformable solver 無效,只能靠 `dynamicFriction`

## 12. 滑鼠拖曳的四道閘門

`omni.physx.ui` 的 `on_mouse_shift_drag_start` 依序擋:

1. `omni.physx.ui` 有在跑且持有 viewport overlay → 要用 full streaming app,不是 headless standalone
2. timeline 正在播放 → `endTimeCode = 0` 會讓 `play()` 一按就停,拖不動
3. 全程按住 Shift → 可用 `get_physicsui_instance().mouse_interaction_override_toggle(ENABLED)` 免除
4. 沒有其他 gesture / hover 佔用游標 → 選取後的移動 gizmo 會搶走

`/physics/forceGrab=false` 改用約束式拖曳,不受 `pickingForce` 縮放影響,拉軟膜比較穩。
