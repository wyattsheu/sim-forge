#!/usr/bin/env python3
"""折法多樣性(FINAL_PLAN §3):抽樣 / 列折序 / 逐一跑 wrap_vol.py --until box 篩選 / 寫 variants/VARIANTS.csv。
用法(在 vol/ 下,python3 即可,模擬用 /isaac-sim/python.sh):
  python3 fold_variants.py --list                         # 列 24 種折序
  python3 fold_variants.py --orders                       # 產生 24 折序組(其餘預設,布 500)→ variants/o_<序>/
  python3 fold_variants.py --n 12 --seed 7                # 隨機抽 12 組 → variants/r7_00.. /
  python3 fold_variants.py --run [--ids o_*] [--full]     # 逐一跑(一次一個,GPU 已用 <20000MiB 才開跑);--full = 通過者再跑整鏈
  python3 fold_variants.py --csv                          # 只重新彙整 CSV(含 layer_order 最外層片)
"""
import os, sys, re, json, csv, glob, time, random, itertools, argparse, subprocess, fnmatch
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
VD = "variants"; PY = "/isaac-sim/python.sh"; GPU_MAX = 20000
SIDES4 = ["xp", "xn", "yp", "yn"]
ORDERS = [",".join(p) for p in itertools.permutations(SIDES4)]
BASE = dict(sheet_mm=500)

def cls(o):
    s = o.split(","); fx = "x先" if s[0][0] == "x" else "y先"
    return fx + ("/同軸連續" if s[0][0] == s[1][0] else "/交錯")

def write(vid, prm):
    d = os.path.join(VD, vid); os.makedirs(d, exist_ok=True)
    json.dump(prm, open(os.path.join(d, "params.json"), "w"), indent=1, ensure_ascii=False)
    args = " ".join("--%s=%s" % (k, v) for k, v in prm.items() if not k.startswith("_"))
    open(os.path.join(d, "cmd.sh"), "w").write(
        "#!/bin/bash\n# %s\ncd %s\nUNTIL=${UNTIL:-box}; OUT=${OUT:-%s/%s/box}\n%s wrap_vol.py %s --until $UNTIL --out $OUT\n"
        % (vid, HERE, VD, vid, PY, args))
    os.chmod(os.path.join(d, "cmd.sh"), 0o755)

def sample(n, seed):
    R = random.Random(seed)
    for k in range(n):
        sx = R.uniform(420, 560); ar = R.uniform(0.8, 1.25); sy = min(560, max(420, sx * ar))
        yaw = R.choice([0, 90, 180, 270]) + R.uniform(-10, 10)
        prm = dict(sheet_x_mm=round(sx), sheet_y_mm=round(sy), fold_order=R.choice(ORDERS),
                   mug_off_mm="%d,%d" % (R.randint(-30, 30), R.randint(-30, 30)), mug_yaw_deg=round(yaw, 1),
                   tip_over_mm=R.randint(10, 45), margin=round(R.uniform(0.008, 0.020), 4), wall=round(R.uniform(0.003, 0.010), 4),
                   tuck=R.choice([0, 1]), fold_span=round(R.uniform(2, 4), 2), fold_hold=round(R.uniform(0.2, 1.0), 2),
                   young=int(R.uniform(1.5e3, 3e3)), seed=seed * 1000 + k)
        write("r%d_%02d" % (seed, k), prm)

def gpu_used():
    try: return max(int(x) for x in subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]).split())
    except Exception: return 0

def parse(log):
    r = dict(status="nolog")
    if not os.path.exists(log): return r
    L = open(log, errors="ignore").read()
    m = re.search(r"折線 CX=([\d.]+) CY=([\d.]+)", L); r["CX"], r["CY"] = (float(m[1]), float(m[2])) if m else (np.nan, np.nan)
    r["no_reach"] = ",".join(re.findall(r"  (\w\w):折線.*搆不到中線", L))
    r["infeasible"] = ",".join(re.findall(r"  (\w\w):折線.*infeasible", L))
    ins = re.search(r"入箱前.*?\n\s*布\s+\d+ 點;超出內腔 (\d+) \| x 超 (\d+) / y 超 (\d+) / 低於底 (\d+).*?/ 高於口 (\d+)", L, re.S)
    rows = re.findall(r"t=\s*([\d.]+) (fold \w\w|tuck ears \(side squeeze\)|into box)\s+bbox (\d+)x(\d+)x\s*(\d+) \| 自穿\s+(\d+) \| 布穿杯\s+(\d+) \| 反轉\s+(\d+) \| 體積比 ([\d.]+) \| 邊長比 \[([\d.]+),([\d.]+)\]", L)
    pre = [x for x in rows if not x[1].startswith("into")]
    if not ins or not pre:
        r["status"] = "crash/incomplete"; return r
    f = pre[-1]; foldrows = [x for x in rows if x[1].startswith("fold")]
    r.update(out=int(ins[1]), out_x=int(ins[2]), out_y=int(ins[3]), out_hi=int(ins[5]),
             self_max=max(int(x[5]) for x in pre), mugpen_max=max(int(x[6]) for x in pre), inv_max=max(int(x[7]) for x in pre),
             edge_lo=min(float(x[9]) for x in pre), edge_hi=max(float(x[10]) for x in pre),
             fold_bbox="%sx%sx%s" % foldrows[-1][2:5], pre_bbox="%sx%sx%s" % f[2:5])
    fail = []
    if r["out"] > 0: fail.append("超出內腔%d(x%d/y%d/口%d)" % (r["out"], r["out_x"], r["out_y"], r["out_hi"]))
    if r["mugpen_max"] > 0: fail.append("穿杯%d" % r["mugpen_max"])
    if r["self_max"] >= 20: fail.append("自穿%d" % r["self_max"])
    if r.get("infeasible"): fail.append("infeasible(" + r["infeasible"] + ")")
    if r["inv_max"] > 0: fail.append("反轉%d" % r["inv_max"])
    if not (0.5 <= r["edge_lo"] and r["edge_hi"] <= 1.65): fail.append("邊長比[%.2f,%.2f]" % (r["edge_lo"], r["edge_hi"]))
    r["phys_pass"] = int(not [x for x in fail if not x.startswith("邊長比")])   # 不看邊長比(預設組本身就 0.57/1.56)
    r["fail"] = ";".join(fail); r["status"] = "PASS" if not fail else "FAIL"
    return r

