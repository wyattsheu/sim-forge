#!/usr/bin/env python3
"""collect_runs.py — 掃 work/ 底下所有含 wrap_sim.log 的目錄,每個 run 產一列 → RUNS.csv(純 CPU)。

    python3 collect_runs.py                       # 寫 RUNS.csv,印統計
    python3 collect_runs.py --out other.csv
    python3 collect_runs.py --no_layer            # 不跑 layer_gap(快)
    python3 collect_runs.py --extra_stdout_dir D  # 額外找 .stdout 的目錄(可重複)
    python3 collect_runs.py --include-vol         # 另收 ../vol/**/wrap_vol.log(volume 版,kind=vol)

每跑完一次模擬就重產一次。數字一律用 regex 從 log 抽,抽不到留空,不猜。
指令列從 stdout 的 "Passing the following args to the base kit application: [...]" 抽;
找 stdout 的地方:run 目錄的上一層、run 目錄自己、--extra_stdout_dir;
以 '--out' 值 == run_id(或去掉 _bad 尾碼)配對,多個候選取 mtime 最接近 log 的。
"""
import argparse
import ast
import csv
import datetime as dt
import glob
import os
import re
import shlex
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
SKIP_TOP = {"yield", "videos", "archive_src", "__pycache__", "tests"}

# ---------------------------------------------------------------- 批次規則(搬目錄也用這張表)
BATCH_RULES = [
    ("01_baseline", r"^out_(c1|c2|bl_.*)$"),
    ("02_offsets", r"^(v1|v2|v3|v3b)_"),
    ("03_anchor", r"^(v4a|v4b|v4c)_"),
    ("04_press_isolate", r"^p[0-3]_"),
    ("05_tipover_thin", r"^(q|r|s|u)_"),
    ("06_release", r"^(t|t2|t3|t5)_"),
    ("07_res", r"^w_res50_"),
    ("08_crease", r"^cr_(before|held)$"),
    ("09_sheet", r"^(sh450|sh400)_"),
    ("10_box_move", r"^(lidcheck|mb_.*|mb[2-6]_.*)$"),
    ("11_final", r"^(fin|finA|finB|fincam|dm)_"),
]


def batch_of(run_id):
    for b, pat in BATCH_RULES:
        if re.search(pat, run_id):
            return b
    return "99_misc"


# ---------------------------------------------------------------- 有效性(手動標)
_INTERP = "invalid:互穿,高度不可信(自穿模上百~上千)"
VALIDITY = {
    "t_c1_bad": "invalid:放手時方塊掃過布(bbox z 2343),09-30 改 RemovePrim 前的舊版",
    "t2_c1_bad": "invalid:放手時方塊掃過布(bbox z 2343),09-30 改 RemovePrim 前的舊版",
    "t_c2_bad": "invalid:起點是 t_c1_bad(方塊掃布)",
    "t2_c2_bad": "invalid:起點是 t2_c1_bad(方塊掃布)",
    "out_bl_box": "invalid:缺 carton meta,蓋子沒動(階段名照印)",
    "out_bl_boxmeta": "invalid:蓋子 USD 預設=關,t=0 就壓扁包裹",
    "sh400_mb_yz": "invalid:杯子方位與包裹不符(腳本已併折序 patch、包裹是舊折序)",
    "mb_x30": "invalid:診斷用,地板摩擦拖住布",
    "mb_yz": "invalid:診斷用,地板摩擦拖住布",
    "v4a_c3": "invalid:sleep 凍住(另有互穿)",
    "sh450_c3": "invalid:c3 沒帶 --sheet_mm,log 的邊長比基準錯(bbox/壓實數字可用)",
    "sh400_c3": "invalid:c3 沒帶 --sheet_mm,log 的邊長比基準錯(bbox/壓實數字可用)",
}
VALIDITY_PATTERNS = [
    (r"^mb[23]_", "invalid:診斷用,地板摩擦拖住布"),
    (r"^(v1|v2|v3|v3b|v4a|r|s)_", _INTERP),
]


def validity_of(run_id):
    if run_id in VALIDITY:
        return VALIDITY[run_id]
    for pat, v in VALIDITY_PATTERNS:
        if re.search(pat, run_id):
            return v
    return "valid"


