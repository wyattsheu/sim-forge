#!/bin/bash
# 把這次任務的開發成果(腳本、素材、USD、文件、測試)推到 github.com/wyattsheu/sim-forge 的子資料夾,
# 並另存 handoff_<日期>.tgz。不含模擬輸出(out_*/runs/videos/npz),影片由指令重跑產出。
# 用法: publish_sim_forge.sh "<commit 訊息>"
set -euo pipefail
MSG="${1:-update}"
SRC=/isaac-sim/test_scripts/manip_fr3
H=$SRC/handoff_20260929
TASK=fr3_bubblewrap_pack_20261007
CLONE=/tmp/claude-0/sim-forge
STAGE=$CLONE/$TASK

if [ ! -d $CLONE/.git ]; then git clone -q git@github.com:wyattsheu/sim-forge.git $CLONE; fi
cd $CLONE && git config user.name wyattsheu && git config user.email wyattsheu@gmail.com && git pull -q --rebase || true
mkdir -p $STAGE

EXC=(--exclude '__pycache__' --exclude '*.pyc' --exclude 'out_*/' --exclude 'runs/' --exclude 'videos/' --exclude 'soft/' --exclude 'rect/' --exclude 'img/' --exclude 'data/' --exclude 'logs/' --exclude '*.mp4' --exclude '*.stdout' --exclude '*.tgz' --exclude 'wrap_sim.py.before_*' --exclude 'wrap_sim_old.py' --exclude 'wrap_sim_crease.py' --exclude 'wrap_vol.py.before_*' --exclude 'before/' --exclude 'over*/' --exclude 'under/' --exclude 'phys_scene*/' --exclude '*_bad/' --exclude 'lidcheck/' --exclude 'mb*/' --exclude 'dm_*/' --exclude 'fin*/' --exclude 'sh4*/' --exclude 'v[1-4]*/' --exclude 'cr_*/' --exclude 'w_res*/' --exclude '[pqrstu]_*/' --exclude 't[235]_*/' --exclude 'p[0-3]_*/' --exclude 'v3b_*/' --exclude 'v4[abc]_*/' --exclude 'out_c*/')

# work/:腳本、素材、文件、測試、中間狀態 npz(小)
rsync -a --delete "${EXC[@]}" --exclude 'MOVED.txt' $H/work/ $STAGE/work/
# symlink 換成實體檔(給 Windows / 他人 clone)
for f in carton_w131.usd carton_w131.meta.json; do rm -f $STAGE/work/$f; cp -L $H/work/$f $STAGE/work/$f; done
# vol/、arm/:腳本與小素材
rsync -a --delete "${EXC[@]}" $H/vol/ $STAGE/vol/
for f in carton_w131.usd carton_w131.meta.json; do [ -L $STAGE/vol/$f ] && { rm -f $STAGE/vol/$f; cp -L $H/vol/$f $STAGE/vol/$f; } || true; done
[ -d $H/arm ] && rsync -a --delete "${EXC[@]}" $H/arm/ $STAGE/arm/
# 原始交接文件
mkdir -p $STAGE/docs/handoff_20260929
cp $H/*.md $STAGE/docs/handoff_20260929/ 2>/dev/null || true
cp $H/publish_sim_forge.sh $STAGE/
cp $H/REPO_README.md $STAGE/README.md
# 場景 USD(雙臂 + 紙箱 + 包裹)
mkdir -p $STAGE/scene
cp $SRC/handoff_20261002/scene_final.usd $STAGE/scene/
cp $SRC/handoff_20261002/build/stationary_ai_carton_scene_flat.usd $STAGE/scene/
cp $SRC/handoff_20261002/build/build_full_scene.py $STAGE/scene/
cp $SRC/handoff_20261002/README.md $STAGE/scene/README_scene_20261002.md 2>/dev/null || true

cat > $STAGE/.gitignore <<'G'
__pycache__/
*.pyc
*.mp4
*.stdout
out_*/
runs/
videos/
soft/
rect/
img/
logs/
data/
*.tgz
G

cd $CLONE
git add -A $TASK
git -c core.quotepath=off commit -q -m "$MSG" || echo "(沒有變更可提交)"
git push -q origin HEAD
echo "pushed: $(git rev-parse --short HEAD)  $(git log -1 --format=%s)"
du -sh $STAGE | cut -f1

# tgz(舊的保留)
cd $CLONE && tar czf $SRC/handoff_20261007.tgz $TASK
ls -la $SRC/handoff_2026100*.tgz | awk '{print $5, $9}'