def outer_layer(npz, CX, CY, moff, snap="snap_fold_end"):
    """layer_order.analyze:每片被他片壓住的比例;最外層 = 被壓比例最小的片。"""
    sys.path.insert(0, HERE); import layer_order as LO
    try: d = np.load(npz)
    except Exception: return "", {}
    if snap not in d.files: return "", {}
    T = d[snap]; n = len(T) // 2; Pm = (T[:n] + T[n:]) / 2 * 1e3
    F2 = d["flat"][:n, :2] + np.asarray(moff) / 1e3
    side = LO.side_of(F2, CX / 1e3, CY / 1e3); pct = {}
    for sd in SIDES4:
        idx, over, who, under = LO.analyze(Pm, side, sd)
        pct[sd] = round(100 * over.mean(), 1) if len(idx) else np.nan
    return min(pct, key=lambda k: pct[k]), pct

COLS = ["id", "status", "phys_pass", "fail", "fold_order", "class", "first", "outer_by_order", "outer_layer", "over_pct",
        "sheet_x_mm", "sheet_y_mm", "mug_off_mm", "mug_yaw_deg", "tip_over_mm", "margin", "wall", "tuck", "fold_span", "fold_hold", "young", "seed",
        "CX", "CY", "no_reach", "infeasible", "out", "out_x", "out_y", "out_hi", "mugpen_max", "self_max", "inv_max", "edge_lo", "edge_hi", "fold_bbox", "pre_bbox",
        "wall_s", "full_status"]

def summarize():
    out = []
    for d in sorted(glob.glob(os.path.join(VD, "*/params.json"))):
        vd = os.path.dirname(d); vid = os.path.basename(vd)
        if vid.startswith("_"): continue
        prm = json.load(open(d)); fo = prm.get("fold_order", "xp,xn,yp,yn")
        r = parse(os.path.join(vd, "box", "wrap_vol.log"))
        row = dict(prm); row.update(r); row.update(id=vid, fold_order=fo, first=fo.split(",")[0], outer_by_order=fo.split(",")[-1]); row["class"] = cls(fo)
        if r["status"] in ("PASS", "FAIL"):
            moff = [float(x) for x in str(prm.get("mug_off_mm", "0,0")).split(",")]
            ol, pct = outer_layer(os.path.join(vd, "box", "wrap.npz"), r["CX"], r["CY"], moff)
            row["outer_layer"] = ol; row["over_pct"] = " ".join("%s:%s" % kv for kv in pct.items())
        if os.path.exists(os.path.join(vd, "wall_s")): row["wall_s"] = open(os.path.join(vd, "wall_s")).read().strip()
        if os.path.exists(os.path.join(vd, "full", "wrap_vol.log")):
            L = open(os.path.join(vd, "full", "wrap_vol.log"), errors="ignore").read()
            m = re.findall(r"真的入箱了嗎.*?\n.*?\n\s*布\s+\d+ 點;超出內腔 (\d+)", L, re.S)
            row["full_status"] = ("done,搬後超出%s" % m[-1]) if m else "incomplete"
        out.append(row)
    for p in (os.path.join(VD, "VARIANTS.csv"), "VARIANTS.csv"):
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, COLS, extrasaction="ignore"); w.writeheader(); [w.writerow(x) for x in out]
    return out

