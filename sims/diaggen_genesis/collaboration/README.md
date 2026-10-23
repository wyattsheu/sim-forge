# DiagGen 資產測試與 GitHub 協作指南

學妹可以 clone 後編輯程式，但 clone 本身不會下載伺服器上的模型產物、生成模型權重或 Conda 環境。本專案把已完成的七件資產另放在固定版本的 GitHub Release；clone 協作分支後，執行一次下載工具即可在自己的電腦取得外觀與物理檔案。只看模型、讀參數和寫 CPU 測試不需要 SAM3／OmniPart 權重，也不需要 Hugging Face 或模型 API 帳號。

建議先採 **學妹 fork → 自己的功能分支 → PR → Wyatt 審核合併**。目前是公開的個人 Repo；訪客能閱讀與 fork，沒有寫入權限便不能 push 到 Wyatt 的 Repo。GitHub 寫入權限、伺服器 SSH 權限、模型服務帳號是三件不同的事。

## 分支與下載包

| 名稱 | 用途 |
| --- | --- |
| `main` | 原本 sim-forge 主專案；預設 clone 會選這裡，目前不是 DiagGen 的入口 |
| `diaggen-genesis-progress` | 伺服器自動更新生成進度，勿拿來直接修改測試程式 |
| `diaggen-collaboration` | 本次建立的協作基底，從已核對的 DiagGen 程式與測試資產版本開始 |
| `feat/asset-tests` 等 | 學妹自己的工作分支；完成後 PR 回 `diaggen-collaboration` |

