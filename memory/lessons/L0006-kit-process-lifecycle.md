---
id: L0006
title: 背景 Kit 程序要能自己停乾淨:等它真的退出、必要時 SIGKILL,而且只停自己開的
status: active
severity: medium
confidence: measured
domains: [env, workflow]
tags: [kill, SIGTERM, SIGKILL, pid, port, pgrep, --stop, --replace]
triggers: [寫啟動或停止背景 Kit 的腳本, port 被佔用無法啟動, 寫等待某程序結束的迴圈]
versions: Isaac Sim 5.1.0 / 6.0.1
scope: [sims/fr3_bubblewrap_pack_handoff_20261007, sims/fr3_bubblewrap_pack_20261007, tools/parcel-forge]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/CHANGELOG.md 2026-10-07 03:48 (679eb23), tools/parcel-forge/docs/DECISIONS.md D022, sims/fr3_bubblewrap_pack_20261007/work/PITFALLS.md #11]
related: [L0078]
observed: 2026-10-07
---

## 人話

**問題**:Isaac Sim 關得很慢,而且常常不理會「請關閉」的訊號。停止指令如果送完就回來,緊接著重開會被擋成「已經在跑」;更糟的是可能把別人的程式當成自己的去關。

**做法**:停止時等程式真的結束(最多等一段時間,還不關才強制關);啟動前看清楚佔用連接埠的是誰,是自己開的才關,別人的就停下來問。

## 現象

- `open_in_webrtc.sh --stop` 送出訊號就回來,Kit 還沒退出,立刻重開被拒絕「already running」。
- parcel-forge `pf view` 叫使用者執行另一個專案的 stop 腳本,但佔 port 的其實是 parcel-forge 自己背景開的 viewer,使用者連跑四次都沒用。
- `while pgrep -f wrap_sim; do sleep …; done` 永遠不結束。

## 根因

- Kit 常忽略 SIGTERM。
- 停止邏輯假設了佔用者是誰,沒去查。
- `pgrep -f` 比對整條命令列,連這個 shell 自己的命令列也含 `wrap_sim`。

## 做法

```bash
# 停:送 TERM → 最多等 30 s → 還在就 KILL
kill $PID; for i in $(seq 30); do kill -0 $PID 2>/dev/null || break; sleep 1; done; kill -9 $PID 2>/dev/null
# 找佔 port 的人
ss -lntp | grep 49100; cat /proc/<pid>/cmdline | tr '\0' ' '
# 等某程序:用 pid,或讓 pattern 不比對到自己
pgrep -f '[w]rap_sim.py'
```

- 是自己開的(pid 檔對得上)→ 停掉或提供 `--replace`;不是 → 拒絕並印出佔用者,讓使用者決定。
- 背景開的長駐程序要告訴使用者怎麼停。

## 證據

handoff CHANGELOG `679eb23`:「--stop returned before Kit had actually quit … Now waits up to 30 s, then force-kills」。parcel-forge D022。PITFALLS #11。
