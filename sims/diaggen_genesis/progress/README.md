# DiagGen / Genesis 批次執行進度

狀態：**執行中**  
模型：`gpt-6-luna`，reasoning `max`  
更新：2026-10-21T14:43:24+08:00（Asia/Taipei）

共 9 件：等待 7、執行中 1、完成 0、失敗 1、取消 0。

GPU 可用記憶體門檻：24576 MiB；最多同時 2 件；排程每 15 秒檢查。  
允許與既有運算共用 GPU：是。

只在排程狀態、階段、revision 或預覽成果改變時更新。等待期間不重複提交。

| 物件 | 排程狀態 | Runtime | Revision | 顯存門檻 | 已完成階段 |
|---|---|---|---|---|---|
| usb_hub | failed | seeded | revision_0000 | 24576 MiB | 1/9 |
| capybara_plush_toy | queued | not_initialized | 尚未初始化 | 49152 MiB | 0/9 |
| baseball_cap | running | seeded | revision_0000 | 24576 MiB | 0/9 |
| curling_iron | queued | not_initialized | 尚未初始化 | 24576 MiB | 0/9 |
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

Run：`genesis_capybara_plush_toy_20261021_exr_retry1_memory_retry2`；等待空閒 GPU。

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


## baseball_cap

Run：`genesis_baseball_cap_20261021_exr_retry1`；執行中。

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


## curling_iron

Run：`genesis_curling_iron_20261021_exr_retry1`；等待空閒 GPU。

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
