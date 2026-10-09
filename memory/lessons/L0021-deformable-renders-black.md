---
id: L0021
title: deformable 渲成黑色時依序查:法線沒重算、render mesh 掛了 translate op、相機在背光面
status: active
severity: medium
confidence: observed
domains: [render, surface, volume]
tags: [black render, normals, subdivisionScheme, catmullClark, translate op, headlight, DistantLight]
triggers: [deformable 或軟體物件在影片裡是全黑, 新建一個 deformable 的視覺 mesh]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/vol/grip_common.py ~14-21、~68-70、~179-181、~193]
related: [L0020, L0022]
observed: 2026-10
---

## 人話

**問題**:軟物體在畫面上變成全黑,有三種常見原因,各自修法不同,而且都不會報錯。

**做法**:先確認相機前方有打光;再讓軟物體每一格重算表面方向;最後確認軟物體的位置是直接寫在頂點上,而不是用額外的位移設定。

## 現象

deformable(或 Volume FEM 軟體熊)在 render 裡全黑;有時連剛體紅球也黑。

## 根因(三種,依序排查)

1. **相機在看背光面**:連剛體都黑就是這個,不是 deformable 的問題。
2. **法線沒重算**:deformable 變形後不會重算法線。
3. **Volume FEM 的 render mesh 掛了 translate op** → 渲成黑(bear_a5 驗證過的配方是把位置烘進頂點)。

## 做法

1. 加一盞從相機方向打的 DistantLight(headlight):DistantLight 沿 local −Z 發光,把 −Z 轉到 (tgt − eye)。
2. 視覺 mesh 設 `subdivisionScheme = catmullClark`,每幀從更新後的點重算法線。
3. Volume FEM 物件:位置直接加進頂點座標,不加 translate op。

注意 `grip_common.py` 檔頭另寫「deformable 一律 cook 到原點、再用 translate op 擺位」—— 那是 surface 膜的配方;第 3 點只對 Volume FEM render mesh 驗證過。換配方時兩者都要實測。

## 證據

`vol/grip_common.py` 檔頭設計要點與 `headlight()`、`_author_mesh()`、`add_soft_bear()` 註解。
