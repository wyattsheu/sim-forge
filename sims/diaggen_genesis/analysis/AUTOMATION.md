# 伺服器排程與自動監看

使用者要求剩餘工作由伺服器排程接續，不需持續開著 Codex 對話或 SSH。排程使用目前帳號的 **systemd user timer**，每分鐘觸發一次 `queue/run_monitor.sh`。此機器已啟用 `Linger=yes`；登出後 user manager 繼續運作，重新開機後 timer 也會啟動。實際生成仍使用既有 shell queue 與官方 DiagGen Codex skill，模型維持 GPT-6 Luna Max、Genesis 1.2.0。

## 自動執行範圍

- 每 60 秒檢查真實 queue、worker 與原生階段狀態。等待 GPU 的既有 watcher 每 15 秒檢查顯存。
- 如果 `diaggen-genesis-wait` 或 `diaggen-github-progress` tmux session 意外退出，補起對應服務；既有檔案鎖避免重複啟動。GitHub 網路失敗由 publisher 在下次循環重試。
- 已停止的 worker 若保有完整成功前綴、原始輸入及 GPU 綁定，且原生恢復檢查確認診斷已清理、未形成業務推薦，使用既有 `Queue.resume` 排入同一 run 接續。每個 run 最多自動嘗試 2 次，至少相隔 5 分鐘；記帳存於磁碟，登出不會重置次數。
- 原生已完成但外部 queue 誤判失敗時，使用現有的獨立 export validator 與 archive recovery。完整檔案、雜湊及狀態驗證通過才修正 queue；已匯出且仍為 revise 的結果保持 `exported_unaccepted`。
- worker 消失時先保存原 queue 記錄；不改寫原生 stage。殘留子程序仍存活或無法確認歸屬時，保留等待清理狀態。排除 kernel 標記的 zombie 與已識別的 SSH/PAM 登入程序後，未知且無法檢查的運算程序仍會阻止自動續跑。
- 45 分鐘沒有可觀察更新只會標記 `quiet`。它可能仍在推理，不據此殺程序、解鎖或重開。

真正的 stage failure、診斷 business halt、原生 revision budget exhausted、未完成清理、人工 HOLD、缺少啟動憑證及已用盡自動續跑次數，均保留原因。這些情況不能靠重置預算或更換方法忠實重現論文。

目前料理夾屬於原生修正預算已用完，水豚屬於 spconv int32 限制；排程會監看與發布這兩件的狀態，不會反覆從頭花 token 重跑。龍由既有 worker 自動走完剩餘原生階段；是否通過診斷仍取決於其實際結果。

## 狀態、安裝與暫停

在 repository 根目錄執行：

```bash
# 安裝／重新部署此帳號專用的兩個 units，不需要 sudo。
bash sims/diaggen_genesis/queue/install_monitor.sh

systemctl --user list-timers --all diaggen-genesis-monitor.timer
systemctl --user status diaggen-genesis-monitor.service
cat sims/diaggen_genesis/queue/monitor_status.json
tail -n 5 sims/diaggen_genesis/queue/monitor.log

# 暫停新排程 tick；現有生成工作仍可繼續。
systemctl --user disable --now diaggen-genesis-monitor.timer

# 重新啟用。
systemctl --user enable --now diaggen-genesis-monitor.timer
```

本機 `queue/monitor_status.json` 與 `queue/automation_state.json` 分別記錄最新觀察及恢復次數；原生狀態、完整工作與歷史依既有目錄保存。GitHub [progress](../progress/) 只發布允許的監看結果枚舉與既有產物預覽，不上傳完整執行紀錄或診斷憑證；心跳時間變化不會單獨製造 commit。

`queue/AUTOMATION_STOP` 可停用監看 tick 的服務恢復與自動續跑；移除此檔後，下次 timer 會恢復。既有 `queue/HOLD` 只暫停新工作；監看程式只移除它自己建立且內容未變的短期 recovery HOLD。若監看程序在持有 HOLD 時遭終止，會留下 gate 供人工查核，避免未知狀態繼續執行。`queue/STOP` 沿用原 queue 的取消等待工作語意。

原生 source、環境或輸入改變後，啟動憑證會失效；需完成對應驗證再恢復。服務重啟會恢復監看，並不代表任意中途斷電的 native stage 都符合官方續跑條件。

Codex 官方提供 [`codex exec` 非互動執行](https://learn.chatgpt.com/docs/non-interactive-mode)；既有 worker 已使用這個入口。本次只增加 server timer、確定性外部記帳與監看，沒有建立新的 Python pipeline agent，也沒有額外啟動持續推理的監看模型。


## 2026-10-22 19:58：首次正式自動續跑與修正

Dragon 在 19:10 的 bind 呼叫回傳錯誤後停止；原生 MCP 隨後記錄 `cleanup_retryable`、cleanup complete，尚未形成業務推薦。外部監看把原生 detached `runtime_profiler monitor`（只記錄資源與 profiling 報告）算成仍在運算的殘留工作，導致一直 waiting_cleanup。這是本機新增監看的判斷錯誤。

現在只排除 argv、run-root、原生 hag4r Python、cwd 以及 resource_monitor.lock 中 PID 全部相符的 profiler。沒有停止 profiler、清除診斷鎖或更改原生程式；未知程序與真正的子工作仍會阻止恢復。353 項 CPU／回歸測試全通過，含其他 module、額外參數、不同 PID／exe／cwd 的拒絕對照；95 項啟動憑證通過。

19:58:21 排程實際呼叫既有 Queue.resume，Dragon 已以原 run、原 GPU 和前六個成功階段重新啟動 Codex。這是正式續跑證據，尚不是完成或物理 accept；詳細見 [恢復驗證](dragon_scheduled_recovery_20261022.json)。
