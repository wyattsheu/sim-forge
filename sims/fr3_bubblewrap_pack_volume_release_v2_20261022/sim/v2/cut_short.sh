#!/bin/bash
# usage: v2/cut_short.sh IN.mp4 OUT.mp4   v2 完整流程短版(時間表同 v2/run.sh,約 23 s):
#   關蓋 18.5–26.5 ×8 → 搬箱 28.9–34.9 ×6 → 開蓋 36.9–42.9 ×6 → 手 2 取出整包到桌面 45.9–59.6 ×4 →
#   手 1 掀 yn 60.6–83.3 ×6 → 掀 yp 91.3–114.0 ×6 → 手 2 夾住杯 + 拆 xn 膠帶(自己攤開)122.0–128.6 ×3 → 拆 xp 膠帶 155.0–159.4 ×3 → 手 2 抬杯放旁邊 184.4–195.3 ×3
IN=$1; OUT=$2
S=(18.5:26.5:8 28.9:34.9:6 36.9:42.9:6 45.9:59.6:4 60.6:83.3:6 91.3:114.0:6 122.0:128.6:3 155.0:159.4:3 184.4:195.3:3)
F=""; L=""; i=0
for s in "${S[@]}"; do IFS=: read a b k <<< "$s"; F+="[0:v]trim=$a:$b,setpts=(PTS-STARTPTS)/$k[s$i];"; L+="[s$i]"; i=$((i+1)); done
ffmpeg -loglevel error -y -i "$IN" -filter_complex "${F}${L}concat=n=$i:v=1:a=0,fps=30[v]" -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 23 "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
