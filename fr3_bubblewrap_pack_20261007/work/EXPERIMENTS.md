# EXPERIMENTS —— 每一批:假設 → 變數 → 數字 → 結論 → 留下的旗標

內容以 `REPORT_20260930.md`、`REPORT_THICKNESS.md` 為準;**數字以 `RUNS.csv` 為準**(欄名照抄)。
兩者對不上時標 **⚠ 不一致** 並列出兩個數字,不挑。縮寫:高 = `bbox_z`;S1 = `自穿模(S1)`;
層 = `層數中位 / 層間距中位 / 疊層總厚`(layer_gap,shrink 25mm,只算 35×35 網格);壓/放 = `壓住z / 放開z`。
共用:`--young 2e4 --bend 4 --tex bubble_normal.png`;cont/rest 沒寫就是 5 / 1 mm。

## 01_baseline —— 交接時的參數原樣跑
- 假設:照交付包跑一遍當基準。變數:無(`out_c1` 用的是當時的原版 wrap_sim,log 沒有 collider 行、也沒留 stdout)。
- c1 `out_c1`:高 125、S1 13、層 1 / 5.46 / 18.14 —— 兩片只在中線對接,不是疊。
- c2 `out_bl_c2`:高 162、S1 257、層 5 / 6.88 / 54.26(`out_c2` 是較早一次:高 164、S1 349、層 6 / 7.04 / 60.18)。
- c3 `out_bl_c3`:壓 138 / 放 163、S1 512。box:`out_bl_box` 布超出 148(全部高於口,缺 meta 蓋子沒動,invalid);`out_bl_boxmeta` 超出 82(x 7 / 底 75),蓋子 t=0 壓扁,invalid。
- ⚠ 不一致:`HOW_TO_VIEW.md` 寫「基準四折疊層總厚 43mm、壓實後 29mm」;RUNS.csv `out_bl_c2` 54.26、`out_c2` 60.18、`out_bl_c3` 47.96。
- 結論:包裹太高的根因是錨點幾何(尖端釘在 杯頂+12+k×layer)。留下:`carton_w131.meta.json` symlink。

## 02_offsets —— 縮 collider 偏移量 / 加解算(v1 / v2 / v3 / v3b)
- 假設:層間距 5mm 來自 contactOffset/restOffset,縮小就能疊薄。
- 變數:v1 `--cont 0.002 --rest 0.0002`;v2 再加 `--thick 0.004 --layer_mm 4`;v3 再加 `--solver 128 --col_iter_mult 2`;v3b `--ccd`。
- c1:v1 高 129 / S1 104 / 間距 5.44;v2 125 / 288 / 7.13;v3 131 / 59 / 8.03;v3b 131 / 118 / 6.66。
- c2:v1 144 / 1430;v2 147 / 2237;v3 165 / 2185。c3(有 sleep):v1 132 / 2403;v2 124 / 3488;v3 139 / 3726。
- ⚠ 不一致:REPORT §1-3 寫「contactOffset 5→2mm 自穿模 13 → 400~3700」;RUNS.csv cont=2 的 c1 段是 59 / 104 / 118 / 288(v4a_c1 413),c2/c3 段 1430~3726。
- 結論:層間距沒變(5.46→5.44),只是互穿 → 全批標 invalid(高度不可信)。**維持 cont 5 / rest 1**。留下:`--cont --rest --self_filter --pair_freq --col_iter_mult --ccd`(都沒幫助)。

## 03_anchor —— 錨點終點壓低(v4a / v4b / v4c)
- 假設:尖端停在 杯頂+12mm 把布吊高;`--hold_mm 2` + 壓實不建錨就能疊低。
- v4a(hold 2、thick 4、cont 2 / rest 0.2、layer 3):c1 高 116 / S1 413 / 層 1 / 4.06 / 14.78;c2 138 / 1796;c3 壓 114 / 放 114 / S1 2566(sleep 凍住,invalid)。
- `v4a_c3_nosleep`:壓 114 / 放 127 / S1 2336 —— 關 sleep 才看得到回彈。
- `v4b_c3`(基準 c2 → 壓實不建錨,有 sleep):壓 117 / 放 149 / S1 519 / 疊層 41.04。`v4c_c1`(v4a + tip 40):高 122 / S1 134 / 層 2。
- 結論:壓實段一定要 `--no_anchor --no_sleepy`;薄 offset 仍是互穿。留下:`--hold_mm --no_anchor`。

