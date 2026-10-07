#!/usr/bin/env python3
"""fold_pen.py — 折疊圖的自穿模,**純 CPU,不用 Isaac**。

使用者 2026-09-24:「包材理論上來說 不能穿模 ... 我看影片我認為現在的包覆方法可能有問題」
實測 S0(物理還沒跑就有的穿模)= 6652 次 ⇒ 穿模是折疊圖「擺」出來的,不是模擬造成的。
折疊圖是純幾何,所以參數要掃就在本機掃,不要一次燒 8 分鐘的 Isaac 啟動。

原因(讀 fold_map 就看得出來):四片折邊橫過杯頂時,z 一律 = PLAT_Z + Hm ——
**四片共面**,而且中間還刻意重疊 25mm。共面又重疊 = 必然互穿。

這裡做的事:給每一片自己的層高(真實包裝就是一片疊一片),掃 layer 值看穿模怎麼變。
"""
import numpy as np, argparse
ap = argparse.ArgumentParser()
ap.add_argument("--mug", default="mug.stl")
ap.add_argument("--margin", type=float, default=0.012)
ap.add_argument("--wall", type=float, default=0.006)
ap.add_argument("--overlap", type=float, default=0.025)
ap.add_argument("--res", type=int, default=34)
ap.add_argument("--layers", default="0,3,6,9,12,16")
a = ap.parse_args()
P = lambda *s: print(*s, flush=True)

import trimesh
m = trimesh.load(a.mug, force="mesh")
V = np.array(m.vertices, float)
unit = 0.001 if np.ptp(V, axis=0).max() > 1.0 else 1.0
V = (V - V.mean(0))*unit
Ry = lambda t: np.array([[np.cos(t),0,np.sin(t)],[0,1,0],[-np.sin(t),0,np.cos(t)]])
Rx = lambda t: np.array([[1,0,0],[0,np.cos(t),-np.sin(t)],[0,np.sin(t),np.cos(t)]])
V = V @ Ry(-np.pi/2).T @ Rx(np.pi/2).T
V -= (V.max(0)+V.min(0))/2.0
ME = V.max(0)-V.min(0)
A_, B_, HC = ME[0]+2*a.margin, ME[1]+2*a.margin, ME[2]+a.margin
CY, CX = B_/2+a.wall, A_/2+a.wall
climb = np.hypot(a.wall, HC)
W = max(A_+2*a.wall+2*(climb+A_/2+a.overlap), B_+2*a.wall+2*(climb+B_/2+a.overlap))
WX = WY = W
PLAT_Z, Hm, K_CORNER = 0.0, ME[2], 0.15
P("杯 %.0f x %.0f x %.0f mm;布 %.0f mm 見方;折線 CX %.0f CY %.0f;橫過高度 Hm %.0f mm"
  % (*ME*1e3, W*1e3, CX*1e3, CY*1e3, Hm*1e3))

LAY = {"yp": 0, "yn": 1, "xp": 2, "xn": 3}
def side_of(u, v):
    sx = max(0.0, abs(u)-CX); sy = max(0.0, abs(v)-CY)
    if sy >= sx: return "yp" if v > 0 else "yn"
    return "xp" if u > 0 else "xn"

def fold_map(u, v, lay):
    """lay = 每層墊高(m)。lay=0 就是現行版本。"""
    qx = min(max(u,-CX), CX); qy = min(max(v,-CY), CY)
    dx, dy = u-qx, v-qy
    s_ = float(np.hypot(dx, dy))
    if s_ < 1e-12: return u, v, PLAT_Z
    nx_, ny_ = dx/s_, dy/s_
    corner = (abs(u) > CX) and (abs(v) > CY)
    kc = K_CORNER if corner else 0.0
    dz = LAY[side_of(u, v)]*lay
    # 墊高在爬升的最後 30% 平滑帶入,徑向不留階梯
    w = min(1.0, max(0.0, (s_-0.7*Hm)/(0.3*Hm)))
    if s_ <= Hm:
        return qx+nx_*kc*s_, qy+ny_*kc*s_, PLAT_Z + s_*np.sqrt(max(1e-9,1-kc*kc)) + dz*w
    d = s_-Hm; rho0 = kc*Hm
    return qx+nx_*rho0-nx_*d, qy+ny_*rho0-ny_*d, PLAT_Z + Hm + dz

def build(lay):
    n = a.res
    pts = np.array([fold_map(-WX/2+i*WX/n, -WY/2+j*WY/n, lay)
                    for j in range(n+1) for i in range(n+1)])
    tri = []
    for j in range(n):
        for i in range(n):
            k = j*(n+1)+i
            tri += [(k,k+1,k+n+2), (k,k+n+2,k+n+1)]
    return pts, np.array(tri, int)

