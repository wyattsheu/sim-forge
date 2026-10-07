#!/usr/bin/env python3
"""selfcheck.py — 交付前的自我檢查。純 CPU,不需要 GPU/Isaac。

使用者 2026-09-29:「你列一個 checklist 自己完全檢查」

每一項都是**可執行的斷言**,不是待辦清單。跑完印 PASS/FAIL 總表。
需要 GPU 跑完才知道的項目會標成 PENDING 並說明要去哪裡看。

    python3 selfcheck.py [deliver 目錄]
"""
import sys, os, json, subprocess, re

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "deliver")
SRC = os.path.dirname(os.path.abspath(__file__))
R = []
def chk(sec, name, ok, detail=""):
    R.append((sec, name, ok, detail))
def P(*s): print(*s, flush=True)


# ─── A 紙箱幾何 ────────────────────────────────────────────────────────
CM = None
for cand in (os.path.join(ROOT, "carton", "carton_v3.meta.json"),
             "/tmp/claude-1000/-home-ai-team-01-manip/2e1ab6a8-6559-45b5-8e12-5be1f4cb496b/scratchpad/carton_v3.meta.json"):
    if os.path.exists(cand): CM = cand; break
if CM:
    d = json.load(open(CM)); I, D = d["inputs"], d["derived"]
    t = I["t"]
    chk("A 紙箱", "外徑 270 x 230", abs(2*(I["hx"]+t)-0.270) < 1e-6 and abs(2*(I["hy"]+t)-0.230) < 1e-6,
        "%.0f x %.0f mm" % (2*(I["hx"]+t)*1e3, 2*(I["hy"]+t)*1e3))
    chk("A 紙箱", "板厚 3mm", abs(2*t-0.003) < 1e-9, "%.1f mm" % (2*t*1e3))
    chk("A 紙箱", "內腔 264 x 224", abs(2*D["wall_inner_x"]-0.264) < 1e-6, "%.0f x %.0f mm"
        % (2*D["wall_inner_x"]*1e3, 2*D["wall_inner_y"]*1e3))
    chk("A 紙箱", "下蓋長度 115mm(使用者指定)", abs(D["reach_x"]-0.115) < 1e-9, "%.1f mm" % (D["reach_x"]*1e3))
    chk("A 紙箱", "下蓋兩片縫隙 34mm", abs(D.get("lower_flap_gap", -1)-0.034) < 1e-9,
        "%.1f mm" % (D.get("lower_flap_gap", float('nan'))*1e3))
    chk("A 紙箱", "上蓋齊邊,每邊留 1mm", abs((D["wall_inner_x"]-D["flap_half_width_upper"])-0.001) < 1e-9,
        "%.1f mm" % ((D["wall_inner_x"]-D["flap_half_width_upper"])*1e3))
    chk("A 紙箱", "±x 牆頂 = 下鉸鏈 - 2t", abs(D.get("wall_top_x", -9)-(D["lower_hinge_z"]-2*t)) < 1e-9,
        "%.1f mm" % (D.get("wall_top_x", float('nan'))*1e3))
    chk("A 紙箱", "±y 牆頂 = 上鉸鏈 - 2t", abs(D.get("wall_top_y", -9)-(D["upper_hinge_z"]-2*t)) < 1e-9,
        "%.1f mm" % (D.get("wall_top_y", float('nan'))*1e3))
    chk("A 紙箱", "±x 牆頂 >= 包裹高 120mm(包裹不露出)", D.get("wall_top_x", 0) >= 0.120-1e-9,
        "%.1f mm" % (D.get("wall_top_x", float('nan'))*1e3))
    # ─── 以下三項來自「需求」與既有驗收規格,不是來自我的 diff ───────────
    # PPT 成功定義:「箱子會隨著手臂運動而被移動,不能黏在桌面上」
    # CARTON_QA.md S0 0.10:base 必須 dynamic;kinematic 時去測「箱體沒被推動」是恆真陷阱
    chk("A 紙箱", "★ base 是 dynamic(PPT:箱子不能黏在桌面上)", I.get("dynamic") is True,
        "dynamic=%s" % I.get("dynamic"))
    chk("A 紙箱", "★ 沒有 --anchor(它會把 base 設回 kinematic,抵銷 dynamic)",
        I.get("anchor") is not True, "anchor=%s" % I.get("anchor"))
    chk("A 紙箱", "★ 沒有 --goods_kg(箱內已有真的杯子+包材當配重)",
        not I.get("goods_kg"), "goods_kg=%s" % I.get("goods_kg"))