資產版本為 [`diaggen-test-assets-20261023-v1`](https://github.com/wyattsheu/sim-forge/releases/tag/diaggen-test-assets-20261023-v1)，ZIP 約 **18.3 MB**，解壓約 **29.0 MB**，含七件資產、112 個檔案。固定版清單與逐檔 SHA256 在 [assets_manifest.json](assets_manifest.json)。未來新增資產會使用新版本，不會默默替換這份實驗資料。

| 可取得的資產 | 資產 ID |
| --- | --- |
| 棒球帽 | `baseball_cap` |
| 料理夾 | `kitchen_tongs` |
| 球鞋 | `sneaker` |
| USB Hub | `usb_hub` |
| 樹懶玩偶 | `sloth` |
| 醬料盒 | `sauce_keeper` |
| 電捲棒 | `curling_iron` |

這七件在打包前重新通過既有的獨立 export validator，均有 strict Genesis accept。**龍與水豚尚未完成，不在這份包內。** Strict accept 表示通過既有診斷；材質仍由影像推論，並不代表已用實物量測校準。

## 學妹第一次取得程式

先在 GitHub 開啟 [協作分支](https://github.com/wyattsheu/sim-forge/tree/diaggen-collaboration)，按 **Fork** 建立自己的副本。下面 `YOUR_GITHUB_ACCOUNT` 要換成自己的帳號。即使 fork 只複製了預設分支，仍可從 upstream 取得協作分支：

```bash
git clone https://github.com/YOUR_GITHUB_ACCOUNT/sim-forge.git
cd sim-forge
git remote add upstream https://github.com/wyattsheu/sim-forge.git
git fetch upstream
git switch -c feat/asset-tests upstream/diaggen-collaboration
git remote -v
```

此時 `origin` 是學妹的 fork，`upstream` 是 Wyatt 的 Repo。這個安排不需要 Wyatt 邀請 collaborator，也不會讓學妹直接改到 Wyatt 的任何分支。

只想先拿資源、尚未 fork 的人，可執行：

```bash
git clone --branch diaggen-collaboration https://github.com/wyattsheu/sim-forge.git
cd sim-forge
```

這種 clone 也能編輯本機檔案，但沒有上游寫權限時，不能直接把修改 push 回去。開始交付工作時採前面的 fork 流程。

## 下載與核對七件資產

需要 Python 3.9 以上。以下指令從 Repo 根目錄執行；Windows 若只有 `py`，可將 `python` 換成 `py -3`。

```bash
python sims/diaggen_genesis/collaboration/asset_tools.py fetch
python sims/diaggen_genesis/collaboration/asset_tools.py verify
```

下載工具核對 ZIP 的固定 SHA256、成員清單及每個檔案的 SHA256，全部通過才發布到本機 `sims/diaggen_genesis/collaboration/assets/`。重跑會核對既有檔案，不覆寫自己的修改。資產和大型測試結果均被 `.gitignore` 排除；程式、測試與小型報告才提交 Git。

若網路不允許 Python 直接連 GitHub Release，可在 Release 頁手動下載 **`diaggen-accepted-assets-20261023-v1.zip`**，再執行：

```bash
python sims/diaggen_genesis/collaboration/asset_tools.py fetch --archive /path/to/diaggen-accepted-assets-20261023-v1.zip
```

Release 頁自動產生的 **Source code zip／tar.gz 是程式碼，不是模型資產包**。若 checksum 失敗，先重新取得正確版本，不要關閉核對。若要保留自己的改動，請複製資產到 `results/` 下再測試。

## 先看玩偶長什麼樣子

以樹懶為例，下載後可直接開：

```text
sims/diaggen_genesis/collaboration/assets/sloth/appearance/qa/rest_pose_render.png
```

要旋轉、放大與檢查背面，可在 Blender 選 **File → Import → glTF 2.0**，匯入：

```text
sims/diaggen_genesis/collaboration/assets/sloth/appearance/visual_mesh.glb
```

保留整個 `appearance/` 資料夾，避免遺失外部材質／貼圖。[Blender glTF 匯入文件](https://docs.blender.org/manual/en/4.0/addons/import_export/scene_gltf2.html) 說明此格式的讀取方式。外觀模型適合視覺檢查；它不是拿來直接做 FEM 的四面體網格。讓模型在 Blender 中受重力、加碰撞或套預設軟體材質，不會自動重現本專案的 Genesis 材質。

| 檔案 | 用途 |
| --- | --- |
| `appearance/visual_mesh.glb`、`appearance/albedo.png` | 外觀與貼圖 |
| `final_mesh.mesh` | Genesis 使用的四面體體積網格 |
| `heterogeneous_params.npz` | 逐四面體的材質標籤、密度、Young's modulus 與 Poisson ratio |
| `inferred_params.json` | 各零件的推論材質與語義 |
| `metric_mesh_scaling.json`、`volume_topology.json` | 尺寸與填充拓撲來源 |
| `appearance/visual_to_physics.npz`、`appearance/visual_manifest.json` | 外觀與物理網格的綁定資料 |
| `final_export_manifest.json`、`appearance/qa/` | 原始輸出來源與外觀品質資料 |

`final_mesh.mesh` 已套用公尺尺度，勿再乘一次歷史的 scale factor。原生 JSON 內可能有 `/mnt/HDD4/...` 等歷史來源路徑；在自己的程式使用下載包內的相對路徑。不要把這些來源記錄當成必須存在的本機依賴，也不要為了讀檔修改原始基準資料。

## 執行現成 CPU 檢查

`fetch`／`verify` 只用 Python 標準函式庫；`inspect` 另外需要 NumPy。可在獨立虛擬環境安裝：

```bash
python -m venv sims/diaggen_genesis/collaboration/.venv

# Linux 或 macOS
source sims/diaggen_genesis/collaboration/.venv/bin/activate

# Windows PowerShell 改用
# .\sims\diaggen_genesis\collaboration\.venv\Scripts\Activate.ps1

python -m pip install numpy
python sims/diaggen_genesis/collaboration/asset_tools.py inspect --asset sloth
python sims/diaggen_genesis/collaboration/asset_tools.py inspect
```

輸出包含網格大小、四面體數、材質標籤、推論參數及依密度計算的質量；會檢查材質陣列與四面體數是否一致、數值是否有限、GLB header 是否正確。這些是檔案／幾何一致性檢查，不會啟動 Genesis，也不能取代受力與回彈測試。

本次新增工具的回歸檢查：

```bash
python -m unittest discover -s sims/diaggen_genesis/collaboration -p 'test_*.py' -v
```

## 交給學妹的第一個任務

建議第一個 PR 先用 `sloth`，再加入 `sneaker`、`kitchen_tongs`。把新程式放在 `collaboration/experiments/`，讓輸入採 `--asset-dir`，輸出採 `--output-dir`，不要寫死 Wyatt 的伺服器路徑。

1. **外觀檢查**：讀取 GLB，提供轉動與放大方式，檢查貼圖、缺件和外觀對齊，保存幾個固定視角。
2. **幾何與參數檢查**：重用固定資產版本，比較尺寸、材質數、網格與參數陣列；測試故意缺檔或陣列長度錯誤時，工具會拒絕。
3. **Genesis 物理測試**：先完成無外力穩定測試，再設計壓入／釋放、固定一端輕拉、位移與回復量等測試。固定載入、邊界條件、步長、測試長度與量測定義，輸出數值及影片。

第三項需要可用的 **DiagGen 內附 Genesis 1.2.0 環境與對應的 TetMesh／FEM.Elastic／HeterogeneousMaterial 載入程式**。這個 Repo 沒有把 `tools/diaggen`、第三方 fork 或 Conda 環境包進 Git；下載資產也不會自動安裝模擬器。若在原伺服器測試，Wyatt 應先安排學妹自己的帳號、checkout、輸出目錄與 GPU 時段。現有環境可供確認版本與測試依賴，但不要在現有生成工作運行時安裝套件、執行 setup 或修改 native source。GitHub collaborator 邀請不等於 SSH 授權。

目前這份協作工具提供下載、核對與 CPU 檢查，**尚未提供一鍵互動物理測試程式**。這正是學妹可以接手實作的部分。查看既有實驗的影片可到 [progress](../progress/)；觀看影片不需要重新生成物件，也不需要生成模型權重。

可證偽的測試應記錄初始狀態、施力／位移條件、變形量與釋放後回復，而不是只寫「看起來正常」。結果若要證明符合實物，還需要實物尺寸、力與變形量等量測。報告可從 [report_template.md](report_template.md) 開始。

## 提交修改與開 PR

在自己的 `feat/asset-tests` 分支完成後：

```bash
git status
git add sims/diaggen_genesis/collaboration/experiments/my_test.py
git add sims/diaggen_genesis/collaboration/reports/sloth_test.md
git commit -m "Add reproducible sloth asset tests"
git push -u origin feat/asset-tests
```

把範例檔名換成實際存在的程式／報告。使用明確檔案清單，不要把下載包、虛擬環境、帳號憑證、完整 log 或大型影片加入 Git。影片可放專用 Release 資產或經同意的儲存位置，報告記錄連結與雜湊。

在 GitHub 按 **Compare & pull request**，指定：

```text
base repository: wyattsheu/sim-forge
base branch: diaggen-collaboration
head repository: 學妹自己的 fork
compare branch: feat/asset-tests
```

PR 說明包含測試目的、資產版本、執行指令、結果與限制。Wyatt 檢查 diff、測試數據與影片，提出修改或合併。後續修改直接 commit／push 到同一個功能分支，PR 會更新；不要 force push。

同步新一輪協作內容時，先 commit 目前工作，再執行：

```bash
git fetch upstream
git switch feat/asset-tests
git merge upstream/diaggen-collaboration
```

若有衝突，解決後重新測試、提交，再 push 到自己的 fork。GitHub 合併不會自動把程式部署到目前的生成伺服器；部署仍由 Wyatt 檢查版本與環境後安排。

## Wyatt 的權限設定

2026-10-23 查核時，`wyattsheu/sim-forge` 是 **public、個人帳號持有**，預設分支 `main`；既有 `main`／`diaggen-genesis-progress` 未啟用 branch protection，未設 ruleset。本次準備指南、協作分支與 CODEOWNERS，**沒有替你邀請帳號、變更可見度或啟用保護規則**。

### 先用 fork 模式

先不邀請學妹成為 collaborator。她能下載公開資源、在自己的 fork 開分支並提 PR；Wyatt 保留原 Repo 的寫入與合併控制權。這已符合「不能任意 push 到我的 Repo」的需求。[GitHub 個人 Repo 權限](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository) 說明 collaborator 具有寫入權限。

Public 代表任何人都能讀取與下載，並不表示任何人都能 push。若也要限制讀取，就需改 private 並重新安排資產下載驗證與保護方案；目前公開 Release 的匿名下載工具不適用 private。這次保留目前 public 設定。

### 要讓她在同一個 Repo 開分支時

先完成分支保護，再到 **Settings → Collaborators → Add people**，輸入她自己的 GitHub 帳號，她接受後就有此個人 Repo 的 collaborator 寫權限。不要分享你的帳號、PAT、SSH private key 或已登入的生成服務憑證。個人 Repo 不是 organization 的 Read／Triage／Write／Maintain／Admin 五級角色；需要更細的團隊角色時再考慮 organization。

有 collaborator 權限後，她可以 clone 你的協作分支，自己執行 `git switch -c feat/asset-tests`，再 `git push -u origin feat/asset-tests`；PR 仍回 `diaggen-collaboration`。寫權限不是「只能寫某一個分支」，所以保護重要分支很重要。

### 保護合併目標分支

在 **Settings → Branches → Add classic branch protection rule**，分別為 `main` 與 `diaggen-collaboration` 設定：

- **Require a pull request before merging**。
- **Require approvals：1**，並勾 **Require review from Code Owners**。
- **Dismiss stale pull request approvals when new commits are pushed**。
- **Require conversation resolution before merging**。
- 保持 **Allow force pushes** 與 **Allow deletions** 關閉。

本次 `.github/CODEOWNERS` 內容為 `* @wyattsheu`。協作分支已帶此檔；要保護 `main`，也需把 CODEOWNERS 合入 `main`，因為 PR 使用 **base branch 上**的 CODEOWNERS。只把它放在學妹的功能分支並不會讓主分支規則生效。檔案本身也不會禁止 push，仍需配合上述規則。[CODEOWNERS 說明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)

沒有 CI 狀態名稱前，不要先勾不存在的 required status check；否則 PR 會一直等不到檢查。將來有可重現的測試 workflow，再把實際工作名稱加入 required checks。[Branch protection 說明](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)

Classic 保護預設讓 owner／admin 可以 bypass。兩人協作且唯一 code owner 是 Wyatt 時，保留此設定可讓 Wyatt 管理自己的修改；學妹仍需取得 code-owner review。若要連 Wyatt 也不能 bypass，要先設計其他合格 reviewer，避免自己的 PR 無人可批准。

`diaggen-genesis-progress` 目前由伺服器直接 push。若也對它設 Require PR，必須確認現用 publisher 確實以 owner／admin 身分推送且保留必要 bypass；設好後執行一次現有 publisher 檢查，再觀察進度是否正常更新。不要一開始套用沒有例外的全分支規則，導致背景發布停止。

若日後轉 private，分支保護可用性會受 GitHub 方案影響；官方說明列出 public 免費可用、private 需對應付費方案。這次實際 Repo 為 public。

### 驗證合作權限

學妹可先確認 `git remote -v` 的 origin 是自己的 fork，再把一個小型測試分支 push 到自己的 fork、提 PR；她不需要嘗試 push 主分支。Wyatt 在分支頁／Settings 檢查保護狀態，並在 PR 上確認必須有 owner review 才能合併。不要用 force push、刪除正式分支或拿正式模型產物測權限。

## 可直接交給學妹的任務訊息

> 請從 `diaggen-collaboration` 建立自己的 fork／功能分支，照指南下載固定版本七件資產。先用樹懶建立外觀查看與 CPU 資料檢查，再設計 Genesis 的穩定、壓縮釋放與輕拉測試。新程式使用 `--asset-dir`／`--output-dir`，記錄資產版本、條件、數據與影片。不要更改生成管線或驗收門檻，完成後 PR 回 `diaggen-collaboration` 給我審核。需要伺服器／GPU 時再由我安排，既有權重不必重新下載。
