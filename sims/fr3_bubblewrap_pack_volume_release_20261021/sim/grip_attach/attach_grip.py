#!/usr/bin/env python3
"""attach_grip.py — 夾爪閉合時綁定頂點(VtxXformAttachment),張開時 RemovePrim。

在 SimulationApp 之後 import。用法(見 README.md):
    fp  = finger_pose(center_between_fingers, R_finger_to_world, gap_m, half_xy=(0.01, 0.01))
    vid = select_vertices(Pw, fp, pad_mm=8, layer_mask=mask)     # Pw: 該 deformable 的世界座標頂點
    bind(stage, vid, "/World/fu", points=Pw, body_path="/World/plate", finger_pos=cu, finger_R=R, scope="/World/gatt_a")
    ...
    release(stage)            # 全部放開;release(stage, "/World/gatt_a") 只放一個
"""
import numpy as np
from pxr import Sdf
import os, sys
_VOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _VOL not in sys.path:
    sys.path.insert(0, _VOL)
import volcommon as VC  # noqa: E402

BAND_TOL = 0.002          # 高度帶:指面內側之間再各外擴 2 mm(布 rest/contact offset + 壓縮)
_SCOPES = []


def finger_pose(center, R=None, gap=0.004, half_xy=(0.010, 0.010)):
    """center = 兩指面中間點(世界);R = 指框→世界(第 3 軸 = 夾持法線);gap = 指面內側間距 m;half_xy = 指面半寬。"""
    return dict(c=np.asarray(center, float), R=np.eye(3) if R is None else np.asarray(R, float),
                gap=float(gap), half=np.asarray(half_xy, float))


def select_vertices(points, fp, pad_mm, layer_mask=None, band_tol=BAND_TOL):
    """足跡 = 指面矩形各邊外擴 pad_mm,且 |n| <= gap/2 + band_tol;再與 layer_mask(bool 陣列或索引)取交集。回傳索引。"""
    L = (np.asarray(points, float) - fp["c"]) @ fp["R"]
    pad = pad_mm / 1e3
    m = (np.abs(L[:, 0]) < fp["half"][0] + pad) & (np.abs(L[:, 1]) < fp["half"][1] + pad) & \
        (np.abs(L[:, 2]) <= fp["gap"] / 2 + band_tol)
    if layer_mask is not None:
        lm = np.asarray(layer_mask)
        if lm.dtype != bool:
            b = np.zeros(len(L), bool); b[lm] = True; lm = b
        m &= lm
    return np.where(m)[0]


def bind(stage, verts, finger_prim, points, body_path, finger_pos, finger_R=None, scope=None, P=lambda *s: None):
    """把 verts 以目前相對位置剛性綁到 finger_prim(kinematic/動態剛體,body frame 不含 scale)。回傳 scope path 或 None。"""
    verts = np.asarray(verts, int)
    if len(verts) == 0:
        return None
    R = np.eye(3) if finger_R is None else np.asarray(finger_R, float)
    scope = scope or "/World/gatt_%d" % len(_SCOPES)
    loc = (np.asarray(points, float)[verts] - np.asarray(finger_pos, float)) @ R
    VC.attach_vtx(stage, scope, body_path, body_path, finger_prim, verts, loc, P=P)
    _SCOPES.append(scope)
    return scope


def release(stage, scope=None):
    """RemovePrim 綁定 scope(None = 本模組建立的全部)。"""
    todo = list(_SCOPES) if scope is None else [scope]
    for s in todo:
        if stage.GetPrimAtPath(s).IsValid():
            stage.RemovePrim(Sdf.Path(s))
        if s in _SCOPES:
            _SCOPES.remove(s)
    return todo
