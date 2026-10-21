#!/bin/bash
# [v2x] usage: v2/cut_x.sh OUT.mp4 "標籤|v2/x/NAME/k/wrap.mp4" ...(續跑影片,影片 0 s = 存檔點 t 122.0)
#   每格剪 x 片 + 取杯段 t 124–193(影片 2–71 s)×4 → 約 17 s;2 欄排(個數不夠補黑),每格 640×360 左上角標籤
OUT=$1; shift
FONT=/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
IN=(); F=""; n=0
for x in "$@"; do lab=${x%%|*}; f=${x#*|}; IN+=(-i "$f")
  F+="[$n:v]trim=2:71,setpts=(PTS-STARTPTS)/4,fps=30,scale=640:360,drawtext=fontfile=$FONT:text='$lab':x=8:y=8:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.6[v$n];"; n=$((n+1)); done
[ $((n % 2)) = 1 ] && { F+="color=black:s=640x360:r=30:d=17.25[v$n];"; n=$((n+1)); }
L=""; LAY=""; for i in $(seq 0 $((n-1))); do L+="[v$i]"; c=$((i % 2)); r=$((i / 2)); LAY+="$([ $c = 0 ] && echo 0 || echo w0)_$([ $r = 0 ] && echo 0 || { s=h0; for j in $(seq 2 $r); do s+="+h0"; done; echo $s; })|"; done
ffmpeg -loglevel error -y "${IN[@]}" -filter_complex "${F}${L}xstack=inputs=$n:layout=${LAY%|}:shortest=1[o]" -map "[o]" -c:v libx264 -pix_fmt yuv420p -crf 24 "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
