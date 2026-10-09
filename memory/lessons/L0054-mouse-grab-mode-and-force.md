---
id: L0054
title: 拖剛體用力量式抓取、pickingForce 約 70;抓遠離鉸鏈或支點的地方
status: active
severity: medium
confidence: measured
domains: [ui, rigid]
tags: [forceGrab, pickingForce, joint mode, force mode, lever arm, tip over, MOUSE_PICKING_FORCE]
triggers: [設定滑鼠拖曳參數, 拖曳只動一點點, 提起箱子會翻倒]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_handoff_20261007, sims/wrapped_mug, tools/parcel-forge]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/CHANGELOG.md 2026-10-07 下午, sims/fr3_bubblewrap_pack_handoff_20261007/README.md §3.3、§8.6 Bm、§10 #2b #2c, sims/fr3_bubblewrap_pack_handoff_20261007/sim/webrtc_boot.py ~35, sims/wrapped_mug/docs/FINDINGS.md §12, tools/parcel-forge/docs/DECISIONS.md D062、D067]
related: [L0053, L0055]
observed: 2026-10-07
---

## 人話

**問題**:滑鼠拖東西有兩種模式。預設模式不管力道設多大,拖 15 公分東西只動 1 公分多;力道太大,抓著一面箱壁往上提會把整個箱子翻過來。

**做法**:拖硬物體時用「力量式」並把力道設在 70 左右;盡量抓離轉軸遠的地方;提箱子時翹起來是正常物理,不是程式錯。

## 現象

| 設定 | 結果 |
|---|---|
| 關節式(`forceGrab=false`),任何 pickingForce | 拖 150 mm,0.35 kg 物體只動約 14 mm |
| 力量式 40 / 70 | 抓 +x 牆提起:翹約 25~26°,不翻,包裹留在箱內 |
| 力量式 100 | 桌上推 150 mm 誤差 5 mm 內;但抓牆提起 → 翻 126.7°,包裹灑出 |
| 力量式 ≥ 400 | 不穩,紙箱飛走 |

## 根因

- 關節式抓取的拖曳量與 pickingForce 無關。
- 抓一面牆往上提,箱子以另一側底邊為支點翹起(物理);力太大就翻。
- 力臂:抓蓋子一半高度需要兩倍力,四分之一高度要四倍(parcel-forge D062)。

## 做法

- 啟動腳本:`/physics/forceGrab=true`、`/physics/pickingForce=70`;`MOUSE_PICKING_FORCE` 環境變數可改。
- 力量式要搭配箱底阻尼(線性 / 角 2 / 2),不然會衝過頭。
- 抓蓋子外緣、不要抓鉸鏈附近。
- 例外:wrapped_mug 拉**軟膜**時,`/physics/forceGrab=false`(約束式)較穩、不受 pickingForce 縮放影響 —— 軟膜與剛體的最佳模式不同,要分開設。

## 證據

handoff CHANGELOG(150 mm → 14 mm;70 翹 26° 不翻;100 翻;400 不穩);README §8.6 Bm 表;FINDINGS §12。
