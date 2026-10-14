#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
until ! pgrep -f "wrap_vol.py --sheet_mm 500" >/dev/null && ! pgrep -f peel_with_cloth >/dev/null; do sleep 30; done
date > speed/sweep.start
R=speed/run.sh
$R speed/f_base fold
$R speed/f_ve4 fold --vid_every 4
$R speed/f_res640 fold --vid_res 640x360
$R speed/f_fast fold --fast_pts 1
$R speed/f_123 fold --vid_every 4 --vid_res 640x360 --fast_pts 1
$R speed/f_dt120 fold --dt 0.008333333333333333
$R speed/f_s64 fold --solver 64
$R speed/f_dt120s64 fold --dt 0.008333333333333333 --solver 64
date > speed/sweep.done
