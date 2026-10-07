#!/usr/bin/env python3
"""gutil.py — grip/ 探針共用(在 SimulationApp 之後 import)。

  rigid_mat(st, fric)                 剛體摩擦材質(static = dynamic = fric)
  finger(st, path, size, center, fric, cont, rest)  kinematic 方塊指面(Xform RigidBody + 子 Cube),綁摩擦
  static_box(st, path, size, center, fric)         靜態碰撞箱(桌面)
  in_box(Q, c, half)                  點是否落在軸對齊方塊內 + 深度(到最近面距離)
  edges(T)                            四面體網格的唯一邊
  vis_mesh(st, path, FLAT, nxy, color) 渲染用外表面 Mesh(同 wrap_vol 的作法),回傳 points attr
  Video                               Camera + imageio 寫 mp4 + 字幕
"""
import os, sys
import numpy as np
from pxr import Gf, Sdf, UsdGeom, UsdPhysics, UsdShade, PhysxSchema, Vt
from omni.physx.scripts import physicsUtils

HERE = os.path.dirname(os.path.abspath(__file__))
VOL = os.path.dirname(HERE)
if VOL not in sys.path:
    sys.path.insert(0, VOL)
import volcommon as VC   # noqa: E402


def rigid_mat(st, fric, rest=0.0):
    p = "/World/rmat_%d" % int(round(fric * 100))
    if not st.GetPrimAtPath(p).IsValid():
        mp = st.DefinePrim(p, "Material")
        m = UsdPhysics.MaterialAPI.Apply(mp)
        m.CreateStaticFrictionAttr(float(fric)); m.CreateDynamicFrictionAttr(float(fric)); m.CreateRestitutionAttr(rest)
    return p


def vmat(st, path, col, rough=0.5, op=1.0):
    if st.GetPrimAtPath(path).IsValid():
        return UsdShade.Material(st.GetPrimAtPath(path))
    m = UsdShade.Material.Define(st, path); sh = UsdShade.Shader.Define(st, path + "/S")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*col))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(op)
    m.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return m


def bind_vis(st, prim, col, name):
    m = vmat(st, "/World/Looks/" + name, col)
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(m)


def _collider_offsets(prim, cont, rest):
    pc = PhysxSchema.PhysxCollisionAPI.Apply(prim)
    if cont is not None:
        pc.CreateContactOffsetAttr().Set(float(cont))
    if rest is not None:
        pc.CreateRestOffsetAttr().Set(float(rest))


def finger(st, path, size, center, fric, cont=0.001, rest=0.0, color=(0.15, 0.15, 0.18)):
    pr = VC.kin_box(st, path, size, center, collide=True)
    g = st.GetPrimAtPath(path + "/geom")
    physicsUtils.add_physics_material_to_prim(st, g, rigid_mat(st, fric))
    _collider_offsets(g, cont, rest)
    UsdGeom.Gprim(g).CreateDisplayColorAttr([Gf.Vec3f(*color)])
    bind_vis(st, g, color, "fing_%d_%d_%d" % tuple(int(c * 100) for c in color))
    return pr


class VisBox:
    """純視覺方塊(無物理),每幀寫 translate(tensor kinematic target 不會回寫 USD,渲染看不到指面移動)。"""
    def __init__(self, st, path, size, color):
        cb = UsdGeom.Cube.Define(st, path); cb.CreateSizeAttr(1.0)
        xf = UsdGeom.Xformable(cb)
        self.t = xf.AddTranslateOp(); self.o = xf.AddOrientOp(); xf.AddScaleOp().Set(Gf.Vec3f(*map(float, size)))
        self.o.Set(Gf.Quatf(1, 0, 0, 0))
        bind_vis(st, cb.GetPrim(), color, "vis_%d_%d_%d" % tuple(int(c * 100) for c in color))
        self.t.Set(Gf.Vec3d(0, 0, -5))

    def set(self, c, q=None):
        self.t.Set(Gf.Vec3d(*map(float, c)))
        if q is not None:
            self.o.Set(Gf.Quatf(float(q[0]), float(q[1]), float(q[2]), float(q[3])))


def static_box(st, path, size, center, fric, cont=0.001, rest=0.0, color=(0.55, 0.45, 0.35)):
    cb = UsdGeom.Cube.Define(st, path); cb.CreateSizeAttr(1.0)
    xf = UsdGeom.Xformable(cb)
    xf.AddTranslateOp().Set(Gf.Vec3d(*map(float, center)))
    xf.AddScaleOp().Set(Gf.Vec3f(*map(float, size)))
    UsdPhysics.CollisionAPI.Apply(cb.GetPrim())
    physicsUtils.add_physics_material_to_prim(st, cb.GetPrim(), rigid_mat(st, fric))
    _collider_offsets(cb.GetPrim(), cont, rest)
    cb.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    bind_vis(st, cb.GetPrim(), color, "box_%d_%d_%d" % tuple(int(c * 100) for c in color))
    return cb.GetPrim()


def in_box(Q, c, half):
    """Q (N,3) 在中心 c、半邊長 half 的軸對齊方塊內 → (mask, depth)。depth = 到最近面的距離(只對 mask 內有效)。"""
    d = half - np.abs(Q - c)
    m = (d > 0).all(1)
    return m, d.min(1)


