#!/usr/bin/env python3
"""prof_plan.py — 離線重現 wrap_vol g_plan 的 CPU 規劃(rank + site_candidates + gap_below),量時間 / cProfile / 存結果比對。
  /isaac-sim/python.sh speed2/prof_plan.py --npz ../extract6/X2/wrap.npz --mod grasp_plan --out res_old.pkl [--prof]
"""
import sys, os, argparse, time, pickle, cProfile, pstats, importlib
import numpy as np, trimesh
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "speed2"))
ap = argparse.ArgumentParser()
ap.add_argument("--npz", default=os.path.join(HERE, "..", "extract6", "X2", "wrap.npz"))
ap.add_argument("--mod", default="grasp_plan"); ap.add_argument("--out", default="")
ap.add_argument("--prof", action="store_true"); ap.add_argument("--sides", default="yn,yp")
ap.add_argument("--offw", default="0,0.2,0.097")
ap.add_argument("--snap", default="plan", help="snap_g_<sd>_<snap>")
a = ap.parse_args()
GPL = importlib.import_module(a.mod)
d = np.load(a.npz)
CX, CY = 0.08463, 0.07150
BOXL = dict(IX=0.132, IY=0.112, ZFLOOR=0.003, ZOBST=0.1295 + 0.005)
offw = np.array([float(x) for x in a.offw.split(",")])
MF = trimesh.load(os.path.join(HERE, "mug.stl")).faces
GPL.setup(d["flat"], 35, CX, CY, np.asarray(MF), thick=0.004)
GAPG = 0.004; PAD = 0.024
res = {}
def run():
    for sd in a.sides.split(","):
        Pl = d["snap_g_%s_%s" % (sd, a.snap)].astype(float) - offw; MUGl = d["snapmug_g_%s_%s" % (sd, a.snap)].astype(float) - offw
        t0 = time.time(); c0 = time.process_time(); rows = GPL.rank(Pl, MUGl, sd, BOXL); t1 = time.time()
        cs = GPL.site_candidates(Pl, sd, GAPG, PAD, nk=13, r_mm=16.0, dz_mm=2.0, chord=1)
        for c in cs:
            Rc, _ = GPL.frame(Pl, c["v"]); c["gap"] = GPL.gap_below(Pl, MUGl, c["v"], Rc, BOXL) * 1e3
        t2 = time.time(); c2 = time.process_time()
        res[sd] = dict(rows=rows, cands=cs)
        print("%s rank %.2fs (%d rows, ok %d) | site_cands+gap %.2fs (%d) | 合計 wall %.2fs CPU %.2fs" % (sd, t1 - t0, len(rows), sum(r["ok"] for r in rows), t2 - t1, len(cs), t2 - t0, c2 - c0), flush=True)
if a.prof:
    pr = cProfile.Profile(); pr.enable(); run(); pr.disable()
    pstats.Stats(pr).sort_stats("cumulative").print_stats(30)
else:
    run()
if a.out: pickle.dump(res, open(a.out, "wb"))
if a.out and os.path.exists(a.out.replace("new", "old")) and "new" in os.path.basename(a.out):
    o = pickle.load(open(a.out.replace("new", "old"), "rb")); bad = 0
    for sd in res:
        ro, rn = o[sd]["rows"], res[sd]["rows"]
        for x, y in zip(ro, rn):
            for k in x:
                vx, vy = x[k], y[k]
                same = np.allclose(vx, vy, rtol=0, atol=1e-9) if isinstance(vx, (float, np.ndarray)) else vx == vy
                if not same: bad += 1; print("DIFF", sd, "v", x["v"], y["v"], k, vx, vy)
        for x, y in zip(o[sd]["cands"], res[sd]["cands"]):
            for k in x:
                vx, vy = x[k], y[k]
                same = np.allclose(vx, vy, rtol=0, atol=1e-9) if isinstance(vx, (float, np.ndarray)) else vx == vy
                if not same: bad += 1; print("DIFF cand", sd, k, vx, vy)
        print("%s: rows %d order %s | cands %d order %s" % (sd, len(rn), [r["v"] for r in ro] == [r["v"] for r in rn], len(res[sd]["cands"]), [c["v"] for c in o[sd]["cands"]] == [c["v"] for c in res[sd]["cands"]]))
    print("COMPARE: %d 欄位不同" % bad)
