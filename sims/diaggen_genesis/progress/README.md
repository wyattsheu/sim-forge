# DiagGen / Genesis 批次執行進度

狀態：**執行中**  
模型：`gpt-6-luna`，reasoning `max`  
更新：2026-10-23T18:06:40+08:00（Asia/Taipei）

共 9 件：等待 1、執行中 1、完成匯出 7、失敗 0、取消 0。

已完成匯出中：Genesis accept 7 件；仍需修正 0 件。

匯出完成與 Genesis accept 分開列示；帶 revise 的匯出仍需修正，不能當作物理診斷通過。

GPU 可用記憶體門檻：24576 MiB；最多同時 4 件；排程每 15 秒檢查。  
允許與既有運算共用 GPU：是。

只在排程狀態、階段、revision 或預覽成果改變時更新。等待期間不重複提交。

診斷健康提示是唯讀觀察，不會解除鎖、重排或改寫成功／失敗。久未更新也可能是較長的模型推理，需配合紀錄判讀。

| 物件 | 排程狀態 | Runtime | Revision | 顯存門檻 | 已完成階段 | 診斷結果 | 健康提示 |
|---|---|---|---|---|---|---|---|
| baseball_cap | success | success | revision_0000 | 24576 MiB | 9/9 | accept | 未偵測到上述異常（非成功保證） |
| kitchen_tongs | success | success | revision_0000 | 24576 MiB | 9/9 | accept | 未偵測到上述異常（非成功保證） |
| sneaker | success | success | revision_0000 | 24576 MiB | 9/9 | accept | 未偵測到上述異常（非成功保證） |
| usb_hub | success | success | revision_0000 | 24576 MiB | 9/9 | accept | 未偵測到上述異常（非成功保證） |
| sloth | success | success | revision_0000 | 24576 MiB | 9/9 | accept | 未偵測到上述異常（非成功保證） |
| sauce_keeper | success | success | revision_0000 | 24576 MiB | 9/9 | accept | 未偵測到上述異常（非成功保證） |
| dragon | running | seeded | revision_0000 | 24576 MiB | 2/9 | 尚未判定 | 未偵測到上述異常（非成功保證） |
| capybara_plush_toy | queued | not_initialized | 尚未初始化 | 49152 MiB | 0/9 | 尚未判定 | 未偵測到上述異常（非成功保證） |
| curling_iron | success | success | revision_0000 | 24576 MiB | 9/9 | accept | 未偵測到上述異常（非成功保證） |

伺服器自動監看：啟用；每 60 秒檢查，原 run 最多自動續跑 2 次。

| 物件 | 自動監看結果 |
|---|---|
| baseball_cap | completed |
| kitchen_tongs | completed |
| sneaker | completed |
| usb_hub | completed |
| sloth | completed |
| sauce_keeper | completed |
| dragon | running |
| capybara_plush_toy | queued |
| curling_iron | completed |

故障診斷工作：finished；分類 pipeline_runtime；結果 repaired_and_requeued。

每五分鐘檢查新故障，符合條件時才啟動 Codex 查因、修正及驗證；同一故障最多兩次，正常時不額外呼叫模型。

## baseball_cap

Run：`genesis_baseball_cap_20261022_fresh3`；完成。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | success |
| SAM3 分割 | success |
| OmniPart 幾何生成 | success |
| 材料推估 | success |
| 材料參數配置 | success |
| 體積網格處理 | success |
| Genesis 物理診斷 | success |
| 貼圖生成 | success |
| 最終匯出 | success |

Genesis 診斷 episode 數：2；結果：accept。

![baseball_cap_cleaned_image](media/baseball_cap_cleaned_image.png)

![baseball_cap_processed_white_bg_png](media/baseball_cap_processed_white_bg_png.png)

![baseball_cap_processed_rgba](media/baseball_cap_processed_rgba.png)

![baseball_cap_ordered_mask_vis](media/baseball_cap_ordered_mask_vis.png)

![baseball_cap_segmentation_overlay](media/baseball_cap_segmentation_overlay.png)

![baseball_cap_albedo](media/baseball_cap_albedo.png)