NOTES = {
    "dm_c1": "腳本 wrap_sim_old.py(舊折序,run_demo_old.sh)",
    "dm_c2": "腳本 wrap_sim_old.py(舊折序)", "dm_c3": "腳本 wrap_sim_old.py(舊折序)",
    "dm_box": "腳本 wrap_sim_old.py(舊折序)", "dm_mb": "腳本 wrap_sim_old.py(舊折序)",
    "dm_mb_open": "腳本 wrap_sim_old.py(舊折序);DEMO_old_order_sheet400_v2 最後一段",
    "cr_before": "腳本 wrap_sim_crease.py(摺痕定型探針)", "cr_held": "腳本 wrap_sim_crease.py(摺痕定型探針)",
    "fincam_c1": "DEMO_new_order_sheet400 第 1 段", "fincam_c2": "DEMO_new_order_sheet400 第 2 段",
    "fincam_box": "DEMO_new_order_sheet400 第 3 段", "fincam_mb_open": "DEMO_new_order_sheet400 第 4 段",
    "v4b_c3": "log 帶有 sleep(未加 --no_sleepy)",
}

COLS = ["run_id", "路徑", "批次", "log_mtime", "指令列", "起點npz", "段", "sheet_mm", "thick", "cont", "rest",
        "layer", "hold", "tip", "anchor", "release", "bend", "bbox_x", "bbox_y", "bbox_z", "自穿模(S1)",
        "邊長比中位", "邊長比最大", "壓住z", "放開z", "入箱布超出", "入箱杯超出", "超出分項(x/y/底/口)",
        "杯心xyz", "搬箱相對位移", "搬前超出", "搬後超出", "W1", "W3", "層數中位", "層間距中位", "疊層總厚",
        "影片路徑", "有效性", "備註", "stdout來源",
        # ---- kind + volume 版專屬(值取自 wrap_vol.log 的 SUMMARY;沒有 SUMMARY 時用「判讀」段/入箱區塊,見 vol_來源)
        "kind", "vol_四折後bbox", "vol_收耳後bbox", "vol_關蓋後bbox", "vol_體積÷杯", "vol_開蓋後布頂z",
        "vol_開蓋後布頂z99", "vol_箱口z", "vol_覆蓋率", "vol_自互穿max", "vol_穿杯max", "vol_反轉max",
        "vol_邊長比min", "vol_體積比range", "vol_關蓋超出", "vol_搬前分項", "vol_搬後分項", "vol_杯搬箱位移",
        "vol_E", "vol_tuck", "vol_wall_s", "vol_來源"]
VOL_SKIP = {"__pycache__", "grip", "grasp", "logs", "img", "videos"}   # grasp/ 是別的 agent 正在寫的輸出


# ---------------------------------------------------------------- stdout / 指令列
_PASS = re.compile(r"Passing the following args to the base kit application:\s*(\[.*\])")


def _args_of(path):
    try:
        with open(path, "r", errors="replace") as f:
            for i, line in enumerate(f):
                m = _PASS.search(line)
                if m:
                    try:
                        return ast.literal_eval(m.group(1))
                    except Exception:
                        return None
                if i > 3000:
                    break
    except OSError:
        pass
    return None


def _flag(args, name):
    if not args:
        return None
    for i, t in enumerate(args):
        if t == name and i + 1 < len(args):
            return args[i + 1]
        if t.startswith(name + "="):
            return t.split("=", 1)[1]
    return None


_STDOUT_CACHE = {}


def stdout_index(dirs):
    """回傳 {--out 值: [(path, mtime, args)]}。"""
    idx = {}
    for d in dirs:
        for pat in ("*.stdout", "*.out", "*stdout*.log"):
            for p in glob.glob(os.path.join(d, pat)):
                p = os.path.abspath(p)
                if p not in _STDOUT_CACHE:
                    a = _args_of(p)
                    _STDOUT_CACHE[p] = a
                a = _STDOUT_CACHE[p]
                o = _flag(a, "--out")
                if o:
                    idx.setdefault(os.path.basename(o.rstrip("/")), []).append((p, os.path.getmtime(p), a))
    return idx


def find_stdout(run_id, log_mtime, idx):
    keys = [run_id]
    if run_id.endswith("_bad"):
        keys.append(run_id[:-4])
    cands = {}
    for k in keys:
        for p, mt, a in idx.get(k, []):
            b = os.path.basename(p)
            exact = b.startswith(run_id + ".") or b.startswith("run_" + run_id + ".")
            # 主鍵:與 log 的時間差(以分鐘計);同一分鐘內名稱完全對上的優先
            cands[p] = (round(abs(mt - log_mtime) / 60.0), 0 if exact else 1, p, a)
    if not cands:
        return None, None
    best = sorted(cands.values(), key=lambda c: c[:3])[0]
    return best[2], best[3]


