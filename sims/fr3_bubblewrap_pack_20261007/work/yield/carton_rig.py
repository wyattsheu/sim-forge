#!/usr/bin/env python3
"""carton_rig.py — 紙箱量測的共用機制。今天(2026-07-30)所有的修正都收在這裡。

為什麼要這個模組:七支腳本各自有一份 ang()/step()/settle()/方向校正/擷取路徑,
所以每個修正只會改到當下在動的那一支 —— 實測漏過兩次:
  渲染污染 修了 shot.py 和 torque_demo.py,漏了 demo_open_B.py
  角度符號 修了 probe_max.py,漏了 stair_open.py 和 qa_carton.py
機制只能有一個來源。(跟 para+function 同一個原則:幾何有兩個來源就會不同步。)

收進來的修正
  1 摺線力矩必須施加在「每一個物理步」上
  2 物理步一律 render=False;畫面用 world.render()(只渲染,不推進物理)
    —— world.step(render=True) 會一次推進約 8 個物理步而力矩只施加一次
  3 開啟角要帶符號(掀開為正、往箱內為負);用 abs() 會讓「往下折 65 度」
    被讀成「已經開了 65 度」
  4 角度以「靜置後」為零點,不是生成姿態(生成帶 ajar 會被讀成下垂)
  5 準靜態:只有角速度夠小才把力矩往上加
  6 上限是「力的上限」:力矩上限 = 手臂力 × 力臂(力臂從 sidecar 讀)
  7 幾何從 sidecar 讀,不重算公式
  8 峰值要在「達標那一刻」抓,不是迴圈結束後
  9 幾何交叉驗證:垂 θ 度 → 自由邊該比摺線低 L·sin(θ)
"""
import os, math, json, csv
import numpy as np
from pxr import UsdGeom, UsdPhysics, Gf, UsdLux, Usd
import omni.usd

UPPER = ["fyp", "fyn"]
LOWER = ["fxp", "fxn"]
ALL   = LOWER + UPPER
TUNES = {"v2":   dict(k=3.2, my0=0.60, h=0.85, c=0.33, clip=3.0),   # OPENER_RULES 標明的定版
         "hold145": dict(k=3.2, my0=0.05, h=0.575, c=0.33, clip=3.0),  # 2026-09-24 目標:壓180 保持>=145
         "file": dict(k=3.5, my0=0.85, h=0.55, c=0.28, clip=3.6)}   # crease_physics.py 的檔案預設