![baseball_cap_omnipart_top](media/baseball_cap_omnipart_top.png)

![baseball_cap_omnipart_bottom](media/baseball_cap_omnipart_bottom.png)

![baseball_cap_omnipart_front](media/baseball_cap_omnipart_front.png)

![baseball_cap_omnipart_back](media/baseball_cap_omnipart_back.png)

![baseball_cap_omnipart_left](media/baseball_cap_omnipart_left.png)

![baseball_cap_omnipart_right](media/baseball_cap_omnipart_right.png)

[baseball_cap_episode_001_triptych_video](media/baseball_cap_episode_001_triptych_video.mp4)

[baseball_cap_episode_002_triptych_video](media/baseball_cap_episode_002_triptych_video.mp4)


## kitchen_tongs

Run：`genesis_kitchen_tongs_20261022_native6`；完成。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | success |
| SAM3 分割 | success |
| OmniPart 幾何生成 | success |
| 材料推估 | success |
| 材料參數配置 | success |
| 體積網格處理 | success |
| Genesis 物理診斷 | success |
| 貼圖生成 | success |
| 最終匯出 | success |

Genesis 診斷 episode 數：2；結果：accept。

![kitchen_tongs_cleaned_image](media/kitchen_tongs_cleaned_image.png)

![kitchen_tongs_processed_white_bg_png](media/kitchen_tongs_processed_white_bg_png.png)

![kitchen_tongs_processed_rgba](media/kitchen_tongs_processed_rgba.png)

![kitchen_tongs_ordered_mask_vis](media/kitchen_tongs_ordered_mask_vis.png)

![kitchen_tongs_segmentation_overlay](media/kitchen_tongs_segmentation_overlay.png)

![kitchen_tongs_albedo](media/kitchen_tongs_albedo.png)

![kitchen_tongs_omnipart_top](media/kitchen_tongs_omnipart_top.png)

![kitchen_tongs_omnipart_bottom](media/kitchen_tongs_omnipart_bottom.png)

![kitchen_tongs_omnipart_front](media/kitchen_tongs_omnipart_front.png)

![kitchen_tongs_omnipart_back](media/kitchen_tongs_omnipart_back.png)

![kitchen_tongs_omnipart_left](media/kitchen_tongs_omnipart_left.png)

![kitchen_tongs_omnipart_right](media/kitchen_tongs_omnipart_right.png)

[kitchen_tongs_episode_001_triptych_video](media/kitchen_tongs_episode_001_triptych_video.mp4)

[kitchen_tongs_episode_002_triptych_video](media/kitchen_tongs_episode_002_triptych_video.mp4)


## sneaker

Run：`genesis_sneaker_20261023_sole_group6`；完成。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | success |
| SAM3 分割 | success |
| OmniPart 幾何生成 | success |
| 材料推估 | success |
| 材料參數配置 | success |
| 體積網格處理 | success |
| Genesis 物理診斷 | success |
| 貼圖生成 | success |
| 最終匯出 | success |

Genesis 診斷 episode 數：2；結果：accept。

![sneaker_cleaned_image](media/sneaker_cleaned_image.png)

![sneaker_processed_white_bg_png](media/sneaker_processed_white_bg_png.png)

![sneaker_processed_rgba](media/sneaker_processed_rgba.png)

![sneaker_ordered_mask_vis](media/sneaker_ordered_mask_vis.png)

![sneaker_segmentation_overlay](media/sneaker_segmentation_overlay.png)

![sneaker_albedo](media/sneaker_albedo.png)

![sneaker_omnipart_top](media/sneaker_omnipart_top.png)

![sneaker_omnipart_bottom](media/sneaker_omnipart_bottom.png)

![sneaker_omnipart_front](media/sneaker_omnipart_front.png)

![sneaker_omnipart_back](media/sneaker_omnipart_back.png)

![sneaker_omnipart_left](media/sneaker_omnipart_left.png)

![sneaker_omnipart_right](media/sneaker_omnipart_right.png)

[sneaker_episode_001_triptych_video](media/sneaker_episode_001_triptych_video.mp4)

