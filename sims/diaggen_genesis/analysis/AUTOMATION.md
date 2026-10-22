# 伺服器排程與自動監看

## 圖片入口：不必開啟 Codex 對話

在 `/mnt/HDD4/wyattsheu/ITRI/sim-forge` 執行一次：

```bash
./diaggen start
```

之後直接把 **PNG、JPG、JPEG** 圖片放到
`/mnt/HDD4/wyattsheu/ITRI/sim-forge/sims/diaggen_genesis/inbox/`。
可以透過 SCP、SFTP 或 VS Code Remote SSH 上傳。收件器每分鐘掃描一次；相同檔案連續兩次掃描穩定、且至少相隔 15 秒後才提交，通常約 1–2 分鐘。建議先上傳為 `.part`，完成後才改成圖片副檔名。收件器只掃描這個資料夾第一層，原圖保留；損毀圖片會留在狀態中，其他有效圖片仍可繼續。

也可以一行立即提交圖片或資料夾；提交會自動啟用背景服務，指令結束後即可登出：

```bash
./diaggen '/path/to/物件照片.png'
./diaggen submit '/path/to/圖片資料夾'
./diaggen submit '/path/to/圖片資料夾' --recursive
./diaggen status

# 只驗證，不提交、不啟動工作：
./diaggen submit '/path/to/圖片資料夾' --dry-run
```

圖片會先解碼、檢查格式及 SHA-256，再以原始 bytes 保存到私有的 `inputs/submissions/`；不調整解析度或重新壓縮。正式啟動前再次解碼及檢查雜湊，建立不覆寫的 native input。相同內容只使用既有任務，即使改檔名、反覆提交或已有失敗，都不會默默另開 run／重設原生修正預算。每次手動提交先驗完全部圖片，才加入佇列；上傳變動或任何無效輸入會拒絕該次提交。

收件後沿用：等待可用 GPU → 官方 cleanup／segmentation／OmniPart／材質／網格 → Genesis 診斷與官方修正 → 貼圖與匯出 → 獨立驗收及結果歸檔。執行中仍由一分鐘監看、五分鐘故障調查與既有 GitHub 發布接手。每個 run 的完整本機結果在 `sims/diaggen_genesis/runs/<run_id>/`。`status` 將 `exported_accepted`（已驗證 strict accept）、`exported_unaccepted`（原生 revise 匯出）及缺少有效驗收紀錄的 `exported_unverified` 分開顯示。

原九張 demo 計畫保留為環境預檢 fixture；新圖片採逐件輸入驗證，因此正常增加圖片不需要重跑整套 GPU 環境預檢。收件程式與入口本身仍在啟動憑證及 CPU source inventory 內；更改程式會令憑證失效。單張上限 64 MiB、只接受靜態圖片；目前 queue 與既有進度發布器共同限制為 100 筆任務（含歷史），達到限制會明確拒絕，不會漏排或刪除歷史。

`start` 保留人工 `HOLD`、`STOP`、`AUTOMATION_STOP`、`REPAIR_STOP`，不會把暫停當成故障清除。此伺服器已部署服務並啟用 linger；未部署的其他機器仍需先完成環境、權重、有效的 runtime 憑證及 user systemd 配置。

不必手動打開 Codex，但背景仍需要已登入的 Codex CLI、模型／imagegen 權限與網路，並沿用 GPT-6 Luna Max。登出 SSH 後繼續執行；若授權到期或碰到無法修復的原生限制，系統保留原因並停止該任務，不能保證任意圖片都通過物理診斷。

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
# 安裝／重新部署監看與故障診斷的四個 units，不需要 sudo。
bash sims/diaggen_genesis/queue/install_monitor.sh

systemctl --user list-timers --all diaggen-genesis-monitor.timer
systemctl --user list-timers --all diaggen-genesis-repair.timer
systemctl --user status diaggen-genesis-monitor.service
cat sims/diaggen_genesis/queue/monitor_status.json
tail -n 5 sims/diaggen_genesis/queue/monitor.log

# 暫停新排程 tick；現有生成工作仍可繼續。
systemctl --user disable --now diaggen-genesis-monitor.timer diaggen-genesis-repair.timer

