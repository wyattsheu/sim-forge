import numpy as np, sys
# 幾何驗證:yn 片(flat y < -71.5mm)在 held / released 時,質心相對箱壁外緣 y=-113.5 與 z
for d in sys.argv[1:]:
    z=np.load(d+'/wrap.npz'); F=z['flat']; Fy=F[:,1]-F[:,1].mean()
    yn=Fy< -0.0715
    out=[]
    for k in ('peeled','held','released'):
        P=z['snap_g_yn_'+k]; M=z['snapmug_g_yn_'+k]; c=np.r_[np.median(M[:,:2],0)]; zb=M[:,2].min()
        L=P[yn]-np.r_[c,zb]
        out.append('%s: 質心 y=%.0f z=%.0f | 箱外(y<-113.5) %.0f%% | 最外 y=%.0f' % (k, L[:,1].mean()*1e3, L[:,2].mean()*1e3, 100*(L[:,1]<-0.1135).mean(), L[:,1].min()*1e3))
    print(d, ' ; '.join(out))