# ---------------------------------------------------------------- log 解析
def _last(pat, text, flags=0):
    m = None
    for m in re.finditer(pat, text, flags):
        pass
    return m


def parse_log(text):
    r = {}
    m = re.search(r"實際採用 (\d+) x (\d+) mm", text)
    if m:
        r["sheet_mm"] = m.group(1)
    m = re.search(r"布 collider:contactOffset ([\d.]+)mm / restOffset ([\d.]+)mm \| surfaceThickness ([\d.]+)mm \| layer_mm ([\d.]+)", text)
    if m:
        r["cont"], r["rest"], r["thick"], r["layer"] = m.groups()
    else:
        m = re.search(r"每折 \+(\d+) mm\(布碰撞厚度 (\d+)mm\)", text)
        if m:
            r["layer"], r["thick"] = m.group(1), m.group(2)
    m = re.search(r"錨點幾何:hold_mm ([\d.]+) \| tip_over_mm ([\d.]+) \| no_anchor (True|False)(?: \| release_after (\S+))?", text)
    if m:
        r["hold"], r["tip"] = m.group(1), m.group(2)
        r["anchor"] = "none" if m.group(3) == "True" else "on"
        if m.group(4):
            r["release"] = m.group(4)
    m = _last(r"布 bbox\s+(\d+) x\s+(\d+) x\s+(\d+)", text)
    if m:
        r["bbox_x"], r["bbox_y"], r["bbox_z"] = m.groups()
    m = _last(r"S1 自穿模:布的邊穿過布的面 \*\*(\d+)\*\* 次", text)
    if m:
        r["自穿模(S1)"] = m.group(1)
    m = _last(r"是不是同一張布:.*?中位 ([\d.]+).*?最大 ([\d.]+)", text)
    if m:
        r["邊長比中位"], r["邊長比最大"] = m.groups()
    m = re.search(r"六面壓實判讀.*?壓住時\s+bbox\s+\d+ x\s+\d+ x\s+(\d+).*?放開後\s+bbox\s+\d+ x\s+\d+ x\s+(\d+)", text, re.S)
    if m:
        r["壓住z"], r["放開z"] = m.groups()
    # 入箱:取最後一個「(逐頂點比對內腔…)」區塊(mb 段 = 搬之後)
    blk = None
    for bm in re.finditer(r"===== 真的入箱了嗎\(逐頂點比對內腔[^\n]*\n(.*?)(?:\n\n|\Z)", text, re.S):
        blk = bm.group(1)
    if blk:
        mb = re.search(r"布\s+\d+ 點;超出內腔\s+(\d+) 個.*?x 超 (\d+) / y 超 (\d+) / 低於底 (\d+) / 高於口 (\d+)", blk)
        mc = re.search(r"杯子\s+\d+ 點;超出內腔\s+(\d+) 個", blk)
        if mb:
            r["入箱布超出"] = mb.group(1)
            r["超出分項(x/y/底/口)"] = "/".join(mb.groups()[1:])
        if mc:
            r["入箱杯超出"] = mc.group(1)
    m = _last(r"杯心 \((-?\d+), (-?\d+), (-?\d+)\) mm", text)
    if m:
        r["杯心xyz"] = "(%s,%s,%s)" % m.groups()
    m = re.search(r"⇒ 結論:包裹\(布質心\)相對箱子位移 D=([\d.]+) mm.*?搬前超出 N0=(\d+).*?搬後 N1=(\d+)", text)
    if m:
        r["搬箱相對位移"], r["搬前超出"], r["搬後超出"] = m.groups()
    m = _last(r"^W1 俯視遮蔽\S*\s+(\d+)%", text, re.M)
    if m:
        r["W1"] = m.group(1)
    m = _last(r"^W3 圍蔽 全部 (\d+)%", text, re.M)
    if m:
        r["W3"] = m.group(1)
    m = re.search(r"第二段:布以第一段的結果出生\(([^,)]+)", text)
    if m:
        r["_init_log"] = m.group(1)
    return r


# ---------------------------------------------------------------- volume 版(wrap_vol.log)
_F = r"(-?[\d.]+)"
_VCONT = re.compile(r"(布|杯子)\s+(\d+) 點;超出內腔 (\d+) \| x 超 (\d+) / y 超 (\d+) / 低於底 (\d+)\(最深 ([\d.]+)mm\)"
                    r"/ 高於口 (\d+) \| x " + _F + "~" + _F + r"\(±([\d.]+)\) y " + _F + "~" + _F + r"\(±([\d.]+)\) z "
                    + _F + "~" + _F + r"\(" + _F + "~" + _F + r"\)")
