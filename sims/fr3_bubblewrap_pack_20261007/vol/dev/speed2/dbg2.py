import sys, os, numpy as np, trimesh
sys.path.insert(0, ".")
import grasp_plan as GPL
from trimesh.ray import ray_util as RU
npz, sd, v = sys.argv[1], sys.argv[2], int(sys.argv[3])
d = np.load(npz); offw = np.array([0, .2, .097])
GPL.setup(d["flat"], 35, 0.08463, 0.0715, np.asarray(trimesh.load("mug.stl").faces))
Pl = d["snap_g_%s_plan" % sd].astype(float) - offw; MUGl = d["snapmug_g_%s_plan" % sd].astype(float) - offw
mugm = GPL.mug_mesh(MUGl); N1 = GPL.S["N1"]; M = GPL.mid(Pl); THK = np.linalg.norm(Pl[N1:] - Pl[:N1], axis=1)
R, _ = GPL.frame(Pl, v); p = M[v]; half = THK[v] / 2; ZO = 0.1345
def column(B): return np.vstack([B + [0, 0, dz] for dz in np.arange(0, max(0.0, ZO + 0.025 - B[:, 2].min()) + 1e-9, 0.003)])
fu = column(GPL.samples_box(p, R, [-0.010, -0.015, half + 0.0005], [0.010, 0.005, half + 0.0085], step=0.003))
flc = column(GPL.samples_box(p, R, [-0.010, 0.007, -half - 0.0085], [0.010, 0.027, -half - 0.0005], step=0.003))
fls = GPL.samples_box(p, R, [-0.010, -0.015, -half - 0.0085], [0.010, 0.027, -half - 0.0005], step=0.003)
S_ = np.vstack([fu, flc, fls])
om, _ = GPL._other_mesh(Pl, v); thr = GPL.T / 2 + 0.0005
_, dd, _ = trimesh.proximity.closest_point(om, S_); old = dd < thr
print("old nc", old.sum(), "new nc", GPL.near_count(om, S_, thr))
# per point new
from trimesh import triangles as TR
tri = om.triangles; best = np.array([np.sqrt(((S_[i] - TR.closest_point(tri, np.repeat(S_[i:i+1], len(tri), 0)))**2).sum(1).min()) for i in range(len(S_))])
w = np.where((best < thr) != old)[0]; print("brute vs trimesh differ", w, best[w], dd[w], thr)
c0 = mugm.contains(S_); c1 = GPL.contains_v(mugm, S_); w = np.where(c0 != c1)[0]; print("contains diff", w)
if len(w):
    _, dm, _ = trimesh.proximity.closest_point(mugm, S_[w]); print("dist", dm, "rerun default:", mugm.contains(S_[w]), RU.contains_points(mugm.ray, S_[w], check_direction=[0,0,1.]))
if len(w):
    print("default contains x8:", [tuple(mugm.contains(S_[w])) for _ in range(8)])
