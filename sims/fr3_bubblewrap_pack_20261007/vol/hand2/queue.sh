#!/bin/bash
# usage: hand2/queue.sh NAME:MODE ...
R=/isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/hand2/run.sh
S="--site_xmax_mm 60 --grasp_site_k 13 --arc2_over_cap 0 --arc2_over_mm 30"
for nm in "$@"; do $R ${nm%%:*} $S --hand2 ${nm##*:}; done
touch /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/hand2/queue.done