_VSECT = (("closed", "關蓋後"), ("bm", "搬前"), ("am", "搬後"), ("end", "開蓋後"))


def _bb(m):
    return tuple(int(x) for x in m) if m else None


def _vcont_obj(g):
    return dict(n=int(g[2]), x=int(g[3]), y=int(g[4]), lo=int(g[5]), lo_depth=float(g[6]), hi=int(g[7]),
                xmin=float(g[8]), xmax=float(g[9]), xlim=float(g[10]), ymin=float(g[11]), ymax=float(g[12]),
                ylim=float(g[13]), zmin=float(g[14]), zmax=float(g[15]), zlo=float(g[16]), zhi=float(g[17]))


def parse_vol_log(text):
    """wrap_vol.log → dict。主要從結尾 SUMMARY 段抽;入箱超出/搬箱位移只在「真的入箱了嗎」區塊(SUMMARY 沒印)。
    SUMMARY 缺(舊版 out_v*)時:自穿/穿杯/反轉/邊長比改用「判讀」段的「全程最大」行、覆蓋率用判讀 end 行、
    布頂 z 用入箱區塊「開蓋後」的布 z max − 箱底內面;每個欄位的來源記在 r["src"],抽不到的原因記在 r["missing"]。"""
    r = {"src": {}, "missing": {}, "contain": {}}
    m = re.search(r"^args: (\{.*\})\s*$", text, re.M)
    try:
        r["args"] = ast.literal_eval(m.group(1)) if m else {}
    except Exception:
        r["args"] = {}
    m = re.search(r"^板 (\d+)x(\d+)x([\d.]+)mm", text, re.M)
    r["plate"] = (int(m.group(1)), int(m.group(2)), float(m.group(3))) if m else None
    r["mug_dims"] = _bb(re.search(r"^杯子躺平 (\d+) x (\d+) x (\d+) mm", text, re.M).groups()) \
        if re.search(r"^杯子躺平 (\d+) x (\d+) x (\d+) mm", text, re.M) else None
    # 紙箱:meta、內腔、外框
    m = re.search(r"★ 紙箱 (\S+?)\(meta ([^)]+)\):.*?bbox (\d+)x(\d+)x(\d+);箱底內面 z=([\d.]+)、箱口最高 ([\d.]+);"
                  r"內腔 ±(\d+) x ±(\d+)", text)
    if m:
        r["carton"] = dict(usd=m.group(1), meta=m.group(2), bb=_bb(m.groups()[2:5]), floor=float(m.group(6)),
                           rim=float(m.group(7)), ix=float(m.group(8)), iy=float(m.group(9)))
    r["meta_missing"] = bool(re.search(r"找不到[^\n]*meta", text))
    # 全程 bbox(每步 t= 行 + 判讀段)
    bbs = [_bb(x) for x in re.findall(r"^t=\s*[\d.]+ .*?bbox\s*(\d+)x\s*(\d+)x\s*(\d+)", text, re.M)]
    bbs += [_bb(x) for x in re.findall(r"bbox 布 (\d+)x(\d+)x(\d+)", text)]
    if bbs:
        i = max(range(len(bbs)), key=lambda k: max(bbs[k]))
        r["bbox_max"] = max(bbs[i])
        r["bbox_max_bb"] = bbs[i]
    m = re.search(r"^t=\s*([\d.]+) .*?bbox\s*(\d+)x\s*(\d+)x\s*(\d+)", text, re.M)
    if m:
        r["bbox_t0"] = (float(m.group(1)), _bb(m.groups()[1:]))

    sm = re.search(r"^===== SUMMARY =====\n(.*?)(?:^npz →|\Z)", text, re.S | re.M)
    S = sm.group(1) if sm else ""
    r["has_summary"] = bool(sm)

    def put(key, val, src):
        r[key] = val
        r["src"][key] = src

    if S:
        m = re.search(r"E ([\d.e+-]+) T ([\d.]+)mm 面密度 ([\d.]+) cont ([\d.]+) rest ([\d.]+) tuck (\d+)", S)
        if m:
            put("E", m.group(1), "SUMMARY"); put("tuck", m.group(6), "SUMMARY")
        m = re.search(r"四折後\(收耳前 t=([\d.]+)\)bbox (\d+)x(\d+)x(\d+)", S)
        if m:
            put("fold4_bb", _bb(m.groups()[1:]), "SUMMARY")
        m = re.search(r"收耳後/入箱前 bbox (\d+)x(\d+)x(\d+)", S)
        if m:
            put("tuck_bb", _bb(m.groups()), "SUMMARY")
        m = re.search(r"關蓋後 bbox (\d+)x(\d+)x(\d+) 體積÷杯 ([\d.]+)", S)
        if m:
            put("closed_bb", _bb(m.groups()[:3]), "SUMMARY"); put("vol_per_mug", float(m.group(4)), "SUMMARY")
        m = re.search(r"開蓋後 3s:布頂 z max " + _F + " / 99% " + _F + r" mm\(箱口 " + _F + r"\);杯頂俯視覆蓋 (\d+|nan)%", S)
        if m:
            put("top_z", float(m.group(1)), "SUMMARY"); put("top_z99", float(m.group(2)), "SUMMARY")
            put("rim_z", float(m.group(3)), "SUMMARY")
            if m.group(4) != "nan":
                put("cover", int(m.group(4)), "SUMMARY")
        m = re.search(r"全程最大 自穿 (\d+) 布穿杯 (\d+) 反轉 (\d+) 邊長比 \[([\d.]+),([\d.]+)\] 體積比 \[([\d.]+),([\d.]+)\]", S)
        if m:
            for k, v in zip(("pen_max", "inmug_max", "inv_max"), m.groups()[:3]):
                put(k, int(v), "SUMMARY")
            put("lr", (float(m.group(4)), float(m.group(5))), "SUMMARY")
            put("volr", (float(m.group(6)), float(m.group(7))), "SUMMARY")
        m = re.search(r"wall ([\d.]+)s", S)
        if m:
            put("wall", float(m.group(1)), "SUMMARY")
    # ---- fallback:判讀段
    J = re.search(r"===== 判讀 wrap_vol[^\n]*\n(.*?)(?:\n\n|\Z)", text, re.S)
    J = J.group(1) if J else ""
    if "pen_max" not in r:
        m = re.search(r"全程最大:自穿 (\d+)\(.*?\)\| 布穿杯 (\d+) \| 反轉 (\d+) \| 邊長比 \[([\d.]+), ([\d.]+)\]", J)
        if m:
            for k, v in zip(("pen_max", "inmug_max", "inv_max"), m.groups()[:3]):
                put(k, int(v), "判讀段")
            put("lr", (float(m.group(4)), float(m.group(5))), "判讀段")
    if "closed_bb" not in r:
        m = re.search(r"closed_pre_release\s+t=\s*[\d.]+ bbox 布 (\d+)x(\d+)x(\d+) .*?體積÷杯 ([\d.]+)", J)
        if m:
            put("closed_bb", _bb(m.groups()[:3]), "判讀段"); put("vol_per_mug", float(m.group(4)), "判讀段")
    if "tuck_bb" not in r:
        m = re.search(r"fold_end\s+t=\s*[\d.]+ bbox 布 (\d+)x(\d+)x(\d+)", J)
        if m:
            put("tuck_bb", _bb(m.groups()), "判讀段")
    if "cover" not in r:
        m = re.search(r"^\s*end\s+t=.*?杯頂俯視覆蓋 (\d+)%", J, re.M)
        if m:
            put("cover", int(m.group(1)), "判讀段 end 行")
    if "wall" not in r:
        m = re.search(r"wall ([\d.]+)s / sim", text)
        if m:
            put("wall", float(m.group(1)), "影片行")
    # ---- 入箱區塊(SUMMARY 本來就沒有)
    B = re.search(r"===== 真的入箱了嗎\(逐頂點比對內腔\)=====\n(.*?)(?:\n\n|\n=====|\Z)", text, re.S)
    if B:
        cur = None
        for line in B.group(1).split("\n"):
            hm = re.match(r"^ (關蓋後|搬前|搬後|開蓋後)", line)
            if hm:
                cur = dict((b, a) for a, b in _VSECT)[hm.group(1)]
                r["contain"][cur] = {}
                continue
            cm = _VCONT.search(line)
            if cm and cur:
                r["contain"][cur][cm.group(1)] = _vcont_obj(cm.groups())
        m = re.search(r"搬箱:箱位移 \(" + _F + "," + _F + "," + _F + r"\) mm;布質心相對箱 搬前→搬後 差 ([\d.]+) mm;杯心相對箱 差 ([\d.]+) mm",
                      B.group(1))
        if m:
            put("box_disp", tuple(float(x) for x in m.groups()[:3]), "入箱區塊")
            put("move_cloth", float(m.group(4)), "入箱區塊"); put("move_mug", float(m.group(5)), "入箱區塊")
        m = re.search(r"驗收:([^\n]*)", B.group(1))
        if m:
            r["accept_line"] = m.group(1).strip()
    if "top_z" not in r and r["contain"].get("end", {}).get("布") and r.get("carton"):
        o = r["contain"]["end"]["布"]
        put("top_z", o["zmax"] - r["carton"]["floor"], "入箱區塊開蓋後 z max − 箱底內面")
        put("rim_z", r["carton"]["rim"] - r["carton"]["floor"], "紙箱行")
    # 抽不到的原因
    why_nosum = "log 沒有 SUMMARY 段(舊版 wrap_vol 或沒跑完)" if not S else "SUMMARY 有段但沒有這行"
    until = r["args"].get("until")
    for k, nm in (("fold4_bb", "四折後 bbox"), ("tuck_bb", "收耳後 bbox"), ("closed_bb", "關蓋後 bbox"),
                  ("vol_per_mug", "體積÷杯"), ("top_z", "開蓋後布頂 z"), ("cover", "俯視覆蓋"), ("pen_max", "自互穿 max"),
                  ("inmug_max", "穿杯"), ("inv_max", "反轉"), ("lr", "邊長比"), ("wall", "wall"),
                  ("move_cloth", "搬箱位移")):
        if k not in r:
            r["missing"][k] = ("until=%s(只跑到折完,沒有入箱/關蓋/開蓋)" % until) if until and until != "all" \
                and k in ("closed_bb", "vol_per_mug", "top_z", "cover", "move_cloth") else why_nosum
    return r


