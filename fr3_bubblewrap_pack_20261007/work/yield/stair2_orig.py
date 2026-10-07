#!/usr/bin/env python3
"""stair2.py — S3 正式協議(使用者口述的過程),用 carton_rig 的共用機制。
   stair2.py <carton.usd> <outdir> [tune]

過程(影片就是這個過程在執行):
  步1 靜置,確認不動
  步2 上層兩片一起:施力不過降伏 → 等靜置 → 放力 → 等靜置 → 必須完全彈回
  步3 上層兩片一起:施力過降伏   → 等靜置 → 放力 → 等靜置 → 必須留住一部分
  步4 重複步3(力矩應遞增=硬化),直到開到 180 度
  步5 下層兩片一起:先往下 → 確認被擋住(停得下來)
  步6 下層兩片一起:往上,同樣的循環
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
from isaacsim.core.api import World
from carton_rig import Rig, UPPER, LOWER

CARTON, OUT = sys.argv[1], sys.argv[2]
TUNE = sys.argv[3] if len(sys.argv) > 3 else "v2"
P = lambda *a: print(*a, flush=True)

world = World(stage_units_in_meters=1.0, physics_dt=1/240.0, rendering_dt=1/30.0)
rig = Rig(world, CARTON, tune=TUNE, force_cap_N=30.0, log=P)
rig.look(26, -60)
R = {"tune": TUNE, "yield_deg": rig.YIELD_DEG, "force_cap_N": rig.FORCE_CAP, "cycles": []}

P("="*76); P("步1 靜置")
rig.settle("S1 SETTLE  no force")
P("  " + " ".join("%s tilt%+.2f" % (f, rig.tilt(f)) for f in rig.FLAPS))
P("步1b 方向校正(實測)")
rig.calibrate_dir()

# ★ 影片字幕必須是 ASCII(2026-07-31):容器沒有中文字型,中文會被整段吃掉,
#   之前影片標題變成「( 39+45 84 )」——只剩數字,看不出那一格在做什麼。
#   不要用「事後過濾」的方式處理,直接在源頭給兩個名字:終端機用中文,影片用 ASCII。
def cyc(flaps, tgt, label, layer, ph=None):
    ph = ph or "PHASE"
    base = {f: rig.sopen(f) for f in flaps}
    P("      進入 %s:目前 %s | 目標 %.1f 度"
      % (label, " ".join("%s=%.2f" % (f, base[f]) for f in flaps), tgt))
    # ★ maxs 必須夠大(2026-07-31):預設 40000 會讓「目標 131 只壓到 58」,
    #   而且 capped/stalled 都是 False —— 就是步數用完的特徵,不是物理擋住。
    pk, tau, capped, stalled = rig.ramp_to(flaps, tgt, ph + " PRESS", layer, maxs=250000)
    rig.settle(ph + " HOLD")
    peak = {f: rig.sopen(f) for f in flaps}
    hold = rig.release(flaps, ph + " RELEASE")
    L = rig.LA[layer]
    rs = {f: hold[f] - base[f] for f in flaps}
    P("    %-26s 壓到 %s @ %5.3f N*m (=%5.1f N%s) → 保持 %s  殘留 %s"
      % (label, "/".join("%.2f" % peak[f] for f in flaps), tau, tau/L,
         ",★力上限" if capped else (",靠住" if stalled else ""),
         "/".join("%.2f" % hold[f] for f in flaps),
         "/".join("%+.2f" % rs[f] for f in flaps)))
    return min(peak.values()), min(hold.values()), tau, min(rs.values()), capped, stalled

def staircase(flaps, name, layer):
    P("="*76); P("%s 階梯循環 —— 兩片一起(降伏角 %.2f 度)" % (name, rig.YIELD_DEG))
    # ★ 目標用「增量」不是絕對角:定版腳本的字幕就是答案 ——
    #   "each fold goes a bit further -> permanent crease keeps growing"
    #   累積塑性之後,絕對目標會小於現值 → 迴圈直接跳出、力矩 0.000(踩過兩次)
    rest0 = min(rig.sopen(f) for f in flaps)
    sub_inc = 0.6*rig.YIELD_DEG
    P("  當前靜止角 %.2f 度;所有目標都是「靜止角 + 增量」" % rest0)
    EN = "UPPER" if layer == "upper" else "LOWER"
    pk, hd, tq, rs, cp, st = cyc(flaps, rest0 + sub_inc,
                                 "%s 不過降伏(+%.1f度)" % (name, sub_inc), layer,
                                 ph="%s SUB-YIELD to %.0f deg" % (EN, rest0 + sub_inc))
    ok = abs(rs) < 0.5
    # ★ 判定文字保持中性:不要把推測印成結論(總則四,踩過三次)
    P("  步2 不過降伏 → 殘留 %+.2f 度(需 <0.5)-> %s" % (rs, "OK" if ok else
      "NG(原因待查:可能降伏點偏低,也可能壓入量超出不過降伏的範圍)"))
    R["cycles"].append(dict(layer=name, stage="sub", target=rest0+sub_inc, peak=pk, hold=hd,
                            tau=tq, force=tq/rig.LA[layer], resid=rs, ok=ok))
    prev = tq; hard = True; got180 = False; stalls = 0; prev_peak = pk
    # ★ 循環數不再寫死(2026-07-31 修):上一輪上層蓋七個增量用完就停在 128.6 度,
    #   七次全部 grew=Y held=Y、力矩只到 2.81(上限 5.01)—— 停止的原因是**我的清單跑完了**,
    #   不是箱子做不到。改成「跑到全開 / 力到上限 / 真的靠住」才停,上限 24 循環純粹防呆。
    # ★ 增量表(使用者 2026-07-31):第一個過降伏的循環直接跳到 120 度以上,不要一小格一小格爬。
    #   留住關係 壓到 = 保持x(1+H/k) + My0/k;v2 的 H/k=0.2656、My0/k=10.74 度 ->
    #   要「保持 120」得壓到 162.6;要「保持 180」得壓到 238.5(< 物理止點 ~270,所以做得到)。
    for ci in range(24):
        cur_rest = min(rig.sopen(f) for f in flaps)
        inc = (125.0 - cur_rest) if ci == 0 else 45.0
        # ★ 增量加在「上一次的峰值」而不是「保持角」(2026-07-31 修)。
        #   加在保持角會卡不動點:壓到 135 -> 放手回 90.4 -> 下一輪目標又是 90.4+45=135,
        #   同一行重複八次、塑性不再累積、力矩不再遞增(STAIR6 實際發生)。
        #   協議原文是「每一折都比上一折更深」= 以峰值為基準才單調前進。
        base = max(cur_rest, prev_peak)
        tgt = min(base + inc, rig.MAX_DEG)
        if tgt <= base + 1.0:
            P("  已到角度保護上限 %.0f 度(基準 %.1f 度)-> 停止階梯" % (rig.MAX_DEG, base)); break
        pk, hd, tq, rs, cp, st = cyc(flaps, tgt, "%s 過降伏(靜止%.0f+%.0f→%.0f度)"
                                     % (name, cur_rest, inc, tgt), layer,
                                     ph="%s CYCLE %d  PRESS to %.0f deg" % (EN, ci + 2, tgt))
        grew = tq > prev - 1e-6
        P("       力矩遞增 %s(%.3f→%.3f) | 留住 %s" %
          ("OK" if grew else "NG", prev, tq, "OK" if rs > 0.5 else "NG"))
        hard = hard and grew
        R["cycles"].append(dict(layer=name, stage="supra_%.0f" % tgt, target=tgt, peak=pk,
                                hold=hd, tau=tq, force=tq/rig.LA[layer], resid=rs,
                                tau_grew=grew, held=bool(rs > 0.5), force_capped=bool(cp)))
        prev = max(prev, tq); prev_peak = max(prev_peak, pk)
        for TH in (120.0, 180.0):                       # ★ 使用者要的答案:幾次能維持 > 門檻
            k = "%s_cycles_to_hold_%d" % (name, int(TH))
            if hd > TH and k not in R:
                R[k] = ci + 2                            # +2:第 1 個是不過降伏那格
                P("  ★ 第 %d 個循環達成「保持 > %.0f 度」(實際保持 %.2f,壓到 %.2f)"
                  % (ci + 2, TH, hd, pk))
        # ★ 終止看「保持角」不是「峰值」(2026-07-31 修)。舊版 pk>=175 就 break,
        #   但要保持 180 得壓到約 238 —— 迴圈在 185 自己停掉,結構上答不出這題。
        #   這和 tgt 上限 179 是同一個錯:我設了界限,又把系統停在界限上當成發現。
        if hd >= 180.0: P("  ★ 保持角已達 %.1f 度(放手仍全開)" % hd); got180 = True; break
        if cp: P("  ★ 力已到手臂上限,%.0f 度做不到 -> 停止階梯" % tgt); break
        # 靠住:連兩循環都靠住才停(單次可能是還在彈性段)
        if st:
            stalls += 1
            if stalls >= 2:
                P("  ★ 連續兩循環靠住於 %.1f 度 @ %.3f N*m(力上限 %.3f)-> 停止階梯"
                  % (pk, tq, rig.TAU_CAP[layer]))
                for f in flaps:
                    d, w, ov = rig.penetration(f)
                    P("     %s -> %s" % (f, ("與 %s 重疊 %.4f mm" % (w, d)) if w
                                         else "與四面箱壁皆無交集(擋住它的不是箱壁)"))
                break
        else: stalls = 0
    R[name+"_sub_ok"] = ok; R[name+"_hardening_ok"] = hard
    R[name+"_max_peak"] = pk; R[name+"_reached_180"] = got180

staircase(UPPER, "上層蓋", "upper")

P("="*76); P("步5 下層兩片一起往下 —— 確認被擋住(停得下來)")
a0 = {f: rig.sopen(f) for f in LOWER}
for f in LOWER: rig.PUSH[f] = rig.DOWN[f]*3.5
seq = []
rig.phase = "S5 LOWER FOLD DOWN  expect blocked"
for _ in range(30):
    rig.step(200, cap_every=25)
    seq.append(min(rig.sopen(f) for f in LOWER))
    if len(seq) > 3 and abs(seq[-1]-seq[-4]) < 0.2: break
pen_max = 0.0; pen_worst = None   # 插入深度 mm
for f in LOWER:
    v, w, ov = rig.penetration(f)
    if v > pen_max: pen_max, pen_worst = v, (f, w, ov)
adown = {f: rig.sopen(f) for f in LOWER}
hold = rig.release(LOWER, "S5 LOWER RELEASE")
stopped = len(seq) > 3 and abs(seq[-1]-seq[-4]) < 0.2
P("  往下到 %s 度(起始 %s);尾段 %s -> %s"
  % ("/".join("%.2f" % adown[f] for f in LOWER), "/".join("%.2f" % a0[f] for f in LOWER),
     [round(x,1) for x in seq[-4:]], "停住了 OK" if stopped else "還在動 NG"))
P("  放開後保持 %s 度" % "/".join("%.2f" % hold[f] for f in LOWER))
# ★ 穿牆檢查:停住 != 沒穿牆。蓋子可以停在 90 度、同時已經插進牆裡
P("  ★ 穿牆檢查:最大插入深度 %.4f mm %s"
  % (pen_max, ("(%s vs 牆 %s,三軸重疊 %.2f/%.1f/%.1f mm)"
               % (pen_worst[0], pen_worst[1], *pen_worst[2])) if pen_worst else "(無任何交集)"))
P("     判準:深度 < 接觸判定距離 1.0 mm -> 沒穿牆(已排除鉸接處的貼合)")
R["lower_down_deg"] = min(adown.values()); R["lower_down_stopped"] = bool(stopped)
R["lower_down_penetration_depth_mm"] = pen_max
R["lower_down_no_penetration"] = bool(pen_max < 1.0)

staircase(LOWER, "下層蓋", "lower")

rig.save(OUT, "stair")
json.dump(R, open(os.path.join(OUT, "stair_result.json"), "w"), indent=2, ensure_ascii=False)
P("="*76); P("總結 tune=%s 降伏角 %.2f 度" % (TUNE, rig.YIELD_DEG))
for k in sorted(R):
    if k != "cycles": P("  %-24s = %s" % (k, R[k]))
sim.close()
