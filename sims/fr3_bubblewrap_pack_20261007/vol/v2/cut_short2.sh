#!/bin/bash
# [v2x2] usage: v2/cut_short2.sh IN.mp4 OUT.mp4   v2.1 完整流程短版(E + 寬指 300 + H;時間表同 v2/run.sh,約 24 s):
#   關蓋 18.5–26.5 ×8 → 搬箱 28.9–34.9 ×6 → 開蓋 36.9–42.9 ×6 → 手 2 取出整包 45.9–59.6 ×4 → 掀 yn 60.6–83.3 ×6 → 掀 yp 91.3–114.0 ×6 →
#   掀 xn(手 2 鬆手抬開)122.0–148.0 ×8 → 掀 xp 152.7–178.5 ×8 → 手 2 重夾、抬杯放旁邊 182.1–195.3 ×4
IN=$1; OUT=$2
S=(18.5:26.5:8 28.9:34.9:6 36.9:42.9:6 45.9:59.6:4 60.6:83.3:6 91.3:114.0:6 122.0:148.0:8 152.7:178.5:8 182.1:195.3:4)
F=""; L=""; i=0
for s in "${S[@]}"; do IFS=: read a b k <<< "$s"; F+="[0:v]trim=$a:$b,setpts=(PTS-STARTPTS)/$k[s$i];"; L+="[s$i]"; i=$((i+1)); done
ffmpeg -loglevel error -y -i "$IN" -filter_complex "${F}${L}concat=n=$i:v=1:a=0,fps=30[v]" -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 23 "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
