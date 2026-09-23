# -*- coding: utf-8 -*-
"""wrapped_mug 參數表 —— 每個值標註來源。

provenance:  measured / literature / derived / assumed
"""

# ---------------------------------------------------------------- 紙箱
# 內部尺寸由杯子實際 bbox + 下面的餘裕自動推導(換杯子就自己重算),
# 但不小於 min_inner_*。
CARTON = dict(
    clear_l=0.040,          # 杯長之外,每端留給包材臂與手指的餘裕
    clear_w=0.028,          # 杯寬(含把手)之外,每側的餘裕
    clear_h=0.026,          # 杯頂之上留給包材與夾爪的淨空
    min_inner=(0.200, 0.160, 0.095),
    board_t=0.004,          # literature  B 楞瓦楞紙板厚約 3~4 mm
    density=190.0,          # literature  瓦楞紙板約 150~250 kg/m3
    flap_open_deg=105.0,    # assumed  交付初態:耳朵外翻(看得到內容物)
    drive_stiffness=6.0,    # assumed  N*m/rad,耳朵停得住又推得動
    drive_damping=0.35,     # assumed
    flap_limit_deg=(-5.0, 130.0),
    friction=0.6,           # assumed
)

# ---------------------------------------------------------------- 馬克杯
MUG = dict(
    # 杯子來源。None = 用下面的程序化參數;字串 = USD 檔(相對本資料夾或絕對路徑)。
    #   專案提供的 mug.usd 裡沒有任何幾何(mesh points = 0),不能用。
    #   assets/ 下這四顆是 NVIDIA 官方資產:SM_Mug_A2 / B1 / C1 / D1。
    #   B1 把手孔最大,PPT 第 14 步「夾馬克杯耳朵」最好夾。
    source="assets/SM_Mug_B1.usd",
    scale=0.68,             # 官方杯直徑 89~93 mm,他們的箱內高只有 87 —— 放不下也包不住。
                            #   0.68 -> 直徑 62.9、高 62.5、含把手 92.8 mm,包材臂折過頂還有 12 mm 淨空。
    sdf_resolution=256,     # 開口薄殼網格要用 SDF 才擋得住;越高輪廓越準、越吃資源
    outer_r=0.038,          # assumed  杯身外徑 76 mm
    height=0.095,           # assumed
    wall_t=0.0045,          # assumed
    base_t=0.007,           # assumed
    handle_major_r=0.023,   # assumed  把手環中線半徑
    handle_minor_r=0.0058,  # assumed  把手管半徑 -> 徑向淨開口 ~23 mm,夾爪指進得去
    handle_offset=0.006,    # assumed  環心離杯壁的外推量
    mass=0.32,              # literature  空陶瓷馬克杯 300~400 g
    friction=0.9,           # assumed
    lin_damp=0.12,          # derived  交付值。學長的 3.0 是搬運階段用的
    ang_damp=0.60,   # 圓柱躺在軟膜上很容易滾;把手又讓它偏心          # derived
    handle_roll_deg="auto", # 橫放後繞杯軸的滾轉。"auto" = 自動量出把手在哪一側,
                            #   轉到水平指向 +Y。不同來源的杯子把手軸向不一樣,
                            #   NVIDIA 那幾顆在 +Y,學長的程序化杯在 +X。
                            #   朝上會頂到 120 mm 戳出箱外(箱內高 105),故取水平。
                            #   PPT 未指定把手朝向,待提案方拍板
)

