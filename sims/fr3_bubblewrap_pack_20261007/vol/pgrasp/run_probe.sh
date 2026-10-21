#!/bin/bash
# 用法:pgrasp/run_probe.sh <tag> [probe_edge.py 參數...]   GPU OOM 自動重跑(最多 30 次)
cd "$(dirname "$0")"
TAG=$1; shift
mkdir -p "$TAG"
for try in $(seq 1 30); do
  source ./gpuwait.sh
  /isaac-sim/python.sh probe_edge.py --tag "$TAG" "$@" > "$TAG/stdout.txt" 2>&1
  echo "EXIT $?" >> "$TAG/stdout.txt"
  if grep -qi "out-of-memory\|out of memory\|failed to allocate\|OUT_OF_DEVICE_MEMORY" "$TAG/stdout.txt"; then
    mv "$TAG/stdout.txt" "$TAG/stdout_oom$try.txt"; sleep 60; continue
  fi
  break
done
