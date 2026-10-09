---
id: L0049
title: headless 下自動 attachment 會綁到 0 個頂點,要自己算頂點寫低階 vtx attachment
status: active
severity: high
confidence: measured
domains: [attach, surface, volume]
tags: [create_auto_deformable_attachment, AutoAttachmentAPI, OmniPhysicsVtxXformAttachment, vtxIndicesSrc0, PhysxPhysicsAttachment, headless]
triggers: [把 deformable 頂點釘到剛體或夾爪上, attachment 建好了但布沒被抓住]
versions: Isaac Sim 5.1.0-rc.19
scope: [sims/wrapped_mug, sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §3, sims/wrapped_mug/wf_common.py attach_verts_to_xform ~243-280, sims/fr3_bubblewrap_pack_20261007/vol/grip_common.py ~396-419, sims/fr3_bubblewrap_pack_handoff_20261007/sim/wrap_sim.py 檔頭]
related: [L0050, L0037]
observed: 2026-09
---

## 人話

**問題**:Isaac 有一個「自動把軟物體綁到硬物體上」的功能,在沒有畫面的模式下會回報成功,但其實一個點都沒綁到,布就這樣掉下去。

**做法**:自己算出要綁哪些頂點,直接寫綁定資料;寫完印出綁到幾個點,0 就停下來。

## 現象

- `create_auto_deformable_attachment()` 回傳 True、子 prim(`vtx_xform_attachment`)也建好,但 `vtxIndicesSrc0` 長度 **0**;pump `app.update()` 也沒用。
- 解析後綁到 0 個頂點(234/234 次);圓形軟體 auto-attachment 靜默留空(points0 = 0)。
- 舊的 `PhysxPhysicsAttachment` 對新 beta surface deformable 無效;手寫 vtx 掛在 mesh 底下不讀。

## 根因

填頂點的 attachment authoring 掛在 UI 側,headless 不會跑。

## 做法

自己算重疊頂點,寫低階 `OmniPhysicsVtxXformAttachment`(`wf_common.attach_verts_to_xform`、`grip_common` 手動 attachment):
- points0 = 頂點在 deformable 區域座標;points1 = 同頂點換到剛體區域座標(用剛體 world→local 矩陣)。
- **不要**再套 `AutoAttachmentAPI`(會覆寫)。
- 綁定建立時會回頭改膜的 offset,綁完要再設一次 offset。
- 印出 pinned 頂點數;0 = mask 沒中,直接停。

## 驗證方法

改完錨點頂點 0 → 2,被錨住的頂點位移 0.00000 m。測試若「NO_ANCHOR」就視為測試本身無效(`p0_crease_test.py`)。

## 證據

`FINDINGS.md` §3;`wf_common.py`「YM 坑 6:綁定建立時會回頭改膜的 offset」。
