import sys, os, time, numpy as np, trimesh
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grasp_plan as GPL
d = np.load("../extract6/X2/wrap.npz"); offw = np.array([0, .2, .097])
GPL.setup(d["flat"], 35, 0.08463, 0.0715, np.asarray(trimesh.load("mug.stl").faces))
sd = "yn"; Pl = d["snap_g_yn_plan"].astype(float) - offw; MUGl = d["snapmug_g_yn_plan"].astype(float) - offw
mugm = trimesh.Trimesh(MUGl, GPL.S["MF"], process=False)
N1 = GPL.S["N1"]; M = GPL.mid(Pl); THK = np.linalg.norm(Pl[N1:] - Pl[:N1], axis=1)
F2 = GPL.S["F2"]; ii, jj = GPL.S["ii"], GPL.S["jj"]; NX = 35
cand = np.where(((ii == 0) | (ii == NX) | (jj == 0) | (jj == NX)) & (-F2[:, 1] > 0.0715 - 1e-9))[0]
ZO = 0.1345; tot = [0, 0, 0]
for v in cand[::6]:
    R, _ = GPL.frame(Pl, v); p = M[v]; half = THK[v] / 2
    def column(B): return np.vstack([B + [0, 0, dz] for dz in np.arange(0, max(0.0, ZO + 0.025 - B[:, 2].min()) + 1e-9, 0.003)])
    fu = column(GPL.samples_box(p, R, [-0.010, -0.015, half + 0.0005], [0.010, 0.005, half + 0.0085], step=0.003))
    flc = column(GPL.samples_box(p, R, [-0.010, 0.007, -half - 0.0085], [0.010, 0.027, -half - 0.0005], step=0.003))
    fls = GPL.samples_box(p, R, [-0.010, -0.015, -half - 0.0085], [0.010, 0.027, -half - 0.0005], step=0.003)
    S_ = np.vstack([fu, flc, fls])
    ina = trimesh.bounds.contains(mugm.bounds, S_).sum()
    t0 = time.time(); c0 = mugm.contains(S_); t1 = time.time()
    from trimesh.ray import ray_util as RU; c1 = RU.contains_points(mugm.ray, S_, check_direction=[0, 0, 1.0]); t2 = time.time()
    print("v%d pts %d inAABB %d | default %.2fs n=%d | vertical %.3fs n=%d | diff %d" % (v, len(S_), ina, t1 - t0, c0.sum(), t2 - t1, c1.sum(), (c0 != c1).sum()), flush=True)
