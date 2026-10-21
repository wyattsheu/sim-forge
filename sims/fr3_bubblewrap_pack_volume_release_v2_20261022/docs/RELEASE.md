# 發行版統整:volume 泡泡紙包材 — 包、入箱、搬運、雙臂掀開取杯(2026-10-21)

本文件把三週(09-27 ~ 10-15)嘗試過的方法與結論統整,並交出一個發行版本。
數字只來自下列來源檔(FINAL_PLAN、work/、vol/、arm/ 的文件),沒有重跑模擬。
同參數兩次結果會不同(GPU 解算不可重現),所有「達標」都要看分布,單次不算。
標「待補」的段落是對應檔案(vol/JAW.md、vol/QUALITY.md、EXTRACT3.md v5)在撰寫時不存在。

---

## 1. 發行版是什麼

**材料**:`--young 2e3 --poisson 0.45 --thick_mm 4 --areal 0.1 --fric 0.8`,4 mm 厚四面體 volume deformable 板,表面貼 `bubble_normal.png` 泡泡紋理。層間距 = 板厚 4 mm(surface 版的層間距 4.3~5.6 mm 是自碰撞撐出來的假厚度)。

**幾何**:500 × 500 mm 方布(`--sheet_mm 500 --nxy 35`),杯子躺平 bbox 107 × 133 × 93 mm,折線尖端越過杯中線 30 mm(`--tip_over_mm 30`),收耳 `--tuck 1`;紙箱 `carton_w131.usd`(270 × 230 × 131,內腔 264 × 224)。

**流程**:布鋪平 → 四折(預設 xp, xn, yp, yn,最外層 = yn)→ 收耳 → 入箱 → 關蓋 → 搬箱 → 開蓋 → 第一隻手綁定抓 yn 邊、繞過箱壁頂角翻到箱外 → 第二隻手綁住躺在蓋上那段並一直拿住 → 同樣掀 yp → 第三個夾持把杯子綁住、抬 20 mm、斜升過 yn 壁頂 +40 mm、水平往 −y 滑出 280 mm、落地。

**demo 定義(10-15 改定)**:手臂把包材「掀開並持續拿住」的狀態下取杯(真人拆包也是一手撐開一手拿),**不是**掀開放手後靠重力維持。原因見 §3:這個材料沒有塑性,放手必回彈。

**重現指令**(取自 `vol/extract4/run.sh`,一次一個,GPU < 20000 MiB 且沒有其他 wrap_vol 才開):
```
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
extract4/run.sh X1     # 內容如下
/isaac-sim/python.sh wrap_vol.py --sheet_mm 500 --grasp 1 --grasp_attach 1 --attach_pad_mm 24 \
  --attach_layer both --arc2 1 --arc_k 0.8 --peel_t 6 --gap_mm 4 --clear_mm 6 --steep_deg 45 \
  --second 1 --young 2e3 --grasp_site state --grasp_retry 2 --site_xmax_mm 60 --grasp_site_k 13 \
  --arc2_over_cap 0 --arc2_over_mm 30 --hand2 attach --hand2_pad_mm 15 --hand2_keep 1 --hold_yp 1 \
  --extract 1 --guard_yp 2.6 --guard_n 2 --extract_mode slide --extract_out_mm 280 \
  --guard_yn 2.6 --slide_clear_mm 40 --out extract4/X1
```
- 物理旗標的完整清單在 FINAL_PLAN §2(含 `--cont 0.002 --rest 0.0005 --solver 128 --dt 1/240 --ldamp 0 --edamp 0`);上面的 run.sh 沒有逐項列出,是否等於 wrap_vol 預設值本文未逐項核對。
- 阻尼:完整鏈維持 `--ldamp 0 --edamp 0`(§3)。只做折疊/入箱展示影片可加 `--edamp 0.02`。
- 夾爪版(JAW):**待補:夾爪版**(vol/JAW.md 尚未產生)。
- EXTRACT3.md 的 v5 驗證:**待補**(該檔現有內容止於 v4 驗證)。
- 演示影片:`vol/videos/VOL_twohand_extract.mp4`(extract4/X2)、`vol/videos/DEMO_twohand_extract_short.mp4`(18.2 s)。
- 單程式整鏈 wall 約 639 s(out_ga3,sim 86 s,7.4 倍實時);FINAL_PLAN 表列整鏈 10.7 分鐘。

**發行版的誠實狀態**(逐項見 §4):
| 使用者要求 | 現況 |
|---|---|
| 正常外觀、有厚度 | 達成(真厚度 4 mm,層間距 = 厚度) |
| 能正常包起來、入箱 | 達成(入箱超出 0,出處 FINAL_PLAN §1、SPEED、FOLD_DIVERSITY 整鏈) |
| 搬運 | 達成(DEMO_2,互穿 ≤ 8,可重現 ≤ 2 mm) |
| 被雙臂打開取杯 | 部分:拿住與出箱 3/3、穿杯 0;落地後布被帶起 < 30% 只有 1/3 |
| 沒有抖動 | **未完全達成**:edamp 0.02 降顫抖 40% 但完整鏈抓取會壞(1 次樣本),故完整鏈 0 阻尼 |
| 沒有 Q 彈回彈 | **未達成**:volume 無塑性,靠「持續拿住」迴避,不是消除 |

