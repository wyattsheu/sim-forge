# grip_attach — 閉合時綁定頂點的夾持模組(探針層級)

`attach_grip.py`:摩擦夾持 + 夾爪閉合完成那一步把足跡內頂點用 `OmniPhysicsVtxXformAttachment` 綁到上指,張開開始那一步 `RemovePrim`。

## 呼叫
```python
import attach_grip as AG            # SimulationApp 之後 import
fp  = AG.finger_pose(center, R, gap_m, half_xy=(0.010, 0.010))  # center = 兩指面中點(世界);R = 指框→世界,第 3 軸 = 夾持法線
vid = AG.select_vertices(Pw, fp, pad_mm=16, layer_mask=mask)    # Pw = 該 deformable 世界座標頂點;mask = 只屬最外層片的頂點(bool 或索引)
scp = AG.bind(stage, vid, "/World/finger_up", points=Pw, body_path="/World/plate", finger_pos=cu, finger_R=R, scope="/World/gatt_a")
...
AG.release(stage, scp)              # 或 AG.release(stage) 放開本模組建立的全部
```
- 足跡:指面矩形各邊外擴 `pad_mm`,且 |n| ≤ gap/2 + 2 mm(`BAND_TOL`)。
- local 位置在指 body frame(不含 scale);指剛體要是 `VC.kin_box` 那種 Xform(RigidBody)+ 子 Cube(scale)。
- 綁一次在閉合完成後(不要在合攏途中綁);釋放在張開動作的第一步。

## 推薦參數(給 wrap_vol 整包)
| 參數 | 值 | 理由 |
|---|---|---|
| pad_mm | 16 | ≥ 網格間距(5.7 mm)×2;24 只多 0.05 邊長比改善,足跡大易碰到相鄰折層 |
| 層 | both(該片上下兩面頂點都綁)| top-only 滑動 0.2~0.7 mm、邊長比 1.86~2.16(下層被拖,四面體拉長);both 滑動 ≤ 0.14、邊長比 1.67~1.81 |
| 間隙 | 4 mm(= 板厚)| 6 mm 也可,但兩次跑各一次出現 2~3 點自穿 |
| layer_mask | 只放最外層片(yn)| G2b:下片也進 mask → 下片被掀起 125 mm、互穿 22 |

## 閾值(探針判準)
滑動 < 1 mm、邊長比 < 2.0、互穿 0、釋放後 1 s 質心速度 < 0.1 m/s、疊層翻面 ≥ 90%(釋放後 ≥ 60%)。

## 已知限制
- 綁定 = 無限剛度,力不設上限:被重物壓住的布會被硬拉(G2a 有重物邊長比 2.43,超標),不會像真實夾爪那樣滑脫。需要時改 stiffness 有限值或監看邊長比自動釋放。
- layer_mask 的正確性完全靠上游分片(折序歸屬);錯一片就整片帶走(G2b)。
- 釋放本身乾淨(無黏住、無彈飛,水平速度 ≤ 0.22 m/s);G1 場景中釋放後布常從桌緣滑落地面,是拖拉 100 mm 的幾何,不是綁定造成。
- 同參數 run-to-run 有差(自穿 0↔3 點、落桌時刻),判定邊界附近的組要重跑確認。
- 只測 kinematic 方塊指、單一時刻綁定;夾爪中途再夾緊/換抓未測。

## 檔案
`probe_g1a.py`(G1a 單片掃描)、`probe_g2a.py`(G2a/G2b 疊層翻 180°)、`logs/`、`data/*.json`、`videos/`。

## 補充(實測)
- G2a(pad 16、gap 4):top 綁 38 點 / both 綁 84 點,無重物翻面 100% / 98%,釋放後 100%;下片位移 ≤ 3.5 mm。有重物 62~64%:被壓住那段翻不過去(純摩擦 G2 是 57%),邊長比 2.28~2.43 超標。
- 釋放後「指旁 2 mm 內 6~9 點」:布從桌緣垂下、貼著往下退的下指,質心已離開 45 mm,不是黏住。
- 啟動模擬前先查 nvidia-smi,已用 > 20000 MiB 就等(GPU 和其他 Kit 共用,同時開兩個錄影會 OOM)。
