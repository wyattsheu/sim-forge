#!/bin/bash
# usage: extract5/cut_short.sh IN.mp4 OUT.mp4   (同 EXTRACT2/3:yn 60–68 ×2.5、手2 68–73 ×2、yp 92–102 ×2.5、取杯 117–130 ×1.5)
IN=$1; OUT=$2
ffmpeg -loglevel error -y -i "$IN" -filter_complex "\
[0:v]trim=60:68,setpts=(PTS-STARTPTS)/2.5[a];\
[0:v]trim=68:73,setpts=(PTS-STARTPTS)/2[b];\
[0:v]trim=92:102,setpts=(PTS-STARTPTS)/2.5[c];\
[0:v]trim=117:129.6,setpts=(PTS-STARTPTS)/1.5[d];\
[a][b][c][d]concat=n=4:v=1:a=0,fps=30[v]" -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 23 "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
