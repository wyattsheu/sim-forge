#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
until [ -f quality/queue2.done ]; do sleep 15; done
quality/run_prog.sh Q1 --quality final
touch quality/queue3.done
