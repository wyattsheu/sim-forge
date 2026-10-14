#!/bin/bash
# run.sh NAME LDAMP EDAMP
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol
/isaac-sim/python.sh wrap_vol.py --sheet_mm 500 --out damp/$1 --young 2000 --thick_mm 4 --nxy 35 --cont 0.002 --rest 0.0005 --solver 128 --tuck 1 --movebox 0,0.20,0.10 --until fold --meas_dt 0.0333 --ldamp $2 --edamp $3 > damp/$1.stdout 2>&1
echo done $1
