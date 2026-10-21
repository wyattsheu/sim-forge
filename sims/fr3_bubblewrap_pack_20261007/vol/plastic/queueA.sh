#!/bin/bash
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
plastic/run.sh A1 --grasp 0 --extract 0 --quality fast --plastic_on_fold 1
plastic/run.sh A0 --grasp 0 --extract 0 --quality fast --plastic_on_fold 0