---

## 2. 方法總表

欄位:問題 / 做法 / 結果數字 / 結論 / 出處。出處簡寫:RPT = work/REPORT_20260930.md,EXP = work/EXPERIMENTS.md,THK = work/REPORT_THICKNESS.md,DEC = work/DECISION_phase3.md,FP = FINAL_PLAN.md。

### 2.A 包裹疊層、厚度、體積(surface 階段,09-27 ~ 10-02)

| 方法 | 問題 | 做法 | 結果數字 | 結論 | 出處 |
|---|---|---|---|---|---|
| 錨點幾何根因 | 包裹疊太高(基準四折後高 162) | 查尖端錨點:釘在 杯頂 + 12 mm + 第幾折 × layer_mm,第二段 100 個 hold 錨,壓實段 4 個錨 | 基準 c2 高 162、自穿 257、層 5、層距 6.88、疊層 54.3 mm | **根因確認**:布是被吊著不是疊著。`--hold_mm`、`--no_anchor` 保留 | RPT §1.1、EXP 01 |
| collider 偏移(cont/rest) | 層距 5 mm 是否來自偏移 | v1 `cont 2 / rest 0.2`;v2 加薄;v3 加 solver 128 + 碰撞迭代 ×2;v3b ccd | 層距 5.46 → 5.44 沒變;c1 自穿 104 / 288 / 59 / 118;c2 1430~2237;c3 2403~3726 | **排除**:只是互穿。維持 cont 5 / rest 1(surface) | RPT §1.3、EXP 02、PITFALLS #13 |
| 縮 rest 0.2 | 層距減半能否不互穿 | p1 p0 + rest 0.2 | 層距 8.81 → 4.07,但自穿 394 → 888 | 排除(互穿) | EXP 04 |
| 降 bend | 回彈來自彎曲剛度? | p2 bend 1;p3 bend 1 + rest 0.2 | 放開 152(p0 為 141),回彈更大 | 排除 | EXP 04 |
| surfaceThickness 10 → 4 | 層距是否來自接觸厚度 | 只改 thick | 層距 4.37 vs 4.20,沒影響 | 排除 | RPT §1.3、THK §2 |
| 越線疊合 | 兩片只在中線對接,疊層中位 1 | `--tip_over_mm 40`(尖端越過杯中線) | 自穿三段 2 / 55 / 144(基準 13 / 257 / 512);層中位 2;壓實放開 133(基準 163) | **採用**(surface 唯一乾淨的改善;volume 版用 30) | RPT §1.4、EXP 05 |
| 薄膜(薄 + rest 0.2 + hold 2) | 要不要模擬 PE 薄膜 | r / s 組 | c3 自穿 3317 / 4316,放開 124~130 | **排除**:互穿,高度不可信。材料口徑定為泡泡紙 | EXP 05、THK §2 |
| 放手錨點 | 錨點能否模擬中釋放 | `RemovePrim` / `attachmentEnabled=False` / `SetActive(False)` 七種探針 | m1/m5/m7 成功(放掉後 1 s 掉 0.298 m),m2/m3/m4/m6 失敗 | **採用**:attachment 可中途釋放,原 09-25「無效」是量測假象。注意:RemovePrim 在手臂場景會讓程序無訊息結束,手臂場景用 `attachmentEnabled=False` | RPT §1.2、EXP 探針、INTERFACE §5 |
| 放手(t 系列) | 折到位就放掉錨 | `--release_after 0.3`;c2 `--no_hold` | t c2 x 363(+x 折翻回);t2 c2 層 4 / 層距 9.69;t3 c2 x 299 | 放手可行,但 bend 4 + no_hold 會翻回;第二段保留 hold。放手時搬方塊會掃飛布(S1 19864),改 RemovePrim | EXP 06、PITFALLS #7 |
| sheet 400 / 450 | 586 mm 布每邊多 100 mm 堆在側面 | `--sheet_mm 400` | sh400 c1 366×143×121、S1 20;box 布 0 / 杯 0、178×194×122、S1 156 | surface 可用,入箱 0 超出。volume 版另定 500(見 2.B) | EXP 09、THK §4 |
| 網格 35 → 50 | 皺褶解析度 | `--res 50` | c1 高 124 / S1 3;層距 6.6(THK 引述,RUNS.csv 無數字) | 排除(沒幫助) | EXP 07 |
| 壓實目標(press6) | 壓板照箱內腔訂不是照杯子 | 壓實 + 放開 | 放開後回彈 13~17 mm | 定案鏈改為「不壓、四折直接入箱」(fincam) | THK §3、EXP 11 |
| rest shape 烘焙(surface 的 restBendAngles) | 回彈是否彎曲彈性,壓扁形狀寫成靜止形狀 | cr_before(壓前寫)、cr_held(壓住時寫) | 放開 130 / 134(對照 u_c3 134) | **排除**:照樣彈回,撐開層的是自碰撞距離。volume 無此 schema(PhysX 107.3),FP §4.1 仍列為「需換 solver 或重烘焙」的選項 | EXP 08、FP §4.1 |
| 入箱、關蓋、搬箱 | 蓋子不動、搬箱滑走 | 補 meta、reset 前蓋擺開、`--base_collider_pad 0.02 --no_ground_collision` | mb2_x30 滑 35.3 mm → mb6 7.3;fincam 1.7;fincam 入箱 0 / 0 | 採用。搬箱滑動是地板摩擦拖住壓穿 3 mm 底板的布頂點,不是板子摩擦不足 | EXP 10、11、PITFALLS #1 #8 #9 |