def edges(T):
    return np.unique(np.sort(np.concatenate([T[:, [i, j]] for i in range(4) for j in range(i + 1, 4)]), axis=1), axis=0)


def surf_faces(nx, ny):
    """grid_tets(nx,ny,1) 的外表面三角形(上/下/四側)。頂點索引 (k*(ny+1)+j)*(nx+1)+i。"""
    gid = lambda i, j, k: (k * (ny + 1) + j) * (nx + 1) + i
    F = []
    for j in range(ny):
        for i in range(nx):
            F += [(gid(i, j, 1), gid(i + 1, j, 1), gid(i + 1, j + 1, 1)), (gid(i, j, 1), gid(i + 1, j + 1, 1), gid(i, j + 1, 1))]
            F += [(gid(i, j, 0), gid(i + 1, j + 1, 0), gid(i + 1, j, 0)), (gid(i, j, 0), gid(i, j + 1, 0), gid(i + 1, j + 1, 0))]
    for s in range(nx):
        for (p0, p1) in [((s, 0), (s + 1, 0)), ((s + 1, ny), (s, ny))]:
            a0, a1 = gid(*p0, 0), gid(*p1, 0); b0, b1 = gid(*p0, 1), gid(*p1, 1)
            F += [(a0, a1, b1), (a0, b1, b0)]
    for s in range(ny):
        for (p0, p1) in [((nx, s), (nx, s + 1)), ((0, s + 1), (0, s))]:
            a0, a1 = gid(*p0, 0), gid(*p1, 0); b0, b1 = gid(*p0, 1), gid(*p1, 1)
            F += [(a0, a1, b1), (a0, b1, b0)]
    return np.array(F, int)


def vis_mesh(st, path, FLAT, nx, ny, color):
    F = surf_faces(nx, ny)
    m = UsdGeom.Mesh.Define(st, path)
    m.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in FLAT]))
    m.CreateFaceVertexCountsAttr([3] * len(F)); m.CreateFaceVertexIndicesAttr([int(x) for x in F.ravel()])
    m.CreateSubdivisionSchemeAttr().Set("none"); m.CreateDoubleSidedAttr(True)
    m.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    bind_vis(st, m.GetPrim(), color, "sheet_%d_%d_%d" % tuple(int(c * 100) for c in color))
    return m.GetPointsAttr()


class Video:
    def __init__(self, st, out_mp4, eye, tgt, fps=30, res=(1280, 720), focal=10.0, label=""):
        from isaacsim.sensors.camera import Camera
        from pxr import UsdLux
        import grip_common as G
        import imageio
        self.G = G
        self.cam = Camera(prim_path="/World/cam", resolution=res)
        self.cam.set_focal_length(focal)
        try:
            self.cam.set_clipping_range(0.01, 100.0)
        except Exception:
            pass
        _gl = st.GetPrimAtPath("/World/defaultGroundPlane/SphereLight")
        if _gl.IsValid():
            _ga = _gl.GetAttribute("inputs:intensity")
            if _ga and _ga.IsValid():
                _ga.Set(_ga.Get() / 12.0)
        self.look(eye, tgt)
        G.add_headlight(st, eye, tgt, intensity=300.0, name="hl1")
        UsdLux.DomeLight.Define(st, "/World/dome").CreateIntensityAttr(1500.0)
        self.w = imageio.get_writer(out_mp4, fps=fps, quality=7, macro_block_size=1)
        self.label = label; self.n = 0; self.path = out_mp4

    def init(self):
        self.cam.initialize()
        self.cam.set_clipping_range(0.01, 100.0)   # ★ 預設 near clip 會把 <~1m 的東西切掉

    def look(self, eye, tgt):
        self.cam.set_world_pose(np.array(eye, float), self.G.cam_quat(eye, tgt), camera_axes="world")

    def frame(self, t, txt):
        from PIL import Image, ImageDraw, ImageFont
        rgb = self.cam.get_rgba()
        if rgb is None or not rgb.size:
            return None
        try:
            fn = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 18)
        except Exception:
            fn = ImageFont.load_default()
        im = Image.fromarray(rgb[:, :, :3]); d = ImageDraw.Draw(im); W, H = im.size
        d.rectangle([0, H - 34, W, H], fill=(16, 16, 18)); d.text((8, H - 30), self.label, fill=(230,) * 3, font=fn)
        d.rectangle([0, 0, W, 30], fill=(16, 16, 18)); d.text((8, 5), "t=%5.2fs  %s" % (t, txt), fill=(255,) * 3, font=fn)
        a = np.array(im); self.w.append_data(a); self.n += 1
        return a

    def close(self):
        self.w.close()


def montage(mp4, out_png, n=4, labels=None):
    """從 mp4 平均抽 n 格拼成 2x2(n=4)圖。"""
    import imageio
    from PIL import Image
    r = imageio.get_reader(mp4); fr = [f for f in r]; r.close()
    idx = np.linspace(0, len(fr) - 1, n + 2)[1:-1].astype(int) if labels is None else labels
    ims = [Image.fromarray(fr[i]) for i in idx]
    w, h = ims[0].size
    cols = 2; rows = (len(ims) + 1) // 2
    M = Image.new("RGB", (w * cols, h * rows))
    for k, im in enumerate(ims):
        M.paste(im, ((k % cols) * w, (k // cols) * h))
    M = M.resize((w * cols // 2, h * rows // 2))
    M.save(out_png)
    return idx
