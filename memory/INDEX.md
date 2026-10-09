# INDEX —— 教訓索引(AI 讀這份;由 `memtool.py build` 產生,不要手改)

用法見 [AGENTS.md](AGENTS.md)。每行:`編號 [嚴重度|信心] 規則 — 想起:何時 (+次領域) →檔案`。
每條只列在主領域;次領域的關聯看下面的交叉表。`superseded` 的放最後,**不要照做**。

共 78 條(有效 77、已推翻 1)。

## 領域交叉表(**粗體** = 嚴重度高)

| key | 領域 | 涵蓋 | 主領域 | 也相關 |
|---|---|---|---|---|
| `env` | [環境與啟動](#env) | Isaac 版本差異、python 直譯器、Kit 參數、ROS 2、背景程序 | **L0001** **L0002** **L0005** **L0007** **L0008** L0004 L0006 L0003 L0009 | **L0078** L0062 |
| `usd` | [USD 編寫](#usd) | defaultPrim、PhysicsScene 位置、scale、bbox、meta 檔 | **L0010** **L0011** **L0013** L0016 | **L0002** **L0008** **L0012** **L0014** **L0027** **L0029** L0017 L0018 |
| `render` | [渲染與影片](#render) | 材質、貼圖、燈光、相機、錄影 | L0017 L0018 L0019 L0020 L0021 L0022 L0023 | — |
| `rigid` | [剛體/關節/碰撞](#rigid) | PhysicsScene 參數、contactOffset、kinematic、CCD、摺痕力矩 | **L0012** **L0024** **L0025** **L0027** **L0029** **L0030** **L0031** L0015 L0028 L0026 L0032 | **L0002** **L0010** **L0011** **L0013** **L0033** **L0072** L0054 L0055 |
| `surface` | [Surface deformable](#surface) | 零厚度布 / 膜:rest shape、自碰撞、sleep、官方限制 | **L0033** **L0034** **L0035** **L0036** **L0037** **L0038** **L0039** **L0040** **L0042** L0041 L0043 L0044 L0045 L0046 | **L0007** **L0031** **L0049** **L0050** **L0057** **L0058** **L0063** L0019 L0021 L0052 |
| `volume` | [Volume deformable](#volume) | 四面體薄板:rest shape、建板、反轉 | **L0047** L0048 | **L0007** **L0049** L0021 L0045 L0046 |
| `attach` | [Attachment 與夾持](#attach) | 錨點建立、放手、夾爪 | **L0049** **L0050** L0052 | **L0037** **L0042** L0043 L0045 L0048 |
| `ui` | [UI 與互動](#ui) | 滑鼠拖曳、WebRTC、Script Editor | **L0053** L0054 L0055 L0056 | **L0001** **L0005** **L0011** |
| `measure` | [量測與驗收](#measure) | 判讀方法、恆真陷阱、非決定性、證據標準 | **L0057** **L0058** **L0060** **L0061** **L0063** L0059 L0062 L0064 | **L0005** **L0008** **L0025** **L0030** **L0031** **L0035** **L0036** **L0065** **L0070** **L0077** L0073 |
| `pipeline` | [模擬鏈與檔案](#pipeline) | 多段續跑、參數一致、批次衛生、文件同步 | **L0065** **L0066** **L0067** L0068 L0069 | **L0014** **L0060** **L0063** **L0071** L0064 L0023 |
| `geometry` | [幾何與座標](#geometry) | 方位、置中、尺寸推導、紙箱幾何 | **L0014** **L0070** **L0071** **L0072** L0073 L0074 | **L0013** **L0039** **L0040** L0041 L0044 L0069 |
| `workflow` | [Agent 協作](#workflow) | 多 agent 並行修改、共享環境、證據與結論 | **L0075** **L0077** **L0078** L0076 | **L0025** **L0061** L0006 L0062 L0068 |

<a id="env"></a>
## 環境與啟動 `env`

- **L0001** [高|observed] 會自己建 SimulationApp 的腳本只能在終端機跑,不能貼進 Script Editor — 想起:要在 Isaac Sim UI 的 Script Editor 執行一支腳本;寫一支要同時給 UI 和終端機用的腳本 (+ui) [→](lessons/L0001-no-simulationapp-in-script-editor.md)
- **L0002** [高|measured] Isaac Sim 5.1 和 6.0 的 API 與物理行為不同,程式和資產不要跨版本直接搬 — 想起:在另一台機器或另一個 Isaac 版本上跑既有腳本;把 sims 的程式搬進 tools/parcel-forge 或反過來;重建 scene_final_phys.usd (+usd,rigid) [→](lessons/L0002-isaac-version-differences.md)
- **L0005** [高|measured] WebRTC 串流要在建 SimulationApp 前用 Kit 參數開啟,並以「port 有在聽 + READY」確認 — 想起:寫或修改 WebRTC 串流啟動腳本;使用者說連上去是灰畫面或只有 viewport (+ui,measure) [→](lessons/L0005-webrtc-streaming-startup.md)
- **L0007** [高|measured] 用到 deformable 的場景,Isaac 啟動時就要開 enableDeformableBeta — 想起:開啟含 deformable 的 USD;寫啟動腳本或交付說明;包材在 UI 裡不動 (+surface,volume) [→](lessons/L0007-deformable-beta-at-startup.md)
- **L0008** [高|measured] 讀模擬結果前先確認走的路徑會不會寫回 USD;deformable 要開 updateToUsd — 想起:從 USD 讀模擬後的頂點或姿態;模擬「看起來沒動」;寫匯出最終狀態的程式 (+usd,measure) [→](lessons/L0008-physics-readback-to-usd.md)
- **L0004** [中|measured] 在 Kit 裡用 ROS 2 要用 Isaac 內建的 rclpy,並把系統 /opt/ros 從環境變數拿掉 — 想起:在 Isaac Sim 裡發佈或訂閱 ROS 2 topic;寫啟動腳本並且有 source /opt/ros [→](lessons/L0004-ros2-inside-kit.md)
- **L0006** [中|measured] 背景 Kit 程序要能自己停乾淨:等它真的退出、必要時 SIGKILL,而且只停自己開的 — 想起:寫啟動或停止背景 Kit 的腳本;port 被佔用無法啟動;寫等待某程序結束的迴圈 (+workflow) [→](lessons/L0006-kit-process-lifecycle.md)
- **L0003** [低|observed] 用到 trimesh / pxr / omni 的工具用 Isaac 的 python 跑,純 numpy 工具才用系統 python3 — 想起:執行量測或分析腳本;寫一支新的離線工具 [→](lessons/L0003-system-python-vs-isaac-python.md)
- **L0009** [低|observed] pip 版 Isaac Sim 第一次啟動要編譯約 5 分鐘,不要當成當機 — 想起:在新機器或新 venv 第一次啟動 Isaac;啟動腳本設定逾時 [→](lessons/L0009-pip-isaac-first-start.md)

<a id="usd"></a>
## USD 編寫 `usd`

- **L0010** [高|measured] 匯出 USD 前設 defaultPrim,並把 PhysicsScene 放在 defaultPrim 底下 — 想起:把模擬中的 stage 匯出成 USD 交付;交付的 USD 會被別人用 reference 載入;跑 NVIDIA USD validator (+rigid) [→](lessons/L0010-defaultprim-and-physicsscene-under-it.md)
- **L0011** [高|measured] 要給人在 UI 按 Play 的 USD,一定要自帶調好的 PhysicsScene — 想起:交付一個會在 UI 裡按 Play 的 USD;headless 測試都過但使用者說東西會陷下去 (+rigid,ui) [→](lessons/L0011-ship-tuned-physicsscene.md)
- **L0013** [高|measured] 用 BBoxCache 算位置前,確認它包含哪些子物件和哪些 purpose — 想起:用 bbox 算箱底高度或擺放位置;用 bbox 判斷碰撞體重疊來決定過濾 (+rigid,geometry) [→](lessons/L0013-bbox-purpose-and-children.md)
- **L0016** [低|observed] prim 名稱不能有小數點,用數值當名字時先轉成整數 — 想起:用參數值組 prim 名稱(例如材質摩擦係數) [→](lessons/L0016-prim-name-no-dot.md)

<a id="render"></a>
## 渲染與影片 `render`

- **L0017** [中|measured] 只有 physics MaterialAPI 的材質也要接一個 surface shader,不然整個物體渲成黑色 — 想起:建一個物理材質(摩擦/彈性)並綁到可見物體;物體渲染成全黑 (+usd) [→](lessons/L0017-material-needs-surface-shader.md)
- **L0018** [中|measured] 貼圖在 RTX 下用 OmniPBR,diffuse_color_constant 設白,網格要有 st,貼片保持小尺寸 — 想起:給物體加貼圖或貼紙;貼圖渲染成黑色方塊或很暗 (+usd) [→](lessons/L0018-textures-in-rtx.md)
- **L0019** [中|measured] 包材膜不要開 OmniPBR 的 enable_opacity,交付版用不透明材質 — 想起:想讓包材或膜半透明;膜在畫面上完全看不到 (+surface) [→](lessons/L0019-omnipbr-opacity-hides-film.md)
- **L0020** [中|measured] 顏色看起來不對時先量照度,過曝要降燈光,不要去改材質顏色 — 想起:使用者說顏色怪;淺色物體一片死白;調材質顏色調不準 [→](lessons/L0020-overexposure-fix-lighting.md)
- **L0021** [中|observed] deformable 渲成黑色時依序查:法線沒重算、render mesh 掛了 translate op、相機在背光面 — 想起:deformable 或軟體物件在影片裡是全黑;新建一個 deformable 的視覺 mesh (+surface,volume) [→](lessons/L0021-deformable-renders-black.md)
- **L0022** [低|observed] 相機用驗證過的 look-at 工具,俯視要稍微偏一點,近距離要調 near clip — 想起:設定錄影或截圖的相機位置;截圖是空白或只拍到地板 [→](lessons/L0022-camera-lookat.md)
- **L0023** [低|observed] 影片第 0 格和 replicator 第一次 step 是暖機,串接或量測前要丟掉 — 想起:串接多段模擬影片;從影片抽格量測;用 replicator writer 存圖 (+pipeline) [→](lessons/L0023-render-warmup-frames.md)

<a id="rigid"></a>
## 剛體/關節/碰撞 `rigid`

- **L0012** [高|measured] 帶 xformOp:scale 的資產不要用網格碰撞體,改用解析形狀組合 — 想起:匯入外部資產當剛體;物體靜止後沉進地板或箱底 (+usd) [→](lessons/L0012-scaled-asset-mesh-collider.md)
- **L0024** [高|measured] 薄板的 contactOffset 必須小於板厚,而且要明確設定 — 想起:新增或修改薄板碰撞體(紙箱板、蓋子、托盤);東西沉進薄板;箱子自己彈飛 [→](lessons/L0024-thin-plate-contact-offset.md)
- **L0025** [高|measured] 改別人的場景前先跑一次原封不動的基準測試,不要擅自改 kinematic 設定 — 想起:拿到別人的場景要加東西進去;場景行為怪怪的不知道是誰造成的 (+workflow,measure) [→](lessons/L0025-baseline-original-scene.md)
- **L0027** [高|measured] 摺痕力矩是每步外加的,要設等效慣量、阻尼係數不超過 0.4,係數一律明確傳入 — 想起:用 crease_physics.py 或自己寫摺痕力矩;蓋子抖動或發散;想把摺痕行為存進 USD (+usd) [→](lessons/L0027-crease-torque-model.md)
- **L0029** [高|measured] 碰撞過濾要明確列出對象並實測推得動,不要靠 bbox 自動判斷或 invertFilteredGroups — 想起:加一個隱形輔助碰撞體(墊片、加厚板);設定 collision group;物體突然拖不動 (+usd) [→](lessons/L0029-explicit-collision-filtering.md)
- **L0030** [高|measured] 薄板防穿透要用 dt 掃描驗證;CCD 要場景和物體都開,而且開了不代表有生效 — 想起:快速物體掉進或撞上薄板;調整 physics dt;用 kinematic 暫時抓住一個開了 CCD 的物體 (+measure) [→](lessons/L0030-ccd-thin-plate-tunnelling.md)
- **L0031** [高|measured] 推布用的 kinematic 物體要放慢、每個 physics step 更新;要看真接觸就改成動態加 drive — 想起:用 kinematic 蓋子、壓板、夾爪去推 deformable;布被掃穿箱壁;判斷布到底有沒有被頂住 (+surface,measure) [→](lessons/L0031-kinematic-actor-vs-deformable.md)
- **L0015** [中|observed] 用 FixedJoint 固定物體要設 localPos0/1,否則物體會被拽到世界原點 — 想起:要把一個剛體釘在世界上;想用 joint 把箱子固定在桌上 [→](lessons/L0015-fixedjoint-needs-localpos.md)
- **L0028** [中|measured] 紙箱改成動態剛體時要放配重,不要用 FixedJoint 焊死來「解決」 — 想起:把紙箱 base 從 kinematic 改成 dynamic;空箱被蓋子動作掀翻 [→](lessons/L0028-dynamic-empty-carton-flips.md)
- **L0026** [低|measured] 兩端都是 kinematic/static 的 joint 要設 jointEnabled=False,切回動態時再打開 — 想起:把兩個用 joint 連著的剛體都設成 kinematic;log 出現 cannot create a joint between static bodies [→](lessons/L0026-joint-between-static-bodies.md)
- **L0032** [低|measured] Play 時的 PhysX 警告要分辨:aggregate pairs 容量不足要調大,D6 角度限制 ±180 可忽略 — 想起:Play 後 log 出現 PhysX error 或 warning [→](lessons/L0032-physx-log-triage.md)

<a id="surface"></a>
## Surface deformable `surface`

- **L0033** [高|measured] 搬箱時布會穿過薄底板被地板摩擦拖住,要加厚底板碰撞並關掉地板碰撞 — 想起:搬動裝著 deformable 的箱子;包裹相對箱子滑動 (+rigid) [→](lessons/L0033-floor-friction-drags-cloth.md)
- **L0034** [高|measured] surface deformable 的折痕要把「折好的形狀」寫成 restShapePoints,restBendAngles 在 5.1 被忽略 — 想起:想讓布或膜保持折痕;想讓包好的包材不要彈開;讀到官方文件說可以設 restBendAngles [→](lessons/L0034-crease-via-rest-shape.md)
- **L0035** [高|measured] 布疊層每層約 5 mm 是碰撞距離造成的,縮小 contactOffset 只會互穿,不是變薄 — 想起:想把包裹壓薄或壓小;布疊層太厚;調 cont/rest/thick/solver 參數;解釋回彈的原因 (+measure) [→](lessons/L0035-layer-spacing-is-collision-offset.md)
- **L0036** [高|measured] 布不動時先檢查 sleep / settling 參數和 bend 值;量回彈一律關 sleep — 想起:套用別人 USD 的 deformable 參數;布在模擬中停住不動;量測壓實後的回彈 (+measure) [→](lessons/L0036-sleep-and-bend-freeze-cloth.md)
- **L0037** [高|measured] 設計 surface deformable 前先對照官方限制清單,不支援的功能不要期待 — 想起:設計布或膜的物理行為;想凍結膜;想讓兩片膜黏在一起;調摩擦 (+attach) [→](lessons/L0037-surface-deformable-limits.md)
- **L0038** [高|measured] 折疊的布開自碰撞時,selfCollisionFilterPose 要指向攤平佈局 — 想起:布的初始形狀已經是折疊或重疊的;開 selfCollision 後各片仍互相穿透 [→](lessons/L0038-self-collision-filter-pose.md)
- **L0039** [高|measured] 包材的每一段都要有東西撐著,自立或懸空的部分在重力下一定會倒或攤開 — 想起:設計包材的初始形狀或 rest shape;包材靜置後攤開或往外倒 (+geometry) [→](lessons/L0039-every-segment-must-be-supported.md)
- **L0040** [高|measured] 用「直接生成折好的初始形狀再鬆弛」來折布,不要用夾具推;障礙物就是物體本身 — 想起:設計怎麼用模擬把布折起來;布折不上去或俯視遮蔽 0%;加輔助碰撞體幫忙折 (+geometry) [→](lessons/L0040-fold-by-initial-shape.md)
- **L0042** [高|measured] 錨點的終點幾何決定包裹高度;驅動錨點時直接跟隨、不要外推,後折只驅動還貼地的邊 — 想起:寫或調整用錨點折布的程式;包裹疊得太高;布被甩飛 (+attach) [→](lessons/L0042-anchor-driving-rules.md)
- **L0041** [中|measured] 懸空的水平布只釘外緣一定被重力拉長,攤開時要攤在地板上 — 想起:做開箱或攤平包材的動作;邊長比中位大於 1.05 (+geometry) [→](lessons/L0041-unfold-onto-floor.md)
- **L0043** [中|measured] 布上掛剛體泡泡時,間距用折好後的位置檢查,並過濾泡泡和它腳下那塊布的碰撞 — 想起:在 deformable 上附掛剛體小物件;布一開始就炸開 (+attach) [→](lessons/L0043-rigid-bubbles-on-cloth.md)
- **L0044** [中|measured] 六面壓實的平板要剛好等於箱內尺寸,只壓頂面布會往旁邊攤 — 想起:用壓板壓實包裹;設定 --press6 目標 (+geometry) [→](lessons/L0044-press-plate-equals-cavity.md)
- **L0045** [中|observed] deformable 自己的 contactOffset 預設約 2 cm,做夾取前要在 deformable prim 上設小 — 想起:用夾爪或手指去夾 deformable;夾爪還沒碰到物體就把它推開 (+volume,attach) [→](lessons/L0045-deformable-default-contact-offset.md)
- **L0046** [中|measured] 選 surface 或 volume deformable 前,先用「夾得住、外觀、物理、速度」四軸比較 — 想起:開始一個新的包材或布料模擬;決定要不要從 surface 換成 volume (+volume) [→](lessons/L0046-surface-vs-volume-choice.md)

<a id="volume"></a>
## Volume deformable `volume`

- **L0047** [高|measured] 載入折好狀態的 volume 板時,restShapePoints 要設成那個快照形狀,否則第一步就彈開 — 想起:從 npz 載入已折好或已入箱的 volume 包材繼續模擬;載入後第一步布就彈開 [→](lessons/L0047-volume-rest-shape-snapshot.md)
- **L0048** [中|measured] 很輕的 volume 板要折時,另一邊先釘在固定桿上,否則整片被翻過去而不是折 — 想起:用錨點拉一片很輕的薄板做折疊實驗 (+attach) [→](lessons/L0048-light-plate-pin-edge.md)

<a id="attach"></a>
## Attachment 與夾持 `attach`

- **L0049** [高|measured] headless 下自動 attachment 會綁到 0 個頂點,要自己算頂點寫低階 vtx attachment — 想起:把 deformable 頂點釘到剛體或夾爪上;attachment 建好了但布沒被抓住 (+surface,volume) [→](lessons/L0049-manual-vertex-attachment.md)
- **L0050** [高|measured] attachment 可以在模擬中放手:刪掉 attachment Scope(連同錨點方塊),改 stiffness 沒用 — 想起:折完想讓布自然落下;想在一次模擬裡放開夾爪或錨點;讀到「attachment 跑到一半改無效」的舊註解 (+surface) [→](lessons/L0050-attachment-release-mid-sim.md)
- **L0052** [中|measured] 夾 surface 布的懸出邊要在一開始就合指,懸出段不到 1 秒就垂直下垂 — 想起:設計夾爪夾 surface 布邊的時間表;照 volume 版的夾取流程套到 surface 版 (+surface) [→](lessons/L0052-surface-overhang-drapes.md)

<a id="ui"></a>
## UI 與互動 `ui`

- **L0053** [高|measured] 滑鼠拖不動物體時,依序檢查四道閘門:physx.ui 在跑、timeline 在播、Shift 或 override、沒有 gizmo 搶手勢 — 想起:使用者說滑鼠拖不動;寫給人互動用的 viewer 或啟動腳本;想用 headless 測滑鼠互動 [→](lessons/L0053-mouse-drag-four-gates.md)
- **L0054** [中|measured] 拖剛體用力量式抓取、pickingForce 約 70;抓遠離鉸鏈或支點的地方 — 想起:設定滑鼠拖曳參數;拖曳只動一點點;提起箱子會翻倒 (+rigid) [→](lessons/L0054-mouse-grab-mode-and-force.md)
- **L0055** [中|measured] 給滑鼠開的蓋子,摺痕彈簧要夠軟(0.012 N·m/deg)並加開關閂鎖;先開上層蓋 — 想起:讓使用者在 UI 裡用滑鼠開關紙箱蓋;蓋子拉不開或放手就彈回 (+rigid) [→](lessons/L0055-lid-spring-for-mouse.md)
- **L0056** [低|observed] Script Editor 用 File→Open 跑的腳本拿不到自己的路徑,用 exec(compile(open(p).read(), p, "exec")) 一行載入 — 想起:寫要在 UI Script Editor 執行、又需要 import 同資料夾模組的腳本;教使用者在 UI 裡開場景 [→](lessons/L0056-script-editor-file-path.md)

<a id="measure"></a>
## 量測與驗收 `measure`

- **L0057** [高|measured] 判斷布有沒有折好、疊幾層,不要看整片 bbox,用逐邊與疊層量測 — 想起:判斷包材折疊是否成功;報告包裹尺寸或層數 (+surface) [→](lessons/L0057-bbox-lies-use-per-edge.md)
- **L0058** [高|measured] 判斷布有沒有穿進物體要用邊級別檢查,只測頂點會漏 — 想起:檢查布穿杯或穿箱;驗收報告寫「穿模 0」之前 (+surface) [→](lessons/L0058-edge-level-penetration.md)
- **L0060** [高|measured] 某個量在階段交界跳一下是擺位或記帳 bug,在階段內慢慢爬才是物理 — 想起:多段模擬某個指標突然變差;判斷問題是座標還是物理 (+pipeline) [→](lessons/L0060-step-vs-gradual.md)
- **L0061** [高|measured] 驗收要能失敗:先用已知壞的案例證明檢查會 FAIL,並從產出物本身量,不要從輸入參數推 — 想起:寫新的檢查或驗收腳本;一個測試永遠是 PASS;拿參數檔證明產出正確 (+workflow) [→](lessons/L0061-tests-must-be-able-to-fail.md)
- **L0063** [高|measured] GPU deformable 不是決定性的:差 6 mm 內當噪音,關鍵結論跑兩次,A/B 要餵同一個起點 — 想起:比較兩組參數的結果;重跑一次結果不同;交付時要給參考數字 (+surface,pipeline) [→](lessons/L0063-gpu-nondeterminism.md)
- **L0059** [中|measured] 取樣式指標(射線圍蔽率)100% 不代表沒有縫,要配合邊級別量測和畫面 — 想起:用覆蓋率或圍蔽率判斷包得好不好 [→](lessons/L0059-sampled-metric-gaps.md)
- **L0062** [中|measured] 「我設了選項」不是證據,要觀察到效果(port 在聽、READY、數字改變)才算生效 — 想起:回報某個設定或服務已經生效;改了設定但現象沒變 (+workflow,env) [→](lessons/L0062-setting-is-not-evidence.md)
- **L0064** [中|measured] 抽不到資料就判 SKIP 並寫原因,不能當 PASS;文件數字對不上時兩個都列出來 — 想起:寫自動判讀或驗收腳本;整理報告時發現兩份文件數字不同 (+pipeline) [→](lessons/L0064-missing-data-is-skip.md)

<a id="pipeline"></a>
## 模擬鏈與檔案 `pipeline`

- **L0065** [高|measured] 必要輸入找不到就直接中止,不要安靜地用預設值繼續跑 — 想起:寫讀取設定檔或中間檔的程式;加一個「找不到就用預設」的分支;階段名稱照印但畫面沒變 (+measure) [→](lessons/L0065-fail-loudly-no-silent-fallback.md)
- **L0066** [高|measured] 多段模擬鏈的每一段要用同一版腳本、帶完整的共用參數,接續前比對 log 第一行 — 想起:用上一段的 npz 接著跑下一段;改了腳本後接舊的中間結果;手打每段的指令 [→](lessons/L0066-chain-stages-consistent.md)
- **L0067** [高|measured] 批次跑模擬時每段先刪舊輸出與舊 log,上游沒產出就中止,跑完歸檔再收集 — 想起:寫批次或串接模擬的 shell 腳本;結果好得不合理 [→](lessons/L0067-batch-hygiene.md)
- **L0068** [中|measured] 續跑別人的 run 時從 log 開頭和影片標籤反查指令,不要憑記憶拼;搬家後留路徑對照表 — 想起:接手別人跑過的模擬;舊文件裡的路徑找不到;重現一支舊影片 (+workflow) [→](lessons/L0068-reconstruct-from-logs.md)
- **L0069** [中|measured] 順序或設定只留一個來源,其他全部衍生,並在啟動時用 assert 守住 — 想起:同一個順序或常數在程式裡出現好幾次;改折序或改方位 (+geometry) [→](lessons/L0069-single-source-with-asserts.md)

<a id="geometry"></a>
## 幾何與座標 `geometry`

- **L0014** [高|measured] 紙箱尺寸、鉸鏈高度、內腔一律從生成器輸出的 meta 讀,不要寫死也不要自己重算 — 想起:程式裡需要箱子的任何尺寸;換一個紙箱尺寸;寫讀取 carton 的新腳本 (+usd,pipeline) [→](lessons/L0014-read-derived-dims-from-meta.md)
- **L0070** [高|measured] 物體方位要從網格本身量(杯口是環、底是盤),不要只驗旋轉矩陣代數 — 想起:改物體的擺放方向;寫方位相關的自我檢查;照別人寫的「原始網格朝向」假設做旋轉 (+measure) [→](lessons/L0070-verify-orientation-from-mesh.md)
- **L0071** [高|measured] 搬移物體用 bbox 中心當位置,布和杯子當成一整包用同一個向量搬 — 想起:把上一段的結果搬進箱子或新位置;換階段時物體位置跳一下 (+pipeline) [→](lessons/L0071-placement-bbox-center-rigid-package.md)
- **L0072** [高|measured] 紙箱蓋子的鉸鏈軸、轉向、角度約定要自檢;reset 前先擺到開的姿態;牆高 = 鉸鏈 − 2t — 想起:寫開關紙箱蓋的程式;改紙箱生成器的牆或蓋;模擬開始第一格包裹被壓扁 (+rigid) [→](lessons/L0072-lid-hinge-geometry.md)
- **L0073** [中|measured] 調參數前先算幾何下限:物品高 + 底板 + 包材層數 × 層厚 ≤ 箱內高,做不到就不是調參能解的 — 想起:使用者要求包得更小或箱子更小;開始一輪調參之前 (+measure) [→](lessons/L0073-geometric-lower-bound.md)
- **L0074** [中|measured] 開口薄殼(杯子)的徑向剖面要取投影凸包,逐角度取最大半徑會被內壁騙 — 想起:從網格量物體的外輪廓或周長;算包材要多長 [→](lessons/L0074-thin-shell-profile-convex-hull.md)

<a id="workflow"></a>
## Agent 協作 `workflow`

- **L0075** [高|measured] 別的 agent 正在改的檔案不要直接改,產 patch 並記錄基準 md5,套用前 dry-run — 想起:多個 agent 同時在同一個資料夾工作;要修改一支正在被其他實驗使用的腳本 [→](lessons/L0075-concurrent-agent-edits.md)
- **L0077** [高|measured] 前人的「做不到 / 無效」結論先用最小探針重驗再接受;程式存在不代表跑過 — 想起:交接文件或程式註解說某件事做不到;接手一個專案要判斷進度;打算根據前人結論放棄一個做法 (+measure) [→](lessons/L0077-recheck-prior-conclusions.md)
- **L0078** [高|observed] 不要改共用的 Isaac 安裝、不要打擾使用者正在跑的 WebRTC、不要停別人的程序 — 想起:想安裝或升級套件到 Isaac 環境;想重啟 Kit 或佔用 port;想啟用 Isaac 裡沒開的 extension (+env) [→](lessons/L0078-shared-environment-policy.md)
- **L0076** [中|observed] 驗證腳本和量測工具要收進 repo,scratchpad / /tmp 不會長存 — 想起:在暫存目錄寫了驗證或量測腳本;報告引用一支暫存腳本 [→](lessons/L0076-scratchpad-not-persistent.md)

## 已推翻 / 過時(不要照做;留著是因為舊程式註解或舊文件還這樣寫)

- ~~**L0051** (已推翻)attachment 在模擬中途改無效,要放手只能把模擬拆成兩段~~ → 改看 **L0050** · [L0051-attachment-cannot-release-SUPERSEDED.md](lessons/L0051-attachment-cannot-release-SUPERSEDED.md)

