"""lid_test.py — 蓋子用滑鼠拉得開嗎(UI 路徑)。力量式拖曳(forceGrab=True, pickingForce=PF)從每片蓋子正上方抓住、
往上提 15 cm,量拉著時的角度;放手 2 s 再量。結果寫到 lid_<scene>_pf<PF>[_mode].txt。

  cd sim
  /isaac-sim/python.sh lid_test.py ../scene_final_phys.usd 100 latch    # 預設模式:彈簧 + lid_latch.py
  /isaac-sim/python.sh lid_test.py ../scene_final_phys.usd 100 spring   # 只有彈簧(LID_LATCH=0)
  /isaac-sim/python.sh lid_test.py ../scene_final_phys.usd 100 crease   # crease_hold_ui.py(彈塑性摺痕)
"""
import os, sys, math
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT","1")
SCENE=sys.argv[1]; PF=float(sys.argv[2]); MODE=sys.argv[3] if len(sys.argv)>3 else ""; CREASE=MODE=="crease"; LATCH=MODE=="latch"
from isaacsim import SimulationApp
sim=SimulationApp({"headless":True,"extra_args":["--/persistent/physics/enableDeformableBeta=true"]})
import carb, numpy as np, omni.usd, omni.timeline
import omni.physx.bindings._physx as pxb
s_=carb.settings.get_settings(); s_.set(pxb.SETTING_ENABLE_DEFORMABLE_BETA,True); s_.set_bool("/physics/updateToUsd",True)
from omni.physx import get_physx_interface
from omni.physx.bindings._physx import PhysicsInteractionEvent as PIE
from isaacsim.core.prims import RigidPrim
from pxr import Usd, UsdGeom, Gf
tag="%s_pf%d%s"%(os.path.basename(SCENE).replace(".usd",""),int(PF),"_"+MODE if MODE else "")
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)),"logs"),exist_ok=True)
OUT=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"logs","lid_%s.txt"%tag),"w")
P=lambda *s:(OUT.write(" ".join(str(x) for x in s)+"\n"),OUT.flush())
omni.usd.get_context().open_stage(SCENE)
for _ in range(30): sim.update()
st=omni.usd.get_context().get_stage(); BOX="/World/Packed/Box"
if CREASE:
    p=os.path.join(os.path.dirname(os.path.abspath(__file__)),"crease_hold_ui.py"); exec(compile(open(p).read(),p,"exec"),globals())
if LATCH:
    p=os.path.join(os.path.dirname(os.path.abspath(__file__)),"lid_latch.py"); exec(compile(open(p).read(),p,"exec"),globals())
s_.set_bool("/physics/mouseInteractionEnabled",True); s_.set_bool("/physics/mouseGrab",True); s_.set_bool("/physics/mouseGrabIgnoreInvisible",True)
s_.set_bool("/physics/forceGrab",True); s_.set_float("/physics/pickingForce",PF)
tl=omni.timeline.get_timeline_interface(); tl.play()
for _ in range(90): sim.update()
LIDS=RigidPrim(prim_paths_expr=BOX+"/f[xy][pn]",name="L"); LIDS.initialize()
BASE=RigidPrim(prim_paths_expr=BOX+"/base",name="B"); BASE.initialize()
order=[str(p).rsplit("/",1)[-1] for p in LIDS.prim_paths]
def qmul(a,b):
    w1,x1,y1,z1=a; w2,x2,y2,z2=b
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2,w1*x2+x1*w2+y1*z2-z1*y2,w1*y2-x1*z2+y1*w2+z1*x2,w1*z2+x1*y2-y1*x2+z1*w2])
def qc(q): return np.array([q[0],-q[1],-q[2],-q[3]])
_,q0L=[np.array(x,float) for x in LIDS.get_world_poses()]; p0B,q0B=[np.array(x,float)[0] for x in BASE.get_world_poses()]
REL0=[qmul(qc(q0B),q0L[i]) for i in range(len(order))]
def ang():
    _,qL=[np.array(x,float) for x in LIDS.get_world_poses()]; _,qB=[np.array(x,float)[0] for x in BASE.get_world_poses()]
    o=[]
    for i in range(len(order)):
        rr=qmul(qc(REL0[i]),qmul(qc(qB),qL[i])); rr=-rr if rr[0]<0 else rr; o.append(math.degrees(2*math.atan2(rr[1],rr[0])))
    return np.array(o)
bc=UsdGeom.BBoxCache(Usd.TimeCode.Default(),["default","render"])
px=get_physx_interface()
P("scene=%s pickingForce=%.0f mode=%s"%(os.path.basename(SCENE),PF,MODE or "spring"))
for n in ["fyp","fyn","fxp","fxn"]:
    r=bc.ComputeWorldBound(st.GetPrimAtPath(BOX+"/"+n)).ComputeAlignedRange(); c=(np.array(r.GetMin())+np.array(r.GetMax()))/2
    o=np.array([c[0],c[1],0.6]); d=carb.Float3(0,0,-1)
    px.update_interaction(carb.Float3(*o),d,PIE.MOUSE_DRAG_BEGAN); sim.update()
    i=order.index(n); amax=0.0
    for k in range(150):
        u=(k+1)/150; s=u*u*(3-2*u)
        px.update_interaction(carb.Float3(*(o+np.array([0,0,0.15*s]))),d,PIE.MOUSE_DRAG_CHANGED); sim.update()
        amax=max(amax,abs(ang()[i]))
    held=ang()[i]
    px.update_interaction(carb.Float3(*(o+np.array([0,0,0.15]))),d,PIE.MOUSE_DRAG_ENDED)
    for _ in range(120): sim.update()
    rel=ang()[i]; pB=np.array(BASE.get_world_poses()[0],float)[0]
    P("蓋 %s:拉著時 %+6.1f°(過程最大 %5.1f°) | 放手 2 s 後 %+6.1f° | 箱底位移 %s mm | 其他蓋 %s"%(n,held,amax,rel,np.round((pB-p0B)*1e3,1)," ".join("%s=%+.0f"%(m,v) for m,v in zip(order,ang()) if m!=n)))
    # 把蓋子推回去(用同樣的拖曳往下壓)再繼續下一片
    if abs(rel)>10:
        r=bc.ComputeWorldBound(st.GetPrimAtPath(BOX+"/"+n)).ComputeAlignedRange(); c=(np.array(r.GetMin())+np.array(r.GetMax()))/2
        o=np.array([c[0],c[1],0.6]); px.update_interaction(carb.Float3(*o),d,PIE.MOUSE_DRAG_BEGAN); sim.update()
        for k in range(120):
            px.update_interaction(carb.Float3(*(o-np.array([0,0,0.20*(k+1)/120]))),d,PIE.MOUSE_DRAG_CHANGED); sim.update()
        px.update_interaction(carb.Float3(*(o-np.array([0,0,0.20]))),d,PIE.MOUSE_DRAG_ENDED)
        for _ in range(60): sim.update()
        P("   推回後 %s=%+.1f°"%(n,ang()[i]))
OUT.close(); sim.close()
