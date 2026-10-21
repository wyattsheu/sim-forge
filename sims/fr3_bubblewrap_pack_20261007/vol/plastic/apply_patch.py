#!/usr/bin/env python3
"""把 [plastic] 改動裝進 wrap_vol.py(字串錨點替換,找不到就停)。先備份 wrap_vol.py.before_plastic。"""
import shutil, sys, os
F = "/isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/wrap_vol.py"
s = open(F).read()
if "[plastic]" in s:
    print("已裝過"); sys.exit(0)
if not os.path.exists(F + ".before_plastic"):
    shutil.copy(F, F + ".before_plastic")
def rep(old, new, cnt=1):
    global s
    n = s.count(old); assert n == cnt, (n, old[:80]); s = s.replace(old, new)
rep('ap.add_argument("--quality"', '''ap.add_argument("--plastic_on_release", type=int, default=0, help="[plastic] 1 = 第一隻手放手前 --plastic_pre 秒把 yn/yp 的 rest shape 改成當下形狀(寫 restShapePoints + SetActive 關→開 讓 PhysX 重建),模擬塑性;0 = 舊行為")
ap.add_argument("--plastic_on_fold", type=int, default=0, help="[plastic] 1 = 關蓋完成、放錨點之前把整張布 rest 改成當下(折好)形狀;0 = 舊行為")
ap.add_argument("--plastic_pre", type=float, default=0.2, help="[plastic] 放手前幾秒改 rest")
ap.add_argument("--plastic_region", choices=["all", "side"], default="all", help="[plastic] release 時改哪些頂點:all = 全片;side = 本片 + 鉸線內 30mm(其他頂點 rest 不變)")
ap.add_argument("--plastic_how", choices=["frame", "step"], default="frame", help="[plastic] SetActive(False)→(True) 在同一幀(frame)或中間多走一步(step)")
ap.add_argument("--release_watch", type=int, default=0, help="[plastic] 1 = 放手後 0.5/2/10 s 印 越線/壁外/自穿/穿杯/杯位移(--plastic_on_release 1 時自動開)")
ap.add_argument("--grasp_tail_s", type=float, default=0.0, help="[plastic] 抓取段結束後多觀察幾秒(取杯段之前);0 = 舊行為")
ap.add_argument("--quality"''')
rep("    T_END = TG0 + G_SHEET * len(G_SEQ)\n", "    T_END = TG0 + G_SHEET * len(G_SEQ) + a.grasp_tail_s                     # [plastic] grasp_tail_s 預設 0\n")
rep("writer = imageio.get_writer(", '''# ── [plastic] runtime 改 rest shape(模擬塑性):寫 restShapePoints → SetActive(False/True) 讓 PhysX 以新 rest 重建(points = 當下)
def _stvk(p, rest):
    Dm = np.stack([rest[TETS[:, i]] - rest[TETS[:, 0]] for i in (1, 2, 3)], 2)
    Ds = np.stack([p[TETS[:, i]] - p[TETS[:, 0]] for i in (1, 2, 3)], 2)
    F_ = Ds @ np.linalg.inv(Dm); E_ = 0.5 * (np.transpose(F_, (0, 2, 1)) @ F_ - np.eye(3)); tr_ = np.trace(E_, axis1=1, axis2=2)
    mu_ = a.young / (2 * (1 + a.poisson)); lam_ = a.young * a.poisson / ((1 + a.poisson) * (1 - 2 * a.poisson))
    return float((np.abs(np.linalg.det(Dm)) / 6 * (mu_ * (E_ * E_).sum((1, 2)) + 0.5 * lam_ * tr_ * tr_)).sum())
def plastic_bake(why, t, sel=None):
    assert not a.fast_pts, "[plastic] 重建 body 會讓 fast_pts 的 tensor view 失效"
    ra = PLATE.prim.GetAttribute("omniphysics:restShapePoints")
    cur = PLATE.pts(); old = np.array(ra.Get(), float).reshape(-1, 3); new = old.copy()
    if sel is None: new[:] = cur
    else: new[sel] = cur[sel]
    e0, e1 = _stvk(cur, old), _stvk(cur, new)
    ra.Set(Vt.Vec3fArray.FromNumpy(new.astype(np.float32)))
    PLATE.prim.SetActive(False)
    if a.plastic_how == "step": world.step(render=False)
    st.GetPrimAtPath("/World/plate").SetActive(True)
    PLATE.prim = st.GetPrimAtPath("/World/plate"); PLATE.tm = UsdGeom.TetMesh(PLATE.prim); PLATE.pa = PLATE.tm.GetPointsAttr()
    PLATE.pa.Set(Vt.Vec3fArray.FromNumpy(cur.astype(np.float32)))
    P("★ t=%.2f [plastic] %s:rest ← 當下形狀 %d 點(全片 %d)| 彈性能(StVK)改前 %.3e J → 改後 %.3e J | SetActive 重建(%s)"
      % (t, why, len(cur) if sel is None else int(np.sum(sel)), len(cur), e0, e1, a.plastic_how))
    return e0, e1
def plastic_watch(t):
    for pl in GS["plans"]:
        if "TR" not in pl or (a.hold_yp and pl["sd"] == "yp"): continue
        ev = pl["ev"]
        if a.plastic_on_release and "plastic" not in ev and pl.get("att", {}).get("on") and t >= pl["TR"] - a.plastic_pre - 1e-6:
            S_ = SIDES[pl["sd"]]
            sel = None if a.plastic_region == "all" else (S_["sg"] * FLAT[:, S_["ax"]] > S_["C"] - 0.030)
            ev["plastic"] = dict(t=t); plastic_bake("[%s] 放手前 %.2fs(%s)" % (pl["sd"], a.plastic_pre, a.plastic_region), t, sel)
        for k_s in (0.5, 2.0, 10.0):
            nm_ = "after%g" % k_s
            if nm_ not in ev and t >= pl["TR"] + k_s - 1e-6:
                ev[nm_] = dict(t=t); cr, cy, wo = h2_stat(pl); rm, Pw, _ = measure(t)
                Pl = Pw - g_offw(); m = GSIDE2 == pl["sd"]; ca = float((pl["sg"] * Pl[m, 1] > CY).mean()) * 100
                P("★ t=%.2f [%s] [plastic] 放手後 %gs:越線 %.0f%%(全片 %.0f%%)| 壁外 %.0f%% | 質心 y %.1f mm | 自穿 %d | 布穿杯 %d | 杯位移 %.1f mm"
                  % (t, pl["sd"], k_s, cr, ca, wo, cy, rm["pen"], rm["inmug"], float(np.linalg.norm(mug_world()[0] - pl["mug0"])) * 1e3))

writer = imageio.get_writer(''')
rep('''            st.RemovePrim(Sdf.Path("/World/attach"))
            kin.Set(False)''', '''            if a.plastic_on_fold: plastic_bake("關蓋完成、放錨點前(全片)", tcur)   # [plastic]
            st.RemovePrim(Sdf.Path("/World/attach"))
            kin.Set(False)''')
rep('''        if a.grasp and tcur >= TG0 - 1e-9:
            g_events(tcur); g_drive(tcur)
''', '''        if a.grasp and tcur >= TG0 - 1e-9:
            g_events(tcur); g_drive(tcur)
            if a.plastic_on_release or a.release_watch: plastic_watch(tcur)   # [plastic]
''')
open(F, "w").write(s)
print("OK")