class Rig:
    def __init__(self, world, carton_usd, tune="v2", force_cap_N=30.0,
                 table_h=0.30, cpath="/World/Carton", quiet=0.05, qhold=40,
                 cam_res=(1180, 800), log=print):
        import torch
        from isaacsim.core.prims import RigidPrim
        from isaacsim.sensors.camera import Camera
        self.torch = torch
        self.world, self.P = world, log
        self.CP, self.TH = cpath, table_h
        self.QUIET, self.QHOLD = quiet, qhold
        self.stage = omni.usd.get_context().get_stage()

        self.T = TUNES[tune]; self.tune_name = tune
        self.YIELD_DEG = math.degrees(self.T["my0"] / self.T["k"])
        self.FORCE_CAP = force_cap_N

        # ---- 場景
        world.scene.add_default_ground_plane()
        UsdLux.DomeLight.Define(self.stage, "/World/dome").CreateIntensityAttr(1000.0)
        kl = UsdLux.DistantLight.Define(self.stage, "/World/kl"); kl.CreateIntensityAttr(2200.0)
        UsdGeom.Xformable(kl.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-45, 20, 0))
        cx = UsdGeom.Xform.Define(self.stage, cpath)
        cx.GetPrim().GetReferences().AddReference(carton_usd)
        cx.AddTranslateOp().Set(Gf.Vec3d(0, 0, table_h))
        tb = UsdGeom.Cube.Define(self.stage, "/World/table"); tb.CreateSizeAttr(2.0)
        xf = UsdGeom.Xformable(tb.GetPrim())
        xf.AddTranslateOp().Set(Gf.Vec3d(0, 0, table_h/2))
        xf.AddScaleOp().Set(Gf.Vec3f(0.30, 0.30, table_h/2))
        tb.CreateDisplayColorAttr([Gf.Vec3f(0.34, 0.36, 0.40)])
        UsdPhysics.CollisionAPI.Apply(tb.GetPrim())

        # ---- 修正 7:幾何從 sidecar 讀
        self.META = {}
        mp = carton_usd.rsplit(".", 1)[0] + ".meta.json"
        if os.path.exists(mp):
            self.META = json.load(open(mp))
            self.P("sidecar %s (builder %s)" % (mp, self.META.get("builder_version")))
        else:
            self.P("⚠ 沒有 sidecar %s —— 力臂等衍生量改用預設" % mp)
        d = self.META.get("derived", {})
        self.LA = {"upper": d.get("reach_y", 0.167), "lower": d.get("reach_x", 0.167)}
        # 修正 6:上限是力的上限
        self.TAU_CAP = {k: force_cap_N * v for k, v in self.LA.items()}
        self.WALL_TOP = d.get("wall_top_z")
        self.HINGE_Z = {"upper": d.get("upper_hinge_z"), "lower": d.get("lower_hinge_z")}

        self.cam = Camera(prim_path="/World/cam",
                          position=np.array([1.0, -1.0, table_h + 0.5]), resolution=cam_res)
        self.cam.set_focal_length(3.0); self.cam.initialize()
        world.reset()

        self.VIEW = RigidPrim(prim_paths_expr=cpath + "/f(xp|xn|yp|yn)")
        try: self.VIEW.initialize()
        except Exception as e: self.P("view init:", type(e).__name__, str(e)[:70])
        order = list(getattr(self.VIEW, "prim_paths", []))
        self.FLAPS = [p.rsplit("/", 1)[-1] for p in order]
        self.IDX = {f: i for i, f in enumerate(self.FLAPS)}
        self.PEND = np.zeros((max(len(order), 1), 3), dtype=np.float32)
        self.PUSH = {f: 0.0 for f in self.FLAPS}
        self._bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render", "guide"])

        from crease_physics import ElastoplasticCrease
        self.crease = ElastoplasticCrease(len(self.FLAPS), "cpu", **self.T)
        self._Y0 = {f: self.yax(f) for f in self.FLAPS}
        self.REST0 = None; self.DOWN = {}
        self._ang_prev = {}; self._ang_turn = {}      # unwrap 用
        # ★ 靜置判準改看「淨角度變化」:蓋子壓在硬止檔上會高頻抖動,
        #   角速度永遠不會小(實測 0.26 rad/s),但淨位移是零 → 用角速度判永遠不會靜置。
        #   視窗內的 max-min 對抖動免疫(實測抖動振幅 < 0.01 度)。
        from collections import deque
        self.MAX_DEG = 260.0      # 角度保護上限(使用者 2026-07-31)
        self.STALL_TAU = 1.20     # 靠住:比上次推進時多加這麼多 N*m 還不動
        self.STALL_DEG = 0.20     # 「有推進」的門檻(度)
        self.WIN = 120          # 0.5 秒
        self.ANG_EPS = 0.05     # 度:視窗內變化小於這個就算靜置
        self._win = {f: deque(maxlen=self.WIN) for f in self.FLAPS}
        self.frames = []; self.rows = []; self.fmeta = []
        self.phase = "init"
        self.P("tune=%s k=%.2f My0=%.2f H=%.2f clip=%.1f | 降伏角 My0/k = %.2f 度(與軟硬倍率無關)"
               % (tune, self.T["k"], self.T["my0"], self.T["h"], self.T["clip"], self.YIELD_DEG))
        self.P("力上限 %.1f N;力臂 上層 %.4f 下層 %.4f m -> 力矩上限 %.3f / %.3f N*m"
               % (force_cap_N, self.LA["upper"], self.LA["lower"],
                  self.TAU_CAP["upper"], self.TAU_CAP["lower"]))

    # ---------- 幾何/角度 ----------
    def _m(self, nm):
        return UsdGeom.Xformable(self.stage.GetPrimAtPath(self.CP + "/" + nm)) \
            .ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    def yax(self, nm):
        m = self._m(nm); v = np.array([m[1][0], m[1][1], m[1][2]], float)
        return v / max(1e-9, np.linalg.norm(v))
    def hax(self, nm):
        m = self._m(nm); v = np.array([m[0][0], m[0][1], m[0][2]], float)
        return v / max(1e-9, np.linalg.norm(v))
    def ang_raw(self, nm):
        """atan2 的主值,值域 ±180"""
        y0 = self._Y0.get(nm)
        if y0 is None: return 0.0
        yv, ax = self.yax(nm), self.hax(nm)
        return math.degrees(math.atan2(float(np.dot(np.cross(y0, yv), ax)), float(np.dot(y0, yv))))

    def ang(self, nm):
        """★ 連續累積的轉角(unwrap)。
        atan2 值域只有 ±180 —— 蓋子一轉過 180 度就翻成負的
        (實測拿掉關節極限後,停在 207 度卻讀成 −152.81)。
        真實紙箱打開時蓋子垂在箱外約 270 度,所以一定要 unwrap。
        做法:每次取樣跟上次比,跳超過 180 度就補一圈。"""
        raw = self.ang_raw(nm)
        prev = self._ang_prev.get(nm)
        if prev is None:
            self._ang_prev[nm] = raw; self._ang_turn[nm] = 0.0
            return raw
        d = raw - prev
        if   d >  180.0: self._ang_turn[nm] -= 360.0
        elif d < -180.0: self._ang_turn[nm] += 360.0
        self._ang_prev[nm] = raw
        return raw + self._ang_turn[nm]
    def tilt(self, nm):
        """對水平的傾角。修正 4:報告一律用這個,不要用對生成姿態的"""
        return math.degrees(math.asin(max(-1.0, min(1.0, float(self.yax(nm)[2])))))
    def sopen(self, nm):
        """★ 修正 3+4:帶符號的開啟角,以靜置後為零點。掀開為正、往箱內為負"""
        if self.REST0 is None or nm not in self.DOWN: return 0.0
        return (self.ang(nm) - self.REST0[nm]) * (-self.DOWN[nm])
    def rates(self):
        try: w = np.asarray(self.VIEW.get_angular_velocities())
        except Exception: return {f: 0.0 for f in self.FLAPS}
        return {f: (float(np.dot(w[self.IDX[f]], self.hax(f))) if w is not None else 0.0)
                for f in self.FLAPS}
    def wbox(self, path):
        self._bb.Clear()
        r = self._bb.ComputeWorldBound(self.stage.GetPrimAtPath(path)).ComputeAlignedRange()
        return np.array([[r.GetMin()[i], r.GetMax()[i]] for i in range(3)])
    def cz(self, nm):
        b = self.wbox(self.CP + "/" + nm); return 0.5 * (b[2][0] + b[2][1])

    def penetration(self, nm):
        """★ 穿牆檢查:蓋子的板身 vs 四面箱壁的重疊。
        用軸對齊 bbox 的重疊當篩檢 —— **保守**:重疊為 0 就確定沒穿牆;
        重疊非 0 只代表「不排除」(旋轉後的板子 AABB 可能相交而實體沒碰)。
        回傳 (最大插入深度 mm, 最糟的那面牆, 三軸重疊 mm)。
        排除「鉸接的那面牆」在 0.5mm 以內的貼合 —— 摺線本來就在牆體裡。"""
        # ★ 用「重疊深度」不是體積:薄薄 1.4 微米 × 332×167mm 的面積 = 75.7 mm^3,
        #   看起來像穿牆,其實是鉸接處貼著(構造使然)。深度才有鑑別力。
        fb = self.wbox(self.CP + "/" + nm + "/geo")
        hinge_wall = {"fxp": "wxp", "fxn": "wxn", "fyp": "wyp", "fyn": "wyn"}.get(nm)
        worst = (0.0, None, None)
        for w in ("wxp", "wxn", "wyp", "wyn"):
            pth = self.CP + "/base/" + w
            if not self.stage.GetPrimAtPath(pth).IsValid(): continue
            wb = self.wbox(pth)
            ov = np.array([min(fb[i][1], wb[i][1]) - max(fb[i][0], wb[i][0]) for i in range(3)])
            if np.any(ov <= 0): continue                       # 任一軸不重疊 = 沒交集
            depth_mm = float(np.min(ov)) * 1000.0              # 最小軸就是插入深度
            if w == hinge_wall and depth_mm < 0.5: continue    # 鉸接處貼合,不算穿牆
            if depth_mm > worst[0]: worst = (depth_mm, w, ov * 1000.0)
        return worst

    def blockers(self, nm):
        """★ 擋住這片蓋的是誰?(2026-07-31 補)
        penetration() 只查「蓋 vs 四面箱壁」,所以它說「與箱壁無交集」時,
        真正的阻擋者可能是**另一片蓋** —— 這個洞害我把下層卡住當成無解。
        這裡把四面牆 + 另外三片蓋一起查,回傳 [(對象, 插入深度mm, 三軸重疊mm), ...]。
        一樣是 AABB 保守篩檢:0 就確定沒碰,非 0 只代表不排除。"""
        fb = self.wbox(self.CP + "/" + nm + "/geo")
        hinge_wall = {"fxp": "wxp", "fxn": "wxn", "fyp": "wyp", "fyn": "wyn"}.get(nm)
        out = []
        cand = [("base/" + w, w) for w in ("wxp", "wxn", "wyp", "wyn")]
        cand += [(f + "/geo", f) for f in self.FLAPS if f != nm]
        for pth, lab in cand:
            prim = self.stage.GetPrimAtPath(self.CP + "/" + pth)
            if not prim.IsValid(): continue
            wb = self.wbox(self.CP + "/" + pth)
            if wb is None: continue
            ov = np.array([min(fb[i][1], wb[i][1]) - max(fb[i][0], wb[i][0]) for i in range(3)])
            if np.any(ov <= 0): continue
            d = float(np.min(ov)) * 1000.0
            if lab == hinge_wall and d < 0.5: continue      # 摺線本來就在牆體裡
            out.append((lab, d, ov * 1000.0))
        out.sort(key=lambda t: -t[1])
        return out

    def why_stuck(self, flaps):
        """把 blockers 印成人看得懂的一行"""
        for f in flaps:
            bl = self.blockers(f)
            if not bl:
                self.P("        %s:四面箱壁與其他三片蓋都無交集 -> 不是被幾何擋的" % f); continue
            for lab, d, ov in bl[:3]:
                kind = "另一片蓋" if lab in self.FLAPS else "箱壁"
                self.P("        %s 撞到 %s %s:插入 %.4f mm  三軸 [%.2f %.2f %.2f]"
                       % (f, kind, lab, d, ov[0], ov[1], ov[2]))

    def cross_check(self, nm):
        """修正 9:垂 θ 度 → 自由邊該比摺線低 L·sin(θ)。對不上就是指標錯了"""
        b = self.wbox(self.CP + "/" + nm + "/geo")
        hz = float(self._m(nm)[3][2])
        L = self.LA["upper" if nm in UPPER else "lower"]
        meas = (hz - b[2][0]) * 1000.0
        pred = L * math.sin(math.radians(abs(self.tilt(nm)))) * 1000.0
        return meas, pred, abs(meas - pred)

    # ---------- 推進 ----------
    def step(self, n=1, cap_every=0):
        """修正 1+2:摺線力矩施加在每一個物理步;物理步一律 render=False"""
        tt = self.torch
        for i in range(n):
            angs = {f: self.ang(f) for f in self.FLAPS}     # ★ 一步只算一次(原本一步算十幾次)
            qv = tt.tensor([math.radians(angs[f]) for f in self.FLAPS], dtype=tt.float32)
            w = self.rates()
            qd = tt.tensor([w[f] for f in self.FLAPS], dtype=tt.float32)
            tau = self.crease.step(qv, qd)
            self.PEND[:] = 0.0
            for j, f in enumerate(self.FLAPS):
                self.PEND[self.IDX[f]] = self.hax(f) * (float(tau[j]) + self.PUSH[f])
            self.VIEW.apply_forces_and_torques_at_pos(torques=self.PEND.copy(), is_global=True)
            self.world.step(render=False)
            for f in self.FLAPS: self._win[f].append(self.ang(f))
            pen = max((self.penetration(f)[0] for f in self.FLAPS), default=0.0) \
                  if (len(self.rows) % 25 == 0) else -1.0    # 插入深度 mm
            self.rows.append([self.phase, pen]
                             + [self.sopen(f) for f in self.FLAPS]
                             + [self.tilt(f) for f in self.FLAPS]
                             + [self.PUSH[f] for f in self.FLAPS]
                             + [float(tau[j]) for j in range(len(self.FLAPS))])
            if cap_every and (i % cap_every == 0): self.grab()

    def grab(self):
        """修正 2:只渲染,不推進物理"""
        for _ in range(2):
            try: self.world.render()
            except Exception:
                import omni.kit.app; omni.kit.app.get_app().update()
        im = np.asarray(self.cam.get_rgba())
        if im.ndim == 3 and im.shape[2] >= 3 and im[:, :, :3].sum() > 0:
            self.frames.append(im[:, :, :3].astype(np.uint8))
            # 每一幀都記下當下的數值 —— 合成影片時疊字用,也是「畫面與數字同源」的保證
            self.fmeta.append(dict(frame=len(self.frames) - 1, phase=self.phase,
                                   step=len(self.rows),
                                   sopen={f: round(self.sopen(f), 3) for f in self.FLAPS},
                                   push={f: round(self.PUSH[f], 4) for f in self.FLAPS},
                                   tilt={f: round(self.tilt(f), 3) for f in self.FLAPS}))

    def is_quiet(self, flaps=None):
        """★ 靜置 = 視窗內的淨角度變化夠小。對「壓著止檔高頻抖動」免疫。
        角速度只留著當診斷,不當判準。"""
        for f in (flaps or self.FLAPS):
            w = self._win[f]
            if len(w) < self.WIN: return False
            if (max(w) - min(w)) > self.ANG_EPS: return False
        return True

    def spread(self, flaps=None):
        """視窗內的角度變化量(度)——診斷用"""
        vals = []
        for f in (flaps or self.FLAPS):
            w = self._win[f]
            vals.append((max(w) - min(w)) if len(w) == self.WIN else 999.0)
        return max(vals) if vals else 0.0

    def settle(self, phase=None, maxs=6000, cap_every=10):
        """修正 5:準靜態的基礎 —— 等到角速度連續夠小。
        ★ 超時要說出殘留角速度是多少,不要靜靜回 False(否則呼叫端不知道差多遠)"""
        if phase: self.phase = phase
        for i in range(maxs):
            self.step(1, cap_every=0)
            if cap_every and i % cap_every == 0: self.grab()
            if self.is_quiet(): return True
        self.P("      ⚠ settle 超時(%d 步):視窗內角度變化 %.4f 度(門檻 %.3f);"
               "殘留角速度 %.4f rad/s(只供參考)"
               % (maxs, self.spread(), self.ANG_EPS,
                  max(abs(self.rates()[f]) for f in self.FLAPS)))
        return False

    def calibrate_dir(self, flaps=None):
        """實測「往箱內」是哪個力矩方向 —— 上下層擺放旋轉差 90 度,同號是相反的物理方向"""
        self.settle("calib")
        self.REST0 = {f: self.ang(f) for f in self.FLAPS}
        for f in (flaps or self.FLAPS):
            z0 = self.cz(f); self.PUSH[f] = +0.30; self.step(200); z1 = self.cz(f)
            self.PUSH[f] = 0.0; self.settle("calib")
            self.DOWN[f] = -1.0 if (z1 - z0) > 0 else +1.0
            self.P("  %s: +0.30 N*m 重心 z %+.4f -> 往箱內 = %s"
                   % (f, z1 - z0, "負向" if self.DOWN[f] < 0 else "正向"))
        self.REST0 = {f: self.ang(f) for f in self.FLAPS}   # 校正後重新取零點

    def ramp_to(self, flaps, target_deg, phase, layer, tau_step=0.003,
                stall_hits=6, maxs=40000):
        """準靜態把力矩加到目標角或上限。回傳 (峰值角, 峰值力矩, 是否撞力上限, 是否靠住)
        修正 8:峰值在達標那一刻回傳,呼叫端不要在放鬆之後才量"""
        self.phase = phase
        cap = self.TAU_CAP[layer]; L = self.LA[layer]
        # ★ 角度保護上限(使用者 2026-07-31):最高抓 260 度,不再花時間去逼近真正的止點。
        #   探測已知止點在箱壁外側(~270 度),260 是留餘裕的保護值,不是物理極限。
        target_deg = min(target_deg, self.MAX_DEG)
        tau = 0.0; prev = min(self.sopen(f) for f in flaps); capped = False
        # ★ 停滯判準以「力矩」為尺,不是以「步數」為尺(2026-07-31 修)。
        #   舊版:每 30 步檢查,連續 6 次角度沒動 -> 靠住。在**彈性加載階段**本來就不動,
        #   於是在 0.723 N*m(力上限的 14%)就誤判靠住,而且診斷顯示與四面箱壁皆無交集。
        #   新版:記住「上次真的有進展」時的力矩,之後再加了 STALL_TAU 還推不動才算靠住。
        ang_prog = prev; tau_prog = 0.0
        # ★ 診斷 + 門檻 fallback(使用者授權 2026-07-30):
        #   如果「等靜置」一直不成立,力矩就永遠加不上去 → 力矩停在 0.000(踩過三次)。
        #   先印出實際的殘留角速度(才知道差多遠),再改用寬鬆門檻讓它走。
        noq = 0; relaxed = None; diag_n = 0; cap_flat = 0
        for s in range(maxs):
            sp = self.spread(flaps)
            thr = relaxed if relaxed is not None else self.ANG_EPS
            quiet = sp < thr
            cur = min(self.sopen(f) for f in flaps)
            if cur >= target_deg: break
            if not quiet:
                noq += 1
                if noq % 600 == 0 and diag_n < 4:      # 每 600 步報一次,最多四次
                    diag_n += 1
                    self.P("      DIAG 卡在等靜置 %d 步:角 %.2f 度  力矩 %.3f  "
                           "視窗角度變化 %.4f 度  門檻 %.3f  (角速度 %.3f rad/s 僅參考)"
                           % (noq, cur, tau, sp, thr,
                              max(abs(self.rates()[f]) for f in flaps)))
                if noq >= 1500 and relaxed is None:
                    relaxed = max(self.ANG_EPS, sp * 1.5)
                    self.P("      ★ 靜置門檻達不到 → 放寬到 %.4f 度(原 %.3f)並繼續加力矩"
                           % (relaxed, self.ANG_EPS))
            else:
                noq = 0
            if quiet:
                if tau < cap: tau += tau_step
                elif not capped:
                    capped = True
                    self.P("      ★ 已到力的上限 %.1f N(力矩 %.3f N*m)" % (tau / L, tau))
            for f in flaps: self.PUSH[f] = -self.DOWN[f] * tau
            self.step(1, cap_every=0)
            if s % 20 == 0: self.grab()
            if quiet and s % 30 == 0:
                if cur - ang_prog > self.STALL_DEG:          # 真的推進了 -> 重設基準
                    ang_prog = cur; tau_prog = tau; cap_flat = 0
                elif capped:
                    # ★ 2026-09-29 修:靠住判準用「力矩增量」當尺,但力矩撞到上限之後
                    #   就不再增加,tau - tau_prog 凍結 → 那個 return 永遠不會觸發,
                    #   只能跑滿 maxs。實測上蓋 CYCLE 4 因此燒掉 250000 步(全程的 53%)。
                    #   撞頂之後力矩已經不能再加,唯一要問的是角度還有沒有在爬 ——
                    #   改用「連續 stall_hits 次檢查都沒進展」當判準。
                    cap_flat += 1
                    if cap_flat >= stall_hits:
                        self.P("      ★ 已在力上限 %.3f N*m 且連續 %d 次無進展(%.2f 度)-> 停止加壓"
                               % (tau, stall_hits, cur))
                        self.why_stuck(flaps)
                        return cur, tau, capped, True
                elif tau - tau_prog >= self.STALL_TAU:        # 多加了這麼多力矩仍不動 = 靠住
                    self.P("      靠住於 %.2f 度 @ %.3f N*m(比上次推進時多加了 %.3f N*m,目標 %.1f)"
                           % (cur, tau, tau - tau_prog, target_deg))
                    self.why_stuck(flaps)                 # ★ 擋住它的是誰 —— 量出來,不要猜
                    return cur, tau, capped, True
        if relaxed is not None:
            self.P("      (本循環用了放寬門檻 %.4f 度)" % relaxed)
        return min(self.sopen(f) for f in flaps), tau, capped, False

    def release(self, flaps, phase):
        """放力並等靜置,回傳保持角"""
        for f in flaps: self.PUSH[f] = 0.0
        self.settle(phase)
        return {f: self.sopen(f) for f in flaps}

    def look(self, el, az, fill=0.42):
        import isaacsim.core.utils.numpy.rotations as rot
        self._bb.Clear()
        r = self._bb.ComputeWorldBound(self.stage.GetPrimAtPath(self.CP)).ComputeAlignedRange()
        c = np.array([(r.GetMin()[i] + r.GetMax()[i]) / 2.0 for i in range(3)])
        R = 0.5 * math.sqrt(sum((r.GetMax()[i] - r.GetMin()[i]) ** 2 for i in range(3)))
        hf = min(math.atan(self.cam.get_horizontal_aperture() / 2 / self.cam.get_focal_length()),
                 math.atan(self.cam.get_vertical_aperture() / 2 / self.cam.get_focal_length()))
        d = R / (fill * math.tan(hf))
        e, a = math.radians(el), math.radians(az)
        eye = c + d * np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        fv = c - eye; fv /= np.linalg.norm(fv)
        self.cam.set_world_pose(eye, rot.euler_angles_to_quats(
            np.array([0, math.degrees(math.asin(-fv[2])), math.degrees(math.atan2(fv[1], fv[0]))]),
            degrees=True))

    # ---------- 輸出 ----------
    def save(self, outdir, name="run"):
        os.makedirs(outdir, exist_ok=True)
        hdr = (["phase", "pen_mm3"] + ["sopen_" + f for f in self.FLAPS] + ["tilt_" + f for f in self.FLAPS]
               + ["push_" + f for f in self.FLAPS] + ["tau_" + f for f in self.FLAPS])
        with open(os.path.join(outdir, name + "_steps.csv"), "w", newline="") as fp:
            w = csv.writer(fp); w.writerow(hdr); w.writerows(self.rows)
        self.P("WROTE %s_steps.csv rows=%d" % (name, len(self.rows)))
        json.dump(dict(flaps=self.FLAPS, tune=self.tune_name, tune_params=self.T,
                       yield_deg=self.YIELD_DEG, force_cap_N=self.FORCE_CAP,
                       lever_arm=self.LA, tau_cap=self.TAU_CAP, frames=self.fmeta),
                  open(os.path.join(outdir, name + "_frames.json"), "w"),
                  indent=1, ensure_ascii=False)
        self.P("WROTE %s_frames.json frames=%d" % (name, len(self.fmeta)))
        if self.frames:
            import imageio.v2 as imageio
            p = os.path.join(outdir, name + "_raw.mp4")
            try:
                imageio.mimwrite(p, self.frames, fps=30, quality=7, macro_block_size=1)
                self.P("WROTE %s_raw.mp4 frames=%d  (3D 原始,交給 compose 疊圖表)"
                       % (name, len(self.frames)))
            except Exception as e:
                self.P("mp4 失敗:", type(e).__name__, str(e)[:80])
