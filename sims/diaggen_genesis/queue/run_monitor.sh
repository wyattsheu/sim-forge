#!/usr/bin/env bash
set -euo pipefail
QUEUE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$QUEUE_DIR/../../.." && pwd)"
export PATH="$HOME/.local/bin:$HOME/miniforge3/bin:/usr/local/cuda-12.8/bin:$PATH"
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
exec 9> "$QUEUE_DIR/monitor.lock"
flock -n 9 || exit 0
# Keep logs bounded; full run/recovery history is retained separately.
if [[ -f "$QUEUE_DIR/monitor.log" ]] && (( $(stat -c %s "$QUEUE_DIR/monitor.log") > 5242880 )); then
    mv -- "$QUEUE_DIR/monitor.log" "$QUEUE_DIR/monitor.log.1"
fi
exec >> "$QUEUE_DIR/monitor.log" 2>&1
exec "$WORKSPACE/tools/diaggen/.conda/hag4r_mesh/bin/python" "$QUEUE_DIR/monitor.py"