### 2.B surface vs volume、材料與阻尼

| 方法 | 問題 | 做法 | 結果數字 | 結論 | 出處 |
|---|---|---|---|---|---|
| surface vs volume | 正式包材選哪個 | 九項對照(外觀、入箱、夾持、他片、速度...) | 穿模 surface 97~156 / 0 / 0,volume ≤ 8 / 0 / 0;重現性 surface 差 6 mm,volume 關蓋前 ≤ 2 mm;計算 surface 2~3 分/段,volume 4 分全程 | **volume 採用**;surface 保留作快速篩選與對照 | DEC、FP §1 |
| 厚度與體積合理性 | 包起來 4.7 倍杯子 | 量層距、布寬 | u 鏈入箱關蓋後 125 × 232 × 213、體積 6.2 L vs 杯子 1.3 L;每層 4.3~5.6 mm,小泡泡紙實物 3~4 mm | 高度不算離譜,寬度是大頭(布 586 mm)。sheet 400 的 surface 達 3.1 倍杯子體積 | THK、FP §1 |
| 楊氏模量 E 掃描 | 皺褶軟硬、撐滿內腔 | E 2e3 為正式,抽樣範圍 1.5e3~3e3 | FP 只有一句「撐滿內腔(E 2e3 才留得住)」 | 採用 E 2e3。**待補:E 掃描逐組數字**(不在本文指定來源內) | FP §1、§3.1 |
| 十字形布 | 用十字形減少角落堆疊 | — | DEC 只寫結論 | **排除**("十字形不用",回彈/撐滿內腔靠箱蓋)。無數字 | DEC 決定 5 |
| 收耳 `--tuck` | 角落翹耳 | tuck 1 vs 0 | 隨機 12 組 tuck=0 的 8 組全部 y 向超出內腔 58~411 點 | **採用 tuck=1**,tuck=0 僅作負樣本 | FOLD_DIVERSITY 失敗模式 1、FP §3.4 |
| 阻尼掃描(edamp / ldamp) | 折疊停留期顫抖 | 10 組短跑 + 2 組完整鏈 | base 停留 RMS 0.358;e0.02 0.213;e0.05 0.162;e0.5 / e2 折不上去(bbox 427×299 / 464×408);ldamp 沒幫助。完整鏈 edamp 0.05:yn 59% / 0%;edamp 0.02:yn 0%(夾持中滑 84 mm) | 見 §3。完整鏈 0/0;展示影片 0.02 | DAMPING |
| 速度掃描 | 7.4 倍實時太慢 | `--vid_every`、`--vid_res`、`--fast_pts`、dt、solver | 四折段基準 7.04;vid_every 4 為 6.52;dt 1/120 為 4.37 但放手後 0%;solver 64 為 4.93;兩者 3.36 | 只採用渲染降頻(省 7~9%,物理不變);`--fast_pts` 無效(tensor API 取不到節點);dt/solver 放寬傷掀開,僅 `--solver 64` 可用於四折粗掃 | SPEED |

### 2.C 夾持(10-07 ~ 10-14)