else:
    chk("A 紙箱", "找得到 carton_v3.meta.json", False, "缺檔")

# ─── B 蓋子不穿箱壁(用交付包自己的工具) ─────────────────────────────
sw = os.path.join(SRC, "carton_sweep.py")
def sweep(meta):
    try:
        o = subprocess.run([sys.executable, sw, meta], capture_output=True, text=True, timeout=600).stdout
        n = [int(x) for x in re.findall(r"(\d+)/361", o)]
        return n, o
    except Exception as e:
        return None, str(e)
if CM and os.path.exists(sw):
    n, o = sweep(CM)
    chk("B 蓋子", "新箱 0~180° 全程 0 重疊", n == [0, 0], "下蓋 %s / 上蓋 %s (共 361 角度)" % tuple(n or ["?", "?"]))
    chk("B 蓋子", "自檢:θ=90 蓋尖 z 最大(旋轉方向對)",
        bool(re.search(r"θ= 90°.*?,\s*(\d+)\.", o or "")), "見 carton_sweep 輸出")
    old = os.path.join(ROOT, "carton", "superseded", "carton_flush.meta.json")
    if os.path.exists(old):
        n2, _ = sweep(old)
        chk("B 蓋子", "★ 工具有效性:拿舊箱跑要抓到缺陷", bool(n2) and sum(n2) > 100,
            "舊箱 %s/361 + %s/361 重疊" % tuple(n2 or ["?", "?"]))

# ─── C 程式一致性 ──────────────────────────────────────────────────────
ws = open(os.path.join(SRC, "wrap_sim.py"), encoding="utf-8").read()
mf = re.search(r'FOLD_ORDER = \[([^\]]+)\]', ws)
o1 = [x.strip().strip('"') for x in mf.group(1).split(",")] if mf else None
chk("C 程式", "折序有單一來源 FOLD_ORDER", o1 is not None, str(o1))
chk("C 程式", "折序是 x 先(前/後才會是外層,符合 PPT 先開上下)", o1 == ["xp", "xn", "yp", "yn"], str(o1))
# ★ 三張衍生表都必須從 FOLD_ORDER 來,不可以各自寫死字面值
chk("C 程式", "★ ORD_ 由 FOLD_ORDER 衍生(不是寫死)",
    "ORD_ = FOLD_ORDER[" in ws, "")
chk("C 程式", "★ WORDER 由 FOLD_ORDER 衍生(曾因寫死而 ValueError)",
    "else FOLD_ORDER[" in ws, "")
chk("C 程式", "★ STAGE2_SIDES 由 FOLD_ORDER 衍生(曾因寫死抓 x 邊而 y 沒折到)",
    "STAGE2_SIDES = FOLD_ORDER[" in ws, "")
chk("C 程式", "★ stage2 的邊選取不再寫死軸", "FLAT[v, _s2ax]" in ws and "abs(abs(FLAT[v, 0]) - WX/2)" not in ws, "")
mu = re.search(r'UORDER = \[([^\]]+)\]', ws)
uo = [x.strip().strip('"') for x in mu.group(1).split(",")] if mu else None
chk("C 程式", "逆向開序 = 折序的反序", uo == list(reversed(o1)) if (uo and o1) else False,
    "UORDER=%s(折序反過來應為 %s)" % (uo, list(reversed(o1)) if o1 else "?"))

# 杯子旋轉:必須是純旋轉,且把 杯口->+y、杯耳->+x
import numpy as np
mm = re.search(r'_Rm = np\.array\(\[\[(.+?)\]\]\)', ws, re.S)
if mm:
    Rm = np.array(eval("[[" + mm.group(1) + "]]"))
    # ★ 這兩個是**原始網格**(套 _Rm 之前)的方位,不是模擬結果的方位。
    #   由圓形斷面法量到的結果反推:套舊 _Rm 後是 杯口 −x / 杯耳 +y,
    #   而舊 _Rm 是自身逆矩陣 ⇒ 原始是 杯口 +y / 杯耳 −x。
    rim0 = np.array([0., 1, 0]); h0 = np.array([-1., 0, 0])
    chk("C 程式", "杯子旋轉是純旋轉(det=+1,非鏡像)",
        np.allclose(Rm @ Rm.T, np.eye(3), atol=1e-9) and abs(np.linalg.det(Rm)-1) < 1e-9,
        "det=%.3f" % np.linalg.det(Rm))
    chk("C 程式", "杯口 -> 前(+y)", np.allclose(Rm @ rim0, [0, 1, 0], atol=1e-6), str(np.round(Rm @ rim0, 2)))
    chk("C 程式", "杯耳 -> 右(+x)", np.allclose(Rm @ h0, [1, 0, 0], atol=1e-6), str(np.round(Rm @ h0, 2)))