PHYS = False
def run(pats, full):
    vids = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(VD, "*/cmd.sh")))
    vids = [v for v in vids if any(fnmatch.fnmatch(v, p) for p in pats)]
    for vid in vids:
        vd = os.path.join(VD, vid)
        for stage in (["box", "full"] if full else ["box"]):
            log = os.path.join(vd, stage, "wrap_vol.log")
            if stage == "full" and not (lambda r_: r_["status"] == "PASS" or (PHYS and r_.get("phys_pass")))(parse(os.path.join(vd, "box", "wrap_vol.log"))): break
            if os.path.exists(os.path.join(vd, stage, "wrap.npz")): continue
            while gpu_used() >= GPU_MAX:
                print("  GPU %d MiB >= %d,等 30s" % (gpu_used(), GPU_MAX), flush=True); time.sleep(30)
            env = dict(os.environ, UNTIL="box" if stage == "box" else "all", OUT=os.path.join(VD, vid, stage))
            t0 = time.time(); print("[%s] %s %s 開跑(GPU %d MiB)" % (time.strftime("%H:%M"), vid, stage, gpu_used()), flush=True)
            os.makedirs(os.path.join(vd, stage), exist_ok=True)
            with open(os.path.join(vd, stage + ".stdout"), "w") as so:
                subprocess.call(["timeout", "3600", "bash", os.path.join(vd, "cmd.sh")], stdout=so, stderr=subprocess.STDOUT, env=env)
            if stage == "box": open(os.path.join(vd, "wall_s"), "w").write("%.0f" % (time.time() - t0))
            r = parse(log); print("   → %s %s %.0fs" % (r["status"], r.get("fail", ""), time.time() - t0), flush=True)
            summarize()

def video(maxn=24, out="videos/VARIANTS_grid.mp4"):
    """通過的組:折疊段壓成 5 s + 入箱前 1 幀停 1 s,480x270 加標籤,xstack 拼格。"""
    rows = [r for r in summarize() if r.get("status") == "PASS" or r.get("phys_pass")][:maxn]
    os.makedirs("videos", exist_ok=True); tmp = os.path.join(VD, "_clips"); os.makedirs(tmp, exist_ok=True); clips = []
    for r in rows:
        bd = os.path.join(VD, r["id"], "box"); L = open(os.path.join(bd, "wrap_vol.log"), errors="ignore").read()
        m = re.search(r"折完 ([\d.]+) \| 入箱 ([\d.]+)", L)
        if not m or not os.path.exists(os.path.join(bd, "wrap.mp4")): continue
        tf, ti = float(m[1]), float(m[2]); c = os.path.join(tmp, r["id"] + ".mp4")
        lab = "%s %s out=%s" % (r["id"], r["fold_order"].replace(",", "-"), r.get("outer_layer", ""))
        fc = ("[0:v]trim=0.5:%.2f,setpts=(PTS-STARTPTS)*%.4f,fps=30,scale=480:270[a];"
              "[0:v]trim=%.2f:%.2f,setpts=PTS-STARTPTS,scale=480:270,tpad=stop_mode=clone:stop_duration=1,trim=0:1,setpts=PTS-STARTPTS[b];"
              "[a][b]concat=n=2,drawtext=text='%s':x=6:y=6:fontsize=16:fontcolor=white:box=1:boxcolor=black@0.5[v]") % (
              tf, 5.0 / (tf - 0.5), ti - 0.1, ti - 0.05, lab)
        subprocess.call(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(bd, "wrap.mp4"), "-filter_complex", fc, "-map", "[v]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", c])
        if os.path.exists(c): clips.append(c)
    n = len(clips); cols = int(np.ceil(np.sqrt(n))) if n else 0
    if n == 0: print("沒有通過的組"); return
    if n == 1: subprocess.call(["cp", clips[0], out]); return
    lay = "|".join("%d_%d" % ((i % cols) * 480, (i // cols) * 270) for i in range(n))
    args = sum([["-i", c] for c in clips], [])
    fc = "".join("[%d:v]" % i for i in range(n)) + "xstack=inputs=%d:layout=%s:fill=black[v]" % (n, lay)
    subprocess.call(["ffmpeg", "-y", "-loglevel", "error", *args, "-filter_complex", fc, "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", out])
    print("grid %d 格 → %s" % (n, out))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true"); ap.add_argument("--orders", action="store_true")
    ap.add_argument("--n", type=int, default=0); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--run", action="store_true"); ap.add_argument("--ids", nargs="*", default=["*"])
    ap.add_argument("--full", action="store_true"); ap.add_argument("--csv", action="store_true")
    ap.add_argument("--video", action="store_true", help="拼 videos/VARIANTS_grid.mp4")
    ap.add_argument("--phys", action="store_true", help="--full 的門檻改用 phys_pass(不看邊長比)")
    a = ap.parse_args(); PHYS = a.phys
    if a.list:
        for i, o in enumerate(ORDERS): print("%2d %s  %s  最外層(名義)=%s" % (i, o, cls(o), o.split(",")[-1]))
    if a.orders:
        for o in ORDERS: write("o_" + o.replace(",", ""), dict(BASE, fold_order=o))
    if a.n: sample(a.n, a.seed)
    if a.run: run(a.ids, a.full)
    if a.video: video()
    if a.csv or a.run: [print(x["id"], x.get("status"), x.get("fail", ""), x.get("outer_layer", "")) for x in summarize()]
