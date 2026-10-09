---
id: L0037
title: 設計 surface deformable 前先對照官方限制清單,不支援的功能不要期待
status: active
severity: high
confidence: measured
domains: [surface, attach]
tags: [limitations, kinematicEnabled, attachment stiffness, surfaceStretchStiffness, surfaceShearStiffness, surfaceBendStiffness, staticFriction, dynamicFriction]
triggers: [設計布或膜的物理行為, 想凍結膜, 想讓兩片膜黏在一起, 調摩擦]
versions: Isaac Sim 5.1.0-rc.19 / PhysX 107.3.26
scope: [sims/wrapped_mug]
evidence: [sims/wrapped_mug/docs/FINDINGS.md §11, sims/wrapped_mug/wf_common.py ~96、~278, sims/wrapped_mug/params.py ~71]
related: [L0034, L0049, L0050]
observed: 2026-09
---

## 人話

**問題**:軟膜有一堆「看起來可以設、實際上沒作用」的參數。不知道的話會花很多時間調一個根本不生效的東西。

**做法**:設計之前先看這份清單,避開不支援的功能;例如兩片膜不能黏在一起,就把它們做成同一張。

## 現象 / 限制清單(本案有影響的)

| 想做的事 | 實際 | 對策 |
|---|---|---|
| 模擬中改 rest shape | 不支援 | 折痕離線烘焙,分兩趟(L0034) |
| `kinematicEnabled` 凍結膜 | 對 surface deformable 無效 | 用 attachment 釘住或不要凍結 |
| attachment 的 stiffness / damping | 無效,一律硬約束,沒有「弱黏」 | 要放手就刪 attachment(L0050) |
| 兩個 surface deformable 互相 attach / 碰撞過濾 | 不支援 | 左右兩片做成同一張膜 |
| `surfaceStretchStiffness` / `surfaceShearStiffness` | 完全不支援 | 只能靠 Young's modulus |
| 抗彎 | `surfaceBendStiffness` 是唯一控制,edge bend ∝ SBS · thickness³ | 改厚度會強烈改變彎曲 |
| `staticFriction` | 對 deformable solver 無效 | 只設 `dynamicFriction` |

## 根因

PhysX 107.3 beta surface deformable 的實作限制(官方限制清單 + 實測)。

## 做法

見上表。參數檔裡把無效參數標 `assumed` 並註明「無效」(`params.py`:`dyn_friction=0.75  # staticFriction 在 deformable solver 無效`)。

## 證據

`FINDINGS.md` §11;`wf_common.py` 註解。
