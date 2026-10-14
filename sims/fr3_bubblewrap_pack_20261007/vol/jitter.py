#!/usr/bin/env python3
"""jitter.py — 從 wrap.npz(traj_t / traj_tet)量布的顫抖。

    python3 jitter.py out/wrap.npz [--win 3.5:4,7:7.5,10.5:11,14:14.5] [--rest 17.0:18.1]
    python3 jitter.py --selftest

每格 d_k = RMS_i |P_k,i - P_k-1,i|  (mm,換成 mm/格 不除 dt;並另印 mm/s)
hf_k  = RMS_i |P_k - 2P_k-1 + P_k-2| (二階差分,扣掉緩慢漂移,較純的抖動)
win  = 各折到位後停留段(預設 fold_span 3 / hold 0.5 / 開始 0.5s 的四段)
rest = 四折+收耳完成後靜置段
"""
import argparse, sys
import numpy as np


def frame_rms(P):
    d = np.diff(P, axis=0)
    return np.sqrt((d ** 2).sum(-1).mean(-1)) * 1e3


def hf_rms(P):
    d2 = P[2:] - 2 * P[1:-1] + P[:-2]
    return np.sqrt((d2 ** 2).sum(-1).mean(-1)) * 1e3


def parse_wins(s):
    return [tuple(float(x) for x in w.split(":")) for w in s.split(",") if w]


def measure(t, P, wins):
    d = frame_rms(P); h = hf_rms(P)
    td = t[1:]; th = t[2:]; dt = np.median(np.diff(t))
    out = []
    for a, b in wins:
        m = (td > a + 1e-6) & (td <= b + 1e-6); mh = (th > a + 1e-6) & (th <= b + 1e-6)
        out.append(dict(win=(a, b), n=int(m.sum()), rms=float(d[m].mean()) if m.any() else np.nan,
                        hf=float(h[mh].mean()) if mh.any() else np.nan))
    return out, dt


def summarize(path, wins, rest):
    z = np.load(path); t = z["traj_t"]; P = z["traj_tet"].astype(np.float64)
    hold, dt = measure(t, P, wins); rr, _ = measure(t, P, [rest])
    hm = np.nanmean([w["rms"] for w in hold]); hh = np.nanmean([w["hf"] for w in hold])
    return dict(dt=dt, hold=hold, hold_rms=hm, hold_hf=hh, rest=rr[0])


def selftest():
    rng = np.random.default_rng(0); t = np.arange(0, 2, 1 / 30.)
    base = rng.random((500, 3))
    still = np.repeat(base[None], len(t), 0)
    _, = [summarize_arr(t, still)]
    assert _ < 1e-9, _
    amp = 1e-3  # 1 mm 正弦抖動(每格交替 ±1mm)
    sh = still + (amp * (-1.0) ** np.arange(len(t)))[:, None, None] * np.array([0, 0, 1.0])
    j = summarize_arr(t, sh); assert abs(j - 2.0) < 1e-6, j          # 交替 ±1mm → 每格位移 2mm
    drift = still + (1e-3 * np.arange(len(t)))[:, None, None] * np.array([1.0, 0, 0])
    assert abs(summarize_arr(t, drift) - 1.0) < 1e-6
    assert hf_rms(drift).max() < 1e-6 and hf_rms(sh).min() > 3.9   # 二階差分:漂移 0、抖動 4mm
    print("selftest PASS"); return 0


def summarize_arr(t, P):
    out, _ = measure(t, P, [(0.5, 1.5)]); return out[0]["rms"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("npz", nargs="?")
    ap.add_argument("--win", default="3.5:4,7:7.5,10.5:11,14:14.5")
    ap.add_argument("--rest", default="17.0:18.1")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: sys.exit(selftest())
    s = summarize(a.npz, parse_wins(a.win), parse_wins(a.rest)[0])
    print("%s  取樣 %.4fs" % (a.npz, s["dt"]))
    for w in s["hold"]:
        print("  停留 %5.2f~%5.2f n=%2d  RMS %.3f mm/格  hf %.3f" % (*w["win"], w["n"], w["rms"], w["hf"]))
    r = s["rest"]
    print("  停留平均 RMS %.3f mm/格 (%.1f mm/s) hf %.3f | 靜置 %.2f~%.2f RMS %.3f hf %.3f"
          % (s["hold_rms"], s["hold_rms"] / s["dt"], s["hold_hf"], *r["win"], r["rms"], r["hf"]))
