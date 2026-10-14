#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
W() { until ! pgrep -f "python3 wrap_vol.py" >/dev/null && ! pgrep -f "python3 .*peel_with_cloth" >/dev/null; do sleep 30; done; }
( while true; do echo "$(date +%T) $(pgrep -af 'python3 .*(wrap_vol|peel_with)' | grep -o '\-\-out [^ ]*' | tr '\n' ' ')"; sleep 30; done ) > speed/concurrency.log &
CP=$!
W; speed/run.sh speed/a_base all --vid_every 4 --vid_res 640x360
W; speed/run.sh speed/f_123 fold --vid_every 4 --vid_res 640x360 --fast_pts 1
W; speed/run.sh speed/a_s64b all --solver 64 --vid_every 4 --vid_res 640x360
W; speed/run.sh speed/a_dt120b all --dt 0.008333333333333333 --vid_every 4 --vid_res 640x360
kill $CP
date > speed/q.done
