import re,sys,glob,os
sys.path.insert(0,'.'); import jitter
for n in sys.argv[1:]:
    L=open('damp/%s/wrap_vol.log'%n).read()
    s=jitter.summarize('damp/%s/wrap.npz'%n, jitter.parse_wins("3.5:4,7:7.5,10.5:11,14:14.5"),(17.0,18.1))
    bb=re.search(r'四折後.*?bbox (\S+)',L).group(1); bb2=re.search(r'入箱前 bbox (\S+)',L).group(1)
    mx=re.search(r'全程最大 自穿 (\d+) 布穿杯 (\d+) 反轉 (\d+) 邊長比 (\[\S+\])',L).groups()
    tips=re.findall(r'折 (\w+) 尖端.*?along (\S+) z (\S+) mm',L)
    print("| %s | %.3f | %.3f | %.3f | %.3f | %s | %s | %s | %s | %s | %s |"%(n,s['hold_rms'],s['hold_hf'],s['rest']['rms'],s['rest']['hf'],bb,bb2,mx[0],mx[2],mx[3],"; ".join("%s z%s"%(a,c) for a,b,c in tips)))
