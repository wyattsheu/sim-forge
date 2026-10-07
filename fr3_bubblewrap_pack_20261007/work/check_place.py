#!/usr/bin/env python3
"""check_place.py — 放進箱子之前的座標驗證(純 CPU,吃 wrap.npz)。

使用者 2026-09-25:「你必須確定 當你移動坐標 把這個放入一個開著的箱子時 是否有穿模
應該可以從 max point 之類確認吧,放進去確認沒問題 才開始使用紙蓋壓下」

三件事都用座標判,不看畫面:
  C1 布有沒有穿進**杯子裡面**(杯子是封閉網格 → 用 trimesh.contains 判內外)
  C2 布有沒有超出**紙箱內腔**
  C3 杯子有沒有超出紙箱內腔
只有三項全過,才可以開始關蓋。
"""
import numpy as np, trimesh, argparse
ap = argparse.ArgumentParser()
ap.add_argument("npz")
ap.add_argument("--mug", default="mug.stl")
ap.add_argument("--dz", type=float, default=0.0, help="把整包往上搬多少 m(模擬放進箱子)")
ap.add_argument("--ix", type=float, default=0.132)
ap.add_argument("--iy", type=float, default=0.112)
ap.add_argument("--floor", type=float, default=0.003)
ap.add_argument("--top", type=float, default=0.103)
a = ap.parse_args()
P = lambda *s: print(*s, flush=True)

d = np.load(a.npz)
SP = d["sheet"].copy(); MW = d["mug"].copy()
SP[:, 2] += a.dz; MW[:, 2] += a.dz

# 用 npz 裡的杯子頂點 + STL 的面,重建封閉網格
m = trimesh.load(a.mug)
F = np.asarray(m.faces)
mug = trimesh.Trimesh(vertices=MW, faces=F, process=False)
P("杯子網格:%d 點 %d 面;watertight=%s;體積 %.1f cm^3"
  % (len(MW), len(F), mug.is_watertight, mug.volume*1e6))

inside = mug.contains(SP)
P("\nC1 布穿進杯子裡面的頂點:**%d / %d**(%.1f%%)" % (inside.sum(), len(SP), inside.mean()*100))
if inside.any():
    dmax = trimesh.proximity.signed_distance(mug, SP[inside]).max()
    P("   最深 %.1f mm;這些點的世界座標 x %.0f~%.0f y %.0f~%.0f z %.0f~%.0f mm"
      % (dmax*1e3, *(np.array([SP[inside][:,0].min(), SP[inside][:,0].max(),
                               SP[inside][:,1].min(), SP[inside][:,1].max(),
                               SP[inside][:,2].min(), SP[inside][:,2].max()])*1e3)))

def box_chk(nm, Q):
    ox = np.abs(Q[:,0]) > a.ix; oy = np.abs(Q[:,1]) > a.iy
    olo = Q[:,2] < a.floor - 0.0005; ohi = Q[:,2] > a.top
    bad = ox|oy|olo|ohi
    P("  %-4s %6d 點;超出 %5d(%.1f%%)| x超%d y超%d 低於底%d 高於口%d"
      % (nm, len(Q), int(bad.sum()), bad.mean()*100, int(ox.sum()), int(oy.sum()),
         int(olo.sum()), int(ohi.sum())))
    P("       max point: x %+7.1f / %+7.1f (限 ±%.0f)  y %+7.1f / %+7.1f (限 ±%.0f)  z %+7.1f / %+7.1f (限 %.0f~%.0f)"
      % (Q[:,0].min()*1e3, Q[:,0].max()*1e3, a.ix*1e3,
         Q[:,1].min()*1e3, Q[:,1].max()*1e3, a.iy*1e3,
         Q[:,2].min()*1e3, Q[:,2].max()*1e3, a.floor*1e3, a.top*1e3))
    return int(bad.sum())

P("\nC2/C3 紙箱內腔(|x|<=%.0f, |y|<=%.0f, %.0f<=z<=%.0f mm),整包往上搬了 %.0f mm"
  % (a.ix*1e3, a.iy*1e3, a.floor*1e3, a.top*1e3, a.dz*1e3))
nb_s = box_chk("布", SP); nb_m = box_chk("杯子", MW)

ok = (inside.sum() == 0) and nb_s == 0 and nb_m == 0
P("\n⇒ %s" % ("三項全過,可以開始關蓋 ✅" if ok else
              "**還不能關蓋**:布穿杯 %d、布超箱 %d、杯超箱 %d" % (int(inside.sum()), nb_s, nb_m)))
