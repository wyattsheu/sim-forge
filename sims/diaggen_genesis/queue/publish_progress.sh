#!/usr/bin/env bash
set -euo pipefail
QUEUE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$QUEUE_DIR/../../.." && pwd)"
export PYTHONNOUSERSITE=1
export PYTHONUNBUFFERED=1
exec >> "$QUEUE_DIR/publisher.log" 2>&1
exec "$WORKSPACE/tools/diaggen/.conda/hag4r/bin/python" "$QUEUE_DIR/publish_progress.py" --watch --interval 15
