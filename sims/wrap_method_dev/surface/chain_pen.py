#!/usr/bin/env python3
"""chain_pen.py — 把整條包裝鏈路的 traj.npz 接成一條時間軸,量「布穿過杯子」。

使用者 2026-09-26:「從杯子擺放到包材上 這個時間點開始測穿模」

判定用**邊級別**,不是頂點:每條邊取 19 個內點,測是否落在杯子網格內部。
頂點全在外面、整條邊穿過杯壁是可能的 —— 先前就是這樣漏掉的
(頂點判定說 0 條,邊判定說 14 條)。

用法:
    python3 chain_pen.py mug.stl traj_c1.npz traj_c2.npz traj_c3.npz traj_c4.npz

純 CPU,不需要 Isaac。
"""
import numpy as np, trimesh, sys

MUG = sys.argv[1]
FILES = sys.argv[2:]

nx = ny = 34
tris = []
for j in range(ny):
    for i in range(nx):
        A = j*(nx+1)+i; B = A+1; C = A+nx+1; D = C+1
        tris += [[A, B, D], [A, D, C]]
E = set()
for t in tris:
    for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
        E.add((min(a, b), max(a, b)))
E = np.array(sorted(E))
TS = np.linspace(0.05, 0.95, 19)
F = np.asarray(trimesh.load(MUG).faces)


def quat_R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


print(f"{'總時間':>7} {'段':>3} {'段內t':>6} {'階段':<20}{'邊穿杯':>7}{'最深mm':>8}{'增量':>7}")
T0 = 0.0
prev = None
rows = []
for si, f in enumerate(FILES, 1):
    d = np.load(f)
    T, PH, S, MP, V = d['t'], d['phase'], d['sheet'], d['mugpose'], d['mugrest']
    for k in range(len(T)):
        MW = V @ quat_R(MP[k][3:]).T + MP[k][:3]
        mug = trimesh.Trimesh(vertices=MW, faces=F, process=False)
        SP = S[k]
        P = np.concatenate([SP[E[:, 0]][:, None, :]*(1-u) + SP[E[:, 1]][:, None, :]*u
                            for u in TS], axis=1).reshape(len(E), len(TS), 3)
        # 先用杯子的 bbox 過濾:絕大多數取樣點離杯子很遠,不必做內外判定。
        # 67k 點砍到幾千點 —— 這是能不能在合理時間內跑完的關鍵(第一版沒過濾,40 分鐘沒跑完)。
        lo, hi = MW.min(0) - 1e-4, MW.max(0) + 1e-4
        near = np.all((P > lo) & (P < hi), axis=2)
        ins = np.zeros(near.shape, bool)
        if near.any():
            ins[near] = mug.contains(P[near])
        n = int(ins.any(1).sum())
        dep = (float(trimesh.proximity.signed_distance(mug, P[ins]).max()*1e3)
               if ins.any() else 0.0)
        dn = "" if prev is None else "%+d" % (n - prev)
        print(f"{T0+T[k]:7.1f} {si:3d} {T[k]:6.1f} {str(PH[k]):<20}{n:7d}{dep:8.1f}{dn:>7}")
        rows.append((T0+T[k], si, float(T[k]), str(PH[k]), n, dep))
        prev = n
    T0 += float(T[-1]) + 0.5

R = np.array([(r[0], r[4], r[5]) for r in rows])
print("\n===== 判讀 =====")
print(f"C1 第一格(杯子剛放到攤平的布上):邊穿杯 {rows[0][4]} 條"
      f" ⇒ {'乾淨' if rows[0][4] == 0 else '★ 初始擺放就穿了'}")
for s in sorted(set(r[1] for r in rows)):
    sub = [r for r in rows if r[1] == s]
    mx = max(r[4] for r in sub)
    print(f"   第 {s} 段:{len(sub)} 格,邊穿杯 {min(r[4] for r in sub)}~{mx},"
          f"最深 {max(r[5] for r in sub):.1f} mm")
# 段與段交界的跳變
print("C3 段交界的跳變:")
for s in sorted(set(r[1] for r in rows))[1:]:
    a = [r for r in rows if r[1] == s-1][-1]
    b = [r for r in rows if r[1] == s][0]
    print(f"   第{s-1}段末 {a[4]} → 第{s}段首 {b[4]}  ({b[4]-a[4]:+d})"
          f"{'   ★ 階躍 ⇒ 載入時的座標搬移,不是物理' if abs(b[4]-a[4]) > 20 else ''}")
print(f"C4 全程最深穿入 {R[:,2].max():.1f} mm"
      f"(引擎 restOffset=1.0mm 是目標分離、contactOffset=5.0mm 是接觸帶)")