def vol_stage(v):
    u = (v.get("args") or {}).get("until") or "?"
    return "vol-" + u


def seg_of(args, text):
    if args:
        s = set(args)
        if "--movebox" in s:
            return "mb"
        if "--unbox" in s:
            return "unbox"
        if "--close_lid" in s:
            return "box"
        if "--press6" in s:
            return "c3"
        if "--stage2" in s:
            return "c2"
        if _flag(args, "--wrap_n") == "2":
            return "c1"
        return "其他"
    # 沒有指令列:由 log 推(標 *)
    if "搬箱判讀" in text:
        return "mb*"
    if "unwrap" in text:
        return "unbox*"
    if "真的入箱了嗎" in text:
        return "box*"
    if "六面壓實判讀" in text:
        return "c3*"
    if "第二段:布以第一段" in text:
        return "c2*"
    if re.search(r"wrap (xp|yp)", text):
        return "c1*"
    return ""


# ---------------------------------------------------------------- layer_gap
def layer_stats(npz):
    try:
        import numpy as np
        sys.path.insert(0, ROOT)
        import layer_gap
        d = np.load(npz)
        S, M = d["sheet"].astype(float), d["mug"].astype(float)
        if len(S) != 35 * 35:
            return {}
        with np.errstate(all="ignore"):
            R = layer_gap.measure(S, M, 5.0, 25.0)
        out = {"層數中位": "%.1f" % np.median(R["nabove"])}
        allg = np.concatenate([R["gaps"][k] for k in R["gaps"]]) if R["gaps"] else np.array([])
        if len(allg):
            out["層間距中位"] = "%.2f" % (1000 * np.median(allg))
        if len(R["thick"]):
            out["疊層總厚"] = "%.2f" % (1000 * np.median(R["thick"]))
        return out
    except Exception:
        return {}