| 方法 | 問題 | 做法 | 結果數字 | 結論 | 出處 |
|---|---|---|---|---|---|
| 摩擦夾持 | 純摩擦夾不住疊層 | 整包上純摩擦 | 整包夾到 3 點(網格 14 mm);surface 間隙窗口只有 1.5~2 mm | **排除**(單獨用);保留摩擦接觸 | DEC、INTERFACE §5 |
| 綁定夾持(閉合時綁、張開時 RemovePrim) | 摩擦不夠 | VtxXformAttachment 綁指面足跡內最外層頂點 | 單片探針:both 綁 84 點、滑動 ≤ 0.14、邊長比 1.67~1.81;整包 yn 綁 12 點、滑動 < 1 mm | **採用**(文獻:SoftGym / FlingBot / NVIDIA 論壇都走綁定) | DEC、grip_attach/README、LIT |
| pad / 層選擇 | 足跡多大、綁哪層 | pad 16 vs 24;both vs top;gap 4 vs 6;layer_mask | top-only 滑動 0.2~0.7、邊長比 1.86~2.16;both ≤ 0.14、1.67~1.81;mask 含下片 → 下片被掀 125 mm、互穿 22 | 採用 both、只綁最外層片(yn);整包用 pad 24 | grip_attach/README、FP §2 |
| 角尖 vs 邊中段 | 抓哪裡 | 比較 out_ga2 / out_ga3 | 角尖指間只有 1~2 點;邊中段(邊參數 0.3~0.6)yn 12 點、yp 8 點 | 採用邊中段 | INTERFACE §5 |
| arc2 繞壁 | 停在箱內放手會彈回 | `--arc2 1`,弧線終點繞過箱壁頂角 | out_ga3 yn 越線 100% / 放手後 62% | 採用,但 out_ga3 是起始半開(夾前覆蓋 48%)的單次樣本 | INTERFACE §5、DRAG §0 |
| 有限剛度綁定 | 無限剛度會扯動他片 | A1 schema stiffness/damping,k ∈ {inf ... 0.01} | 伸長中位全 0.02~0.03 mm,k = 0.01 理論應伸 46 mm 卻為 0 | **排除**:PhysX 107.3 把 attachment 當硬約束 | DRAG §1 |
| 力限代理 | 用 D6 drive + maxForce 當保險絲 | `--attach_proxy 1`,k 500,fmax 0.2 / 0.5 / 1.0 | yn 越線 30~41%、放手後 0%;代理落後全程 ≤ 1.0 mm(沒有限到力) | **排除** | DRAG §1 |
| 釘住 xp/xn | 掀 yn 時他片被拖 20% | `--hold_others 1`;修正版 topfree 33 點 | 第一版全是 400 mm 片(漏 `--sheet_mm 500`)且邊長比 4.7~5.2 觸發守衛;修正版 p12:yn 100 / 100 / 他片 9.0;own12:釘住中 5.2、放開後 16.3、yn 只掀 44% | **排除**:釘住期間有效、放開就回彈;釘 167 點反而扯整張(38%) | DRAG §2、第二輪 |
| 先解耦再掀 | 先抬再抽 | `--lift_first_mm 12/15` + 弧線外延 30 | D1 守衛兩次觸發、滑 83 mm;D2 yn 4 / 66 | **未測到本體**:外延 30 把布拉斷守衛 | DRAG 第二輪 |
| 綁定選點(site_pad / mask / top) | 他片拖動是不是綁到被壓頂點 | `--attach_mask_own`、`--attach_layer top` | 遮罩實際排除 0 點(等於基準重跑);C1 他片 22.5 | 排除;證明他片拖動來自 yn 中段翻起時接觸摩擦帶動 | DRAG §3 |
| 狀態選點 + 重夾 | 抓取分布太寬(基準 yn 越線 0~100%) | `--grasp_site state --grasp_retry 2`,7 候選 | 綁點 14~31(基準 0~24);越線 5 次 11 / 79 / 54 / 82 / 100;≥ 80% 只有 2/5;放手後 0~75% | **採用**(綁 0 點的情況消失),但沒讓越線收斂 | ROBUST |
| 基準重現性 | out_ga3 是否穩定 | 原指令重跑 3 次 | yn 越線 / 放手後:44 / 16、0 / 0(沒綁到)、42 / 1;夾前覆蓋 79~91% | **out_ga3「100% / 62%」只是一次樣本**;之後判讀都要 ≥ 3 次 | DRAG 第二輪 |

### 2.D 掀開、翻出箱外、放手(10-14 晚 ~ 10-15)

