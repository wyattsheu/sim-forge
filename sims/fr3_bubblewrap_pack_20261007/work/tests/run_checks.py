#!/usr/bin/env python3
"""run_checks.py — 對單一 run 目錄自動判讀(純 CPU,系統 python3 即可)。

    python3 tests/run_checks.py runs/11_final/fincam_box
    python3 tests/run_checks.py <run_dir> --stage box --json out.json
    python3 tests/run_checks.py <run_dir> --isaac      # 另用 /isaac-sim/python.sh 跑 chain_pen(很慢,數分鐘~數十分鐘)
    python3 tests/run_checks.py ../vol/soft/s2         # volume 版(目錄有 wrap_vol.log → 自動 --kind vol)
    python3 tests/run_checks.py <run_dir> --kind surface|vol|auto

每項輸出 PASS / WARN / FAIL / SKIP / INFO + 數值 + 門檻;最後一行總結。exit 0 = 沒有 FAIL,1 = 有 FAIL。
抽不到資料一律 SKIP 並寫原因(SKIP 不算 PASS)。門檻與來源見 tests/README.md。
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(TESTS)
sys.path.insert(0, WORK)
import collect_runs as CR  # noqa: E402

PACKED = ("c2", "c3", "box", "mb")

# ---------------------------------------------------------------- 可調門檻(來源見 tests/README.md「門檻來源」)
# 使用者 10-07:surface 版 S1 相對門檻 —— 同段基準 ×1.5 以上 WARN、×3 以上 FAIL。mb 沒給基準,沿用 box。
SELF_PEN_BASE = {"c1": 13, "c2": 257, "c3": 512, "box": 513, "mb": 513}
SELF_PEN_WARN_X, SELF_PEN_FAIL_X = 1.5, 3.0
# 使用者 10-07:volume 版 vol_pen 自互穿頂點數 —— 0 PASS / 1~20 WARN / >20 FAIL
VOL_PEN_FAIL = 20
# 使用者 10-02:箱壁/底板厚 3mm;超過內面但沒超過外面 = 陷進板子(WARN),超過外面 = FAIL
WALL_MM_DEFAULT = 3.0
# 使用者 10-07:邊長比最大只報數,> 2.0 才 WARN(夾爪/折角處網格粗,局部 1.6 可接受)
EDGE_MAX_WARN = 2.0
# 使用者 10-07:vol 俯視覆蓋 ≥ 90 PASS / < 90 WARN / < 70 FAIL;開蓋後布頂 z < 箱口(log 的值,預設 131)
COVER_PASS, COVER_FAIL = 90, 70
RIM_Z_DEFAULT = 131.0
# vol bbox_guard:任一軸 > 板子最大邊 × 1.2(布不可能比自己攤平時大)或 > 1000mm = 炸開
VOL_BBOX_X = 1.2


class Res:
    def __init__(self):
        self.items = []

    def add(self, key, status, name, value="", thr="", why=""):
        self.items.append(dict(key=key, status=status, name=name, value=str(value), thr=thr, why=why))


# ---------------------------------------------------------------- 讀 run
def load_run(d):
    logp = os.path.join(d, "wrap_sim.log")
    text = open(logp, errors="replace").read() if os.path.exists(logp) else None
    args = None
    if text is not None:
        rid = os.path.basename(os.path.normpath(d))
        parent = os.path.dirname(os.path.abspath(d))
        sdirs = [parent, os.path.abspath(d), WORK] + glob.glob(os.path.join(parent, "_stdout*"))
        _, args = CR.find_stdout(rid, os.path.getmtime(logp), CR.stdout_index(sdirs))
    return text, args


def resolve_run(rel_npz):
    """'fincam_c2/wrap.npz' → 實際的 run 目錄(work/ 根或 runs/*/)。"""
    if not rel_npz:
        return None
    rel_npz = rel_npz.replace("(log)", "")
    for base in (WORK, *glob.glob(os.path.join(WORK, "runs", "*"))):
        p = os.path.join(base, rel_npz)
        if os.path.exists(p):
            return os.path.dirname(p)
    return None


def mug_line(text):
    m = re.search(r"^杯子躺平 ([^\n]*)", text, re.M)
    return m.group(1).strip() if m else None


def mug_dims(text):
    m = re.search(r"^杯子躺平 (\d+) x (\d+) x (\d+) mm", text, re.M)
    return tuple(int(x) for x in m.groups()) if m else None


def fold_order_script():
    try:
        s = open(os.path.join(WORK, "wrap_sim.py"), encoding="utf-8").read()
        m = re.search(r'^FOLD_ORDER = \[([^\]]+)\]', s, re.M)
        return [x.strip().strip("'\"") for x in m.group(1).split(",")] if m else None
    except OSError:
        return None


# ---------------------------------------------------------------- 各項檢查
def check_validity(R, d, text, args, stage):
    if re.search(r"⚠ 找不到[^\n]*meta", text):
        R.add("meta_guard", "FAIL", "紙箱 meta 讀得到", "log 有「⚠ 找不到 … meta」", "不得出現",
              "蓋子不會動、內腔用整箱 bbox 猜,但階段名照印")
    elif stage in ("box", "mb", "unbox"):
        R.add("meta_guard", "PASS", "紙箱 meta 讀得到", "沒有「找不到 meta」", "不得出現")
    else:
        R.add("meta_guard", "SKIP", "紙箱 meta 讀得到", "", "", "非紙箱段(stage=%s)" % stage)

    bbs = [tuple(int(x) for x in m) for m in re.findall(r"布 bbox\s+(\d+) x\s+(\d+) x\s+(\d+)", text)]
    if bbs:
        mx = max(max(b) for b in bbs)
        R.add("bbox_guard", "FAIL" if mx > 1000 else "PASS", "全程布 bbox 任一軸 ≤ 1000mm(沒被彈飛)",
              "%d mm" % mx, "≤ 1000")
    else:
        R.add("bbox_guard", "SKIP", "全程布 bbox ≤ 1000mm", "", "", "log 沒有『布 bbox』行")

    init = (CR._flag(args, "--init_npz") if args else None)
    if not init:
        m = re.search(r"第二段:布以第一段的結果出生\(([^,)]+)", text)
        init = m.group(1) if m else None
    if not init:
        R.add("mug_orient", "SKIP", "杯子方位與起點 run 一致", "", "", "攤平起步(沒有 init_npz)")
    else:
        src = resolve_run(init)
        if not src or not os.path.exists(os.path.join(src, "wrap_sim.log")):
            R.add("mug_orient", "SKIP", "杯子方位與起點 run 一致", init, "", "找不到起點 run 的 log")
        else:
            a, b = mug_dims(text), mug_dims(open(os.path.join(src, "wrap_sim.log"), errors="replace").read())
            if not a or not b:
                R.add("mug_orient", "SKIP", "杯子方位與起點 run 一致", "", "", "log 沒有『杯子躺平』行")
            else:
                R.add("mug_orient", "PASS" if a == b else "FAIL", "杯子方位與起點 run 一致(杯子躺平 W×D×H)",
                      "本段 %s / 起點 %s(%s)" % ("×".join(map(str, a)), "×".join(map(str, b)), os.path.basename(src)),
                      "相同")


def add_edge_max(R, v, src=""):
    if v is None:
        R.add("edge_max", "SKIP", "邊長比最大(只報數)", "", "> %.1f WARN" % EDGE_MAX_WARN, "抽不到邊長比最大" + src)
        return
    R.add("edge_max", "WARN" if v > EDGE_MAX_WARN else "INFO", "邊長比最大(只報數;使用者 10-07)", "%.3f" % v,
          "> %.1f WARN,不 FAIL" % EDGE_MAX_WARN, "局部網格拉長(夾爪/折角)" if v > EDGE_MAX_WARN else "")


def check_edge(R, text):
    m = CR._last(r"是不是同一張布:.*?中位 ([\d.]+)(?:.*?最大 ([\d.]+))?", text)
    if not m:
        R.add("edge_ratio", "SKIP", "邊長比中位(同一張布)", "", "0.95~1.05", "log 沒有『是不是同一張布』行")
        add_edge_max(R, None, "(log 沒有『是不是同一張布』行)")
        return
    v = float(m.group(1))
    R.add("edge_ratio", "PASS" if 0.95 <= v <= 1.05 else "FAIL", "邊長比中位(同一張布)", "%.3f" % v, "0.95~1.05")
    add_edge_max(R, float(m.group(2)) if m.group(2) else None)


def _pen_files(d):
    rid = os.path.basename(os.path.normpath(d))
    parent = os.path.dirname(os.path.abspath(d))
    c = glob.glob(os.path.join(d, "chain_pen*.txt")) + glob.glob(os.path.join(parent, "pen_%s.txt" % rid)) \
        + glob.glob(os.path.join(parent, "%s_chain_pen.txt" % rid))
    return [p for p in c if os.path.getsize(p) > 0]


def check_mugpen(R, d, isaac):
    files = _pen_files(d)
    if not files and isaac:
        traj = os.path.join(d, "traj.npz")
        if os.path.exists(traj):
            out = os.path.join(d, "chain_pen.txt")
            with open(out, "w") as f:
                subprocess.call(["/isaac-sim/python.sh", "chain_pen.py", "mug.stl", os.path.abspath(traj)],
                                cwd=WORK, stdout=f, stderr=subprocess.STDOUT)
            files = _pen_files(d)
    if not files:
        R.add("mug_pen", "SKIP", "布穿杯(邊級別)= 0", "", "0 條",
              "沒有 chain_pen 輸出;需 /isaac-sim/python.sh(trimesh),加 --isaac 會自動跑")
        return
    txt = open(files[0], errors="replace").read()
    counts = [int(x) for x in re.findall(r"邊穿杯 \d+~(\d+)", txt)]
    m = re.search(r"C4 全程最深穿入 ([\d.]+) mm", txt)
    if not counts and not m:
        R.add("mug_pen", "SKIP", "布穿杯(邊級別)= 0", os.path.basename(files[0]), "0 條", "chain_pen 輸出不完整")
        return
    mx = max(counts) if counts else 0
    R.add("mug_pen", "PASS" if mx == 0 else "FAIL", "布穿杯(邊級別)= 0",
          "最多 %d 條、最深 %s mm(%s)" % (mx, m.group(1) if m else "?", os.path.basename(files[0])), "0 條")


def _box_block(text, which):
    """which='final' 取最後一個「(逐頂點比對內腔…)」區塊;'before' 取「搬之前」。"""
    pat = r"===== 真的入箱了嗎 —— 搬之前[^\n]*\n(.*?)(?:\n\n|\Z)" if which == "before" else \
        r"===== 真的入箱了嗎\(逐頂點比對內腔[^\n]*\n(.*?)(?:\n\n|\Z)"
    blk = None
    for m in re.finditer(pat, text, re.S):
        blk = m.group(1)
    return blk


def _parse_obj(blk, who):
    m = re.search(who + r"\s+\d+ 點;超出內腔\s+(\d+) 個.*?x 超 (\d+) / y 超 (\d+) / 低於底 (\d+) / 高於口 (\d+)\n"
                  r"\s+x\s+(-?[\d.]+)~\s*(-?[\d.]+) \(限 ±(\d+)\) \| y\s+(-?[\d.]+)~\s*(-?[\d.]+) \(限 ±(\d+)\) \| "
                  r"z\s+(-?[\d.]+)~\s*(-?[\d.]+) \(限 (-?[\d.]+)~(-?[\d.]+)\)", blk, re.S)
    if not m:
        return None
    g = m.groups()
    return dict(n=int(g[0]), x=int(g[1]), y=int(g[2]), lo=int(g[3]), hi=int(g[4]),
                xmin=float(g[5]), xmax=float(g[6]), xlim=float(g[7]), ymin=float(g[8]), ymax=float(g[9]),
                ylim=float(g[10]), zmin=float(g[11]), zlo=float(g[13]))


def wall_geom(text):
    """箱壁/底板厚(mm):surface log「整箱 bbox W x D x H」+「內腔 ±a x ±b」+「最低點 z=… → 箱底內面 z=…」;
    vol log「bbox WxDxH;箱底內面 z=…」。抽不到用 WALL_MM_DEFAULT。"""
    wx = wy = fl = WALL_MM_DEFAULT
    m = re.search(r"整箱 bbox (\d+) x (\d+) x \d+ mm;最低點 z=(-?[\d.]+) mm → 箱底內面 z=([\d.]+)", text)
    m2 = re.search(r"內腔 ±(\d+) x ±(\d+)", text)
    if m and m2:
        wx, wy = int(m.group(1)) / 2 - int(m2.group(1)), int(m.group(2)) / 2 - int(m2.group(2))
        fl = float(m.group(4)) - float(m.group(3))
    m = re.search(r"★ 紙箱 [^\n]*?bbox (\d+)x(\d+)x\d+;箱底內面 z=([\d.]+)[^\n]*?內腔 ±(\d+) x ±(\d+)", text)
    if m:
        wx, wy = int(m.group(1)) / 2 - int(m.group(4)), int(m.group(2)) / 2 - int(m.group(5))
        fl = float(m.group(3))            # vol:箱底外面對齊 z=0(log「箱底內面 z=3.0」)
    return wx, wy, fl


def grade_contain(o, walls=(WALL_MM_DEFAULT,) * 3, lid_closed=True):
    """使用者 10-02 口徑:超過內腔內面但沒超過外面(板厚)= 陷進板子 → WARN;超過外面、或高過關著的蓋 → FAIL。"""
    if o["n"] == 0:
        return "PASS", ""
    wx, wy, fl = walls
    F, W = [], []
    for ax, cnt, lo_, hi_, lim, wt in (("x", o["x"], o["xmin"], o["xmax"], o["xlim"], wx),
                                         ("y", o["y"], o["ymin"], o["ymax"], o["ylim"], wy)):
        if cnt:
            over = max(hi_ - lim, -lim - lo_, 0.0)
            (F if over > wt else W).append("%s %d 點%s %.1f mm(板厚 %g)" % (
                ax, cnt, "穿出外面" if over > wt else "陷進牆板", over, wt))
    if o["lo"]:
        depth = o.get("lo_depth", max(o["zlo"] - o["zmin"], 0.0))
        (F if depth > fl else W).append("底 %d 點%s %.1f mm(底板 %g)" % (o["lo"], "穿出箱底外面" if depth > fl else "陷進底板",
                                                                     depth, fl))
    if o["hi"] and lid_closed:
        F.append("高過關著的蓋 %d 點" % o["hi"])
    if F:
        return "FAIL", ";".join(F + W)
    if W:
        return "WARN", ";".join(W)
    return ("FAIL", "超出 %d 點但分項抽不到" % o["n"]) if lid_closed else ("PASS", "只有高於口(蓋開著不計)")


def check_box(R, text, stage):
    if stage not in ("box", "mb"):
        R.add("box_contain", "SKIP", "入箱:布/杯超出內腔", "", "", "非入箱段(stage=%s)" % stage)
        return
    blk = _box_block(text, "final")
    if not blk:
        R.add("box_contain", "SKIP", "入箱:布/杯超出內腔", "", "", "log 沒有『真的入箱了嗎』區塊")
        return
    walls = wall_geom(text)
    for who, key in (("布", "box_contain"), ("杯子", "box_contain_mug")):
        o = _parse_obj(blk, who)
        if not o:
            R.add(key, "SKIP", "入箱:%s超出內腔" % who, "", "", "區塊格式抽不到")
            continue
        st, why = grade_contain(o, walls)
        if who == "杯子" and o["n"] > 0:
            st, why = "FAIL", "杯子超出 = 掉出來;" + why
        R.add(key, st, "入箱:%s超出內腔" % who,
              "%d(x %d / y %d / 底 %d / 口 %d)" % (o["n"], o["x"], o["y"], o["lo"], o["hi"]),
              CONTAIN_THR, why)


CONTAIN_THR = "0 PASS;陷進板(≤板厚 3mm)WARN;穿出外面/高過關著的蓋 FAIL;杯子 >0 FAIL"


def check_lid(R, text, stage):
    if stage not in ("box", "mb"):
        R.add("lid_closed", "SKIP", "蓋子關上", "", "", "非入箱段")
        return
    hz = re.search(r"鉸鏈 下 ([\d.]+) / 上 ([\d.]+)", text)
    lids = [(float(t), dict((k, float(v)) for k, v in re.findall(r"(f[xy][pn])=(-?[\d.]+)", rest)))
            for t, rest in re.findall(r"\[lid\] t=\s*([\d.]+) 蓋中心 z ([^\n]*)", text)]
    if not hz or not lids:
        R.add("lid_closed", "SKIP", "蓋子關上", "", "|蓋中心 z − 鉸鏈 z| < 5mm", "log 沒有 [lid] 行(多半是缺 meta)")
        return
    phase = dict((float(t), p.strip()) for t, p in re.findall(r"\[pen\] t=\s*([\d.]+) ([a-z][a-z ]*[a-z])", text))
    dz = 0.0
    if stage == "mb":
        cand = [(t, l) for t, l in lids if phase.get(t, "") == "settled"]
        mv = re.search(r"箱子實際位移 \((-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\)", text)
        dz = float(mv.group(3)) if mv else 0.0
        if not cand:
            R.add("lid_closed", "SKIP", "蓋子關上(搬完、開蓋前)", "", "", "找不到 settled 階段的 [lid] 行")
            return
        t, L = cand[-1]
    else:
        t, L = lids[-1]
    lo, hi = float(hz.group(1)), float(hz.group(2))
    errs = {k: abs(v - dz - (lo if k.startswith("fx") else hi)) for k, v in L.items()}
    worst = max(errs.values())
    R.add("lid_closed", "PASS" if worst < 5.0 else "FAIL", "蓋子關上(t=%.1f%s)" % (t, ",已扣搬箱 z %.0f" % dz if dz else ""),
          "最大 |Δz| %.1f mm(%s)" % (worst, max(errs, key=errs.get)), "< 5 mm")


def check_move(R, text, stage):
    if stage != "mb":
        R.add("move_rel", "SKIP", "搬箱:包裹相對箱子位移", "", "", "非搬箱段")
        R.add("move_delta", "SKIP", "搬箱:搬後超出 − 搬前超出", "", "", "非搬箱段")
        return
    m = re.search(r"⇒ 結論:包裹\(布質心\)相對箱子位移 D=([\d.]+) mm.*?搬前超出 N0=(\d+).*?搬後 N1=(\d+)", text)
    if not m:
        R.add("move_rel", "SKIP", "搬箱:包裹相對箱子位移", "", "< 10 mm", "log 沒有搬箱結論行")
        R.add("move_delta", "SKIP", "搬箱:搬後超出 − 搬前超出", "", "≤ 2", "log 沒有搬箱結論行")
        return
    D, n0, n1 = float(m.group(1)), int(m.group(2)), int(m.group(3))
    R.add("move_rel", "PASS" if D < 10 else "FAIL", "搬箱:包裹(布質心)相對箱子位移", "%.1f mm" % D, "< 10 mm")
    R.add("move_delta", "PASS" if n1 - n0 <= 2 else "FAIL", "搬箱:搬後超出 − 搬前超出",
          "%d − %d = %d" % (n1, n0, n1 - n0), "≤ 2")


def check_fold(R, text, stage):
    seq = []
    for s in re.findall(r"wrap (xp|xn|yp|yn)", text):
        if s not in seq:
            seq.append(s)
    FO = fold_order_script()
    if stage not in ("c1", "c2") or not seq:
        R.add("fold_order", "SKIP", "折序 = 腳本 FOLD_ORDER", "", "", "非折疊段或 log 沒有 wrap 行")
        return
    if not FO:
        R.add("fold_order", "SKIP", "折序 = 腳本 FOLD_ORDER", "", "", "wrap_sim.py 抽不到 FOLD_ORDER")
        return
    exp = FO[:2] if stage == "c1" else FO[2:]
    R.add("fold_order", "PASS" if seq == exp else "FAIL", "折序 = 腳本 FOLD_ORDER(%s)" % stage,
          "log %s" % ",".join(seq), "%s" % ",".join(exp))


def check_wrap(R, d, text, stage):
    if stage == "unbox":
        R.add("W1", "SKIP", "包覆 W1 俯視遮蔽", "", "", "開箱段(布本來就攤開)")
        R.add("W3", "SKIP", "包覆 W3 圍蔽", "", "", "開箱段")
    else:
        for k, pat, nm in (("W1", r"^W1 俯視遮蔽\S*\s+(\d+)%", "包覆 W1 俯視遮蔽"),
                           ("W3", r"^W3 圍蔽 全部 (\d+)%", "包覆 W3 圍蔽")):
            m = CR._last(pat, text, re.M)
            if not m:
                R.add(k, "SKIP", nm, "", "≥ 95%", "log 沒有 %s 行" % k)
            else:
                v = int(m.group(1))
                R.add(k, "PASS" if v >= 95 else "FAIL", nm, "%d%%" % v, "≥ 95%")
    npz = os.path.join(d, "wrap.npz")
    if stage not in PACKED:
        R.add("layers", "SKIP", "杯頂上方層數中位", "", "≥ 2", "只評 c2/c3/box/mb(stage=%s)" % stage)
    elif not os.path.exists(npz):
        R.add("layers", "SKIP", "杯頂上方層數中位", "", "≥ 2", "缺 wrap.npz")
    else:
        L = CR.layer_stats(npz)
        if "層數中位" not in L:
            R.add("layers", "SKIP", "杯頂上方層數中位", "", "≥ 2", "非 35×35 網格或量不到")
        else:
            v = float(L["層數中位"])
            # 使用者 10-07:搬箱段(mb)搬完布會重新分布,層數不足只 WARN
            st = "PASS" if v >= 2 else ("WARN" if stage == "mb" else "FAIL")
            R.add("layers", st, "杯頂上方層數中位(layer_gap,shrink 25)",
                  "%.1f 層(層間距 %s mm、疊層 %s mm)" % (v, L.get("層間距中位", "-"), L.get("疊層總厚", "-")),
                  "≥ 2(mb 段 < 2 = WARN)", "搬箱後布重新分布(使用者 10-07)" if st == "WARN" else "")


def check_volume(R, d, stage):
    npz = os.path.join(d, "wrap.npz")
    if stage not in PACKED:
        R.add("volume", "SKIP", "體積比(布 bbox ÷ 杯 bbox)", "", "", "只評 c2/c3/box/mb")
        return
    try:
        import numpy as np
        z = np.load(npz)
        S, M = z["sheet"], z["mug"]
        vs, vm = np.prod(S.max(0) - S.min(0)), np.prod(M.max(0) - M.min(0))
        r = float(vs / vm)
    except Exception as e:
        R.add("volume", "SKIP", "體積比(布 bbox ÷ 杯 bbox)", "", "", "讀不到 wrap.npz:%s" % e)
        return
    st = "PASS" if r < 3.0 else ("WARN" if r < 4.0 else "FAIL")
    R.add("volume", st, "體積比(布 bbox ÷ 杯 bbox)", "%.2f" % r, "<3.0 PASS / <4.0 WARN")


def check_selfpen(R, text, stage):
    m = CR._last(r"S1 自穿模:布的邊穿過布的面 \*\*(\d+)\*\* 次", text)
    nm = "布自穿模 S1 ÷ 同段基準(使用者 10-07)"
    thr = "×%.1f WARN / ×%.0f FAIL" % (SELF_PEN_WARN_X, SELF_PEN_FAIL_X)
    if not m:
        R.add("self_pen_rel", "SKIP", nm, "", thr, "log 沒有 S1 行")
        return
    s1 = int(m.group(1))
    base = SELF_PEN_BASE.get(stage)
    if not base:
        R.add("self_pen_rel", "SKIP", nm, "S1 %d" % s1, thr, "段 %s 沒有基準(SELF_PEN_BASE)" % stage)
        return
    x = s1 / float(base)
    st = "FAIL" if x > SELF_PEN_FAIL_X else ("WARN" if x > SELF_PEN_WARN_X else "PASS")
    R.add("self_pen_rel", st, nm, "S1 %d ÷ %s 基準 %d = ×%.2f" % (s1, stage, base, x), thr)


# ---------------------------------------------------------------- volume 版(wrap_vol.log)
parse_vol_log = CR.parse_vol_log


def run_vol(d, stage=None):
    R = Res()
    logp = os.path.join(d, "wrap_vol.log")
    text = open(logp, errors="replace").read()
    v = parse_vol_log(text)
    stage = stage or CR.vol_stage(v)
    full = stage == "vol-all"
    miss = v["missing"]

    def skip(key, nm, k, thr=""):
        R.add(key, "SKIP", nm, "", thr, miss.get(k, "抽不到"))

    # --- 守門
    if v["meta_missing"]:
        R.add("meta_guard", "FAIL", "紙箱 meta 讀得到", "log 有「找不到 … meta」", "不得出現")
    elif v.get("carton"):
        R.add("meta_guard", "PASS", "紙箱 meta 讀得到", "meta %s" % v["carton"]["meta"], "不得出現")
    else:
        R.add("meta_guard", "SKIP", "紙箱 meta 讀得到", "", "", "log 沒有『★ 紙箱 …(meta …)』行")
    if "bbox_max" in v:
        pl = max(v["plate"][:2]) if v.get("plate") else None
        lim = min(1000.0, VOL_BBOX_X * pl) if pl else 1000.0
        t0 = v.get("bbox_t0")
        R.add("bbox_guard", "FAIL" if v["bbox_max"] > lim else "PASS", "全程布 bbox 任一軸 ≤ 板子 ×%.1f 且 ≤ 1000" % VOL_BBOX_X,
              "%d mm(%s)%s" % (v["bbox_max"], "x".join(map(str, v["bbox_max_bb"])),
                               ";t=%.2f %s" % (t0[0], "x".join(map(str, t0[1]))) if t0 else ""),
              "≤ %.0f(板 %s)" % (lim, "x".join(map(str, v["plate"][:2])) if v.get("plate") else "?"),
              "炸開" if v["bbox_max"] > lim else "")
    else:
        R.add("bbox_guard", "SKIP", "全程布 bbox", "", "", "log 沒有 bbox 行")
    init = (v.get("args") or {}).get("init_npz")
    if not init:
        R.add("mug_orient", "SKIP", "杯子方位與起點 run 一致", "", "",
              "攤平起步(args 沒有 init_npz;rest_npz=%s 是 rest shape 不是起點)" % ((v.get("args") or {}).get("rest_npz") or "-"))
    else:
        src = os.path.join(os.path.dirname(d), os.path.dirname(init))
        lp = [p for p in (os.path.join(src, "wrap_vol.log"), os.path.join(src, "wrap_sim.log")) if os.path.exists(p)]
        b = mug_dims(open(lp[0], errors="replace").read()) if lp else None
        if not b or not v.get("mug_dims"):
            R.add("mug_orient", "SKIP", "杯子方位與起點 run 一致", init, "", "找不到起點 run 的『杯子躺平』")
        else:
            R.add("mug_orient", "PASS" if tuple(b) == tuple(v["mug_dims"]) else "FAIL", "杯子方位與起點 run 一致",
                  "本段 %s / 起點 %s" % ("×".join(map(str, v["mug_dims"])), "×".join(map(str, b))), "相同")
    # --- 網格 / 互穿
    R.add("edge_ratio", "SKIP", "邊長比中位(同一張布)", "", "0.95~1.05", "vol log 只有邊長比 [min,max],沒有中位")
    if v.get("lr"):
        add_edge_max(R, v["lr"][1])
        R.items[-1]["value"] += "(min %.3f;%s)" % (v["lr"][0], v["src"]["lr"])
    else:
        add_edge_max(R, None, ":" + miss.get("lr", ""))
    for key, k, nm in (("mug_pen", "inmug_max", "布穿杯(全程最大)= 0"), ("inversion", "inv_max", "四面體反轉(全程最大)= 0")):
        if k in v:
            R.add(key, "PASS" if v[k] == 0 else "FAIL", nm, "%d(%s)" % (v[k], v["src"][k]), "0")
        else:
            skip(key, nm, k, "0")
    nm = "自互穿頂點數(vol_pen.self_pen_count,全程最大;使用者 10-07)"
    if "pen_max" in v:
        n = v["pen_max"]
        R.add("self_pen_vol", "PASS" if n == 0 else ("WARN" if n <= VOL_PEN_FAIL else "FAIL"), nm,
              "%d(%s)" % (n, v["src"]["pen_max"]), "0 PASS / 1~%d WARN / >%d FAIL" % (VOL_PEN_FAIL, VOL_PEN_FAIL))
    else:
        skip("self_pen_vol", nm, "pen_max")
    if v.get("volr"):
        R.add("vol_ratio", "INFO", "四面體總體積 ÷ rest(全程 min~max)", "%.4f~%.4f" % v["volr"], "只報數")
    # --- 各階段 bbox / 體積(只報數)
    bbs = ["%s %s" % (nm_, "x".join(map(str, v[k]))) for k, nm_ in (("fold4_bb", "四折後"), ("tuck_bb", "收耳後"),
                                                                    ("closed_bb", "關蓋後")) if v.get(k)]
    if bbs:
        R.add("bbox_stages", "INFO", "各階段布 bbox(mm)", ";".join(bbs), "只報數",
              "缺:" + ",".join(k for k in ("fold4_bb", "tuck_bb", "closed_bb") if k in miss) if any(
                  k in miss for k in ("fold4_bb", "tuck_bb", "closed_bb")) else "")
    if "vol_per_mug" in v:
        R.add("volume", "INFO", "關蓋後 布 bbox ÷ 杯 bbox", "%.2f(%s)" % (v["vol_per_mug"], v["src"]["vol_per_mug"]),
              "只報數(vol 包裹貼箱,surface 的 <3.0 不適用)")
    else:
        skip("volume", "關蓋後 布 bbox ÷ 杯 bbox", "vol_per_mug")
    # --- 入箱
    if not full:
        for key in ("box_contain", "box_contain_mug", "move_rel", "move_delta", "top_z", "cover"):
            R.add(key, "SKIP", key, "", "", "stage=%s(只跑到折完)" % stage)
    else:
        walls = wall_geom(text)
        C = v["contain"]
        for who, key in (("布", "box_contain"), ("杯子", "box_contain_mug")):
            parts, worst = [], "PASS"
            whys = []
            for ph, phn in (("closed", "關蓋"), ("bm", "搬前"), ("am", "搬後")):
                o = C.get(ph, {}).get(who)
                if not o:
                    parts.append("%s ?" % phn)
                    continue
                st, why = grade_contain(o, walls)
                if who == "杯子" and o["n"] > 0:
                    st, why = "FAIL", "杯子超出 = 掉出來;" + why
                parts.append("%s %d(%d/%d/%d/%d)" % (phn, o["n"], o["x"], o["y"], o["lo"], o["hi"]))
                if why:
                    whys.append("%s:%s" % (phn, why))
                worst = max(worst, st, key=["PASS", "WARN", "FAIL"].index)
            if all(p.endswith("?") for p in parts):
                R.add(key, "SKIP", "入箱:%s超出內腔(關蓋/搬前/搬後)" % who, "", CONTAIN_THR, "log 沒有『真的入箱了嗎』區塊")
            else:
                R.add(key, worst, "入箱:%s超出內腔(關蓋/搬前/搬後,x/y/底/口)" % who, ";".join(parts), CONTAIN_THR,
                      " | ".join(whys))
        e = C.get("end", {}).get("布")
        if e:
            st, why = grade_contain(e, walls, lid_closed=False)
            R.add("box_contain_end", "INFO", "開蓋後(結束)布超出(蓋開著,口不計;只報數)",
                  "%d(%d/%d/%d/%d)" % (e["n"], e["x"], e["y"], e["lo"], e["hi"]), "只報數", why)
        if "move_cloth" in v:
            R.add("move_rel", "PASS" if v["move_cloth"] < 10 else "FAIL", "搬箱:布質心相對箱子位移",
                  "%.1f mm(杯 %.1f;箱位移 %s)" % (v["move_cloth"], v["move_mug"], v.get("box_disp")), "< 10 mm")
        else:
            skip("move_rel", "搬箱:布質心相對箱子位移", "move_cloth", "< 10 mm")
        bm, am = C.get("bm", {}).get("布"), C.get("am", {}).get("布")
        if bm and am:
            R.add("move_delta", "PASS" if am["n"] - bm["n"] <= 2 else "FAIL", "搬箱:搬後超出 − 搬前超出",
                  "%d − %d = %d" % (am["n"], bm["n"], am["n"] - bm["n"]), "≤ 2")
        else:
            R.add("move_delta", "SKIP", "搬箱:搬後超出 − 搬前超出", "", "≤ 2", "入箱區塊沒有搬前/搬後")
        nm = "開蓋後布頂 z < 箱口(使用者 10-07)"
        if "top_z" in v:
            rim = v.get("rim_z", RIM_Z_DEFAULT)
            R.add("top_z", "PASS" if v["top_z"] < rim else "FAIL", nm,
                  "max %.1f%s mm(%s)" % (v["top_z"], " / 99%% %.1f" % v["top_z99"] if "top_z99" in v else "",
                                         v["src"]["top_z"]), "< %.1f" % rim,
                  "布彈出箱口" if v["top_z"] >= rim else "")
        else:
            skip("top_z", nm, "top_z")
        nm = "開蓋後杯頂俯視覆蓋(使用者 10-07)"
        if "cover" in v:
            c = v["cover"]
            R.add("cover", "PASS" if c >= COVER_PASS else ("WARN" if c >= COVER_FAIL else "FAIL"), nm,
                  "%d%%(%s)" % (c, v["src"]["cover"]), "≥ %d PASS / < %d WARN / < %d FAIL" % (COVER_PASS, COVER_PASS, COVER_FAIL))
        else:
            skip("cover", nm, "cover")
    R.add("lid_closed", "SKIP", "蓋子關上", "", "", "vol log 沒有關蓋中的蓋中心 z(只有開蓋後)")
    R.add("layers", "SKIP", "杯頂上方層數中位", "", "", "vol 不評層數(npz 沒有 35×35 的 sheet)")
    if "wall" in v:
        R.add("wall", "INFO", "wall time", "%.1f s" % v["wall"], "只報數")
    if miss:
        R.add("vol_missing", "INFO", "抽不到的 vol 欄位", ",".join(sorted(miss)), "", ";".join(sorted(set(miss.values()))))
    return R, stage


def detect_kind(d):
    return "vol" if os.path.exists(os.path.join(d, "wrap_vol.log")) else "surface"


# ---------------------------------------------------------------- main
def run(d, stage=None, isaac=False, kind="auto"):
    d = os.path.realpath(d)          # golden/ 裡是 symlink:用真實位置找 stdout / 起點 run
    if kind == "auto":
        kind = detect_kind(d)
    if kind == "vol":
        if not os.path.exists(os.path.join(d, "wrap_vol.log")):
            R = Res()
            R.add("log", "FAIL", "wrap_vol.log 存在", "缺檔", "")
            return R, stage
        return run_vol(d, stage)
    R = Res()
    text, args = load_run(d)
    if text is None:
        R.add("log", "FAIL", "wrap_sim.log 存在", "缺檔", "")
        return R, stage
    if not stage:
        stage = CR.seg_of(args, text).rstrip("*") or "其他"
    check_validity(R, d, text, args, stage)
    check_edge(R, text)
    check_mugpen(R, d, isaac)
    check_box(R, text, stage)
    check_lid(R, text, stage)
    check_move(R, text, stage)
    check_fold(R, text, stage)
    check_wrap(R, d, text, stage)
    check_volume(R, d, stage)
    check_selfpen(R, text, stage)
    return R, stage


def summary(R):
    c = {s: sum(i["status"] == s for i in R.items) for s in ("PASS", "WARN", "FAIL", "SKIP", "INFO")}
    overall = "FAIL" if c["FAIL"] else ("WARN" if c["WARN"] else "PASS")
    return overall, c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--stage", choices=["c1", "c2", "c3", "box", "mb", "unbox", "vol-all", "vol-fold"])
    ap.add_argument("--kind", choices=["surface", "vol", "auto"], default="auto",
                    help="auto:目錄裡有 wrap_vol.log 就是 vol")
    ap.add_argument("--json")
    ap.add_argument("--isaac", action="store_true", help="沒有 chain_pen 輸出時用 /isaac-sim/python.sh 跑(慢)")
    a = ap.parse_args()
    R, stage = run(a.run_dir, a.stage, a.isaac, a.kind)
    kind = a.kind if a.kind != "auto" else detect_kind(os.path.realpath(a.run_dir))
    print("run %s | kind %s | stage %s" % (a.run_dir, kind, stage))
    for i in R.items:
        print("  %-4s  %-14s %-44s %-40s 門檻 %s%s" % (i["status"], i["key"], i["name"], i["value"], i["thr"] or "-",
                                                    ("  ← " + i["why"]) if i["why"] else ""))
    overall, c = summary(R)
    if a.json:
        json.dump(dict(run=a.run_dir, kind=kind, stage=stage, overall=overall, counts=c, items=R.items),
                  open(a.json, "w"), ensure_ascii=False, indent=1)
    print("總結 %s:PASS %d / WARN %d / FAIL %d / SKIP %d / INFO %d" % (overall, c["PASS"], c["WARN"], c["FAIL"],
                                                                      c["SKIP"], c["INFO"]))
    sys.exit(1 if c["FAIL"] else 0)


if __name__ == "__main__":
    main()
