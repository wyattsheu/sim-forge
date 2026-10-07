#!/usr/bin/env python3
"""yield_run.py — 單一循環的降伏示範(TASK_INTERN 目標 6):
   靜置(起點 Z)→ 準靜態加壓到目標角 X → 保持 → 放開 → **固定秒數**靜置(不提早結束)→ 停在 Y

   yield_run.py --carton <usd> --out <dir> --name <name> --target_deg <X> [--tune v2] ...

  加壓/靜置機制全部沿用 carton_rig.Rig(stair2.py 的 cyc 同一套:ramp_to 準靜態 + 每物理步施摺線力矩)。
  跟 stair2.py 的差別只有時間軸:
    * 放開後的靜置不是「靜置判準成立就結束」(原本 ~1 秒 sim、~25 幀),而是固定 --settle_s 秒;
    * 放開後前 --fast_s 秒每 --cap_fast 個物理步擷一幀(回彈是 0.3~0.5 秒內的事,原本每 10 步擷不到);
    * 到達目標後固定保持 --hold_s 秒再放開,讓「壓到 X 度」在畫面上停得住。
  影格比例(30/10/60)在 compose_yield.py 重排,這裡只負責把每個階段都擷夠。
"""
import os, sys, json, math, argparse, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser()
ap.add_argument("--carton", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--name", default="yield")
ap.add_argument("--tune", default="v2")
ap.add_argument("--target_deg", type=float, required=True, help="加壓目標角(sopen,度,以校正後靜置為零)")
ap.add_argument("--rest_s", type=float, default=1.0, help="加壓前展示起點的靜置秒數(sim)")
ap.add_argument("--hold_s", type=float, default=1.0, help="到達目標後保持力矩的秒數(sim)")
ap.add_argument("--fast_s", type=float, default=0.5, help="放開後密集擷取的秒數(sim)")
ap.add_argument("--settle_s", type=float, default=6.0, help="放開後的總靜置秒數(sim),含 fast_s,不提早結束")
ap.add_argument("--cap_rest", type=int, default=8)
ap.add_argument("--cap_hold", type=int, default=4)
ap.add_argument("--cap_fast", type=int, default=1)
ap.add_argument("--cap_settle", type=int, default=4)
ap.add_argument("--el", type=float, default=26.0)
ap.add_argument("--az", type=float, default=-60.0)
ap.add_argument("--force_cap_N", type=float, default=30.0)
ap.add_argument("--maxs", type=int, default=250000, help="ramp_to 的步數上限(stair2 用 250000)")
a = ap.parse_args()
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
T_WALL0 = time.time()

from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import numpy as np
from isaacsim.core.api import World
from carton_rig import Rig, UPPER

P = lambda *x: print(*x, flush=True)
DT = 1.0 / 240.0
os.makedirs(a.out, exist_ok=True)

world = World(stage_units_in_meters=1.0, physics_dt=DT, rendering_dt=1 / 30.0)
rig = Rig(world, a.carton, tune=a.tune, force_cap_N=a.force_cap_N, log=P)
rig.look(a.el, a.az)
FLAPS = UPPER                       # 上層兩片一起(跟 stair2 的上層階梯相同)
KEY = "fyp" if "fyp" in rig.FLAPS else FLAPS[0]
COL = {f: 2 + rig.IDX[f] for f in rig.FLAPS}          # rows 裡 sopen 欄位的位置
TAUCOL = {f: 2 + 3 * len(rig.FLAPS) + rig.IDX[f] for f in rig.FLAPS}
SEG = {}                                              # 階段 -> (起步, 迄步)  半開區間

def so_at(step_idx, f=KEY):
    return float(rig.rows[step_idx][COL[f]])

def so_mean(s0, s1, f=KEY):
    return float(np.mean([rig.rows[i][COL[f]] for i in range(s0, s1)]))

def run_fixed(phase, seconds, cap_every):
    """固定秒數推進,每 cap_every 個物理步擷一幀;不看靜置判準、不提早結束"""
    rig.phase = phase
    n = int(round(seconds / DT)); s0 = len(rig.rows)
    for i in range(n):
        rig.step(1)
        if i % cap_every == 0: rig.grab()
    SEG[phase] = (s0, len(rig.rows))
    return s0, len(rig.rows)

P("=" * 76)
P("yield_run  target %.2f deg  tune %s  降伏角 %.2f deg  目標/降伏 = %.2f 倍"
  % (a.target_deg, a.tune, rig.YIELD_DEG, a.target_deg / rig.YIELD_DEG))
P("步1 靜置(靜置判準)")
s0 = len(rig.rows); rig.settle("S1 SETTLE  no force"); SEG["S1 SETTLE  no force"] = (s0, len(rig.rows))
P("  " + " ".join("%s tilt%+.2f" % (f, rig.tilt(f)) for f in rig.FLAPS))
P("步1b 方向校正(實測)")
s0 = len(rig.rows); rig.calibrate_dir(); SEG["calib"] = (s0, len(rig.rows))

P("步1c 起點展示 %.1f s" % a.rest_s)
r0, r1 = run_fixed("REST", a.rest_s, a.cap_rest)
Z = {f: so_mean(r1 - 60, r1, f) for f in FLAPS}      # 起點 = 加壓前最後 0.25 s 的平均
P("  起點 Z: " + " ".join("%s=%.3f" % (f, Z[f]) for f in FLAPS))

P("步2 準靜態加壓到 %.2f deg(ramp_to,tau_step 0.003,每 20 步擷一幀)" % a.target_deg)
p0 = len(rig.rows)
pk, tau_pk, capped, stalled = rig.ramp_to(FLAPS, a.target_deg, "PRESS to %.0f deg" % a.target_deg,
                                          "upper", maxs=a.maxs)
p1 = len(rig.rows); SEG["PRESS to %.0f deg" % a.target_deg] = (p0, p1)
P("  ramp_to 回傳 峰值 %.2f deg @ %.3f N*m  力上限 %s  靠住 %s  步數 %d(sim %.1f s)"
  % (pk, tau_pk, capped, stalled, p1 - p0, (p1 - p0) * DT))
if p1 - p0 >= a.maxs:
    P("  ⚠ ramp_to 用完 maxs=%d 步仍未到目標 —— 結果不能當「壓到目標」" % a.maxs)

P("步3 保持 %.1f s(力矩不變)" % a.hold_s)
h0, h1 = run_fixed("HOLD", a.hold_s, a.cap_hold)
X_release = {f: so_at(h1 - 1, f) for f in FLAPS}      # 放開那一刻的角度 = 「壓到 X」
X_max = {f: max(rig.rows[i][COL[f]] for i in range(p0, h1)) for f in FLAPS}
creep = {f: so_at(h1 - 1, f) - so_at(h0, f) for f in FLAPS}
tau_hold = {f: float(rig.PUSH[f]) for f in FLAPS}
P("  放開那一刻 X: " + " ".join("%s=%.3f" % (f, X_release[f]) for f in FLAPS)
  + " | 加壓+保持期間最大 " + " ".join("%s=%.3f" % (f, X_max[f]) for f in FLAPS)
  + " | 保持中爬行 " + " ".join("%s=%+.3f" % (f, creep[f]) for f in FLAPS))
P("  保持時的推力矩 " + " ".join("%s=%+.4f N*m" % (f, tau_hold[f]) for f in FLAPS))

P("步4 放開(推力矩歸零),前 %.2f s 每 %d 步擷一幀" % (a.fast_s, a.cap_fast))
for f in FLAPS: rig.PUSH[f] = 0.0
rel0, rel1 = run_fixed("RELEASE", a.fast_s, a.cap_fast)
P("  放開後 %.2f s 角度: " % a.fast_s + " ".join("%s=%.3f" % (f, so_at(rel1 - 1, f)) for f in FLAPS))

P("步5 靜置 %.1f s(固定,不提早結束),每 %d 步擷一幀" % (a.settle_s - a.fast_s, a.cap_settle))
st0, st1 = run_fixed("SETTLE", a.settle_s - a.fast_s, a.cap_settle)

# ---- 結果(全部從 rows 量,不用回傳值)
N3 = int(round(3.0 / DT)); N05 = int(round(0.5 / DT))
Y = {f: so_mean(st1 - N05, st1, f) for f in FLAPS}    # 停在 Y = 最後 0.5 s 平均
last3 = {f: (max(rig.rows[i][COL[f]] for i in range(st1 - N3, st1))
             - min(rig.rows[i][COL[f]] for i in range(st1 - N3, st1))) for f in FLAPS}
resid = {f: Y[f] - Z[f] for f in FLAPS}
quiet_now = rig.is_quiet(FLAPS)
# 模型的塑性留住預測(等速加壓的解析解;只當參考,不當結果)
T = rig.T; k, my0, h = T["k"], T["my0"], T["h"]
xr = math.radians(X_release[KEY])
pred = 0.0 if xr <= my0 / k else math.degrees((xr - my0 / k) / (1.0 + h / k))
mode = "over" if a.target_deg > rig.YIELD_DEG else "under"
crit = {"over": dict(resid_ge_10=(abs(resid[KEY]) >= 10.0), last3_lt_1=(last3[KEY] < 1.0)),
        "under": dict(resid_lt_2=(abs(resid[KEY]) < 2.0), last3_lt_1=(last3[KEY] < 1.0))}[mode]
P("=" * 76)
P("結果(%s,主角 %s)" % (mode, KEY))
P("  起點 Z = %.2f deg   壓到 X = %.2f deg(目標 %.2f)   停在 Y = %.2f deg   |Y-Z| = %.2f deg"
  % (Z[KEY], X_release[KEY], a.target_deg, Y[KEY], abs(resid[KEY])))
P("  最後 3 s 角度變化 %.3f deg   目前靜置判準 %s   模型預測留住 %.2f deg" % (last3[KEY], quiet_now, pred))
P("  另一片 %s: Z %.2f  X %.2f  Y %.2f  |Y-Z| %.2f  最後3s %.3f"
  % ([f for f in FLAPS if f != KEY][0], *[d[[f for f in FLAPS if f != KEY][0]] for d in (Z, X_release, Y)],
     abs(resid[[f for f in FLAPS if f != KEY][0]]), last3[[f for f in FLAPS if f != KEY][0]]))
P("  判準 %s -> %s" % (crit, "PASS" if all(crit.values()) else "FAIL"))

rig.save(a.out, a.name)
frames_by_phase = {}
for fm in rig.fmeta: frames_by_phase[fm["phase"]] = frames_by_phase.get(fm["phase"], 0) + 1
res = dict(mode=mode, key=KEY, flaps=FLAPS, tune=a.tune, tune_params=T, yield_deg=rig.YIELD_DEG,
           target_deg=a.target_deg, target_over_yield=a.target_deg / rig.YIELD_DEG,
           Z=Z, X_release=X_release, X_max=X_max, hold_creep=creep, tau_hold=tau_hold, tau_peak_ramp=tau_pk,
           ramp_capped=bool(capped), ramp_stalled=bool(stalled), ramp_steps=p1 - p0, ramp_hit_maxs=bool(p1 - p0 >= a.maxs),
           Y=Y, resid=resid, abs_resid_key=abs(resid[KEY]), last3_range=last3, quiet_at_end=bool(quiet_now),
           model_pred_resid_deg=pred, criteria=crit, PASS=bool(all(crit.values())),
           release_step=rel0, hold_step=h0, press_step=p0, rest_step=r0, end_step=st1,
           segments={k: dict(step0=v[0], step1=v[1], sim_s=(v[1] - v[0]) * DT) for k, v in SEG.items()},
           frames_by_phase=frames_by_phase, physics_dt=DT, args=vars(a),
           wall_s=time.time() - T_WALL0)
json.dump(res, open(os.path.join(a.out, a.name + "_result.json"), "w"), indent=1, ensure_ascii=False)
P("WROTE %s_result.json   wall %.0f s" % (a.name, res["wall_s"]))
sim.close()
