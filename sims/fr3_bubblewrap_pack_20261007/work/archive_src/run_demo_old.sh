#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/work
P=/isaac-sim/python.sh; S=wrap_sim_old.py
C="--tex bubble_normal.png --wrapsim --young 2e4 --bend 4 --thick 0.004 --sheet_mm 400 --layer_mm 5 --cam_ref 0.586"
V="--hold_mm 6 --tip_over_mm 0"
wait_gpu(){ while [ $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) -gt 22000 ]; do sleep 20; done; }
run(){ wait_gpu; o=$1; shift; rm -rf $o; $P $S $C "$@" --out $o > $o.stdout 2>&1; [ -f $o/wrap.npz ] || { echo "FAIL $o"; exit 1; }; }
run dm_c1 $V --wrap_edge --wrap_n 2
run dm_c2 $V --stage2 --init_npz dm_c1/wrap.npz
run dm_c3 --init_npz dm_c2/wrap.npz --press6 180,190,115 --no_anchor --no_sleepy --press_off 6
run dm_box --init_npz dm_c3/wrap.npz --carton carton_w131.usd --close_lid --lid_span 4 --no_anchor
run dm_mb --init_npz dm_box/wrap.npz --carton carton_w131.usd --no_anchor --in_box_already --no_ground_collision --base_collider_pad 0.02 --movebox 0,0.20,0.10 --move_t 6 --move_wait 2 --settle 4
: > videos/demo_old_list.txt
for d in dm_c1 dm_c2 dm_c3 dm_box dm_mb; do ffmpeg -y -loglevel error -ss 0.5 -i $d/wrap.mp4 -c:v libx264 -pix_fmt yuv420p -crf 20 $d/trim.mp4; echo "file '$PWD/$d/trim.mp4'" >> videos/demo_old_list.txt; done
ffmpeg -y -loglevel error -f concat -safe 0 -i videos/demo_old_list.txt -c copy videos/DEMO_old_order_sheet400_v2.mp4
echo DONE
for d in dm_c1 dm_c2 dm_c3 dm_box dm_mb; do echo "$d $(grep '布 bbox' $d/wrap_sim.log | tail -1 | sed -E 's/.*布 bbox//') | $(grep -oE 'S1 自穿模.*次' $d/wrap_sim.log)"; done
grep -A4 '真的入箱了嗎' dm_box/wrap_sim.log | head -5; grep '⇒ 結論' dm_mb/wrap_sim.log
