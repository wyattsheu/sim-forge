#!/usr/bin/env python3
"""wrap_vol.py — volume deformable 薄板(4mm)包馬克杯 → 入紙箱關蓋 → 搬箱 → 開蓋,單一次模擬跑完全程。

    /isaac-sim/python.sh wrap_vol.py --sheet_mm 400 --out out_v400 [--until fold|box|move]

階段(預設時間,秒;--fold_span / --lid_span 可改):
  settle 0.5 → fold xp → fold xn → fold yp → fold yn(各 3.0 動 + 0.5 停)
  → into box(紙箱折疊期間停在旁邊 OFF_SIDE;折完把**箱子**剛性瞬移到包裹周圍 —— 與 surface 版
    「整包(布+杯子)用同一個向量搬」等價:只看相對位置)→ settle 1.0
  → close lower lids(4)→ close upper lids(4)→ release anchors(RemovePrim)+ 杯子轉 dynamic → settle 2
  → move box(6,smoothstep)→ settle 2 → open upper lids(3)→ open lower lids(3)→ hold 3

從 ../work/wrap_sim.py 搬來(標 [ws]):杯子躺平/方位(Rz(-90)+_Rm)、佔位/折線幾何(margin/wall)、
  FOLD_ORDER、SIDEPICK 角落歸屬規則、wrap_arc_from 兩段圓弧的想法、film_tex 泡泡材質、vmat、燈光、
  紙箱載入/不透明材質/meta 讀內腔與鉸鏈、蓋子 sgn 自檢、reset 前把蓋子擺開、lid_pose、關/開蓋順序、
  搬箱 smoothstep、base_collider_pad、地板碰撞關閉、inbox 逐頂點比對、相機/字幕。
從 vol/ 探針沿用:volcommon.build_plate(manual 35x35x1、5-tet 鏡像)、attach_vtx、vol_pen.self_pen_count。
"""
import os, sys, argparse, time, json
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--sheet_mm", type=float, default=400.0)
ap.add_argument("--sheet_x_mm", type=float, default=0.0, help="長方形布 x 邊長;0 = 沿用 --sheet_mm")
ap.add_argument("--sheet_y_mm", type=float, default=0.0, help="長方形布 y 邊長;0 = 沿用 --sheet_mm")
ap.add_argument("--out", default="out_vol")
ap.add_argument("--mug", default="mug.stl")
ap.add_argument("--carton", default="carton_w131.usd")
ap.add_argument("--tex", default="bubble_normal.png")
ap.add_argument("--tex_mm", type=float, default=200.0)
ap.add_argument("--thick_mm", type=float, default=4.0)
ap.add_argument("--nxy", type=int, default=35)
ap.add_argument("--young", type=float, default=2e3, help="楊氏模數 Pa;2e3 = 官方值(soft/s2、out_ga3),2e4 為舊預設")
ap.add_argument("--ldamp", type=float, default=0.0, help="physxDeformableBody:linearDamping(0 = 舊行為)")
ap.add_argument("--edamp", type=float, default=0.0, help="physxDeformableMaterial:elasticityDamping(0 = 舊行為)")
ap.add_argument("--poisson", type=float, default=0.45)
ap.add_argument("--areal", "--areal_density", dest="areal", type=float, default=0.1, help="面密度 kg/m²")
ap.add_argument("--fric", type=float, default=0.8)
ap.add_argument("--cont", type=float, default=0.002)
ap.add_argument("--rest", type=float, default=0.0005)
ap.add_argument("--solver", type=int, default=128)
ap.add_argument("--dt", type=float, default=1/240.0)
ap.add_argument("--margin", type=float, default=0.012, help="[ws] 佔位比杯子大多少(m)")
ap.add_argument("--wall", type=float, default=0.006, help="[ws] 折線離佔位側面(m)")
ap.add_argument("--fold_span", type=float, default=3.0, help="每折動作秒數")
ap.add_argument("--fold_hold", type=float, default=0.5, help="每折到位後停幾秒")
ap.add_argument("--slow", default="", help="某折放慢,例 yp:1.5,yn:1.5")
ap.add_argument("--tip_extra", default="", help="某折終點加高 mm,例 yp:2 或 all:2")
ap.add_argument("--tip_over_mm", type=float, default=30.0, help="尖端最多越過中線多少 mm(夾住)")
ap.add_argument("--lid_span", type=float, default=4.0)
ap.add_argument("--open_span", type=float, default=3.0)
ap.add_argument("--movebox", default="0,0.20,0.10")
ap.add_argument("--move_t", type=float, default=6.0)
ap.add_argument("--base_collider_pad", type=float, default=0.02)
ap.add_argument("--squeeze_t", type=float, default=2.5, help="四折後四面側板收到紙箱內腔-3mm 用幾秒(0=不做)")
ap.add_argument("--squeeze_mm", type=float, default=3.0, help="側板停在內腔內縮幾 mm")
ap.add_argument("--until", choices=["fold", "box", "move", "all", "yn"], default="all", help="yn = [speed2] 跑到 yn 片結束(= --second 0 --extract 0)")
ap.add_argument("--rest_npz", default="", help="restShapePoints = 這個 npz 的 fold_end tet 頂點(points 仍平)")
ap.add_argument("--cam_ref", type=float, default=0.586)
ap.add_argument("--meas_dt", type=float, default=0.5)
ap.add_argument("--vid_every", type=int, default=1, help="[speed] 每 N 個渲染幀才真的 render+讀回+編碼一次(量測不變;1 = 舊行為)")
ap.add_argument("--vid_res", default="1280x720", help="[speed] 相機解析度 WxH")
ap.add_argument("--fast_pts", type=int, default=0, help="[speed] 1 = PhysX tensor volume deformable view 直接讀 sim 節點,取代 USD points")
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--tuck", type=int, default=1, help="1 = 四折後側板收耳(預設);0 = 不收耳(等同 --squeeze_t 0)")
ap.add_argument("--grasp", type=int, default=0, help="1 = 開蓋 hold 之後同一次模擬續跑:挑角 → 夾 → 沿弧線掀 yn(再掀 yp)")
ap.add_argument("--grasp_rank", type=int, default=1, help="yn 片用排名第幾的抓取點")
ap.add_argument("--pick_mm", type=float, default=25.0, help="挑角:單指伸進 25mm 後往上抬幾 mm")
ap.add_argument("--pick_in_mm", type=float, default=25.0, help="挑角:單指沿 −u 伸進幾 mm")
ap.add_argument("--arc_k", type=float, default=0.9, help="掀:弧半徑 = arc_k x 夾點到彎折處的材料長度")
ap.add_argument("--peel_t", type=float, default=3.0, help="掀:弧線秒數")
ap.add_argument("--gap_mm", type=float, default=4.5, help="夾:指面間距")
ap.add_argument("--ffric", type=float, default=2.0, help="指面摩擦")
ap.add_argument("--pick_mode", choices=["jaw", "rod", "wide"], default="jaw",   # [pgrasp] wide = jaw 路徑 + 寬指(--wide_mm)
                help="jaw(預設):下指本身當挑角的指(插到布邊下 → 上抬)再由上指從 +n 合;rod:另一根 8mm 單指挑角,上下指張口從布邊外插入再合(第 2~4 次實跑夾到 0)")
ap.add_argument("--chord", type=int, default=1, help="挑角/夾的局部框:1 = 布邊切線(預設,同 grasp_points);2 = 布邊→往內第 2 排的弦")
ap.add_argument("--arc2", type=int, default=1, help="1 = 弧線第 2 段繞箱壁頂角轉到 180°(箱外指頭最低點墊高到蓋頂);0 = 只做第 1 段(轉到指向箱壁頂角為止)")
ap.add_argument("--clear_mm", type=float, default=3.0, help="挑角:下指頂面在布底下幾 mm 插入")
ap.add_argument("--steep_deg", type=float, default=90.0, help="布邊坡度 >= 這個角度就不上抬(角已翹起,下指插到位直接合上指)")
ap.add_argument("--second", type=int, default=1, help="1 = yn 掀完接著掀 yp(不論 yn 判定)")
ap.add_argument("--gcam_focal", type=float, default=2.8, help="抓取段相機 focal(Camera API 單位,x10 = mm)")
ap.add_argument("--grasp_attach", type=int, default=0, help="1 = 夾爪閉合完成那步把指間 yn 片頂點 VtxXformAttachment 綁到上指,張開時 RemovePrim")
ap.add_argument("--attach_pad_mm", type=float, default=16.0, help="綁定挑點:指面足跡(夾爪框 t/u)半寬外擴到這個 mm")
ap.add_argument("--attach_nlo_mm", type=float, default=-1.0, help="綁定挑點的 n 下限(指間中面以下幾 mm;<0 = 同上限 間距/2+4);n<0 的頂點綁到下指")
ap.add_argument("--attach_layer", choices=["both", "top"], default="both", help="both = 指間上下層都綁;top = 只綁 n>0(上指側)")
ap.add_argument("--attach_mask_own", type=int, default=0, help="[drag] 1 = 綁定時排除被 xp/xn 等他片壓住(over)的 yn 頂點;2 = 再排除緊貼他片上方(under)的;0 = 舊行為")
ap.add_argument("--attach_mask_r_mm", type=float, default=16.0, help="[drag] layer_order 鄰域半徑 mm")
ap.add_argument("--attach_mask_dz_mm", type=float, default=2.0, help="[drag] layer_order 層高差門檻 mm")
ap.add_argument("--lift_first_mm", type=float, default=0.0, help="[drag] 夾好後先直線拉起這麼多 mm 再轉弧(0 = 舊行為)")
ap.add_argument("--lift_first_t", type=float, default=1.0, help="[drag] 拉起用時 s")
ap.add_argument("--lift_first_dir", choices=["z", "n"], default="z", help="[drag] z = 世界垂直;n = 上指法線")
ap.add_argument("--attach_stiff", type=float, default=0.0, help="[drag] 夾持綁定 omniphysics:stiffness(每頂點 N/m);0 = 舊無限剛度")
ap.add_argument("--hold_others", type=int, default=0, help="[drag] 1 = 綁定 yn/yp 那一步同時把他片(xp/xn)靠折線側釘到不碰撞 kinematic 錨(PPT 第二隻手),放手後移除;0 = 舊行為")
ap.add_argument("--hold_pad_mm", type=float, default=24.0, help="[drag] 他片在 flat 座標從該片折線往內延伸幾 mm 都釘(耳朵區一定包含)")
ap.add_argument("--hold_mode", choices=["attach", "pad"], default="attach", help="[drag] attach = VtxXformAttachment 釘住;pad = 壓板(未實作)")
ap.add_argument("--hold_sides", default="xp,xn", help="[drag] 要釘的片,逗號分隔")
ap.add_argument("--hold_layer", choices=["both", "top", "topfree"], default="both", help="[drag] both = TOP+BOT 兩層;top = 只釘上層")
ap.add_argument("--hold_region", choices=["ear", "own"], default="ear", help="[drag2] ear = 舊:靠本片(yn/yp)折線內 pad;own = 他片自己折線(|flat x|<=CX+pad)那一帶")
ap.add_argument("--hold_min_d_mm", type=float, default=0.0, help="[drag2] 釘點離本片綁定頂點(世界 xy)至少這麼遠;0 = 不限")
ap.add_argument("--guard_hold", type=float, default=0.0, help="[drag2] 釘住期間守衛邊長比門檻(>0 才生效,否則 2.3)")
ap.add_argument("--lift_first_out_mm", type=float, default=0.0, help="[drag2] 先拉起時同時往箱外(本片外側 y)抽這麼多 mm")
ap.add_argument("--arc2_ext_mm", type=float, default=0.0, help="[drag2] 弧線終點後再往箱外(本片外側 y)直線延伸 mm;0 = 舊行為")
ap.add_argument("--arc2_ext_t", type=float, default=1.0, help="[drag2] 延伸用時 s")
ap.add_argument("--arc2_over_mm", type=float, default=0.0, help="[peel] 弧線終點後夾爪中心再越過箱壁外緣這麼多 mm,同時轉到 180°(片翻過箱壁躺到外側);上限 = 材料長 − 鉸點到箱壁頂角 − 5mm;0 = 舊行為")
ap.add_argument("--arc2_over_cap", type=int, default=1, help="[peel3] 1 = 越壁量受 材料長−鉸點到頂角−5 上限(舊);0 = 不截(靠守衛 2.3 防撕)")
ap.add_argument("--arc2_target", default="open", choices=["open", "centroid"], help="[peel3] centroid = 越壁段閉環:每 0.25s 算片質心 y,往外往下直到過壁外緣−margin")
ap.add_argument("--arc2_margin_mm", type=float, default=5.0, help="[peel3] centroid 目標:質心過壁外緣多少 mm")
ap.add_argument("--arc2_cl_t", type=float, default=3.0, help="[peel3] centroid 時間上限 s(之後固定再停 1 s)")
ap.add_argument("--arc2_cl_max_mm", type=float, default=80.0, help="[peel3] centroid 夾爪最多越壁 mm(w=1)")
ap.add_argument("--arc2_cl_down_mm", type=float, default=30.0, help="[peel3] centroid w=1 時往下 mm")
ap.add_argument("--arc2_lay", type=int, default=0, help="[peel4] 1 = 越壁段後夾爪往下到 箱外指頭最低點 = 打開的蓋頂 + 2mm(放寬舊的 +T+2),讓片躺到蓋上再停再放手;放手改成先往箱外抽出再抬起")
ap.add_argument("--arc2_lay_t", type=float, default=1.0, help="[peel4] 往下用時 s(之後照舊停 peel_hold 再放手)")
ap.add_argument("--arc2_er_stop", type=float, default=0.0, help="[peel4] 越壁(閉環)/往下段邊長比 > 此值就凍結夾爪;0 = 舊行為")
ap.add_argument("--arc2_over_t", type=float, default=1.5, help="[peel] 越過用時 s")
ap.add_argument("--arc_grow_max_mm", type=float, default=0.0, help="[peel] 弧半徑最多比夾爪起始離彎折處距離 r0 大這麼多 mm(片被他片壓住/材料皺著時不硬拉長);0 = 舊行為")
ap.add_argument("--release_press_mm", type=float, default=0.0, help="[peel] 放手前末端再往下壓 mm(箱壁外側貼住);0 = 舊行為")
ap.add_argument("--release_settle_s", type=float, default=0.0, help="[peel] 下壓後再停 s 才放手;0 = 舊行為")
ap.add_argument("--hold_rel_s", type=float, default=0.5, help="[drag] TR(放手開始)後幾秒移除釘住")
ap.add_argument("--attach_damp", type=float, default=0.0, help="[drag] 夾持綁定 omniphysics:damping(每頂點 N·s/m);-1 = 自動臨界 2*sqrt(k*m_vtx)")
ap.add_argument("--attach_proxy", type=int, default=0, help="[drag] 1 = 上指綁定改綁到動態代理 /World/gfing/upx(D6 drive 掛在上指,力上限 proxy_fmax);0 = 舊行為")
ap.add_argument("--proxy_k", type=float, default=500.0, help="[drag] 代理 drive 剛度 N/m")
ap.add_argument("--proxy_c", type=float, default=-1.0, help="[drag] 代理 drive 阻尼 N·s/m;-1 = 2*sqrt(k*m_proxy)")
ap.add_argument("--proxy_fmax", type=float, default=0.5, help="[drag] 代理 drive maxForce N(每軸);布抗力超過就讓代理落後")
ap.add_argument("--grasp_site", choices=["design", "state"], default="design", help="[robust] design = 舊行為(自由邊中段);state = 夾前用實際頂點狀態在自由邊取候選,選預估綁點最多、沒被他片壓住、下方有支撐的")
ap.add_argument("--grasp_retry", type=int, default=0, help="[robust] 合指後綁點 < --grasp_retry_min 就張開、換下一個候選重夾,最多 N 次;0 = 舊行為")
ap.add_argument("--grasp_retry_min", type=int, default=6, help="[robust] 重夾門檻(綁點數)")
ap.add_argument("--site_xmax_mm", type=float, default=0.0, help="[peel2] state 候選排除位置 |x|(箱局部)>= 此值;0 = 舊行為")
ap.add_argument("--site_exclude_walltop", type=int, default=0, help="[peel2] 1 = 排除已在箱壁頂上(|y| > 內壁、z > 壁頂 − 10mm)的候選")
ap.add_argument("--hinge_from_state", type=int, default=0, help="[peel2] 1 = 彎折處偵測 nan 時用頂點狀態(箱底/下層接觸最前緣)求實際彎折,不退名義折線")
ap.add_argument("--grasp_site_k", type=int, default=7, help="[robust] state 模式沿自由邊取幾個候選")
ap.add_argument("--fold_order", default="xp,xn,yp,yn", help="[variants] 折序,四片任意排列;預設 = 舊行為")
ap.add_argument("--mug_off_mm", default="0,0", help="[variants] 杯子(佔位中心)相對布中心偏 dx,dy mm;實作 = 布反向平移")
ap.add_argument("--mug_yaw_deg", type=float, default=0.0, help="[variants] 杯子繞 z 轉幾度(佔位 = 轉後 AABB)")
ap.add_argument("--seed", type=int, default=0, help="[variants] 隨機種子(記錄用)")
ap.add_argument("--hand2", choices=["off", "press", "attach", "jaw"], default="off", help="[hand2] 第二隻手:jaw = [jaw2] 兩指夾爪從上方下、沿 x 合指,合好才綁指間足跡(+hand2_pad_mm)頂點;press = 放手前在夾點外側(壁外 10~40mm)以有碰撞 kinematic 壓板(40x30x4mm)壓住躺在蓋上那段;attach = 同位置 VtxXformAttachment 綁到 kinematic 方塊;off = 舊行為")
ap.add_argument("--hand2_hold_s", type=float, default=3.0, help="[hand2] 第一隻手放手後第二隻手持續壓/綁幾秒,之後垂直抬起(attach:先解綁)")
ap.add_argument("--hand2_lead_s", type=float, default=0.5, help="[hand2] 放手前幾秒壓到位(之前 0.5s 從上方下壓)")
ap.add_argument("--hand2_pad_mm", type=float, default=15.0, help="[hand2] attach:方塊足跡外擴 mm 內的頂點都綁")
ap.add_argument("--hand2_keep", type=int, default=0, help="[extract] 1 = 第二隻手綁住 yn 後不撤(到流程結束);只用在 yn")
ap.add_argument("--hold_yp", type=int, default=0, help="[extract] 1 = yp 掀到壁外後第一隻手不放(停在那裡到結束)")
ap.add_argument("--extract", type=int, default=0, help="[extract] 1 = yp 段結束後第三隻 kinematic 取杯手:下到杯頂 → 綁杯(杯轉 kinematic 跟手)→ 抬 150mm → 水平 +x 移 → 放到地面")
ap.add_argument("--extract_lift_mm", type=float, default=150.0, help="[extract] 垂直抬起 mm")
ap.add_argument("--extract_out_mm", type=float, default=200.0, help="[extract] 水平 +x 移出 mm")
ap.add_argument("--extract_mode", default="lift", choices=["lift", "slide"], help="[extract2] lift = 舊(垂直抬 → +x);slide = 抬 20mm → 斜升過 yn 壁頂 → 水平 −y 移出 extract_out_mm → 降到地面")
ap.add_argument("--guard_yp", type=float, default=0.0, help="[extract2] >0:yp 段守衛邊長比門檻(取代 2.3)")
ap.add_argument("--guard_yn", type=float, default=0.0, help="[extract3] >0:yn 段守衛門檻(取代 2.3),且 --guard_n 也套用到 yn 段")
ap.add_argument("--slide_clear_mm", type=float, default=10.0, help="[extract3] slide 過壁:杯底高過壁頂 mm(預設 10 = 舊)")
ap.add_argument("--hand2_tuck_mm", type=float, default=0.0, help="[extract3] >0:取杯開始時手 2 把 yn 布往壁外、往下各移 mm(綁杯前完成)")
ap.add_argument("--hand1_jaw", type=int, default=0, help="[jaw2] 1 = 第一隻手(grasp_attach 模式)顯示下指(純視覺:布邊外 35mm 降下 → 沿 −u 滑到布下 → 上指合;合好後跟著上指、放手時張開);0 = 舊(只看得到上指)")
ap.add_argument("--extract_grip", choices=["pad", "jaw"], default="pad", help="[jaw2] 取杯手:pad = 舊(方塊壓杯頂、杯轉 kinematic 跟手);jaw = 兩指沿 y 從杯兩端夾:張開下降 → 合指到接觸 → 杯轉 kinematic 跟手 → 放下後張開再抬")
ap.add_argument("--jaw_collide", type=int, default=0, help="[jaw3] 1 = 夾爪指都是 kinematic 碰撞體(GU.finger,cont 1mm/rest 0,摩擦 ffric):手 1 用實體下指 lo 走下指路徑、手 2 兩指、取杯手兩指;log 指-布最小距離;0 = jaw2 純視覺")
ap.add_argument("--finger_mm", type=float, default=20.0, help="[jaw2] 第一隻手指面邊長 mm(t,u);預設 20 = 舊")
ap.add_argument("--wide_mm_x", type=float, default=0.0, help="[v2x2] >0 = x 片(xn/xp)改用這個寬度的寬指(另一組實體指 upW/loW,x 片開始時換手;yn/yp 照 --wide_mm);0 = 全部 --wide_mm(舊)")
ap.add_argument("--wide_mm", type=float, default=150.0, help="[pgrasp] --pick_mode wide:指長(沿自由邊 t)mm;指面 = wide_mm x wide_depth_mm x wide_thick_mm")
ap.add_argument("--wide_squeeze_mm", type=float, default=1.0, help="[pgrasp] --pick_mode wide:合指後指間 = 布厚 − 這個(1.0 → 3.0mm、1.5 → 2.5mm;取代 --gap_mm)")
ap.add_argument("--wide_depth_mm", type=float, default=20.0, help="[pgrasp] 寬指深(u)mm")
ap.add_argument("--wide_thick_mm", type=float, default=6.0, help="[pgrasp] 寬指厚(n)mm")
ap.add_argument("--guard_n", type=int, default=1, help="[extract2] yp 段守衛需連續 N 次量測超過門檻才放手(預設 1 = 舊)")
ap.add_argument("--proxy_m", type=float, default=0.005, help="[drag] 代理質量 kg")
ap.add_argument("--plastic_on_release", type=int, default=0, help="[plastic] 1 = 第一隻手放手前 --plastic_pre 秒把 yn/yp 的 rest shape 改成當下形狀(寫 restShapePoints + SetActive 關→開 讓 PhysX 重建),模擬塑性;0 = 舊行為")
ap.add_argument("--plastic_on_fold", type=int, default=0, help="[plastic] 1 = 關蓋完成、放錨點之前把整張布 rest 改成當下(折好)形狀;0 = 舊行為")
ap.add_argument("--plastic_pre", type=float, default=0.2, help="[plastic] 放手前幾秒改 rest")
ap.add_argument("--plastic_region", choices=["all", "side"], default="all", help="[plastic] release 時改哪些頂點:all = 全片;side = 本片 + 鉸線內 30mm(其他頂點 rest 不變)")
ap.add_argument("--plastic_how", choices=["frame", "step"], default="step", help="[plastic] SetActive(False)→(True) 在同一幀(frame)或中間多走一步(step);frame + edamp 0.02 + jaw_collide 1 曾 segfault(PLASTIC.md)")
ap.add_argument("--plastic_filter_mm", type=float, default=-1.0, help="[plastic] 重建時把 selfCollisionFilterDistance(以 rest 形狀量)改成這個 mm;折好的 rest 層間 <1mm 會被濾掉自碰撞;<0 = 不改")
ap.add_argument("--plastic_spread_mm", type=float, default=0.0, help="[spread] >0 = 烘焙(全片)時 rest 用 plastic/spread_rest.solve 把疊層撐開到表面間距 >= d mm(邊長 = 當下);自碰撞以 rest 距離濾除,d >= 5 才保得住(PLASTIC.md A2);0 = 舊行為(rest = 當下)")
ap.add_argument("--release_watch", type=int, default=0, help="[plastic] 1 = 放手後 0.5/2/10 s 印 越線/壁外/自穿/穿杯/杯位移(--plastic_on_release 1 時自動開)")
ap.add_argument("--grasp_tail_s", type=float, default=0.0, help="[plastic] 抓取段結束後多觀察幾秒(取杯段之前);0 = 舊行為")
ap.add_argument("--unwrap_on_table", type=int, default=0, help="[table] 1 = 四折+收耳、放錨點後不入箱(箱子留在旁邊、桌面=地面),settle --ut_settle_s 後直接在桌面上掀:抬起 → 繞桌面鉸點往外翻 180° 攤平(取代越壁弧線);0 = 舊行為")
ap.add_argument("--ut_settle_s", type=float, default=2.0, help="[table] 放錨點後停幾秒才開始掀")
ap.add_argument("--ut_lift_mm", type=float, default=40.0, help="[table] 夾好後先垂直抬起 mm")
ap.add_argument("--ut_lift_t", type=float, default=1.0, help="[table] 抬起用時 s")
ap.add_argument("--ut_arc_k", type=float, default=0.9, help="[table] 翻轉弧半徑 = 這個 x 材料長(桌面鉸點 → 夾爪中心)")
ap.add_argument("--ut_end_k", type=float, default=1.0, help="[table] 終點夾爪中心離鉸點(往外)= 這個 x 材料長,z = 桌面 + T")
ap.add_argument("--ut_tape", type=int, default=1, help="[table] 1 = 放錨點時錨點不移除(當膠帶封住四片;不入箱時全放 → 整包 1.5 s 內自己彈開攤平,table/smoke 實測),掀某片夾好那一刻才移除那片的錨點;0 = 照舊全部移除")
ap.add_argument("--tape_follow", type=int, default=0, help="[v2] 1 = 放錨點時錨點不移除(膠帶),之後每步錨點 kinematic 目標 = 杯子姿態 x 放錨點那一刻的相對位姿(膠帶跟著包裹走,入箱/搬箱/取出都適用);2 = 膠帶保留但錨點固定不動(對照,= 舊 --ut_tape 在入箱流程);0 = 舊行為")
ap.add_argument("--takeout", type=int, default=0, help="[v2] 1 = 開蓋 hold 完,手 2 從上方夾住整包(杯 kinematic 跟手 + 膠帶跟杯)抬起 → 平移到箱外 −y(--tk_out_mm)桌面 → 放下、杯轉回 dynamic;之後在桌面上掀(同 --unwrap_on_table 的掀法)、取杯放旁邊")
ap.add_argument("--tk_lift_mm", type=float, default=150.0, help="[v2] 取出:垂直抬起 mm")
ap.add_argument("--tk_out_mm", type=float, default=400.0, help="[v2] 取出:放到箱中心往 −y 這麼遠的桌面上")
ap.add_argument("--v2_xflaps", type=int, default=0, help="[v2] 1 = yn/yp 掀完再掀 xn、xp(寬指純摩擦;開始時先拆該片膠帶、等 --v2_xcut_s 秒才規劃,已自己攤開就不夾)")
ap.add_argument("--v2_xcut_s", type=float, default=2.0, help="[v2] x 片:拆膠帶後等幾秒才規劃夾取")
ap.add_argument("--v2_hold_cup", type=int, default=0, help="[v2] 1 = x 片開始前手 2(取杯手)先夾住杯、扶著不動,x 片都處理完才抬走(掀 x 片時杯躺著會被布帶著滾:v2/A/3 杯被拖 115~355 mm);0 = 取杯在全部片之後才開始")
ap.add_argument("--ut_release_up", type=int, default=0, help="[v2x] 1 = 桌面掀法放手:兩指先張開到各 +20 mm,布上那根直接垂直抬(不沿 u 往外抽);布下那根(翻面後已在桌面下)在桌面下沿 u 平移出布外再抬;0 = 舊(張開 10 mm → 沿 u 抽 → 抬)")
ap.add_argument("--v2_xmode", choices=["grasp", "sweep", "outer", "tapegrip"], default="grasp", help="[v2x] x 片(拆膠帶 --v2_xcut_s 後越線 < 80%%)的做法:grasp = 舊(斜靠不夾、否則寬指夾翻);tapegrip = D 不先拆膠帶,跟 yn/yp 一樣寬指夾自由邊、夾好那一刻才拆該片膠帶、繞桌面鉸點翻;sweep = A 撥開(寬指當槳,從杯頂上方沿 ±x 壓著片往外掃到 鉸點 + 材料長 x --ut_end_k、指面高 桌面 + T,不夾);outer = B 從片外側用寬指水平夾住片的頂緣,往外、往下拉到桌面攤平")
ap.add_argument("--v2_sweep_push", type=int, default=0, help="[v2x] --v2_xmode sweep 時:1 = A2,片尖還在杯上(高於桌面 30 mm)就先用直立的槳貼著杯面把片尖往外推過杯最外緣,再做低掃;0 = A(從杯頂上方壓著掃)")
ap.add_argument("--v2_h2_free", type=int, default=0, help="[v2x2] E:--v2_hold_cup 1 + --v2_xmode tapegrip 時,x 片夾好(拆膠帶)那一刻手 2 張開、抬 --v2_h2_lift_mm(杯轉 dynamic),片翻完再回來重夾(重新量杯姿態;取杯那次要 指-布最小距離 > --v2_h2_clear_mm 才合指);0 = 舊(一直扶)")
ap.add_argument("--v2_h2_lift_mm", type=float, default=60.0, help="[v2x2] --v2_h2_free:手 2 鬆手後抬多高")
ap.add_argument("--v2_h2_clear_mm", type=float, default=2.0, help="[v2x2] --v2_h2_free:重夾杯時兩指(含張開→合的掃掠)與布的最小距離要 > 這個值;找不到就退回舊夾位(杯端外有布 → 停在 杯 + 布厚 + 1 mm)")
ap.add_argument("--v2_xpress_s", type=float, default=0.0, help="[v2x2] G:x 片(桌面掀法)放手、手指抬開後,手 1 寬指平放到 鉸點往外 --v2_xpress_mm 處,壓到 桌面 + T − 1 mm 停這麼多秒再抬開(讓鉸點附近皺褶鬆弛);0 = 不壓(舊)")
ap.add_argument("--v2_xpress_depth_mm", type=float, default=0.0, help="[v2x2] --v2_xpress_s:>0 = 壓指底 = max(桌面 + T − 1 mm, 下指那一刻足跡內布頂 − 這個值)(G 實測鉸點外有 38 mm 高的拱,壓到桌面 + T − 1 會壓爛:反轉 257、自穿 74);0 = 一律壓到桌面 + T − 1 mm")
ap.add_argument("--v2_xpress_mm", type=float, default=30.0, help="[v2x2] --v2_xpress_s:壓指中心在鉸點往外幾 mm(指深沿 x)")
ap.add_argument("--v2_xend_k", type=float, default=0.0, help="[v2x2] x 片(桌面掀法)終點 = 鉸點往外 這個 x 材料長;0 = 跟 --ut_end_k 一樣(舊)")
ap.add_argument("--v2_xrel_slide", type=int, default=0, help="[v2x2] H(2 = yn/yp 也用;整鏈 V21S/1 的 yp 同樣是上指張開時布跟著指、+2 s 翻回 129°):x 片放手時,布上那根只張開 2 mm 就沿 u 往外抽出布外再抬(--ut_release_up 的「張開 20 mm 再垂直抬」會讓片尖跟著指往上、翻回杯上:E/F 實測指-布 0.5 mm 跟到 +20 mm);布下那根照 --ut_release_up;0 = 舊")
ap.add_argument("--quality", choices=["off", "fast", "final"], default="off",
                help="[quality] fast = 開發用(dt 1/120 solver 48 vid_every 2 960x540);final = 出片(dt 1/240 solver 128);off = 舊行為。個別旗標有明確給時以個別旗標為準")
ap.add_argument("--save_state", default="", help="[speed2] npz:在 --at 時間點存 布頂點/速度、杯姿態、箱/蓋/側板、時間、量測狀態(SNAP/EV/LOGR/軌跡/RNG),之後照常跑完(--save_exit 1 存完就停)")
ap.add_argument("--at", default="grasp", help="[speed2] 存檔點:grasp = 掀開段開始前(TG0,開蓋 hold + settle 完,預設)/ opened = 開蓋 hold 結束(T_END_ALL)/ 秒數(放錨點後 ~ TG0)/ [v2x] xflaps = v2 桌面上 yn、yp 掀完、x 片開始前(要 --v2_xflaps 1)")
ap.add_argument("--save_exit", type=int, default=0, help="[speed2] 1 = 存檔後結束(不跑掀開段)")
ap.add_argument("--load_state", default="", help="[speed2] 從 --save_state 的 npz 續跑:布 points = 存檔值(rest 仍平板)、速度歸零、杯/箱/蓋/側板/錨點/地板/相機/燈 到存檔狀態,從存檔時間繼續")
a = ap.parse_args()
QUALITY_PRESET = {"fast": dict(dt=1/120.0, solver=48, vid_every=2, vid_res="960x540"),   # 1/60+solver 32 自穿 ~100、四折 bbox 差 13 mm → 退到 1/120+48(quality/F1)
                  "final": dict(dt=1/240.0, solver=128)}.get(a.quality, {})
_given = {x.split("=")[0][2:] for x in sys.argv[1:] if x.startswith("--")}
QUALITY_SET = {k: v for k, v in QUALITY_PRESET.items() if k not in _given}
for _k, _v in QUALITY_SET.items(): setattr(a, _k, _v)
WIDE = a.pick_mode == "wide"                                                  # [pgrasp] 寬指 = 走 jaw 路徑(下指挑角 → 上指合)、指面換成寬指、抓點 = 自由邊中點
if WIDE: a.pick_mode = "jaw"; a.gap_mm = a.thick_mm - a.wide_squeeze_mm
if a.tuck == 0:
    a.squeeze_t = 0.0
if a.until == "yn":                                                           # [speed2] 只跑到 yn 片結束
    a.second = 0; a.extract = 0
UT = bool(a.unwrap_on_table)                                                 # [table] 桌面上掀開(不入箱、不取杯)
if UT: a.extract = 0
TK = bool(a.takeout) and not UT                                               # [v2] 入箱 → 搬 → 開蓋 → 整包取出到桌面 → 桌面掀開
UTT = UT or TK                                                                # [v2] 掀開段用桌面掀法(UT 或取出後)
TAPE = bool(UT and a.ut_tape) or a.tape_follow > 0                            # [v2] 放錨點時錨點保留(膠帶)
LOADED = None
if a.load_state:                                                              # [speed2] 讀存檔(場景建好、world.reset 之前套用)
    import pickle as _pk
    _ld = np.load(a.load_state)
    LOADED = dict(_pk.loads(_ld["meta"].tobytes()), pts=_ld["pts"].astype(float), vel=_ld["vel"].astype(float), traj_t=list(_ld["traj_t"]),
                  traj_p=list(_ld["traj_p"]), traj_m=list(_ld["traj_m"]))
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
os.makedirs(a.out, exist_ok=True)
T = a.thick_mm / 1e3
WX = (a.sheet_x_mm or a.sheet_mm) / 1e3; WY = (a.sheet_y_mm or a.sheet_mm) / 1e3
WA = (WX, WY)                      # 依軸取邊長
W = max(WX, WY)                    # 只用在側板起始位置等「夠大就好」的地方
MOVE = np.array([float(x) for x in a.movebox.split(",")])
FOLD_ORDER = [x.strip() for x in a.fold_order.split(",")]   # [variants] 從 --fold_order;預設 xp,xn,yp,yn
assert sorted(FOLD_ORDER) == ["xn", "xp", "yn", "yp"], "--fold_order 要是 xp,xn,yp,yn 的排列"
MOFF = np.array([float(x) for x in a.mug_off_mm.split(",")]) / 1e3   # [variants] 杯子相對布中心
SC = -MOFF                                     # [variants] 布中心(杯子/佔位/箱子留在原點)
np.random.seed(a.seed)
UORDER = list(reversed(FOLD_ORDER))

def kv(s):
    d = {}
    for it in [x for x in s.split(",") if x]:
        k, v = it.split(":"); d[k] = float(v)
    return d
SLOW = kv(a.slow); TIPX = kv(a.tip_extra)

LOG = open(os.path.join(a.out, "wrap_vol.log"), "w")
def P(*s):
    m = " ".join(str(x) for x in s); print(m, flush=True); LOG.write(m + "\n"); LOG.flush()

os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import carb, omni.physx.bindings._physx as pxb
carb.settings.get_settings().set(pxb.SETTING_ENABLE_DEFORMABLE_BETA, True)
from isaacsim.core.api import World
from isaacsim.core.prims import SingleXFormPrim
from isaacsim.sensors.camera import Camera
from pxr import Usd, Gf, Sdf, UsdGeom, UsdPhysics, UsdShade, UsdLux, PhysxSchema, Vt
import omni.usd, imageio, trimesh
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, HERE)
import volcommon as VC
import vol_pen as VP
import grip_common as G
import layer_gap as LG

P("=== wrap_vol sheet %.0f ===" % a.sheet_mm); P("args:", vars(a))
P("quality: %s | dt 1/%.0f solver %d vid_every %d vid_res %s | preset 套用 %s(明確旗標優先)" % (a.quality, 1/a.dt, a.solver, a.vid_every, a.vid_res, sorted(QUALITY_SET) or "無"))
world = World(physics_dt=a.dt, rendering_dt=a.dt)
world.scene.add_default_ground_plane()
st = omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(st, 1.0); UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
pxs = PhysxSchema.PhysxSceneAPI.Apply(st.GetPrimAtPath("/physicsScene"))
pxs.CreateEnableGPUDynamicsAttr(True); pxs.CreateBroadphaseTypeAttr("GPU")
for at, v in [("CreateGpuCollisionStackSizeAttr", 128*1024*1024),
              ("CreateGpuFoundLostAggregatePairsCapacityAttr", 8192)]:
    try: getattr(pxs, at)(v)
    except Exception: pass

# ── 材質 [ws] ─────────────────────────────────────────────────────────
def vmat(path, col, op, rough=.25, ior=None):
    m = UsdShade.Material.Define(st, path); s = UsdShade.Shader.Define(st, path + "/S")
    s.CreateIdAttr("UsdPreviewSurface")
    s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*col))
    s.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    s.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(op)
    s.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(ior if ior is not None else (1.0 if op < 0.99 else 1.5))
    m.CreateSurfaceOutput().ConnectToSource(s.ConnectableAPI(), "surface"); return m

def film_tex(path, tex):
    m = UsdShade.Material.Define(st, path)
    sh = UsdShade.Shader.Define(st, path + "/S"); sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.90, .95, .97))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.18)
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
    sh.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.0)
    st_r = UsdShade.Shader.Define(st, path + "/st"); st_r.CreateIdAttr("UsdPrimvarReader_float2")
    st_r.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    st_r.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    nt = UsdShade.Shader.Define(st, path + "/nrm"); nt.CreateIdAttr("UsdUVTexture")
    nt.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(tex)
    nt.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_r.ConnectableAPI(), "result")
    nt.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(2, 2, 2, 1))
    nt.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(-1, -1, -1, 0))
    nt.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
    nt.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
    nt.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    sh.CreateInput("normal", Sdf.ValueTypeNames.Normal3f).ConnectToSource(nt.ConnectableAPI(), "rgb")
    m.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return m
FILM = film_tex("/World/film", os.path.abspath(a.tex))
MUGM = vmat("/World/mugm", (144/255./1.19*0.894, 163/255./1.11*0.931, 189/255./1.005), 1.0, .40)

# ── 杯子 [ws] ─────────────────────────────────────────────────────────
m_ = trimesh.load(a.mug)
V = np.asarray(m_.vertices, float); F = np.asarray(m_.faces)
unit = 0.001 if V.ptp(0).max() > 1.0 else 1.0
V = (V - V.mean(0)) * unit
Ry = lambda t: np.array([[np.cos(t), 0, np.sin(t)], [0, 1, 0], [-np.sin(t), 0, np.cos(t)]])
Rx = lambda t: np.array([[1, 0, 0], [0, np.cos(t), -np.sin(t)], [0, np.sin(t), np.cos(t)]])
Rz = lambda t: np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1]])
V = V @ Ry(-np.pi/2).T @ Rx(np.pi/2).T @ Rz(-np.pi/2).T      # 基準姿態:杯口 +y、杯耳 −x
_Rm = np.array([[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]])
V = V @ _Rm.T
V -= (V.max(0) + V.min(0)) / 2.0
if a.mug_yaw_deg: V = V @ Rz(np.radians(a.mug_yaw_deg)).T; V -= (V.max(0) + V.min(0)) / 2.0   # [variants]
ME = V.max(0) - V.min(0); hx, hy, H2 = ME / 2.0
MUG_VOL = float(np.prod(ME))
P("杯子躺平 %.0f x %.0f x %.0f mm;杯口 +y、杯耳 +x;watertight=%s" % (*(ME*1e3), m_.is_watertight))
A_, B_ = ME[0] + 2*a.margin, ME[1] + 2*a.margin
CX, CY = A_/2 + a.wall, B_/2 + a.wall
P("折線 CX=%.2f CY=%.2f mm;折邊長 x %.1f / y %.1f mm" % (CX*1e3, CY*1e3, (WX/2-CX)*1e3, (WY/2-CY)*1e3))

# ── 板 ───────────────────────────────────────────────────────────────
ZB = 0.001
REST_NPZ = None
if a.rest_npz:
    REST_NPZ = np.load(a.rest_npz)["fold_end_tet"]
info = VC.build_plate(st, "/World/plate", WX, T, ZB, "manual", nxy=a.nxy, nz=1, youngs=a.young, poisson=a.poisson,
                      areal=a.areal, fric=a.fric, cont=a.cont, rest=a.rest, solver=a.solver, self_coll=True,
                      self_filter=2*a.rest, ldamp=a.ldamp, edamp=a.edamp, P=P, size_y=WY, cx=float(SC[0]), cy=float(SC[1]))
P("阻尼 ldamp=%g edamp=%g" % (a.ldamp, a.edamp))
PLATE = VC.Mesh(st, "/World/plate")
FLAT = PLATE.pts().copy(); TETS = PLATE.tets()
N1 = (a.nxy + 1) ** 2
assert len(FLAT) == 2 * N1
BOT, TOP = np.arange(N1), np.arange(N1, 2 * N1)
V0 = VP.tet_vol(FLAT, TETS)
EDG = np.unique(np.sort(np.concatenate([TETS[:, [i, j]] for i in range(4) for j in range(i + 1, 4)]), axis=1), axis=0)
L0 = np.linalg.norm(FLAT[EDG[:, 0]] - FLAT[EDG[:, 1]], axis=1)
if REST_NPZ is not None:
    assert len(REST_NPZ) == len(FLAT)
    PLATE.prim.GetAttribute("omniphysics:restShapePoints").Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, q)) for q in REST_NPZ]))
    V0 = VP.tet_vol(REST_NPZ, TETS)
    P("★ --rest_npz %s:restShapePoints = 折好的形狀(points 仍平);反轉以它為基準" % a.rest_npz)
UsdGeom.Imageable(PLATE.prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
P("板 %.0fx%.0fx%.0fmm:%d 點 %d tets;dxy %.2fmm;solver %d dt 1/%.0f" % (WX*1e3, WY*1e3, T*1e3, len(FLAT), len(TETS),
                                                                   WX/a.nxy*1e3, a.solver, 1/a.dt))

# 視覺網格(外表面三角形),每個渲染幀寫入 sim 頂點
n = a.nxy
gid = lambda i, j, k: k * N1 + j * (n + 1) + i
VF = []
for j in range(n):
    for i in range(n):
        VF += [(gid(i, j, 1), gid(i+1, j, 1), gid(i+1, j+1, 1)), (gid(i, j, 1), gid(i+1, j+1, 1), gid(i, j+1, 1))]
        VF += [(gid(i, j, 0), gid(i+1, j+1, 0), gid(i+1, j, 0)), (gid(i, j, 0), gid(i, j+1, 0), gid(i+1, j+1, 0))]
for s_ in range(n):
    for (p0, p1) in [((s_, 0), (s_+1, 0)), ((n, s_), (n, s_+1)), ((s_+1, n), (s_, n)), ((0, s_+1), (0, s_))]:
        a0, a1 = gid(*p0, 0), gid(*p1, 0); b0, b1 = gid(*p0, 1), gid(*p1, 1)
        VF += [(a0, a1, b1), (a0, b1, b0)]
VF = np.array(VF, int)
vis = UsdGeom.Mesh.Define(st, "/World/sheet_vis")
vis.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in FLAT]))
vis.CreateFaceVertexCountsAttr([3] * len(VF)); vis.CreateFaceVertexIndicesAttr([int(x) for x in VF.ravel()])
vis.CreateSubdivisionSchemeAttr().Set("none"); vis.CreateDoubleSidedAttr(True)
_tl = a.tex_mm / 1000.0
UsdGeom.PrimvarsAPI(vis.GetPrim()).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex).Set(
    Vt.Vec2fArray([Gf.Vec2f(float(p[0]/_tl), float(p[1]/_tl)) for p in FLAT]))
UsdShade.MaterialBindingAPI.Apply(vis.GetPrim()).Bind(FILM)
VISPTS = vis.GetPointsAttr()
P("視覺網格 /World/sheet_vis:%d 三角形(上/下/側面),泡泡法線貼圖 %s" % (len(VF), a.tex))

# ── 杯子剛體 [ws] ───────────────────────────────────────────────────
PLATE_TOP0 = a.rest + T
MZ = PLATE_TOP0 + 0.002 + H2
MUGTOP = MZ + H2
mug = UsdGeom.Xform.Define(st, "/World/mug")
UsdGeom.Xformable(mug).AddTranslateOp().Set(Gf.Vec3d(0, 0, MZ))
UsdPhysics.RigidBodyAPI.Apply(mug.GetPrim()).CreateKinematicEnabledAttr(True)
prb = PhysxSchema.PhysxRigidBodyAPI.Apply(mug.GetPrim())
prb.CreateLinearDampingAttr(0.3); prb.CreateAngularDampingAttr(0.6)
UsdPhysics.MassAPI.Apply(mug.GetPrim()).CreateMassAttr(0.0807)
g = UsdGeom.Mesh.Define(st, "/World/mug/geo")
g.CreatePointsAttr([Gf.Vec3f(*map(float, p)) for p in V])
g.CreateFaceVertexIndicesAttr([int(i) for f in F for i in f])
g.CreateFaceVertexCountsAttr([3]*len(F)); g.CreateSubdivisionSchemeAttr().Set("none")
g.CreateDoubleSidedAttr(True)
UsdPhysics.CollisionAPI.Apply(g.GetPrim())
UsdPhysics.MeshCollisionAPI.Apply(g.GetPrim()).CreateApproximationAttr("convexDecomposition")
gc = PhysxSchema.PhysxCollisionAPI.Apply(g.GetPrim())
gc.CreateContactOffsetAttr(0.004); gc.CreateRestOffsetAttr(0.001)
UsdShade.MaterialBindingAPI.Apply(g.GetPrim()).Bind(MUGM)
MTRI = trimesh.Trimesh(V, F, process=False)
P("杯子 kinematic,底 z=%.1f 頂 z=%.1f mm" % ((MZ-H2)*1e3, MUGTOP*1e3))

# ── 折疊錨(每邊一根 kinematic 桿,無碰撞;VtxXformAttachment 綁該邊最外圈上下兩層)────
DXY = (WX / a.nxy, WY / a.nxy)
fx_, fy_ = FLAT[:, 0], FLAT[:, 1]
def sidepick(fx, fy):
    """[ws] SIDEPICK:以『超出折線多少』分邊,角落歸較大者(x 長邊 ⇒ 角落歸 y)。"""
    sx = max(0.0, abs(fx) - CX); sy = max(0.0, abs(fy) - CY)
    return ("yp" if fy > 0 else "yn") if sy >= sx else ("xp" if fx > 0 else "xn")
Z0 = a.rest + T / 2
SIDES = {}
for sd in FOLD_ORDER:
    ax = 0 if sd[0] == "x" else 1; sg = 1.0 if sd[1] == "p" else -1.0
    C = CX if ax == 0 else CY
    EDGE = SC[ax] + sg * WA[ax] / 2              # [variants] 布邊位置(布可能偏)
    outer = np.abs(FLAT[:, ax] - EDGE) < 1e-6
    picked = np.array([v for v in np.where(outer)[0] if sidepick(fx_[v], fy_[v]) == sd], int)
    _k = FOLD_ORDER.index(sd)
    _bar = not any(SIDES_AX != ax for SIDES_AX in [0 if q[0] == "x" else 1 for q in FOLD_ORDER[:_k]])   # [variants] 另一軸都還沒折 = 整根桿
    if _bar:
        # 先折的兩邊:整條邊,不含角落(角落 SIDEPICK 歸 y)
        # 先折的兩邊:SIDEPICK 歸本邊的最外圈,再只留 |y| <= CY(杯子 y 範圍 + margin + wall)。
        # ★ 實測(out_v400_fold 第 1、2 版):照 SIDEPICK 抓到 |y|<=177 時,4mm 板的 x 折邊兩端(角落區)被桿釘在
        #   y=±177 的杯頂上,入箱前 y 超出內腔(±112)163~497 點;內腔 224mm 根本放不下 ±177 的錨點。
        vids = picked[np.abs(FLAT[picked, 1 - ax]) <= (CY if ax == 0 else CX) + 1e-6]
    else:
        # 後折的兩邊:只抓前兩折期間仍貼地的那段(|另一軸| <= 對方折線),等同 surface 版 floor_edges
        Co = CX if ax == 1 else CY
        vids = picked[np.abs(FLAT[picked, 1 - ax]) <= Co - 0.25 * DXY[1 - ax]]
    SIDES[sd] = dict(ax=ax, sg=sg, C=C, R=sg*EDGE - C, vids=vids, k=_k, bar=_bar)
    P("錨 %s:最外圈 %d 點中 SIDEPICK 歸本邊 %d,綁 %d 點(上下兩層)" % (sd, int(outer.sum()), len(picked), len(vids)))

# 終點:尖端底面停在 杯頂 + 已疊層數 x (T+1mm) + 2mm;已疊層數 = 先前折的 flap 頂面範圍與本折重疊者
def plan_ends():
    for sd in FOLD_ORDER:
        S_ = SIDES[sd]
        prev = FOLD_ORDER[:S_["k"]]
        other = [pd for pd in prev if SIDES[pd]["ax"] != S_["ax"]]
        same = [pd for pd in prev if SIDES[pd]["ax"] == S_["ax"]]
        lay = 0
        if other:      # 另一軸先折的片在下面:兩片各佔一側,彼此重疊(尖端越過中線)才算兩層
            lay += 1
            if len(other) == 2 and SIDES[other[0]].get("along_end", 1) + SIDES[other[1]].get("along_end", 1) < 0:
                lay += 1
        for pd in same:
            if SIDES[pd]["along_end"] + S_.get("along_end", S_["C"]) < 0:
                lay += 1
        S_["lay"] = lay
        S_["zend"] = MUGTOP + lay * (T + 0.001) + 0.002 + T / 2 + TIPX.get(sd, TIPX.get("all", 0.0)) / 1e3
        S_["arm"] = S_["R"] - (S_["zend"] - Z0)
        S_["along_end"] = max(-a.tip_over_mm / 1e3, S_["C"] - S_["arm"])
plan_ends(); plan_ends()
for sd in FOLD_ORDER:
    S_ = SIDES[sd]
    P("  %s:折線 %.1f、折邊 %.1f、已疊 %d 層 → 尖端中面 z=%.1f(底面 %.1f)、越過頂面 arm %.1f → 尖端 along=%.1f mm%s"
      % (sd, S_["C"]*1e3, S_["R"]*1e3, S_["lay"], S_["zend"]*1e3, (S_["zend"]-T/2)*1e3, S_["arm"]*1e3,
         S_["along_end"]*1e3, ("(搆不到中線)" if S_["along_end"] > 0.001 else "(到/越過中線)") + (" ★ infeasible:折邊搆不到杯頂(arm<0)" if S_["arm"] < 0 else "")))

UsdGeom.Xform.Define(st, "/World/bars")
def qaxis(axis, ang):
    axis = np.asarray(axis, float); axis /= np.linalg.norm(axis)
    return np.array([np.cos(ang/2), *(np.sin(ang/2) * axis)])
def qmul(p, q):
    w1, x1, y1, z1 = p; w2, x2, y2, z2 = q
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2, w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])
QI = np.array([1.0, 0, 0, 0])

def xmap(S_, s, u):
    """[ws wrap_arc_from 改寫] 折邊上離折線 s 的點,在折疊進度 u 時的 (along, z, 轉角)。
    A 段 繞底部折線 (C,Z0) 轉 90°;B 段 立起高度 H=zend-Z0 以內停在側面,超過的部分繞頂部折線 (C,zend) 再轉 90°。
    s = R 就是邊緣(桿)。半徑都 = 該點到折線的材料長度 ⇒ 不拉伸。"""
    C, ze = S_["C"], S_["zend"]; H = ze - Z0
    if u <= 0.5:
        th = np.pi * u
        return C + s*np.cos(th), Z0 + s*np.sin(th), th
    ps = np.pi * (u - 0.5)
    if s <= H:
        return C, Z0 + s, np.pi/2
    h = s - H
    return max(-a.tip_over_mm/1e3, C - h*np.sin(ps)), ze + h*np.cos(ps), np.pi/2 + ps

def yarc(S_, cur, u):
    """[ws wrap_arc_from] 後折的錨從**它當下的位置**起弧:A 段繞底部折線把它轉到正上方(半徑 = 當下到折線距離),
    B 段繞頂部折線 (C,zend) 蓋過去。回傳 (along, z, 本折累計轉角)。"""
    C, ze = S_["C"], S_["zend"]
    a0 = S_["sg"]*cur[S_["ax"]] - C; z0 = cur[2] - Z0
    Rv = float(np.hypot(max(a0, 1e-6), z0)); th0 = float(np.arctan2(z0, max(a0, 1e-6)))
    if u <= 0.5:
        th = th0 + (np.pi/2 - th0)*(u/0.5)
        return C + Rv*np.cos(th), Z0 + Rv*np.sin(th), th - th0
    ps = np.pi * (u - 0.5); h0 = Z0 + Rv - ze
    return max(-a.tip_over_mm/1e3, C - h0*np.sin(ps)), ze + h0*np.cos(ps), np.pi/2 - th0 + ps

ANC = []          # 每個 kinematic 錨:x 邊一根桿;y 邊每一欄一個(上下兩點)
for sd, S_ in SIDES.items():
    _ax = S_["ax"]; _o = 1 - _ax
    if S_["bar"]:
        ctr = np.zeros(3); ctr[_ax] = SC[_ax] + S_["sg"] * WA[_ax] / 2; ctr[2] = Z0
        groups = [(sd, ctr, S_["vids"])]
    else:
        groups = []
        cols = np.unique(np.round(FLAT[S_["vids"], _o], 6))
        for ci, cx_ in enumerate(cols):
            vv = S_["vids"][np.abs(FLAT[S_["vids"], _o] - cx_) < 1e-6]
            _c = np.zeros(3); _c[_o] = cx_; _c[_ax] = SC[_ax] + S_["sg"] * WA[_ax] / 2; _c[2] = Z0
            groups.append(("%s_c%02d" % (sd, ci), _c, vv))
    for nm_, ctr, vv in groups:
        pth = "/World/bars/" + nm_
        VC.kin_box(st, pth, [0.004, 0.004, 0.004], ctr, collide=False, visible=False)
        sc = "/World/attach/" + nm_
        VC.attach_vtx(st, sc, "/World/plate", "/World/plate", pth, vv, FLAT[vv] - ctr, P=lambda *x: None)
        ANC.append(dict(nm=nm_, side=sd, path=pth, scope=sc, c0=ctr, vids=vv))
P("錨:%d 個 kinematic 錨體(x 邊各 1 根桿;y 邊每欄 1 個,共 %d 欄),全部無碰撞;VtxXformAttachment 掛 /World/attach/*"
  % (len(ANC), sum(1 for A in ANC if A["side"][0] == "y")))

def anchor_pose(A, t):
    sd = A["side"]; S_ = SIDES[sd]
    _ax = S_["ax"]; _o = 1 - _ax
    _rot = lambda ax_, sg_: [0, -sg_, 0] if ax_ == 0 else [sg_, 0, 0]   # [variants] 繞折線轉的軸
    if S_["bar"]:
        t0, sp_ = FT[sd]; u = ss((t - t0)/sp_)
        al, z, ang = xmap(S_, S_["R"], u)
        p = np.zeros(3); p[_ax] = S_["sg"]*al; p[2] = z
        return p, qaxis(_rot(_ax, S_["sg"]), ang)
    # y 邊的一欄:先跟著 x 折(若這欄在 x 折邊上 = 角落『耳朵』),再做自己的 y 折
    cx_ = A["c0"][_o]
    sdx = ("xy"[_o]) + ("p" if cx_ > 0 else "n"); Sx = SIDES[sdx]
    s = abs(cx_) - Sx["C"]
    def xstate(tt):
        if s <= 0: return A["c0"].copy(), QI
        t0x, spx = FT[sdx]; ux = ss((tt - t0x)/spx)
        al, z, ang = xmap(Sx, s, ux)
        q_ = A["c0"].copy(); q_[_o] = Sx["sg"]*al; q_[2] = z
        return q_, qaxis(_rot(_o, Sx["sg"]), ang)
    t0, sp_ = FT[sd]
    if t < t0:
        return xstate(t)
    if "ystart" not in A:
        A["ystart"] = xstate(t0)
    cur, qx = A["ystart"]
    u = ss((t - t0)/sp_)
    al, z, ang = yarc(S_, cur, u)
    p = cur.copy(); p[_ax] = S_["sg"]*al; p[2] = z
    return p, qmul(qaxis(_rot(_ax, S_["sg"]), ang), qx)

# ── 收耳朵用的四面側板(kinematic、不可見):四折完從外面收到紙箱內腔 −squeeze_mm ────
PADS = []
PAD_H = 0.16
for nm_, ax_, sg_ in (("pxp", 0, 1), ("pxn", 0, -1), ("pyp", 1, 1), ("pyn", 1, -1)):
    sz = [W + 0.12, W + 0.12, PAD_H]; sz[ax_] = 0.010
    c_ = np.zeros(3); c_[ax_] = sg_ * (W/2 + float(np.abs(MOFF).max()) + 0.03 + 0.005); c_[2] = PAD_H/2 + 0.0005
    pr_ = VC.kin_box(st, "/World/pads/" + nm_, sz, c_, collide=True, visible=False)
    _pc = PhysxSchema.PhysxCollisionAPI.Apply(st.GetPrimAtPath("/World/pads/%s/geom" % nm_))
    _pc.CreateContactOffsetAttr(0.002); _pc.CreateRestOffsetAttr(0.0005)
    PADS.append(dict(nm=nm_, ax=ax_, sg=sg_, c0=c_, path="/World/pads/" + nm_))

# ── 紙箱 [ws] ────────────────────────────────────────────────────────
_bx = st.DefinePrim("/World/Box", "Xform")
_bx.GetReferences().AddReference(os.path.abspath(a.carton))
_nk = 0
for _p in Usd.PrimRange(_bx):
    if _p.HasAPI(UsdPhysics.RigidBodyAPI):
        _at = _p.GetAttribute("physics:kinematicEnabled")
        (_at if _at and _at.IsValid() else _p.CreateAttribute("physics:kinematicEnabled", Sdf.ValueTypeNames.Bool)).Set(True)
        _nk += 1
_CB = vmat("/World/cartonmat", (0.62, 0.46, 0.29), 1.0, 0.85)
for _p in Usd.PrimRange(_bx):
    if _p.IsA(UsdGeom.Gprim):
        UsdShade.MaterialBindingAPI.Apply(_p).Bind(_CB, UsdShade.Tokens.strongerThanDescendants)
UsdShade.MaterialBindingAPI.Apply(_bx).Bind(_CB, UsdShade.Tokens.strongerThanDescendants)
_rr = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(_bx).ComputeAlignedRange()
CDZ = float(_rr.GetMin()[2]) + 0.003            # 箱底內面(箱子在原點時)
ZHI0 = float(_rr.GetMax()[2])                   # 箱口(含關著的蓋)最高點
BOXC = np.array([(_rr.GetMin()[0]+_rr.GetMax()[0])/2, (_rr.GetMin()[1]+_rr.GetMax()[1])/2])
_mj = os.path.splitext(os.path.abspath(a.carton))[0] + ".meta.json"
_dv = json.load(open(_mj))["derived"]
CBOX = dict(ix=float(_dv["wall_inner_x"]), iy=float(_dv["wall_inner_y"]), top=float(_dv["wall_top_x"]),
            top_y=float(_dv["wall_top_y"]), hz_lo=float(_dv["lower_hinge_z"]), hz_up=float(_dv["upper_hinge_z"]))
P("★ 紙箱 %s(meta %s):%d 剛體 kinematic;bbox %.0fx%.0fx%.0f;箱底內面 z=%.1f、箱口最高 %.1f;內腔 ±%.0f x ±%.0f;鉸鏈 %.1f/%.1f"
  % (a.carton, os.path.basename(_mj), _nk, *((np.array(_rr.GetMax())-np.array(_rr.GetMin()))*1e3), CDZ*1e3, ZHI0*1e3,
     CBOX["ix"]*1e3, CBOX["iy"]*1e3, CBOX["hz_lo"]*1e3, CBOX["hz_up"]*1e3))
if a.base_collider_pad > 0:
    _bt = st.GetPrimAtPath("/World/Box/base/bottom")
    _br = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(
        _bt if _bt.IsValid() else st.GetPrimAtPath("/World/Box/base")).ComputeAlignedRange()
    _lo, _hi = np.array(_br.GetMin()), np.array(_br.GetMax())
    _ctr = np.array([(_lo[0]+_hi[0])/2, (_lo[1]+_hi[1])/2, _lo[2] - a.base_collider_pad/2])
    _pad = UsdGeom.Cube.Define(st, "/World/Box/base/pad_collider"); _pad.CreateSizeAttr(1.0)
    _Wb = UsdGeom.Xformable(st.GetPrimAtPath("/World/Box/base")).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    _pxx = UsdGeom.Xformable(_pad)
    _pxx.AddTranslateOp().Set(_Wb.GetInverse().Transform(Gf.Vec3d(*map(float, _ctr))))
    _pxx.AddScaleOp().Set(Gf.Vec3f(float(_hi[0]-_lo[0]), float(_hi[1]-_lo[1]), float(a.base_collider_pad)))
    UsdPhysics.CollisionAPI.Apply(_pad.GetPrim()); _pad.CreatePurposeAttr(UsdGeom.Tokens.guide)
    P("★ 底板碰撞加厚 %.0fmm(不可見)" % (a.base_collider_pad*1e3))

def _rodr(v, h, ax, deg):
    ax = np.asarray(ax, float)/np.linalg.norm(ax); th = np.radians(deg); r = np.asarray(v, float) - h
    return h + r*np.cos(th) + np.cross(ax, r)*np.sin(th) + ax*np.dot(ax, r)*(1.0 - np.cos(th))
LIDS = []
_hx, _hy = CBOX["ix"], CBOX["iy"]
for nm, hinge, axis, order in (("fxp", (_hx, 0.0, CBOX["hz_lo"]), (0.0, 1.0, 0.0), 0),
                               ("fxn", (-_hx, 0.0, CBOX["hz_lo"]), (0.0, -1.0, 0.0), 0),
                               ("fyp", (0.0, _hy, CBOX["hz_up"]), (-1.0, 0.0, 0.0), 1),
                               ("fyn", (0.0, -_hy, CBOX["hz_up"]), (1.0, 0.0, 0.0), 1)):
    pr = st.GetPrimAtPath("/World/Box/" + nm)
    L = dict(nm=nm, h=np.array(hinge), ax=np.array(axis), order=order,
             T0=Gf.Matrix4d(UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(Usd.TimeCode.Default())))
    _r = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(pr).ComputeAlignedRange()
    _c = (np.array(_r.GetMin()) + np.array(_r.GetMax()))/2.0
    L["sgn"] = 1.0 if _rodr(_c, L["h"], L["ax"], 90)[2] >= _rodr(_c, L["h"], L["ax"], -90)[2] else -1.0
    L["rest_closed"] = bool(np.linalg.norm(_c[:2]) < np.linalg.norm(L["h"][:2]))
    L["c_loc"] = L["T0"].GetInverse().Transform(Gf.Vec3d(*map(float, _c)))
    L["cz0"] = _c[2]
    L["zmin0"] = float(_r.GetMin()[2])        # 關著時蓋子底面(箱子在原點)
    LIDS.append(L)
    P("  蓋 %s:USD 預設中心 z=%.1f → %s;開 = 轉 %s180°" % (nm, _c[2]*1e3, "關" if L["rest_closed"] else "開",
                                                        "+" if L["sgn"] > 0 else "−"))
BASE_T0 = Gf.Matrix4d(UsdGeom.Xformable(st.GetPrimAtPath("/World/Box/base")).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))

def lid_M(L, deg):
    h = Gf.Vec3d(*[float(x) for x in L["h"]])
    return (Gf.Matrix4d().SetTranslate(-h) * Gf.Matrix4d().SetRotate(
        Gf.Rotation(Gf.Vec3d(*[float(x) for x in L["ax"]]), float(deg)*L["sgn"])) * Gf.Matrix4d().SetTranslate(h))
def lid_pose(L, deg, off):
    Wm = L["T0"] * lid_M(L, deg)
    q = Wm.ExtractRotationQuat()
    return (np.array([float(x) for x in Wm.ExtractTranslation()]) + off,
            np.array([float(q.GetReal()), *[float(x) for x in q.GetImaginary()]]))
OFF_SIDE = np.array([-0.80, 0.45, -CDZ])
# reset 前:箱子擺到旁邊、蓋子擺開(180°)[ws「reset 前」]
for pth, Wm in [("/World/Box/base", BASE_T0)] + [("/World/Box/" + L["nm"], L["T0"] * lid_M(L, 180.0)) for L in LIDS]:
    _pr = st.GetPrimAtPath(pth)
    _Wm2 = Wm * Gf.Matrix4d().SetTranslate(Gf.Vec3d(*map(float, OFF_SIDE)))
    _par = UsdGeom.Xformable(_pr.GetParent()).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    _xf = UsdGeom.Xformable(_pr); _xf.ClearXformOpOrder(); _xf.AddTransformOp().Set(_Wm2 * _par.GetInverse())
P("★ 紙箱 reset 前擺到旁邊 %s mm、蓋子開(180°);箱底內面對齊地面(z 偏 −%.1fmm)" % (np.round(OFF_SIDE*1e3), CDZ*1e3))

# ── 抓取段的 kinematic 指(--grasp 1):挑角單指 rod + 平行夾爪上/下指;實體不可見,另放純視覺方塊 ──
if a.grasp:
    sys.path.insert(0, os.path.join(HERE, "grip"))
    import gutil as GU
    GFS = np.array([a.finger_mm / 1e3, a.finger_mm / 1e3, 0.008])        # 指面 (t,u,n)  [jaw2] finger_mm 預設 20 = 舊
    if WIDE: GFS = np.array([a.wide_mm, a.wide_depth_mm, a.wide_thick_mm]) / 1e3   # [pgrasp]
    GRS = np.array([0.008, 0.030, 0.008])        # 挑角單指(8mm 方桿,沿 u 30mm)
    GPARK = {"rod": np.array([3.0, 3.0, 1.0]), "up": np.array([3.0, 3.1, 1.0]), "lo": np.array([3.0, 3.2, 1.0])}
    GPATH = {k: "/World/gfing/" + k for k in GPARK}
    GVIS = {}
    for k_ in GPARK:
        GU.finger(st, GPATH[k_], GRS if k_ == "rod" else GFS, GPARK[k_], 0.5 if k_ == "rod" else a.ffric, cont=0.001, rest=0.0)
        UsdGeom.Imageable(st.GetPrimAtPath(GPATH[k_])).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
        GVIS[k_] = GU.VisBox(st, "/World/gvis_" + k_, GRS if k_ == "rod" else GFS,
                             (0.2, 0.7, 0.25) if k_ == "rod" else (0.9, 0.45, 0.1))
        GVIS[k_].set(GPARK[k_])
    GFSX = None; SWX = dict(on=False)                                         # [v2x2] --wide_mm_x:x 片用另一組寬指 upW / loW
    if WIDE and a.wide_mm_x > 0:
        GFSX = np.array([a.wide_mm_x, a.wide_depth_mm, a.wide_thick_mm]) / 1e3
        for k_, pk_ in (("upW", [3.0, 4.0, 1.0]), ("loW", [3.0, 4.1, 1.0])):
            GPARK[k_] = np.array(pk_); GPATH[k_] = "/World/gfing/" + k_
            GU.finger(st, GPATH[k_], GFSX, GPARK[k_], a.ffric, cont=0.001, rest=0.0)
            UsdGeom.Imageable(st.GetPrimAtPath(GPATH[k_])).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            GVIS[k_] = GU.VisBox(st, "/World/gvis_" + k_, GFSX, (0.9, 0.45, 0.1)); GVIS[k_].set(GPARK[k_])
    class SBox:                                                               # [jaw2] 純視覺方塊(可改尺寸)
        def __init__(s, path, color, size):
            cb = UsdGeom.Cube.Define(st, path); cb.CreateSizeAttr(1.0); xf = UsdGeom.Xformable(cb)
            s.t = xf.AddTranslateOp(); s.o = xf.AddOrientOp(); s.s = xf.AddScaleOp()
            GU.bind_vis(st, cb.GetPrim(), color, "vis_%d_%d_%d" % tuple(int(c * 100) for c in color))
            s.set([3.0, 3.5, 1.0], [1, 0, 0, 0], size)
        def set(s, c, q=None, size=None):
            s.t.Set(Gf.Vec3d(*map(float, c)))
            if q is not None: s.o.Set(Gf.Quatf(*map(float, q)))
            if size is not None: s.s.Set(Gf.Vec3f(*map(float, size)))
    JV, JVS = {}, {}
    if a.hand1_jaw and not a.jaw_collide: JV["lov"] = SBox("/World/gvis_lov", (0.9, 0.45, 0.1), GFS)
    KOV = {}; LOJ = bool(a.jaw_collide and a.hand1_jaw and a.grasp_attach); JM = {}   # [jaw3] KOV = 每步覆寫的指 pose;LOJ = 實體下指 lo 走下指路徑;JM = 合指後指-布最小距離
    P("★ --grasp 1:kinematic 指 rod %s / 上下指 %s mm,指面摩擦 %.1f(rod 0.5),cont 1 / rest 0;停在 %s"
      % (GRS*1e3, GFS*1e3, a.ffric, GPARK["rod"]))
    if a.hand2 != "off":                                                       # [hand2] 第二隻手(壓板 / 綁定方塊)
        H2S = np.array([0.040, 0.030, 0.004]); GPARK["h2"] = np.array([3.0, 3.3, 1.0]); GPATH["h2"] = "/World/gfing/h2"
        if a.hand2 == "press": GU.finger(st, GPATH["h2"], H2S, GPARK["h2"], a.fric, cont=0.001, rest=0.0)
        else: VC.kin_box(st, GPATH["h2"], H2S, GPARK["h2"], collide=False, visible=False)
        UsdGeom.Imageable(st.GetPrimAtPath(GPATH["h2"])).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
        GVIS["h2"] = GU.VisBox(st, "/World/gvis_h2", H2S, (0.15, 0.4, 0.9)); GVIS["h2"].set(GPARK["h2"])
        if a.hand2 == "jaw":                                                  # [jaw2] 綁定錨方塊不顯示,改畫兩指 + 掌
            UsdGeom.Imageable(st.GetPrimAtPath("/World/gvis_h2")).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            H2F = np.array([0.008, 0.020, 0.030]); H2GAP = 0.006               # 指 (x 厚, y 寬, z 長);合指後指間 6mm
            if a.jaw_collide:                                                 # [jaw3] 兩指 = kinematic 碰撞體(進 kinematic view);合指後指間 = 兩層布 8 + 1 mm
                H2GAP = 0.009
                for k_ in ("h2a", "h2b"):
                    GPARK[k_] = np.array([3.0, 3.5, 1.0]); GPATH[k_] = "/World/gfing/" + k_
                    GU.finger(st, GPATH[k_], H2F, GPARK[k_], a.ffric, cont=0.001, rest=0.0)
                    UsdGeom.Imageable(st.GetPrimAtPath(GPATH[k_])).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
                    GVIS[k_] = GU.VisBox(st, "/World/gvis_" + k_, H2F, (0.15, 0.4, 0.9)); GVIS[k_].set(GPARK[k_])
            else:
                for k_ in ("h2a", "h2b"): JV[k_] = SBox("/World/gvis_" + k_, (0.15, 0.4, 0.9), H2F)
            JV["h2p"] = SBox("/World/gvis_h2p", (0.1, 0.25, 0.6), [0.05, 0.02, 0.006])
        P("★ --hand2 %s:第二隻手 %s %s mm(%s);放手前 %.1fs 到位,放手後持續 %.1fs 再抬起"
          % (a.hand2, GPATH["h2"], H2S * 1e3, "有碰撞 摩擦 %.1f" % a.fric if a.hand2 == "press" else "不碰撞、綁頂點 pad %.0f mm" % a.hand2_pad_mm, a.hand2_lead_s, a.hand2_hold_s))
    if a.extract:                                                             # [extract] 第三隻手(純視覺;杯子轉 kinematic 跟著走 = 剛性綁定)
        H3S = np.array([0.070, 0.070, 0.012]); GVIS["h3"] = GU.VisBox(st, "/World/gvis_h3", H3S, (0.85, 0.2, 0.75)); GVIS["h3"].set([3.0, 3.4, 1.0])
        if a.extract_grip == "jaw":                                           # [jaw2] 取杯手 = 兩指(沿 y 夾杯兩端)+ 掌
            UsdGeom.Imageable(st.GetPrimAtPath("/World/gvis_h3")).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            H3F = np.array([0.030, 0.008, 0.050])                             # 指 (x 寬, y 厚, z 長)
            if a.jaw_collide:                                                 # [jaw3] 兩指 = kinematic 碰撞體(位置由 x_events 寫 KOV)
                for k_ in ("h3a", "h3b"):
                    GPARK[k_] = np.array([3.0, 3.6, 1.0]); GPATH[k_] = "/World/gfing/" + k_
                    GU.finger(st, GPATH[k_], H3F, GPARK[k_], a.ffric, cont=0.001, rest=0.0)
                    UsdGeom.Imageable(st.GetPrimAtPath(GPATH[k_])).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
                    GVIS[k_] = GU.VisBox(st, "/World/gvis_" + k_, H3F, (0.85, 0.2, 0.75)); GVIS[k_].set(GPARK[k_])
            else:
                for k_ in ("h3a", "h3b"): JV[k_] = SBox("/World/gvis_" + k_, (0.85, 0.2, 0.75), H3F)
            JV["h3p"] = SBox("/World/gvis_h3p", (0.6, 0.12, 0.5), [0.03, 0.15, 0.012])
    if TK:                                                                    # [v2] 手 2 取出整包:兩片寬指(沿 x 夾包裹兩側)+ 掌,純視覺(同取杯手顏色);整包跟手 = 杯 kinematic + 膠帶跟杯
        TKF = np.array([0.008, 0.110, 0.070])                                 # 指 (x 厚, y 寬, z 長)
        for k_ in ("tka", "tkb"): JV[k_] = SBox("/World/gvis_" + k_, (0.85, 0.2, 0.75), TKF)
        JV["tkp"] = SBox("/World/gvis_tkp", (0.6, 0.12, 0.5), [0.2, 0.12, 0.012])
    if a.attach_proxy:                                                       # [drag] 力限代理:動態剛體 upx 以 D6 drive 掛在上指
        GPATH["upx"] = "/World/gfing/upx"
        _px = VC.kin_box(st, GPATH["upx"], [0.004] * 3, GPARK["up"], collide=False, visible=False)
        UsdPhysics.RigidBodyAPI(_px).GetKinematicEnabledAttr().Set(False)
        PhysxSchema.PhysxRigidBodyAPI.Apply(_px).CreateDisableGravityAttr(True)
        _pm = UsdPhysics.MassAPI.Apply(_px); _pm.CreateMassAttr(float(a.proxy_m)); _pm.CreateDiagonalInertiaAttr(Gf.Vec3f(1e-7, 1e-7, 1e-7))
        PROXY_C = a.proxy_c if a.proxy_c >= 0 else 2 * np.sqrt(a.proxy_k * a.proxy_m)
        _j = UsdPhysics.Joint.Define(st, "/World/gfing/upx_joint")
        _j.CreateBody0Rel().SetTargets([Sdf.Path(GPATH["up"])]); _j.CreateBody1Rel().SetTargets([Sdf.Path(GPATH["upx"])])
        _j.CreateLocalPos0Attr(Gf.Vec3f(0, 0, 0)); _j.CreateLocalPos1Attr(Gf.Vec3f(0, 0, 0))
        _j.CreateLocalRot0Attr(Gf.Quatf(1, 0, 0, 0)); _j.CreateLocalRot1Attr(Gf.Quatf(1, 0, 0, 0))
        _j.CreateCollisionEnabledAttr(False); _j.CreateBreakForceAttr(float("inf")); _j.CreateBreakTorqueAttr(float("inf"))
        for _ax in ("rotX", "rotY", "rotZ"):
            _l = UsdPhysics.LimitAPI.Apply(_j.GetPrim(), _ax); _l.CreateLowAttr(1.0); _l.CreateHighAttr(-1.0)
        for _ax in ("transX", "transY", "transZ"):
            _d = UsdPhysics.DriveAPI.Apply(_j.GetPrim(), _ax); _d.CreateTypeAttr("force"); _d.CreateTargetPositionAttr(0.0)
            _d.CreateStiffnessAttr(float(a.proxy_k)); _d.CreateDampingAttr(float(PROXY_C)); _d.CreateMaxForceAttr(float(a.proxy_fmax))
        P("★ --attach_proxy 1:上指綁定改綁 %s(動態、無碰撞、無重力、m %.3f kg);D6 drive k %g N/m c %g N·s/m maxForce %g N(每軸)"
          % (GPATH["upx"], a.proxy_m, a.proxy_k, PROXY_C, a.proxy_fmax))
    if a.hold_others:                                                         # [drag] 釘他片用的不碰撞 kinematic 錨(永不移動)
        if a.hold_mode != "attach": raise NotImplementedError("--hold_mode pad 未實作(耳朵被 yn 尖端罩住、側向無空間)")
        HOLD_ANC = np.array([3.0, 3.4, 1.0])
        VC.kin_box(st, "/World/ghold/anc", [0.004] * 3, HOLD_ANC, collide=False, visible=False)
        P("★ --hold_others 1:他片 %s 釘到 /World/ghold/anc(不碰撞、停在 %s);pad %.0f mm 層 %s;TR+%.1fs 放開" % (a.hold_sides, HOLD_ANC, a.hold_pad_mm, a.hold_layer, a.hold_rel_s))

# ── 相機 / 燈 [ws] ───────────────────────────────────────────────────
FPS = a.fps
cam = Camera(prim_path="/World/cam", resolution=tuple(int(v) for v in a.vid_res.lower().split("x")))
cam.set_focal_length(4.0)
_gl = st.GetPrimAtPath("/World/defaultGroundPlane/SphereLight")
if _gl.IsValid():
    _ga = _gl.GetAttribute("inputs:intensity")
    if _ga and _ga.IsValid(): _ga.Set(_ga.Get()/12.0)
_cr = a.cam_ref
EYE_F = [_cr*1.5, -_cr*1.6, _cr*0.9]; TGT_F = [0, 0, 0]
G.look(cam, EYE_F, TGT_F)
G.add_headlight(st, EYE_F, TGT_F, intensity=245.0, name="hl1")
G.add_headlight(st, [-.5, -.5, .8], TGT_F, intensity=135.0, name="hl2")
UsdLux.DomeLight.Define(st, "/World/dome").CreateIntensityAttr(2600.0)
_dl = UsdLux.DistantLight.Define(st, "/World/toplight")
UsdGeom.Xformable(_dl).AddRotateXYZOp().Set(Gf.Vec3f(-70.0, 0.0, 25.0)); _dl.CreateIntensityAttr(0.0); _dl.CreateAngleAttr(2.0)
_dl2 = UsdLux.DistantLight.Define(st, "/World/toplight2")
UsdGeom.Xformable(_dl2).AddRotateXYZOp().Set(Gf.Vec3f(-90.0, 0.0, 0.0)); _dl2.CreateIntensityAttr(0.0); _dl2.CreateAngleAttr(4.0)

def _xf_set(pth, p, q):                                                       # [speed2] reset 前直接寫世界姿態(同「reset 前擺到旁邊」寫法)
    _pr = st.GetPrimAtPath(pth); _Wm = Gf.Matrix4d().SetRotate(Gf.Quatd(float(q[0]), Gf.Vec3d(*map(float, q[1:])))) * Gf.Matrix4d().SetTranslate(Gf.Vec3d(*map(float, p)))
    _par = UsdGeom.Xformable(_pr.GetParent()).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    _x = UsdGeom.Xformable(_pr); _x.ClearXformOpOrder(); _x.AddTransformOp().Set(_Wm * _par.GetInverse())
from scipy.spatial.transform import Rotation as _Rot0                          # [v2x]
if LOADED is not None:                                                        # [speed2] 布以外的狀態在 reset 前寫進 USD → PhysX 直接以存檔狀態建立(箱/蓋/側板不會以 kinematic 速度掃過布)
    _m = LOADED
    _dif = {k: (v, vars(a).get(k)) for k, v in _m["args"].items() if vars(a).get(k) != v and k not in ("out", "save_state", "load_state", "at", "save_exit")}
    P("★ [load] %s:存檔 t=%.3f(%s,第 %d 步 / 第 %d 幀)%s" % (a.load_state, _m["t"], _m["at"], _m["step"], _m["fr"], ";存檔時整鏈 wall %.0f s" % _m["wall"]))
    P("  [load] 與存檔不同的旗標:%s" % (_dif or "無"))
    if st.GetPrimAtPath("/World/attach").IsValid(): st.RemovePrim(Sdf.Path("/World/attach"))
    st.GetPrimAtPath("/World/mug").GetAttribute("physics:kinematicEnabled").Set(not _m["ST"]["released"])
    _xf_set("/World/mug", _m["mug_p"], _m["mug_q"])
    for _pth, (_p, _q) in _m["box"].items(): _xf_set(_pth, _p, _q)
    if _m["ST"].get("pads_gone"):
        for q_ in PADS: _xf_set(q_["path"], [0, 0, -3.0], [1, 0, 0, 0])
    if _m["ST"]["inbox"]:
        for _gp in Usd.PrimRange(st.GetPrimAtPath("/World/defaultGroundPlane")):
            if _gp.HasAPI(UsdPhysics.CollisionAPI): UsdPhysics.CollisionAPI(_gp).CreateCollisionEnabledAttr(False)
        _dl.GetIntensityAttr().Set(3500.0); _dl2.GetIntensityAttr().Set(2200.0)
    if "xs" in _m:                                                            # [v2x] 膠帶錨點 / 手指(kinematic)放到存檔姿態;桌面(地板)碰撞照存檔;剩下的膠帶綁定在 reset、寫布之後再建
        for _pth, (_p, _q) in _m["xs"]["anc"].items(): _xf_set(_pth, _p, _q)
        for k_, (_p, _R) in _m["xs"]["gpose"].items():
            if k_ in GPATH and st.GetPrimAtPath(GPATH[k_]).IsValid():
                _xq = _Rot0.from_matrix(_R).as_quat(); _xf_set(GPATH[k_], _p, [_xq[3], *_xq[:3]])
        if _m["xs"]["ground"]:
            for _gp in Usd.PrimRange(st.GetPrimAtPath("/World/defaultGroundPlane")):
                if _gp.HasAPI(UsdPhysics.CollisionAPI): UsdPhysics.CollisionAPI(_gp).CreateCollisionEnabledAttr(True)
    P("  [load] reset 前:移除錨點綁定、杯 %s 姿態 %s mm、箱/蓋 %d 個剛體、側板 %s、地板碰撞 %s"
      % ("dynamic" if _m["ST"]["released"] else "kinematic", np.round(np.array(_m["mug_p"]) * 1e3, 1), len(_m["box"]), "撤到 z=-3" if _m["ST"].get("pads_gone") else "原位", "關" if _m["ST"]["inbox"] else "開"))
world.reset(); cam.initialize()
for k_ in range(3):
    sim.update()
if LOADED is not None:                                                        # [speed2] 布:body 照常以平板建立(rest = 平、自碰撞過濾同整鏈),reset 後才把 points 寫成存檔值(USD 寫入 → PhysX 更新 sim 節點)、速度歸零
    _P0 = PLATE.pts()
    PLATE.pa.Set(Vt.Vec3fArray.FromNumpy(LOADED["pts"].astype(np.float32)))
    PLATE.tm.GetVelocitiesAttr().Set(Vt.Vec3fArray.FromNumpy(LOADED["vel"].astype(np.float32)))   # 速度歸零會讓布一載入就睡著(凍住不動,smokeR 實測)→ 寫回存檔速度
    P("  [load] reset 後寫入布 points(%d 點;collision mesh = sim mesh 同一個 TetMesh)、velocities = 存檔值(|v| 最大 %.3f m/s);寫入前 max|P - 存檔| = %.1f mm(平板)"
      % (len(LOADED["pts"]), np.abs(LOADED["vel"]).max(), np.abs(_P0 - LOADED["pts"]).max() * 1e3))
ANCV = world.physics_sim_view.create_rigid_body_view([A["path"] for A in ANC])
_vp = list(ANCV.prim_paths); _pi = {A["path"]: i_ for i_, A in enumerate(ANC)}
ANC_ORD = np.array([_pi[p_] for p_ in _vp]); ANC_IDX = np.arange(ANCV.count, dtype=np.int32)
P("錨 rigid body view:%d 個(kinematic target)" % ANCV.count)
if LOADED is not None and "xs" in LOADED:                                     # [v2x] 剩下的膠帶(x 片)重建綁定:local = 原本的 FLAT − 錨中心(錨已在存檔姿態,布頂點也在 → 約束一致)
    _xa = LOADED["xs"]; _D = np.zeros((len(ANC), 7), np.float32)
    for i_, A in enumerate(ANC):
        _p, _q = _xa["anc"][A["path"]]; _D[i_, :3] = _p; _D[i_, 3:6] = _q[1:]; _D[i_, 6] = _q[0]
        if A["scope"] in _xa["alive"]: VC.attach_vtx(st, A["scope"], "/World/plate", "/World/plate", A["path"], A["vids"], FLAT[A["vids"]] - A["c0"], P=lambda *x: None)
    ANCV.set_kinematic_targets(_D[ANC_ORD], ANC_IDX)
    P("  [load] [v2x] 重建膠帶綁定 %d 個(%s)" % (len(_xa["alive"]), sorted({A["side"] for A in ANC if A["scope"] in _xa["alive"]})))
base_x = SingleXFormPrim("/World/Box/base", name="boxbase")
for L in LIDS:
    L["prim"] = SingleXFormPrim("/World/Box/" + L["nm"], name="lid_" + L["nm"])
_bp, _bq = BASE_T0.ExtractTranslation(), BASE_T0.ExtractRotationQuat()
BASE_P0 = np.array([float(x) for x in _bp]); BASE_Q0 = np.array([float(_bq.GetReal()), *[float(x) for x in _bq.GetImaginary()]])
mugx = SingleXFormPrim("/World/mug", name="mugx")
for q_ in PADS:
    q_["x"] = SingleXFormPrim(q_["path"], name=q_["nm"])
BOXV = world.physics_sim_view.create_rigid_body_view(["/World/Box/base"] + ["/World/Box/" + L["nm"] for L in LIDS])
kin = st.GetPrimAtPath("/World/mug").GetAttribute("physics:kinematicEnabled")
if a.grasp:
    GKEYS = list(GPARK)
    for k_ in (["lov"] if a.hand1_jaw else []) + (["h2a", "h2b"] if a.hand2 == "jaw" and not a.jaw_collide else []): GPARK[k_] = np.array([3.0, 3.5, 1.0])   # [jaw2] 純視覺指(不進 kinematic view)
    GFV = world.physics_sim_view.create_rigid_body_view([GPATH[k_] for k_ in GKEYS])
    _gpi = {GPATH[k_]: i_ for i_, k_ in enumerate(GKEYS)}
    GF_ORD = np.array([_gpi[p_] for p_ in GFV.prim_paths]); GF_IDX = np.arange(GFV.count, dtype=np.int32)
    P("抓取指 rigid body view:%d 個" % GFV.count)
    if a.attach_proxy:                                                    # [drag] 代理另開 view(不能進 kinematic view)
        GPXV = world.physics_sim_view.create_rigid_body_view([GPATH["upx"]])
        def g_proxy_pose():
            _t = GPXV.get_transforms(); _t = _t.numpy() if hasattr(_t, "numpy") else np.asarray(_t); _t = _t[0]
            return _t[:3].astype(float), np.array([_t[6], _t[3], _t[4], _t[5]], float)
if a.fast_pts:                                        # [speed] tensor 直讀 sim 節點
    _usd_pts = PLATE.pts
    import omni.physics.tensors as _opt                # numpy 前端拿不到 GPU deformable 資料 → 另開 warp 前端
    _NPL = len(FLAT); _FP = {}
    def _fast_pts():
        if "v" not in _FP:                             # 第一次量測時(已跑過 step)才建 view
            _WSV = _opt.create_simulation_view("warp"); _WSV.set_subspace_roots("/")
            v = _WSV.create_volume_deformable_body_view("/World/plate")
            P("[fast_pts] view count %d max_sim_nodes %d sim_elems %d (USD pts %d)"
              % (v.count, v.max_simulation_nodes_per_body, v.max_simulation_elements_per_body, _NPL))
            if v.max_simulation_nodes_per_body < _NPL:
                P("[fast_pts] ★ view 無節點(此版 omni.physics.tensors 對 /World/plate 回 max_sim_nodes 0;numpy/torch/warp 皆同)→ 退回 USD"); _FP["v"] = None
            else:
                _FP["v"] = v; _FP["sv"] = _WSV
        if _FP["v"] is None: return _usd_pts()
        return _FP["v"].get_simulation_nodal_positions().numpy().astype(float).reshape(-1, 3)[:_NPL]
    PLATE.pts = _fast_pts

# ── 時間表 ───────────────────────────────────────────────────────────
T_SET = 0.5
FT = {}
t_ = T_SET
for sd in FOLD_ORDER:
    sp_ = a.fold_span * SLOW.get(sd, 1.0)
    FT[sd] = (t_, sp_); t_ += sp_ + a.fold_hold
T_FOLD_END = t_
T_SQ0 = T_FOLD_END
T_SQ1 = T_SQ0 + a.squeeze_t
T_INBOX = T_SQ1 + (0.5 if a.squeeze_t > 0 else 0.0)
T_LID0 = T_INBOX + 1.0
T_LID1 = T_LID0 + a.lid_span
T_REL = T_LID1 + a.lid_span            # 蓋子關好 → 側板外撤 0.3s
T_ANC = T_REL + 0.4                     # 放錨點 + 杯子轉 dynamic
T_MOVE0 = T_ANC + 2.0
T_MOVE1 = T_MOVE0 + a.move_t
T_OPEN0 = T_MOVE1 + 2.0
T_OPEN1 = T_OPEN0 + a.open_span
T_OPEN2 = T_OPEN1 + a.open_span
T_END_ALL = T_OPEN2 + 3.0
if UT: T_MOVE0 = T_MOVE1 = T_OPEN0 = T_OPEN1 = T_OPEN2 = T_END_ALL = T_ANC + a.ut_settle_s   # [table] 不入箱:沒有搬/開蓋,放錨點 settle 完就掀
TKT = dict(down=1.5, close=0.8, lift=2.5, move=3.0, lower=2.5, open=0.4, up=1.0, settle=2.0)   # [v2] 取出整包各段秒數
V2XG = 0.0                                                                     # [v2] --v2_hold_cup:x 片開始時手 2 夾杯用的秒數(x 片拆膠帶延後這麼多)
T_TK0 = T_END_ALL; T_TK1 = T_TK0 + (sum(TKT.values()) if TK else 0.0)
if TK: assert a.grasp and a.until == "all", "[v2] --takeout 1 要 --grasp 1、--until all"
T_END = {"fold": T_INBOX + 0.6, "box": T_MOVE0, "move": T_OPEN0, "all": T_END_ALL, "yn": T_END_ALL}[a.until]
# 抓取段時間表(相對每片的 S0;yn 在 open hold 完 + settle 1s 開始)
GT = dict(rod_above=1.0, rod_down=1.0, rod_in=1.0, rod_lift=1.0, pick_hold=0.5, lo_above=0.8, lo_down=0.8, lo_in=1.0,
          rod_out=0.6, rod_up=0.5, up_above=0.8, up_down=0.7, close=0.8, grip_hold=0.3, peel_hold=2.0, rel_open=0.5, rel_slide=0.5, rel_up=0.7)
G_TPICK = GT["rod_above"] + GT["rod_down"] + GT["rod_in"] + GT["rod_lift"] + GT["pick_hold"]            # 4.5
G_TLOIN = G_TPICK + GT["lo_above"] + GT["lo_down"] + GT["lo_in"]                                        # 7.1 張口兩指插到位
G_TJAW = G_TLOIN + GT["close"]                                                                          # 7.9 合好 → rod 撤
G_TGRIP = G_TJAW + GT["rod_out"] + GT["rod_up"] + GT["grip_hold"] + 0.4                                 # 9.7 登記夾到的點、開始掀
G_LF = a.lift_first_t if a.lift_first_mm > 0 else 0.0                                                  # [drag] 先拉起
G_EXT = a.arc2_ext_t if a.arc2_ext_mm > 0 else 0.0                                                # [drag2]
G_EXT += (a.arc2_cl_t + 1.0 if a.arc2_target == "centroid" else a.arc2_over_t if a.arc2_over_mm > 0 else 0.0) + (0.5 if a.release_press_mm > 0 else 0.0) + a.release_settle_s   # [peel]
G_EXT += a.arc2_lay_t if a.arc2_lay else 0.0                                                      # [peel4]
if UTT: G_EXT = a.ut_lift_t                                                                         # [table] 越壁/延伸都不做,換成抬起([v2] 取出後同)
G_EXT2 = (a.hand2_hold_s + 3.0) if a.hand2 != "off" else 0.0                                      # [hand2] 放手後:壓 hold_s + 抬 1s + 觀察 2s
G_RT = 4.0                                                                                             # [robust] 每次重夾:抬 0.5 + 移 0.8 + 降 0.8 + 合 0.8 + 停 0.7 + 餘
G_SHEET = G_RT * a.grasp_retry + G_TGRIP + G_LF + G_EXT + a.peel_t + GT["peel_hold"] + GT["rel_open"] + GT["rel_slide"] + GT["rel_up"] + 0.3 + G_EXT2
G_SEQ = (["yn", "yp"] if a.second else ["yn"]) if a.grasp else []
if UTT and a.v2_xflaps and a.grasp: G_SEQ += ["xn", "xp"]                    # [v2] 桌面上再掀 x 片(xn 疊在 xp 上 → 先 xn)
TG0 = T_TK1 + 1.0                                                              # [v2] T_TK1 = T_END_ALL(沒有 --takeout 時 = 舊)
if a.grasp and (a.until in ("all", "yn") or UT):                          # [speed2] yn = 只 yn 片;[table] UT 時 --until fold 也接掀開段
    T_END = TG0 + G_SHEET * len(G_SEQ) + a.grasp_tail_s                     # [plastic] grasp_tail_s 預設 0
    P("抓取段:open hold 完 %.2f → settle → %s 每片 %.1fs(挑角 0~%.1f、下指進 ~%.1f、夾好 %.1f、掀 %.1fs、停 %.1fs、放開);結束 %.2f"
      % (T_END_ALL, " / ".join("%s@%.2f" % (sd, TG0 + k_*G_SHEET) for k_, sd in enumerate(G_SEQ)), G_SHEET, G_TPICK, G_TLOIN,
         G_TGRIP, a.peel_t, GT["peel_hold"], T_END))
if a.extract:                                                                  # [extract] 取杯段接在 yp 段之後
    XT = dict(down=1.5, bind=0.3, lift=3.0, move=3.0, lower=2.5, up=1.0, obs=1.0)
    if a.extract_grip == "jaw": XT.update(bind=0.8, open=0.4)                 # [jaw2] 合指 0.8s;放下後張開 0.4s 再抬
    T_X0 = T_END; T_END = T_X0 + sum(XT.values())
    if a.v2_hold_cup and "xn" in G_SEQ:                                       # [v2] x 片開始時手 2 就夾住杯(down + bind),扶到 x 片結束(hold)再抬
        T_X0 = TG0 + G_SHEET * G_SEQ.index("xn"); XT["hold"] = (TG0 + G_SHEET * len(G_SEQ) + a.grasp_tail_s) - T_X0 - XT["down"] - XT["bind"]
        V2XG = XT["down"] + XT["bind"]; T_END = T_X0 + sum(XT.values())
    P("[extract] 取杯段 %.2f~%.2f %s" % (T_X0, T_END, XT))
P("時間表:折 %s | 折完 %.2f | 入箱 %.2f | 關下蓋 %.2f | 關上蓋 %.2f | 放錨+杯動態 %.2f | 搬 %.2f~%.2f | 開上蓋 %.2f | 開下蓋 %.2f | 結束 %.2f(本次跑到 %.2f)"
  % (" ".join("%s@%.1f(%.1fs)" % (k, *v) for k, v in FT.items()), T_FOLD_END, T_INBOX, T_LID0, T_LID1, T_REL,
     T_MOVE0, T_MOVE1, T_OPEN0, T_OPEN1, T_END_ALL, T_END))
ss = lambda u: (lambda v: v*v*(3-2*v))(min(max(u, 0.), 1.))

def phase(t):
    if t < T_SET: return "settle"
    for sd in FOLD_ORDER:
        t0, sp_ = FT[sd]
        if t < t0 + sp_ + a.fold_hold: return "fold " + sd
    if t < T_INBOX: return "tuck ears (side squeeze)"
    if t < T_LID0: return "into box"
    if t < T_LID1: return "close lower lids"
    if t < T_REL: return "close upper lids"
    if t < T_ANC: return "release paddles"
    if t < T_MOVE0: return "release anchors / settle"
    if t < T_MOVE1: return "move box"
    if t < T_OPEN0: return "settle"
    if t < T_OPEN1: return "open upper lids"
    if t < T_OPEN2: return "open lower lids"
    if t < T_END_ALL or not a.grasp: return "hold"
    if TK and t < T_TK1: return "TAKEOUT: " + TKS.get("st", "")                  # [v2]
    if t < TG0: return "grasp settle"
    if a.extract and t >= T_X0 and X["st"] != "hold cup": return ("EXTRACT: " + X["st"]).replace("hand3", "hand2" if TK else "hand3")   # [extract]([v2] 扶杯時顯示片的階段)
    k_ = min(int((t - TG0) // G_SHEET), len(G_SEQ) - 1); sd = G_SEQ[k_]; r_ = t - TG0 - k_ * G_SHEET
    if sd[0] == "x":                                                          # [v2] x 片:先拆膠帶等 xcut 秒
        r_ -= V2XG + (0.0 if a.v2_xmode == "tapegrip" else a.v2_xcut_s)      # [v2x]
        if r_ < -a.v2_xcut_s or (a.v2_xmode == "tapegrip" and r_ < 0): return "%s (hand2 grips cup)" % sd
        if r_ < 0: return "%s cut tape" % sd
        _xp = [p_ for p_ in GS["plans"] if p_.get("xm") and p_["sd"] == sd]    # [v2x]
        if _xp: return "%s %s" % (sd, ({"sweep": "sweep (paddle push out)", "outer": "outer-edge grasp + pull"}[_xp[0]["xm"]]) if t < _xp[0]["TR"] else "release")
        if any(p_.get("skip") and p_["sd"] == sd for p_ in GS["plans"]): return "%s %s (no grasp)" % (sd, "leaning on cup" if any(p_.get("lean") and p_["sd"] == sd for p_ in GS["plans"]) else "opened by itself")
    _pf ="lower jaw" if a.pick_mode == "jaw" else "rod"
    _sq = ([("upper jaw down", G_TPICK + GT["lo_above"] + GT["lo_down"]), ("close jaws", G_TPICK + GT["lo_above"] + GT["lo_down"] + GT["close"]),
            ("grip hold", G_TGRIP)] if a.pick_mode == "jaw" else [("open jaws in", G_TLOIN), ("close jaws", G_TJAW), ("rod out / grip hold", G_TGRIP)])
    for nm_, tt_ in [("pick: %s to corner" % _pf, GT["rod_above"] + GT["rod_down"]), ("pick: %s insert" % _pf, GT["rod_above"] + GT["rod_down"] + GT["rod_in"]),
                     ("pick: lift corner", G_TPICK)] + _sq + [
                     ("LIFT first", G_TGRIP + G_LF), ("PEEL arc", G_TGRIP + G_LF + a.peel_t + G_EXT), ("hold peeled", G_TGRIP + G_LF + a.peel_t + G_EXT + GT["peel_hold"])]:
        if r_ < tt_: return "%s %s" % (sd, nm_)
    return "%s release" % sd

ST = dict(inbox=False, released=False, OFF_IN=None)
TKS = dict(st="")                                                              # [v2] 取出整包狀態
def tape_follow_targets(t):
    """[v2] 膠帶跟著包裹:錨點目標 = 杯子姿態 x 放錨點那一刻(錨點相對杯)的相對位姿"""
    mp, mq = mugx.get_world_pose(); mp = np.array(mp, float); mq = np.array(mq, float); mq /= np.linalg.norm(mq)
    w_, x_, y_, z_ = mq
    Rq = np.array([[1-2*(y_*y_+z_*z_), 2*(x_*y_-z_*w_), 2*(x_*z_+y_*w_)], [2*(x_*y_+z_*w_), 1-2*(x_*x_+z_*z_), 2*(y_*z_-x_*w_)], [2*(x_*z_-y_*w_), 2*(y_*z_+x_*w_), 1-2*(x_*x_+y_*y_)]])
    if "tape" not in ST:
        qc = mq * [1, -1, -1, -1]; ST["tape"] = []
        for A in ANC:
            p, q = anchor_pose(A, t); ST["tape"].append((Rq.T @ (np.asarray(p, float) - mp), qmul(qc, q)))
    D = np.zeros((len(ANC), 7), np.float32)
    for i_, (pr, qr) in enumerate(ST["tape"]):
        q = qmul(mq, qr); D[i_, :3] = mp + Rq @ pr; D[i_, 3:6] = q[1:]; D[i_, 6] = q[0]
    return D
def box_off(t):
    if not ST["inbox"]: return OFF_SIDE
    return ST["OFF_IN"] + MOVE * ss((t - T_MOVE0) / a.move_t)
def lid_deg(L, t):
    if not ST["inbox"]: return 180.0
    if t < T_OPEN0:
        t0 = T_LID0 if L["order"] == 0 else T_LID1
        return 180.0 * (1.0 - ss((t - t0) / a.lid_span))
    t0 = T_OPEN0 if L["order"] == 1 else T_OPEN1
    return 180.0 * ss((t - t0) / a.open_span)

def drive(t):
    if not ST["released"]:
        D = np.zeros((len(ANC), 7), np.float32)
        for i_, A in enumerate(ANC):
            p, q = anchor_pose(A, t)
            D[i_, :3] = p; D[i_, 3:6] = q[1:]; D[i_, 6] = q[0]
        ANCV.set_kinematic_targets(D[ANC_ORD], ANC_IDX)
    elif a.tape_follow == 1 and not ST.get("tape_frozen"):                    # [v2] 膠帶跟著杯子(包裹整體剛體運動);放到桌面後固定(包裹靜置)
        ANCV.set_kinematic_targets(tape_follow_targets(t)[ANC_ORD], ANC_IDX)
    if a.squeeze_t > 0 and not ST.get("pads_gone") and t >= T_SQ0 - 0.1:
        lim = {0: CBOX["ix"] - a.squeeze_mm/1e3, 1: CBOX["iy"] - a.squeeze_mm/1e3}
        u = ss((t - T_SQ0)/a.squeeze_t)
        # ★ 第 4 版(out_v400 第 1 次全程):側板在入箱時就撤,4mm 板回彈 → 關下蓋時 y 端被擠到 y 牆頂上方,
        #   上蓋再把它夾在牆頂外(關蓋後 y 超 20 點,z 122~138)。改成側板留到上下蓋都關好才撤(往外退 40mm,分離方向)。
        back = 0.04 * ss((t - T_REL)/0.3)
        for q_ in PADS:
            d0 = abs(q_["c0"][q_["ax"]]); d1 = lim[q_["ax"]] + 0.005
            c_ = q_["c0"].copy(); c_[q_["ax"]] = q_["sg"]*(d0 + (d1 - d0)*u + back)
            if t >= T_REL + 0.35:
                c_ = np.array([0, 0, -3.0]); ST["pads_gone"] = True
            q_["x"].set_world_pose(position=c_, orientation=QI)
    if ST["inbox"]:
        off = box_off(t)
        base_x.set_world_pose(position=BASE_P0 + off, orientation=BASE_Q0)
        for L in LIDS:
            p, q = lid_pose(L, lid_deg(L, t), off)
            L["prim"].set_world_pose(position=p, orientation=q)

# ── 量測 ─────────────────────────────────────────────────────────────
def mug_world():
    mp, mq = mugx.get_world_pose()
    w_, x_, y_, z_ = [float(v) for v in mq]
    Rq = np.array([[1-2*(y_*y_+z_*z_), 2*(x_*y_-z_*w_), 2*(x_*z_+y_*w_)],
                   [2*(x_*y_+z_*w_), 1-2*(x_*x_+z_*z_), 2*(y_*z_-x_*w_)],
                   [2*(x_*z_-y_*w_), 2*(y_*z_+x_*w_), 1-2*(x_*x_+y_*y_)]])
    return np.array(mp, float), Rq, V @ Rq.T + np.array(mp, float)

def sheet_in_mug(Pp, mp, Rq):
    loc = (Pp - mp) @ Rq                         # 世界 → 杯子局部
    lo, hi = V.min(0) - 0.002, V.max(0) + 0.002
    cand = np.where(((loc > lo) & (loc < hi)).all(1))[0]
    if not len(cand): return 0, cand
    ins = MTRI.contains(loc[cand])
    return int(ins.sum()), cand[ins]

IX, IY = CBOX["ix"], CBOX["iy"]
def inbox(nm, Q, off):
    """[ws inbox] 逐頂點比對內腔;off = 箱子目前位移(箱子在原點時的座標系 + off)。"""
    Q = Q - off
    ox = np.abs(Q[:, 0] - BOXC[0]) > IX; oy = np.abs(Q[:, 1] - BOXC[1]) > IY
    olo = Q[:, 2] < CDZ - 0.0005; ohi = Q[:, 2] > ZHI0
    bad = ox | oy | olo | ohi
    dlo = (CDZ - Q[olo, 2]).max()*1e3 if olo.any() else 0.0
    P("  %-4s %5d 點;超出內腔 %d | x 超 %d / y 超 %d / 低於底 %d(最深 %.2fmm)/ 高於口 %d | x %.1f~%.1f(±%.0f) y %.1f~%.1f(±%.0f) z %.1f~%.1f(%.1f~%.1f)"
      % (nm, len(Q), int(bad.sum()), int(ox.sum()), int(oy.sum()), int(olo.sum()), dlo, int(ohi.sum()),
         (Q[:, 0].min()-BOXC[0])*1e3, (Q[:, 0].max()-BOXC[0])*1e3, IX*1e3, (Q[:, 1].min()-BOXC[1])*1e3,
         (Q[:, 1].max()-BOXC[1])*1e3, IY*1e3, Q[:, 2].min()*1e3, Q[:, 2].max()*1e3, CDZ*1e3, ZHI0*1e3))
    return dict(n=int(bad.sum()), x=int(ox.sum()), y=int(oy.sum()), lo=int(olo.sum()), hi=int(ohi.sum()), dlo=dlo)

def lid_cz():
    return {L["nm"]: UsdGeom.Xformable(st.GetPrimAtPath("/World/Box/" + L["nm"])).ComputeLocalToWorldTransform(
        Usd.TimeCode.Default()).Transform(L["c_loc"])[2] for L in LIDS}

def layers(Pp, MW):
    mid = (Pp[BOT] + Pp[TOP]) / 2
    try:
        R = LG.measure(mid, MW, grid_mm=5.0, shrink_mm=15.0)
    except Exception as e:
        return None
    na = R["nabove"]
    try:
        R0 = LG.measure(mid, MW, grid_mm=5.0, shrink_mm=0.0)
        cov = float((R0["nabove"] >= 1).mean())
    except Exception:
        cov = float("nan")
    allg = np.concatenate([R["gaps"][k] for k in R["gaps"]]) if R["gaps"] else np.array([])
    return dict(nlay=float(np.median(na)), dist={int(u): int(c) for u, c in zip(*np.unique(na, return_counts=True))},
                gap=float(np.median(allg))*1e3 if len(allg) else float("nan"),
                top=float(np.median(R["thick"]))*1e3 + T/2*1e3 if len(R["thick"]) else float("nan"),
                first=float(np.median(R["first"]))*1e3 - T/2*1e3 if len(R["first"]) else float("nan"), cov=cov)

def measure(t, full=False):
    Pp = PLATE.pts()
    mp, Rq, MW = mug_world()
    r = dict(t=t, ph=phase(t))
    r["finite"] = bool(np.isfinite(Pp).all())
    r["bb"] = (Pp.max(0) - Pp.min(0)) * 1e3
    r["pen"], _ = VP.self_pen_count(Pp, TETS, FLAT)
    r["inmug"], _ = sheet_in_mug(Pp, mp, Rq)
    r["inv"], v = VC.inverted(Pp, TETS, V0)
    r["volr"] = v.sum() / V0.sum()
    Lr = np.linalg.norm(Pp[EDG[:, 0]] - Pp[EDG[:, 1]], axis=1) / L0
    r["lr"] = (Lr.min(), Lr.max())
    r["mug"] = mp
    allp = np.vstack([Pp, MW])
    r["pkg"] = (allp.max(0) - allp.min(0)) * 1e3
    r["pkgvol"] = float(np.prod(Pp.max(0) - Pp.min(0))) / MUG_VOL
    if full:
        r["lay"] = layers(Pp, MW)
    return r, Pp, MW

# ── 抓取段(--grasp 1)────────────────────────────────────────────────
if a.grasp:
    import grasp_plan as GPL
    from scipy.spatial.transform import Rotation as _Rot
    import itertools
    GPL.setup(FLAT, a.nxy, CX, CY, np.asarray(m_.faces), thick=T)
    GSIDE2 = GPL.S["SIDE2"]; GF2 = GPL.S["F2"]
    BOXL = dict(IX=IX, IY=IY, ZFLOOR=CDZ, ZOBST=max(CBOX["top"], CBOX["top_y"], CBOX["hz_up"]) + 0.005)
    if UTT: BOXL.update(IX=1.0, IY=1.0)                                       # [table] 沒有箱壁(地面 = ZFLOOR)([v2] 取出後同)
    GAPG = a.gap_mm / 1e3
    GF = {k_: dict(segs=[], last=(GPARK[k_].copy(), np.eye(3))) for k_ in GPARK}
    GS = dict(k=-1, plans=[], rows=[])
    def rq(Rm):
        x_, y_, z_, w_ = _Rot.from_matrix(Rm).as_quat(); return np.array([w_, x_, y_, z_])
    def rotm(axis, ang):
        return _Rot.from_rotvec(np.asarray(axis, float) / np.linalg.norm(axis) * ang).as_matrix()
    def g_lin(k_, t0, dur, pos, Rm=None):
        p0, R0_ = GF[k_]["last"]; R1 = R0_ if Rm is None else Rm
        p0 = np.array(p0, float); pos = np.array(pos, float)
        GF[k_]["segs"].append((t0, t0 + dur, lambda w, p0=p0, pos=pos, R1=R1: (p0 + (pos - p0) * w, R1)))
        GF[k_]["last"] = (pos, R1)
    def g_fn(k_, t0, dur, fn):
        GF[k_]["segs"].append((t0, t0 + dur, fn)); GF[k_]["last"] = fn(1.0)
    CL = dict(t=0.0)                                                          # [peel3] 閉環狀態
    def g_pose(k_, t):
        if k_ in KOV: return KOV[k_]                                          # [jaw3]
        if LOJ and k_ == "lo": return lov_pose(t)                             # [jaw3] 實體下指 = 下指路徑
        CL["t"] = t; cur = None
        for (t0, t1, fn) in GF[k_]["segs"]:
            if t >= t1: cur = fn(1.0)
            elif t >= t0: return fn(ss((t - t0) / (t1 - t0)))
            else: break
        return cur if cur is not None else (GPARK[k_], np.eye(3))
    def g_phys(k_, t):                                                        # [v2x2] --wide_mm_x:換手後 up/lo 的路徑由 upW/loW 實體指走,原指停 park
        if SWX["on"]:
            if k_ in ("up", "lo"): return GPARK[k_], np.eye(3)
            if k_ in ("upW", "loW"): return g_pose(k_[:2], t)
        return g_pose(k_, t)
    def g_drive(t):
        D = np.zeros((len(GKEYS), 7), np.float32)
        for i_, k_ in enumerate(GKEYS):
            p_, R_ = g_phys(k_, t); q_ = rq(R_)
            D[i_, :3] = p_; D[i_, 3:6] = q_[1:]; D[i_, 6] = q_[0]
        GFV.set_kinematic_targets(D[GF_ORD], GF_IDX)
    def g_vis(t):
        for k_ in GKEYS:
            p_, R_ = g_phys(k_, t); GVIS[k_].set(p_, rq(R_))
        if "lov" in GF:                                                       # [jaw2] 第一隻手下指(jaw2 純視覺;jaw3 = 實體 lo 同 pose)
            p_, R_ = lov_pose(t); JVS["lov"] = (p_, R_)
            if "lov" in JV: JV["lov"].set(p_, rq(R_))
        if "h2p" in JV:                                                       # [jaw2] 第二隻手兩指 + 掌
            pa, Ra = g_pose("h2a", t); pb, _ = g_pose("h2b", t)
            if "h2a" in JV: JV["h2a"].set(pa, rq(Ra)); JV["h2b"].set(pb, rq(Ra))
            JV["h2p"].set((pa + pb) / 2 + [0, 0, H2F[2] / 2 + 0.003], None, [abs(pb[0] - pa[0]) + H2F[0], H2F[1], 0.006])
    def lov_pose(t):
        """[jaw2] 下指視覺:合指前走排好的路徑(布邊外 → 滑到布下);合好後 = 上指 − n(指厚 + 間距),放手時再張開 20mm;重夾時先張開 15mm"""
        pls = GS["plans"]
        if not pls: return GPARK["lov"], np.eye(3)
        pl = pls[-1]
        if t < pl["S0"] + G_TPICK:
            if len(pls) < 2: return g_pose("lov", t)
            pl = pls[-2]
        elif t < pl["S0"] + G_TPICK + GT["lo_above"] + GT["lo_down"] + GT["close"]: return g_pose("lov", t)
        pu, Ru = g_pose("up", t); off = GFS[2] + GAPG
        if "rt0" in pl and t < pl["t_grip"]:
            off += 0.015 * min(ss((t - pl["rt0"]) / 0.3), 1.0 - ss((t - (pl["t_grip"] - 1.5)) / 0.8))
        if "TR" in pl and t >= pl["TR"] and not (a.hold_yp and pl["sd"] == "yp"):
            off += 0.020 * ss((t - pl["TR"]) / GT["rel_open"])
        return pu - Ru @ [0, 0, off], Ru
    def g_offw():
        if UT: return np.array([0.0, 0.0, -CDZ])                             # [table] = 入箱(側板以原點收)時的局部框:桌面 z = CDZ
        if TK:                                                                # [v2] 取出後:桌面放置點(箱中心往 −y tk_out_mm)為局部原點,桌面 z = CDZ
            _b = box_off(T_END_ALL) + np.array([BOXC[0], BOXC[1], 0.0]); return np.array([_b[0], _b[1] - a.tk_out_mm / 1e3, -CDZ])
        return box_off(T_END_ALL) + np.array([BOXC[0], BOXC[1], 0.0])
    def g_state():
        offw = g_offw(); Pw = PLATE.pts(); mp, Rq, MW = mug_world()
        return offw, Pw, Pw - offw, MW - offw, mp
    def g_frame_now(t):
        pu, Ru = g_pose("up", t); pl_, _ = g_pose("lo", t)
        if a.grasp_attach:
            pl_ = pu - Ru @ [0, 0, GFS[2] + GAPG]
        return (pu + pl_) / 2, Ru
    def g_between(Pw, t):
        gc, Rg = g_frame_now(t)
        L_ = (Pw - gc) @ Rg
        m_ = (np.abs(L_[:, 0]) < GFS[0] / 2) & (np.abs(L_[:, 1]) < GFS[1] / 2) & (np.abs(L_[:, 2]) <= GAPG / 2 + 0.0005)
        return np.where(m_)[0], L_
    def lid_top_local(sd):
        nm_ = "fyn" if sd == "yn" else "fyp"
        r_ = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(
            st.GetPrimAtPath("/World/Box/" + nm_)).ComputeAlignedRange()
        return float(r_.GetMax()[2]) - g_offw()[2]

    def g_site_cands(Pl, MUGl, sd, t):
        """[robust] 自由邊候選表:預估綁點(同 pad/|n| 規則)、被他片壓住、下方空隙(>15mm 視為沒支撐,上指會把布壓走)"""
        cs = GPL.site_candidates(Pl, sd, GAPG, a.attach_pad_mm / 1e3, nk=a.grasp_site_k, r_mm=a.attach_mask_r_mm, dz_mm=a.attach_mask_dz_mm, chord=a.chord)
        for c in cs:
            Rc, _ = GPL.frame(Pl, c["v"]); c["gap"] = GPL.gap_below(Pl, MUGl, c["v"], Rc, BOXL) * 1e3
            c["sup"] = c["gap"] <= 15.0
        if a.site_xmax_mm > 0 or a.site_exclude_walltop:
            cs, rej = GPL.site_filter(cs, a.site_xmax_mm, a.site_exclude_walltop, IY, CBOX["top_y"])
            for c, why in rej:
                P("   [peel2] 排除候選 v%d flat x %.0f 位置 (%.1f,%.1f,%.1f):%s" % (c["v"], c["flat_x"], *c["p"], why))
        cs.sort(key=lambda c: (c["press"], not c["sup"], c["n_att"] < 8, c["dmid"], -c["n_att"]))   # v2:綁點夠(>=8)就取近中段(v1 取綁點最多 → 選到 flat x 207 的角,綁 27 但只掀 25%)
        P("\n★ t=%.2f [%s] 抓點候選表(state v2;自由邊 %d 點;排序 = 沒被壓 > 有支撐(空隙<=15) > 預估綁>=8 > 近中段 > 綁點多)" % (t, sd, len(cs)))
        for k_, c in enumerate(cs):
            P("   CAND #%d v%-4d flat x %5.0f 位置 (%6.1f,%6.1f,%6.1f) 預估綁 %2d(窗上方 %2d)| 窗內 %2d 點被壓 %2d(%s)%s | 下方空隙 %5.1f %s"
              % (k_ + 1, c["v"], c["flat_x"], *c["p"], c["n_att"], c["n_above"], c["n_win"], c["n_press"], c["who"], " 壓住" if c["press"] else "", c["gap"], "" if c["sup"] else "沒支撐"))
        return cs

    def g_regrip(pl, t, n_att):
        """[robust] 綁點不足:上指抬起 → 換下一個候選(用當下狀態重算)→ 降、合;回傳 False = 沒候選"""
        offw, Pw, Pl, MUGl, mp = g_state(); sd = pl["sd"]
        cs = [c for c in g_site_cands(Pl, MUGl, sd, t) if c["v"] not in pl["tried"]]
        if not cs: return False
        c = cs[0]; v = c["v"]
        R0, slope = GPL.frame(Pl, v, rows=a.chord); tt_ = R0[:, 0]; M = GPL.mid(Pl)
        nbs = [b_ for b_ in (v - 1, v + 1) if 0 <= b_ < N1 and GSIDE2[b_] == sd and b_ // (a.nxy + 1) == v // (a.nxy + 1)]
        nb = min(nbs, key=lambda b_: np.linalg.norm(M[b_, :2])) if nbs else v
        p = M[v] + tt_ * float(np.dot(M[nb] - M[v], tt_)) / 2
        pc = p + R0 @ [0, -0.012, 0]; lo_f = pc - R0 @ [0, 0, GAPG / 2 + GFS[2] / 2]
        up_f = lo_f + R0 @ [0, 0, GFS[2] + GAPG]; up_pre = up_f + R0 @ [0, 0, 0.015]; up_above = up_pre + [0, 0, 0.06]
        pu0, _ = g_pose("up", t)
        g_lin("up", t, 0.5, pu0 + [0, 0, 0.05]); t_ = t + 0.5
        g_lin("up", t_, 0.8, up_above + offw, R0); t_ += 0.8
        g_lin("up", t_, 0.8, up_pre + offw); t_ += 0.8
        g_lin("up", t_, 0.8, up_f + offw); t_ += 0.8 + 0.7
        pl["retries"] += 1; pl["tried"].append(v); pl["rt0"] = t                 # [jaw2] rt0 只給下指視覺用
        _rv = {r["v"]: r for r in pl["rows"]}
        pl.update(v=v, nb=nb, R0=R0, p=p, lo_lift=lo_f, lo_f=lo_f, up_f=up_f, z_v0=float(M[v, 2]), t_grip=t_,
                  pick=dict(pl["pick"], v=v, p=M[v] * 1e3, slope=slope, gap=c["gap"], kind="tip"))
        pl.setdefault("retry_log", []).append(dict(t=t, n_att=n_att, v_new=v))
        P("★ t=%.2f [%s] RETRY %d/%d:綁 %d < %d → 上指抬起、換候選 v%d(flat x %.0f、預估綁 %d、空隙 %.1f);%.2f 再合指"
          % (t, sd, pl["retries"], a.grasp_retry, n_att, a.grasp_retry_min, v, c["flat_x"], c["n_att"], c["gap"], t_))
        return True

    def v2x_plan(sd, S0, sg, TOPS, cr0, offw, Pw, Pl, MUGl, mp, others):
        """[v2x] x 片 A(--v2_xmode sweep 撥開)/ B(outer 外側夾頂緣):排手 1 寬指路徑(不走 g_after_pick / g_grip_and_arc、不綁)。
        座標 o = 從杯心往外(sg·x);鉸點同 g_ut_arc(中間那一列從折線往外、最後一個仍貼桌面的頂點),材料長 L = 鉸點 → 自由邊(flat)"""
        M = GPL.mid(Pl); zg = BOXL["ZFLOOR"]; xm, yc = float((mp - offw)[0]), float((mp - offw)[1]); mode = a.v2_xmode
        jj = GPL.S["jj"]; cand = np.where(GSIDE2[:N1] == sd)[0]; jm = jj[cand[np.argmin(np.abs(GF2[cand, 1]))]]
        col = np.where((jj == jm) & (sg * GF2[:, 0] > CX - 1e-9))[0]; col = col[np.argsort(sg * GF2[col, 0])]
        k = 0
        while k + 1 < len(col) and M[col[k + 1], 2] < zg + T + 0.003: k += 1
        h = int(col[k]); hx = float(M[h, 0]); Bz = zg + T / 2; L = float(sg * GF2[col[-1], 0] - sg * GF2[h, 0]); o_h = sg * (hx - xm)
        o_end = o_h + a.ut_end_k * L
        z_ct = float(MUGl[:, 2].max()); o_cup = float((sg * (MUGl[:, 0] - xm)).max())
        th, d, wt = GFS[2], GFS[1], GFS[0]; oP = sg * (Pl[:, 0] - xm); inb = np.abs(Pl[:, 1] - yc) < wt / 2
        oi = (H3F[0] / 2 + 0.003) if (a.extract and a.extract_grip == "jaw") else 0.0   # 槳內緣避開手 2 的指 / 掌(杯頂中線 ±15 mm)
        z_safe = max(z_ct + 0.10, float(Pl[:, 2].max()) + 0.06)
        W = lambda o, z: np.array([xm + sg * o, yc, z]) + offw                  # 局部 (o, z) → 世界
        segs = []                                                             # (秒, up 中心 (o, z), lo 中心 (o, z))
        if mode == "sweep":                                                   # A:槳 = 上指(指面朝下 n = −z),下指疊在上面(合著、不碰布)
            R = np.column_stack([[0.0, sg, 0.0], [sg, 0.0, 0.0], [0.0, 0.0, -1.0]])
            sel = inb & (oP >= oi) & (oP <= o_cup) & (Pl[:, 2] > z_ct - 0.010)
            zf1 = max(z_ct + 0.0015, (float(Pl[sel, 2].max()) - 0.001) if sel.any() else 0.0)   # 指面:杯頂上的布頂 − 1 mm(壓著)
            o0 = oi + d / 2; o2 = o_cup + d / 2 + 0.005; o3 = o2 + 0.010; o4 = max(o_end, o3 + 0.030)
            zf3, zf4 = zg + 2 * T - 0.001, zg + T
            dz = th + GAPG
            _ev = np.where((GPL.S["ii"] == (0 if sd == "xn" else a.nxy)) & (GSIDE2[:N1] == sd) & (np.abs(GF2[:, 1]) < 0.04))[0]   # 自由邊(中間 ±40 mm)
            tip_o, tip_z = float(np.min(sg * (M[_ev, 0] - xm))), float(np.median(M[_ev, 2])); push = ""
            if a.v2_sweep_push and tip_z > zg + 0.030:                        # [v2x] A2:片尖還在杯上 → 先用直立的槳(指面朝外)貼著杯面把片尖往外推過杯的最外緣(讓它掉到杯外)
                R1 = np.column_stack([[0.0, sg, 0.0], [0.0, 0.0, 1.0], [sg, 0.0, 0.0]])   # t = y、u = +z(40 mm 高)、n = 往外
                _mv = np.abs(MUGl[:, 1] - yc) < 0.03; _mo, _mz = sg * (MUGl[_mv, 0] - xm), MUGl[_mv, 2]
                def cupz(o):                                                  # 杯在 o 處的頂面高(超出杯 → 杯最外緣那一點的高)
                    m_ = np.abs(_mo - o) < 0.003
                    return float(_mz[m_].max()) if m_.any() and o < o_cup else float(_mz[np.argmax(_mo)])
                c0 = max(tip_o - 0.008 - th / 2, oi + th / 2); oE = o_cup + th / 2 + 0.010; P1 = lambda c: (c, cupz(c + th / 2) - 0.001 + d / 2)   # 槳底邊 = 杯面 − 1 mm
                segs.append((1.0, (c0, P1(c0)[1] + 0.05), (c0 - dz, P1(c0)[1] + 0.05), R1)); segs.append((0.8, P1(c0), (c0 - dz, P1(c0)[1] + 0.015)))   # 下指在槳內側、高 15 mm(不碰杯面上的布)
                for c in np.linspace(c0, oE, 11)[1:]: segs.append((3.0 / 10, P1(c), (c - dz, P1(c)[1] + 0.015)))
                segs.append((0.6, (oE + 0.03, P1(oE)[1]), (oE + 0.03 - dz, P1(oE)[1] + 0.015))); segs.append((0.8, (oE + 0.03, z_safe), (oE + 0.03 - dz, z_safe)))
                segs.append((0.8, (o3, zf3 + 0.06 + th / 2), (o3, zf3 + 0.06 + th / 2 + dz), R))
                for du, o, zf in ((1.0, o3, zf3), (3.0, o4, zf4)): segs.append((du, (o, zf + th / 2), (o, zf + th / 2 + dz)))
                push = "A2 先推片尖:片尖 o %.1f z %.1f → 直立槳(指面朝外)從 o %.1f 貼杯面(底邊 = 杯面 − 1 mm)推到 o %.1f(杯外緣 %.1f + 10)再往外 30 mm、抬起;" % (tip_o * 1e3, tip_z * 1e3, (c0 + th / 2) * 1e3, (oE + th / 2) * 1e3, o_cup * 1e3)
            else:
                for du, o, zf in ((1.0, o0, zf1 + 0.06), (0.8, o0, zf1), (1.5, o2, zf1), (1.2, o3, zf3), (3.0, o4, zf4)):
                    segs.append((du, (o, zf + th / 2), (o, zf + th / 2 + dz)))
            info = push + "A 撥開:槳(寬指 %.0fx%.0f,指面朝下)杯頂上方 → 降到指面 z %.1f(杯頂 %.1f;杯頂上布頂 −1)→ 沿 %s 掃到 o %.1f(杯外緣 %.1f + 半指深 + 5)→ 斜降到 o %.1f 指面 z %.1f(桌面 + 2T − 1)→ 壓著往外掃到 o %.1f(鉸點 o %.1f + %.2f × L %.1f)指面 z %.1f(桌面 + T)" % (
                wt * 1e3, d * 1e3, zf1 * 1e3, z_ct * 1e3, "+x" if sg > 0 else "−x", o2 * 1e3, o_cup * 1e3, o3 * 1e3, zf3 * 1e3, o4 * 1e3, o_h * 1e3, a.ut_end_k, L * 1e3, zf4 * 1e3)
        else:                                                                 # B:兩指水平(n = +z),從片外側沿 −o 伸進去夾頂緣 → 往外、往下沿鉸點弧線拉到桌面
            R = np.column_stack([[0.0, -sg, 0.0], [sg, 0.0, 0.0], [0.0, 0.0, 1.0]])
            mf = (GSIDE2 == sd) & (np.abs(GF2[np.arange(len(Pl)) % N1, 1]) < 0.04) & (sg * GF2[np.arange(len(Pl)) % N1, 0] > CX + 0.030)
            vt = int(np.where(mf)[0][np.argmax(Pl[mf, 2])]); z_e = float(Pl[vt, 2]); o_e = float(oP[vt])   # 頂緣 = 片(中間 ±40 mm 列)最高點
            zl_top = z_e - T - 0.003                                          # 下指頂面:頂緣那層布底下 3 mm(捲起的片 = 捲內;斜靠的片 = 片外側)
            band = (GSIDE2 == sd) & inb & (Pl[:, 2] > zl_top - th - 0.002) & (Pl[:, 2] < zl_top + 0.002)
            o_out = float(oP[band].max()) if band.any() else o_e                  # 下指高度上片的最外緣(下指從外側水平伸進來會先碰到這裡)
            o_u = o_l = o_e - 0.015 + d / 2                                   # 兩指內緣都越過頂緣 15 mm(往杯的方向)
            zu0, zl0 = z_e + 0.008 + th / 2, zl_top - th / 2; zc = z_e - T / 2; zu1, zl1 = zc + GAPG / 2 + th / 2, zc - GAPG / 2 - th / 2   # 合:夾心 = 頂緣那層布中面,壓 1 mm
            segs += [(1.0, (o_u + 0.08, zu0 + 0.06), (o_l + 0.08, zl0 + 0.06)), (0.8, (o_u + 0.08, zu0), (o_l + 0.08, zl0)),
                     (1.0, (o_u, zu0), (o_l, zl0)), (0.8, (o_u, zu1), (o_l, zl1)), (0.3, (o_u, zu1), (o_l, zl1))]
            gc = np.array([(o_u + o_l) / 2, zc]); ofu, ofl = np.array([o_u, zu1]) - gc, np.array([o_l, zl1]) - gc
            g1 = gc + [0.030, 0.0]; segs.append((0.8, tuple(g1 + ofu), tuple(g1 + ofl)))   # 先往外拉 30 mm(離開杯側)
            ge = np.array([o_end, zg + T]); os_, zs = g1[0] - o_h, g1[1] - Bz; ph_s = float(np.arctan2(zs, os_)); r_s = float(np.hypot(os_, zs))
            oe, ze = ge[0] - o_h, ge[1] - Bz; ph_e = float(np.arctan2(ze, oe)); r_e = float(np.hypot(oe, ze))
            NA = 16
            for i_ in range(1, NA + 1):                                       # 繞鉸點的弧(半徑線性 r_s → r_e),分段直線近似
                w_ = i_ / NA; ph = ph_s + (ph_e - ph_s) * w_; r = r_s + (r_e - r_s) * w_; g = np.array([o_h + r * np.cos(ph), Bz + r * np.sin(ph)])
                segs.append((a.peel_t / NA, tuple(g + ofu), tuple(g + ofl)))
            segs.append((1.0, tuple(ge + ofu), tuple(ge + ofl)))
            info = "B 外側夾頂緣:頂緣 v%d o %.1f z %.1f(杯頂 %.1f、杯外緣 o %.1f)| 下指頂面 z %.1f 處片最外 o %.1f(下指從這裡往內推進)→ 下指內緣 o %.1f、上指內緣 o %.1f(越過頂緣 15 mm)| 合到夾心 z %.1f | 往外 30 mm → 繞鉸點弧 %.0f° → %.0f°、半徑 %.1f → %.1f(%.1f s)→ 終點夾心 o %.1f(鉸點 o %.1f + %.2f × L %.1f)z %.1f" % (
                vt, o_e * 1e3, z_e * 1e3, z_ct * 1e3, o_cup * 1e3, zl_top * 1e3, o_out * 1e3, (o_l - d / 2) * 1e3, (o_u - d / 2) * 1e3, zc * 1e3,
                np.degrees(ph_s), np.degrees(ph_e), r_s * 1e3, r_e * 1e3, a.peel_t, ge[0] * 1e3, o_h * 1e3, a.ut_end_k, L * 1e3, ge[1] * 1e3)
        t_ = S0; R0_ = segs[0][3] if len(segs[0]) > 3 else R
        for k_ in ("up", "lo"):                                               # 先抬到安全高度、平移到起點上方
            p0_, _ = GF[k_]["last"]; p0_ = np.array(p0_, float)
            g_lin(k_, t_, 0.6, np.array([p0_[0], p0_[1], max(p0_[2], z_safe + offw[2])]), R0_)
            o_, z_ = segs[0][1] if k_ == "up" else segs[0][2]
            g_lin(k_, t_ + 0.6, 1.0, W(o_, z_safe + (0.0 if k_ == "up" or len(segs[0]) > 3 else th + GAPG)))
        t_ += 1.6
        for sq_ in segs:
            du, pu, pl_ = sq_[:3]; Rs_ = sq_[3] if len(sq_) > 3 else None
            g_lin("up", t_, du, W(*pu), Rs_); g_lin("lo", t_, du, W(*pl_), Rs_); t_ += du
        TR = t_
        if mode == "sweep":                                                   # 放開:直接垂直抬 80 mm
            for k_ in ("up", "lo"): g_lin(k_, TR, 0.8, np.array(GF[k_]["last"][0]) + [0, 0, 0.08])
        else:                                                                 # 放開 = --ut_release_up 那套:張開到 +20 mm,上指垂直抬;下指(在桌面下)沿 +o 出布外再抬
            pu_, _ = GF["up"]["last"]; pl0_, _ = GF["lo"]["last"]; pu_ = np.array(pu_, float); pl0_ = np.array(pl0_, float)
            g_lin("up", TR, 0.5, pu_ + [0, 0, 0.020]); g_lin("up", TR + 0.5, 1.2, pu_ + [0, 0, 0.100])
            pA = pl0_ - [0, 0, 0.020]; pB = pA + np.array([sg * (d + 0.020), 0, 0])
            g_lin("lo", TR, 0.5, pA); g_lin("lo", TR + 0.5, 0.5, pB); g_lin("lo", TR + 1.0, 0.7, pB + [0, 0, 0.12])
        r_, _, _ = measure(S0, full=True)
        pl = dict(sd=sd, sg=sg, S0=S0, ax=0, C=CX, TOPS=TOPS, P0=Pw.copy(), Pl0=Pl.copy(), mug0=mp.copy(), others=np.isin(GSIDE2, others), osides=others,
                  slip=[], ev={}, xm=mode, rows=[], pick={}, cov0=(r_.get("lay") or {}).get("cov", float("nan")), TR=TR, hinge=(hx, Bz),
                  ut=dict(h=h, hy=hx, Bz=Bz, L=L, flat_h=float(GF2[h, 0]), n_gv=0), xlabel={"sweep": "撥開", "outer": "外側夾頂緣"}[mode], cr_cut=cr0)
        GS["plans"].append(pl)
        P("\n★ t=%.2f [%s] [v2x] 拆膠帶 %.1f s 後越線 %.0f%% → %s;鉸點 v%d x %.1f(o %.1f)z %.1f、材料長 L %.1f mm;杯頂覆蓋 %.0f%%;路徑 %.1f s,放開 @%.2f\n  [%s] [v2x] %s"
          % (S0, sd, a.v2_xcut_s, 100 * cr0, pl["xlabel"], h, hx * 1e3, o_h * 1e3, Bz * 1e3, L * 1e3, 100 * pl["cov0"], TR - S0, TR, sd, info))
        return pl

    def g_plan(sd, S0):
        """S0:用 sim 當下頂點算抓取點 → 排定挑角/下指/上指的 kinematic 路徑(掀的弧線在夾好後才排)。"""
        tw = time.time()
        offw, Pw, Pl, MUGl, mp = g_state()
        sg = -1.0 if sd in ("yn", "xn") else 1.0                              # [v2] xn 也是負側
        AX = 0 if sd[0] == "x" else 1; Cs = CX if AX == 0 else CY                 # [v2] x 片沿 x 軸(GPL.rank 只支援 y 片)
        others = {"yn": ("yp", "xp", "xn"), "yp": ("xp", "xn"), "xn": ("xp",), "xp": ("xn",)}[sd]
        if AX == 0:                                                           # [v2] x 片:自由邊 = 最外欄(i = 0 / NX)上屬於本片的頂點
            TOPS = GS.get("xtops", {}).get(sd)
            if TOPS is None: TOPS = np.where((GSIDE2 == sd) & (sg * Pl[:, 0] < CX - 0.003))[0]
            cr0 = float((sg * Pl[TOPS, 0] > CX).mean()) if len(TOPS) else float("nan")
            _M = GPL.mid(Pl); _ev = np.where((GPL.S["ii"] == (0 if sd == "xn" else a.nxy)) & (GSIDE2[:N1] == sd))[0]
            _vc = int(_ev[np.argmin(np.abs(GF2[_ev, 1]))]); _ztop = float(MUGl[:, 2].max())   # 自由邊中點、杯頂
            if a.v2_xmode in ("sweep", "outer") and cr0 < 0.8: return v2x_plan(sd, S0, sg, TOPS, cr0, offw, Pw, Pl, MUGl, mp, others)   # [v2x] A 撥開 / B 外側夾頂緣
            lean = cr0 < 0.8 and _M[_vc, 2] < _ztop - 0.010                   # 自由邊不在杯頂上(片立起斜靠在杯側):寬指要從杯和片之間插進去,只會推杯(A2 實測推 52 mm)→ 不夾
            if cr0 >= 0.8 or lean:                                            # 拆膠帶後自己攤開 → 不夾
                r_, _, _ = measure(S0, full=True)
                pl = dict(sd=sd, sg=sg, S0=S0, ax=AX, C=Cs, TOPS=TOPS, P0=Pw.copy(), Pl0=Pl.copy(), mug0=mp.copy(), others=np.isin(GSIDE2, others), osides=others,
                          slip=[], ev={}, skip=True, lean=bool(lean), rows=[], pick={}, cov0=(r_.get("lay") or {}).get("cov", float("nan")))
                GS["plans"].append(pl)
                if lean: P("\n★ t=%.2f [%s] [v2] 拆膠帶 %.1f s 後只開一部分(越線 %.0f%%),片立起斜靠在杯側:自由邊中點 z %.1f < 杯頂 %.1f − 10 mm → 不夾(寬指只能從杯和片之間插入、會推杯);杯頂覆蓋 %.0f%%"
                           % (S0, sd, a.v2_xcut_s, 100 * cr0, _M[_vc, 2] * 1e3, _ztop * 1e3, 100 * pl["cov0"]))
                else: P("\n★ t=%.2f [%s] [v2] 拆膠帶 %.1f s 後已自己攤開(越線 %.0f%% >= 80%%)→ 不夾;杯頂覆蓋 %.0f%%" % (S0, sd, a.v2_xcut_s, 100 * cr0, 100 * pl["cov0"]))
                return pl
            rows = []
            for _v in _ev:
                _R, _sl = GPL.frame(Pl, _v)
                rows.append(dict(v=int(_v), kind="tip", side=sd, flat=GF2[_v] * 1e3, p=_M[_v] * 1e3, slope=_sl, gap=GPL.gap_below(Pl, MUGl, _v, _R, BOXL) * 1e3,
                                 a=0, b=(0, 0, 0, 0), ok_a=True, ok_b=True))
                rows[-1]["ok_c"] = rows[-1]["ok"] = rows[-1]["gap"] >= 6.0
            rows.sort(key=lambda r: abs(r["flat"][1]))
            P("  [%s] [v2] 拆膠帶 %.1f s 後越線 %.0f%%(< 80%% → 夾);自由邊 %d 點" % (sd, a.v2_xcut_s, 100 * cr0, len(rows)))
        else:
            rows = GPL.rank(Pl, MUGl, sd, BOXL)
        P("\n★ t=%.2f [%s] 抓取點即時排名(%d 候選,(a)上方沒被壓 %d / (b)掃掠不撞 %d / (c)下方空隙>=6mm %d / 全過 %d;算了 %.1fs)"
          % (S0, sd, len(rows), sum(r["ok_a"] for r in rows), sum(r["ok_b"] for r in rows), sum(r["ok_c"] for r in rows),
             sum(r["ok"] for r in rows), time.time() - tw))
        for k_, r in enumerate(rows[:6]):
            P("   #%d v%-4d %-4s %-4s flat(%4.0f,%4.0f) 位置(箱局部) (%6.1f,%6.1f,%6.1f) 坡度 %5.1f° 下方空隙 %5.1f 上方他層 %d 掃掠 牆/底/杯/布 %s %s"
              % (k_ + 1, r["v"], r["kind"], r["side"], *r["flat"], *r["p"], r["slope"], r["gap"], r["a"], "/".join(map(str, r["b"])),
                 "OK" if r["ok"] else "NG"))
        okr = [r for r in rows if r["ok"]]
        rk = a.grasp_rank if sd == "yn" else 1
        ATT_MODE = bool(a.grasp_attach)
        ab = [r for r in rows if r["ok_a"] and r["ok_b"] and r["kind"] == "tip"]
        if ATT_MODE and ab:
            xs = [r["flat"][0] for r in rows if r["kind"] == "tip"]
            lo_x, hi_x = min(xs), max(xs)
            mid_ = [r for r in ab if r["flat"][0] - lo_x >= 40 and hi_x - r["flat"][0] >= 40] or ab
            pick = min(mid_, key=lambda r: abs(r["flat"][0] - (lo_x + hi_x) / 2))
            why = "綁定模式:自由邊中段(邊 flat x %.0f~%.0f,選 x=%.0f;只檢 a/b,跳過 c)" % (lo_x, hi_x, pick["flat"][0])
        elif okr:
            pick = rows[min(rk, len(okr)) - 1]; why = "合格第 %d 名" % min(rk, len(okr))
        else:
            pick = max(rows, key=lambda r: r["gap"]); why = "★ 沒有合格點 → 退而求其次:下方空隙最大"
        cands = g_site_cands(Pl, MUGl, sd, S0) if (a.grasp_site == "state" or a.grasp_retry > 0) and AX == 1 else []   # [v2] x 片不算候選表
        if a.grasp_site == "state" and ATT_MODE and cands:
            _rv = {r["v"]: r for r in rows}; pick = _rv[cands[0]["v"]]
            why = "★ state 選點:候選表第 1(預估綁 %d、%s、下方空隙 %.1f)" % (cands[0]["n_att"], "被壓" if cands[0]["press"] else "沒被壓", cands[0]["gap"])
        if WIDE:                                                              # [pgrasp] 寬指沿整條自由邊:取自由邊(tip)離邊中點最近的頂點
            _fa = 1 - AX                                                      # [v2] 沿自由邊的 flat 座標(y 片 = x、x 片 = y)
            _tp = [r for r in rows if r["kind"] == "tip"] or rows; _xs = [r["flat"][_fa] for r in _tp]; _xc = (min(_xs) + max(_xs)) / 2
            pick = min(_tp, key=lambda r: abs(r["flat"][_fa] - _xc))
            why = "[pgrasp] 寬指 %.0fx%.0fx%.0fmm 指間 %.1fmm:自由邊中點(flat %s %.0f~%.0f,選 %.0f)" % (*(GFS * 1e3), a.gap_mm, "xy"[_fa], min(_xs), max(_xs), pick["flat"][_fa])
        v = pick["v"]
        R0, slope = GPL.frame(Pl, v, rows=a.chord); tt_, uu, nn_ = R0[:, 0], R0[:, 1], R0[:, 2]
        if AX == 0 and a.v2_xmode == "tapegrip":                              # [v2x] D:x 片自由邊躺在杯頂上 → 夾爪框改水平(u = ±x、n = +z),下指沿杯頂水平滑到邊下(final 實測 chord 框斜 42°、u 帶 −0.28 y,下指從邊上方過去、夾到 1 點)
            _su = 1.0 if R0[0, 1] >= 0 else -1.0; R0 = np.column_stack([[0.0, -_su, 0.0], [_su, 0.0, 0.0], [0.0, 0.0, 1.0]]); tt_, uu, nn_ = R0[:, 0], R0[:, 1], R0[:, 2]
        M = GPL.mid(Pl); half = np.linalg.norm(Pl[v + N1] - Pl[v]) / 2
        i_, j_ = v % (a.nxy + 1), v // (a.nxy + 1)
        nbs = [v - 1, v + 1] if j_ in (0, a.nxy) else [v - (a.nxy + 1), v + (a.nxy + 1)]
        nbs = [b_ for b_ in nbs if 0 <= b_ < N1 and GSIDE2[b_] == sd]
        nb = min(nbs, key=lambda b_: np.linalg.norm(M[b_, :2])) if nbs else v
        toff = float(np.dot(M[nb] - M[v], tt_)) / 2
        p = M[v] + tt_ * toff
        P("  [%s] 選 %s:v%d(%s)位置 (%.1f,%.1f,%.1f) mm、邊坡度 %.1f°、下方空隙 %.1f mm;外法線 u=(%.2f,%.2f,%.2f);指面沿邊置中在 v%d/v%d 之間(t 偏 %.1fmm)"
          % (sd, why, v, pick["kind"], *(M[v] * 1e3), slope, pick["gap"], *uu, v, nb, toff * 1e3))
        pin = a.pick_in_mm / 1e3; lift = a.pick_mm / 1e3
        rod_ins = p + R0 @ [0, 0.020 - pin, -(half + 0.003 + GRS[2] / 2)]      # rod 長 30(沿 u):前端 = 中心 −15mm;起點前端在布邊外 +5mm,伸進 pin
        rod_pre = rod_ins + R0 @ [0, pin, 0]
        rod_above = rod_pre + [0, 0, 0.08]
        rod_lift = rod_ins + [0, 0, lift]
        rod_out = rod_lift + R0 @ [0, 0.045, 0]; rod_up = rod_out + [0, 0, 0.08]
        lo_f = rod_lift + R0 @ [0, (-0.0075) - (0.020 - pin), 0.0005]      # 下指足跡 u ∈ [−17.5, +2.5](布邊 u=0)
        lo_pre = lo_f + R0 @ [0, 0.032, 0]; lo_above = lo_pre + [0, 0, 0.06]
        up_f = lo_f + R0 @ [0, 0, GFS[2] + GAPG]
        up_pre = up_f + R0 @ [0, 0, 0.012]; up_above = up_pre + [0, 0, 0.06]
        W_ = lambda x: np.asarray(x) + offw
        if a.pick_mode == "jaw" and a.grasp_attach:
            pc = p + R0 @ [0, -0.012, 0]
            lo_lift = pc - R0 @ [0, 0, GAPG / 2 + GFS[2] / 2]      # 虛擬下指(不動,停在 park):只用來定夾爪框
            pl_extra = dict(lo_lift=lo_lift)
            P("  [%s] 綁定模式:下指不插入(停 park);上指從 +z 降到邊上方,指面中心在邊內 12mm %s" % (sd, np.round(pc * 1e3, 1)))
        elif a.pick_mode == "jaw":
            # 下指(20x20x8)本身挑角:足跡起點 u∈[+7,+27](= grasp_points (b) 檢查的下指掃掠)、頂面在布底下 3mm,沿 −u 伸進 pin,再上抬
            if slope >= a.steep_deg:
                lift = 0.0
                P("  [%s] 布邊坡度 %.1f° >= %.0f° → 角已翹起,不上抬(下指插到位後直接合上指)" % (sd, slope, a.steep_deg))
            lo_ins = p + R0 @ [0, (GFS[1] / 2 + 0.007 if WIDE else 0.017) - pin, -(half + a.clear_mm / 1e3 + GFS[2] / 2)]   # [pgrasp] 寬指:起點足跡 u∈[+7, +7+指深](20mm 指 = 舊 0.017)
            lo_pre_ = lo_ins + R0 @ [0, pin, 0]; lo_ab_ = lo_pre_ + [0, 0, 0.08]; lo_lift = lo_ins + [0, 0, lift]
            g_lin("lo", S0, GT["rod_above"], W_(lo_ab_), R0)
            t_ = S0 + GT["rod_above"]; g_lin("lo", t_, GT["rod_down"], W_(lo_pre_))
            t_ += GT["rod_down"]; g_lin("lo", t_, GT["rod_in"], W_(lo_ins))
            t_ += GT["rod_in"]; g_lin("lo", t_, GT["rod_lift"], W_(lo_lift))
            pl_extra = dict(lo_lift=lo_lift)
            P("  [%s] 挑角路徑(jaw 模式,箱局部 mm):下指從上方降到 %s(足跡 u∈[+7,+27]、頂面在布底下 %.0fmm)→ 沿 −u 伸進 %.0fmm 到 %s(足跡 u∈[%.0f,%.0f])→ 上抬 %.0fmm 到 %s"
              % (sd, np.round(lo_pre_ * 1e3, 1), a.clear_mm, pin * 1e3, np.round(lo_ins * 1e3, 1), (0.007 - pin) * 1e3, (0.027 - pin) * 1e3, lift * 1e3,
                 np.round(lo_lift * 1e3, 1)))
        if a.pick_mode == "rod":
            pl_extra = {}
            g_lin("rod", S0, GT["rod_above"], W_(rod_above), R0)
            t_ = S0 + GT["rod_above"]; g_lin("rod", t_, GT["rod_down"], W_(rod_pre))
            t_ += GT["rod_down"]; g_lin("rod", t_, GT["rod_in"], W_(rod_ins))
            t_ += GT["rod_in"]; g_lin("rod", t_, GT["rod_lift"], W_(rod_lift))
            t_ = S0 + G_TJAW                                  # 兩指夾好後 rod 才撤(第 2 次實跑:先撤 rod,布角落回去、下指撈不到)
            g_lin("rod", t_, GT["rod_out"], W_(rod_out)); g_lin("rod", t_ + GT["rod_out"], GT["rod_up"], W_(rod_up))
            g_lin("rod", t_ + GT["rod_out"] + GT["rod_up"], 1.0, GPARK["rod"])
            # 上/下指的路徑在挑角完(S0+G_TPICK)才用『當下』的布邊位置/局部框排(第 1 次實跑:照挑角前規劃 → 角幾乎直立時下指足跡整個在布邊外,夾到 0)
            P("  [%s] 挑角路徑(箱局部 mm):rod 從上方降到 %s(前端在布邊外 %.0fmm、頂面在布底下 3mm)→ 沿 −u 伸進 %.0fmm 到 %s → 上抬 %.0fmm 到 %s;下指進來後 rod 沿 +u 撤 45mm"
              % (sd, np.round(rod_pre * 1e3, 1), 5.0, pin * 1e3, np.round(rod_ins * 1e3, 1), lift * 1e3, np.round(rod_lift * 1e3, 1)))
        if AX == 1: TOPS = np.where((GSIDE2 == sd) & (sg * Pl[:, 1] < CY - 0.003))[0]   # [v2] x 片的 TOPS 在上面(拆膠帶前)
        r_, _, _ = measure(S0, full=True)
        pl = dict(sd=sd, sg=sg, ax=AX, C=Cs, S0=S0, v=v, nb=nb, R0=R0, p=p, half=half, pick=pick, rows=rows[:6], offw=offw, P0=Pw.copy(), Pl0=Pl.copy(),
                  mug0=mp.copy(), others=np.isin(GSIDE2, others), osides=others, TOPS=TOPS, lo_f=lo_f, up_f=up_f, z_v0=float(M[v, 2]),
                  cov0=(r_.get("lay") or {}).get("cov", float("nan")), r_plan=r_, slip=[], ev={}, cands=cands, tried=[v], retries=0, **pl_extra)
        SNAP["g_%s_plan" % sd] = (Pw.copy(), mug_world()[2].copy(), r_)
        P("  [%s] 翻面量測集:%s 片在折線(y=%+.1fmm)內側的頂點 %d 個;他片 %s 共 %d 頂點;杯頂俯視覆蓋 %.0f%%(露出 %.0f%%)"
          % (sd, sd, sg * Cs * 1e3, len(TOPS), "/".join(others), int(pl["others"].sum()), 100 * pl["cov0"], 100 * (1 - pl["cov0"])))
        GS["plans"].append(pl)
        return pl

    def g_after_pick(pl, t):
        offw, Pw, Pl, MUGl, mp = g_state(); v = pl["v"]
        M = GPL.mid(Pl); Rn, _ = GPL.frame(Pl, v)
        gap = GPL.gap_below(Pl, MUGl, v, Rn, BOXL) * 1e3
        d_ = np.linalg.norm(Pw - pl["P0"], axis=1)
        om = pl["others"] | ((GSIDE2 != pl["sd"]) & (GSIDE2 != "base"))
        oth = (GSIDE2 != pl["sd"])
        n10 = int((d_[oth] > 0.010).sum())
        pl["ev"]["pick"] = dict(z0=pl["z_v0"] * 1e3, z1=float(M[v, 2]) * 1e3, gap0=pl["pick"]["gap"], gap1=gap, adj_n10=n10,
                                adj_max=float(d_[oth].max()) * 1e3, adj_tot=int(oth.sum()))
        e = pl["ev"]["pick"]
        P("\n★ t=%.2f [%s] 挑角完:角 v%d z %.1f → %.1f mm(+%.1f);下方空隙 %.1f → %.1f mm;相鄰層(非 %s 片)位移 >10mm 頂點 %d / %d,最大 %.1f mm"
          % (t, pl["sd"], v, e["z0"], e["z1"], e["z1"] - e["z0"], e["gap0"], e["gap1"], pl["sd"], n10, e["adj_tot"], e["adj_max"]))
        SNAP["g_%s_pick" % pl["sd"]] = (Pw.copy(), mug_world()[2].copy(), measure(t)[0])
        if a.pick_mode == "jaw":
            # 上指:在挑角時的局部框 R0 裡,停在下指正上方 15mm(先從 +z 垂直降),再沿 −n 合到指面間距 gap
            R0 = pl["R0"]; lo_f = pl["lo_lift"]; up_f = lo_f + R0 @ [0, 0, GFS[2] + GAPG]
            up_pre = up_f + R0 @ [0, 0, 0.015]; up_above = up_pre + [0, 0, 0.06]
            W_ = lambda x: np.asarray(x) + offw
            t_ = pl["S0"] + G_TPICK
            g_lin("up", t_, GT["lo_above"], W_(up_above), R0); t_ += GT["lo_above"]
            g_lin("up", t_, GT["lo_down"], W_(up_pre)); t_ += GT["lo_down"]
            g_lin("up", t_, GT["close"], W_(up_f))
            pl.update(lo_f=lo_f, up_f=up_f)
            if a.hand1_jaw and a.grasp_attach:                                # [jaw2] 純視覺下指:布邊外 35mm 上方 → 降 → 沿 −u 滑到布下(上指合之前到位)
                GF["lov"]["last"] = JVS.get("lov", (GPARK["lov"], np.eye(3))); lo_o = lo_f + R0 @ [0, 0.035, 0]; t_ = pl["S0"] + G_TPICK
                g_lin("lov", t_, GT["lo_above"], W_(lo_o + [0, 0, 0.06]), R0); t_ += GT["lo_above"]
                g_lin("lov", t_, GT["lo_down"] / 2, W_(lo_o)); g_lin("lov", t_ + GT["lo_down"] / 2, GT["lo_down"] / 2, W_(lo_f))
            Lk = (Pw - (lo_f + offw)) @ R0
            on = (np.abs(Lk[:, 0]) < GFS[0] / 2) & (np.abs(Lk[:, 1]) < GFS[1] / 2) & (Lk[:, 2] > GFS[2] / 2 - 0.001) & (Lk[:, 2] < GFS[2] / 2 + 0.008)
            P("  [%s] 上指:從 +z 降到下指正上方 %s → 沿 −n 合 15mm 到 %s(指面間距 %.1fmm);挑角後躺在下指頂面上(0~7mm)的布頂點 %d 個"
              % (pl["sd"], np.round(up_pre * 1e3, 1), np.round(up_f * 1e3, 1), a.gap_mm, int(on.sum())))
            return
        # 用當下的布邊排上/下指
        R1, sl1 = GPL.frame(Pl, v); t1 = R1[:, 0]
        nb = pl["nb"]; toff = float(np.dot(M[nb] - M[v], t1)) / 2 if nb != v else 0.0
        p1 = M[v] + t1 * toff
        lo_f = p1 + R1 @ [0, -0.0075, -(GAPG / 2 + GFS[2] / 2)]; up_f = p1 + R1 @ [0, -0.0075, GAPG / 2 + GFS[2] / 2]
        # ★ 第 3 次實跑:下指頂面貼布底(−2.25mm)沿 −u 插 → 撞到被 rod 折彎的布角、把它推掉,夾到 0。
        #   改成「張口 = 間距 + 2x10mm」從布邊外沿 −u 同時插上下兩指(上指在布上方 10mm、下指在布下方 10mm),再對稱合到 4.5mm
        OPEN = 0.010
        lo_o = lo_f + R1 @ [0, 0, -OPEN]; up_o = up_f + R1 @ [0, 0, OPEN]
        lo_pre = lo_o + R1 @ [0, 0.032, 0]; lo_above = lo_pre + [0, 0, 0.06]
        up_pre = up_o + R1 @ [0, 0.032, 0]; up_above = up_pre + [0, 0, 0.06]
        W_ = lambda x: np.asarray(x) + offw
        for k_, ab_, pr_, o_, f_ in (("lo", lo_above, lo_pre, lo_o, lo_f), ("up", up_above, up_pre, up_o, up_f)):
            t_ = pl["S0"] + G_TPICK
            g_lin(k_, t_, GT["lo_above"], W_(ab_), R1); t_ += GT["lo_above"]
            g_lin(k_, t_, GT["lo_down"], W_(pr_)); t_ += GT["lo_down"]
            g_lin(k_, t_, GT["lo_in"], W_(o_)); t_ += GT["lo_in"]
            g_lin(k_, t_, GT["close"], W_(f_))
        pl.update(lo_f=lo_f, up_f=up_f, R0=R1)
        P("  [%s] 夾爪路徑(用挑角後的布邊:v%d (%.1f,%.1f,%.1f) 坡度 %.1f°,外法線 u=(%.2f,%.2f,%.2f)):張口 %.1fmm 的上/下指從上方降到布邊外 32mm(下 %s / 上 %s)"
              "→ 沿 −u 平移 32mm(足跡 u∈[−17.5,+2.5])→ 對稱合到 下 %s / 上 %s(指面間距 %.1fmm);合好後 rod 沿 +u 撤"
          % (pl["sd"], v, *(M[v] * 1e3), sl1, *R1[:, 1], a.gap_mm + 2 * OPEN * 1e3, np.round(lo_pre * 1e3, 1), np.round(up_pre * 1e3, 1),
             np.round(lo_f * 1e3, 1), np.round(up_f * 1e3, 1), a.gap_mm))

    def g_grip_and_arc(pl, t):
        """夾好:登記夾到的頂點;用『現在』的彎折處排弧線(半徑 = arc_k x 材料長度)+ 停 + 放開。"""
        offw, Pw, Pl, MUGl, mp = g_state(); sd, sg, v = pl["sd"], pl["sg"], pl["v"]
        G_, L_ = g_between(Pw, t)
        pl["G"] = G_; pl["rel0"] = L_[G_].copy()
        try:
            _tr = GFV.get_transforms(); _tr = _tr.numpy() if hasattr(_tr, "numpy") else np.asarray(_tr)
            for i_, pth_ in enumerate(GFV.prim_paths):
                k_ = [kk for kk in GKEYS if GPATH[kk] == pth_][0]
                P("  [%s] 實際 %s 位置(箱局部)%s mm vs 目標 %s" % (sd, k_, np.round((_tr[i_, :3] - offw) * 1e3, 1), np.round((g_pose(k_, t)[0] - offw) * 1e3, 1)))
        except Exception as e_:
            P("  get_transforms 失敗 %s" % e_)
        P("\n★ t=%.2f [%s] 夾好:指面之間(間距 %.1fmm、足跡 20x20)的布頂點 %d 個(歸屬 %s)"
          % (t, sd, a.gap_mm, len(G_), dict(zip(*np.unique(GSIDE2[G_], return_counts=True))) if len(G_) else {}))
        _m25 = (np.abs(L_[:, 0]) < GFS[0] / 2 + 0.0025) & (np.abs(L_[:, 1]) < GFS[1] / 2 + 0.0025) & (np.abs(L_[:, 2]) <= GAPG / 2 + 0.0025)
        _near = (np.abs(L_[:, 0]) < 0.03) & (np.abs(L_[:, 1]) < 0.03) & (np.abs(L_[:, 2]) < 0.03)
        P("  [%s] 參考:足跡外擴 2.5mm、離指面 <=2.5mm 的布頂點 %d 個;夾爪 30mm 內布頂點的 (t,u,n) mm:%s"
          % (sd, int(_m25.sum()), "; ".join("v%d(%.0f,%.0f,%.0f)" % (q, *(L_[q] * 1e3)) for q in np.where(_near)[0][:14])))
        pl["ev"]["grip"] = dict(n=len(G_), n25=int(_m25.sum()))
        if a.grasp_attach:
            pad = a.attach_pad_mm / 1e3
            nlo = a.attach_nlo_mm / 1e3 if a.attach_nlo_mm >= 0 else GAPG / 2 + 0.004
            ma = (np.abs(L_[:, 0]) < pad) & (np.abs(L_[:, 1]) < pad) & (L_[:, 2] <= GAPG / 2 + 0.004) & (L_[:, 2] >= -nlo) & (GSIDE2 == sd)
            if a.attach_layer == "top":
                ma &= L_[:, 2] > 0
            if a.attach_mask_own:                                             # [drag] 排除被他片壓住的頂點
                import layer_order as LO
                _Mm = GPL.mid(Pl) * 1e3; _idx, _over, _who, _under = LO.analyze(_Mm, GSIDE2[:N1], sd, r=a.attach_mask_r_mm, dz=a.attach_mask_dz_mm)
                _bad = np.zeros(N1, bool); _bad[_idx] = _over if a.attach_mask_own == 1 else (_over | (np.array(_under) != ""))
                _ma0 = ma.copy(); ma = ma & ~_bad[np.arange(len(ma)) % N1]
                _rm = np.where(_ma0 & ~ma)[0]; _pos = {v_: k_ for k_, v_ in enumerate(_idx)}
                P("  [%s] 綁定遮罩 own=%d r=%.0f dz=%.0f:候選 %d → 排除被壓/貼他片 %d → 綁 %d(壓住者 %s;貼在 %s 上)"
                  % (sd, a.attach_mask_own, a.attach_mask_r_mm, a.attach_mask_dz_mm, int(_ma0.sum()), len(_rm), int(ma.sum()),
                     dict(zip(*np.unique([_who[_pos[q % N1]] for q in _rm] or ["-"], return_counts=True))),
                     dict(zip(*np.unique([_under[_pos[q % N1]] for q in _rm] or ["-"], return_counts=True)))))
                pl["mask_removed"] = int(len(_rm))
                if ma.sum() == 0:
                    ma = _ma0; P("  [%s] ★ 遮罩後 0 點 → 退回不遮罩" % sd)
            AV = np.where(ma)[0]
            if a.grasp_retry > 0 and len(AV) < a.grasp_retry_min and pl["retries"] < a.grasp_retry:   # [robust]
                if g_regrip(pl, t, len(AV)):
                    del pl["ev"]["grip"]; return
                P("  [%s] ★ RETRY:沒有剩下的候選,照綁 %d 點" % (sd, len(AV)))
            pu_, Ru_ = g_pose("up", t)
            loc = (Pw[AV] - pu_) @ Ru_
            scp = "/World/gatt_%s" % sd
            AVu = AV if a.attach_nlo_mm < 0 else AV[L_[AV, 2] >= 0]
            AVl = np.array([], int) if a.attach_nlo_mm < 0 else AV[L_[AV, 2] < 0]
            _astf = a.attach_stiff if a.attach_stiff > 0 else float("inf")
            _adamp = a.attach_damp if a.attach_damp >= 0 else 2 * np.sqrt(a.attach_stiff * a.areal * WX * WY / len(Pw))
            if len(AVu) and a.attach_proxy:                               # [drag] 綁到代理(以代理當下 pose 算 local)
                _pp, _pq = g_proxy_pose(); _pR = Ru_                       # 旋轉被 joint 鎖住 = 上指旋轉
                P("  [%s] 代理 upx 位置 %s mm(上指目標 %s;落後 %.2f mm)" % (sd, np.round((_pp - offw) * 1e3, 1), np.round((pu_ - offw) * 1e3, 1), np.linalg.norm(_pp - pu_) * 1e3))
                VC.attach_vtx(st, scp, "/World/plate", "/World/plate", GPATH["upx"], AVu, (Pw[AVu] - _pp) @ _pR, P=P, stiff=_astf, damp=_adamp)
            elif len(AVu):
                VC.attach_vtx(st, scp, "/World/plate", "/World/plate", GPATH["up"], AVu, (Pw[AVu] - pu_) @ Ru_, P=P, stiff=_astf, damp=_adamp)
            if len(AVl):
                pl_, Rl_ = g_pose("lo", t)
                VC.attach_vtx(st, scp + "_lo", "/World/plate", "/World/plate", GPATH["lo"], AVl, (Pw[AVl] - pl_) @ Rl_, P=P, stiff=_astf, damp=_adamp)
            P("  [%s] 綁到上指 %d / 下指 %d(n 範圍 [%.1f, %.1f] mm)stiff=%s damp=%g" % (sd, len(AVu), len(AVl), -nlo * 1e3, (GAPG / 2 + 0.004) * 1e3, _astf, _adamp))
            pl["att"] = dict(scope=scp, vids=AV, n=len(AV), on=bool(len(AV)), loc0=loc.copy(), lo=bool(len(AVl)))
            pl["ev"]["grip"]["n_att"] = len(AV)
            P("★ t=%.2f [%s] 綁住 %d 個頂點(%s;足跡半寬 %.0fmm、|n|<=%.1fmm、層 %s);指間非 %s 頂點(未綁)%d"
              % (t, sd, len(AV), sd, pad * 1e3, (GAPG / 2 + 0.004) * 1e3, a.attach_layer, sd,
                 int(((np.abs(L_[:, 0]) < pad) & (np.abs(L_[:, 1]) < pad) & (np.abs(L_[:, 2]) <= GAPG / 2 + 0.004) & (GSIDE2 != sd)).sum())))
        if a.hold_others:                                                     # [drag] 釘住他片靠折線側(含耳朵)
            hs = [x_ for x_ in a.hold_sides.split(",") if x_]
            mh = np.isin(GSIDE2, hs) & (sg * FLAT[:, 1] >= CY - a.hold_pad_mm / 1e3)
            if a.hold_region == "own": mh = np.isin(GSIDE2, hs) & (np.abs(FLAT[:, 0]) <= CX + a.hold_pad_mm / 1e3)   # [drag2]
            if a.hold_layer == "top": mh &= np.arange(len(mh)) >= N1
            if a.hold_layer == "topfree":                                     # [drag2] 只取上層、且 layer_order 判定沒被別片壓住
                import layer_order as LO
                _Mm = GPL.mid(Pl) * 1e3; _free = np.zeros(len(mh), bool)
                for _s in hs:
                    _i, _o, _, _ = LO.analyze(_Mm, GSIDE2[:N1], _s, r=a.attach_mask_r_mm, dz=a.attach_mask_dz_mm)
                    _free[_i[~_o] + N1] = True
                mh &= _free
            if a.hold_min_d_mm > 0 and pl.get("att", {}).get("n", 0) > 0:      # [drag2] 離綁定區
                _A = Pw[np.asarray(pl["att"]["vids"]), :2]
                _d = np.min(np.linalg.norm(Pw[:, None, :2] - _A[None], axis=2), axis=1)
                mh &= _d >= a.hold_min_d_mm / 1e3
            HV = np.where(mh)[0]
            if len(HV):
                VC.attach_vtx(st, "/World/ghold_%s" % sd, "/World/plate", "/World/plate", "/World/ghold/anc", HV, Pw[HV] - HOLD_ANC, P=P)
            pl["hold"] = dict(scope="/World/ghold_%s" % sd, vids=HV, n=len(HV), on=bool(len(HV)), P0=Pw[HV].copy())
            P("★ t=%.2f [%s] 壓住(釘)他片 %d 點(%s;flat 折線內 %.0f mm;層 %s;z %.0f~%.0f mm;模式 %s)"
              % (t, sd, len(HV), dict(zip(*np.unique(GSIDE2[HV], return_counts=True))) if len(HV) else {}, a.hold_pad_mm, a.hold_layer,
                 (Pw[HV, 2].min() - offw[2]) * 1e3 if len(HV) else np.nan, (Pw[HV, 2].max() - offw[2]) * 1e3 if len(HV) else np.nan, a.hold_mode))
        SNAP["g_%s_grip" % sd] = (Pw.copy(), mug_world()[2].copy(), measure(t)[0])
        if UTT: return g_ut_arc(pl, t, offw, Pl)                              # [table]([v2] 取出後同)
        col_i = v % (a.nxy + 1)
        hy, hz, hfy, ym, zm, nc = GPL.hinge(Pl, sd, col_i)
        if not (np.isfinite(hy) and np.isfinite(hz)) and a.hinge_from_state:
            _hs = GPL.hinge_state(Pl, sd, col_i, BOXL["ZFLOOR"], r_mm=a.attach_mask_r_mm, dz_mm=a.attach_mask_dz_mm)
            if _hs is not None:
                hy, hz, hfy = _hs[0], _hs[1], _hs[2]
                P("  [%s] [peel2] 彎折處偵測 nan(欄數 %d)→ 頂點狀態求實際彎折 y=%.1f z=%.1f mm flat y=%.1f(著地 %d 點)" % (sd, nc, hy * 1e3, hz * 1e3, hfy * 1e3, _hs[3]))
        if not (np.isfinite(hy) and np.isfinite(hz)):
            P("  [%s] ★ 彎折處偵測 nan(欄數 %d)→ 用名義折線 y=%+.1f z=106.0 mm" % (sd, nc, sg * CY * 1e3))
            hy, hz = sg * CY, 0.106
        if not np.isfinite(hfy): hfy = sg * CY
        M = GPL.mid(Pl)
        col = np.where((GPL.S["ii"] == col_i) & (sg * GF2[:, 1] > CY - 1e-9))[0]
        col = col[np.argsort(sg * GF2[col, 1])]
        kb = int(np.argmin(np.abs(GF2[col, 1] - hfy))) if np.isfinite(hfy) else 0
        seg = col[kb:]; Lcur = float(np.linalg.norm(np.diff(M[seg], axis=0), axis=1).sum()) if len(seg) > 1 else float("nan")
        Lflat = float(abs(GF2[v, 1] - hfy))
        if a.grasp_attach and pl.get("att", {}).get("n", 0) > 0:
            Lflat = float(np.median(np.abs(GF2[np.asarray(pl["att"]["vids"]) % N1, 1] - hfy)))
        Lmat = max(Lcur, Lflat)
        Rr = a.arc_k * (Lmat - 0.0075)
        if a.hinge_from_state: P("  [%s] [peel2] 鉸點 y=%.1f z=%.1f mm flat y=%.1f;材料長 現在 %.1f / flat %.1f → %.1f mm" % (sd, hy * 1e3, hz * 1e3, hfy * 1e3, Lcur * 1e3, Lflat * 1e3, Lmat * 1e3))
        up_f, lo_f, R0 = pl["up_f"], pl["lo_f"], pl["R0"]; TP0 = t
        if a.lift_first_mm > 0:                                               # [drag] 先直線拉起再轉弧
            dl = (np.array([0, 0, 1.0]) if a.lift_first_dir == "z" else R0[:, 2]) * a.lift_first_mm / 1e3
            dl = dl + np.array([0, sg * a.lift_first_out_mm / 1e3, 0])       # [drag2] 往箱外抽(lift_first_out_mm=0 不變)
            for k_ in (("up",) if a.grasp_attach else ("up", "lo")):
                g_lin(k_, t, a.lift_first_t, pl[k_ + "_f"] + dl + offw, R0)
            up_f, lo_f = up_f + dl, lo_f + dl; TP0 = t + a.lift_first_t
            P("  [%s] 先沿 %s 拉起 %.0f mm(%.1f s)再轉弧" % (sd, a.lift_first_dir, a.lift_first_mm, a.lift_first_t))
        gc0 = (lo_f + up_f) / 2
        o_ = {"up": up_f - gc0, "lo": lo_f - gc0}
        Ba, Bz = -sg * hy, hz
        Ea, Ez = -(IY + 0.0015), CBOX["top_y"] + T / 2 + 0.002
        a0, z0 = -sg * gc0[1] - Ba, gc0[2] - Bz; r0 = float(np.hypot(a0, z0)); th0 = float(np.arctan2(z0, a0))
        BE = float(np.hypot(Ea - Ba, Ez - Bz)); th1 = float(np.arctan2(Ez - Bz, Ea - Ba))
        if a.arc_grow_max_mm > 0 and Rr > r0 + a.arc_grow_max_mm / 1e3:       # [peel]
            P("  [%s] [peel] 弧半徑 %.1f → %.1f mm(r0 %.1f + %.0f)" % (sd, Rr * 1e3, (r0 + a.arc_grow_max_mm / 1e3) * 1e3, r0 * 1e3, a.arc_grow_max_mm))
            Rr = r0 + a.arc_grow_max_mm / 1e3
        R2 = Rr - BE; two = (R2 > 0.012) and bool(a.arc2)
        if th0 >= th1:
            th1 = th0
        s1 = Rr * (th1 - th0); s2 = R2 * (np.pi - th1) if two else 0.0
        zclear = lid_top_local(sd) + T + 0.002
        axis = np.array([-sg, 0.0, 0.0])
        corners = np.array(list(itertools.product((-1, 1), repeat=3)), float) * GFS / 2
        def at(w):
            s_ = w * (s1 + s2)
            if not two or s_ <= s1:
                th = th0 + (th1 - th0) * (s_ / s1 if s1 > 0 else 1.0)
                r = r0 + (Rr - r0) * min(1.0, (th - th0) / max(1e-6, 0.3 * (th1 - th0)))
                A_, Z_ = Ba + r * np.cos(th), Bz + r * np.sin(th)
            else:
                th = th1 + (np.pi - th1) * ((s_ - s1) / s2)
                A_, Z_ = Ea + R2 * np.cos(th), Ez + R2 * np.sin(th)
            Rt = rotm(axis, th - th0)
            gc = np.array([gc0[0], -sg * A_, Z_])
            Pf = {k_: gc + Rt @ o_[k_] for k_ in o_}; Rf = Rt @ R0
            cs = np.array([Pf[k_] + c_ @ Rf.T for k_ in Pf for c_ in corners])
            m_ = sg * cs[:, 1] > IY - 0.003
            if m_.any():
                dz = max(0.0, zclear - cs[m_, 2].min())
                Pf = {k_: Pf[k_] + [0, 0, dz] for k_ in Pf}
            return Pf, Rf, th
        TP1 = TP0 + a.peel_t
        for k_ in (("up",) if a.grasp_attach else ("up", "lo")):
            g_fn(k_, TP0, a.peel_t, lambda w, k_=k_: (at(w)[0][k_] + offw, at(w)[1]))
        if not np.all(np.isfinite([r0, th0, th1, Rr])):
            raise RuntimeError("弧線參數 nan: r0=%s th0=%s th1=%s Rr=%s" % (r0, th0, th1, Rr))
        Pf1, Rf1, th_e = at(1.0)
        n_e, u_e = Rf1[:, 2], Rf1[:, 1]
        if a.arc2_ext_mm > 0:                                                 # [drag2] 弧線終點再往箱外延伸
            Pf1 = {k_: Pf1[k_] + np.array([0, sg * a.arc2_ext_mm / 1e3, 0]) for k_ in Pf1}
            for k_ in (("up",) if a.grasp_attach else ("up", "lo")):
                g_lin(k_, TP1, a.arc2_ext_t, Pf1[k_] + offw, Rf1)
            P("  [%s] 弧線終點再往箱外延伸 %.0f mm(%.1f s)" % (sd, a.arc2_ext_mm, a.arc2_ext_t)); TP1 = TP1 + a.arc2_ext_t
        if a.arc2_over_mm > 0 or a.arc2_target == "centroid":                # [peel] 越過箱壁外緣並轉到 180°
            CLm = a.arc2_target == "centroid"                                 # [peel3]
            Dm = a.arc2_cl_max_mm / 1e3 if CLm else max(0.005, min(a.arc2_over_mm / 1e3, Lmat - BE - 0.005) if a.arc2_over_cap else a.arc2_over_mm / 1e3)
            if not a.arc2_over_cap or CLm: P("  [%s] [peel3] 越壁不截:%.1f mm(舊上限會是 %.1f)" % (sd, Dm * 1e3, (Lmat - BE - 0.005) * 1e3))
            gce = (Pf1["up"] + Pf1["lo"]) / 2; o2 = {k_: Rf1.T @ (Pf1[k_] - gce) for k_ in Pf1}
            gct = np.array([gce[0], sg * (IY + Dm), gce[2]])
            def over(w, gce=gce, gct=gct, o2=o2, Rf1=Rf1, th_e=th_e):
                th = th_e + (np.pi - th_e) * min(1.0, w * (3.0 if CLm else 1.0)); Rt = rotm(axis, th - th_e)
                gc = gce + (gct - gce) * w - np.array([0, 0, a.arc2_cl_down_mm / 1e3 * w if CLm else 0.0]); Rf = Rt @ Rf1
                Pf = {k_: gc + Rf @ o2[k_] for k_ in o2}
                cs = np.array([Pf[k_] + c_ @ Rf.T for k_ in Pf for c_ in corners])
                m_ = sg * cs[:, 1] > IY - 0.003
                if m_.any():
                    dz = max(0.0, zclear - cs[m_, 2].min()); Pf = {k_: Pf[k_] + [0, 0, dz] for k_ in Pf}
                return Pf, Rf
            if CLm:                                                           # [peel3] w 由時間推進,達標/守衛時凍結
                pl["cl"] = dict(T0=TP1, wf=1.0, stop=None, next=TP1, over=over)
                def wcl(pl=pl):
                    c_ = pl["cl"]; w_ = min(1.0, max(0.0, (CL["t"] - c_["T0"]) / a.arc2_cl_t))
                    return w_ if c_["stop"] is None else min(w_, c_["stop"])
                for k_ in (("up",) if a.grasp_attach else ("up", "lo")):
                    g_fn(k_, TP1, a.arc2_cl_t + 1.0, lambda w, k_=k_: (over(wcl())[0][k_] + offw, over(wcl())[1]))
            else:
                for k_ in (("up",) if a.grasp_attach else ("up", "lo")):
                    g_fn(k_, TP1, a.arc2_over_t, lambda w, k_=k_: (over(w)[0][k_] + offw, over(w)[1]))
            Pf1, Rf1 = over(1.0); n_e, u_e = Rf1[:, 2], Rf1[:, 1]
            P("  [%s] [peel] 越過箱壁外緣 %.1f mm(要求 %.0f;材料長 %.1f − 鉸點到頂角 %.1f − 5)轉到 180°(%.1f s);終點夾爪中心 y=%.1f z=%.1f mm"
              % (sd, Dm * 1e3, a.arc2_over_mm, Lmat * 1e3, BE * 1e3, a.arc2_over_t, ((Pf1["up"] + Pf1["lo"]) / 2)[1] * 1e3, ((Pf1["up"] + Pf1["lo"]) / 2)[2] * 1e3))
            TP1 = TP1 + (a.arc2_cl_t + 1.0 if CLm else a.arc2_over_t)
            if a.arc2_lay:                                                    # [peel4] 沿箱壁外側往下,讓片躺到打開的蓋上
                zlay = zclear - T                                             # 箱外指頭最低點下限:蓋頂 + 2mm(舊:+T+2)
                def layf(w, P0=(Pf1, Rf1)):
                    Pq, Rq_ = pl["cl"]["over"](pl["cl"]["wf"]) if CLm else P0; cs = np.array([Pq[k_] + c_ @ Rq_.T for k_ in Pq for c_ in corners])
                    m_ = pl["sg"] * cs[:, 1] > IY - 0.003; dz = (cs[m_, 2].min() - zlay) if m_.any() else 0.0
                    if pl.get("lay", {}).get("stop") is not None: w = min(w, pl["lay"]["stop"])
                    return {k_: Pq[k_] - np.array([0, 0, max(0.0, dz) * w]) for k_ in Pq}, Rq_
                pl["lay"] = dict(T0=TP1, stop=None, f=layf)
                for k_ in (("up",) if a.grasp_attach else ("up", "lo")):
                    g_fn(k_, TP1, a.arc2_lay_t, lambda w, k_=k_: (layf(w)[0][k_] + offw, layf(w)[1]))
                Pf1, Rf1 = layf(1.0); n_e, u_e = Rf1[:, 2], Rf1[:, 1]
                P("  [%s] [peel4] 往下貼蓋:箱外指頭最低點下限 蓋頂 %.1f + 2 = %.1f mm(舊 %.1f);預計夾爪中心 z %.1f → %.1f(%.1f s,再停 %.1f s 放手;邊長比 > %.2f 凍結)"
                  % (sd, (zclear - T - 0.002) * 1e3, zlay * 1e3, zclear * 1e3, ((over(1.0)[0]["up"] + over(1.0)[0]["lo"]) / 2)[2] * 1e3,
                     ((Pf1["up"] + Pf1["lo"]) / 2)[2] * 1e3, a.arc2_lay_t, GT["peel_hold"], a.arc2_er_stop))
                TP1 = TP1 + a.arc2_lay_t
        if a.release_press_mm > 0 or a.release_settle_s > 0:                  # [peel] 放手前下壓 + 停
            if a.release_press_mm > 0:
                Pf1 = {k_: Pf1[k_] - np.array([0, 0, a.release_press_mm / 1e3]) for k_ in Pf1}
                for k_ in (("up",) if a.grasp_attach else ("up", "lo")):
                    g_lin(k_, TP1, 0.5, Pf1[k_] + offw, Rf1)
                TP1 = TP1 + 0.5
            P("  [%s] [peel] 放手前下壓 %.0f mm 再停 %.1f s" % (sd, a.release_press_mm, a.release_settle_s)); TP1 = TP1 + a.release_settle_s
        TR = TP1 + GT["peel_hold"]
        for k_, sgn in ((("up", 1.0),) if a.grasp_attach else (("up", 1.0), ("lo", -1.0))):
            if a.hold_yp and sd == "yp": continue                             # [extract] yp 不放手:不排放開軌跡
            if "lay" in pl:                                                   # [peel4] 放手:從(凍結的)貼蓋位置先往箱外抽 40mm 再抬
                def relL(w, k_=k_, ph=0):
                    Pq, Rq_ = pl["lay"]["f"](1.0); p1 = Pq[k_] + offw; B = p1 + np.array([0, pl["sg"] * 0.040, 0]); C = B + [0, 0, 0.08]
                    return (p1 if ph == 0 else (p1 + (B - p1) * w) if ph == 1 else (B + (C - B) * w)), Rq_
                g_fn(k_, TR, GT["rel_open"], lambda w, f=relL: f(w, ph=0))
                g_fn(k_, TR + GT["rel_open"], GT["rel_slide"], lambda w, f=relL: f(w, ph=1))
                g_fn(k_, TR + GT["rel_open"] + GT["rel_slide"], GT["rel_up"], lambda w, f=relL: f(w, ph=2))
                continue
            if "cl" in pl:                                                    # [peel3] 放手從凍結位置出發
                def relf(w, k_=k_, sgn=sgn, ph=0):
                    Pq, Rq_ = pl["cl"]["over"](pl["cl"]["wf"]); p1 = Pq[k_] + offw; n_, u_ = Rq_[:, 2], Rq_[:, 1]
                    A = p1 + sgn * n_ * 0.010; B = A + u_ * 0.030; C = B + [0, 0, 0.08]
                    return ((p1 + (A - p1) * w) if ph == 0 else (A + (B - A) * w) if ph == 1 else (B + (C - B) * w)), Rq_
                g_fn(k_, TR, GT["rel_open"], lambda w, f=relf: f(w, ph=0))
                g_fn(k_, TR + GT["rel_open"], GT["rel_slide"], lambda w, f=relf: f(w, ph=1))
                g_fn(k_, TR + GT["rel_open"] + GT["rel_slide"], GT["rel_up"], lambda w, f=relf: f(w, ph=2))
                continue
            p1 = Pf1[k_] + offw
            g_lin(k_, TR, GT["rel_open"], p1 + sgn * n_e * 0.010)
            g_lin(k_, TR + GT["rel_open"], GT["rel_slide"], p1 + sgn * n_e * 0.010 + u_e * 0.030)
            g_lin(k_, TR + GT["rel_open"] + GT["rel_slide"], GT["rel_up"], p1 + sgn * n_e * 0.010 + u_e * 0.030 + [0, 0, 0.08])
        pl.update(TP0=TP0, TP1=TP1, TR=TR, hinge=(hy, hz), Lcur=Lcur, Lflat=Lflat, Rr=Rr, r0=r0, th0=th0, th1=th1, R2=R2, two=two,
                  zclear=zclear, end_local=(Pf1["up"] + Pf1["lo"]) / 2)
        P("  [%s] 弧線:彎折處(夾點那欄,即時)y=%.1f z=%.1f mm(|flat x|<CX 各欄中位 y=%.1f z=%.1f;題目名義折線 y=%+.1f);材料長度 現在 %.1f / flat %.1f mm → 半徑 %.2f x (%.1f − 7.5) = %.1f mm(夾爪中心起始離彎折處 %.1f mm,前 30%% 角度內漸變)"
          % (sd, hy * 1e3, hz * 1e3, ym * 1e3, zm * 1e3, sg * CY * 1e3, Lcur * 1e3, Lflat * 1e3, a.arc_k, Lmat * 1e3, Rr * 1e3, r0 * 1e3))
        P("  [%s] 第 1 段繞彎折處 %.0f° → %.0f°(指向箱壁外頂角 y=%+.1f z=%.1f);第 2 段 %s;箱外指頭最低點 >= 蓋頂 %.1f + T + 2 = %.1f mm;終點夾爪中心 (%.1f,%.1f,%.1f) mm;%.1fs 後停 %.1fs 再放開"
          % (sd, np.degrees(th0), np.degrees(th1), sg * (IY + 0.0015) * 1e3, Ez * 1e3,
             ("繞箱壁頂角 半徑 %.1fmm 轉到 180°" % (R2 * 1e3)) if two else ("略過(半徑剩 %.1fmm;--arc2 %d)" % (R2 * 1e3, a.arc2)),
             (zclear - T - 0.002) * 1e3, zclear * 1e3, *(pl["end_local"] * 1e3), a.peel_t, GT["peel_hold"]))

    def g_ut_arc(pl, t, offw, Pl):
        """[table] 桌面上掀開:鉸點 = 夾點那欄從折線往外仍貼桌面(z < 桌面 + T + 3mm)的最外頂點;材料長 L = 鉸點 → 夾持頂點(flat 中位);
        抬起 ut_lift_mm → 繞鉸點弧線(半徑 r0 → ut_arc_k*L(前 30%)→ 保持 → 最後 25% 到終點),夾爪同時繞 x 轉 180°;
        終點夾爪中心 = 鉸點往外 ut_end_k*L、z = 桌面 + T;停 peel_hold → 兩指沿 n 張開 10mm → 沿 u 往外抽(指深 + 20mm)→ 抬 80mm。"""
        sd, sg, v = pl["sd"], pl["sg"], pl["v"]; M = GPL.mid(Pl); zg = BOXL["ZFLOOR"]; ax = pl.get("ax", 1)   # [v2] ax = 0:x 片
        if TAPE:                                                              # 剪掉這片的膠帶(錨點)
            _sc = [A["scope"] for A in ANC if A["side"] == sd and st.GetPrimAtPath(A["scope"]).IsValid()]
            for _s in _sc: st.RemovePrim(Sdf.Path(_s))
            P("★ t=%.2f [%s] [table] 夾好 → 移除 %s 片錨點 %d 個(膠帶);其他片仍封著" % (t, sd, sd, len(_sc)))
        if a.v2_h2_free and ax == 0 and XT.get("hold") and "bind" in X and "free" not in X and "rel" not in XH:   # [v2x2] E:手 2 鬆手抬開,片翻完再回來
            _k = G_SEQ.index(sd); _rg = min(TG0 + G_SHEET * (_k + 1), T_X0 + XT["down"] + XT["bind"] + XT["hold"] - V2XG)
            XH.update(rel=t, sd=sd, rg=_rg, hp0=np.array(X["B"], float), j0=dict(X["jaw"]), last=(_k + 1 == len(G_SEQ)))
            P("★ t=%.2f [%s] [v2x2] 手 2 鬆手:張開 0.4 s、抬 %.0f mm(杯轉 dynamic);%.2f 回來重夾%s" % (t, sd, a.v2_h2_lift_mm, _rg, "(取杯那次:指-布 > %.1f mm 才合指)" % a.v2_h2_clear_mm if XH["last"] else ""))
        if ax == 1: col = np.where((GPL.S["ii"] == v % (a.nxy + 1)) & (sg * GF2[:, 1] > CY - 1e-9))[0]
        else: col = np.where((GPL.S["jj"] == v // (a.nxy + 1)) & (sg * GF2[:, 0] > CX - 1e-9))[0]   # [v2] x 片:夾點那一列
        col = col[np.argsort(sg * GF2[col, ax])]
        k = 0
        while k + 1 < len(col) and M[col[k + 1], 2] < zg + T + 0.003: k += 1
        h = int(col[k]); hy = float(M[h, ax]); Bz = zg + T / 2                 # [v2] hy = 鉸點在片軸上的座標(y 片 y、x 片 x)
        if pl.get("att", {}).get("n", 0): gv = np.asarray(pl["att"]["vids"]) % N1
        else:
            gv = np.asarray(pl.get("G", []), int) % N1; gv = gv[GSIDE2[gv] == sd] if len(gv) else gv
            if not len(gv): gv = np.array([v])
        L = abs(float(np.median(GF2[gv, ax])) - float(GF2[h, ax]))
        up_f, lo_f, R0 = pl["up_f"], pl["lo_f"], pl["R0"]
        gc0 = (up_f + lo_f) / 2; ol = {"up": R0.T @ (up_f - gc0), "lo": R0.T @ (lo_f - gc0)}
        KS = ("up",) if a.grasp_attach else ("up", "lo")
        dl = np.array([0.0, 0.0, a.ut_lift_mm / 1e3])
        for k_ in KS: g_lin(k_, t, a.ut_lift_t, pl[k_ + "_f"] + dl + offw, R0)
        TP0 = t + a.ut_lift_t; gs = gc0 + dl
        os_, zs = sg * (gs[ax] - hy), gs[2] - Bz; ph_s = float(np.arctan2(zs, os_)); r_s = float(np.hypot(os_, zs))
        oe, ze = (a.v2_xend_k if (ax == 0 and a.v2_xend_k > 0) else a.ut_end_k) * L, zg + T - Bz   # [v2x2] v2_xend_k
        ph_e = float(np.arctan2(ze, oe)); r_e = float(np.hypot(oe, ze)); Rr = a.ut_arc_k * L
        Rend = np.column_stack([[-sg, 0.0, 0.0], [0.0, sg, 0.0], [0.0, 0.0, -1.0]])   # t,u,n:u 往外(離開包裹)、n 朝下(翻面)
        Rpi = lambda w: rotm([sg, 0.0, 0.0], -np.pi * w)
        if ax == 0:                                                           # [v2] x 片:u = sg x、繞 y 翻
            Rend = np.column_stack([[0.0, sg, 0.0], [sg, 0.0, 0.0], [0.0, 0.0, -1.0]]); Rpi = lambda w: rotm([0.0, sg, 0.0], np.pi * w)
        Cv = _Rot.from_matrix((Rpi(1.0) @ R0).T @ Rend).as_rotvec()
        if np.linalg.norm(Cv) > np.radians(60):
            P("  [%s] [table] ★ 終點姿態修正 %.0f° > 60°,不修正(只繞 x 轉 180°)" % (sd, np.degrees(np.linalg.norm(Cv)))); Cv = np.zeros(3)
        def at(w):
            ph = ph_s + (ph_e - ph_s) * w
            r = (r_s + (Rr - r_s) * min(1.0, w / 0.3)) if w < 0.75 else (Rr + (r_e - Rr) * (w - 0.75) / 0.25)
            gc = np.array(gs, float); gc[ax] = hy + sg * r * np.cos(ph); gc[2] = Bz + r * np.sin(ph)   # [v2] ax
            Rf = Rpi(w) @ R0 @ _Rot.from_rotvec(Cv * w).as_matrix()
            return {k_: gc + Rf @ ol[k_] for k_ in ol}, Rf
        for k_ in KS: g_fn(k_, TP0, a.peel_t, lambda w, k_=k_: (at(w)[0][k_] + offw, at(w)[1]))
        TP1 = TP0 + a.peel_t; TR = TP1 + GT["peel_hold"]
        Pf1, Rf1 = at(1.0); n_e, u_e = Rf1[:, 2], Rf1[:, 1]
        for k_, sgn in ((("up", 1.0),) if a.grasp_attach else (("up", 1.0), ("lo", -1.0))):
            if a.hold_yp and sd == "yp": continue
            p1 = Pf1[k_] + offw; A_ = p1 + sgn * n_e * 0.010; B_ = A_ + u_e * (GFS[1] + 0.020)
            if a.ut_release_up:                                               # [v2x] 張開到 +20 mm;布上那根垂直抬、不往外抽;布下那根(已在桌面下)在桌面下沿 u 出布外再抬
                A_ = p1 + sgn * n_e * 0.020; B_ = A_ + u_e * (GFS[1] + 0.020) if sgn * n_e[2] < 0 else A_
                if a.v2_xrel_slide and (ax == 0 or a.v2_xrel_slide == 2) and sgn * n_e[2] >= 0:   # [v2x2] H:布上那根張開 2 mm → 沿 u 抽出布外 → 抬(2 = yn/yp 也用)
                    A_ = p1 + sgn * n_e * 0.002; B_ = A_ + u_e * (GFS[1] + 0.020)
            g_lin(k_, TR, GT["rel_open"], A_); g_lin(k_, TR + GT["rel_open"], GT["rel_slide"], B_)
            g_lin(k_, TR + GT["rel_open"] + GT["rel_slide"], GT["rel_up"], B_ + [0, 0, 0.08])
        if a.v2_xpress_s > 0 and ax == 0:                                     # [v2x2] G:放手抬開後,"up" 指平放壓在片根部外側 v2_xpress_s 秒再抬
            _t = TR + GT["rel_open"] + GT["rel_slide"] + GT["rel_up"]; _pc = np.array([hy + sg * a.v2_xpress_mm / 1e3, float(pl["p"][1]), zg + T + GFS[2] / 2 - 0.001]) + offw
            _Rp = np.column_stack([[0.0, -sg, 0.0], [sg, 0.0, 0.0], [0.0, 0.0, 1.0]])
            if a.v2_xpress_depth_mm > 0:                                      # 壓指高度在下指那一刻才量(布頂 − depth)
                PRZ = {}
                def _pz(_t=_t, _pc=_pc, PRZ=PRZ, sd=sd):
                    if "z" not in PRZ:
                        if CL["t"] < _t + 1.0 - 1e-6: return float(_pc[2])
                        _Pw = PLATE.pts(); _m = (np.abs(_Pw[:, 0] - _pc[0]) < GFS[1] / 2) & (np.abs(_Pw[:, 1] - _pc[1]) < GFS[0] / 2)
                        _zt = float(_Pw[_m, 2].max()) if _m.any() else float(_pc[2])
                        PRZ["z"] = max(float(_pc[2]), _zt - a.v2_xpress_depth_mm / 1e3 + GFS[2] / 2)
                        P("  [%s] [v2x2] 壓片根部 t=%.2f:足跡內布頂 z %.1f mm(%d 點)→ 指底 z %.1f(桌面 + T − 1 = %.1f)" % (sd, CL["t"], (_zt - offw[2]) * 1e3, int(_m.sum()), (PRZ["z"] - GFS[2] / 2 - offw[2]) * 1e3, (_pc[2] - GFS[2] / 2 - offw[2]) * 1e3))
                    return PRZ["z"]
                _xy = lambda z_, _pc=_pc: np.array([_pc[0], _pc[1], z_])
                g_lin("up", _t, 1.0, _pc + [0, 0, 0.06], _Rp)
                g_fn("up", _t + 1.0, 0.7, lambda w, _pc=_pc: (_xy(_pc[2] + 0.06 + (_pz() - _pc[2] - 0.06) * w), _Rp))
                g_fn("up", _t + 1.7, a.v2_xpress_s, lambda w: (_xy(_pz()), _Rp))
                g_fn("up", _t + 1.7 + a.v2_xpress_s, 0.7, lambda w: (_xy(_pz() + 0.08 * w), _Rp))
            else: g_lin("up", _t, 1.0, _pc + [0, 0, 0.06], _Rp); g_lin("up", _t + 1.0, 0.7, _pc); g_lin("up", _t + 1.7, a.v2_xpress_s, _pc); g_lin("up", _t + 1.7 + a.v2_xpress_s, 0.7, _pc + [0, 0, 0.08])
            pl["press"] = (_t + 1.7, _t + 1.7 + a.v2_xpress_s)
            P("  [%s] [v2x2] 放手後壓片根部:%.2f 起 指 %s mm(箱局部;鉸點往外 %.0f mm、指底 = 桌面 + T − 1 mm)壓 %.1f s(%.2f ~ %.2f)再抬 80 mm"
              % (sd, _t, np.round((_pc - offw) * 1e3, 1), a.v2_xpress_mm, a.v2_xpress_s, *pl["press"]))
        pl.update(TP0=TP0, TP1=TP1, TR=TR, hinge=(hy, Bz), Lcur=L, Lflat=L, Rr=Rr, r0=r_s, th0=ph_s, th1=ph_e, R2=None, two=False, zclear=None,
                  end_local=(Pf1["up"] + Pf1["lo"]) / 2, ut=dict(h=h, hy=hy, Bz=Bz, L=L, flat_h=float(GF2[h, ax]), n_gv=len(gv)))
        P(("  [%s] [table] 桌面鉸點 v%d " + "xy"[ax] + "=%.1f z=%.1f mm(flat " + "xy"[ax] + " %.1f;折線 %+.1f)| 材料長 鉸點→夾持頂點(%d 點 flat 中位)%.1f mm | 抬 %.0f mm(%.1f s)→ 弧 %.0f° → %.0f°、半徑 %.1f → %.1f(%.2f L)→ %.1f mm、夾爪繞 x 轉 180°(%.1f s)| 終點夾爪中心 (%.1f,%.1f,%.1f) mm;停 %.1f s 放手 @%.2f")
          % (sd, h, hy * 1e3, Bz * 1e3, GF2[h, ax] * 1e3, sg * pl.get("C", CY) * 1e3, len(gv), L * 1e3, a.ut_lift_mm, a.ut_lift_t, np.degrees(ph_s), np.degrees(ph_e),
             r_s * 1e3, Rr * 1e3, a.ut_arc_k, r_e * 1e3, a.peel_t, *(pl["end_local"] * 1e3), GT["peel_hold"], TR))

    def ut_stat(pl, Pw=None):
        """[table] 翻片角 = 片外段方向(flat 離折線 50~70% 那帶 → 85~100% 那帶的質心連線)在 (往外, z) 平面的角度:0° 攤平往外、90° 直立、180° 蓋回;
        質心 = 主片(|flat x| < CX)中面質心相對鉸線 (往外 o, 高 z) mm;越線 = 規劃時在折線內側的頂點越過折線 %"""
        Pl = (PLATE.pts() if Pw is None else Pw) - g_offw(); sd, sg = pl["sd"], pl["sg"]; M = GPL.mid(Pl)
        ax = pl.get("ax", 1); Cs = pl.get("C", CY); Co = CX if ax == 1 else CY   # [v2] x 片沿 x 軸
        hy, Bz = pl["ut"]["hy"], pl["ut"]["Bz"]; s = sg * GF2[:, ax] - Cs; Ls = WA[ax] / 2 + sg * SC[ax] - Cs
        main = (GSIDE2[:N1] == sd) & (np.abs(GF2[:, 1 - ax]) < Co)
        bm = main & (s >= 0.50 * Ls) & (s <= 0.70 * Ls); bt = main & (s >= 0.85 * Ls)
        o = sg * (M[:, ax] - hy); z = M[:, 2] - Bz
        ang = float(np.degrees(np.arctan2(z[bt].mean() - z[bm].mean(), o[bt].mean() - o[bm].mean())))
        if ang < -90: ang += 360.0
        oc, zc = float(o[main].mean()), float(z[main].mean())
        return dict(ang=ang, angc=float(np.degrees(np.arctan2(zc, oc))), oc=oc * 1e3, zc=zc * 1e3,
                    cross=float((sg * Pl[pl["TOPS"], ax] > Cs).mean()) * 100 if len(pl["TOPS"]) else float("nan"),
                    out=float((o[main] > 0).mean()) * 100)

    def g_metrics(pl, t, Pw=None):
        offw = g_offw()
        if Pw is None: Pw = PLATE.pts()
        Pl = Pw - offw; sd, sg = pl["sd"], pl["sg"]
        r = dict(t=t)
        gc, Rg = g_frame_now(t)
        r["up"] = (g_pose("up", t)[0] - offw) * 1e3; r["lo"] = (g_pose("lo", t)[0] - offw) * 1e3
        Gn, L_ = g_between(Pw, t); r["ngrip"] = len(Gn)
        att = pl.get("att")
        if att is not None:
            r["ngrip"] = att["n"]
        if att is not None and att["n"] and pl.get("TP0") is not None and t <= pl["TR"] + 1e-6:
            pu_, Ru_ = g_pose("up", t)
            dd = np.linalg.norm((Pw[att["vids"]] - pu_) @ Ru_ - att["loc0"], axis=1)
            r["slip"] = float(np.median(dd)) * 1e3; r["slip_max"] = float(dd.max()) * 1e3
            pl["slip"].append((t, r["slip"], r["slip_max"]))
        elif "G" in pl and len(pl["G"]) and pl.get("TP0") is not None and t <= pl["TR"] + 1e-6:
            dd = np.linalg.norm(L_[pl["G"]] - pl["rel0"], axis=1)
            r["slip"] = float(np.median(dd)) * 1e3; r["slip_max"] = float(dd.max()) * 1e3
            pl["slip"].append((t, r["slip"], r["slip_max"]))
        else:
            r["slip"] = r["slip_max"] = float("nan")
        ax = pl.get("ax", 1); Cs = pl.get("C", CY)                           # [v2] x 片沿 x 軸
        r["cross"] = float((sg * Pl[pl["TOPS"], ax] > Cs).mean()) if len(pl["TOPS"]) else float("nan")
        msd = GSIDE2 == sd
        r["cross_all"] = float((sg * Pl[msd, ax] > Cs).mean())
        r["cross_h"] = float((sg * Pl[pl["TOPS"], ax] > sg * pl["hinge"][0]).mean()) if ("hinge" in pl and len(pl["TOPS"])) else float("nan")
        d_ = np.linalg.norm(Pw - pl["P0"], axis=1)
        o_ = pl["others"]; r["oth_n10"] = int((d_[o_] > 0.010).sum()); r["oth_pct"] = 100.0 * r["oth_n10"] / max(1, int(o_.sum()))
        r["oth_max"] = float(d_[o_].max()) * 1e3
        r["oth_side"] = {s_: int(((GSIDE2 == s_) & (d_ > 0.010)).sum()) for s_ in pl["osides"]}
        r["mug_d"] = float(np.linalg.norm(mug_world()[0] - pl["mug0"])) * 1e3
        if a.attach_proxy:                                                    # [drag] 代理落後上指目標 mm
            r["lag"] = float(np.linalg.norm(g_proxy_pose()[0] - g_pose("up", t)[0])) * 1e3
        if pl.get("hold") is not None:                                        # [drag] 追加欄位
            hv = pl["hold"]["vids"]; of_ = o_.copy(); of_[hv] = False
            r["hold_n"] = int(pl["hold"]["n"]); r["hold_on"] = bool(pl["hold"]["on"])
            r["oth_pct_free"] = 100.0 * int((d_[of_] > 0.010).sum()) / max(1, int(of_.sum()))
            r["hold_d"] = float(np.linalg.norm(Pw[hv] - pl["hold"]["P0"], axis=1).max()) * 1e3 if len(hv) else float("nan")
        return r

    def g_line(pl, r, rm):
        P("  G[%s] t=%6.2f %-26s 上指 (%6.1f,%6.1f,%6.1f) 下指 (%6.1f,%6.1f,%6.1f) | 夾到 %2d | 滑動 中位 %s 最大 %s | %s 越過折線 %3.0f%%(實測彎折 %3.0f%%;整片 %3.0f%%)| 他片 >10mm %4d(%.1f%%)最大 %5.1f | 杯位移 %.1f | 自穿 %d 穿杯 %d 反轉 %d"
          % (pl["sd"], r["t"], phase(r["t"]), *r["up"], *r["lo"], r["ngrip"], "%.1f" % r["slip"] if np.isfinite(r["slip"]) else "-",
             "%.1f" % r["slip_max"] if np.isfinite(r["slip_max"]) else "-", pl["sd"], 100 * r["cross"], 100 * r["cross_h"], 100 * r["cross_all"],
             r["oth_n10"], r["oth_pct"], r["oth_max"], r["mug_d"], rm["pen"], rm["inmug"], rm["inv"])
          + (" | 壓住 %d 他片(扣壓住) %.1f%% 釘點位移 %.1f" % (r["hold_n"], r["oth_pct_free"], r["hold_d"]) if "hold_n" in r else "")
          + (" | 代理落後 %.1f" % r["lag"] if "lag" in r else ""))
        GS["rows"].append(dict(sd=pl["sd"], **{k_: (v_.tolist() if isinstance(v_, np.ndarray) else v_) for k_, v_ in r.items()},
                               pen=rm["pen"], inmug=rm["inmug"], inv=rm["inv"]))

    def h2_stat(pl, Pw=None):                                                 # [hand2] yn 越線 / 質心 y / 壁外比例
        Pl = (PLATE.pts() if Pw is None else Pw) - g_offw(); sd, sg = pl["sd"], pl["sg"]; m = GSIDE2 == sd
        ax = pl.get("ax", 1); Cs = pl.get("C", CY); Iw = IX if ax == 0 else IY  # [v2] x 片沿 x 軸
        return (float((sg * Pl[pl["TOPS"], ax] > Cs).mean()) * 100 if len(pl["TOPS"]) else float("nan"),
                float(Pl[m, ax].mean()) * 1e3, float((sg * Pl[m, ax] > Iw + 0.0015).mean()) * 100)
    def h2_events(pl, t):
        if a.hand2_keep and pl["sd"] != "yn": return                          # [extract] 第二隻手只拿 yn、不移走
        h = pl.setdefault("h2", {}); sd, sg = pl["sd"], pl["sg"]; TR = pl["TR"]; I3 = np.eye(3)
        TA = TR - a.hand2_lead_s; TH = TR + a.hand2_hold_s; TL = TH + 1.0
        if "pos" not in h and t >= TA - (0.5 if a.hand2 == "press" else 1.4 if a.hand2 == "jaw" else 0.0) - 1e-6:   # [jaw2] jaw:下降 0.8 + 合指 0.6
            offw, Pw, Pl, _, _ = g_state(); m = GSIDE2 == sd; gx = float(((g_pose("up", t)[0] - offw))[0])
            ltop = lid_top_local(sd); e0 = IY + 0.0015
            c = m & (sg * Pl[:, 1] >= e0 + 0.010) & (sg * Pl[:, 1] <= e0 + 0.040) & (Pl[:, 2] < ltop + 0.020)
            best = (-1, 0.0)
            for xc in np.arange(-0.100, 0.1001, 0.005):
                if abs(xc - gx) < 0.033: continue
                n_ = int((c & (np.abs(Pl[:, 0] - xc) < 0.020)).sum())
                if n_ > best[0] or (n_ == best[0] and abs(xc - gx) < abs(best[1] - gx)): best = (n_, xc)
            xc = best[1]; yc = sg * (e0 + 0.025); zb = ltop + T + 0.001
            fp = m & (np.abs(Pl[:, 0] - xc) < 0.020) & (np.abs(Pl[:, 1] - yc) < 0.015)
            ztop = float(Pl[fp, 2].max()) if fp.any() else zb
            zp = zb + H2S[2] / 2; za = max(zp, ztop + H2S[2] / 2 + 0.010) + 0.005
            h.update(pos=np.array([xc, yc, zp]), n_cand=best[0], gx=gx)
            if a.hand2 == "press":
                g_fn("h2", t, 1e-3, lambda w, p_=np.array([xc, yc, za]) + offw: (p_, I3))
                g_lin("h2", t + 0.01, max(0.05, TA - t - 0.01), np.array([xc, yc, zp]) + offw, I3)
                g_lin("h2", TH, 1.0, np.array([xc, yc, zp + 0.060]) + offw, I3)
                g_fn("h2", TL + 0.01, 1e-3, lambda w: (GPARK["h2"], I3))
                P("★ t=%.2f [%s] [hand2] press 壓板中心 (%.1f,%.1f) mm(夾爪 x %.1f;壁外 10~40mm 候選 %d 點);從 z %.1f 下壓到 %.1f(底 = 蓋頂 %.1f + T + 1 = %.1f)@%.2f;放手 %.2f;抬起 %.2f~%.2f"
                  % (t, sd, xc * 1e3, yc * 1e3, gx * 1e3, best[0], za * 1e3, zp * 1e3, ltop * 1e3, zb * 1e3, TA, TR, TH, TL))
            elif a.hand2 == "jaw":                                            # [jaw2] 兩指從上方 80mm 張開(指間 40)下降 → TA 前 0.6s 沿 x 合到指間 6mm → TA 綁
                zf = ztop + H2F[2] / 2 - 0.001
                if a.jaw_collide:                                             # [jaw3] 指尖停在兩指掃過範圍的布頂 +0.5mm(C1f:壓 1mm 再合 → 布被拖皺,yn 邊長比 5.3 守衛放手)
                    _fz = m & (np.abs(Pl[:, 0] - xc) < 0.030) & (np.abs(Pl[:, 1] - yc) < H2F[1] / 2 + 0.002)
                    zf = (float(Pl[_fz, 2].max()) if _fz.any() else ztop) + H2F[2] / 2 + 0.0005
                oo = 0.020 + H2F[0] / 2; oc = H2GAP / 2 + H2F[0] / 2; pw_ = np.array([xc, yc, ztop]) + offw
                g_fn("h2", t, 1e-3, lambda w, p_=pw_: (p_, I3))               # 綁定錨(不碰撞、不顯示)先就位
                for k_, s_ in (("h2a", -1.0), ("h2b", 1.0)):
                    g_fn(k_, t, 1e-3, lambda w, p_=np.array([xc + s_ * oo, yc, zf + 0.08]) + offw: (p_, I3))
                    g_lin(k_, t + 0.01, 0.8, np.array([xc + s_ * oo, yc, zf]) + offw, I3)
                    g_lin(k_, TA - 0.6, 0.6, np.array([xc + s_ * oc, yc, zf]) + offw, I3)
                    if not a.hand2_keep:
                        g_lin(k_, TH, 0.3, np.array([xc + s_ * oo, yc, zf]) + offw, I3); g_lin(k_, TH + 0.3, 0.7, np.array([xc + s_ * oo, yc, zf + 0.06]) + offw, I3)
                        g_fn(k_, TL + 0.02, 1e-3, lambda w, k_=k_: (GPARK[k_], I3))
                if not a.hand2_keep: g_lin("h2", TH + 0.01, 1.0, pw_ + [0, 0, 0.060], I3); g_fn("h2", TL + 0.02, 1e-3, lambda w: (GPARK["h2"], I3))
                h.update(att_t=TA, pw=pw_, jaw=dict(xc=xc, yc=yc, ltop=ltop))
                P("★ t=%.2f [%s] [hand2] jaw 夾爪中心 (%.1f,%.1f) mm(夾爪 x %.1f;候選 %d 點);指尖 z %.1f(布頂 %.1f);下降 %.2f~%.2f 合指 %.2f~%.2f(指間 %.0f → %.0f mm)綁 @%.2f;放手 %.2f"
                  % (t, sd, xc * 1e3, yc * 1e3, gx * 1e3, best[0], (zf - H2F[2] / 2) * 1e3, ztop * 1e3, t + 0.01, t + 0.81, TA - 0.6, TA, 2 * (oo - H2F[0] / 2) * 1e3, H2GAP * 1e3, TA, TR))
            else:
                hv = np.where(m & (np.abs(Pl[:, 0] - xc) < 0.020 + a.hand2_pad_mm / 1e3) & (np.abs(Pl[:, 1] - yc) < 0.015 + a.hand2_pad_mm / 1e3)
                              & (Pl[:, 2] < ltop + 0.025))[0]
                zc = float(Pl[hv, 2].mean()) if len(hv) else zp; pw_ = np.array([xc, yc, zc]) + offw
                g_fn("h2", t, 1e-3, lambda w, p_=pw_: (p_, I3))
                if not a.hand2_keep:                                          # [extract] keep = 不抬不停放
                    g_lin("h2", TH + 0.01, 1.0, pw_ + [0, 0, 0.060], I3)
                    g_fn("h2", TL + 0.02, 1e-3, lambda w: (GPARK["h2"], I3))
                h["att_t"] = t + 0.02; h["hv"] = hv; h["pw"] = pw_
                P("★ t=%.2f [%s] [hand2] attach 方塊中心 (%.1f,%.1f,%.1f) mm(夾爪 x %.1f;候選 %d 點);綁 %d 點(pad %.0f mm,z %.0f~%.0f);放手 %.2f;解綁 %.2f 抬起 ~%.2f"
                  % (t, sd, xc * 1e3, yc * 1e3, zc * 1e3, gx * 1e3, best[0], len(hv), a.hand2_pad_mm,
                     Pl[hv, 2].min() * 1e3 if len(hv) else np.nan, Pl[hv, 2].max() * 1e3 if len(hv) else np.nan, TR, TH, TL))
        if a.hand2 in ("attach", "jaw") and "att_on" not in h and "att_t" in h and t >= h["att_t"]:
            if "jaw" in h:                                                    # [jaw2] 合指完成才挑點:指間 x ±(6/2 + pad)、指寬 y ±(20/2 + pad)
                j_ = h["jaw"]; _Pl = PLATE.pts() - g_offw(); _pd = a.hand2_pad_mm / 1e3
                h["hv"] = np.where((GSIDE2 == sd) & (np.abs(_Pl[:, 0] - j_["xc"]) < H2GAP / 2 + _pd) & (np.abs(_Pl[:, 1] - j_["yc"]) < H2F[1] / 2 + _pd) & (_Pl[:, 2] < j_["ltop"] + 0.025))[0]
                P("★ t=%.2f [%s] [hand2] jaw 合指完成 → 綁 %d 點(指間 ±%.0f × ±%.0f mm,z %.0f~%.0f)"
                  % (t, sd, len(h["hv"]), (H2GAP / 2 + _pd) * 1e3, (H2F[1] / 2 + _pd) * 1e3, _Pl[h["hv"], 2].min() * 1e3 if len(h["hv"]) else np.nan, _Pl[h["hv"], 2].max() * 1e3 if len(h["hv"]) else np.nan))
            h["att_on"] = bool(len(h["hv"]))
            if len(h["hv"]):
                Pw = PLATE.pts(); VC.attach_vtx(st, "/World/gh2_%s" % sd, "/World/plate", "/World/plate", GPATH["h2"], h["hv"], Pw[h["hv"]] - h["pw"], P=P)
        if h.get("att_on") and t >= TH - 1e-6 and not a.hand2_keep:
            st.RemovePrim(Sdf.Path("/World/gh2_%s" % sd)); h["att_on"] = False; P("★ t=%.2f [%s] [hand2] 解綁 %d 點" % (t, sd, len(h["hv"])))
        for nm_, tt_ in (("pre", TR - 0.02), ("rel+0.5", TR + 0.5), ("rel+2", TR + 2.0), ("lift+2", TL + 2.0)):
            if "pos" in h and nm_ not in h and t >= tt_:
                cr, cy, wo = h2_stat(pl); h[nm_] = (cr, cy, wo); extra = ""
                if nm_ == "pre" and a.hand2 == "press":
                    Pl = PLATE.pts() - g_offw(); p_ = h["pos"]; mm = GSIDE2 == sd
                    nc = int((mm & (np.abs(Pl[:, 0] - p_[0]) < 0.022) & (np.abs(Pl[:, 1] - p_[1]) < 0.017) & (Pl[:, 2] > p_[2] - H2S[2] / 2 - T - 0.003) & (Pl[:, 2] < p_[2])).sum())
                    h["contact"] = nc; extra = " | 壓板下接觸 %d 點" % nc
                if nm_ == "pre" and a.hand2 in ("attach", "jaw"): extra = " | 綁 %d 點" % len(h["hv"])
                P("★ t=%.2f [%s] [hand2] %s:%s 越線 %.0f%% | 質心 y %.1f mm | 壁外 %.0f%%%s" % (t, sd, nm_, sd, cr, cy, wo, extra))
        if "lift+2" in h and "sum" not in h:
            h["sum"] = 1
            P("[hand2] SUMMARY %s mode=%s pos=(%.1f,%.1f,%.1f) n=%d 越線 pre/0.5/2/lift+2 = %.0f/%.0f/%.0f/%.0f%% 質心y = %.1f/%.1f/%.1f/%.1f 壁外 = %.0f/%.0f/%.0f/%.0f%%"
              % (sd, a.hand2, *(h["pos"] * 1e3), h.get("contact", len(h.get("hv", []))), *[h[k][0] for k in ("pre", "rel+0.5", "rel+2", "lift+2")],
                 *[h[k][1] for k in ("pre", "rel+0.5", "rel+2", "lift+2")], *[h[k][2] for k in ("pre", "rel+0.5", "rel+2", "lift+2")]))

    def v2_xcut(sd, t):                                                       # [v2] x 片開始:拆該片膠帶(錨點),記下折線內側頂點(越線基準)
        offw, Pw, Pl, _, _ = g_state(); sg = -1.0 if sd == "xn" else 1.0
        GS.setdefault("xtops", {})[sd] = np.where((GSIDE2 == sd) & (sg * Pl[:, 0] < CX - 0.003))[0]
        n_ = 0
        if TAPE:
            for A in ANC:
                if A["side"] == sd and st.GetPrimAtPath(A["scope"]).IsValid(): st.RemovePrim(Sdf.Path(A["scope"])); n_ += 1
        r_, _, _ = measure(t, full=True)
        P("\n★ t=%.2f [%s] [v2] 開始掀 %s:先拆膠帶(移除錨點 %d 個),等 %.1f s 再規劃;折線內側頂點 %d;杯頂覆蓋 %.0f%%"
          % (t, sd, sd, n_, a.v2_xcut_s, len(GS["xtops"][sd]), 100 * (r_.get("lay") or {}).get("cov", float("nan"))))
    def v2_skip_log(pl, t, S0o):                                              # [v2] x 片拆膠帶後自己攤開:+10 s、片結束時量測
        for nm_, tt_ in (("cut+10", S0o + 10.0), ("released", S0o + G_SHEET - 0.05)):
            if nm_ not in pl["ev"] and t >= tt_:
                rm, Pw, _ = measure(t, full=True); r = g_metrics(pl, t, Pw); cov = (rm.get("lay") or {}).get("cov", float("nan"))
                pl["ev"][nm_] = dict(t=t, cross=r["cross"], cov=cov, mug=r["mug_d"], inmug=rm["inmug"], oth=r["oth_pct"])
                P(("★ t=%.2f [%s] [v2] " + (pl.get("xlabel") or ("斜靠沒夾" if pl.get("lean") else "自己攤開")) + " %s:越線 %.0f%% | 他片 >10mm %.1f%% | 杯位移 %.1f mm | 穿杯 %d | 自穿 %d | 杯頂覆蓋 %.0f%%")
                  % (t, pl["sd"], nm_, 100 * r["cross"], r["oth_pct"], r["mug_d"], rm["inmug"], rm["pen"], 100 * cov))
    def g_events(t):
        """每個物理步呼叫:到點就做規劃 / 量測。"""
        k_ = int((t - TG0) // G_SHEET)
        if k_ >= len(G_SEQ): return
        S0 = TG0 + k_ * G_SHEET; S0o = S0
        if G_SEQ[k_][0] == "x":                                               # [v2] x 片:先拆膠帶、等 v2_xcut_s 秒才規劃(--v2_hold_cup:手 2 先夾杯 V2XG 秒)
            if t < S0 + V2XG - 1e-9: return
            if a.v2_xmode == "tapegrip": S0 = S0 + V2XG                       # [v2x] D:膠帶不先拆(夾好才拆,同 yn/yp)
            else:
                if GS.get("xcut", -1) < k_: GS["xcut"] = k_; v2_xcut(G_SEQ[k_], t)
                S0 = S0 + V2XG + a.v2_xcut_s
            if t < S0 - 1e-9: return
        if GS["k"] < k_:
            GS["k"] = k_; g_plan(G_SEQ[k_], S0)
            if G_SEQ[k_][0] == "x" and (k_ == 0 or G_SEQ[k_ - 1][0] != "x"):  # [v2] x 片從 −y 看 x-z 平面
                G.look(cam, list(g_offw() + np.array([0.10, -0.80, 0.42])), list(g_offw() + np.array([0.0, 0.0, 0.05])))
            if k_ == 0:
                EYE = g_offw() + np.array([0.62, -0.06, 0.50]); TGT = g_offw() + np.array([0.0, -0.06, 0.07])
                if UTT: EYE = g_offw() + np.array([0.78, 0.0, 0.40]); TGT = g_offw() + np.array([0.0, 0.0, 0.05])   # [table] 從 +x 看 y-z 平面(兩片都看得到)
                cam.set_focal_length(a.gcam_focal)
                try: cam.set_clipping_range(0.01, 100.0)
                except Exception: pass
                G.look(cam, list(EYE), list(TGT)); CAMS["glook"] = (list(EYE), list(TGT))   # [v2x] 存檔(--at xflaps)要記相機
        pl = GS["plans"][k_]; ev = pl["ev"]
        if pl.get("skip") or pl.get("xm"): return v2_skip_log(pl, t, S0o)     # [v2] x 片自己攤開:只量測([v2x] 撥開 / 外側夾:路徑已排好,放手後量測走 plastic_watch)
        _r = t - S0
        if a.pick_mode == "jaw" and 1.5 <= _r <= G_TPICK + 0.05 and int(round(_r / a.dt)) % int(round(0.1 / a.dt)) == 0:
            pj, Rj = g_pose("lo", t); Lj = (PLATE.pts() - pj) @ Rj
            fp = (np.abs(Lj[:, 0]) < GFS[0] / 2) & (np.abs(Lj[:, 1]) < GFS[1] / 2)
            ontop = fp & (Lj[:, 2] >= GFS[2] / 2) & (Lj[:, 2] < GFS[2] / 2 + 0.008)
            inside = fp & (np.abs(Lj[:, 2]) < GFS[2] / 2)
            below = fp & (Lj[:, 2] <= -GFS[2] / 2) & (Lj[:, 2] > -GFS[2] / 2 - 0.008)
            P("    pick t=%.2f 下指足跡內:頂面上 0~8mm %d 點 / 穿進指內 %d 點 / 底面下 0~8mm %d 點;角 v%d z=%.1f"
              % (t, int(ontop.sum()), int(inside.sum()), int(below.sum()), pl["v"], (GPL.mid(PLATE.pts())[pl["v"], 2] - g_offw()[2]) * 1e3))
        if "ins" not in ev and t >= S0 + GT["rod_above"] + GT["rod_down"] + GT["rod_in"] - 1e-6:
            ev["ins"] = dict(t=t); SNAP["g_%s_ins" % pl["sd"]] = (PLATE.pts().copy(), mug_world()[2].copy(), dict(t=t))
        if "pick" not in ev and t >= S0 + G_TPICK - 1e-6:
            g_after_pick(pl, t)
        if "grip" not in ev and t >= pl.get("t_grip", S0 + G_TGRIP) - 1e-6:
            g_grip_and_arc(pl, t)
        if a.hand2 != "off" and "TR" in pl: h2_events(pl, t)                   # [hand2]
        if pl.get("att", {}).get("on") and t >= pl["TR"] - 1e-6 and not (a.hold_yp and pl["sd"] == "yp"):
            st.RemovePrim(Sdf.Path(pl["att"]["scope"])); pl["att"]["on"] = False
            if pl["att"].get("lo"): st.RemovePrim(Sdf.Path(pl["att"]["scope"] + "_lo"))
            P("★ t=%.2f [%s] 張開:RemovePrim %s(釋放 %d 頂點)" % (t, pl["sd"], pl["att"]["scope"], pl["att"]["n"]))
        if pl.get("hold", {}).get("on") and t >= pl["TR"] + a.hold_rel_s - 1e-6:   # [drag] 放開他片
            st.RemovePrim(Sdf.Path(pl["hold"]["scope"])); pl["hold"]["on"] = False; pl["hold"]["t_rel"] = t
            P("★ t=%.2f [%s] 放開他片:RemovePrim %s(%d 點)" % (t, pl["sd"], pl["hold"]["scope"], pl["hold"]["n"]))
        for nm_, tt_ in (("peel_1_3", pl.get("TP0", 1e9) + a.peel_t / 3), ("peel_2_3", pl.get("TP0", 1e9) + 2 * a.peel_t / 3),
                         ("peeled", pl.get("TP1", 1e9)), ("held", pl.get("TR", 1e9) - 1e-3), ("released", S0o + G_SHEET - 0.05)):
            if nm_ not in ev and t >= tt_:
                rm, Pw, _ = measure(t, full=nm_ in ("held", "released"))
                r = g_metrics(pl, t, Pw); r["rm"] = dict(pen=rm["pen"], inmug=rm["inmug"], inv=rm["inv"],
                                                          cov=(rm.get("lay") or {}).get("cov", float("nan")))
                ev[nm_] = r
                SNAP["g_%s_%s" % (pl["sd"], nm_)] = (Pw.copy(), mug_world()[2].copy(), rm)
                P("\n★ t=%.2f [%s] %s" % (t, pl["sd"], nm_)); g_line(pl, r, rm)
                if nm_ in ("held", "released"):
                    P("  杯頂俯視覆蓋 %.0f%% → 露出 %.0f%%(開始時 %.0f%%)" % (100 * r["rm"]["cov"], 100 * (1 - r["rm"]["cov"]), 100 * (1 - pl["cov0"])))

# ── [extract] 第三隻手取杯 ──
X = dict(st="wait")
XH = {}                                                                        # [v2x2] --v2_h2_free:手 2 鬆手 / 重夾狀態
if a.extract:
    def h3_boxd(Pw, c, hs):                                                   # [v2x2] 布頂點到軸對齊盒(中心 c、半邊 hs)的最小距離(負 = 在盒內)
        q_ = np.abs(Pw - c) - hs; return float(np.where((q_ < 0).all(1), q_.max(1), np.linalg.norm(np.maximum(q_, 0), axis=1)).min())
    def h3_regrip_plan(t, last):
        """[v2x2] 重夾:用當下杯姿態找夾位(指頂高 杯頂 + dz、指 x 偏 dx),兩指從張開 25 mm 到合(停在杯 + 1 mm)的掃掠盒與布最小距離 > clear 才用;都不行 → 舊規則(預設夾位、杯端外 10 mm 有布 → 停 T + 1 mm)"""
        mp, Rq, MW = mug_world(); Pw = PLATE.pts(); ztp = float(MW[:, 2].max()); xb = float(MW[MW[:, 2] > ztp - 0.005, 0].mean()); clr = a.v2_h2_clear_mm / 1e3
        res = []
        for dzs in (0.0, 0.010, 0.020, 0.030):
            for dxs in (0.0, -0.010, 0.010, -0.020, 0.020):
                xb_, zt_ = xb + dxs, ztp + dzs
                bd = (np.abs(MW[:, 0] - xb_) < H3F[0] / 2) & (MW[:, 2] > zt_ - H3F[2]) & (MW[:, 2] < zt_)
                if bd.sum() < 10: continue
                y0, y1 = float(MW[bd, 1].min()), float(MW[bd, 1].max()); zc = zt_ - H3F[2] / 2
                ca_ = np.array([xb_, y0 - H3F[1] / 2 - 0.001 - 0.0125, zc]); cb_ = np.array([xb_, y1 + H3F[1] / 2 + 0.001 + 0.0125, zc])   # 掃掠盒中心(合位 ~ 張開 25 mm)
                hs_ = np.array([H3F[0], H3F[1] + 0.025, H3F[2]]) / 2
                da, db = h3_boxd(Pw, ca_, hs_), h3_boxd(Pw, cb_, hs_)
                res.append(dict(dz=dzs, dx=dxs, y0=y0, y1=y1, xb=xb_, zt=zt_, da=da, db=db, ok=min(da, db) > clr))
        ok = [r for r in res if r["ok"]]; pick = ok[0] if ok else res[0]
        ca = cb = 0.001
        if not ok:                                                            # 舊規則(jaw3)
            _bb = (np.abs(Pw[:, 0] - xb) < H3F[0] / 2 + 0.005) & (Pw[:, 2] > ztp - H3F[2]) & (Pw[:, 2] < ztp + 0.010)
            ca = T + 0.001 if (_bb & (Pw[:, 1] > pick["y0"] - 0.010) & (Pw[:, 1] < pick["y0"] + 0.002)).any() else 0.001
            cb = T + 0.001 if (_bb & (Pw[:, 1] < pick["y1"] + 0.010) & (Pw[:, 1] > pick["y1"] - 0.002)).any() else 0.001
        hz = pick["zt"] - mp[2] + H3S[2] / 2; B1 = mp + [0, 0, hz]
        j1 = dict(dx=pick["xb"] - B1[0], dz=pick["zt"] - H3F[2] / 2 - B1[2], ya=pick["y0"] - B1[1] - H3F[1] / 2 - ca, yb=pick["y1"] - B1[1] + H3F[1] / 2 + cb)
        P("★ t=%.2f [v2x2] 手 2 重夾規劃%s:杯心 (%.1f,%.1f,%.1f) mm(鬆手時 %s)位移 %.1f mm;候選 %d 個、無布 %d 個 → 用 指頂 杯頂%+.0f mm、x 偏 %+.0f mm(掃掠盒-布 −y %.1f / +y %.1f mm)%s"
          % (t, "(取杯)" if last else "", *(mp * 1e3), np.round((XH["hp0"] - [0, 0, X["hz"]]) * 1e3, 1), np.linalg.norm(mp - (XH["hp0"] - [0, 0, X["hz"]])) * 1e3,
             len(res), len(ok), pick["dz"] * 1e3, pick["dx"] * 1e3, pick["da"] * 1e3, pick["db"] * 1e3, "" if ok else ";★ 沒有無布夾位 → 舊規則,停點 −y %.1f / +y %.1f mm" % (ca * 1e3, cb * 1e3)))
        return dict(B1=B1, j1=j1, hz=hz, MW=MW, ok=bool(ok), pick=pick)
    def h2free(t):
        """[v2x2] 回傳 (手心, 張開量 w, 指偏移 j) 或 None(照舊)。段:鬆手 rel → 張開 0.4 → 抬 1.0 → 等 → rg 平移到新夾位上方 0.5 → 降 1.0 → 合 0.8 → 杯 kinematic"""
        if "rel" not in XH or t < XH["rel"]: return None
        up = np.array([0, 0, a.v2_h2_lift_mm / 1e3]); te = t - XH["rel"]
        if "dyn" not in XH:
            kin.Set(False); XH["dyn"] = t; XH["open"] = True; _m3 = mug_world(); XH["mp_rel"] = _m3[0]; XH["zmin_rel"] = float(_m3[2][:, 2].min())
        if t < XH["rg"]: return XH["hp0"] + up * ss((te - 0.4) / 1.0), ss(te / 0.4), XH["j0"]
        if "plan" not in XH: XH["plan"] = h3_regrip_plan(t, XH["last"])
        pn = XH["plan"]; tr = t - XH["rg"]; B1, j0, j1 = pn["B1"], XH["j0"], pn["j1"]
        if tr < 0.5:
            w = ss(tr / 0.5); return XH["hp0"] + up + (B1 - XH["hp0"]) * w, 1.0, {k_: j0[k_] + (j1[k_] - j0[k_]) * w for k_ in j0}
        if tr < 1.5: return B1 + up * (1.0 - ss((tr - 0.5) / 1.0)), 1.0, j1
        if XH.get("open"):                                                    # 合指前:指(合位 ~ 張開掃掠)與布的最小距離
            XH["open"] = False; Pw = PLATE.pts(); mp, Rq, MW = mug_world(); hs_ = np.array([H3F[0], H3F[1] + 0.025, H3F[2]]) / 2
            da = h3_boxd(Pw, B1 + [j1["dx"], j1["ya"] - 0.0125, j1["dz"]], hs_); db = h3_boxd(Pw, B1 + [j1["dx"], j1["yb"] + 0.0125, j1["dz"]], hs_)
            XH.setdefault("chk", []).append((XH["sd"], da * 1e3, db * 1e3)); XH["regrips"] = XH.get("regrips", 0) + 1
            P("★ t=%.2f [v2x2] 合指前 指-布最小距離(張開→合 掃掠盒)−y %.1f / +y %.1f mm(判準 > %.1f)%s;杯從鬆手時位移 %.1f mm"
              % (t, da * 1e3, db * 1e3, a.v2_h2_clear_mm, " OK" if min(da, db) * 1e3 > a.v2_h2_clear_mm else " ★ 不合格", np.linalg.norm(mp - XH["mp_rel"]) * 1e3))
        if tr < 2.3 - 1e-6: return B1, 1.0 - ss((tr - 1.5) / 0.8), j1
        q_ = np.array(mugx.get_world_pose()[1], float); mp, Rq, MW = mug_world()   # 合好:杯轉 kinematic、取杯路徑跟著新夾位平移
        dB = B1 - X["B"]; X["E"] = X["E"] + dB - [0, 0, float(MW[:, 2].min()) - XH["zmin_rel"]]   # 落點:杯底仍放在同一高度
        X["C"] = X["C"] + dB; X["D"] = X["D"] + dB; X["A"] = X["A"] + dB; X["B"] = B1; X["hz"] = pn["hz"]; X["jaw"] = dict(j1); X["q0"] = q_
        kin.Set(True)
        P("★ t=%.2f [v2x2] 手 2 重夾好 → 杯 kinematic;杯心 (%.1f,%.1f,%.1f) mm,鬆手期間位移 %.1f mm" % (t, *(mp * 1e3), np.linalg.norm(mp - XH["mp_rel"]) * 1e3))
        XH.setdefault("disp", []).append((XH["sd"], np.linalg.norm(mp - XH["mp_rel"]) * 1e3))
        for k_ in ("rel", "sd", "rg", "hp0", "j0", "last", "dyn", "open", "mp_rel", "zmin_rel", "plan"): XH.pop(k_, None)
        return None
    def x_hand(r_):
        """取杯手中心(世界)。段:A 上方 → B 杯頂 → 綁 → C 抬 → D 移 → E 放 → 手抬開"""
        if "path" in X:                                                      # [extract2] slide:多段折線
            segs = [(0.0, XT["down"], X["A"], X["B"])] + [(XT["down"] + XT["bind"] + XT.get("hold", 0.0) if k_ == 0 else None, du_, p0_, p1_) for k_, (du_, p0_, p1_) in enumerate(X["path"])] \
                   + ([(None, XT["open"], X["E"], X["E"])] if "open" in XT else []) + [(None, XT["up"], X["E"], X["E"] + [0, 0, 0.10])]
        else: segs = [(0.0, XT["down"], X["A"], X["B"]), (XT["down"] + XT["bind"] + XT.get("hold", 0.0), XT["lift"], X["B"], X["C"]), (None, XT["move"], X["C"], X["D"]),
                (None, XT["lower"], X["D"], X["E"])] + ([(None, XT["open"], X["E"], X["E"])] if "open" in XT else []) + [(None, XT["up"], X["E"], X["E"] + [0, 0, 0.10])]
        t0 = 0.0; cur = X["A"]
        for s0, du, p0, p1 in segs:
            t0 = s0 if s0 is not None else t0
            if r_ < t0: return cur
            if r_ < t0 + du: return p0 + (p1 - p0) * ss((r_ - t0) / du)
            cur = p1; t0 += du
        return cur
    def x_part_boxes():
        bc = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
        return [(nm_, bc.ComputeWorldBound(st.GetPrimAtPath("/World/Box/" + nm_)).ComputeAlignedRange()) for nm_ in ["base"] + [L["nm"] for L in LIDS]]
    def x_cavity(MW):
        q = MW - g_offw(); return bool(((np.abs(q[:, 0]) < IX) & (np.abs(q[:, 1]) < IY) & (q[:, 2] < max(CBOX["top"], CBOX["top_y"]))).any())
    def x_cloth_stats(Pw, MW, mp, Rq):
        lo, hi = MW.min(0) - 0.005, MW.max(0) + 0.005
        near = int(((Pw > lo) & (Pw < hi)).all(1).sum())
        inm, _ = sheet_in_mug(Pw, mp, Rq); d = np.linalg.norm(Pw - X["P0"], axis=1)
        return near, inm, int((d > 0.010).sum()), float(d.max()) * 1e3, d
    def x_final_cloth(Pw):
        Pl = Pw - g_offw(); out = []
        for pl in GS["plans"]:
            sd, sg = pl["sd"], pl["sg"]; m = GSIDE2 == sd; ax = pl.get("ax", 1); Cs = pl.get("C", CY); Iw = IX if ax == 0 else IY   # [v2]
            out.append("%s 越線 %.0f%% 壁外 %.0f%%" % (sd, float((sg * Pl[pl["TOPS"], ax] > Cs).mean()) * 100 if len(pl["TOPS"]) else float("nan"),
                                                   float((sg * Pl[m, ax] > Iw + 0.0015).mean()) * 100))
        inb = float(((np.abs(Pl[:, 0]) < IX) & (np.abs(Pl[:, 1]) < IY) & (Pl[:, 2] < max(CBOX["top"], CBOX["top_y"]))).mean()) * 100
        return out, inb
    def x_events(t):
        r_ = t - T_X0
        if "A" not in X:
            if TAPE and not XT.get("hold"):                                   # [v2] 取杯前拆掉剩下的膠帶(沒掀的片);扶杯模式在抬起時才拆
                _sc = [A["scope"] for A in ANC if st.GetPrimAtPath(A["scope"]).IsValid()]
                for _s in _sc: st.RemovePrim(Sdf.Path(_s))
                P("★ t=%.2f [v2] 取杯前拆掉剩下的膠帶:移除錨點 %d 個(%s)" % (t, len(_sc), sorted({A["side"] for A in ANC if A["scope"] in _sc})))
            mp, Rq, MW = mug_world(); X["q0"] = np.array(mugx.get_world_pose()[1], float); X["mp0"] = mp.copy()
            hz = float(MW[:, 2].max()) - mp[2] + H3S[2] / 2; X["hz"] = hz
            X["B"] = mp + [0, 0, hz]; X["A"] = X["B"] + [0, 0, 0.15]; X["C"] = X["B"] + [0, 0, a.extract_lift_mm / 1e3]
            X["D"] = X["C"] + [a.extract_out_mm / 1e3, 0, 0]
            zg = g_offw()[2] + CDZ
            def _land(D_):
                dst = MW + (D_ - X["B"]); z_land = zg; hit = []
                for nm_, rg in x_part_boxes():
                    mn, mx = np.array(rg.GetMin()), np.array(rg.GetMax())
                    if (dst[:, 0].max() > mn[0]) and (dst[:, 0].min() < mx[0]) and (dst[:, 1].max() > mn[1]) and (dst[:, 1].min() < mx[1]) and mx[2] > z_land:
                        z_land = mx[2]; hit.append(nm_)
                return D_ + [0, 0, (z_land + 0.001) - dst[:, 2].min()], hit
            if a.extract_mode == "slide":                                     # [extract2] 抬 20 → 斜升過 yn 壁 → 水平 −y → 降
                o_ = g_offw(); rM = float(MW[:, 1].max() - MW[:, 1].min()) / 2; hM = float(MW[:, 2].max() - MW[:, 2].min())
                zc = o_[2] + max(CBOX["top"], CBOX["top_y"]) + hM / 2 + a.slide_clear_mm / 1e3 + (mp[2] - (MW[:, 2].max() + MW[:, 2].min()) / 2)   # 杯底高過壁頂 10mm
                X["C"] = X["B"] + [0, 0, 0.020]
                yin = o_[1] - (IY - rM - 0.005); hzc = zc + hz
                C2 = np.array([X["C"][0], min(X["C"][1], yin), max(X["C"][2], hzc)])
                outm = a.extract_out_mm / 1e3
                for k_ in range(12):                                          # 落點撞箱件(蓋)→ 再往 −y 推 20mm
                    D_ = np.array([X["B"][0], X["B"][1] - outm, max(X["C"][2], hzc)]); E_, hit = _land(D_)
                    _dst = MW + (D_ - X["B"]); _bx = {nm_: rg for nm_, rg in x_part_boxes()}
                    P("  [extract3] 落點檢查 #%d 往 −y %.0f mm:杯 y %.1f~%.1f x %.1f~%.1f z_min %.1f(箱局部)| 擋到 %s"
                      % (k_, outm * 1e3, (_dst[:, 1].min() - o_[1]) * 1e3, (_dst[:, 1].max() - o_[1]) * 1e3, (_dst[:, 0].min() - o_[0]) * 1e3, (_dst[:, 0].max() - o_[0]) * 1e3,
                         (_dst[:, 2].min() - o_[2]) * 1e3, ", ".join("%s[y %.1f~%.1f x %.1f~%.1f ztop %.1f]" % (n_, (_bx[n_].GetMin()[1] - o_[1]) * 1e3, (_bx[n_].GetMax()[1] - o_[1]) * 1e3,
                         (_bx[n_].GetMin()[0] - o_[0]) * 1e3, (_bx[n_].GetMax()[0] - o_[0]) * 1e3, (_bx[n_].GetMax()[2] - o_[2]) * 1e3) for n_ in hit) or "無"))
                    if not hit: break
                    outm += 0.020
                X["D"] = D_; X["E"], X["land_on"] = E_, hit; X["zg"] = zg; X["out_used"] = outm
                X["path"] = [(0.8, X["B"], X["C"]), (2.2, X["C"], C2), (2.0, C2, X["D"]), (XT["lower"], X["D"], X["E"])]
                X["seg_t"] = np.cumsum([XT["down"] + XT["bind"] + XT.get("hold", 0.0)] + [p_[0] for p_ in X["path"]])
                P("★ [extract2] slide:杯半徑 %.1f 高 %.1f | 壁頂(局部) %.1f → 過壁手心 z %.1f | 路徑 B%s → C%s → C2%s → D%s → E%s mm | 往 −y 實際 %.0f mm(要求 %.0f)落點擋到 %s"
                  % (rM * 1e3, hM * 1e3, max(CBOX["top"], CBOX["top_y"]) * 1e3, (hzc - o_[2]) * 1e3, *[np.round((q_ - o_) * 1e3, 1) for q_ in (X["B"], X["C"], C2, X["D"], X["E"])],
                     outm * 1e3, a.extract_out_mm, hit or "無"))
                z_land = MW[:, 2].min() + (X["E"][2] - X["B"][2]) - 0.001; hit = X["land_on"]
            else:
                X["E"], hit = _land(X["D"]); X["zg"] = zg; X["land_on"] = hit; z_land = MW[:, 2].min() + (X["E"][2] - X["B"][2]) - 0.001
            if a.hand2_tuck_mm > 0:                                           # [extract3] 手 2 把 yn 布往壁外、往下壓
                for _p2 in GS["plans"]:
                    _h2 = _p2.get("h2", {})
                    if _p2["sd"] == "yn" and _h2.get("att_on"):
                        _tk = a.hand2_tuck_mm / 1e3; _pt = _h2["pw"] + [0, _p2["sg"] * _tk, -_tk]
                        g_lin("h2", t, XT["down"], _pt, np.eye(3))
                        P("★ t=%.2f [extract3] 手 2 tuck:yn 方塊 %s → %s mm(箱局部,往壁外 %.0f、往下 %.0f,%.1f s)"
                          % (t, np.round((_h2["pw"] - g_offw()) * 1e3, 1), np.round((_pt - g_offw()) * 1e3, 1), a.hand2_tuck_mm, a.hand2_tuck_mm, XT["down"]))
                    elif _p2["sd"] == "yn": P("★ t=%.2f [extract3] 手 2 tuck 略過:yn 沒在綁(%s)" % (t, _h2.get("att_on")))
            X["P0"] = PLATE.pts().copy(); X["log"] = []; X["next"] = t
            if not XT.get("hold") and TK:                                     # [v2x] 不扶杯時:取杯段開始(手 2 下降前)量杯頂覆蓋
                _rm, _, _ = measure(t, full=True); X["cov_lift"] = (_rm.get("lay") or {}).get("cov", float("nan"))
                P("★ t=%.2f [v2x] 取杯前 杯頂覆蓋 %.0f%%(露出 %.0f%%)" % (t, 100 * X["cov_lift"], 100 * (1 - X["cov_lift"])))
            if a.extract_grip == "jaw":                                       # [jaw2] 接觸面 = 指 x 帶、指 z 帶(杯頂往下 50mm)內杯頂點的 y 極值
                ztp = float(MW[:, 2].max()); xb = float(MW[MW[:, 2] > ztp - 0.005, 0].mean())
                bd = (np.abs(MW[:, 0] - xb) < H3F[0] / 2) & (MW[:, 2] > ztp - H3F[2])
                y0, y1 = float(MW[bd, 1].min()), float(MW[bd, 1].max()); hp0 = X["B"]
                ca = cb = 0.0005
                if a.jaw_collide:                                             # [jaw3] 杯端外 10mm 內有布 → 停在 杯 + 布厚 + 1mm(C1f:停 1mm 把布夾在指與 kinematic 杯之間,穿入 2.8mm);沒布 → 杯 + 1mm
                    _Pw = PLATE.pts(); _bb = (np.abs(_Pw[:, 0] - xb) < H3F[0] / 2 + 0.005) & (_Pw[:, 2] > ztp - H3F[2]) & (_Pw[:, 2] < ztp + 0.010)
                    _na = int((_bb & (_Pw[:, 1] > y0 - 0.010) & (_Pw[:, 1] < y0 + 0.002)).sum()); _nb = int((_bb & (_Pw[:, 1] < y1 + 0.010) & (_Pw[:, 1] > y1 - 0.002)).sum())
                    ca = T + 0.001 if _na else 0.001; cb = T + 0.001 if _nb else 0.001
                    P("  [jaw3] 取杯指停點:−y 端外 10mm 布點 %d → 離杯 %.1f mm;+y 端 %d → %.1f mm" % (_na, ca * 1e3, _nb, cb * 1e3))
                X["jaw"] = dict(dx=xb - hp0[0], dz=ztp - H3F[2] / 2 - hp0[2], ya=y0 - hp0[1] - H3F[1] / 2 - ca, yb=y1 - hp0[1] + H3F[1] / 2 + cb)
                P("★ t=%.2f [jaw2] 取杯夾爪:指 %s mm 沿 y 夾杯兩端;杯身 x %.1f(箱局部)接觸 y %.1f / %.1f(杯長 %.1f mm,z 帶 %.1f~%.1f);張開每邊 +25mm;合指 %.1fs → 接觸才轉 kinematic"
                  % (t, H3F * 1e3, (xb - g_offw()[0]) * 1e3, (y0 - g_offw()[1]) * 1e3, (y1 - g_offw()[1]) * 1e3, (y1 - y0) * 1e3, (ztp - H3F[2] - g_offw()[2]) * 1e3, (ztp - g_offw()[2]) * 1e3, XT["bind"]))
            EYE = g_offw() + np.array([0.55, -0.80, 0.60]); TGT = g_offw() + np.array([0.10, 0.0, 0.10])
            if TK: EYE = g_offw() + np.array([0.75, -0.95, 0.65]); TGT = g_offw() + np.array([0.19, 0.0, 0.08])   # [v2] 杯放到 +x 380 mm 也拍得到
            X["cam"] = (list(EYE), list(TGT))
            if not XT.get("hold"): G.look(cam, list(EYE), list(TGT))
            P("\n★ t=%.2f [extract] 開始:杯心 (%.1f,%.1f,%.1f) mm(箱局部 %s);取杯手 %s mm 從杯頂上方 150mm 下;抬 %.0f → +x %.0f → 放到 z %.1f(地面 %.1f;落點擋到 %s)"
              % (t, *(mp * 1e3), np.round((mp - g_offw()) * 1e3, 1), H3S * 1e3, a.extract_lift_mm, a.extract_out_mm,
                 (z_land + 0.001) * 1e3, zg * 1e3, hit or "無"))
        TB = XT["down"]; TBi = TB + XT["bind"]; TH = TBi + XT.get("hold", 0.0); TC = TH + XT["lift"]; TD = TC + XT["move"]; TE = TD + XT["lower"]
        if XT.get("hold") and "lift0" not in X and r_ >= TH - 1e-6:          # [v2] 扶杯結束、開始抬:拆剩下的膠帶、布位移基準重設、換取杯相機
            X["lift0"] = t; _sc = [A["scope"] for A in ANC if st.GetPrimAtPath(A["scope"]).IsValid()] if TAPE else []
            for _s in _sc: st.RemovePrim(Sdf.Path(_s))
            X["P0"] = PLATE.pts().copy(); G.look(cam, *X["cam"])
            P("★ t=%.2f [v2] 手 2 扶杯 %.1f s 結束 → 抬起取杯(拆剩下的膠帶 %d 個;布被帶起從這一刻起算)" % (t, XT["hold"], len(_sc)))
            _rm, _, _ = measure(t, full=True); X["cov_lift"] = (_rm.get("lay") or {}).get("cov", float("nan"))   # [v2x]
            P("★ t=%.2f [v2x] 取杯前 杯頂覆蓋 %.0f%%(露出 %.0f%%)" % (t, 100 * X["cov_lift"], 100 * (1 - X["cov_lift"])))
        X["st"] = ("hand3 down" if r_ < TB else "bind cup" if r_ < TBi else "hold cup" if r_ < TH else "lift %.0fmm" % a.extract_lift_mm if r_ < TC else
                   "move out %.0fmm" % a.extract_out_mm if r_ < TD else "place on ground" if r_ < TE else "hand3 release/up")
        if "path" in X:                                                       # [extract2]
            TE = X["seg_t"][-1]
            X["st"] = ("hand3 down" if r_ < TB else "bind cup" if r_ < TBi else "lift 20mm" if r_ < X["seg_t"][1] else "rise over yn wall" if r_ < X["seg_t"][2]
                       else "slide -y" if r_ < X["seg_t"][3] else "place on ground" if r_ < TE else "hand3 release/up")
        _hf = h2free(t) if (a.v2_h2_free and "bind" in X and "free" not in X) else None   # [v2x2](先算:重夾好那一步會更新 X["B"])
        hp = x_hand(r_) if _hf is None else _hf[0]
        GVIS["h3"].set(hp)
        if "jaw" in X:                                                        # [jaw2] 開合:下降時張開 → bind 段合到接觸 → 放下後張開
            j_ = X["jaw"]; w_ = 1.0 if r_ < TB else (1.0 - ss((r_ - TB) / XT["bind"])) if "free" not in X else ss((t - X["free"]) / XT["open"])
            if _hf is not None: w_, j_ = _hf[1], _hf[2]                       # [v2x2]
            ya, yb = j_["ya"] - 0.025 * w_, j_["yb"] + 0.025 * w_
            if a.jaw_collide: KOV["h3a"] = (hp + [j_["dx"], ya, j_["dz"]], np.eye(3)); KOV["h3b"] = (hp + [j_["dx"], yb, j_["dz"]], np.eye(3))   # [jaw3]
            else: JV["h3a"].set(hp + [j_["dx"], ya, j_["dz"]]); JV["h3b"].set(hp + [j_["dx"], yb, j_["dz"]])
            JV["h3p"].set(hp + [j_["dx"], (ya + yb) / 2, 0.0], None, [H3F[0], yb - ya + H3F[1], H3S[2]])
            X["st"] = X["st"].replace("bind cup", "close jaws on cup")
        if "bind" not in X and r_ >= (TBi if "jaw" in X else TB) - 1e-6:      # [jaw2] jaw:合指到接觸(bind 段結束)才轉 kinematic
            kin.Set(True); X["bind"] = t; X["P0"] = PLATE.pts().copy()
            mp, Rq, MW = mug_world(); near, inm, nmov, dmx, _ = x_cloth_stats(X["P0"], MW, mp, Rq)
            X["bind_near"] = near; X["bind_inm"] = inm
            P("★ t=%.2f [extract] 綁杯:杯子 physics:kinematicEnabled=True、之後每步杯心 = 手 − %.1f mm(剛性綁定);杯邊 5mm 內布頂點 %d、布穿杯 %d" % (t, X["hz"] * 1e3, near, inm))
        if "bind" in X and "free" not in X and _hf is None and "rel" not in XH:   # [v2x2] 鬆手期間杯是 dynamic
            mugx.set_world_pose(position=hp - [0, 0, X["hz"]], orientation=X["q0"])
            if r_ >= TE - 1e-6: X["free"] = t; P("★ t=%.2f [extract] 放下、手鬆開(杯子保持 kinematic 停在落點;地板碰撞早已關)" % t)
        if "bind" in X and t >= X["next"] - 1e-9:
            X["next"] = t + 0.25; Pw = PLATE.pts(); mp, Rq, MW = mug_world()
            near, inm, nmov, dmx, d = x_cloth_stats(Pw, MW, mp, Rq); cav = x_cavity(MW)
            if not cav and "t_out" not in X: X["t_out"] = t; X["out_pct"] = 100.0 * nmov / len(Pw); P("★ t=%.2f [extract2] 離箱(杯出內腔):布被帶起 %.1f%%" % (t, X["out_pct"]))
            if "free" in X and "land_pct" not in X: X["land_pct"] = 100.0 * nmov / len(Pw); P("★ t=%.2f [extract2] 落地:布被帶起 %.1f%%" % (t, X["land_pct"]))
            X["log"].append((t, near, inm, nmov, dmx))
            P("  [extract] t=%.2f %-16s 杯心 (%.1f,%.1f,%.1f) 抬 %.1f mm | 杯邊 5mm 內布點 %d | 布穿杯 %d | 布位移>10mm %d 點(%.1f%%)最大 %.1f mm | 杯在內腔 %s"
              % (t, X["st"], *(mp * 1e3), (mp[2] - X["mp0"][2]) * 1e3, near, inm, nmov, 100.0 * nmov / len(Pw), dmx, "是" if cav else "否"))
        if "sum" not in X and r_ >= sum(XT.values()) - 0.05:
            X["sum"] = 1; Pw = PLATE.pts(); mp, Rq, MW = mug_world(); near, inm, nmov, dmx, d = x_cloth_stats(Pw, MW, mp, Rq)
            L_ = X["log"]; lift = [x for x in L_ if X["bind"] + XT["bind"] + XT.get("hold", 0.0) <= x[0] <= X["bind"] + XT["bind"] + XT.get("hold", 0.0) + XT["lift"] + 1e-6]
            if "path" in X: lift = [x for x in L_ if x[0] <= X.get("t_out", 1e9) + 1e-6]   # [extract2] 抬起時 = 綁到離箱
            fc, inb = x_final_cloth(Pw); cav = x_cavity(MW); mx_inm = max([x[2] for x in L_] + [0])
            ok = (not cav) and mx_inm == 0 and np.linalg.norm(mp - X["mp0"]) > 0.15
            P("[extract] SUMMARY bind_t=%.2f 綁時杯邊布點 %d | 全程杯邊布點最大 %d 布穿杯最大 %d | 抬起段 布位移>10mm 最大 %d 點(%.1f%%)最大位移 %.1f mm | 離開內腔 t=%s | 最終杯心 世界 (%.1f,%.1f,%.1f) 箱局部 (%.1f,%.1f,%.1f) mm 杯底 z %.1f(地面 %.1f) | 最終 布位移>10mm %.1f%% 黏在杯邊 %d 點 | %s | 布在箱內 %.1f%% | 取杯 %s"
              % (X["bind"], X["bind_near"], max(x[1] for x in L_), mx_inm, max([x[3] for x in lift] + [0]), 100.0 * max([x[3] for x in lift] + [0]) / len(Pw),
                 max([x[4] for x in lift] + [0]), "%.2f" % X["t_out"] if "t_out" in X else "未離開", *(mp * 1e3), *((mp - g_offw()) * 1e3),
                 MW[:, 2].min() * 1e3, X["zg"] * 1e3, 100.0 * nmov / len(Pw), near, " / ".join(fc), inb, "OK" if ok else "NG"))
            if a.v2_h2_free:                                                  # [v2x2] 取杯只看抬起之後(扶杯 / x 片期間手 1 下指把布推進 kinematic 杯的瞬間穿杯另列)
                _il = [x[2] for x in L_ if x[0] >= X.get("lift0", 1e9) - 1e-6]; _ih = [x[2] for x in L_ if x[0] < X.get("lift0", 1e9) - 1e-6]
                P("[v2x2] SUMMARY 取杯(抬起後)布穿杯最大 %d(抬起前扶杯期間 %d)| 杯移動 %.0f mm | %s | 手 2 鬆手期間杯位移 %s mm | 重夾合指前 指-布(掃掠盒)%s mm"
                  % (max(_il + [0]), max(_ih + [0]), np.linalg.norm(mp - X["mp0"]) * 1e3, "OK" if (not cav and max(_il + [0]) == 0 and np.linalg.norm(mp - X["mp0"]) > 0.15) else "NG",
                     " / ".join("%s %.1f" % d_ for d_ in XH.get("disp", [])), " / ".join("%s %.1f,%.1f" % c_ for c_ in XH.get("chk", []))))
            P("[extract2] SUMMARY mode=%s 布被帶起 抬起時最大 %.1f%% | 離箱 %s | 落地 %s | 最終 %.1f%% | 最終杯心 箱局部 (%.1f,%.1f,%.1f) 落點擋到 %s | 布在箱內 %.1f%%"
              % (a.extract_mode, 100.0 * max([x[3] for x in lift] + [0]) / len(Pw), "%.1f%%" % X["out_pct"] if "out_pct" in X else "-",
                 "%.1f%%" % X["land_pct"] if "land_pct" in X else "-", 100.0 * nmov / len(Pw), *((mp - g_offw()) * 1e3), X["land_on"] or "無", inb))
        return

# ── [v2] 膠帶跟隨量測 / 手 2 取出整包 ──
from scipy.spatial.transform import Rotation as _Rot
TAPEV = np.unique(np.concatenate([A["vids"] for A in ANC])) if ANC else np.zeros(0, int)
V2E = {}
def qslerp(q0, q1, w):
    q0 = np.asarray(q0, float) / np.linalg.norm(q0); q1 = np.asarray(q1, float) / np.linalg.norm(q1); d = float(np.dot(q0, q1))
    if d < 0: q1 = -q1; d = -d
    if d > 0.9995: q = q0 + w * (q1 - q0); return q / np.linalg.norm(q)
    th = np.arccos(d); return (np.sin((1 - w) * th) * q0 + np.sin(w * th) * q1) / np.sin(th)
def ground_coll(on):
    n_ = 0
    for _gp in Usd.PrimRange(st.GetPrimAtPath("/World/defaultGroundPlane")):
        if _gp.HasAPI(UsdPhysics.CollisionAPI): UsdPhysics.CollisionAPI(_gp).CreateCollisionEnabledAttr(bool(on)); n_ += 1
    return n_
def v2_snap(nm_, t, ref=None):
    """[v2] 量測:膠帶點相對杯位移(vs 放錨點)、全布相對杯位移(vs ref 快照;沒給 = 放錨點)、窗內邊長比最大、杯頂覆蓋、穿杯、杯姿態"""
    rm, Pp, MW = measure(t, full=True); mp, Rq, _ = mug_world(); loc = (Pp - mp) @ Rq
    E = dict(t=t, loc=loc, P=Pp.copy(), mp=mp.copy(), cov=(rm.get("lay") or {}).get("cov", float("nan")), inmug=rm["inmug"], pen=rm["pen"], lr=rm["lr"])
    b0 = V2E.get("anc"); dt_ = np.linalg.norm(loc[TAPEV] - b0["loc"][TAPEV], axis=1) * 1e3 if b0 is not None and len(TAPEV) else np.array([np.nan])
    rf = V2E.get(ref, b0); dc = np.linalg.norm(loc - rf["loc"], axis=1) * 1e3 if rf is not None else np.array([np.nan])
    t_prev = max([e["t"] for e in V2E.values()] + [0.0]); lrw = [r["lr"][1] for r in LOGR if t_prev - 1e-6 <= r["t"] <= t + 1e-6] + [rm["lr"][1]]
    _q = np.array(mugx.get_world_pose()[1], float); ang = np.degrees(2 * np.arccos(min(1.0, abs(_q[0]))))
    if rf is not None and "P" in rf:                                          # 包裹形狀變化 = 布(世界座標)和 ref 做最佳剛體對齊(Kabsch)後的殘差
        A_, B_ = rf["P"], Pp; ca, cb = A_.mean(0), B_.mean(0); U_, _, Vt_ = np.linalg.svd((B_ - cb).T @ (A_ - ca)); dd = np.sign(np.linalg.det(Vt_.T @ U_.T))
        Rk = Vt_.T @ np.diag([1, 1, dd]) @ U_.T; dk = np.linalg.norm((B_ - cb) @ Rk.T + ca - A_, axis=1) * 1e3
    else: dk = np.array([np.nan])
    _rv = np.degrees(_Rot.from_quat([_q[1], _q[2], _q[3], _q[0]]).as_rotvec())
    E.update(tape_med=float(np.median(dt_)), tape_max=float(np.max(dt_)), cl_med=float(np.median(dc)), cl_p90=float(np.percentile(dc, 90)), cl_max=float(np.max(dc)), lrmax=float(max(lrw)),
             sh_med=float(np.median(dk)), sh_p90=float(np.percentile(dk, 90)), rotvec=_rv)
    V2E[nm_] = E
    P("★ t=%.2f [v2] %s:膠帶點 %d 相對杯位移(vs 放錨點)中位 %.2f / 最大 %.2f mm | 布相對杯位移(vs %s)中位 %.1f / p90 %.1f / 最大 %.1f mm | 包裹形狀變化(剛體對齊後)中位 %.1f / p90 %.1f mm | 邊長比 窗內最大 %.3f(%.2f~%.2f s)| 杯頂覆蓋 %.0f%% | 穿杯 %d | 自穿 %d | 杯心 (%.1f,%.1f,%.1f) mm 轉 %.1f°(rotvec %.1f,%.1f,%.1f)| 布 z %.1f~%.1f mm"
      % (t, nm_, len(TAPEV), E["tape_med"], E["tape_max"], ref or "放錨點", E["cl_med"], E["cl_p90"], E["cl_max"], E["sh_med"], E["sh_p90"], E["lrmax"], t_prev, t, 100 * E["cov"], E["inmug"], E["pen"],
         *(mp * 1e3), ang, *_rv, Pp[:, 2].min() * 1e3, Pp[:, 2].max() * 1e3))
    return E
def v2_events(t):
    if a.tape_follow and ST["released"] and "anc" not in V2E:
        mp, Rq, _ = mug_world(); _P = PLATE.pts(); V2E["anc"] = dict(t=t, loc=(_P - mp) @ Rq, P=_P.copy(), mp=mp.copy())
        P("\n★ t=%.3f [v2] --tape_follow %d:錨點保留當膠帶(%d 個錨、%d 頂點)%s" % (t, a.tape_follow, len(ANC), len(TAPEV),
          ",每步錨點目標 = 杯子姿態 x 放錨點時的相對位姿" if a.tape_follow == 1 else ",錨點固定不動(對照)"))
    if "anc" not in V2E: return
    for nm_, tt_, ref in (("before_move", T_MOVE0 - 0.02, None), ("after_move", T_OPEN0 - 0.02, None), ("opened", T_END_ALL - 0.02, None)) + \
            ((("tk_done", T_TK1 - 0.02, "opened"),) if TK else ()):
        if nm_ not in V2E and t >= tt_ and ST["inbox"]: v2_snap(nm_, t, ref)
TKD = {}
def tk_events(t):
    """[v2] 手 2 取出整包:下 → 合指(杯轉 kinematic、地板碰撞打開)→ 抬 → 平移到桌面放置點(杯姿態 slerp 回初始)→ 放 → 杯轉 dynamic → 張開 → 抬手"""
    r_ = t - T_TK0; d = TKT
    tD = d["down"]; tC = tD + d["close"]; tL = tC + d["lift"]; tM = tL + d["move"]; tW = tM + d["lower"]; tO = tW + d["open"]; tU = tO + d["up"]
    if "p0" not in TKD:
        mp, Rq, MW = mug_world(); q0 = np.array(mugx.get_world_pose()[1], float); offw = g_offw()
        Pp = PLATE.pts(); bot = float(min(Pp[:, 2].min(), MW[:, 2].min())); wtop = box_off(t)[2] + max(CBOX["top"], CBOX["top_y"], ZHI0 - 0.003)
        lift = max(a.tk_lift_mm / 1e3, wtop + 0.040 - bot)                     # 包裹底至少高過箱口 40 mm
        P1 = mp + [0, 0, lift]; P2 = np.array([offw[0], offw[1], P1[2]]); P3 = np.array([offw[0], offw[1], MZ + 0.001])
        TKD.update(p0=mp.copy(), q0=q0, P1=P1, P2=P2, P3=P3, lift=lift)
        ztop = float(Pp[:, 2].max()) - mp[2]
        TKD["fx"] = CX + T + 0.0005 + TKF[0] / 2; TKD["fz"] = ztop - TKF[2] / 2 + 0.010; TKD["pz"] = ztop + 0.010 + 0.006
        _bc = box_off(t) + np.array([BOXC[0], BOXC[1], 0.0]); TGT = 0.4 * _bc + 0.6 * np.array([offw[0], offw[1], 0.0]) + [0, 0, 0.10]
        G.look(cam, list(TGT + np.array([1.2, -1.3, 1.05])), list(TGT))
        P("\n★ t=%.2f [v2] 手 2 取出整包開始:杯心 (%.1f,%.1f,%.1f) mm(箱局部 %s)| 包裹底 z %.1f、箱口 z %.1f → 抬 %.0f mm(要求 %.0f)→ 平移到桌面放置點 (%.1f,%.1f)(箱中心往 −y %.0f mm)→ 放到杯心 z %.1f;夾法 = 杯 kinematic 跟手 + 膠帶跟杯(手指純視覺:沿 x 夾包裹兩側 ±%.1f mm)"
          % (t, *(mp * 1e3), np.round((mp - box_off(t) - np.array([BOXC[0], BOXC[1], 0.0])) * 1e3, 1), bot * 1e3, wtop * 1e3, lift * 1e3, a.tk_out_mm, offw[0] * 1e3, offw[1] * 1e3, a.tk_out_mm, P3[2] * 1e3, TKD["fx"] * 1e3))
    if "bind" not in TKD and r_ >= tC - 1e-6:
        kin.Set(True); TKD["bind"] = t; ng = ground_coll(True)
        v2_snap("tk_bind", t, "opened")
        P("★ t=%.2f [v2] 手 2 合指完成 → 杯 kinematic 跟手(包裹靠膠帶跟杯);地板(桌面)碰撞打開 %d collider" % (t, ng))
    if "bind" in TKD and "free" not in TKD:
        if r_ < tL: p = TKD["p0"] + (TKD["P1"] - TKD["p0"]) * ss((r_ - tC) / d["lift"]); q = TKD["q0"]
        elif r_ < tM: w = ss((r_ - tL) / d["move"]); p = TKD["P1"] + (TKD["P2"] - TKD["P1"]) * w; q = qslerp(TKD["q0"], QI, w)
        else: p = TKD["P2"] + (TKD["P3"] - TKD["P2"]) * ss((r_ - tM) / d["lower"]); q = QI
        mugx.set_world_pose(position=p, orientation=q)
        if r_ >= tW - 1e-6:
            v2_snap("tk_place", t, "opened")                                  # 放下那一刻(杯轉 dynamic 前):只含搬運本身
            kin.Set(False); TKD["free"] = t; ST["tape_frozen"] = True
            P("★ t=%.2f [v2] 放到桌面:杯轉回 dynamic,手 2 張開、抬起;膠帶錨點停在當下位置(包裹靜置在桌上,不再跟杯 —— 跟杯時杯子會在包裹裡自己滾 16°、包裹頂面歪掉,smoke 實測)" % t)
        if "mv" not in TKD and r_ >= tL:
            TKD["mv"] = 1; P("★ t=%.2f [v2] 抬起完成(%.0f mm),開始平移" % (t, TKD["lift"] * 1e3))
    TKS["st"] = "hand2 down" if r_ < tD else "close on package" if r_ < tC else "lift %.0fmm" % (TKD["lift"] * 1e3) if r_ < tL else "move to table" if r_ < tM \
        else "lower" if r_ < tW else "release (cup dynamic)" if r_ < tO else "hand2 up" if r_ < tU else "settle on table"
    # 視覺:手 = 杯姿態 x 固定偏移;張開量 下降時 25 mm → 合指 → 放下後張開
    if r_ < tU + 0.2:
        mp_, mq_ = mugx.get_world_pose(); mp_ = np.array(mp_, float); mq_ = np.array(mq_, float); _, Rq_, _ = mug_world()
        op = 0.025 if r_ < tD else 0.025 * (1 - ss((r_ - tD) / d["close"])) if r_ < tW else 0.025 * ss((r_ - tW) / d["open"])
        dz = 0.15 * (1 - ss(r_ / tD)) if r_ < tD else 0.12 * ss((r_ - tO) / d["up"]) if r_ >= tO else 0.0
        base = (TKD["p0"] if "bind" not in TKD else mp_) + [0, 0, dz]; qv = TKD["q0"] if "bind" not in TKD else mq_; Rv = Rq_ if "bind" in TKD else mug_world()[1]
        if "free" in TKD: base = TKD.setdefault("pfree", mp_.copy()) + [0, 0, dz]; qv = QI; Rv = np.eye(3)
        for k_, s_ in (("tka", -1.0), ("tkb", 1.0)): JV[k_].set(base + Rv @ [s_ * (TKD["fx"] + op), 0.0, TKD["fz"]], qv)
        JV["tkp"].set(base + Rv @ [0.0, 0.0, TKD["pz"]], qv, [2 * (TKD["fx"] + op) + TKF[0], 0.12, 0.012])
    elif "park" not in TKD:
        TKD["park"] = 1
        for k_ in ("tka", "tkb", "tkp"): JV[k_].set([3.0, 3.5, 1.0])

# ── 主迴圈 ───────────────────────────────────────────────────────────
try: FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 17)
except Exception: FONT = ImageFont.load_default()
L1 = ("VOLUME sheet %.0fx%.0fx%.0fmm n%d | E=%.0e nu=%.2f %.2fkg/m2 mu=%.1f | mug %.0fx%.0fx%.0f | fold %s"
      % (WX*1e3, WY*1e3, T*1e3, a.nxy, a.young, a.poisson, a.areal, a.fric, *(ME*1e3), "-".join(FOLD_ORDER)))
L2 = ("solver %d dt 1/%.0f cont %.1f rest %.2f self on | ldamp %g edamp %g | tip=top+lay*(T+1)+2mm %s%s | move %s | carton w131%s"
      % (a.solver, 1/a.dt, a.cont*1e3, a.rest*1e3, a.ldamp, a.edamp, ("extra " + a.tip_extra + " ") if a.tip_extra else "",
         ("slow " + a.slow) if a.slow else "", a.movebox, " | REST=folded" if a.rest_npz else ""))
if a.quality != "off": L2 += " | Q " + a.quality
if a.attach_stiff > 0: L2 += " | astiff %g" % a.attach_stiff
if a.attach_proxy: L2 += " | proxy k%g fmax%g" % (a.proxy_k, a.proxy_fmax)
def stamp(rgb, t, ph_):
    im = Image.fromarray(rgb[:, :, :3]); d = ImageDraw.Draw(im); Wd, Hh = im.size
    d.rectangle([0, Hh-58, Wd, Hh], fill=(16, 16, 18))
    d.text((10, Hh-54), L1, fill=(235,)*3, font=FONT)
    d.text((10, Hh-30), L2, fill=(170, 200, 230), font=FONT)
    d.rectangle([Wd-430, 4, Wd-4, 32], fill=(16, 16, 18))
    d.text((Wd-424, 8), "t=%5.2fs  %s" % (t, ph_), fill=(255,)*3, font=FONT)
    return np.array(im)

# ── [plastic] runtime 改 rest shape(模擬塑性):寫 restShapePoints → SetActive(False/True) 讓 PhysX 以新 rest 重建(points = 當下)
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
    if a.plastic_spread_mm > 0 and sel is None:                               # [spread] rest 疊層撐開(PLASTIC.md A2)
        sys.path.insert(0, os.path.join(HERE, "plastic")); import spread_rest as _SR
        _t0 = time.time(); new, _si = _SR.solve(cur, FLAT, TETS, T, a.plastic_spread_mm / 1e3, P=P)
        P("★ t=%.2f [spread] rest 撐開 %.0f mm:疊層對 %d、中面最小 %.2f mm(目標 %.1f)、邊長應變 max %.3f、四面體體積 min %.2e、解 %.1f s"
          % (t, a.plastic_spread_mm, _si["npair"], _si["sep_min_mm"], _si["D_mm"], _si.get("strain", 0), _si["vmin"], time.time() - _t0))
    e0, e1 = _stvk(cur, old), _stvk(cur, new)
    ra.Set(Vt.Vec3fArray.FromNumpy(new.astype(np.float32)))
    if a.plastic_filter_mm >= 0: PLATE.prim.GetAttribute("physxDeformableBody:selfCollisionFilterDistance").Set(a.plastic_filter_mm / 1e3)
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
                if UTT and "ut" in pl: ut_log(pl, t, nm_, k_s >= 2.0)          # [table]
        if UTT and "ut" in pl and "pre" not in pl["ut"] and t >= pl["TR"] - 0.05: ut_log(pl, t, "pre", True)   # [table] 放手前

def ut_log(pl, t, nm_, full):                                                # [table] 翻片角 / 質心 / 越線 / 他片 / 杯 / 穿杯 / 杯頂覆蓋
    rm, Pw, _ = measure(t, full=full); u = ut_stat(pl, Pw); r = g_metrics(pl, t, Pw)
    u.update(t=t, oth=r["oth_pct"], mug=r["mug_d"], inmug=rm["inmug"], pen=rm["pen"], cov=(rm.get("lay") or {}).get("cov", float("nan")) * 100)
    pl["ut"][nm_] = u
    P("★ t=%.2f [%s] [table] %s:翻片角 %.1f°(質心角 %.1f°)| 質心相對鉸線 往外 %.1f / 高 %.1f mm | 主片在鉸線外 %.0f%% | 越線 %.0f%% | 他片 >10mm %.1f%% | 杯位移 %.1f mm | 穿杯 %d | 自穿 %d | 杯頂覆蓋 %.0f%%"
      % (t, pl["sd"], nm_, u["ang"], u["angc"], u["oc"], u["zc"], u["out"], u["cross"], u["oth"], u["mug"], u["inmug"], u["pen"], u["cov"]))

writer = imageio.get_writer(os.path.join(a.out, "wrap.mp4"), fps=max(1, round(FPS / a.vid_every)), quality=7, macro_block_size=1)
SPF = int(round(1.0 / (FPS * a.dt)))                 # 每個渲染幀幾個物理步
NFR = int(round(T_END * FPS))
ME_EVERY = int(round(a.meas_dt * FPS))
KEYS = {"fold_half": FT[FOLD_ORDER[2]][0] - 0.05, "fold_done": T_FOLD_END - 0.05, "in_box": T_LID0 - 0.05,
        "lids_closed": T_MOVE0 - 0.05, "after_move": T_OPEN0 - 0.05, "opened": T_END_ALL - 0.05}
KEYF = {k: int(round(v * FPS)) - 1 for k, v in KEYS.items()}
LOGR = []; SNAP = {}; TRAJ_T = []; TRAJ_P = []; TRAJ_M = []
EV = {}
t0w = time.time(); step = 0; tcur = 0.0; nan = False
FR0 = 0                                                                       # [speed2]
CAMS = {}
T_XS = TG0 + G_SHEET * G_SEQ.index("xn") if (a.grasp and "xn" in G_SEQ) else None   # [v2x] x 片開始(yn、yp 掀完)
T_SAVE = {"grasp": TG0 if a.grasp else T_END_ALL, "opened": T_END_ALL, "xflaps": T_XS}.get(a.at) if not a.at.replace(".", "", 1).isdigit() else float(a.at)
XSAVE = a.at == "xflaps"                                                      # [v2x]
if a.save_state:
    assert not XSAVE or T_XS is not None, "[v2x] --at xflaps 要 --takeout 1 --v2_xflaps 1"
    assert XSAVE or T_ANC + 0.1 <= T_SAVE <= (TG0 if a.grasp else T_END_ALL) + 1e-9, "--at 要在放錨點(%.2f)之後、掀開段(%.2f)之前" % (T_ANC, TG0)
    P("[save] 會在 t=%.3f(%s)前的最後一幀存 %s" % (T_SAVE, a.at, a.save_state))
def _pk_safe(o):                                                              # [v2x] 去掉 lambda / closure(夾爪軌跡)才能 pickle
    import pickle as _pk
    if callable(o): return None
    if isinstance(o, dict): return {k_: _pk_safe(v_) for k_, v_ in o.items() if not callable(v_)}
    if isinstance(o, (list, tuple)): return type(o)(_pk_safe(v_) for v_ in o)
    try: _pk.dumps(o); return o
    except Exception: return None
def state_save(path, fr_):
    """[speed2] 存檔:布 points/velocities、杯姿態、箱/蓋世界姿態、ST、時間、SNAP/EV/LOGR/軌跡、RNG"""
    import pickle as _pk
    Pp = PLATE.pts(); _v = PLATE.tm.GetVelocitiesAttr().Get(); vel = np.array(_v, float).reshape(-1, 3) if _v is not None and len(_v) == len(Pp) else np.zeros_like(Pp)
    mp_, mq_ = mugx.get_world_pose()
    box = {"/World/Box/base": (BASE_P0 + box_off(tcur), BASE_Q0)}
    for L in LIDS: box["/World/Box/" + L["nm"]] = lid_pose(L, lid_deg(L, tcur), box_off(tcur))
    meta = dict(t=tcur, step=step, fr=fr_, at=a.at, ST={k: v for k, v in ST.items()}, SNAP=SNAP, EV=EV, LOGR=LOGR, rng=np.random.get_state(),
                args=vars(a).copy(), mug_p=np.array(mp_, float), mug_q=np.array(mq_, float), box={k: (np.array(p_, float), np.array(q_, float)) for k, (p_, q_) in box.items()},
                wall=time.time() - t0w, TG0=TG0 if a.grasp else None, T_END_ALL=T_END_ALL, dt=a.dt, cam=CAMS.get("look"))
    if XSAVE:                                                                 # [v2x] 抓取段中途(yn、yp 掀完):另存膠帶錨點、手指、地板、GS / 取出 / v2 量測狀態
        _at = ANCV.get_transforms(); _at = _at.numpy() if hasattr(_at, "numpy") else np.asarray(_at)
        _ap = {pth_: (np.array(_at[i_, :3], float), np.array([_at[i_, 6], *_at[i_, 3:6]], float)) for i_, pth_ in enumerate(ANCV.prim_paths)}
        _gp = {}
        for k_ in GKEYS:
            _p, _R = g_pose(k_, tcur); _gp[k_] = (np.array(_p, float), np.array(_R, float))
        _gc = [bool(UsdPhysics.CollisionAPI(_g).GetCollisionEnabledAttr().Get()) for _g in Usd.PrimRange(st.GetPrimAtPath("/World/defaultGroundPlane")) if _g.HasAPI(UsdPhysics.CollisionAPI)]
        meta.update(xs=dict(T_XS=T_XS, anc=_ap, alive=[A["scope"] for A in ANC if st.GetPrimAtPath(A["scope"]).IsValid()], gpose=_gp, ground=bool(_gc and all(_gc)),
                            GS=_pk_safe({k_: v_ for k_, v_ in GS.items()}), TKD=_pk_safe(TKD), TKS=dict(TKS), V2E=_pk_safe(V2E), glook=CAMS.get("glook"), gfocal=a.gcam_focal,
                            kin=bool(kin.Get())))
    np.savez_compressed(path, pts=Pp.astype(np.float64), vel=vel, traj_t=np.array(TRAJ_T), traj_p=np.array(TRAJ_P, np.float32), traj_m=np.array(TRAJ_M),
                        meta=np.frombuffer(_pk.dumps(meta), np.uint8))
    P("★ t=%.3f [save] 存檔 → %s(布 %d 點、|v| 最大 %.3f m/s、杯 %s mm、wall %.0f s)" % (tcur, path, len(Pp), np.abs(vel).max(), np.round(np.array(mp_) * 1e3, 1), meta["wall"]))
if LOADED is not None:                                                        # [speed2] 續跑:接回量測狀態、時間、RNG
    _m = LOADED
    assert abs(_m["T_END_ALL"] - T_END_ALL) < 1e-6 and (not a.grasp or _m["TG0"] is None or abs(_m["TG0"] - TG0) < 1e-6), "存檔的時間表(折/蓋/搬)跟這次旗標不同"
    ST.update(_m["ST"]); SNAP.update(_m["SNAP"]); EV.update(_m["EV"]); LOGR.extend(_m["LOGR"])
    TRAJ_T.extend(_m["traj_t"]); TRAJ_P.extend(_m["traj_p"]); TRAJ_M.extend(_m["traj_m"])
    np.random.set_state(_m["rng"])
    tcur = _m["t"]; step = int(round(tcur / a.dt)); FR0 = _m["fr"] + 1
    if _m.get("cam"): G.look(cam, *_m["cam"])
    if "xs" in _m:                                                            # [v2x] x 片開始前的存檔:接回 GS(yn/yp 計畫)、手指停點、取出 / v2 量測、相機
        _x = _m["xs"]; assert abs(_x["T_XS"] - T_XS) < 1e-6, "[v2x] 存檔的 x 片開始時間 %.3f ≠ 這次旗標 %.3f(抓取段時間表不同)" % (_x["T_XS"], T_XS)
        GS.update(_x["GS"]); TKD.update(_x["TKD"]); TKS.update(_x["TKS"]); V2E.update(_x["V2E"])
        for k_, (_p, _R) in _x["gpose"].items():
            if k_ in GF: GF[k_]["segs"] = [(0.0, 1e-3, lambda w, _p=_p, _R=_R: (_p, _R))]; GF[k_]["last"] = (_p, _R)
        if _x.get("glook"):
            cam.set_focal_length(_x["gfocal"]); G.look(cam, *_x["glook"]); CAMS["glook"] = _x["glook"]
            try: cam.set_clipping_range(0.01, 100.0)
            except Exception: pass
        P("  [load] [v2x] x 片存檔:GS 計畫 %s(k=%d)、膠帶錨點 %d 個仍在(%s)、桌面碰撞 %s、手指停點 %s"
          % ([p_["sd"] for p_ in GS["plans"]], GS["k"], len(_x["alive"]), sorted({A["side"] for A in ANC if A["scope"] in _x["alive"]}), "開" if _x["ground"] else "關",
             {k_: np.round(v_[0] * 1e3).tolist() for k_, v_ in _x["gpose"].items() if np.linalg.norm(v_[0]) < 2.0}))
    P("  [load] 從第 %d 幀(t=%.3f、第 %d 步)續跑到 %.2f;量測 %d 筆、快照 %s" % (FR0, tcur, step, T_END, len(LOGR), sorted(SNAP)))
SAVED = False
P("渲染 %d fps,每幀 %d 物理步;共 %d 幀 | quality %s:影片 %d fps %s(vid_every %d)" % (FPS, SPF, NFR, a.quality, max(1, round(FPS / a.vid_every)), a.vid_res, a.vid_every))
for fr in range(FR0, NFR):                                                       # [speed2] FR0 = 0(續跑時 = 存檔幀 + 1)
    _vid = (fr % a.vid_every == 0) or fr == NFR - 1 or fr in KEYF.values()
    for k in range(SPF):
        step += 1; tcur = step * a.dt
        # ── 事件 ──
        if UT and "fold_end" not in SNAP and tcur >= T_INBOX:                 # [table] 不入箱:只記 fold_end;箱子留在旁邊、地面(= 桌面)碰撞保留
            r_, _, _ = measure(tcur, full=True); SNAP["fold_end"] = (PLATE.pts().copy(), mug_world()[2].copy(), r_)
            _dl.GetIntensityAttr().Set(3500.0); _dl2.GetIntensityAttr().Set(2200.0)
            P("\n★ t=%.3f [table] 四折+收耳完成:不入箱(箱子留在 %s mm),包裹留在桌面上;側板 %.2f 撤、放錨點 %.2f、掀開 %.2f" % (tcur, np.round(OFF_SIDE * 1e3), T_REL, T_ANC, TG0))
        if not ST["inbox"] and not UT and tcur >= T_INBOX:
            Pp = PLATE.pts(); mp, Rq, MW = mug_world()
            r_, _, _ = measure(tcur, full=True); SNAP["fold_end"] = (Pp.copy(), MW.copy(), r_)
            c = (Pp[:, :2].min(0) + Pp[:, :2].max(0)) / 2
            if a.squeeze_t > 0:
                c = np.zeros(2)          # 側板以原點為中心收,箱子也以原點為中心
            ST["OFF_IN"] = np.array([c[0] - BOXC[0], c[1] - BOXC[1], -CDZ])
            # ★ 箱子用 PhysX tensor set_transforms **瞬移**(不經 kinematic target)。
            #   第 3 版用 USD set_world_pose 瞬移:kinematic 以 ~200 m/s 的速度「走」過去,同時側板以 720 m/s 往下撤,
            #   碰到的布被摩擦拖走 → 那一格自穿 4→211、反轉 0→19、布穿杯 0→6。
            _off = ST["OFF_IN"]
            _D = np.zeros((BOXV.count, 7), np.float32)
            for i_, pth_ in enumerate(BOXV.prim_paths):
                if pth_.endswith("/base"):
                    p_, q_w = BASE_P0 + _off, BASE_Q0
                else:
                    L_ = [L for L in LIDS if pth_.endswith("/" + L["nm"])][0]
                    p_, q_w = lid_pose(L_, 180.0, _off)
                _D[i_, :3] = p_; _D[i_, 3:6] = q_w[1:]; _D[i_, 6] = q_w[0]
            BOXV.set_transforms(_D, np.arange(BOXV.count, dtype=np.int32))
            BOXV.set_velocities(np.zeros((BOXV.count, 6), np.float32), np.arange(BOXV.count, dtype=np.int32))
            P("  箱子 tensor set_transforms 瞬移 %d 個剛體(base + 4 蓋)" % BOXV.count)
            P("\n★ t=%.3f 入箱:包裹(布)bbox 中心 (%.1f,%.1f) mm,杯心 (%.1f,%.1f,%.1f);箱子剛性瞬移到 %s mm(箱底內面 = 地面)"
              % (tcur, c[0]*1e3, c[1]*1e3, *(mp*1e3), np.round(ST["OFF_IN"]*1e3, 1)))
            P("  入箱前(瞬移前)以箱子目標位置比對內腔:")
            EV["pre_in"] = (inbox("布", Pp, ST["OFF_IN"]), inbox("杯子", MW, ST["OFF_IN"]))
            ST["inbox"] = True
            _ng = 0
            for _gp in Usd.PrimRange(st.GetPrimAtPath("/World/defaultGroundPlane")):
                if _gp.HasAPI(UsdPhysics.CollisionAPI):
                    UsdPhysics.CollisionAPI(_gp).CreateCollisionEnabledAttr(False); _ng += 1
            P("  地板碰撞關閉(%d collider);箱底(+pad)接手" % _ng)
            _dl.GetIntensityAttr().Set(3500.0); _dl2.GetIntensityAttr().Set(2200.0)
            _R = 0.64
            EB = np.array([_R*1.55, -_R*1.70, _R*2.05]) + MOVE/2 + ST["OFF_IN"] * [1, 1, 0]
            TB = np.array([0, 0, 0.030]) + MOVE/2 + ST["OFF_IN"] * [1, 1, 0]
            G.look(cam, list(EB), list(TB)); CAMS["look"] = (list(EB), list(TB))   # [speed2] 存檔要記相機
        if not ST["released"] and tcur >= T_ANC:
            Pp = PLATE.pts(); mp, Rq, MW = mug_world()
            r_, _, _ = measure(tcur, full=True); SNAP["closed_pre_release"] = (Pp.copy(), MW.copy(), r_)
            if a.plastic_on_fold: plastic_bake("關蓋完成、放錨點前(全片)", tcur)   # [plastic]
            if TAPE: P("\n★ t=%.3f [table] --ut_tape 1:錨點保留(當膠帶),掀哪片夾好時才移除那片的" % tcur)   # [table]([v2] --tape_follow 同)
            else: st.RemovePrim(Sdf.Path("/World/attach"))
            kin.Set(False)
            ST["released"] = True
            P("\n★ t=%.3f 關蓋完成 → RemovePrim 全部錨點(4 scope);杯子轉 dynamic" % tcur)
        if TK and T_TK0 - 1e-9 <= tcur < T_TK1 + 1e-9: tk_events(tcur)         # [v2] 手 2 取出整包
        drive(tcur)
        if a.tape_follow or TK: v2_events(tcur)                               # [v2]
        if a.grasp and tcur >= TG0 - 1e-9:
            if GFSX is not None and not SWX["on"] and T_XS is not None and tcur >= T_XS - 1e-9:   # [v2x2] x 片開始:換成 x 片寬指
                SWX["on"] = True; GFS = GFSX
                P("★ t=%.2f [v2x2] x 片開始:手 1 換成寬指 %s mm(upW/loW;yn/yp 用的 up/lo 停 park)" % (tcur, np.round(GFSX * 1e3)))
            g_events(tcur); g_drive(tcur)
            if a.plastic_on_release or a.release_watch: plastic_watch(tcur)   # [plastic]
        if a.extract and tcur >= T_X0 - 1e-9: x_events(tcur)                   # [extract]
        world.step(render=(k == SPF - 1) and _vid)
    # ── 渲染幀 ──
    Pp = PLATE.pts()
    if not np.isfinite(Pp).all():
        P("★ NaN t=%.3f" % tcur); nan = True; break
    if a.fast_pts and fr in (5, ME_EVERY * 8):            # [speed] 驗證 tensor 與 USD 一致
        P("[fast_pts] t=%.2f max|tensor-USD| = %.3g m" % (tcur, np.abs(Pp - _usd_pts()).max()))
    if _vid:
        VISPTS.Set(Vt.Vec3fArray.FromNumpy(Pp.astype(np.float32)))
    if a.grasp and tcur >= TG0 - 1e-9:
        g_vis(tcur)
    rgb = cam.get_rgba() if _vid else None
    ph_ = phase(tcur)
    if rgb is not None and rgb.size:
        img = stamp(rgb, tcur, ph_)
        if fr % a.vid_every == 0: writer.append_data(img)
        for kname, kf in KEYF.items():
            if fr == kf:
                Image.fromarray(img).save(os.path.join(a.out, "key_%s.png" % kname))
    # ── 量測 ──
    if fr % ME_EVERY == 0 or fr == NFR - 1:
        full = (fr % (ME_EVERY * 4) == 0) or fr == NFR - 1
        r, Pp, MW = measure(tcur, full=full)
        LOGR.append(r); TRAJ_T.append(tcur); TRAJ_P.append(Pp.astype(np.float32)); TRAJ_M.append(np.r_[r["mug"]])
        s_ = ("t=%6.2f %-24s bbox %3.0fx%3.0fx%3.0f | 自穿 %4d | 布穿杯 %3d | 反轉 %3d | 體積比 %.4f | 邊長比 [%.3f,%.3f] | 杯心 (%5.1f,%5.1f,%5.1f)"
              % (tcur, ph_, *r["bb"], r["pen"], r["inmug"], r["inv"], r["volr"], *r["lr"], *(r["mug"]*1e3)))
        if ST["inbox"]:
            off = box_off(tcur); lz = lid_cz()
            s_ += " | 箱位移 (%.0f,%.0f,%.0f) 蓋z(相對箱底) %s" % (*((off - ST["OFF_IN"])*1e3),
                                                          " ".join("%s=%.1f" % (k_, (v_ - off[2] - CDZ)*1e3) for k_, v_ in lz.items()))
        if r.get("lay"):
            s_ += " | 杯頂上 %.0f 層 間距 %.2f 頂厚 %.1f" % (r["lay"]["nlay"], r["lay"]["gap"], r["lay"]["top"])
        P(s_)
        if a.grasp and GS["plans"] and tcur >= TG0:
            _pl = GS["plans"][-1]; g_line(_pl, g_metrics(_pl, tcur, Pp), r)
            if a.jaw_collide:                                                 # [jaw3] 指-布最小距離(布頂點對指盒 SDF,負 = 穿入)
                _FS = {"up": GFS, "lo": GFS, "h2a": H2F if a.hand2 == "jaw" else None, "h2b": H2F if a.hand2 == "jaw" else None,
                       "h3a": H3F if (a.extract and a.extract_grip == "jaw") else None, "h3b": H3F if (a.extract and a.extract_grip == "jaw") else None}   # [matsweep] --extract 0 時 H3F 未定義
                _cl = {"up": "grip" in _pl["ev"] and (tcur < _pl.get("TR", 1e9) or (a.hold_yp and _pl["sd"] == "yp")),
                       "h2": any(_p.get("h2", {}).get("att_on") for _p in GS["plans"]), "h3": "bind" in X and "free" not in X and not XH.get("open")}
                _out = []
                for _k, _sz in _FS.items():
                    if _sz is None or _k not in GPATH: continue
                    _p, _R = g_pose(_k, tcur)
                    if np.linalg.norm(_p - g_offw()) > 1.0: continue
                    _q = np.abs((Pp - _p) @ _R) - _sz / 2; _d = np.where((_q < 0).all(1), _q.max(1), np.linalg.norm(np.maximum(_q, 0), axis=1)).min() * 1e3
                    _c = _cl["up" if _k in ("up", "lo") else _k[:2]]
                    if _c: JM[_k] = min(JM.get(_k, 1e9), _d)
                    _out.append("%s %.1f%s" % (_k, _d, "*" if _c else ""))
                if _out: P("  [jaw3] t=%.2f 指-布最小距離 mm(* = 合指中):%s" % (tcur, " | ".join(_out)))
                if fr == NFR - 1: P("[jaw3] SUMMARY 合指中 指-布最小距離 mm(負 = 穿入,判準 >= -2):%s" % " | ".join("%s %.1f" % kv for kv in JM.items()))
            _gth = a.guard_hold if (a.guard_hold > 0 and _pl.get("hold", {}).get("on")) else 2.3   # [drag2]
            _gn = 1
            if _pl["sd"] == "yp":                                              # [extract2] yp 段門檻/連續次數
                if a.guard_yp > 0: _gth = a.guard_yp
                _gn = max(1, a.guard_n)
            if _pl["sd"] == "yn" and a.guard_yn > 0:                           # [extract3] yn 段門檻/連續次數
                _gth = a.guard_yn; _gn = max(1, a.guard_n)
            _pl["gcnt"] = (_pl.get("gcnt", 0) + 1) if r["lr"][1] > _gth else 0
            if _pl.get("att", {}).get("on") and r["lr"][1] > _gth and _pl["gcnt"] < _gn:
                P("  [guard_yp] t=%.2f [%s] 邊長比 %.3f > %.2f 第 %d/%d 次,先不放" % (tcur, _pl["sd"], r["lr"][1], _gth, _pl["gcnt"], _gn))
            if _pl.get("att", {}).get("on") and r["lr"][1] > _gth and _pl["gcnt"] >= _gn:
                st.RemovePrim(Sdf.Path(_pl["att"]["scope"])); _pl["att"]["on"] = False
                if _pl["att"].get("lo"): st.RemovePrim(Sdf.Path(_pl["att"]["scope"] + "_lo")); _pl["ev"]["lr_guard"] = tcur
                P("★ t=%.2f [%s] 守衛:邊長比最大 %.3f > %.2f(連續 %d 次)→ RemovePrim %s 放手" % (tcur, _pl["sd"], r["lr"][1], _gth, _pl["gcnt"], _pl["att"]["scope"]))
                if _pl.get("hold", {}).get("on"):                               # [drag] 守衛時也放開他片
                    st.RemovePrim(Sdf.Path(_pl["hold"]["scope"])); _pl["hold"]["on"] = False; _pl["ev"]["hold_guard"] = tcur
                    P("★ t=%.2f [%s] 守衛:同時 RemovePrim %s 放開他片 %d 點" % (tcur, _pl["sd"], _pl["hold"]["scope"], _pl["hold"]["n"]))
    if a.grasp and GS["plans"] and not a.arc2_over_cap and "cl" not in GS["plans"][-1] and GS["plans"][-1].get("TP1") is not None \
            and tcur >= GS["plans"][-1]["TP1"] - 1e-6 and "p3log" not in GS["plans"][-1]:   # [peel3] 開環越壁到位時印
        _pl = GS["plans"][-1]; _pl["p3log"] = 1; _g = (g_pose("up", tcur)[0] - g_offw()); _sg = _pl["sg"]
        _cy = float((PLATE.pts() - g_offw())[GSIDE2 == _pl["sd"], 1].mean())
        P("  [peel3] t=%.2f [%s] 越壁到位:上指 y=%.1f(越壁外緣 %.1f mm)質心 y=%.1f | 邊長比 %.3f" % (tcur, _pl["sd"], _g[1] * 1e3, (_sg * _g[1] - IY - 0.0015) * 1e3, _cy * 1e3, LOGR[-1]["lr"][1] if LOGR else float("nan")))
    if a.grasp and GS["plans"] and "cl" in GS["plans"][-1]:                  # [peel3] 閉環越壁
        _pl = GS["plans"][-1]; _c = _pl["cl"]
        if _c["T0"] - 1e-9 <= tcur <= _c["T0"] + a.arc2_cl_t + 1e-6 and tcur >= _c["next"] - 1e-6 and _c["stop"] is None:
            _c["next"] += 0.25
            _Pl = PLATE.pts() - g_offw(); _sg = _pl["sg"]; _cy = float(_Pl[GSIDE2 == _pl["sd"], 1].mean())
            _w = min(1.0, max(0.0, (tcur - _c["T0"]) / a.arc2_cl_t)); _Pq, _ = _c["over"](_w); _g = (_Pq["up"] + _Pq["lo"]) / 2
            _edge = IY + 0.0015; _over = _sg * _g[1] - _edge
            _why = None
            if _sg * _cy >= _edge + a.arc2_margin_mm / 1e3: _why = "達標"
            elif not _pl.get("att", {}).get("on"): _why = "守衛/已放"
            elif a.arc2_er_stop > 0 and LOGR and LOGR[-1]["lr"][1] > a.arc2_er_stop: _why = "邊長比 %.3f > %.2f" % (LOGR[-1]["lr"][1], a.arc2_er_stop)   # [peel4]
            elif _w >= 1.0: _why = "時間上限"
            P("  [peel3] t=%.2f [%s] 質心 y=%.1f mm(壁外緣 %.1f − %.0f)| 夾爪 y=%.1f z=%.1f 越壁 %.1f mm w=%.2f | 邊長比 %.3f%s"
              % (tcur, _pl["sd"], _cy * 1e3, -_sg * _edge * 1e3, a.arc2_margin_mm, _g[1] * 1e3, _g[2] * 1e3, _over * 1e3, _w,
                 LOGR[-1]["lr"][1] if LOGR else float("nan"), (" → 停(%s)" % _why) if _why else ""))
            if _why: _c["stop"] = _w; _c["wf"] = _w
    if a.grasp and GS["plans"] and "lay" in GS["plans"][-1]:                 # [peel4] 往下段:每 0.25s 印,邊長比過門檻凍結
        _pl = GS["plans"][-1]; _L = _pl["lay"]
        if _L["T0"] - 1e-9 <= tcur <= _L["T0"] + a.arc2_lay_t + GT["peel_hold"] + 1e-6 and tcur >= _L.get("next", _L["T0"]) - 1e-6:
            _L["next"] = tcur + 0.25; _wl = ss(min(1.0, (tcur - _L["T0"]) / a.arc2_lay_t)); _g = g_pose("up", tcur)[0] - g_offw()
            _cy = float((PLATE.pts() - g_offw())[GSIDE2 == _pl["sd"], 1].mean()); _lr = LOGR[-1]["lr"][1] if LOGR else float("nan")
            _st = ""
            if _L["stop"] is None and a.arc2_er_stop > 0 and _lr > a.arc2_er_stop and _wl < 1.0:
                _L["stop"] = _wl; _st = " → 凍結(邊長比 > %.2f)" % a.arc2_er_stop
            P("  [peel4] t=%.2f [%s] 往下 w=%.2f 上指 y=%.1f z=%.1f | 質心 y=%.1f | 邊長比 %.3f%s" % (tcur, _pl["sd"], _wl, _g[1] * 1e3, _g[2] * 1e3, _cy * 1e3, _lr, _st))
    # 階段快照
    for nm_, tt_ in [("fold_" + FOLD_ORDER[1], FT[FOLD_ORDER[2]][0] - 1e-6), ("after_move", T_OPEN0 - 1e-6),
                     ("before_move", T_MOVE0 - 1e-6), ("end", T_END_ALL - 1e-6)]:
        if nm_ not in SNAP and tcur >= tt_ - 1.0/FPS and tcur < tt_ + 1.0/FPS:
            _P = PLATE.pts(); _, _, _MW = mug_world(); r_, _, _ = measure(tcur, full=True)
            SNAP[nm_] = (_P.copy(), _MW.copy(), r_)
            if nm_ == "before_move":
                SNAP[nm_] = (_P.copy(), _MW.copy(), r_, box_off(tcur).copy(), mugx.get_world_pose()[0].copy())
    if LOADED is not None and fr == FR0:                                      # [speed2] 續跑第 1 幀:布有沒有真的從存檔狀態開始
        P("  [load] 續跑第 1 幀 t=%.3f:max|布 - 存檔| = %.2f mm(1 幀內的運動;>50 mm = points 寫入沒生效)" % (tcur, np.abs(PLATE.pts() - LOADED["pts"]).max() * 1e3))
    if a.save_state and not SAVED and tcur + SPF * a.dt >= T_SAVE - 1e-9:      # [speed2] 下一幀會碰到存檔點 → 現在存
        state_save(a.save_state, fr); SAVED = True
        if a.save_exit: break
writer.close()
wall = time.time() - t0w
P("\n影片 → %s/wrap.mp4(%d 幀);wall %.1fs / sim %.2fs = %.2f" % (a.out, fr + 1, wall, tcur, wall / max(tcur, 1e-9)))

# ── 結尾判讀 ─────────────────────────────────────────────────────────
Pf = PLATE.pts(); mpf, Rqf, MWf = mug_world()
rf, _, _ = measure(tcur, full=True)
SNAP.setdefault("final", (Pf.copy(), MWf.copy(), rf))
P("\n===== 判讀 wrap_vol sheet %.0f(%s)=====" % (a.sheet_mm, "NaN 中止" if nan else "跑到 %s" % a.until))
def row(nm_, r):
    ly = r.get("lay") or {}
    P("  %-22s t=%6.2f bbox 布 %3.0fx%3.0fx%3.0f / 含杯 %3.0fx%3.0fx%3.0f | 體積÷杯 %.2f | 自穿 %d | 布穿杯 %d | 反轉 %d | 體積比 %.4f | 杯頂上 %s 層(分佈 %s)間距 %s 頂厚 %s 第1層離杯頂 %s"
      % (nm_, r["t"], *r["bb"], *r["pkg"], r["pkgvol"], r["pen"], r["inmug"], r["inv"], r["volr"],
         ly.get("nlay", "-"), ly.get("dist", "-"), "%.2f" % ly["gap"] if ly else "-",
         "%.1f" % ly["top"] if ly else "-", "%.1f" % ly["first"] if ly else "-")
      + (" | 杯頂俯視覆蓋 %.0f%%" % (100*ly["cov"]) if ly else ""))
for nm_ in ["fold_" + FOLD_ORDER[1], "fold_end", "closed_pre_release", "before_move", "after_move", "end", "final"]:
    if nm_ in SNAP:
        row(nm_, SNAP[nm_][2])
P("  全程最大:自穿 %d(t=%.2f %s)| 布穿杯 %d | 反轉 %d | 邊長比 [%.3f, %.3f]"
  % (max(r["pen"] for r in LOGR), max(LOGR, key=lambda r: r["pen"])["t"], max(LOGR, key=lambda r: r["pen"])["ph"],
     max(r["inmug"] for r in LOGR), max(r["inv"] for r in LOGR), min(r["lr"][0] for r in LOGR), max(r["lr"][1] for r in LOGR)))
# 每折自穿增量
P("  每階段結束時自穿:")
lastph = None
for r in LOGR:
    if lastph is not None and r["ph"] != lastph[0]:
        P("    %-26s 結束 t=%.2f 自穿 %d" % (lastph[0], lastph[1], lastph[2]))
    lastph = (r["ph"], r["t"], r["pen"])
if lastph: P("    %-26s 結束 t=%.2f 自穿 %d" % lastph)
# 折疊驅動檢查:每折錨點尖端位置
if "fold_end" in SNAP:
    Pfe = SNAP["fold_end"][0]
    for sd, S_ in SIDES.items():
        vv_ = S_["vids"] if S_["ax"] == 0 else S_["vids"][np.abs(FLAT[S_["vids"], 0]) <= CX]
        q = Pfe[vv_]
        P("  折 %s 尖端(綁的、|x|<=CX 的 %d 點)along %.1f~%.1f z %.1f~%.1f mm(目標 along %.1f z %.1f±2)"
          % (sd, len(q), (S_["sg"]*q[:, S_["ax"]]).min()*1e3, (S_["sg"]*q[:, S_["ax"]]).max()*1e3, q[:, 2].min()*1e3,
             q[:, 2].max()*1e3, S_["along_end"]*1e3, S_["zend"]*1e3))
if ST["inbox"]:
    P("\n===== 真的入箱了嗎(逐頂點比對內腔)=====")
    if "closed_pre_release" in SNAP:
        P(" 關蓋後(放錨前):")
        EV["closed"] = (inbox("布", SNAP["closed_pre_release"][0], ST["OFF_IN"]), inbox("杯子", SNAP["closed_pre_release"][1], ST["OFF_IN"]))
    if "before_move" in SNAP:
        P(" 搬前:")
        bm = SNAP["before_move"]
        EV["bm"] = (inbox("布", bm[0], bm[3]), inbox("杯子", bm[1], bm[3]))
    if "after_move" in SNAP:
        P(" 搬後(原點 = 箱子最終位置):")
        offm = box_off(T_OPEN0 - 1e-6)
        EV["am"] = (inbox("布", SNAP["after_move"][0], offm), inbox("杯子", SNAP["after_move"][1], offm))
        bm = SNAP["before_move"]; am = SNAP["after_move"]
        rel0 = bm[0].mean(0) - bm[3]; rel1 = am[0].mean(0) - offm
        mr0 = bm[4] - bm[3]; mr1 = am[2]["mug"] - offm
        P("  搬箱:箱位移 (%.1f,%.1f,%.1f) mm;布質心相對箱 搬前→搬後 差 %.1f mm;杯心相對箱 差 %.1f mm"
          % (*((offm - bm[3])*1e3), np.linalg.norm(rel1 - rel0)*1e3, np.linalg.norm(mr1 - mr0)*1e3))
        P("  杯心相對箱中心(搬後):(%+.1f, %+.1f, %+.1f) mm(z 相對箱底內面)"
          % ((mr1[0]-BOXC[0])*1e3, (mr1[1]-BOXC[1])*1e3, (mr1[2]-CDZ)*1e3))
    if tcur >= T_END_ALL - 0.1:
        P(" 開蓋後(結束):")
        offe = box_off(tcur)
        EV["end"] = (inbox("布", SNAP["end"][0], offe), inbox("杯子", SNAP["end"][1], offe)) if "end" in SNAP else (inbox("布", Pf, offe), inbox("杯子", MWf, offe))
    off = box_off(tcur); lz = lid_cz()
    P("  蓋中心 z(相對箱底內面):%s;關著時預設 %s"
      % (" ".join("%s=%.1f" % (k_, (v_ - off[2] - CDZ)*1e3) for k_, v_ in lz.items()),
         " ".join("%s=%.1f" % (L["nm"], (L["cz0"] - CDZ)*1e3) for L in LIDS)))
    def verdict(e, lid_open=False):
        s, m = e
        if lid_open:      # 蓋子開著:高於口不算出箱,只看 x/y/底
            s = dict(s, n=s["x"] + s["y"] + s["lo"], hi=0); m = dict(m, n=m["x"] + m["y"] + m["lo"], hi=0)
        if s["n"] + m["n"] == 0: return "PASS"
        if s["x"] + s["y"] + s["hi"] + m["x"] + m["y"] + m["hi"] == 0 and s["n"] + m["n"] <= 10 and max(s["dlo"], m["dlo"]) < 5: return "WARN"
        return "FAIL"
    def cnt(v_, lid_open):
        return [(d["x"] + d["y"] + d["lo"]) if lid_open else d["n"] for d in v_]
    P("  驗收:" + " | ".join("%s %s(布 %d 杯 %d)" % (k_, verdict(v_, k_ in ("pre_in", "end")), *cnt(v_, k_ in ("pre_in", "end")))
                            for k_, v_ in EV.items()) + "(pre_in / end 蓋子開著,只計 x/y/底)")
    _q = mugx.get_world_pose()[1]
    P("  杯子姿態:相對初始轉了 %.1f°(dynamic 之後)" % np.degrees(2*np.arccos(min(1.0, abs(float(_q[0]))))))
# ── 軟度掃描用摘要 ──
def zrel(Pp, off): return (Pp[:, 2] - off[2] - CDZ) * 1e3          # 相對箱底內面 mm
LIDBOT = min(L["zmin0"] for L in LIDS) - CDZ                         # 下蓋底面(相對箱底內面),m
try:
    pre = [r for r in LOGR if r["t"] <= T_SQ0 + 1e-6][-1]
    P("\n===== SUMMARY =====")
    P("  E %.0e T %.1fmm 面密度 %.2f cont %.2f rest %.2f tuck %d" % (a.young, a.thick_mm, a.areal, a.cont*1e3, a.rest*1e3, a.tuck))
    P("  四折後(收耳前 t=%.2f)bbox %.0fx%.0fx%.0f;側板內縮目標 %.0fx%.0f ⇒ 側板%s碰到布(四折後 bbox 是否超出)"
      % (pre["t"], *pre["bb"], 2*(IX - a.squeeze_mm/1e3)*1e3, 2*(IY - a.squeeze_mm/1e3)*1e3,
         "會" if (pre["bb"][0] > 2*(IX - a.squeeze_mm/1e3)*1e3 or pre["bb"][1] > 2*(IY - a.squeeze_mm/1e3)*1e3) else "不會"))
    if "fold_end" in SNAP: P("  收耳後/入箱前 bbox %.0fx%.0fx%.0f" % tuple(SNAP["fold_end"][2]["bb"]))
    if "closed_pre_release" in SNAP:
        r_ = SNAP["closed_pre_release"][2]; P("  關蓋後 bbox %.0fx%.0fx%.0f 體積÷杯 %.2f" % (*r_["bb"], r_["pkgvol"]))
    if "closed_pre_release" in SNAP and "before_move" in SNAP:
        z1 = zrel(SNAP["closed_pre_release"][0], ST["OFF_IN"]); z2 = zrel(SNAP["before_move"][0], SNAP["before_move"][3])
        P("  頂力代理:下蓋底面 %.1fmm;布頂 z(max/99%%)放錨前 %.1f/%.1f → 放錨後 2s %.1f/%.1f;離蓋底 <2mm 的頂點 %d → %d"
          % (LIDBOT*1e3, z1.max(), np.percentile(z1, 99), z2.max(), np.percentile(z2, 99),
             int((z1 > LIDBOT*1e3 - 2).sum()), int((z2 > LIDBOT*1e3 - 2).sum())))
    if "end" in SNAP and tcur >= T_END_ALL - 0.1:
        ze = zrel(SNAP["end"][0], box_off(tcur)); ly = SNAP["end"][2].get("lay") or {}
        P("  開蓋後 3s:布頂 z max %.1f / 99%% %.1f mm(箱口 %.1f);杯頂俯視覆蓋 %.0f%%" % (ze.max(), np.percentile(ze, 99), (ZHI0-CDZ)*1e3, 100*ly.get("cov", float("nan"))))
    P("  全程最大 自穿 %d 布穿杯 %d 反轉 %d 邊長比 [%.3f,%.3f] 體積比 [%.4f,%.4f]"
      % (max(r["pen"] for r in LOGR), max(r["inmug"] for r in LOGR), max(r["inv"] for r in LOGR),
         min(r["lr"][0] for r in LOGR), max(r["lr"][1] for r in LOGR), min(r["volr"] for r in LOGR), max(r["volr"] for r in LOGR)))
    P("  wall %.1fs" % wall)
except Exception as e:
    P("SUMMARY 失敗:%s" % e)
if a.grasp:
    P("\n===== 抓取段判讀(--grasp 1;rank %d、挑角 %.0f/%.0fmm、半徑係數 %.2f、掀 %.1fs、間距 %.1fmm、指面摩擦 %.1f)====="
      % (a.grasp_rank, a.pick_in_mm, a.pick_mm, a.arc_k, a.peel_t, a.gap_mm, a.ffric))
    GSUM = []
    for pl in GS["plans"]:
        ev = pl["ev"]; sd = pl["sd"]
        if pl.get("xm"):                                                      # [v2x]
            _u = pl["ut"]; _a = [_u.get(k_, {}) for k_ in ("pre", "after2", "after10")]; _r = ev.get("released", {})
            P("  [%s] [v2x] SUMMARY %s 拆膠帶後越線 %.0f%% | 鉸點 x %.1f L %.1f mm | 翻片角 放手前/2s/10s = %s° | 越線 %s%% | 杯頂覆蓋 %s%% | 片結束 越線 %.0f%% 杯頂覆蓋 %.0f%% 杯位移 %.1f mm 穿杯 %s"
              % (sd, pl["xlabel"], 100 * pl["cr_cut"], _u["hy"] * 1e3, _u["L"] * 1e3, *["/".join("%.0f" % q.get(k_, np.nan) if q else "-" for q in _a) for k_ in ("ang", "cross", "cov")],
                 100 * _r.get("cross", np.nan), 100 * _r.get("cov", np.nan), _r.get("mug", np.nan), _r.get("inmug", "-")))
            continue
        if "held" not in ev:
            P("  [%s] 沒跑完(ev %s)" % (sd, list(ev))); continue
        h = ev["held"]; pk = ev.get("pick", {}); rl = ev.get("released", h)
        rows_ = [r for r in GS["rows"] if r["sd"] == sd and pl.get("TP0", 1e9) - 1e-6 <= r["t"] <= pl["TR"] + 1e-6]
        slip_med = max([s_[1] for s_ in pl["slip"]] or [float("nan")]); slip_mx = max([s_[2] for s_ in pl["slip"]] or [float("nan")])
        mugmax = max([r["mug_d"] for r in GS["rows"] if r["sd"] == sd] + [h["mug_d"]])
        allr = [r for r in GS["rows"] if r["sd"] == sd]
        pen_mx = max([r["pen"] for r in allr] + [0]); inm_mx = max([r["inmug"] for r in allr] + [0]); inv_mx = max([r["inv"] for r in allr] + [0])
        ok = dict(grip=ev["grip"].get("n_att", ev["grip"]["n"]) >= 6, slip=(slip_med < 10.0), cross=h["cross"] >= 0.8, oth=h["oth_pct"] < 5.0, mug=mugmax < 5.0, inmug=inm_mx == 0)
        allok = all(ok.values())
        P("  [%s] 抓取點 v%d 位置 (%.1f,%.1f,%.1f) 坡度 %.1f° 空隙 %.1f | 挑角後 z %.1f→%.1f 空隙 %.1f→%.1f 相鄰層 >10mm %d(最大 %.1f)"
          % (sd, pl["v"], *pl["pick"]["p"], pl["pick"]["slope"], pl["pick"]["gap"], pk.get("z0", np.nan), pk.get("z1", np.nan),
             pk.get("gap0", np.nan), pk.get("gap1", np.nan), pk.get("adj_n10", -1), pk.get("adj_max", np.nan)))
        P("  [%s] 夾到 %d %s | 滑動(夾持中 中位/最大頂點)%.1f / %.1f mm %s | 越過折線 %.0f%%(整片 %.0f%%)%s;放開後 %.0f%% | 他片 >10mm %d(%.1f%%)最大 %.1f mm %s %s | 杯位移最大 %.1f mm %s | 自穿最多 %d 穿杯 %d %s 反轉 %d | 露出 %.0f%% → %.0f%%(放開後 %.0f%%)⇒ %s"
          % (sd, ev["grip"]["n"], "OK" if ok["grip"] else "NG", slip_med, slip_mx, "OK" if ok["slip"] else "NG", 100 * h["cross"], 100 * h["cross_all"],
             "OK" if ok["cross"] else "NG", 100 * rl["cross"], h["oth_n10"], h["oth_pct"], h["oth_max"], h["oth_side"], "OK" if ok["oth"] else "NG",
             mugmax, "OK" if ok["mug"] else "NG", pen_mx, inm_mx, "OK" if ok["inmug"] else "NG", inv_mx, 100 * (1 - pl["cov0"]),
             100 * (1 - h["rm"]["cov"]), 100 * (1 - rl["rm"]["cov"]), "PASS" if allok else "FAIL"))
        P("  [%s] ATTACH 綁 %s 點 | 越線 名義 %.0f%% / 實測彎折 %.0f%%(掀完停 2s)→ 放手後 名義 %.0f%% / 實測 %.0f%%"
          % (sd, ev["grip"].get("n_att", "-"), 100 * h["cross"], 100 * h.get("cross_h", np.nan), 100 * rl["cross"], 100 * rl.get("cross_h", np.nan)))
        if pl.get("hold") is not None:                                        # [drag]
            hv = pl["hold"]["vids"]; _hsd = dict(zip(*np.unique(GSIDE2[hv], return_counts=True))) if len(hv) else {}
            P("  [%s] HOLD 釘 %d 點(%s)| 他片 全部 held %.1f%% / released %.1f%% | 他片(扣壓住) held %.1f%% / released %.1f%% | 釘住點放開後最大位移 %.1f mm | 守衛 %s"
              % (sd, pl["hold"]["n"], _hsd, h["oth_pct"], rl["oth_pct"], h.get("oth_pct_free", np.nan), rl.get("oth_pct_free", np.nan),
                 rl.get("hold_d", np.nan), "有 t=%.2f" % ev["hold_guard"] if "hold_guard" in ev else "無"))
            pk = dict(pk, hold=dict(n=pl["hold"]["n"], sides=_hsd, oth_free_held=h.get("oth_pct_free"), oth_free_rel=rl.get("oth_pct_free"),
                                    hold_d_rel=rl.get("hold_d"), guard=ev.get("hold_guard")))
        if pl.get("ut"):                                                      # [table]
            _u = pl["ut"]; _a = [_u.get(k_, {}) for k_ in ("pre", "after2", "after10")]
            _ok = bool(_a[2] and _a[2]["ang"] < 45.0 and _a[2]["cross"] >= 80.0)
            P("  [%s] [table] SUMMARY 鉸點 y %.1f L %.1f mm | 翻片角 放手前/2s/10s = %s° | 越線 %s%% | 質心往外 %s mm | 他片 %s%% | 杯位移 %s mm | 穿杯 %s | 杯頂覆蓋 %s%% ⇒ %s(判準 10s 翻片角 < 45° 且越線 >= 80%%)"
              % (sd, _u["hy"] * 1e3, _u["L"] * 1e3, *["/".join("%.0f" % q.get(k_, np.nan) if q else "-" for q in _a) for k_ in ("ang", "cross", "oc", "oth", "mug", "inmug", "cov")],
                 "PASS" if _ok else "FAIL"))
            _u["PASS"] = _ok
        GSUM.append(dict(sd=sd, v=pl["v"], pick=pk, grip=ev["grip"]["n"], ut=pl.get("ut"), slip_med=slip_med, slip_max=slip_mx, cross=h["cross"],
                         cross_rel=rl["cross"], oth_n10=h["oth_n10"], oth_pct=h["oth_pct"], oth_max=h["oth_max"], mug=mugmax, pen=pen_mx,
                         inmug=inm_mx, inv=inv_mx, cov0=pl["cov0"], cov_held=h["rm"]["cov"], cov_rel=rl["rm"]["cov"], ok=ok, PASS=allok,
                         hinge=pl.get("hinge"), Lcur=pl.get("Lcur"), Lflat=pl.get("Lflat"), Rr=pl.get("Rr"), r0=pl.get("r0"),
                         th0=pl.get("th0"), th1=pl.get("th1"), R2=pl.get("R2"), events={k_: ev[k_]["t"] for k_ in ev if isinstance(ev[k_], dict) and "t" in ev[k_]},
                         TP0=pl.get("TP0"), TP1=pl.get("TP1"), S0=pl["S0"]))
    json.dump(dict(summary=GSUM, rows=GS["rows"]), open(os.path.join(a.out, "grasp.json"), "w"), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    P("  抓取段明細 → %s/grasp.json" % a.out)
if V2E:                                                                       # [v2] 膠帶 / 取出 各時間點
    P("\n===== [v2] SUMMARY(--tape_follow %d --takeout %d)=====" % (a.tape_follow, a.takeout))
    for k_, E in V2E.items():
        if k_ == "anc": continue
        P("  [v2] %-12s t=%7.2f 膠帶點相對杯 中位/最大 %.2f/%.2f mm | 布相對杯 中位/p90/最大 %.1f/%.1f/%.1f mm | 包裹形狀變化 中位/p90 %.1f/%.1f mm | 邊長比 窗內最大 %.3f | 杯頂覆蓋 %.0f%% | 穿杯 %d | 自穿 %d"
          % (k_, E["t"], E["tape_med"], E["tape_max"], E["cl_med"], E["cl_p90"], E["cl_max"], E["sh_med"], E["sh_p90"], E["lrmax"], 100 * E["cov"], E["inmug"], E["pen"]))
    json.dump({k_: {kk: vv for kk, vv in E.items() if kk not in ("loc", "P")} for k_, E in V2E.items()}, open(os.path.join(a.out, "v2.json"), "w"), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
np.savez_compressed(os.path.join(a.out, "wrap.npz"),
                    sheet_mid=(Pf[BOT] + Pf[TOP]) / 2, tet=Pf, tets=TETS, flat=FLAT, mug=MWf, mugrest=V,
                    fold_end_tet=SNAP["fold_end"][0] if "fold_end" in SNAP else Pf,
                    **{"snap_" + k_: v_[0] for k_, v_ in SNAP.items()},
                    **{"snapmug_" + k_: v_[1] for k_, v_ in SNAP.items()},
                    traj_t=np.array(TRAJ_T), traj_tet=np.array(TRAJ_P), traj_mug=np.array(TRAJ_M))
P("npz → %s/wrap.npz" % a.out)
LOG.close()
sim.close()