# ---------------------------------------------------------------- 泡泡紙
# 推導鏈: 量 W 與彎曲長度 c -> D = W*g*c^3 -> surfaceBendStiffness = D / t^3
#         官方: edge bend stiffness 正比於 surfaceBendStiffness * surfaceThickness^3
BUBBLE = dict(
    areal_mass=0.060,       # literature  30~150 g/m2,60 GSM 為常用中量級
    bubble_pitch=0.010,     # literature  泡泡直徑 9.5~10.0 mm
    bubble_height=0.004,    # literature  泡高約 4 mm
    film_gauge=6.0e-5,      # literature  雙層 LDPE 60 um(僅供記錄,不當物理厚度)
    bending_length=0.034,   # ASSUMED — 唯一需要拿尺量的數字(ASTM D1388 懸臂法)
                            #   0.050 太挺,膜會Q彈;真實泡泡紙大約 30~40 mm
    thickness=0.004,        # derived  取泡高為等效殼厚:決定二次矩的長度尺度
    youngs=5.0e4,           # assumed  僅影響面內;垂墜對它不敏感
    poisson=0.45,           # assumed
    dyn_friction=0.75,      # assumed  staticFriction 在 deformable solver 無效
    elasticity_damping=0.85,   # 調高:膜要像被折過的包材,不是彈簧床
    bend_damping=0.85,
    lin_damp=0.60,
    cell_size=0.008,        # derived  規則: <= 杯半徑/5,才貼得上 R38 的杯身
    contact_offset=0.005,
    rest_offset=0.001,
    # OmniPBR 的 enable_opacity 在本機 RTX Real-Time 下會讓膜完全不渲染
    # (實測:把 diffuse 設成鮮紅,畫面上一點紅都沒有)。交付版走不透明,
    # 靠淺藍 + 高鏡面 + 泡泡法線貼圖表現塑膠膜質感。
    transparent=False,
    opacity=0.55,
    roughness=0.05,
    bump_factor=3.0,
)


def bend_stiffness(areal_mass, bending_length, thickness, g=9.81):
    """D = W*g*c^3 ;  surfaceBendStiffness = D / t^3  (官方公式的反解)"""
    D = areal_mass * g * bending_length ** 3
    return D / thickness ** 3, D


BUBBLE["surface_bend_stiffness"], BUBBLE["flexural_rigidity"] = bend_stiffness(
    BUBBLE["areal_mass"], BUBBLE["bending_length"], BUBBLE["thickness"])

# ---------------------------------------------------------------- 包覆形狀
# 十字形(plus)裁片:中央貼箱底,四隻臂分別往上折。
# 四角不留料 —— 平面裁片折成立體時,有角料就一定產生高斯曲率衝突(會皺、會撐)。
# 每隻臂用「曲率剖面」產生:沿弧長給定切線角再積分 -> 等距映射,不產生面內應變。
WRAP = dict(
    center_half_x=0.062,    # 中央panel 半長:馬克杯端面在 ±47.5,留 14.5 mm
    center_half_y=0.078,    # 中央panel 半寬:把手尖端在 +72.8,留 5 mm;箱內壁 90,留 12 mm
    # 長邊(Y 方向)兩隻臂:繞著杯身捲上去,在杯頂合攏 —— 主要的包覆
    side=dict(corner_r=0.008, wall_rise=0.070, fold_r=0.014, fold_deg=90.0,
              tip_len=None, target_gap=0.004),
    # 短邊(X 方向)兩隻臂:立起來後往內壓,蓋住杯子的兩個端面 —— 封前後
    # 折得比長邊低,讓長邊的臂壓在它上面(真實包法也是先折短邊再折長邊)
    end=dict(corner_r=0.008, wall_rise=0.066, fold_r=0.016, fold_deg=100.0,
             tip_len=None, target_gap=None),   # target_gap 由杯長推導
)

# ---------------------------------------------------------------- 場景 / 求解
SIM = dict(
    bake_hz=240,
    deliver_hz=120,
    bake_solver_iter=64,
    deliver_solver_iter=32,
    bake_collision_pair_update=2,
    bake_collision_iter_mult=2,
    settle_steps=900,          # 第一階段:杯子 kinematic,膜自己貼合
    settle2_steps=900,         # 第二階段:杯子轉動態,兩者一起落定

    settle_vel_eps=1.5e-3,
    max_depen_vel=0.5,
    plasticity_alpha=1.0,   # 1.0 = 靜置形狀即零能量狀態(完全定型)
)

# ---------------------------------------------------------------- 互動
VIEW = dict(
    picking_force=25.0,
    joint_drag=True,        # 約束式拖曳,不受 pickingForce 縮放影響
    no_shift=True,          # 免按 Shift,左鍵直接拉
)
