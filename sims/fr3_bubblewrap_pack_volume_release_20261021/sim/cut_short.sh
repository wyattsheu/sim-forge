#!/bin/bash
# usage: extract6/cut_short.sh IN.mp4 OUT.mp4   三次合指都用 1x:手1 yn 合指 52–54 ×1、yn 掀 54–64 ×4、手2 下降+合指 64–66.2 ×1、
#        yp 夾+掀 88–102 ×4、取杯 下降+合指+抬 117.3–120 ×1、出箱+放下 120–130.5 ×2
IN=$1; OUT=$2
ffmpeg -loglevel error -y -i "$IN" -filter_complex "\
[0:v]trim=52:54,setpts=PTS-STARTPTS[a];\
[0:v]trim=54:64,setpts=(PTS-STARTPTS)/4[b];\
[0:v]trim=64:66.2,setpts=PTS-STARTPTS[c];\
[0:v]trim=88:102,setpts=(PTS-STARTPTS)/4[d];\
[0:v]trim=117.3:120,setpts=PTS-STARTPTS[e];\
[0:v]trim=120:130.5,setpts=(PTS-STARTPTS)/2[f];\
[a][b][c][d][e][f]concat=n=6:v=1:a=0,fps=30[v]" -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 23 "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
