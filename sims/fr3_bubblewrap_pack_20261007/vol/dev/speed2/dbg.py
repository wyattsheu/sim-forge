import sys, os, numpy as np, trimesh
sys.path.insert(0, ".")
import grasp_plan as GPL
from trimesh.ray import ray_util as RU
d = np.load("../extract6/X2/wrap.npz"); offw = np.array([0, .2, .097])
GPL.setup(d["flat"], 35, 0.08463, 0.0715, np.asarray(trimesh.load("mug.stl").faces))
Pl = d["snap_g_yp_plan"].astype(float) - offw; MUGl = d["snapmug_g_yp_plan"].astype(float) - offw
mugm = GPL.mug_mesh(MUGl); N1 = GPL.S["N1"]; M = GPL.mid(Pl); THK = np.linalg.norm(Pl[N1:] - Pl[:N1], axis=1)
v = 1224; R, _ = GPL.frame(Pl, v); p = M[v]; half = THK[v] / 2; ZO = 0.1345
def column(B): return np.vstack([B + [0, 0, dz] for dz in np.arange(0, max(0.0, ZO + 0.025 - B[:, 2].min()) + 1e-9, 0.003)])
fu = column(GPL.samples_box(p, R, [-0.010, -0.015, half + 0.0005], [0.010, 0.005, half + 0.0085], step=0.003))
flc = column(GPL.samples_box(p, R, [-0.010, 0.007, -half - 0.0085], [0.010, 0.027, -half - 0.0005], step=0.003))
fls = GPL.samples_box(p, R, [-0.010, -0.015, -half - 0.0085], [0.010, 0.027, -half - 0.0005], step=0.003)
S_ = np.vstack([fu, flc, fls])
c0 = mugm.contains(S_); c1 = GPL.contains_v(mugm, S_); c2 = RU.contains_points(mugm.ray, S_, check_direction=[0, 0, 1.0])
w = np.where(c0 != c1)[0]; print("diff idx", w, c0[w], c1[w], c2[w])
q = S_[w]; cp, dd, _ = trimesh.proximity.closest_point(mugm, q); print("dist to surface", dd)
print("sd", trimesh.proximity.signed_distance(mugm, q))
_, dd_all, _ = trimesh.proximity.closest_point(mugm, S_[trimesh.bounds.contains(mugm.bounds, S_)]); print("min dist of inAABB pts", np.sort(dd_all)[:5])
