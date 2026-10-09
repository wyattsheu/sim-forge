#!/bin/bash
# full test matrix for docs/CREASE_MECHANICS.md (sequential: GPU memory is shared with other jobs)
#   SCENE=<built scene> ./run_crease_matrix.sh      optional comparisons: OLD_SCENE=<pre-2026-10-09 scene> SPRING_SCENE=<spring-only scene>
cd "$(dirname "$0")"; mkdir -p ../videos; export OMNI_KIT_ACCEPT_EULA=YES; PY=~/env_isaaclab/bin/python; L=../logs; V=../videos; mkdir -p logs; N=${SCENE:-../scene_final_phys.usd}
run(){ echo "== $*"; "$@" > $L/matrix_last.stdout 2>&1 || echo "   (exit $?)"; grep -m2 "Traceback" $L/matrix_last.stdout; }
run $PY crease_test.py $N --lid fyp --track 90 --cycles 3 --empty
[ -f "$OLD_SCENE" ] && run $PY crease_test.py $OLD_SCENE --lid fyp --track 90 --model latch --empty --out logs/crease_fyp_90_oldlatch_empty
[ -f "$SPRING_SCENE" ] && run $PY crease_test.py $SPRING_SCENE --lid fyp --track 90 --model spring --empty --out logs/crease_fyp_90_spring_empty
run $PY crease_test.py $N --lid fyp --track 90 --empty --video $V/crease_fold90.mp4 --label "Fold to 90 deg, hold 1 s, release (empty carton)"
run $PY crease_test.py $N --lid fyp --track 270 --empty --video $V/crease_fold270.mp4 --label "Fold to 270 deg (down the outside of the wall), release"
run $PY crease_test.py $N --lid fyp --track 90 --video $V/crease_fold90_packed.mp4 --label "Fold to 90 deg with the package inside"
run $PY lid_test.py $N 70 plastic
run $PY verify_phys_scene.py $N --test P --pull_lid fyp --pull_max 3 --log $L/P_fyp_crease.txt --video $V/pull_fyp_crease.mp4 --label "Arm-like pull on the flap edge (elastic-plastic crease)"
run $PY verify_phys_scene.py $N --test A --log $L/A_crease.txt
run $PY verify_phys_scene.py $N --test B --log $L/B_crease.txt
run $PY verify_phys_scene.py $N --test S --shake_amp 0.08 --shake_hz 3 --log $L/S2_crease.txt
echo MATRIX DONE
