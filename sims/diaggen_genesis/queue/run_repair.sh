#!/usr/bin/env bash
# Only this shell launches the incident investigator; Python is bookkeeping.
set -euo pipefail
QUEUE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$QUEUE_DIR/../../.." && pwd)"
export PATH="$HOME/.local/bin:$HOME/miniforge3/bin:/usr/local/cuda-12.8/bin:$PATH"
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export DIAGGEN_REPAIR_RUNNER_PID=$$
PYTHON="$WORKSPACE/tools/diaggen/.conda/hag4r/bin/python"
exec 9> "$QUEUE_DIR/repair.lock"
flock -n 9 || exit 0
MODE=()
if [[ "${1:-}" == --audit && $# == 1 ]]; then
    MODE=(--audit)
elif [[ "${1:-}" == --retry-launch-fix && $# == 1 ]]; then
    MODE=(--retry-launch-fix)
elif [[ $# != 0 ]]; then
    exit 2
fi
JOB_ID="$("$PYTHON" "$QUEUE_DIR/repair_control.py" prepare "${MODE[@]}")"
[[ -n "$JOB_ID" ]] || exit 0
[[ "$JOB_ID" =~ ^[A-Za-z0-9_]+$ ]] || exit 2
JOB_DIR="$QUEUE_DIR/repair_jobs/$JOB_ID"
exec >> "$JOB_DIR/launcher.log" 2>&1
finish_repair() {
    local result=$?
    trap - EXIT
    "$PYTHON" "$QUEUE_DIR/repair_control.py" finish "$JOB_ID" "$result"
    exit "$result"
}
trap finish_repair EXIT
# Inherit the same automatic review policy as generation; never bypass it.
timeout --signal=TERM --kill-after=30s 2700 \
  codex exec --approve-for-me --cd "$WORKSPACE" --disable multi_agent_v2 \
    --model gpt-6-luna -c 'model_reasoning_effort="max"' \
    -c "mcp_servers.hag4r_genesis_diagnostics.command=\"$PYTHON\"" \
    -c 'mcp_servers.hag4r_genesis_diagnostics.args=["-B","-m","hag4r.agentic.diagnostic_mcp_server"]' \
    -c 'mcp_servers.hag4r_genesis_diagnostics.enabled=false' \
    --output-schema "$QUEUE_DIR/repair_result.schema.json" \
    --json -o "$JOB_DIR/result.json" - \
    < "$JOB_DIR/prompt.txt" > "$JOB_DIR/events.jsonl" 2> "$JOB_DIR/stderr.log"
