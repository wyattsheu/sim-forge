import numpy as np, sys, re
OFF=np.r_[0,0.2,0.1]
for d in sys.argv[1:]:
    z=np.load(d+'/wrap.npz'); F=z['flat']; Fy=(F[:,1]-F[:,1].mean())*1e3; yn=Fy< -71.5
    log=open(d+'/wrap_vol.log').read(); th=float(re.search(r'★ t=([\d.]+) \[yn\] held',log).group(1))
    T=z['traj_t']; X=z['traj_tet']
    print('==',d)
    for nm,t in (('放手前',th),('+0.5',th+0.5),('+2',th+2)):
        P=(X[np.argmin(abs(T-t))]-OFF)*1e3
        # 沿 flat y(折線 -71.5 → 尖端 -250)每 20mm 一帶:該帶頂點的 y、z 中位
        s=[]
        for a in range(-80,-250,-20):
            m=yn&(Fy<=a)&(Fy>a-20)
            s.append('%d:(%.0f,%.0f)'%(-a,np.median(P[m,1]),np.median(P[m,2])))
        print('  %-5s'%nm,' '.join(s))