| 方法 | 問題 | 做法 | 結果數字 | 結論 | 出處 |
|---|---|---|---|---|---|
| 越壁 30(PEEL A) | 第 2 段繞壁從未跑(R2 < 12 mm) | `--arc2_over_mm 30` | A:2/3 達標(100 / 100,第 3 次守衛);B 下壓 0/3;C 限半徑 0/3;基準 0/5 | 當時最好,但後續證實是臨界平衡碰對邊 | PEEL |
| 選點過濾 + 實際鉸點(PEEL2) | 選點在箱壁頂、鉸點 nan | `--site_xmax_mm 50`、`--hinge_from_state 1` | yn 0/5(越線 53~98%,放手後 0~3%);yp 越線 ≥ 80% 1/5 | 排除:候選只剩 1 個、越壁量被材料長上限截斷 | PEEL2 |
| 越壁不截 + 質心閉環(PEEL3) | 質心過壁外才放手 | `--arc2_over_cap 0`、`--arc2_target centroid` | 開環 0/2,閉環 0/5;c4 質心 −130 仍放手翻回 −78;yp 閉環 5/5 守衛 | 排除:片被拉長而非翻出;「質心過壁就留得住」被推翻 | PEEL3 |
| 貼蓋(PEEL4,arc2_lay) | 讓片躺到打開的蓋上 | 箱外指頭下限 蓋頂 + 2 | yn 1/5(L5 98 / 100)、yp 0/5;夾爪只多下降 4~6.5 mm(指頭轉 180° 傾斜佔 ~15 mm) | **停止「單手掀 + 放手靠重力」**:成功與失敗的掀完狀態無可分辨差異,是立在內壁那段的臨界平衡 | PEEL4 |
| 質心閉環 / 邊長比停 2.0 | 防止拉過頭 | `--arc2_er_stop 2.0` | 3 次在往下一開始就凍結 | 沒救到 | PEEL3、PEEL4 |
| 雙手壓板 | 第二隻手壓住躺在蓋上那段 | `--hand2 press`,壓到 蓋頂 + T + 1 | 0/3(yn)、0/3(yp);放手 0.5 s 內越線 100% → 7% | **排除**:位置式壓板沒有正向力 | HAND2 |
| 雙手綁定 | 同上,改綁定 | `--hand2 attach` | yn 撐住期間 54~100%;撤走後 2/5 留住(但壁外只剩 8% / 3%),yp 0/5(8 次裡 0 次) | **改為「一直拿住」**:撐住期間有效、一撤即翻回;壓 3 s 不會定型 | HAND2、FP §4.1 |
| 力限 / 兩片互壓 | 放手後仍開 | yn、yp 都掀完互相壓住再撤 | 未試 | 待定(替代:材料加塑性) | HAND2、FP §4.1 |
| yp 守衛連續次數 | yp 守衛被單格尖峰(2.3~2.8)放手 | `--guard_yp 2.6 --guard_n 2` | yp 3/3 拿住到取杯前(舊 1/3) | **採用** | EXTRACT2、FP §4.2 |
| yn 守衛連續次數 | X2 的 yn 被 2.3 單格尖峰放手 | `--guard_yn 2.6`(套 `--guard_n 2`) | yn 守衛 3/3 沒觸發 | **採用** | EXTRACT3 |
| 取杯:垂直抬 | 杯子在布袋裡 | `--extract 1`(抬 150 → +x 移 200) | 3/3 取杯 OK、穿杯 0;布被帶起 40.6~86.6%;+x 落點被打開的 fxp 蓋擋住(杯放在蓋上 z 221) | **排除**(帶起太多) | EXTRACT |
| 取杯:水平滑出(slide) | 降低帶起 | `--extract_mode slide`(抬 20 → 斜升過壁頂 → 水平 −y 260 → 落地) | 3/3 出箱落地;帶起(抬起時)29.6 / 32.2 / 25.7%,落地後 53.6 / 47.6 / 30.6%;穿杯 3~4 點 | **採用**;問題在滑過 yn 壁時把掛著的 yn 布拖出 | EXTRACT2 |
| 過壁 +40 | 滑過壁不拖布、不穿杯 | `--slide_clear_mm 40` | 穿杯 3/3 = 0(v2 有 3~4 點) | **採用** | EXTRACT3 |
| hand2 tuck | 滑出前手 2 把 yn 往外下壓 | `--hand2_tuck_mm 20` | 2/3 把 yp 扯斷(邊長比 3.4~5.4);X1 落地 22.8% | **排除**(有害) | EXTRACT3、FP §4.3 |
| 落點 `--extract_out_mm 280` | 落點與打開的 yn 蓋重疊 15 mm | 直接用 280 | 需 ≥ 275.3 mm 才不碰 | 採用 | EXTRACT3 |
| v4 驗證(正式 demo 旗標) | 三次驗證 | extract4/X1~X3 | yn 3/3、yp 3/3 拿住;穿杯 0;落地後帶起 33.8 / 19.1 / 36.6% | 目前正式版 | EXTRACT3 v4 |

### 2.E 折法多樣性、手臂端

| 方法 | 問題 | 做法 | 結果數字 | 結論 | 出處 |
|---|---|---|---|---|---|
| 折序 24 種 | 下游要多種包法 | `--fold_order`,各跑 `--until box` | 嚴格 PASS 9/24,物理 PASS 20/24(嚴格 = 加邊長比 [0.50,1.65];預設折序兩次邊長比 1.56 / 1.66,門檻落在雜訊內) | 24 種全部能包進箱;最外層 22/24 = 最後折的那片(例外:yn,yp,xp,xn 與 yp,yn,xn,xp 兩片並列 ~22%) | FOLD_DIVERSITY |
| 隨機抽樣 12 組 | 杯偏位 ±30、轉向 0/90/180/270 ± 10°、布 440~560 | `fold_variants.py --n 12 --seed 7` | 嚴格 0/12、物理 2/12;tuck=0 的 8 組全超出;r7_08、r7_11 整鏈搬後 / 開蓋後超出 0、穿杯 0、自穿 3~4;infeasible 1 組(r7_09) | 抽樣固定 tuck=1;布小 + 偏位會 infeasible | FOLD_DIVERSITY、FP §3.4 |
| 手臂 r1 | 夾持軸平行布邊切線 | 綁定 | 綁到 0 點 | 排除;夾持軸必須垂直布面 | INTERFACE §5 |
| 手臂 r2 | v2 軌跡、高度帶放寬 14 mm | 綁定代理方塊 | yn 越線 56~60%;他片 29%;下降穿入 6.9 mm | 未過 | INTERFACE §5 |
| 手臂 r3 | 數值 Jacobian 修 72 mm 平移 | — | 發散 | 排除;改 lula IK 重解 | INTERFACE §5 |
| 手臂 v3 u0.45 | lula 重解 | — | 越線 26%、放手後 2%、他片 79%;綁 1 點 | 排除(指頭把布壓下去) | INTERFACE §5 |
| 手臂 v3 u0.60 | 最好一組 | 自由邊外 8~24 mm 垂直下降、滑入 8 mm 再合指;R 143 掃到 100° | 越線 64~68%;放手後 56~66%;他片 16~52%(兩次差很大);下降穿入 18 mm(指頭盒 36×70×60 插進皺布) | **最佳但未全過**;210 組 φ×ψ×偏移沒有一組指頭盒完全不插布 | INTERFACE §5 |
| 手臂 v3 yp u0.40 | 掀 yp | — | 越線 21%、放手後 22%;綁 5 點、σ 0.015 近奇異 | 排除 | INTERFACE §5 |

