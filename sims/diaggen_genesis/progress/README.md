# DiagGen / Genesis 批次執行進度

狀態：**執行中**  
模型：`gpt-6-luna`，reasoning `max`  
更新：2026-10-21T18:09:21+08:00（Asia/Taipei）

共 9 件：等待 0、執行中 1、完成 0、失敗 8、取消 0。

GPU 可用記憶體門檻：24576 MiB；最多同時 2 件；排程每 15 秒檢查。  
允許與既有運算共用 GPU：是。

只在排程狀態、階段、revision 或預覽成果改變時更新。等待期間不重複提交。

| 物件 | 排程狀態 | Runtime | Revision | 顯存門檻 | 已完成階段 |
|---|---|---|---|---|---|
| usb_hub | failed | seeded | revision_0000 | 24576 MiB | 1/9 |
| capybara_plush_toy | failed | seeded | revision_0000 | 49152 MiB | 2/9 |
| baseball_cap | failed | seeded | revision_0000 | 24576 MiB | 0/9 |
| curling_iron | failed | running | revision_0000 | 24576 MiB | 9/9 |
| dragon | failed | seeded | revision_0000 | 24576 MiB | 0/9 |
| kitchen_tongs | failed | seeded | revision_0000 | 24576 MiB | 2/9 |
| sauce_keeper | failed | failed | revision_0000 | 24576 MiB | 6/9 |
| sloth | failed | seeded | revision_0000 | 24576 MiB | 2/9 |
| sneaker | running | seeded | revision_0000 | 24576 MiB | 4/9 |

## usb_hub

Run：`genesis_first_20261021_exr_retry1_display_retry2`；執行失敗。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | success |
| SAM3 分割 | pending |
| OmniPart 幾何生成 | pending |
| 材料推估 | pending |
| 材料參數配置 | pending |
| 體積網格處理 | pending |
| Genesis 物理診斷 | pending |
| 貼圖生成 | pending |
| 最終匯出 | pending |

Genesis 診斷 episode 數：0。

![usb_hub_cleaned_image](media/usb_hub_cleaned_image.png)


## capybara_plush_toy

Run：`genesis_capybara_plush_toy_20261021_exr_retry1_memory_retry2`；執行失敗。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | success |
| SAM3 分割 | success |
| OmniPart 幾何生成 | failed |
| 材料推估 | pending |
| 材料參數配置 | pending |
| 體積網格處理 | pending |
| Genesis 物理診斷 | pending |
| 貼圖生成 | pending |
| 最終匯出 | pending |

Genesis 診斷 episode 數：0。

![capybara_plush_toy_cleaned_image](media/capybara_plush_toy_cleaned_image.png)

![capybara_plush_toy_processed_white_bg_png](media/capybara_plush_toy_processed_white_bg_png.png)

![capybara_plush_toy_processed_rgba](media/capybara_plush_toy_processed_rgba.png)

![capybara_plush_toy_ordered_mask_vis](media/capybara_plush_toy_ordered_mask_vis.png)

![capybara_plush_toy_segmentation_overlay](media/capybara_plush_toy_segmentation_overlay.png)


## baseball_cap

Run：`genesis_baseball_cap_20261021_exr_retry1`；執行失敗。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | failed |
| SAM3 分割 | pending |
| OmniPart 幾何生成 | pending |
| 材料推估 | pending |
| 材料參數配置 | pending |
| 體積網格處理 | pending |
| Genesis 物理診斷 | pending |
| 貼圖生成 | pending |
| 最終匯出 | pending |

Genesis 診斷 episode 數：0。


## curling_iron

Run：`genesis_curling_iron_20261021_exr_retry1`；執行失敗。

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

Genesis 診斷 episode 數：2。

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


## dragon

Run：`genesis_dragon_20261021`；執行失敗。

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

Genesis 診斷 episode 數：0。


## kitchen_tongs

Run：`genesis_kitchen_tongs_20261021`；執行失敗。

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

Genesis 診斷 episode 數：0。