## 04_press_isolate —— 單獨拆壓實段(p0~p3,起點都是 out_bl_c2)
- 假設:回彈來自 restOffset 或彎曲剛性。變數:p0 無錨無 sleep;p1 +rest 0.2;p2 +bend 1;p3 兩者。
- p0 壓 117 / 放 141 / S1 394 / 疊層 35.80;p1 119 / 143 / 888 / 28.09;p2 117 / 152 / 433 / 46.36;p3 119 / 137 / 897 / 28.75。
- 結論:rest 0.2 層間距減半(8.81→4.07)但 S1 翻倍;bend 1 回彈更大(放開 152)。都不採用。留下:`--press_off 6` 的用法。

## 05_tipover_thin —— 尖端越線(q)、薄膜(u)、薄+rest 0.2(r / s)
- 假設:兩片在中線對接只重疊 20mm;尖端越過中線 40mm 才會真的疊。
- q(`--tip_over_mm 40`):c1 高 122 / S1 **2** / 層 2 / 4.37 / 11.58;c2 158 / 55 / 6 / 6.57;c3 壓 117 / 放 133 / S1 144 / 疊層 31.02。
- u(q + thick 4 + layer 5 + hold 6):c1 116 / 3 / 4.20;c2 147 / 136;c3 117 / 134 / 247 / 疊層 33.64。
- r(thick 4 + rest 0.2 + hold 2,cont 5):c3 114 / 124 / **3317**;s(r + bend 1):c3 114 / 130 / 4316 —— 互穿,invalid。
- 結論:**越線是唯一乾淨的改善**(S1 三段 2/55/144 vs 基準 13/257/512)。留下:`--tip_over_mm`(建議 40;定案鏈用 0,見 11)。

## 06_release —— 折到位就放掉錨點(t / t2 / t3 / t5)
- 假設:attachment 可以在模擬中放掉(探針證實),放掉後布會自然疊下。變數:`--release_after 0.3`,c2 `--no_hold`;t2 = bend 1;t3 = 薄 + 保留 hold;t5 = t3_c1 起、c2 不放手。
- `t_c1_bad` / `t2_c1_bad`:放手時方塊掃過布 → S1 19864 / 13754,W1 0%,後續 `*_c2_bad` 同樣 invalid。改 RemovePrim 後重跑:
- t:c1 高 113 / S1 9;c2 **x 363**(+x 折翻回地上)/ S1 244;c3 壓 109 / 放 107。t2:c1 113 / 3;c2 156 / 148 / 層 4 / 9.69;c3 117 / 130 / 229。
- t3:c1 109 / 3;c2 x 299 / S1 299;c3 117 / 137 / 293。t5:c2 148 / 462;c3 117 / 151 / 626;box 布超出 1(高於口)。
- 結論:放手可行,但 bend 4 + no_hold 會讓後折邊翻回;第二段要保留 hold。回彈 13mm(t2)最小但仍在。留下:`--release_after --no_hold`。

## 07_res —— 網格 35→50
- `w_res50_c1`:高 124 / S1 3。RUNS.csv 無層數欄(非 35×35,collect 不算)。REPORT_THICKNESS 寫「34→50 層間距反而 6.6」,RUNS.csv 無數字可比對。
- 結論:加密沒有幫助。留下:`--res`(既有)。

## 08_crease —— 摺痕定型(restBendAngles 寫入,腳本 `archive_src/wrap_sim_crease.py`)
- 假設:回彈是彎曲彈性,把靜止彎角設成壓扁形狀就不會彈。起點 `u_c2`。
- `cr_before`(壓之前寫入):壓 117 / 放 130 / S1 301;`cr_held`(壓住時寫入):117 / 134 / 325;對照 u_c3 放 134。
- 結論:照樣彈回 → 撐開層的是自碰撞距離,不是彎曲。旗標沒有併回 wrap_sim.py。

