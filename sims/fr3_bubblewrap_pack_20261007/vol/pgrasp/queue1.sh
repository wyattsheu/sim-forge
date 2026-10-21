#!/bin/bash
# 布摩擦對照(指面摩擦是否有作用):L150 mu1.0/2.0 g2.5/3.0,布 fric 0.3 / 2.0
cd "$(dirname "$0")"
./run_probe.sh cf03 --only 6,7,10,11 --fric 0.3
./run_probe.sh cf20 --only 6,7,10,11 --fric 2.0