[sneaker_episode_002_triptych_video](media/sneaker_episode_002_triptych_video.mp4)


## usb_hub

Run：`genesis_usb_hub_20261022_clean_diagnostics3`；完成。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | success |
| SAM3 分割 | success |
| OmniPart 幾何生成 | success |
| 材料推估 | success |
| 材料參數配置 | success |
| 體積網格處理 | success |
| Genesis 物理診斷 | success |
| 貼圖生成 | success |
| 最終匯出 | success |

Genesis 診斷 episode 數：2；結果：accept。

![usb_hub_cleaned_image](media/usb_hub_cleaned_image.png)

![usb_hub_processed_white_bg_png](media/usb_hub_processed_white_bg_png.png)

![usb_hub_processed_rgba](media/usb_hub_processed_rgba.png)

![usb_hub_ordered_mask_vis](media/usb_hub_ordered_mask_vis.png)

![usb_hub_segmentation_overlay](media/usb_hub_segmentation_overlay.png)

![usb_hub_albedo](media/usb_hub_albedo.png)

![usb_hub_omnipart_top](media/usb_hub_omnipart_top.png)

![usb_hub_omnipart_bottom](media/usb_hub_omnipart_bottom.png)

![usb_hub_omnipart_front](media/usb_hub_omnipart_front.png)

![usb_hub_omnipart_back](media/usb_hub_omnipart_back.png)

![usb_hub_omnipart_left](media/usb_hub_omnipart_left.png)

![usb_hub_omnipart_right](media/usb_hub_omnipart_right.png)

[usb_hub_episode_001_triptych_video](media/usb_hub_episode_001_triptych_video.mp4)

[usb_hub_episode_002_triptych_video](media/usb_hub_episode_002_triptych_video.mp4)


## sloth

Run：`genesis_sloth_20261022_clean_diagnostics3`；完成。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | success |
| SAM3 分割 | success |
| OmniPart 幾何生成 | success |
| 材料推估 | success |
| 材料參數配置 | success |
| 體積網格處理 | success |
| Genesis 物理診斷 | success |
| 貼圖生成 | success |
| 最終匯出 | success |

Genesis 診斷 episode 數：2；結果：accept。

![sloth_cleaned_image](media/sloth_cleaned_image.png)

![sloth_processed_white_bg_png](media/sloth_processed_white_bg_png.png)

![sloth_processed_rgba](media/sloth_processed_rgba.png)

![sloth_ordered_mask_vis](media/sloth_ordered_mask_vis.png)

![sloth_segmentation_overlay](media/sloth_segmentation_overlay.png)

![sloth_albedo](media/sloth_albedo.png)

![sloth_omnipart_top](media/sloth_omnipart_top.png)

![sloth_omnipart_bottom](media/sloth_omnipart_bottom.png)

![sloth_omnipart_front](media/sloth_omnipart_front.png)

![sloth_omnipart_back](media/sloth_omnipart_back.png)

![sloth_omnipart_left](media/sloth_omnipart_left.png)

![sloth_omnipart_right](media/sloth_omnipart_right.png)

[sloth_episode_001_triptych_video](media/sloth_episode_001_triptych_video.mp4)

[sloth_episode_002_triptych_video](media/sloth_episode_002_triptych_video.mp4)


## sauce_keeper

Run：`genesis_sauce_keeper_20261022_clean_diagnostics2`；完成。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | success |
| SAM3 分割 | success |
| OmniPart 幾何生成 | success |
| 材料推估 | success |
| 材料參數配置 | success |
| 體積網格處理 | success |
| Genesis 物理診斷 | success |
| 貼圖生成 | success |
| 最終匯出 | success |

Genesis 診斷 episode 數：2；結果：accept。

![sauce_keeper_cleaned_image](media/sauce_keeper_cleaned_image.png)

![sauce_keeper_processed_white_bg_png](media/sauce_keeper_processed_white_bg_png.png)

![sauce_keeper_processed_rgba](media/sauce_keeper_processed_rgba.png)

![sauce_keeper_ordered_mask_vis](media/sauce_keeper_ordered_mask_vis.png)

