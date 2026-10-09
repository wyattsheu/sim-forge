---
id: L0067
title: 批次跑模擬時每段先刪舊輸出與舊 log,上游沒產出就中止,跑完歸檔再收集
status: active
severity: high
confidence: measured
domains: [pipeline]
tags: [rm -rf, stale output, chain3.sh, run_demo.sh, collect_runs.py, runs/ directory]
triggers: [寫批次或串接模擬的 shell 腳本, 結果好得不合理]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007, sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/docs/handoff_20260929/CHANGES_TO_VERIFY.md D1-D3, sims/fr3_bubblewrap_pack_20261007/work/tests/README.md 建議流程, sim-forge 分支 portable-isaac-launch sim/run_demo.sh]
related: [L0066, L0068]
observed: 2026-09-29
---

## 人話

**問題**:批次跑的時候,如果上一輪的檔案還留著,某一段失敗了,下一段會拿到舊檔案繼續跑,跑出看起來很漂亮但完全是假的數字。

**做法**:每一段開始前先清掉自己的輸出和紀錄檔;上一段沒產生結果就整批停下來;跑完把結果搬進固定的歸檔資料夾再做統計。

## 現象

- 讀到五天前的 `out_v3/wrap.npz`,跑出假的漂亮數字。
- 讀到上一輪的 `W2.log`,誤判而殺掉好好的 run。
- 上游失敗、下游用舊檔硬跑。

## 根因

輸出路徑固定、沒有清理,失敗不會中斷鏈。

## 做法

```bash
run(){ o=$1; shift; rm -rf $o; $P wrap_sim.py $C "$@" --out $o > $o.stdout 2>&1; [ -f $o/wrap.npz ] || { echo "FAIL $o (see $o.stdout)"; exit 1; }; }
```
跑完:`mv X X.stdout runs/NN_xxx/` → `python3 collect_runs.py` → `python3 tests/run_checks.py runs/NN_xxx/X`;有 FAIL 就停,不要把這個 run 當下一段的 `--init_npz`。

## 證據

CHANGES_TO_VERIFY D1~D3;tests/README「建議的自動化流程」。
