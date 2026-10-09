---
id: L0078
title: 不要改共用的 Isaac 安裝、不要打擾使用者正在跑的 WebRTC、不要停別人的程序
status: active
severity: high
confidence: observed
domains: [workflow, env]
tags: [shared install, do not modify, live session, WebRTC, process ownership]
triggers: [想安裝或升級套件到 Isaac 環境, 想重啟 Kit 或佔用 port, 想啟用 Isaac 裡沒開的 extension]
versions: Isaac Sim 6.0.1(parcel-forge 機器)/ 5.1.0
scope: [tools/parcel-forge, sims]
evidence: [tools/parcel-forge/CLAUDE.md, tools/parcel-forge/AGENTS.md, tools/parcel-forge/docs/DECISIONS.md D003、D022、D057]
related: [L0006]
observed: 2026-09-16
---

## 人話

**問題**:實驗室的 Isaac Sim 是大家共用的,使用者也可能正在用遠端畫面操作。AI 為了自己方便去裝東西、重開程式、搶連接埠,會弄壞別人的環境或打斷正在進行的工作。

**做法**:不改共用安裝;需要額外套件就裝在專案自己的隔離環境;要啟用新功能或停掉程式,先問使用者。

## 現象

parcel-forge:機器上的 Isaac Sim 6.0.1 明文「must not be modified, reinstalled or upgraded」;「A user WebRTC session may be live; never disturb it」;自動核准啟用已安裝的 UI extension 被拒(D057),需使用者明確同意。

## 根因

共用資源;使用者的工作狀態 agent 看不到。

## 做法

- 隔離環境:專案的 `.venvs/`、`external/`(parcel-forge 的做法)。
- 開 port 前先查佔用者(L0006),不是自己的就拒絕並回報。
- 唯讀診斷可以做;任何改變共用環境的動作先問。

## 證據

parcel-forge CLAUDE.md、AGENTS.md;D003(livestream 預設關)、D022、D057。
