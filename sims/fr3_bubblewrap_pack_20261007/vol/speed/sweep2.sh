#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
until [ -f speed/sweep.done ]; do sleep 20; done
until ! pgrep -f "wrap_vol.py --sheet_mm 500" >/dev/null && ! pgrep -f peel_with_cloth >/dev/null; do sleep 30; done
speed/run.sh speed/f_fast fold --fast_pts 1
speed/run.sh speed/f_123 fold --vid_every 4 --vid_res 640x360 --fast_pts 1
date > speed/sweep2.done
