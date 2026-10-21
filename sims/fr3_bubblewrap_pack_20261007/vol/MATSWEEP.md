# MATSWEEP:只調材料係數讓 yn 片掀出後「垂著不彈回」(2026-10-21,進行中)

使用者:「調一下係數讓它不要那麼彈」。只動 `--young`(E)和 `--areal`(面密度),不改結構、不烘焙。
物理:回彈力矩 ∝ 彎曲剛度 E·T³,讓片垂下的力矩 ∝ 重力 ∝ 面密度。E 降 4 倍 + 面密度升 3 倍 = 「重力 / 剛度」升 12 倍。

## 狀態(05:46 第一次推送)
- **還沒有結果**:9 組都在排隊。GPU 門檻 < 26000 MiB(使用者指定)下,同時另有 plastic agent 的模擬 + GUI kit,
  實際上一次只開得了 1 組(每組 fast 約 5.6 GB × 2 context);一組 fast(只掀 yn + 放手後 10 s)約 10~12 分鐘。
- 第一批兩組(E5e2_d0.3、E1e3_d0.2)在 t=47 撞到 wrap_vol.py 的 bug:`--extract 0 --jaw_collide 1` 時 `H3F` 未定義(NameError)。
  已修(1 行,`[matsweep]` 標記,備份 `wrap_vol.py.before_matsweep`;預設行為不變),兩組重排;crash log 在 `matsweep/crashed_H3F/`。
- E2e3_d0.1(對照,現值)跑到掀開段:綁 12 點,t=61.03 守衛(邊長比 3.375 > 2.6,連續 2 次)放手。

## 旗標
`matsweep/run.sh NAME --young E --areal D` = FINAL_PLAN §2 夾爪版(extract6/run.sh)+
`--hand2 off --hand2_keep 0 --hold_yp 0 --extract 0 --second 0 --quality fast --edamp 0.02 --guard_yn 2.6 --guard_n 2 --peel_t 8 --hand1_jaw 1 --jaw_collide 1 --arc2_over_cap 0 --arc2_over_mm 30 --release_watch 1 --grasp_tail_s 8.5`
(`--release_watch 1` 印放手後 0.5/2/10 s 的越線/壁外/質心;`--grasp_tail_s 8.5` = 放手後共停約 10.5 s,不需新旗標)。
判讀:`python3 matsweep/table.py matsweep/E*`(grep stdout.txt + wrap.npz 算垂下角)。

結果表、final 確認、建議係數待補。
