import numpy as np, sys, re
# PEEL4 比對:yn 片在 掀完/放手前/放手後0.5s/2s 的 z 分佈、質心、貼蓋/貼壁外側(箱局部 = world - 箱位移(0,200,100))
OFF=np.r_[0,0.2,0.1]; WALL=-0.1135; LIDTOP=0.1295
for d in sys.argv[1:]:
    z=np.load(d+'/wrap.npz'); F=z['flat']; yn=(F[:,1]-F[:,1].mean())< -0.0715
    log=open(d+'/wrap_vol.log').read()
    tp=float(re.search(r'★ t=([\d.]+) \[yn\] peeled',log).group(1)); th=float(re.search(r'★ t=([\d.]+) \[yn\] held',log).group(1))
    T=z['traj_t']; X=z['traj_tet']
    up=[(float(m[0]),float(m[1]),float(m[2]),float(m[3])) for m in re.findall(r'G\[yn\] t=\s*([\d.]+) yn (?:PEEL|hold|release)[^上]*上指 \(\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)\)',log)]
    print('==',d)
    print('  夾爪 y,z (掀~放手):', ' '.join('%.1f:%.0f/%.0f'%(t,y,zz) for t,x,y,zz in up if t<=th+1.0))
    for nm,t in (('掀完',tp),('放手前',th),('放手+0.5s',th+0.5),('放手+2s',th+2.0),('放手+5s',th+5.0)):
        i=np.argmin(abs(T-t)); P=(X[i][yn]-OFF)*1e3
        out=P[:,1]<WALL*1e3
        onlid=(P[:,1]<WALL*1e3-3)&(P[:,2]<LIDTOP*1e3+12)
        wallo=(P[:,1]<WALL*1e3)&(P[:,1]>WALL*1e3-8)&(P[:,2]<LIDTOP*1e3)
        print('  %-9s t=%.2f 質心 y=%.0f z=%.0f | z p10/50/90 %.0f/%.0f/%.0f | 壁外 %.0f%% | 貼蓋(y<-116.5,z<141.5) %d 點 | 貼壁外側 %d 點 | 最外 y %.0f'%(nm,T[i],P[:,1].mean(),P[:,2].mean(),*np.percentile(P[:,2],[10,50,90]),100*out.mean(),onlid.sum(),wallo.sum(),P[:,1].min()))
