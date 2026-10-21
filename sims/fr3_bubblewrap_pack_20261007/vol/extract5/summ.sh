#!/bin/bash
# usage: extract5/summ.sh extract4/X1 extract5/X1 ...   (在 vol/ 下執行;印 EXTRACT3 v4 同欄位的表格列)
for d in "$@"; do f=$d/stdout.txt
 ynb=$(grep -o "\[yn\] 綁住 [0-9]*" $f | grep -o "[0-9]*$"); ypb=$(grep -o "\[yp\] 綁住 [0-9]*" $f | grep -o "[0-9]*$")
 h2=$(grep "^\[hand2\] SUMMARY" $f); h2n=$(echo "$h2" | grep -o " n=[0-9]*" | cut -d= -f2); h2l=$(echo "$h2" | grep -o "= [0-9/]*%" | head -1 | grep -o "[0-9]*%$")
 xs=$(grep "^\[extract\] SUMMARY" $f); yne=$(echo "$xs" | grep -o "yn 越線 [0-9]*%" | grep -o "[0-9]*%"); ype=$(echo "$xs" | grep -o "yp 越線 [0-9]*%" | grep -o "[0-9]*%")
 out=$(echo "$xs" | grep -o "離開內腔 t=[0-9.]*" | cut -d= -f2); pen=$(echo "$xs" | grep -o "布穿杯最大 [0-9]*" | grep -o "[0-9]*$")
 yp117=$(grep "G\[yp\] t=117.25" $f | grep -o "yp 越過折線 *[0-9]*%" | grep -o "[0-9]*%")
 g=$(grep -c "守衛:邊長比" $f)
 x2=$(grep "^\[extract2\] SUMMARY" $f); up=$(echo "$x2" | grep -o "抬起時最大 [0-9.]*" | grep -o "[0-9.]*$"); lv=$(echo "$x2" | grep -o "離箱 [0-9.]*" | grep -o "[0-9.]*$"); gr=$(echo "$x2" | grep -o "落地 [0-9.]*" | grep -o "[0-9.]*$")
 cup=$(echo "$x2" | grep -o "箱局部 ([^)]*)" | cut -d' ' -f2); inb=$(echo "$x2" | grep -o "布在箱內 [0-9.]*%" | grep -o "[0-9.]*%")
 wall=$(grep -o "wall [0-9.]*s / sim" $f | grep -o "^wall [0-9.]*" | cut -d" " -f2)
 echo "| $d | $ynb / $h2n | $h2l → $yne | $ypb | $yp117 → $ype | 守衛行 $g | $out | $pen | $up / $lv / $gr% | $cup | $inb | $wall |"
done
