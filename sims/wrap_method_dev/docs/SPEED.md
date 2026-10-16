# wrap_vol.py 加速評估(2026-10-14)

倍率 = wall / sim(越小越快;out_ga3 基準 7.41 = 7.4 倍慢於實時)。GPU 上同時有非我們的串流 kit(pid 1949101,isaacsim.exp.full.streaming,~6.6 GB)全程佔用,所有數字都含它的干擾。

## 新旗標(預設 = 舊行為)
| 旗標 | 作用 |
|---|---|
| `--vid_every N` | 每 N 個渲染幀才 render(world.step render=True)+ 寫顯示網格 + get_rgba + stamp + 編碼;影片 fps = 30/N(播放仍實時);key_*.png 幀與最後一幀一定渲染;量測/npz 不變 |
| `--vid_res WxH` | 相機解析度(預設 1280x720) |
| `--fast_pts 1` | 嘗試用 omni.physics.tensors `create_volume_deformable_body_view` 直讀 sim 節點。**此版(physics.tensors 107.3.26)對 /World/plate 回 count 1 但 max_simulation_nodes 0**,numpy/torch/warp 前端、建 view 前後跑 step 皆同 → 自動退回 USD 並在 log 印 ★。實測 USD 讀 2592 點+寫回 = 0.023 ms/幀,本來就不是瓶頸,這刀無收益 |
| `--dt`、`--solver` | 原本就有 |

## 四折段速度掃描(`--until fold`,sim 18.1 s,一次只跑一個)
| 組 | 旗標 | wall | 倍率 | 省 | fold_end bbox (mm) | fold_end 自穿 / 全程最大 | 反轉 | 邊長比 [min,max] | 顫抖 停留 RMS / 靜置 RMS (mm/格) |
|---|---|---|---|---|---|---|---|---|---|
| 基準 | — | 127.4 s | 7.04 | — | 255x216x124 | 3 / 7 | 0 | [0.567, 1.873] | 4.18 / 1.35 |
| 1 | `--vid_every 4` | 118.1 s | 6.52 | 7% | 251x216x124 | 4 / 7 | 0 | [0.514, 1.775] | 4.32 / 1.10 |
| 2 | `--vid_res 640x360` | 125.5 s | 6.94 | 1.5% | 255x216x125 | 7 / 7 | 0 | [0.562, 1.884] | 4.25 / 1.18 |
| 3 | `--fast_pts 1` | — | — | ~0 | (退回 USD,未計時) | | | | |
| 4a | `--dt 1/120` | 79.1 s | 4.37 | 38% | 252x216x125 | **13 / 13** | 0 | [0.558, 1.547] | 4.51 / 1.12 |
| 4b | `--solver 64` | 89.3 s | 4.93 | 30% | 251x216x125 | 7 / 9 | 0 | [0.572, 1.563] | 4.16 / 1.21 |
| 4c | `--dt 1/120 --solver 64` | 60.7 s | 3.36 | 52% | 256x216x126 | **17 / 19** | 0 | [0.540, 1.538] | 4.46 / 1.00 |

雜訊參考:組 1、2 物理完全相同(只改渲染),自穿仍在 3~7 間跳 → GPU 非決定性約 ±4。入箱 0 超出:全部組別 0。
渲染只佔 ~8% wall,其餘是 PhysX(6125 tets selfCollision、128 iter)。

## 完整鏈(參數照 out_ga3,+ `--vid_every 4 --vid_res 640x360`)
| 組 | 倍率* | 全程最大自穿 | 反轉 | 邊長比 | 入箱超出 | yn 越線 / 放手後(名義) | yp 越線 / 放手後 |
|---|---|---|---|---|---|---|---|
| out_ga3 基準 | 7.41 | 5 | 5 | [0.439, 2.125] | 0 | **100% / 62%** | 73% / 67% |
| solver 64 | 7.90* | 10 | 0 | [0.442, 1.609] | 0 | 40% / **0%** | 37% / 0% |
| dt 1/120 | 5.76* | 14 | 0 | [0.406, 1.932] | 0(關蓋後/搬前/搬後) | 100% / **0%** | 53% / 13% |
| dt 1/120 + solver 64 | 6.02* | 25 | 0 | [0.488, 1.710] | 0 | 59% / **0%** | 43% / 3% |

\* 完整鏈跑的時候其他 agent 的模擬中途開跑(最多同時 3 個),倍率被污染,只看品質欄。
未完成:同旗標基準的完整鏈重跑(量掀開結果的 run-to-run 雜訊)— GPU 一直被其他模擬佔用,為遵守「一次一個」而中止。三組物理放寬放手後全掉到 0~13%(基準 62%),方向一致,判定為品質退化。

## 結論 / 建議
- 安全:`--vid_every 4`(+ `--vid_res 640x360`)。四折段 7.04 → ~6.4(約 -9%),物理不變。參數掃描時建議用;要交付影片時用預設。
- 無效:`--fast_pts`(此版 tensor API 拿不到 volume deformable 節點;USD 讀寫本就 0.02 ms)。
- 傷品質:`--dt 1/120`、`--solver 64` 及兩者合用。四折段可快 30~52%,四折外形/反轉/顫抖看不出差,但自穿翻倍(dt)、且掀開「放手後」從 62% 掉到 0~13%。只建議拿 `--solver 64` 做四折段的粗掃,掀開/抓取段一律 dt 1/240、solver 128。
- 建議預設不變(dt 1/240、solver 128),掃描時加 `--vid_every 4 --vid_res 640x360`。

## 重現
```
cd vol
speed/run.sh speed/f_base fold                       # out_ga3 args,覆寫 out/until
speed/run.sh speed/f_ve4 fold --vid_every 4
speed/run.sh speed/f_s64 fold --solver 64
speed/run.sh speed/a_s64 all --solver 64 --vid_every 4 --vid_res 640x360
speed/extract.sh speed/f_base speed/f_ve4 ...       # wall、fold_end、全程最大、超出內腔、ATTACH 越線、jitter
```