# ---------------------------------------------------------------- main
def find_runs(root):
    runs = []
    for dp, dns, fns in os.walk(root):
        rel = os.path.relpath(dp, root)
        top = rel.split(os.sep)[0]
        if top in SKIP_TOP:
            dns[:] = []
            continue
        if "wrap_sim.log" in fns and dp != root:
            runs.append(dp)
    return sorted(runs, key=lambda p: os.path.getmtime(os.path.join(p, "wrap_sim.log")))


VOL_DIR = os.path.join(os.path.dirname(ROOT), "vol")
VOL_VALIDITY = {
    "vol/out_v500_restfold": "invalid:rest shape 用折好的 npz,t=0 炸開 bbox 661(自穿上千)",
}


def find_vol_runs(root=VOL_DIR):
    runs = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [x for x in dns if x not in VOL_SKIP]
        if "wrap_vol.log" in fns:
            runs.append(dp)
    return sorted(runs, key=lambda p: os.path.getmtime(os.path.join(p, "wrap_vol.log")))


def _fmt_bb(b):
    return "x".join(str(x) for x in b) if b else ""


def _fmt_cont(c):
    o = c.get("布") if c else None
    return "%d(%d/%d/%d/%d)" % (o["n"], o["x"], o["y"], o["lo"], o["hi"]) if o else ""


