#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
until [ -f speed/full2.done ]; do sleep 20; done
W() { until ! pgrep -f "wrap_vol.py --sheet_mm 500" >/dev/null && ! pgrep -f peel_with_cloth >/dev/null; do sleep 30; done; }
( while true; do echo "$(date +%T) $(pgrep -af 'python3 .*(wrap_vol|peel_with)' | grep -o '\-\-out [^ ]*' | tr '\n' ' ')"; sleep 30; done ) > speed/concurrency.log &
CP=$!
W; speed/run.sh speed/a_base all --vid_every 4 --vid_res 640x360
W; speed/run.sh speed/a_s64b all --solver 64 --vid_every 4 --vid_res 640x360
kill $CP
date > speed/full3.done
