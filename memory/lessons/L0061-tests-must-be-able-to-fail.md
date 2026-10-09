---
id: L0061
title: 驗收要能失敗:先用已知壞的案例證明檢查會 FAIL,並從產出物本身量,不要從輸入參數推
status: active
severity: high
confidence: measured
domains: [measure, workflow]
tags: [tautology, false pass, kinematic, selfcheck, golden test, negative control, validator]
triggers: [寫新的檢查或驗收腳本, 一個測試永遠是 PASS, 拿參數檔證明產出正確]
versions: Isaac Sim 5.1.0 / 6.0.1
scope: [sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007, tools/parcel-forge]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/sim/make_carton_P.py 檔頭與 --anchor help, sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/CHANGES_TO_VERIFY.md A1/A4、C1、C3, sims/fr3_bubblewrap_pack_20261007/work/FOLDORDER_NOTES.md §3, sims/fr3_bubblewrap_pack_20261007/work/tests/README.md golden, tools/parcel-forge/docs/DECISIONS.md D010]
related: [L0025, L0062, L0070]
observed: 2026-09-26
---

## 人話

**問題**:有些檢查永遠會通過,因為它檢查的東西根本不可能出錯。例如把箱子固定住之後再檢查「箱子有沒有被推動」,當然永遠沒動;或者只檢查自己寫進去的參數,而不是實際產生出來的檔案。

**做法**:每個檢查先拿一個已知是壞的例子跑,確定它真的會報錯;檢查要讀實際產出的檔案或模擬結果,不要讀輸入參數。

## 現象

- base 是 kinematic 時「箱體位移 0.00」恆真;用 FixedJoint 焊死更陰險(base 仍 dynamic,P0.2 假 PASS 但不可能被推動)。
- `selfcheck` 讀 meta 參數證明縫隙 = 1 mm,但那只證明「寫進去的值對」,不證明 USD 真的長那樣(權威量法是 `gap.py` 讀 USD 世界 bbox)。
- `selfcheck` 只驗旋轉矩陣代數:照字面套 `_Rm` 會全過,杯口卻在 +x(L0070)。
- `make_carton_B.py` 結尾 print 少一個參數會 TypeError,但 `Save()` 在前面,USD 已寫出,crash 一直沒被發現。

## 根因

檢查的對象跟可能出錯的地方不是同一個東西。

## 做法

- 每個新檢查附一個負向對照:`carton_sweep.py` 拿舊箱跑必須報出缺陷(360/361);`selfcheck` 這輪抓到 `STAGE2_SIDES` 寫死才算有效;parcel-forge 證明 NVIDIA validator 會 FAIL(D010)。
- golden 測試集同時有 good 與 bad(`tests/golden/golden.json` 的 `expect_fail`),改門檻前先跑 `test_golden.py`。
- 量產出物:USD 用世界 bbox、模擬結果用 npz 頂點、方位用網格本身。
- 刻意讓某項 FAIL(例如 `--anchor` 讓 S0 0.10 FAIL)比假 PASS 誠實。

## 證據

`make_carton_P.py` 檔頭與 `--anchor` 說明;CHANGES_TO_VERIFY 開頭的 ★ 與 C 段;tests/README golden 15/15。