![sauce_keeper_segmentation_overlay](media/sauce_keeper_segmentation_overlay.png)

![sauce_keeper_albedo](media/sauce_keeper_albedo.png)

![sauce_keeper_omnipart_top](media/sauce_keeper_omnipart_top.png)

![sauce_keeper_omnipart_bottom](media/sauce_keeper_omnipart_bottom.png)

![sauce_keeper_omnipart_front](media/sauce_keeper_omnipart_front.png)

![sauce_keeper_omnipart_back](media/sauce_keeper_omnipart_back.png)

![sauce_keeper_omnipart_left](media/sauce_keeper_omnipart_left.png)

![sauce_keeper_omnipart_right](media/sauce_keeper_omnipart_right.png)

[sauce_keeper_episode_001_triptych_video](media/sauce_keeper_episode_001_triptych_video.mp4)

[sauce_keeper_episode_002_triptych_video](media/sauce_keeper_episode_002_triptych_video.mp4)


## dragon

Run：`genesis_dragon_20261023_saverfix174003`；執行中。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | success |
| SAM3 分割 | success |
| OmniPart 幾何生成 | pending |
| 材料推估 | pending |
| 材料參數配置 | pending |
| 體積網格處理 | pending |
| Genesis 物理診斷 | pending |
| 貼圖生成 | pending |
| 最終匯出 | pending |

Genesis 診斷 episode 數：0；結果：尚未判定。

![dragon_cleaned_image](media/dragon_cleaned_image.png)

![dragon_processed_white_bg_png](media/dragon_processed_white_bg_png.png)

![dragon_processed_rgba](media/dragon_processed_rgba.png)

![dragon_ordered_mask_vis](media/dragon_ordered_mask_vis.png)

![dragon_segmentation_overlay](media/dragon_segmentation_overlay.png)


## capybara_plush_toy

Run：`genesis_capybara_plush_toy_20261023_two_material6`；等待空閒 GPU。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | pending |
| SAM3 分割 | pending |
| OmniPart 幾何生成 | pending |
| 材料推估 | pending |
| 材料參數配置 | pending |
| 體積網格處理 | pending |
| Genesis 物理診斷 | pending |
| 貼圖生成 | pending |
| 最終匯出 | pending |

Genesis 診斷 episode 數：0；結果：尚未判定。


## curling_iron

Run：`genesis_curling_iron_20261021_exr_retry1`；完成。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | success |
| SAM3 分割 | success |
| OmniPart 幾何生成 | success |
| 材料推估 | success |
| 材料參數配置 | success |
| 體積網格處理 | success |
| Genesis 物理診斷 | success |
| 貼圖生成 | success |
| 最終匯出 | success |

Genesis 診斷 episode 數：2；結果：accept。

![curling_iron_cleaned_image](media/curling_iron_cleaned_image.png)

![curling_iron_processed_white_bg_png](media/curling_iron_processed_white_bg_png.png)

![curling_iron_processed_rgba](media/curling_iron_processed_rgba.png)

![curling_iron_ordered_mask_vis](media/curling_iron_ordered_mask_vis.png)

![curling_iron_segmentation_overlay](media/curling_iron_segmentation_overlay.png)

![curling_iron_albedo](media/curling_iron_albedo.png)

![curling_iron_omnipart_top](media/curling_iron_omnipart_top.png)

![curling_iron_omnipart_bottom](media/curling_iron_omnipart_bottom.png)

![curling_iron_omnipart_front](media/curling_iron_omnipart_front.png)

![curling_iron_omnipart_back](media/curling_iron_omnipart_back.png)

![curling_iron_omnipart_left](media/curling_iron_omnipart_left.png)

![curling_iron_omnipart_right](media/curling_iron_omnipart_right.png)

[curling_iron_episode_001_triptych_video](media/curling_iron_episode_001_triptych_video.mp4)

[curling_iron_episode_002_triptych_video](media/curling_iron_episode_002_triptych_video.mp4)

完整執行紀錄、GPU 識別資訊與失敗細節保留在伺服器。
