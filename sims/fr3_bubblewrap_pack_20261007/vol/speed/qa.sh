#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
speed/run.sh speed/a_base all --vid_every 4 --vid_res 640x360
speed/run.sh speed/a_s64b all --solver 64 --vid_every 4 --vid_res 640x360
date > speed/qa.done
