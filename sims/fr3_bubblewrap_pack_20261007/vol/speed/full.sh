#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
W() { until ! pgrep -f "wrap_vol.py --sheet_mm 500" >/dev/null && ! pgrep -f peel_with_cloth >/dev/null; do sleep 30; done; }
W; speed/run.sh speed/a_s64 all --solver 64 --vid_every 4 --vid_res 640x360
W; speed/run.sh speed/a_dt120 all --dt 0.008333333333333333 --vid_every 4 --vid_res 640x360
W; speed/run.sh speed/a_dt120s64 all --dt 0.008333333333333333 --solver 64 --vid_every 4 --vid_res 640x360
date > speed/full.done