---

## 3. 抖動與回彈

### 3.1 抖動(顫抖)
- **現象**:4 mm volume 四面體板(6125 tets、selfCollision 開)折疊停留期明顯顫抖;surface 版因有 sleep 而小(FP §1)。
- **度量**:每格頂點位移 RMS(mm/格,1/30 s),`vol/jitter.py`。基準 base(0/0)停留 RMS 0.358、hf 0.527,靜置 0.260 / 0.431。
- **已驗證的處方**(DAMPING.md,短跑 `--until fold`):
  | 設定 | 停留 RMS / hf | 靜置 RMS | 自穿max / 反轉max | 邊長比 | 折到位 |
  |---|---|---|---|---|---|
  | base 0 / 0 | 0.358 / 0.527 | 0.260 | 9 / 0 | [0.472, 1.723] | 是 |
  | edamp 0.02 | 0.213 / 0.252 | 0.192 | 0 / 2 | [0.321, 1.828] | 是 |
  | edamp 0.05 | **0.162 / 0.188** | 0.225 | 2 / 6 | [0.169, 2.191] | 是(局部拉扯) |
  | edamp ≥ 0.2 | — | — | — | — | 0.5 以上布跟不上錨點,折不上去 |
  | ldamp 1 / 5 | 0.302 / 0.332 | 0.557 / 0.482(靜置反而變大) | — | — | 是 |
- **edamp 0.02 的狀態:已採用,但僅限展示折疊/入箱影片;完整鏈未採用**。短跑顫抖降約 40%、自穿 0、邊長比最接近 base。
- **完整鏈上 edamp 0.02 為「待驗」而不是「已證實有害」**:完整鏈各只跑一次——
  | | out_ga3(0/0) | edamp 0.05 | edamp 0.02 |
  |---|---|---|---|
  | yn 越過折線 | 100% | 59% | 0%(夾持中滑 84 mm) |
  | yn 放手後 | 62% | 0% | 0% |
  | yp 越過 / 放手後 | 73% / 67% | 0%(滑 92 mm)/ 0% | 38% / 0% |
  | wall | 639 s | 1163 s | 約 1160 s |
  DAMPING 本身註明「無法分辨這是阻尼造成,還是改了初始條件後混沌發散」。但依 §2.C 的基準重現性(同指令 yn 越線 0~100%),單次比較本來就分不出差異;**要把「無抖動」併入發行版,需對 edamp 0.02 的完整鏈各跑 ≥ 3 次看分布。** 目前結論:完整鏈 0 阻尼,抖動仍在。
- **夾爪版 / 其他抗抖手段**:**待補:夾爪版**(vol/JAW.md)。
- 快速模式(降頻渲染等)的品質結論:**待補:快速模式**(vol/QUALITY.md);目前已知僅 SPEED.md:`--vid_every 4 --vid_res 640x360` 物理不變,dt 1/120、solver 64 傷掀開(放手後 62% → 0~13%)。

### 3.2 Q 彈回彈
- **根因**(依序從證據收斂):
  1. surface 階段:壓實放開後回彈 13~17 mm(133 vs 壓住 117)。曾懷疑彎曲彈性,但把靜止形狀設成壓扁形狀(cr_before / cr_held)照樣彈回 130 / 134,降 bend 反而更彈 → 撐開層的是**自碰撞距離**,不是彎曲(RPT §1.5、EXP 08)。
  2. volume 階段:4 mm 板立在箱內壁的那段有持續的**彎曲回彈**,材料**無塑性**(PhysX 107.3 volume 無此 schema)。雙手實驗:第二隻手綁住期間 yn 越線 54~100%、yp 70~97%;解綁抬起後 yn 撤後 0~2%(少數留在內壁)、yp 0/8。壓 3 s 也不會定型(HAND2)。
  3. 放手瞬間是立在箱壁上的臨界平衡:往牆倒就留住、往內倒就翻回;PEEL A~PEEL4 共 7 + 5 + 5 + 3 次只有 3 次留住,成功與失敗的掀完狀態(質心、半徑、貼蓋點)無可分辨差異(PEEL4)。
