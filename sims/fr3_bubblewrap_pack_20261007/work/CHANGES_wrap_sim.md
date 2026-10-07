# CHANGES_wrap_sim —— 2026-09-30 ~ 10-02 對 `wrap_sim.py` 的修改

比對基準:`archive_src/wrap_sim.py.orig_20260930`(交付原檔)→ 根目錄 `wrap_sim.py`(10-02 07:44)。
中間版本:`archive_src/wrap_sim.py.before_movebox`(09-30 03:00)、`archive_src/wrap_sim.py.before_foldorder`(10-02 06:57)。
所有新旗標預設 = 舊行為。

## 新增旗標(`diff` 的 argparse 新增項,共 21 個)
| 旗標 | 預設 | 作用 | 建議值 |
|---|---|---|---|
| `--cont` | 0.005 | 布 collider contactOffset(m),原寫死 5mm | **0.005**(縮 = 互穿)|
| `--rest` | 0.001 | 布 collider restOffset(m),原寫死 1mm | **0.001** |
| `--self_filter` | -1.0 | selfCollisionFilterDistance(m);<0 不設 | 不設(沒幫助;未單獨掃過)|
| `--pair_freq` | 0 | collisionPairUpdateFrequency;0 不設 | 不設 |
| `--col_iter_mult` | 0 | collisionIterationMultiplier;0 不設 | 不設(v3 試 2,救不回互穿)|
| `--ccd` | off | enableSpeculativeCCD | 不開(v3b 沒幫助)|
| `--hold_mm` | 12.0 | 折完錨點停在杯頂上方幾 mm(原寫死 LZ_HOLD) | 6(≥ thick + 2mm)|
| `--no_anchor` | off | 完全不建錨點 | 壓實 / 入箱 / 搬箱段**必開** |
| `--tip_over_mm` | 0.0 | 折邊尖端越過杯子中線多少 mm | 40 讓兩片真的疊(q / u);定案鏈用 0 |
| `--release_after` | -1.0 | 每折到位後幾秒放掉錨點(RemovePrim);<0 不放 | 不用(定案);實驗用 0.3 |
| `--no_hold` | off | 第二段不建 100 個 hold 錨 | **不要用**(bend 4 時折邊翻回)|
| `--movebox` | "" | 搬紙箱 X,Y,Z(m);箱體+4 蓋 kinematic 平移,杯子動態 | `0,0.20,0.10` |
| `--move_t` | 6.0 | 搬運秒數(smoothstep) | 6 |
| `--move_wait` | 2.0 | 搬之前靜置秒數 | 2 |
| `--move_mode` | xform | `xform` 每步 set_world_pose / `ktarget` PhysX kinematic target | xform(ktarget 沒改善,mb3)|
| `--ground_z` | 0.0 | 地板高度(m),診斷用 | 0(改用下兩項)|
| `--no_ground_collision` | off | 關預設地板碰撞(視覺保留) | 搬箱段開 |
| `--base_collider_pad` | 0.0 | 紙箱底板下方加厚不可見碰撞(m) | 搬箱段 0.02 |
| `--in_box_already` | off | `--init_npz` 已是箱內座標,跳過入箱平移 | 從 `*_box` 接搬箱 / 開箱時開 |
| `--move_open` | off | 搬完靜置後原地開四片蓋 | DEMO 用 |
| `--cam_ref` | 0.0 | 非紙箱段相機距離基準(m);0 = max(WX,WY) | 0.586(sheet 400 時)|

(`--crease_at` 只在 `archive_src/wrap_sim_crease.py`,沒併回。)

## 修正(非旗標)
- **蓋子 reset 前先開**:定版紙箱 USD 預設 = 關;舊版 `world.reset()` 時蓋子在關的姿態,第一格才甩開 → 壓扁包裹(`out_bl_boxmeta`)。現在 reset 前把蓋子 USD 姿態擺到 180°(開),再 drive 180°→0°。
- **`lid_pose` 的 sgn**:建 LIDS 時從 USD 量蓋子中心轉 ±90° 的 z,`L["sgn"]` 保證「正角度 = 往上開」;順便判 `rest_closed`。舊註解「0=平躺全開」訂正。
- **杯子入箱平移**:上一段杯子位置改用世界頂點的 **bbox 中心**(原用頂點平均,多搬 (−8.8,−5.5)mm,跟布錯開 ~10mm);布+杯子當一整包剛性搬;`--in_box_already` 時淨位移 0。
- **折序單一來源**:檔頭 `FOLD_ORDER = ["xp","xn","yp","yn"]`,`STAGE2_SIDES / WORDER / ORD_ / UORDER / ORDER / _ORD` 全部由它衍生,加 3 個 assert(`archive_src/foldorder.patch`、`FOLDORDER_NOTES.md`)。
- **杯子方位**:躺平後多轉 `Rz(−90)` 再套 `_Rm = [[-1,0,0],[0,1,0],[0,0,-1]]`(繞 y 轉 180°)⇒ 杯口 +y、杯耳 +x(只套 `_Rm` 會讓 selfcheck 過但杯口在 +x)。
- **SIDEPICK**:挑錨點時記下每個頂點屬於哪一邊,建 PULLS 時沿用(新幾何下角落頂點原本會被 `|x|>=|y|` 改判到錯的那一折)。
- **floor_edges 守衛**:`floor_edges.json` 的鍵 ≠ `STAGE2_SIDES` 就 `SystemExit`(舊折序 json 會讓 y 邊安靜地沒折到)。
- **放手用 RemovePrim**:放錨點時刪 attachment Scope + 方塊 prim(舊版搬方塊會掃飛布,`t_c1_bad`)。
- **搬箱出生懸空量測**:log 印杯子最低點與正下方布的高度差(找布被壓穿底板的原因)。
