# DiagGen / Genesis 批次執行進度

狀態：**執行中**  
模型：`gpt-6-luna`，reasoning `max`  
更新：2026-10-21T15:24:49+08:00（Asia/Taipei）

共 9 件：等待 5、執行中 2、完成 0、失敗 2、取消 0。

GPU 可用記憶體門檻：24576 MiB；最多同時 2 件；排程每 15 秒檢查。  
允許與既有運算共用 GPU：是。

只在排程狀態、階段、revision 或預覽成果改變時更新。等待期間不重複提交。

| 物件 | 排程狀態 | Runtime | Revision | 顯存門檻 | 已完成階段 |
|---|---|---|---|---|---|
| usb_hub | failed | seeded | revision_0000 | 24576 MiB | 1/9 |
| capybara_plush_toy | running | seeded | revision_0000 | 49152 MiB | 2/9 |
| baseball_cap | failed | seeded | revision_0000 | 24576 MiB | 0/9 |
| curling_iron | running | seeded | revision_0000 | 24576 MiB | 2/9 |
| dragon | queued | not_initialized | 尚未初始化 | 24576 MiB | 0/9 |
| kitchen_tongs | queued | not_initialized | 尚未初始化 | 24576 MiB | 0/9 |
| sauce_keeper | queued | not_initialized | 尚未初始化 | 24576 MiB | 0/9 |
| sloth | queued | not_initialized | 尚未初始化 | 24576 MiB | 0/9 |
| sneaker | queued | not_initialized | 尚未初始化 | 24576 MiB | 0/9 |

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

Run：`genesis_capybara_plush_toy_20261021_exr_retry1_memory_retry2`；執行中。

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

Run：`genesis_curling_iron_20261021_exr_retry1`；執行中。

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

![curling_iron_cleaned_image](media/curling_iron_cleaned_image.png)

![curling_iron_processed_white_bg_png](media/curling_iron_processed_white_bg_png.png)

![curling_iron_processed_rgba](media/curling_iron_processed_rgba.png)

![curling_iron_ordered_mask_vis](media/curling_iron_ordered_mask_vis.png)

![curling_iron_segmentation_overlay](media/curling_iron_segmentation_overlay.png)


## dragon

Run：`genesis_dragon_20261021`；等待空閒 GPU。

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

Run：`genesis_kitchen_tongs_20261021`；等待空閒 GPU。

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


## sauce_keeper

Run：`genesis_sauce_keeper_20261021`；等待空閒 GPU。

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


## sloth

Run：`genesis_sloth_20261021`；等待空閒 GPU。

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


## sneaker

Run：`genesis_sneaker_20261021`；等待空閒 GPU。

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

完整執行紀錄、GPU 識別資訊與失敗細節保留在伺服器。
