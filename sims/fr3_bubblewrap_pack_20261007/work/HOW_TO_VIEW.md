# 怎麼檢視每一次模擬的產出

每跑一次 `wrap_sim.py --out 某目錄`，那個目錄裡會有四個檔。**先看 log 的數字，再看影片**——影片會騙人（布懸在杯子上方，俯視也是 100% 遮蔽）。

```
某目錄/
├── wrap.mp4        影片,30fps。底部黑條壓著這次的完整參數字串,要重現就照那行跑
├── wrap.npz        最終狀態:sheet(布 1225 頂點 xyz, m)、mug(杯子頂點)、top/dn/blk(判讀用)
├── traj.npz        每 0.5s 一格的布頂點 + 杯子姿態,給 chain_pen.py 做邊級別穿模
└── wrap_sim.log    完整判讀。跟終端印的一樣,可以離線讀
```

---

## 1. 影片 `wrap.mp4`

**看**:VS Code 檔案樹直接點開就能播。或拉回本機:
```bash
scp <帳號>@<主機>:/isaac-sim/test_scripts/manip_fr3/handoff_20260929/work/videos/baseline_full.mp4 .
```

**每個變體的完整流程影片**在 `work/videos/`(各段 c1→c2→c3 串起來):

| 檔名 | 內容 |
|---|---|
| `baseline_full.mp4` | 基準參數,四折 → 壓實 → 入箱關蓋 |
| `v1_offsets_full.mp4` | collider 偏移量 5/1mm → 2/0.2mm |
| `v2_tight_full.mp4` | 偏移量 + surfaceThickness 4mm + layer_mm 4 |
| `v3_solver_full.mp4` | 偏移量 + solver 128 + 碰撞迭代 ×2 |
| `v4a_anchor_full.mp4` | 錨點終點 hold 2mm + layer 3mm + 壓實不建錨 |
| `v4b_noanchor_press.mp4` | 基準四折 → 壓實段不建錨(單段對照) |
| `press_p0_base.mp4` … `press_p3_rest_bend1.mp4` | 單段壓實:無錨無 sleep 基準 / 只縮 rest / 只降 bend / 兩者 |
| `q_tipover_full.mp4` | **越線 40mm**(兩片真的疊起來)+ 基準物理 —— 第一個乾淨的改善 |
| `r_thin_robust_full.mp4`、`s_thin_softbend_full.mp4` | 薄膜 + rest 0.2 + hold 2(自穿模爆,反面教材) |
| `u_thin_only_full.mp4` | 越線 + 薄膜 4mm 單獨拆出(cont/rest 基準) |
| `t_release_full.mp4`、`t2_release_softbend_full.mp4` | **折到位就放手**(RemovePrim attachment)+ 越線,bend 4 / 1 |
| `movebox_*.mp4` | 搬箱子(目標 4) |
| `yield_over.mp4`、`yield_under.mp4` | 紙箱蓋降伏影片重剪(目標 6):過降伏 / 不過降伏對照 |

**抽幾格不開播放器看**(第 0 / 150 / 300 格並排):
```bash
ffmpeg -y -i 某目錄/wrap.mp4 -vf "select=eq(n\,0)+eq(n\,150)+eq(n\,300),scale=640:-1,tile=3x1" -frames:v 1 某目錄/contact.png
```

**影片底部那行參數**就是重現用的。格式:
```
init=flat | E=2e+04 bend=4e+00 solver=64 | thick=10 cont=5.0 rest=1.00 layer=8 hold=12 tip=0 anchor=on rel=no | fold=on
```
`tip` = `--tip_over_mm`(尖端越過中線),`hold` = `--hold_mm`,`anchor=none` = `--no_anchor`,`rel` = `--release_after`。

**入箱段一定要讀得到 meta**:`wrap_sim.py` 用 USD 檔名推 meta 檔名(`carton_w131.usd` → `carton_w131.meta.json`)。
`work/` 裡已放 symlink;若自己另建目錄,沒有 meta 時 log 會印「⚠ 找不到 … meta」,**蓋子不會動**、內腔上限用整箱 bbox 猜,但階段名照印,很容易誤以為關了蓋。

---

## 2. 數字 `wrap_sim.log`

用 `grep` 直接抓,不用整份讀:

