#!/bin/bash
# usage: matsweep/cut_short.sh IN.mp4 OUT.mp4   掀 → 放手 → 放手後 10 s:合指 54–56.6 ×2、掀 56.6–66.1 ×4、停 66.1–68.1 ×2、放手 68.1–70.1 ×1、70.1–78.6 ×1.5
IN=$1; OUT=$2
ffmpeg -loglevel error -y -i "$IN" -filter_complex "\
[0:v]trim=54:56.6,setpts=(PTS-STARTPTS)/2[a];\
[0:v]trim=56.6:66.1,setpts=(PTS-STARTPTS)/4[b];\
[0:v]trim=66.1:68.1,setpts=(PTS-STARTPTS)/2[c];\
[0:v]trim=68.1:70.1,setpts=PTS-STARTPTS[d];\
[0:v]trim=70.1:78.6,setpts=(PTS-STARTPTS)/1.5[e];\
[a][b][c][d][e]concat=n=5:v=1:a=0,fps=30[v]" -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 23 "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
