#!/bin/bash
# old(grasp_plan.py.before_speed)vs new 在多個 npz / 快照上逐欄比對;單執行緒、同時 2 個(不搶其他模擬的 CPU)
cd /isaac-sim/test_scripts/manip_fr3/handoff_20260929/vol/dev
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
cp -p grasp_plan.py.before_speed speed2/grasp_plan_old.py
job() { r=$1; sn=$2; tag=$(echo $r | tr / _)_$sn
  [ -f speed2/val/old_$tag.pkl ] || nice -n 10 /isaac-sim/python.sh speed2/prof_plan.py --npz ../$r/wrap.npz --snap $sn --mod grasp_plan_old --out speed2/val/old_$tag.pkl > speed2/val/old_$tag.txt 2>&1
  nice -n 10 /isaac-sim/python.sh speed2/prof_plan.py --npz ../$r/wrap.npz --snap $sn --mod grasp_plan --out speed2/val/new_$tag.pkl > speed2/val/new_$tag.txt 2>&1; }
export -f job
printf "%s\n" "extract4/X1 plan" "extract4/X3 plan" "extract6/C3f plan" "quality/F3 plan" "quality/Q1 plan" "peel4/L1 plan" "robust/r3 plan" "extract6/X2 grip" | xargs -P 2 -L 1 bash -c 'job $0 $1'
grep -h "COMPARE\|order\|rank" speed2/val/new_*.txt