```bash
L=某目錄/wrap_sim.log
grep -E '布 collider|錨點幾何'      $L   # 這次用的物理與錨點參數(開頭)
grep -E '施力點|第二段錨點'          $L   # 建了幾個錨點、釘在哪
grep -E '布 bbox' $L | tail -1            # 最終 bbox(尤其 z = 包裹高)
grep -E 'S1 自穿模'                 $L   # 布穿布幾次(基準前兩折 13)
grep -E '是不是同一張布'             $L   # 邊長比中位;偏離 1 = 布被拉長
grep -A3 '六面壓實判讀'             $L   # 壓之前 / 壓住時 / 放開後 bbox(c3 才有)
grep -A6 '真的入箱了嗎'             $L   # 逐頂點比對內腔(入箱段才有)
grep -A30 '自穿模時間序'            $L   # 穿模是哪一折爆的
```

放手流程的 log 多兩種行:`[t=4.80] yp 這一折拉到位,開始放掉錨點`(每邊一行)、`錨點幾何:… release_after 0.30s | no_hold True`。
放手後**下一行 bbox 的 z 應在 90~130、x 應仍 ~590**;若 z 幾百或幾千、x 縮到 550 以下,就是方塊掃到布(2026-09-30 修過一次)。

判準(對照 `CHECKLIST_2026-09-29.md`):
- 入箱:布超出內腔 **0** 個、杯子 0 個
- 布穿杯:邊級別 **0** 條(用 chain_pen,不是頂點)
- 邊長比中位 0.95~1.05
- 自穿模:越低越好,沒有硬門檻

---

## 3. 幾何 `wrap.npz`(純 CPU 工具,系統 `python3` 就能跑)

```bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/work

# 布疊在杯子上方幾層、層與層隔幾 mm、布頂離杯頂多遠 —— 「壓不小」的主指標
python3 layer_gap.py out_c1/wrap.npz v4a_c3/wrap.npz --shrink_mm 25
python3 layer_gap.py --selftest            # 合成兩張隔 3mm 的布,必須量出 3.000

# 四條邊各自跑到哪 —— 判折疊只能用這支,不要看整片 bbox
python3 edge_report.py out_c1/wrap.npz

# 用 numpy 直接看
python3 -c "
import numpy as np; d=np.load('out_c1/wrap.npz')
S=d['sheet']; M=d['mug']
print('布 bbox mm', ((S.max(0)-S.min(0))*1e3).round(0))
print('布 z 分位 mm', np.percentile(S[:,2],[50,95,99,100]).round(1)*1e3)
print('杯頂 z mm', M[:,2].max()*1e3)
"
```

`layer_gap.py` 輸出怎麼讀:
- **層數分佈**:杯頂上方每個取樣點疊了幾層。真的包起來四折應該大部分 ≥ 2 層;基準 c1 中位 1 層 = 兩片只是對接
- **層間距中位**:相鄰兩層隔幾 mm。貼合應 < 2mm;基準 5.5mm
- **疊層總厚**:布最高點 − 杯頂。這就是包裹比杯子高出的量;基準四折 43mm、壓實後 29mm
- `--shrink_mm 25` 只取杯頂平坦區,避開杯子弧面兩側把 p95 撐大

---

## 4. 穿模(要 Isaac 的 python,有 trimesh)

```bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/work

# 布穿過杯子:邊級別,把整條鏈的 traj.npz 接成一條時間軸
/isaac-sim/python.sh chain_pen.py mug.stl out_c1/traj.npz out_c2/traj.npz out_c3/traj.npz

# 放進箱子之前的座標驗證:布穿杯 / 布超內腔 / 杯超內腔(定版箱要加 --top 0.120)
/isaac-sim/python.sh check_place.py out_c3/wrap.npz --mug mug.stl --top 0.120
```

---

## 5. 一次看所有變體(比較表)

```bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/work
python3 layer_gap.py out_c2/wrap.npz v1_c2/wrap.npz v2_c2/wrap.npz v3_c2/wrap.npz v4a_c2/wrap.npz --shrink_mm 25 | tail -8
for d in out_c3 v1_c3 v2_c3 v3_c3 v4a_c3 v4b_c3; do
  [ -f $d/wrap_sim.log ] && printf "%-8s %s | %s\n" $d "$(grep '布 bbox' $d/wrap_sim.log | tail -1 | sed 's/.*布 bbox//')" "$(grep -o 'S1 自穿模.*次' $d/wrap_sim.log)"
done
```

---

## 6. 重現某一次

讀影片底部或 log 開頭的參數行,照著組旗標。三個漏掉就白跑:`--young 2e4 --bend 4`、`--tex bubble_normal.png`、`--unbox` 配 `--floor_edges floor_edges.json`。範例在 `../README.md` §3。