def self_pen(SP, TRI):
    ES = set()
    for t in TRI:
        for u_, v_ in ((0,1),(1,2),(2,0)): ES.add((min(t[u_],t[v_]), max(t[u_],t[v_])))
    E = np.array(sorted(ES), int)
    P0, P1 = SP[E[:,0]], SP[E[:,1]]; D = P1-P0
    V0, V1, V2 = SP[TRI[:,0]], SP[TRI[:,1]], SP[TRI[:,2]]
    E1, E2 = V1-V0, V2-V0
    hits = 0
    for s0 in range(0, len(TRI), 128):
        e1, e2, v0, tr = E1[s0:s0+128], E2[s0:s0+128], V0[s0:s0+128], TRI[s0:s0+128]
        pv = np.cross(D[:,None,:], e2[None,:,:])
        det = (e1[None,:,:]*pv).sum(-1); ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0/np.where(ok, det, 1.0), 0.0)
        tv = P0[:,None,:]-v0[None,:,:]
        u = (tv*pv).sum(-1)*inv
        qv = np.cross(tv, np.broadcast_to(e1[None,:,:], tv.shape))
        vv = (D[:,None,:]*qv).sum(-1)*inv
        tt = (e2[None,:,:]*qv).sum(-1)*inv
        hit = ok & (u>=0)&(u<=1)&(vv>=0)&(u+vv<=1)&(tt>1e-9)&(tt<1-1e-9)
        sh = ((E[:,None,0]==tr[None,:,0])|(E[:,None,0]==tr[None,:,1])|(E[:,None,0]==tr[None,:,2])|
              (E[:,None,1]==tr[None,:,0])|(E[:,None,1]==tr[None,:,1])|(E[:,None,1]==tr[None,:,2]))
        hits += int((hit & ~sh).sum())
    return hits

P("\n 每層墊高 | 自穿模次數 | 包裹高度 | 最短層間距")
P(" ---------|-----------|---------|----------")
for lmm in [float(x) for x in a.layers.split(",")]:
    pts, tri = build(lmm/1000.0)
    n = self_pen(pts, tri)
    P("  %5.0f mm | %9d | %6.0f mm |" % (lmm, n, (pts[:,2].max()-pts[:,2].min())*1e3))

# ── 定位:那些穿模發生在布的哪個區域 ──────────────────────────────────
def locate(lay):
    n = a.res
    FL = np.array([[-WX/2+i*WX/n, -WY/2+j*WY/n] for j in range(n+1) for i in range(n+1)])
    SP, TRI = build(lay)
    ES = set()
    for t in TRI:
        for u_, v_ in ((0,1),(1,2),(2,0)): ES.add((min(t[u_],t[v_]), max(t[u_],t[v_])))
    E = np.array(sorted(ES), int)
    P0, P1 = SP[E[:,0]], SP[E[:,1]]; D = P1-P0
    V0, V1, V2 = SP[TRI[:,0]], SP[TRI[:,1]], SP[TRI[:,2]]
    E1, E2 = V1-V0, V2-V0
    reg = {"角落錐面":0, "折邊(橫過杯頂)":0, "折邊(爬升)":0, "中央平台":0}
    pairs = []
    for s0 in range(0, len(TRI), 128):
        e1, e2, v0, tr = E1[s0:s0+128], E2[s0:s0+128], V0[s0:s0+128], TRI[s0:s0+128]
        pv = np.cross(D[:,None,:], e2[None,:,:])
        det = (e1[None,:,:]*pv).sum(-1); ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0/np.where(ok, det, 1.0), 0.0)
        tv = P0[:,None,:]-v0[None,:,:]
        u = (tv*pv).sum(-1)*inv
        qv = np.cross(tv, np.broadcast_to(e1[None,:,:], tv.shape))
        vv = (D[:,None,:]*qv).sum(-1)*inv
        tt = (e2[None,:,:]*qv).sum(-1)*inv
        hit = ok & (u>=0)&(u<=1)&(vv>=0)&(u+vv<=1)&(tt>1e-9)&(tt<1-1e-9)
        sh = ((E[:,None,0]==tr[None,:,0])|(E[:,None,0]==tr[None,:,1])|(E[:,None,0]==tr[None,:,2])|
              (E[:,None,1]==tr[None,:,0])|(E[:,None,1]==tr[None,:,1])|(E[:,None,1]==tr[None,:,2]))
        ei, ti = np.where(hit & ~sh)
        for k in range(len(ei)):
            pairs.append((E[ei[k]], tr[ti[k]]))
    for e, t in pairs:
        mu, mv = FL[e].mean(0)
        sx = max(0.0, abs(mu)-CX); sy = max(0.0, abs(mv)-CY)
        s_ = np.hypot(sx, sy)
        if sx > 0 and sy > 0:          reg["角落錐面"] += 1
        elif s_ > Hm:                  reg["折邊(橫過杯頂)"] += 1
        elif s_ > 0:                   reg["折邊(爬升)"] += 1
        else:                          reg["中央平台"] += 1
    P("\n=== lay=%.0fmm 的 %d 次穿模,發生在哪(依「穿人的那條邊」的攤平位置分類)===" % (lay*1e3, len(pairs)))
    for k, v in sorted(reg.items(), key=lambda x: -x[1]):
        P("   %-18s %5d  (%.0f%%)" % (k, v, v/max(1,len(pairs))*100))


P("\n=== 掃角落錐面比例 K_CORNER(其餘不動)===")
P(" K_CORNER | 自穿模 | 最小三角形面積(mm^2)")
import sys
for K in [0.0, 0.05, 0.10, 0.15, 0.25, 0.40, 0.60]:
    K_CORNER = K
    globals()["K_CORNER"] = K
    pts, tri = build(0.0)
    ar = 0.5*np.linalg.norm(np.cross(pts[tri[:,1]]-pts[tri[:,0]], pts[tri[:,2]]-pts[tri[:,0]]), axis=1)
    P("   %5.2f  | %6d | %.4f" % (K, self_pen(pts, tri), ar.min()*1e6))
globals()["K_CORNER"] = 0.15
locate(0.0)