- **已採用的處方**:不消除回彈,**改 demo 定義**——掀開後由第二隻手綁住(attach)躺在蓋上那段並一直拿住(`--hand2 attach --hand2_keep 1`),yp 以 `--hold_yp 1` 不排放手軌跡。此定義下取杯 3/3 出箱、穿杯 0。
- **仍存在的限制**:
  - 沒有塑性 → 折痕不留形;任何「放手後仍開」都不成立。
  - 要真正解決,只剩:材料加塑性(換 solver 或 rest-shape 重烘焙)、或兩片互壓再撤(未試)。
  - 使用者要求的「沒有 Q 彈回彈」在發行版中**以持續拿住規避,並未從材料上消除**。

---

## 4. 判準與現況

判準定義:FP §2 驗收(入箱 0 超出、穿杯 0、邊長比、yn 越線 ≥ 80%、放手後 ≥ 50%、他片 < 5%)+ demo 追加(yn/yp 拿住、出箱落地、落地後布被帶起 < 30%)。
下表「最新 3 次」取各項最近三次有該欄位的完整鏈;無法取三次的註明。

| 判準 | 最新 3 次分布 | 是否達標 | 出處 |
|---|---|---|---|
| 入箱 0 超出 | SPEED 完整鏈四組(基準、solver 64、dt 1/120、兩者)全部 0;FOLD_DIVERSITY 整鏈 r7_08、r7_11 搬後 / 開蓋後 0(僅 2 次) | 達標(分布窄) | SPEED、FOLD_DIVERSITY |
| 搬運後仍在箱內 | r7_08、r7_11 搬後超出 0;surface 側 fincam mb_x30 位移 1.7 mm | 達標 | FOLD_DIVERSITY、EXP 11 |
| 穿杯 0 | extract4 X1~X3 全 0;EXTRACT3 X1~X3 全 0;EXTRACT2 X1~X3 為 4 / 0 / 3 | 達標(v4 起) | EXTRACT2、3 |
| 邊長比 | out_ga3 [0.509,1.625]、預設折序兩次 1.56 / 1.66;DRAG 基準 yp [0.526,1.970];FOLD 預設組 [0.57,1.56] | 門檻 0.95~1.05(FP §2)沒有任何組達到,FOLD_DIVERSITY 判定該門檻在雜訊內,改用 [0.50,1.65] | FP §2、FOLD_DIVERSITY |
| yn 越線 ≥ 80%(掀完) | PEEL4 L3~L5:11 / 69 / 98;ROBUST r5~r7:54 / 82 / 100;HAND2(attach 撐住期間)A3~A5:1 / 65 / 78 | 不穩:2~3 次中 1 次 | PEEL4、ROBUST、HAND2 |
| yn 放手後 ≥ 50% | PEEL4 L3~L5:0 / 0 / 100;HAND2 撤走後 A3~A5:1 / 100 / 2 | **不達標**(臨界平衡,見 §3.2) | PEEL4、HAND2 |
| yn 拿住(持續拿住定義) | extract4 X1~X3:越線 76% → 76%、56% → 99%、1% → 0%,守衛都沒觸發 | 守衛達標;X3 手 2 綁在 x = 85,yn 只過線 1% | EXTRACT3 v4 |
| yp 拿住 | extract4 X1~X3:越線(取杯前)80 / 98 / 97%,結束 79 / 97 / 96%;守衛 0 次 | 達標 3/3 | EXTRACT3 v4 |
| 落地後布被帶起 < 30% | extract4 X1~X3:33.8 / 19.1 / 36.6%(抬起時 28.5 / 22.0 / 35.5) | **1/3**(EXTRACT3 X1 曾 22.8%,同旗標不同次差很大) | EXTRACT3 |
| 他片被拖 < 5% | DRAG base_r1~r3(yn):4.9 / 1.9(沒綁到)/ 18.8;PEEL4 L3~L5:22.6 / 62.0 / 70.2 | **不達標**(綁定無限剛度,他片 5~70%) | DRAG、PEEL4 |
| 綁點數 ≥ 6 | PEEL4 yn L3~L5:22 / 13 / 9;extract4 yn:25 / 14 / 14 | 達標(綁 0 點的情況已由狀態選點消除) | PEEL4、EXTRACT3 |
| 滑動 < 1 mm | extract 之前各組中位 0.07~0.14 mm;守衛放手後滑動 74~172 mm 的屬失敗樣本 | 達標(未放手時) | PEEL4、ROBUST |
| 自穿 / 反轉 | FOLD 嚴格:自穿峰 < 20、反轉 0;DAMPING base 9 / 0、e0.02 0 / 2;SPEED 完整鏈 5 / 5(基準)~ 25 | 受 GPU 非決定性影響,±4 | DAMPING、SPEED |
| 抖動 | base 停留 RMS 0.358,e0.02 0.213,e0.05 0.162(三組短跑,非 3 次重複) | 完整鏈未降 | DAMPING |

---

## 5. 已知限制與下一步