## 09_sheet —— 布縮小(sh450 / sh400)
- 假設:586mm 布每邊多 100mm,堆在側面;縮布可降寬度與體積。
- sh450:c1 450×153×116 / S1 44;c2 183×175×125 / 152;c3 240×177×118(invalid:沒帶 `--sheet_mm`,邊長比中位 0.769)。
- sh400:c1 366×143×121 / S1 20;c2 155×169×134 / 99;c3 172×183×130 / 108(invalid,邊長比 0.688);box 布 0 / 杯 0、178×194×122、S1 156。
- `sh400_mb_yz` invalid(杯子方位與包裹不符)。結論:400 可用,四折完的包裹直接入箱 0 超出。留下:`--sheet_mm 400`。

## 10_box_move —— 關蓋 + 搬箱(lidcheck、mb ~ mb6)
- 假設:箱體 kinematic 平移,包裹靠摩擦跟著走。起點:`mb_*` 用 u_c3,其餘用 `lidcheck`(u_c3 入箱關蓋:布 0 / 杯 0、高 125、S1 386)。
- `mb_x30` 相對位移 19.2mm、超出 17→20;`mb2_x30` 35.3(3→6);`mb2_x30_slow` 36.1;`mb3_x30`(ktarget)34.7;yz 方向都 1~2mm。
- `mb4_x30`(`--ground_z -0.02`)7.7;`mb5_x30`(`--base_collider_pad 0.02`)17.1;`mb6_x30`(pad + `--no_ground_collision`)7.3、超出 3→3;`mb6_x30_fast` 9.0。
- 結論:x 方向滑走是**壓穿 3mm 底板的布頂點被地板摩擦拖住**(摩擦探針:板子帶得動布)。留下:`--movebox --move_t --move_wait --move_mode --ground_z --no_ground_collision --base_collider_pad --in_box_already`。

## 11_final —— 新折序全鏈(fin / finA / finB / fincam)與舊折序 DEMO(dm)
- fin(sheet 400、新折序、c3 `--press6 193,167,115`):c1 144×365×118 / S1 14;c2 170×184×156 / 80;c3 壓 117 / 放 138(x×y 178×248);box 布 **24** 超出(y 24,口 1)、杯心 (-15,33,55)。
- ⚠ 不一致:`PROMPT_status_20261002.md` 寫 fin_c1 bbox 144×**366**×118;RUNS.csv `fin_c1` 144×**365**×118(差 1mm,取 log 最後一行 bbox)。
- finA(press6 193,200,115):c3 放 138;box 布 **77** 超出(全 y)。finB(c2 直接入箱,不壓):box 布 0 / 杯 0、184×203×126;mb_yz 位移 8.7、mb_x30 12.2。
- fincam(= finB 鏈 + `--cam_ref 0.586`):c1 S1 26;c2 118;box 0 / 0、163×172×122、W1/W3 100;mb_open 位移 2.5mm、超出 6→6(全部低於箱底);mb_yz 1.9;mb_x30 1.7。
- dm(舊折序 wrap_sim_old.py):c3 壓 117 / 放 124;box 0 / 0;mb 8.8(0→3);mb_open 9.8(0→5)。
- unbox:`fin_unbox`、`fincam_unbox` 跑完攤平,最終 S1 56 / 80、邊長比中位 1.051 / 1.060;布穿杯(邊級別)`pen_fincam_unbox.txt` 最多 58 條、最深 3.8mm;`pen_fin_unbox.txt` 最多 69 條、最深 4.0mm(開箱段沒過 S2)。
- 結論:定案 = fincam 鏈(不壓、四折直接入箱)。留下:`--move_open --cam_ref`。

## 探針(runs/probes_logs/)
- attachment 放手(`detach_m1~m7`):m1 / m5 / m7 成功(放掉後 1s 掉 0.298m),m2 / m3 / m4 / m6 失敗 —— RemovePrim / attachmentEnabled=False / SetActive(False) 有效,改 stiffness、清 relationship 無效。
- 摺痕(`crease_m0~m8`):多數「回彈」,m4 陣列寫入「沒有作用」,m5「介於中間」,m8「有作用但往另一邊折」→ 見 08。
- 摩擦(`probe_fric_a~g`):kinematic 板平移 300mm,布質心相對板 0~5.8mm,全部「帶得動」⇒ 搬箱滑動不是板子摩擦不足,是地板(見 10)。
