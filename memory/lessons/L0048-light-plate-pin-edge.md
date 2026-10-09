---
id: L0048
title: 很輕的 volume 板要折時,另一邊先釘在固定桿上,否則整片被翻過去而不是折
status: active
severity: medium
confidence: measured
domains: [volume, attach]
tags: [volume plate, pin, kinematic bar, fold, light plate]
triggers: [用錨點拉一片很輕的薄板做折疊實驗]
versions: Isaac Sim 5.1.0
scope: [sims/fr3_bubblewrap_pack_20261007]
evidence: [sims/fr3_bubblewrap_pack_20261007/vol/probe_vol_stack.py ~148]
related: [L0039]
observed: 2026-10
---

## 人話

**問題**:很輕的板子(幾公克)拉一邊想把它折起來,結果整片被翻過去,根本沒折。

**做法**:拉之前先把另一邊固定住。

## 現象

4 g 的板被整片翻過去而不是折(pass1 第一版)。

## 根因

板太輕,拉力直接帶動整片剛體運動,沒有反力讓它彎。

## 做法

−x 邊釘在不動的 kinematic 桿上,再拉 +x 邊。

## 證據

`vol/probe_vol_stack.py`:「-x 邊釘在不動的 kinematic 桿上(否則 4g 的板會被整片翻過去而不是折,實測 pass1 第一版)」。
