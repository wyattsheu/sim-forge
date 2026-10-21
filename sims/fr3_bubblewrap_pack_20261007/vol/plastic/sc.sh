#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
source plastic/gpuwait.sh
/isaac-sim/python.sh plastic/probe_selfcoll.py "$@" > plastic/logs/stdout_sc_$(echo "$@" | tr -d ' -').txt 2>&1
