#!/bin/bash
# 用法: bash work/make_demo_videos.sh   (純 ffmpeg；來源不存在或損毀則跳過並警告)
R=/isaac-sim/test_scripts/manip_fr3/handoff_20260929
O=$R/work/videos/demo; T=$O/tmp; F=$R/work/yield/fonts/NotoSansTC.ttf
mkdir -p $T; cd $R; rm -f $T/*.mp4
ENC="-r 30 -s 1280x720 -pix_fmt yuv420p -c:v libx264 -crf 20 -an"
VF="scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1"
dur(){ ffprobe -v error -show_entries format=duration -of csv=p=0 "$1" 2>/dev/null | head -1; }
ok(){ [ -f "$1" ] && [ -n "$(dur "$1")" ] && [[ "$(dur "$1")" =~ ^[0-9.]+$ ]]; }
title(){ # out text
  ffmpeg -v error -y -f lavfi -i "color=c=0x1b2a3a:s=1280x720:d=2:r=30" -vf "drawtext=fontfile=$F:text='$2':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2" $ENC $1; }
seg(){ # out src ss len "a:b:label|a:b:label"  (len=0 全段)
  local out=$1 src=$2 ss=$3 len=$4 labs=$5 vf=$VF
  if ! ok "$src"; then echo "警告: 跳過 $src (不存在或未完成)" >&2; return 1; fi
  while IFS= read -r l; do IFS=: read a b txt <<<"$l"
    vf="$vf,drawtext=fontfile=$F:text='$txt':fontcolor=white:fontsize=34:box=1:boxcolor=black@0.55:boxborderw=10:x=20:y=20:enable='between(t\,$a\,$b)'"; done < <(tr '|' '\n' <<<"$labs")
  local tl=(); [ "$len" != 0 ] && tl=(-t $len)
  ffmpeg -v error -y -ss $ss -i "$src" "${tl[@]}" -vf "$vf" $ENC $out; }
blk(){ [ -f $T/black.mp4 ] || ffmpeg -v error -y -f lavfi -i "color=c=black:s=1280x720:d=1:r=30" $ENC $T/black.mp4; }
cat_(){ local out=$1; shift; : > $T/l.txt; for f in "$@"; do [ -f $f ] && echo "file '$f'" >> $T/l.txt; done
  ffmpeg -v error -y -f concat -safe 0 -i $T/l.txt $ENC $out; }

V=$R/work/videos; D=$R/vol
title $T/t1.mp4 "surface 版：泡泡紙包杯 → 入箱 → 搬箱 → 開蓋"
seg $T/s1.mp4 $V/DEMO_new_order_sheet400.mp4 0 0 "0:30:折疊|30:46:入箱關蓋|46:56:搬箱|56:63:開蓋"
cat_ $O/DEMO_1_surface_pipeline.mp4 $T/t1.mp4 $T/s1.mp4

title $T/t2.mp4 "volume 版：四折 → 收耳 → 入箱 → 搬箱 → 開蓋"
seg $T/s2.mp4 $D/videos/VOL_soft_best.mp4 0 0 "0:14:四折|14:17:收耳|17:27:入箱關蓋|27:35:搬箱|35:46:開蓋"
cat_ $O/DEMO_2_volume_pipeline.mp4 $T/t2.mp4 $T/s2.mp4

title $T/t3.mp4 "夾爪夾布：摩擦 vs 綁定、surface vs volume"
seg $T/p1.mp4 $R/deck/figs/11_peel_side_by_side.mp4 0 12 "0:12:夾爪探針 掀角（摩擦）"
seg $T/p2.mp4 $R/deck/figs/12_grip_side_by_side.mp4 0 12 "0:12:夾爪探針 夾持（摩擦）"
seg $T/p3.mp4 $D/grip_attach/videos/g1a_best_p16_both_g4.mp4 0 12 "0:12:綁定夾持 g1a（雙邊）"
seg $T/p4.mp4 $D/grip_attach/videos/g2ab_G2a_noW.mp4 0 12 "0:12:綁定夾持 g2ab（無 W）"
cat_ $O/DEMO_3_grasp_probes.mp4 $T/t3.mp4 $T/p1.mp4 $T/p2.mp4 $T/p3.mp4 $T/p4.mp4

title $T/t4.mp4 "6 軸雙臂：開蓋 + 掀包材乾跑 → 有布 → 綁定掀"
seg $T/a1.mp4 $R/arm/videos/arm_peel_dry_v2.mp4 0 20 "0:20:雙臂乾跑 v2（無布）"
seg $T/a2.mp4 $R/arm/cloth/videos/dry_with_cloth.mp4 0 15 "0:15:手臂 + 布 乾跑"
seg $T/a3.mp4 $R/arm/cloth/videos/peel_v3_best.mp4 0 0 "0:99:手臂真掀 v3（Lula 重解，綁定 24 點，掀 64%，放手留 56%）"
cat_ $O/DEMO_4_arm.mp4 $T/t4.mp4 $T/a1.mp4 $T/a2.mp4 $T/a3.mp4

title $T/t5.mp4 "整包掀開：surface vs volume"
seg $T/w1.mp4 $V/SURF_grasp_attach.mp4 0 0 "0:20:surface 整包綁定掀"
W=$D/grasp/out_ga2/wrap.mp4; ws=0
if ok $W; then ws=$(awk -v d=$(dur $W) 'BEGIN{s=d-35;print (s<0?0:s)}'); fi
seg $T/w2.mp4 $W $ws 35 "0:35:volume 整包綁定掀"
cat_ $O/DEMO_5_wrap_peel.mp4 $T/t5.mp4 $T/w1.mp4 $T/w2.mp4

title $T/t6.mp4 "雙手掀開並拿住 → 取杯（volume）"
seg $T/x1.mp4 $D/videos/DEMO_twohand_extract_short.mp4 0 0 "0:20:掀 yn → 第二手接住 → 掀 yp → 取杯"
seg $T/x2.mp4 $D/videos/VARIANTS_grid.mp4 0 0 "0:8:24 種折序並排"
cat_ $O/DEMO_6_twohand_extract.mp4 $T/t6.mp4 $T/x1.mp4 $T/x2.mp4

blk
cat_ $O/DEMO_ALL.mp4 $O/DEMO_1_surface_pipeline.mp4 $T/black.mp4 $O/DEMO_2_volume_pipeline.mp4 $T/black.mp4 $O/DEMO_3_grasp_probes.mp4 $T/black.mp4 $O/DEMO_4_arm.mp4 $T/black.mp4 $O/DEMO_5_wrap_peel.mp4 $T/black.mp4 $O/DEMO_6_twohand_extract.mp4

{ echo "# DEMO 索引"; echo; echo "| 成品 | 長度(s) | 來源 / 段 |"; echo "|---|---|---|"
 row(){ echo "| $1 | $(printf %.1f $(dur $O/$1)) | $2 |"; }
 row DEMO_1_surface_pipeline.mp4 "work/videos/DEMO_new_order_sheet400.mp4；標題 0-2；折疊 2-32、入箱關蓋 32-48、搬箱 48-58、開蓋 58-64"
 row DEMO_2_volume_pipeline.mp4 "vol/videos/VOL_soft_best.mp4；標題 0-2；四折 2-16、收耳 16-19、入箱關蓋 19-29、搬箱 29-37、開蓋 37-47"
 row DEMO_3_grasp_probes.mp4 "deck/figs/11、12 side_by_side；g1a_best_p16_both_g4；g2ab_G2a_noW（各 ≤12 s，標題 2 s）"
 row DEMO_4_arm.mp4 "arm_peel_dry_v2（0-20s）；dry_with_cloth（15s）；peel_v3_best（v3 u0.60）"
 row DEMO_5_wrap_peel.mp4 "SURF_grasp_attach（來源僅 19 s，故取全段）；vol/grasp/out_ga2/wrap.mp4（存在才納入，取最後 35s）"
 row DEMO_6_twohand_extract.mp4 "vol/videos/DEMO_twohand_extract_short.mp4（X3，18 s）；VARIANTS_grid.mp4（6 s）"
 row DEMO_ALL.mp4 "A~F 串接，段間 1 s 黑幕"; } > $O/DEMO_INDEX.md
rm -rf $T; ls -l $O
