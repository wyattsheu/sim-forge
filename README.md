# sim-forge

Isaac Sim 物理模擬資產的生成管線。每個模擬是 `sims/` 底下一個獨立資料夾,
自帶參數表、生成腳本、驗收腳本與實測紀錄。

目前有三個:

| 模擬 | 內容 |
| --- | --- |
| [`sims/wrapped_mug`](sims/wrapped_mug) | 逆物流情境:紙箱內用泡泡紙包覆的馬克杯,放進 stationary_ai 雙臂平台 |
| [`sims/fr3_bubblewrap_pack_20261007`](sims/fr3_bubblewrap_pack_20261007) | 同一情境的**物理模擬開發紀錄**(2026-09-30~10-07):surface / volume deformable 包材折疊、入箱、搬箱、開蓋、夾爪掀包材、FR3 可達性;含 122 次模擬紀錄、自動測試集與場景 USD |
| [`sims/fr3_bubblewrap_pack_handoff_20261007`](sims/fr3_bubblewrap_pack_handoff_20261007) | 同一情境的**交付版 handoff**(拿到就能用):雙臂工作站 + 紙箱 + 包好的馬克杯場景 USD,Isaac Sim UI / WebRTC 開啟與滑鼠互動,`make_videos.sh` 重新產生影片。開發過程看上一列 |

![wrapped_mug](sims/wrapped_mug/docs/img/rig.png)

## 踩坑記憶:動手前先讀

[`memory/`](memory) 收錄所有模擬與工具踩過的坑和解法。
人看 [`memory/HANDBOOK.md`](memory/HANDBOOK.md);**AI agent 動手實作前先讀 [`memory/AGENTS.md`](memory/AGENTS.md)**,
照裡面的規程讀索引與相關教訓,做完把新踩到的坑寫回去。

## 設計原則

每個模擬遵守同一套規矩,方便互相參考、也方便換件:

1. **所有數字集中在 `params.py`**,每個值標註來源(`measured` / `literature` / `derived` / `assumed`)。
   寫死在程式裡的常數不算數。
2. **尺寸盡量推導,不手填**。換一顆杯子,紙箱與包材尺寸要自己重算。
3. **每個踩過的坑寫進註解**,而且寫「為什麼」,不只寫「怎麼做」。
   跨版本的 API 行為差異尤其要記,下一個人才不用重踩。
4. **驗收要可證偽**。`verify_render.py` 重開產出的 USD、無外力播放 N 步、量漂移,
   給出數字而不是「看起來還好」。
5. **產出物不進版控**。USD、算圖、log 都由腳本重建。

## 環境

Isaac Sim 5.1.0-rc.19(Kit 107.3 / PhysX 107.3.26),安裝在 `/isaac-sim`。
腳本一律用 `/isaac-sim/python.sh` 執行。

```bash
# 不啟動 Isaac runtime 也能用 pxr / PhysxSchema(讀 USD、算幾何)
source tools/usdenv.sh && $PY your_script.py
```

## 第三方資產

`sims/*/assets/` 不進版控。NVIDIA 官方資產用腳本取得:

```bash
tools/fetch_assets.sh
```

## 工具:parcel-forge

[`tools/parcel-forge`](tools/parcel-forge) 是 git submodule,指向獨立 repo
[wyattsheu/parcel-forge](https://github.com/wyattsheu/parcel-forge)(Isaac Sim 資產的可重現生成與自動驗證:image→TripoSR→rigid USD→PhysX、紙箱 / 開箱判定等),
自己有一套 AGENTS.md 與開發流程,所以不複製進來,只記版本。

```bash
# 第一次 clone 時一起拉
git clone --recurse-submodules https://github.com/wyattsheu/sim-forge.git

# 已經 clone 了才補拉
git submodule update --init tools/parcel-forge

# 把 parcel-forge 更新到它的最新版,再提交新的指標
git submodule update --remote tools/parcel-forge
git add tools/parcel-forge && git commit -m "tools: bump parcel-forge"
```

要改 parcel-forge 的程式,進 `tools/parcel-forge` 當成獨立 repo 操作(commit / push 到它自己的 repo),
回到 sim-forge 再提交指標更新。
