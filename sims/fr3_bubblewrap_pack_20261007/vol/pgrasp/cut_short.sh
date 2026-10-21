#!/bin/bash
# usage: pgrasp/cut_short.sh IN.mp4 OUT.mp4   寬指純摩擦:下指滑入布下 48–51.4 ×2、上指降 + 合指 51.4–56.6 ×4、掀 56.6–66.1 ×4、停 66.1–68.1 ×2、放手 68.1–70.1 ×1、放手後 70.1–78.6 ×3(約 11 s)
IN=$1; OUT=$2
ffmpeg -loglevel error -y -i "$IN" -filter_complex "\
[0:v]trim=48:51.4,setpts=(PTS-STARTPTS)/2[a];\
[0:v]trim=51.4:56.6,setpts=(PTS-STARTPTS)/4[b];\
[0:v]trim=56.6:66.1,setpts=(PTS-STARTPTS)/4[c];\
[0:v]trim=66.1:68.1,setpts=(PTS-STARTPTS)/2[d];\
[0:v]trim=68.1:70.1,setpts=PTS-STARTPTS[e];\
[0:v]trim=70.1:78.6,setpts=(PTS-STARTPTS)/3[f];\
[a][b][c][d][e][f]concat=n=6:v=1:a=0,fps=30[v]" -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 23 "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