1. **他片拖動**:綁定無限剛度,掀 yn 時透過接觸摩擦把相連的 xp/xn/yp 帶動(5~70%);有限剛度、力限代理、釘住 xp/xn 都試過沒用(§2.C)。下一步:降低 yn 與 xp/xn 的接觸摩擦(指面 2.0、布布摩擦未掃)、或改折序(`--fold_order`)讓待掀片本來就少被壓。
2. **指頭盒**:手臂夾指外框 36 × 70 × 60 mm,抓點離牆 < ~30 mm 會撞牆或蓋;手臂 v3 最好(u0.60)下降穿入仍 18 mm,210 組 φ×ψ×偏移沒有零穿入。下一步:縮小指頭外框或換抓法(夾爪版見 JAW)——**待補:夾爪版**。
3. **塑性**:volume 無塑性,折痕不留形、放手必回彈。下一步:換 solver 或 rest-shape 重烘焙,或兩片互壓再撤(未試)。
4. **落地後布被帶起**:杯在布袋裡滑出時帶起 19~37%(< 30% 只有 1/3);主因是滑過 yn 壁時拖出掛著的 yn 布、以及落點與打開的 yn 蓋重疊。下一步:過壁再抬高(+30~50 mm 之外)、改從 x 側出箱、或手 2 先把 yn 壓低但不能扯到 yp(tuck 已證實有害)。
5. **抓取不可重現**:同指令 yn 越線 0~100%,四折後夾前覆蓋 48~91%;任何單次「達標」都不算。下一步:所有改動用 ≥ 3 次分布驗收。
6. **速度**:10.7 分鐘 / 86 s sim;可靠的加速只有渲染降頻。surface 版可做參數粗篩(約 5 分鐘)。
7. **阻尼完整鏈驗證**:edamp 0.02 需 ≥ 3 次完整鏈分布才能決定是否併入發行版。
8. **GPU 共用**:同時開兩個錄影會 OOM;啟動前查 `nvidia-smi` < 20000 MiB;系統 `python3` 沒有 trimesh,需用 `/isaac-sim/python.sh`(PITFALLS #12)。
9. **手臂場景放手**:`RemovePrim` 在手臂場景會無訊息結束程序,用 `attachmentEnabled=False`(INTERFACE §5)。

---

## 6. 檔案地圖

| 要看什麼 | 檔案 |
|---|---|
| 最終方案、surface vs volume、正式旗標、折序多樣性、掀開四輪結論 | `FINAL_PLAN.md`(§1~4.3 是主幹) |
| 為何選 volume + 綁定夾持 | `work/DECISION_phase3.md`、`work/LIT_grasp_20261014.md` |
| 厚度 / 體積合不合理(泡泡紙口徑) | `work/REPORT_THICKNESS.md` |
| 錨點根因、越線、放手錨點、入箱、搬箱(09-30) | `work/REPORT_20260930.md` |
| surface 階段逐批實驗(01~11)與 RUNS.csv 對照 | `work/EXPERIMENTS.md` |
| 踩過的坑(meta 缺失、sleep 掩蓋回彈、版本對應等) | `work/PITFALLS.md` |
| 阻尼掃描(顫抖數字、完整鏈) | `vol/DAMPING.md`(`vol/jitter.py`、`vol/damp/`) |
| 速度掃描 | `vol/SPEED.md`(`vol/speed/`) |
| 他片拖動三方案 + 基準分布 | `vol/DRAG.md` |
| 狀態選點 / 重夾 | `vol/ROBUST.md` |
| 掀開軌跡四輪 | `vol/PEEL.md`、`PEEL2.md`、`PEEL3.md`、`PEEL4.md` |
| 雙手壓板 / 綁定 | `vol/HAND2.md` |
| 取杯 v1、v2、v3、v4 驗證 | `vol/EXTRACT.md`、`EXTRACT2.md`、`EXTRACT3.md`;正式指令 `vol/extract4/run.sh`,三次結果 `vol/extract4/X1~X3/`(`wrap_vol.log`、`wrap.mp4`、`key_*.png`) |
| 折法多樣性 24 + 12 組 | `vol/FOLD_DIVERSITY.md`、`vol/VARIANTS.csv`、`vol/videos/VARIANTS_grid.mp4` |
| 閉合時綁定模組 | `vol/grip_attach/README.md`(`attach_grip.py`) |
| 手臂端座標、綁定介面、手臂 r1~v3 數據 | `arm/INTERFACE.md`(`arm/peel_traj_v3.py`、`arm/cloth/videos/peel_v3_best.mp4`) |
| 主程式 | `vol/wrap_vol.py`、`volcommon.py`、`vol_pen.py`、`layer_order.py`、`grasp_plan.py`、`fold_variants.py` |
| 驗收腳本 | `work/tests/run_checks.py`(10 函式 23 項) |
| 夾爪版(JAW) | **待補**:`vol/JAW.md` 尚未產生 |
| 快速模式品質(QUALITY) | **待補**:`vol/QUALITY.md` 尚未產生 |
| EXTRACT3 v5 | **待補**:現有檔案止於 v4 驗證 |
