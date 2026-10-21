#!/bin/bash
# usage: table/cut_short.sh IN.mp4 OUT.mp4   桌面掀 yn(時間表同 table/run.sh):四折+收耳 0.5–17.5 ×8、放錨點(膠帶留著)17.5–29.9 ×8、
#        挑角/合指 29.9–39.6 ×6、抬起+翻 180° 39.6–48.6 ×2、停 48.6–50.6 ×2、放手 50.6–52.6 ×1、放手後 52.6–60.6 ×4(約 14 s)
IN=$1; OUT=$2
ffmpeg -loglevel error -y -i "$IN" -filter_complex "\
[0:v]trim=0.5:17.5,setpts=(PTS-STARTPTS)/8[a];\
[0:v]trim=17.5:29.9,setpts=(PTS-STARTPTS)/8[b];\
[0:v]trim=29.9:39.6,setpts=(PTS-STARTPTS)/6[c];\
[0:v]trim=39.6:48.6,setpts=(PTS-STARTPTS)/2[d];\
[0:v]trim=48.6:50.6,setpts=(PTS-STARTPTS)/2[e];\
[0:v]trim=50.6:52.6,setpts=PTS-STARTPTS[f];\
[0:v]trim=52.6:60.6,setpts=(PTS-STARTPTS)/4[g];\
[a][b][c][d][e][f][g]concat=n=7:v=1:a=0,fps=30[v]" -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 23 "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