def vol_rows():
    """../vol/**/wrap_vol.log → RUNS.csv 列(kind=vol)。只讀,不寫 vol/。"""
    rows = []
    hroot = os.path.dirname(ROOT)
    for p in find_vol_runs():
        logp = os.path.join(p, "wrap_vol.log")
        with open(logp, errors="replace") as f:
            text = f.read()
        v = parse_vol_log(text)
        A = v.get("args") or {}
        r = {c: "" for c in COLS}
        rid = os.path.relpath(p, hroot)                       # 例 vol/soft/s2
        r["run_id"] = rid
        r["路徑"] = os.path.relpath(p, ROOT)
        r["批次"] = "vol_" + (rid.split(os.sep)[1] if rid.count(os.sep) >= 2 else "out")
        r["log_mtime"] = dt.datetime.fromtimestamp(os.path.getmtime(logp)).strftime("%m-%d %H:%M")
        r["指令列"] = "wrap_vol.py " + " ".join("--%s %s" % (k, A[k]) for k in ("out", "sheet_mm", "young", "areal", "cont",
                                                                                 "rest", "until", "rest_npz", "tuck")
                                                if A.get(k) not in (None, ""))
        r["段"] = vol_stage(v)
        if v.get("plate"):
            r["sheet_mm"] = "%dx%d" % v["plate"][:2]
            r["thick"] = "%g" % v["plate"][2]
        if A.get("cont") is not None:
            r["cont"] = "%g" % (float(A["cont"]) * 1e3)
            r["rest"] = "%g" % (float(A["rest"]) * 1e3)
        if v.get("closed_bb"):
            r["bbox_x"], r["bbox_y"], r["bbox_z"] = (str(x) for x in v["closed_bb"])
        if "pen_max" in v:
            r["自穿模(S1)"] = ""                               # surface 專用;vol 用 vol_自互穿max
        if v.get("lr"):
            r["邊長比最大"] = "%.3f" % v["lr"][1]
            r["vol_邊長比min"] = "%.3f" % v["lr"][0]
        C = v["contain"]
        if C.get("am", {}).get("布"):
            o = C["am"]["布"]
            r["入箱布超出"] = str(o["n"])
            r["超出分項(x/y/底/口)"] = "%d/%d/%d/%d" % (o["x"], o["y"], o["lo"], o["hi"])
        if C.get("am", {}).get("杯子"):
            r["入箱杯超出"] = str(C["am"]["杯子"]["n"])
        if "move_cloth" in v:
            r["搬箱相對位移"] = "%.1f" % v["move_cloth"]
            r["vol_杯搬箱位移"] = "%.1f" % v["move_mug"]
        if C.get("bm", {}).get("布"):
            r["搬前超出"] = str(C["bm"]["布"]["n"])
        if C.get("am", {}).get("布"):
            r["搬後超出"] = str(C["am"]["布"]["n"])
        r["vol_關蓋超出"] = _fmt_cont(C.get("closed"))
        r["vol_搬前分項"] = _fmt_cont(C.get("bm"))
        r["vol_搬後分項"] = _fmt_cont(C.get("am"))
        r["vol_四折後bbox"] = _fmt_bb(v.get("fold4_bb"))
        r["vol_收耳後bbox"] = _fmt_bb(v.get("tuck_bb"))
        r["vol_關蓋後bbox"] = _fmt_bb(v.get("closed_bb"))
        for col, k, fmt in (("vol_體積÷杯", "vol_per_mug", "%.2f"), ("vol_開蓋後布頂z", "top_z", "%.1f"),
                            ("vol_開蓋後布頂z99", "top_z99", "%.1f"), ("vol_箱口z", "rim_z", "%.1f"),
                            ("vol_覆蓋率", "cover", "%d"), ("vol_自互穿max", "pen_max", "%d"),
                            ("vol_穿杯max", "inmug_max", "%d"), ("vol_反轉max", "inv_max", "%d"),
                            ("vol_wall_s", "wall", "%.1f")):
            if k in v:
                r[col] = fmt % v[k]
        if v.get("volr"):
            r["vol_體積比range"] = "%.4f~%.4f" % v["volr"]
        r["vol_E"] = v.get("E") or ("%g" % A["young"] if A.get("young") is not None else "")
        r["vol_tuck"] = v.get("tuck") or ("" if A.get("tuck") is None else str(A["tuck"]))
        srcs = sorted(set(v["src"].values()))
        r["vol_來源"] = ("SUMMARY" if v["has_summary"] else "無 SUMMARY") + ";" + ",".join(s_ for s_ in srcs if s_ != "SUMMARY")
        vids = [x for x in ("wrap.mp4",) if os.path.exists(os.path.join(p, x))]
        r["影片路徑"] = " ".join(os.path.join(r["路徑"], x) for x in vids)
        r["有效性"] = VOL_VALIDITY.get(rid, "valid")
        r["kind"] = "vol"
        rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ROOT, "RUNS.csv"))
    ap.add_argument("--no_layer", action="store_true")
    ap.add_argument("--extra_stdout_dir", action="append", default=[])
    ap.add_argument("--include-vol", dest="include_vol", action="store_true",
                    help="另收 ../vol/**/wrap_vol.log(volume 版,kind=vol;略過 %s)" % ",".join(sorted(VOL_SKIP)))
    a = ap.parse_args()

    runs = find_runs(ROOT)
    sdirs = {ROOT} | {os.path.dirname(p) for p in runs} | set(runs) | set(a.extra_stdout_dir)
    for p in runs:                       # 批次資料夾裡的 _stdout/ 子目錄
        sdirs |= set(glob.glob(os.path.join(os.path.dirname(p), "_stdout*")))
    idx = stdout_index(sorted(sdirs))

    rows = []
    for p in runs:
        rid = os.path.basename(p)
        logp = os.path.join(p, "wrap_sim.log")
        lm = os.path.getmtime(logp)
        with open(logp, errors="replace") as f:
            text = f.read()
        r = {c: "" for c in COLS}
        r.update({k: v for k, v in parse_log(text).items() if k in r})
        info = parse_log(text)
        r["run_id"] = rid
        r["路徑"] = os.path.relpath(p, ROOT)
        rel_parent = os.path.relpath(os.path.dirname(p), ROOT)
        r["批次"] = rel_parent.split(os.sep)[-1] if rel_parent.startswith("runs") else batch_of(rid)
        r["log_mtime"] = dt.datetime.fromtimestamp(lm).strftime("%m-%d %H:%M")
        sp, args = find_stdout(rid, lm, idx)
        if args:
            r["指令列"] = " ".join(shlex.quote(t) for t in args)
            r["stdout來源"] = os.path.relpath(sp, ROOT) if sp.startswith(ROOT) else sp
            r["起點npz"] = _flag(args, "--init_npz") or ""
            r["bend"] = _flag(args, "--bend") or ""
            if not r["sheet_mm"] and _flag(args, "--sheet_mm"):
                r["sheet_mm"] = _flag(args, "--sheet_mm")
        if not r["起點npz"] and info.get("_init_log"):
            r["起點npz"] = info["_init_log"] + "(log)"
        r["段"] = seg_of(args, text)
        if not r["release"] and r["hold"]:
            r["release"] = ""
        vids = [v for v in ("wrap.mp4", "trim.mp4") if os.path.exists(os.path.join(p, v))]
        r["影片路徑"] = " ".join(os.path.join(r["路徑"], v) for v in vids)
        r["有效性"] = validity_of(rid)
        r["備註"] = NOTES.get(rid, "")
        if not a.no_layer and os.path.exists(os.path.join(p, "wrap.npz")):
            r.update(layer_stats(os.path.join(p, "wrap.npz")))
        r["kind"] = "surface"
        rows.append(r)

    nvol = 0
    if a.include_vol:
        for r in vol_rows():
            rows.append(r)
            nvol += 1

    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)

    print("寫入 %s" % a.out)
    print("總列數 %d(surface %d / vol %d)" % (len(rows), len(rows) - nvol, nvol))
    for b, n in sorted(Counter(r["批次"] for r in rows).items()):
        print("  %-18s %3d" % (b, n))
    nv = sum(r["有效性"] == "valid" for r in rows)
    print("valid %d / invalid %d" % (nv, len(rows) - nv))
    print("有指令列 %d / 無 %d" % (sum(bool(r["指令列"]) for r in rows), sum(not r["指令列"] for r in rows)))


if __name__ == "__main__":
    main()