# 重新啟用。
systemctl --user enable --now diaggen-genesis-monitor.timer diaggen-genesis-repair.timer
```

本機 `queue/monitor_status.json` 與 `queue/automation_state.json` 分別記錄最新觀察及恢復次數；原生狀態、完整工作與歷史依既有目錄保存。GitHub [progress](../progress/) 只發布允許的監看結果枚舉與既有產物預覽，不上傳完整執行紀錄或診斷憑證；心跳時間變化不會單獨製造 commit。

`queue/AUTOMATION_STOP` 可停用監看 tick 的服務恢復與自動續跑；移除此檔後，下次 timer 會恢復。既有 `queue/HOLD` 只暫停新工作；監看程式只移除它自己建立且內容未變的短期 recovery HOLD。若監看程序在持有 HOLD 時遭終止，會留下 gate 供人工查核，避免未知狀態繼續執行。`queue/STOP` 沿用原 queue 的取消等待工作語意。

原生 source、環境或輸入改變後，啟動憑證會失效；需完成對應驗證再恢復。服務重啟會恢復監看，並不代表任意中途斷電的 native stage 都符合官方續跑條件。

Codex 官方提供 [`codex exec` 非互動執行](https://learn.chatgpt.com/docs/non-interactive-mode)；既有 worker 已使用這個入口。本次只增加 server timer、確定性外部記帳與監看，沒有建立新的 Python pipeline agent，也沒有額外啟動持續推理的監看模型。


## 2026-10-22 19:58：首次正式自動續跑與修正

Dragon 在 19:10 的 bind 呼叫回傳錯誤後停止；原生 MCP 隨後記錄 `cleanup_retryable`、cleanup complete，尚未形成業務推薦。外部監看把原生 detached `runtime_profiler monitor`（只記錄資源與 profiling 報告）算成仍在運算的殘留工作，導致一直 waiting_cleanup。這是本機新增監看的判斷錯誤。

現在只排除 argv、run-root、原生 hag4r Python、cwd 以及 resource_monitor.lock 中 PID 全部相符的 profiler。沒有停止 profiler、清除診斷鎖或更改原生程式；未知程序與真正的子工作仍會阻止恢復。353 項 CPU／回歸測試全通過，含其他 module、額外參數、不同 PID／exe／cwd 的拒絕對照；95 項啟動憑證通過。

19:58:21 排程實際呼叫既有 Queue.resume，Dragon 已以原 run、原 GPU 和前六個成功階段重新啟動 Codex。這是正式續跑證據，尚不是完成或物理 accept；詳細見 [恢復驗證](dragon_scheduled_recovery_20261022.json)。

## 故障觸發的 Codex 診斷與修復

使用者進一步要求：排程執行時若突然停止，要判斷是流程還是排程出錯，修正後重新自動執行。因此增加 `diaggen-genesis-repair.timer`，每 **5 分鐘**檢查新事件；正常工作不呼叫模型。只有發現未解的 runtime／stage failure、新的 native halt、等待清理過久、監看資料失效或程序失聯等情況，才由 shell 啟動 **GPT-6 Luna Max 的 Codex exec** 查因。這個程序是外部故障調查，沒有替換官方 pipeline agent。

新的 native halt 需要先調查：它可能是正當的物理／語意停止，也可能是 child 遇到檔案或 runtime 錯誤後呼叫 halt。調查不會自動清除 halt；若確認是真正業務限制，保留結果，不再用相同事件反覆啟動模型。部署前已知的料理夾與水豚失敗存為 baseline；新的 run 或新的失敗狀態仍會進入調查。

調查會讀取既有紀錄與官方程式，重現問題、做最小相容修正、執行對應檢查及完整 CPU suite，再以實際 source／環境指紋更新並驗證啟動憑證。只能使用既有 guarded queue resume／reconcile 或符合官方規則的新 run；不能改寫診斷結果、降低品質、繞過審核或重置修正預算。自動審核如拒絕必要操作，會留下 `blocked_review` 與原因，不改權限繞過。

每個事件最多調查 **2 次**，間隔至少 **15 分鐘**；單次最長 **45 分鐘**。PID、檔案鎖與磁碟記帳防止重複調查。修復時建立它自己的 HOLD，結束後只有啟動憑證驗證通過，才能移除同一個 gate；途中退出會保留證據及 gate，下一輪依同一事件次數接手。人工 HOLD 不會被競爭或移除。

本機調查紀錄在 `queue/repair_jobs/<id>/`，包含 request、Codex JSONL、結果與完成記帳；`queue/repair_status.json` 的允許枚舉會進 GitHub 即時進度。原始紀錄、憑證、session 識別資訊不公開。修正由調查工作以專用 worktree、精確檔案清單推送，沒有共同作者註記。`queue/REPAIR_STOP` 可暫停新的模型調查；原有一分鐘監看與執行工作仍可繼續。

Dragon 在 20:07 暴露的新事件是 `material audit registration snapshot path already exists: cleaned_source_image`：重試的登錄資料已清空，但先前快照檔仍存在，child 寫入 native halt。它會列為新 halt 調查，不直接當作物理不通過，也不直接刪檔重試。先前 19:58 的成功續跑仍是啟動證據，不能稱為完整成功。


第一次正式診斷工作在模型啟動前被 CLI 拒絕：只設定 disabled 的 MCP entry 缺少 transport，屬於新增修復程序的部署設定錯誤。已補齊停用的完整 Python command/args，透過本機 Codex CLI 實際解析 worker 的原始設定參數；377 項測試、98 項啟動檢查通過。已失敗的啟動及其紀錄保留。只有在憑證通過、確認先前是此特定 transport 錯誤且沒有任何模型事件時，才可明確以 `run_repair.sh --retry-launch-fix` 立即使用下一次既有事件名額；不重設事件次數，也不能跳過已開始的模型或原生階段上限。


## 20:48：獨立覆核與實際重新派工

故障觸發的 Codex 已重現快照衝突，加入第九份相容性補丁：只有通過原生 attempt archive 驗證的重試，才使用該 attempt 的獨立材質稽核快照子目錄；第一輪路徑及既有快照保留。新的三例及完整 380 項回歸通過。原 run 頂層仍為 seeded，既有 snapshot queue guard 拒絕，因此保存舊 halt，改用已允許且保留歷史的新 raw-image run。

獨立覆核發現診斷工作把 CPU-only 報告當成啟動憑證，於派工前另加 HOLD 攔下。現在 readiness 必須收到完整 runtime schema，具備 host、mesh、Genesis、OmniPart 四組與三項 CPU collection 檢查，名稱唯一且統計相符；不能再用 orchestration report 單獨放行。補做四組 71 項實際環境／硬體檢查，383 項 CPU／回歸測試全通過，沒有失敗、錯誤或跳過。完整憑證共有 75 項 required checks：71 項 smoke、3 項 CPU collection 結果與 1 項拒絕 CPU-only 憑證的確認；檢查群組與內部測試案例是不同層級。

20:48:09，`genesis_dragon_20261022_retryfix_af4645266949` 的正式 worker 由排程啟動，新 Codex thread 已開始。這次從原圖重跑完整流程，原 run 和先前產物保留；尚未宣稱新資產完成。來源、啟動與覆核證據見 [獨立覆核](repair_supervision_review_20261022.json)。
