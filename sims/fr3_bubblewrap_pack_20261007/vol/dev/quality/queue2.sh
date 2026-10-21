#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
quality/run.sh F3 --quality fast
quality/run.sh F4 --quality fast
touch quality/queue2.done
