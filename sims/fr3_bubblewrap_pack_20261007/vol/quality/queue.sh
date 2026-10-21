#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
quality/run.sh F1 --quality fast
quality/run.sh F2 --quality fast
touch quality/queue.done
