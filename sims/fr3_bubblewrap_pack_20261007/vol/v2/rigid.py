#!/usr/bin/env python3
"""v2/rigid.py RUN... :用 wrap.npz 的快照,分開「整包剛體轉動」和「杯在包裹裡自轉」。
每段印:布(全部頂點)最佳剛體對齊(Kabsch)的轉動 rotvec(度)與殘差(包裹形狀變化)中位 / p90 mm、杯子轉動 rotvec(度)、杯心相對布質心位移 mm。
段:放錨點(closed_pre_release)→ 搬後(after_move)→ 開蓋後(end)→ 取出放好 + 1 s(g_yn_plan)。"""
import sys, glob, os
import numpy as np
from scipy.spatial.transform import Rotation as R
def kab(A, B):
    ca, cb = A.mean(0), B.mean(0); U, S, Vt = np.linalg.svd((B - cb).T @ (A - ca)); dd = np.sign(np.linalg.det(Vt.T @ U.T)); Rk = Vt.T @ np.diag([1, 1, dd]) @ U.T
    return R.from_matrix(Rk.T), np.linalg.norm((B - cb) @ Rk.T + ca - A, axis=1) * 1e3
print("| run | 段 | 布 整包剛體轉 rotvec ° | 布 形狀變化(剛體對齊後)中位 / p90 mm | 杯 轉 rotvec ° | 杯相對整包 多轉 ° | 杯心相對布質心 位移 mm |")
print("|---|---|---|---|---|---|---|")
for a in sys.argv[1:]:
    for r in (sorted(glob.glob(os.path.join(a, "[0-9]*"))) or [a]):
        f = os.path.join(r, "wrap.npz")
        if not os.path.exists(f): continue
        d = np.load(f)
        for x, y, nm in (("closed_pre_release", "after_move", "放錨點 → 搬後"), ("closed_pre_release", "end", "放錨點 → 開蓋後"), ("end", "g_yn_plan", "開蓋後 → 取出放好 +1 s")):
            if "snap_" + x not in d.files or "snap_" + y not in d.files: continue
            A, B = d["snap_" + x], d["snap_" + y]; MA, MB = d["snapmug_" + x], d["snapmug_" + y]
            rc, res = kab(A, B); rm, _ = kab(MA, MB)
            rel = (rc.inv() * rm).magnitude()
            dm = np.linalg.norm(rc.inv().apply(MB.mean(0) - B.mean(0)) - (MA.mean(0) - A.mean(0))) * 1e3
            print("| %s | %s | %s | %.1f / %.1f | %s | %.1f | %.1f |" % (r, nm, np.round(np.degrees(rc.as_rotvec()), 1).tolist(), np.median(res), np.percentile(res, 90),
                  np.round(np.degrees(rm.as_rotvec()), 1).tolist(), np.degrees(rel), dm))