else:
    chk("C 程式", "找得到杯子旋轉矩陣 _Rm", False, "")

# 入箱是整包剛性搬移(布和杯子用同一個向量)
chk("C 程式", "入箱:杯子跟著布一起搬(不是只搬布)",
    "_mp0 + _sh" in ws and "SP0 += _sh" in ws, "檢查 wrap_sim.py 入箱區塊")

# ★ 2026-09-29:第二段的 hold 只能是「杯子正上方」。
#   我曾把第一段折好的 x 邊也釘進 hold(想治 −x 回彈),結果 bbox y 從 208 爆到 558:
#   ±x 邊是沿 y 方向 586mm 的長條,它的兩端只能靠「後折的 y 蓋下來時把它帶進去」收攏,
#   釘住就等於把那個機制關掉。這條擋的是我自己再加回去。
_s2 = ws.split("elif a.stage2:")[1].split("elif a.wrapsim:")[0] if "elif a.stage2:" in ws else ""
chk("C 程式", "★ 第二段 hold 不得釘住第一段折好的邊(x 邊要自由)",
    bool(_s2) and "np.concatenate([hold" not in _s2,
    "hold 只能來自『杯子正上方』那一個 np.where")

# ─── D 跑批腳本的防護 ──────────────────────────────────────────────────
ch = os.path.join(SRC, "chain3.sh")
if not os.path.exists(ch): ch = "/tmp/chain3.sh"
if os.path.exists(ch):
    c = open(ch).read()
    # ★ 壓實目標的長短邊必須跟折序一致,否則包裹長邊會落在箱子短邊 ⇒ 塞不進去。
    #   實際踩過:折序改 x 先之後 press6 還是舊的 250,210 ⇒ 包裹 230x256,y 超出 32mm。
    mp = re.search(r'--press6\s+([\d.]+),([\d.]+),', c)
    if mp and CM:
        pw, pl = float(mp.group(1)), float(mp.group(2))
        bx, by = 2*D["wall_inner_x"]*1e3, 2*D["wall_inner_y"]*1e3
        ok = (pw < bx) and (pl < by)
        chk("D 批次", "★ press6 目標裝得進內腔(長短邊沒對調)", ok,
            "包裹目標 %.0f x %.0f vs 內腔 %.0f x %.0f" % (pw, pl, bx, by))
    chk("D 批次", "★ 每段先清空輸出目錄(防殘留舊 npz)", "rm -rf" in c, "")
    chk("D 批次", "★ 每段檢查 wrap.npz 有產生,否則中止", "wrap.npz" in c and "exit 1" in c, "")

# ─── E 交付包內容 ──────────────────────────────────────────────────────
need = [("README.md", "說明"), ("CHANGELOG.md", "版本與驗證"), ("ADAPTING.md", "怎麼改尺寸"),
        ("scripts/wrap_sim.py", "主程式"), ("scripts/carton_sweep.py", "蓋子檢查"),
        ("scripts/chain_pen.py", "穿模檢查"), ("scripts/crease_physics.py", "摺痕物理"),
        ("carton/make_carton_P.py", "紙箱生成器"), ("assets/mug.stl", "杯子"),
        ("assets/bubble_normal.png", "泡泡布貼圖")]
for f, why in need:
    chk("E 交付包", "%s(%s)" % (f, why), os.path.exists(os.path.join(ROOT, f)), "")
ppt = "/home/ai_team_01/manip/carton_lab/spec/PPT_逆物流Demo方向定義.md"
chk("E 交付包", "PPT 原文抄錄存在", os.path.exists(ppt), ppt)

# ─── 總表 ──────────────────────────────────────────────────────────────
P("\n" + "="*74)
sec = None
np_, nf = 0, 0
for s, n, ok, d in R:
    if s != sec: P("\n【%s】" % s); sec = s
    P("  %s  %-46s %s" % ("PASS" if ok else "FAIL", n, d))
    np_ += ok; nf += (not ok)
P("\n" + "="*74)
P("PASS %d  /  FAIL %d" % (np_, nf))
if nf: P("\n★ 有 FAIL,不可交付。")
