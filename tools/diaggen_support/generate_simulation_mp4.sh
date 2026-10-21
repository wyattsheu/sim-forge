#!/usr/bin/env bash
# Native DiagGen encoder entrypoint: scene.json, time multiplier.
set -euo pipefail
SUPPORT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
exec "${HAG4R_PYTHON_BIN:-python3}" "$SUPPORT_DIR/encode_simulation_video.py" "$@"
