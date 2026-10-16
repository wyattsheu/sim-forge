#!/usr/bin/env python3
"""carton_sweep.py — 蓋子會不會穿箱壁?純 CPU 解析掃掠,不用 Isaac、不用 GPU。

用法:
    python3 carton_sweep.py carton_w131.meta.json

原理:紙箱的幾何全部寫在 meta.json 的 derived 裡。把蓋子繞它的鉸鏈從
0°(關)掃到 180°(全開),每 0.5° 取一次,算蓋子的板(2t 厚)有沒有落在箱壁的板帶裡。

為什麼需要這支:
  2026-09-26 實測,鉸鏈放在箱壁**內面**、蓋子又是 2t 厚的板 ⇒ 蓋子一旦傾斜,
  它的外上角就掃進箱壁那 2t 的帶子,而且此時還在箱口以下。舊紙箱 360/361 個角度都重疊,
  最深 1.50mm = 剛好半個板厚。修法是把該面箱壁降到「鉸鏈 z − 2t」。

★ 一定要看自檢那幾行。 第一版我把旋轉方向寫反(算成蓋子往下垂進箱子),
  得到完全錯誤的結論還回報出去了。自檢印的是 θ=0/90/180 時蓋尖的 (x, z):
  正確的應該是 θ=0 在箱內、θ=90 直立朝上、θ=180 水平朝外。
"""
import numpy as np, json, sys

if len(sys.argv) < 2:
    sys.exit(__doc__)
d = json.load(open(sys.argv[1]))
I, D = d["inputs"], d["derived"]
hx, hy, t = I["hx"], I["hy"], I["t"]
H = I["height"]
WTX = D.get("wall_top_x", H)          # 舊 meta 沒有這兩欄 → 退回 height
WTY = D.get("wall_top_y", H)
ZIN, ZOUT = D["lower_hinge_z"], D["upper_hinge_z"]
P = lambda *s: print(*s, flush=True)


def sweep(hinge_a, hinge_z, reach, wa0, wa1, wall_top):
    """蓋子繞 (hinge_a, hinge_z) 的鉸鏈線轉,和箱壁板帶 [wa0, wa1] x [0, wall_top] 取交集。

    蓋子局部:沿蓋長 ax = -d(關的時候朝箱內)、厚度 az = t+s(關的時候朝上)
    開蓋 = 往上翻出去:
        A = hinge_a + ax*cos + az*sin
        Z = hinge_z - ax*sin + az*cos        (ax=-d ⇒ Z = hinge_z + d*sin,往上 ✓)
    """
    th = np.arange(0, 180.5, 0.5)
    dd = np.linspace(0, reach, 300)
    ss = np.array([-t, 0.0, t])
    n, deep, angs = 0, 0.0, []
    for T in th:
        c, s0 = np.cos(np.radians(T)), np.sin(np.radians(T))
        ax = -dd[:, None] + 0*ss[None, :]
        az = (t + ss)[None, :] + 0*dd[:, None]
        A = hinge_a + ax*c + az*s0
        Z = hinge_z - ax*s0 + az*c
        m = (A > wa0) & (A < wa1) & (Z > 0) & (Z < wall_top)
        if m.any():
            n += 1
            angs.append(T)
            deep = max(deep, float(np.minimum(A[m] - wa0, wa1 - A[m]).max()*1e3))
    return n, deep, ((angs[0], angs[-1]) if angs else None)


P("%s" % sys.argv[1].split("/")[-1])
P("  板厚 %.0f mm(半厚 t=%.1f);箱高參數 %.1f" % (2*t*1e3, t*1e3, H*1e3))
P("  ±x 牆頂 %.1f mm / ±y 牆頂 %.1f mm" % (WTX*1e3, WTY*1e3))
P("  下鉸鏈 %.1f / 上鉸鏈 %.1f mm" % (ZIN*1e3, ZOUT*1e3))

P("\n  自檢(旋轉方向對不對)—— 下蓋蓋尖的 (x, z):")
for T in (0, 90, 180):
    c, s0 = np.cos(np.radians(T)), np.sin(np.radians(T))
    A = D["wall_inner_x"] - D["reach_x"]*c + t*s0
    Z = ZIN + D["reach_x"]*s0 + t*c
    P("     θ=%3d°  (%7.1f, %7.1f) mm" % (T, A*1e3, Z*1e3))
P("     應為:θ=0 在箱內、θ=90 直立朝上(z 最大)、θ=180 水平朝外(x 最大)")

bad = 0
P("")
for nm, ha, hz, reach, wa0, wa1, wtop in [
        ("下蓋 fxp vs ±x 牆", D["wall_inner_x"], ZIN, D["reach_x"],
         D["wall_inner_x"], hx + t, WTX),
        ("上蓋 fyp vs ±y 牆", D["wall_inner_y"], ZOUT, D["reach_y"],
         D["wall_inner_y"], hy + t, WTY)]:
    n, dp, rng = sweep(ha, hz, reach, wa0, wa1, wtop)
    bad += n
    P("  %s:%3d/361 個角度重疊,最深 %.2f mm%s%s"
      % (nm, n, dp,
         "" if rng is None else "  (角度 %.0f~%.0f°)" % rng,
         "   ← 0 重疊 ✅" if n == 0 else "   ✗"))

P("\n  ⇒ %s" % ("全部 0 重疊 ✅" if bad == 0 else
                "還有 %d 個角度重疊 ✗ —— 牆頂要降到「該面蓋子的鉸鏈 z − 2t」" % bad))