![kitchen_tongs_cleaned_image](media/kitchen_tongs_cleaned_image.png)

![kitchen_tongs_processed_white_bg_png](media/kitchen_tongs_processed_white_bg_png.png)

![kitchen_tongs_processed_rgba](media/kitchen_tongs_processed_rgba.png)

![kitchen_tongs_ordered_mask_vis](media/kitchen_tongs_ordered_mask_vis.png)

![kitchen_tongs_segmentation_overlay](media/kitchen_tongs_segmentation_overlay.png)


## sauce_keeper

Run：`genesis_sauce_keeper_20261021`；執行失敗。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | success |
| SAM3 分割 | success |
| OmniPart 幾何生成 | success |
| 材料推估 | success |
| 材料參數配置 | success |
| 體積網格處理 | success |
| Genesis 物理診斷 | failed |
| 貼圖生成 | pending |
| 最終匯出 | pending |

Genesis 診斷 episode 數：1。

![sauce_keeper_cleaned_image](media/sauce_keeper_cleaned_image.png)

![sauce_keeper_processed_white_bg_png](media/sauce_keeper_processed_white_bg_png.png)

![sauce_keeper_processed_rgba](media/sauce_keeper_processed_rgba.png)

![sauce_keeper_ordered_mask_vis](media/sauce_keeper_ordered_mask_vis.png)

![sauce_keeper_segmentation_overlay](media/sauce_keeper_segmentation_overlay.png)

![sauce_keeper_omnipart_top](media/sauce_keeper_omnipart_top.png)

![sauce_keeper_omnipart_bottom](media/sauce_keeper_omnipart_bottom.png)

![sauce_keeper_omnipart_front](media/sauce_keeper_omnipart_front.png)

![sauce_keeper_omnipart_back](media/sauce_keeper_omnipart_back.png)

![sauce_keeper_omnipart_left](media/sauce_keeper_omnipart_left.png)

![sauce_keeper_omnipart_right](media/sauce_keeper_omnipart_right.png)


## sloth

Run：`genesis_sloth_20261021`；執行失敗。

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

Genesis 診斷 episode 數：0。

![sloth_cleaned_image](media/sloth_cleaned_image.png)

![sloth_processed_white_bg_png](media/sloth_processed_white_bg_png.png)

![sloth_processed_rgba](media/sloth_processed_rgba.png)

![sloth_ordered_mask_vis](media/sloth_ordered_mask_vis.png)

![sloth_segmentation_overlay](media/sloth_segmentation_overlay.png)


## sneaker

Run：`genesis_sneaker_20261021`；執行中。

| 階段 | 狀態 |
|---|---|
| 圖片清理 | success |
| SAM3 分割 | success |
| OmniPart 幾何生成 | success |
| 材料推估 | success |
| 材料參數配置 | pending |
| 體積網格處理 | pending |
| Genesis 物理診斷 | pending |
| 貼圖生成 | pending |
| 最終匯出 | pending |

Genesis 診斷 episode 數：0。

![sneaker_cleaned_image](media/sneaker_cleaned_image.png)

![sneaker_processed_white_bg_png](media/sneaker_processed_white_bg_png.png)

![sneaker_processed_rgba](media/sneaker_processed_rgba.png)

![sneaker_ordered_mask_vis](media/sneaker_ordered_mask_vis.png)

![sneaker_segmentation_overlay](media/sneaker_segmentation_overlay.png)

![sneaker_omnipart_top](media/sneaker_omnipart_top.png)

![sneaker_omnipart_bottom](media/sneaker_omnipart_bottom.png)

![sneaker_omnipart_front](media/sneaker_omnipart_front.png)

![sneaker_omnipart_back](media/sneaker_omnipart_back.png)

![sneaker_omnipart_left](media/sneaker_omnipart_left.png)

![sneaker_omnipart_right](media/sneaker_omnipart_right.png)

完整執行紀錄、GPU 識別資訊與失敗細節保留在伺服器。
