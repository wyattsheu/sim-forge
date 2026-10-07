# PITFALLS —— 踩過的坑(現象 / 原因 / 怎麼避免)

| # | 坑 | 現象 | 原因 | 怎麼避免 |
|---|---|---|---|---|
| 1 | 缺 carton meta,蓋子不動但階段名照印 | log 照印 close lower/upper flaps,影片蓋子沒動;`out_bl_box` 布 148 點高於口 | `--carton X.usd` 用檔名推 `X.meta.json`;找不到就 `LIDS` 空、內腔用整箱 bbox 猜 | work/ 保留 `carton_w131.meta.json` symlink;grep log 有沒有「⚠ 找不到 … meta」;`tests/run_checks.py` 會直接 FAIL |
| 2 | `--sleepy`(預設套用)掩蓋回彈 | 壓住 = 放開(`v4a_c3` 114/114,`v1_c3` 132/132) | 布睡著,放開後不動 | 量回彈一律加 `--no_sleepy`(`v4a_c3_nosleep` 放開 127) |
| 3 | 整片 bbox 會騙人 | bbox 看起來「包好了」,其實某條邊翻回地上或沒折到 | bbox 只有 6 個數,看不出哪條邊在哪 | 判折疊用 `edge_report.py`(逐邊);疊層用 `layer_gap.py` |
| 4 | W3 圍蔽 100% 但開蓋看得到杯身 | log W1/W3 100%,畫面/實際有縫 | W3 只從杯心沿 300 條射線(穿過 300 個隨機杯子頂點)打布三角形,射線之間、斜看的縫不會被算到 | 不單看 W1/W3;配合邊級別 `chain_pen.py` 與畫面,數字優先 |
| 5 | 同參數兩次差 ~6mm,甚至折邊滑開 | 同一組旗標兩次 bbox 差數 mm;偶發一折滑開 | 未查實(推測 GPU 解算非決定性 + 接觸敏感)| 差 < 6mm 當噪音;關鍵結論至少跑兩次;影片要看 |
| 6 | c3 漏 `--sheet_mm` | `sh450_c3` 邊長比中位 0.769、`sh400_c3` 0.688,log 寫布 586 | 邊長比的「攤平長度」用預設 586 布算 | 每段都帶完整共用參數(`C=…`,見 README);`run_checks.py` 邊長比會 FAIL |
| 7 | 放手時搬方塊會掃飛布 | `t_c1_bad` S1 19864、bbox z 上千、W1 0% | 舊版把錨點方塊移走,方塊掃過布 | 放手用 `stage.RemovePrim`(attachment Scope + 方塊);放手後 bbox z 應 90~130 |
| 8 | `world.reset()` 時蓋子在 USD 預設(關)姿態 | `out_bl_boxmeta` t=0 包裹被壓扁到 117 | 定版紙箱 USD 預設是關,第一格 drive 才甩到開 | 已修:reset 前先擺到 180°(開);log 有「reset 前先擺到 180°」 |
| 9 | 搬箱時地板摩擦拖住布 | `mb2_x30` 包裹相對箱子滑 35mm | 3mm 底板被布頂點壓穿 → 碰到地板 → 被摩擦留住 | `--base_collider_pad 0.02 --no_ground_collision`(`mb6_x30` 7.3mm、`fincam_mb_x30` 1.7mm) |
| 10 | 包裹與腳本版本要同一折序(杯子方位) | `sh400_mb_yz` 杯子方位跟包裹不合 | `--init_npz` 只拿杯子的平移,方位由當下腳本的 `_Rm` 決定;舊折序包裹配新腳本就錯 | 同一條鏈用同一版腳本;log 第一行「杯子躺平 W x D x H」要跟起點 run 一致(`run_checks.py` 會比) |
| 11 | `pgrep -f` 等待迴圈抓到自己 | `while pgrep -f wrap_sim; do sleep…` 永遠不結束 | `pgrep -f` 比對整條命令列,包含這個 shell 自己 | 用 `pgrep -f '[w]rap_sim.py'` 或記 PID 用 `wait`/`kill -0 $PID` |
| 12 | 系統 `python3` 沒有 trimesh | `chain_pen.py` / `check_place.py` ImportError | trimesh 只裝在 Isaac 的 python | 用 `/isaac-sim/python.sh chain_pen.py …`;純 numpy 工具(layer_gap / edge_report / collect_runs)用系統 python3 |
| 13 | 縮 contactOffset = 互穿 | cont 2mm:層「變薄」但 S1 上百~上千(v1/v2/v3/r/s) | 接觸帶比一步位移小,布直接穿過 | 維持 cont 5 / rest 1;薄的數字標「互穿,高度不可信」 |
| 14 | 影片第 0 格是渲染暖機 | 串接影片每段開頭閃一格舊畫面/黑畫面 | 第 0 格在 renderer 暖機時抓的 | 串接前 `ffmpeg -ss 0.5` 剪掉(`trim.mp4`);抽格不要用第 0 格 |
| 15 | 相機距離跟布寬走 | sheet 400 時鏡頭太近,看不到全貌 | 非紙箱段相機距離用 max(WX,WY) | 加 `--cam_ref 0.586`(跟 586 布同一個鏡頭) |
| 16 | 階段交界的跳變 ≠ 物理 | 入箱 t=0 杯心就跳到 (−15,33,55)(`fin_box`) | 擺位/記帳 bug(杯子平移用頂點平均而非 bbox 中心,多搬 ~10mm) | 已修(bbox 中心);判讀規則:交界跳一階 = 擺位 bug,段內漸增 = 物理 |
| 17 | 舊折序 `floor_edges.json` 配新折序 | y 邊安靜地沒折到 | 鍵名是 xp/xn,新折序後兩折是 yp/yn | 已加守衛(SystemExit);新折序用 `floor_edges_fin*.json` |
| 18 | 搬家後舊文件路徑失效 | REPORT / HOW_TO_VIEW 寫 `out_c1/wrap.npz` | 2026-10-02 整理成 `runs/NN_*/` | 查 `MOVED.txt`;新 run 跑完搬進 runs/ 再跑 `collect_runs.py` |
