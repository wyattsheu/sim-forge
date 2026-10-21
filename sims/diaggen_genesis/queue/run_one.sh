#!/usr/bin/env bash
# Run exactly one GPU-reserved batch entry with a real Codex orchestrator.
set -euo pipefail
ROOT_QUEUE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(cd "$ROOT_QUEUE/.." && pwd)"
WORKSPACE="$(cd "$BASE/../.." && pwd)"
export DIAGGEN_ROOT="$WORKSPACE/tools/diaggen"
export PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1
export CUDA_HOME=/usr/local/cuda-12.8
export PATH="$CUDA_HOME/bin:$HOME/.local/bin:$HOME/miniforge3/bin:$PATH"
PYTHON="$DIAGGEN_ROOT/.conda/hag4r/bin/python"
CONTROL="$ROOT_QUEUE/batch_control.py"
SUPPORT="$ROOT_QUEUE/support.py"
JOB_ID="${1:?A claimed batch job ID is required}"
batch() { "$PYTHON" "$CONTROL" "$@"; }
state() { "$PYTHON" "$SUPPORT" status "$@"; }
WORKER_FINALIZED=0
finish_job() {
    batch finish "$JOB_ID" "$@"
    WORKER_FINALIZED=1
}
worker_exit() {
    local rc=$?
    trap - EXIT
    if ((WORKER_FINALIZED == 0)); then
        set +e
        if [[ -n "${DIAGGEN_QUEUE_RUN_ID:-}" && -n "${DIAGGEN_JOB_QUEUE_DIR:-}" ]]; then
            state failed "Worker exited before terminal status (code $rc)"
        fi
        batch finish "$JOB_ID" failed launcher_error
        if ((rc == 0)); then rc=1; fi
    fi
    exit "$rc"
}
# Bind and all queue lookups are covered, including failures before log setup.
trap worker_exit EXIT
batch bind "$JOB_ID" "$$"
DIAGGEN_QUEUE_RUN_ID="$(batch info "$JOB_ID" run_id)"
export DIAGGEN_QUEUE_RUN_ID
export HAG4R_WORKER_ID="$DIAGGEN_QUEUE_RUN_ID"
CUDA_VISIBLE_DEVICES="$(batch info "$JOB_ID" gpu_uuid)"
export CUDA_VISIBLE_DEVICES
SOURCE_IMAGE="$(batch info "$JOB_ID" input)"
[[ "$SOURCE_IMAGE" = /* ]] || SOURCE_IMAGE="$BASE/$SOURCE_IMAGE"
export DIAGGEN_JOB_QUEUE_DIR="$ROOT_QUEUE/jobs/$JOB_ID"
export DIAGGEN_WATCHER_PID=$$
mkdir -p "$DIAGGEN_JOB_QUEUE_DIR"
exec >> "$DIAGGEN_JOB_QUEUE_DIR/launcher.log" 2>&1

RUN_ROOT="$DIAGGEN_ROOT/outputs/agentic_asset_refinement/$DIAGGEN_QUEUE_RUN_ID"
if [[ -e "$DIAGGEN_JOB_QUEUE_DIR/STARTED" || -e "$RUN_ROOT/state.json" ]]; then
    state failed "Refusing to overwrite an existing run"
    finish_job failed duplicate_run
    exit 0
fi
(set -o noclobber; printf '%s\n' "$DIAGGEN_QUEUE_RUN_ID" > "$DIAGGEN_JOB_QUEUE_DIR/STARTED")
printf '%s\n' "$CUDA_VISIBLE_DEVICES" > "$DIAGGEN_JOB_QUEUE_DIR/selected_gpu.txt"
printf '%s\n' "$SOURCE_IMAGE" > "$DIAGGEN_JOB_QUEUE_DIR/original_input.txt"
state running "Shared GPU $CUDA_VISIBLE_DEVICES; Genesis diagnostics enabled"
export HAG4R_SAM3_CHECKPOINT_PATH="$HOME/.cache/huggingface/hub/models--facebook--sam3/snapshots/3c879f39826c281e95690f02c7821c4de09afae7/sam3.pt"
# Keep Genesis cache writes separate when both GPUs have an active batch job.
export GS_CACHE_FILE_PATH="$RUN_ROOT/.cache/genesis"
if ! "$DIAGGEN_ROOT/.conda/hag4r_segmentation/bin/python" "$WORKSPACE/tools/check_diaggen_exr.py" \
    > "$DIAGGEN_JOB_QUEUE_DIR/exr_preflight.json" 2> "$DIAGGEN_JOB_QUEUE_DIR/exr_preflight.stderr.log"; then
    printf '%s\n' "SAM3 EXR preflight failed; repair the local environment before clearing HOLD." > "$ROOT_QUEUE/HOLD"
    state failed "SAM3 EXR preflight failed; new jobs held"
    finish_job failed exr_preflight_failed
    exit 0
fi
cd "$DIAGGEN_ROOT"
mkdir -p outputs/inputs
FROZEN_INPUT="$DIAGGEN_ROOT/outputs/inputs/${DIAGGEN_QUEUE_RUN_ID}.${SOURCE_IMAGE##*.}"
cp -- "$SOURCE_IMAGE" "$FROZEN_INPUT"
printf '%s\n' "$FROZEN_INPUT" > "$DIAGGEN_JOB_QUEUE_DIR/selected_input.txt"
"$PYTHON" -m hag4r.agentic.run_diaggen_pipeline \
    --source_image "$FROZEN_INPUT" --run_id "$DIAGGEN_QUEUE_RUN_ID" \
    --output_tag "$DIAGGEN_QUEUE_RUN_ID" \
    --run_root outputs/agentic_asset_refinement \
    --config configs/config_genesis_diagnostics_enabled.yaml \
    > "$DIAGGEN_JOB_QUEUE_DIR/initializer.json"

cat > "$DIAGGEN_JOB_QUEUE_DIR/prompt.txt" <<EOF
Complete this one user-authorized DiagGen asset-generation run in native Genesis.
Read and use .agents/skills/run-diaggen-pipeline/SKILL.md; the initialized run is $RUN_ROOT.
You are the Codex orchestrator. Read state.json and delegate each pending stage to a child reading
its owning stage skill. Use built-in imagegen for image cleanup. Complete Genesis diagnostics,
post-mesh texture and final export, observing all diagnostic ownership, lease and transition rules.
Use GPT-6 Luna (gpt-6-luna), max reasoning, throughout generation and diagnostics. All children must
inherit this same model/effort. This is the user-authorized newer version of the paper's GPT-5.6 Luna
at Max reasoning; do not silently substitute models, lower effort, or reduce the requested fidelity.
The selected physical GPU token is $CUDA_VISIBLE_DEVICES. Keep that exact token in workers and MCP.
The GPU is shared with existing work. Do not stop or alter other processes, claim another GPU,
install packages, edit project code, start Isaac Sim, or initialize another run. Existing model
caches and necessary public model downloads are allowed. Preserve the per-job GS_CACHE_FILE_PATH.
If memory allocation fails, stop with the actual failure and preserve artifacts; do not fabricate
success, evidence or recommendations. Other jobs are managed by an external shell queue.
All generated work belongs in this checkout's outputs/. A wrapper will archive results under
$BASE/runs/$DIAGGEN_QUEUE_RUN_ID and publish safe progress to GitHub.
If sandbox execution fails with bwrap/Operation not permitted, request escalation for the exact
necessary command and let automatic approval review decide. Never bypass the configured policy.
End with a concise Traditional Chinese status report and actual mesh, image and video paths.
EOF

set +e
codex exec --approve-for-me --cd "$DIAGGEN_ROOT" --enable multi_agent_v2 \
    --model gpt-6-luna -c 'model_reasoning_effort="max"' \
    -c 'agents.max_depth=2' \
    -c 'agents.default_subagent_model="gpt-6-luna"' \
    -c 'agents.default_subagent_reasoning_effort="max"' \
    -c 'shell_environment_policy.inherit="all"' \
    -c "mcp_servers.hag4r_genesis_diagnostics.command=\"$PYTHON\"" \
    -c 'mcp_servers.hag4r_genesis_diagnostics.args=["-B","-m","hag4r.agentic.diagnostic_mcp_server","--owner-lease-timeout-s","3900"]' \
    -c "mcp_servers.hag4r_genesis_diagnostics.cwd=\"$DIAGGEN_ROOT\"" \
    -c "mcp_servers.hag4r_genesis_diagnostics.env={CUDA_VISIBLE_DEVICES=\"$CUDA_VISIBLE_DEVICES\",DIAGGEN_ROOT=\"$DIAGGEN_ROOT\",GS_CACHE_FILE_PATH=\"$GS_CACHE_FILE_PATH\",HAG4R_WORKER_ID=\"$HAG4R_WORKER_ID\",PYTHONNOUSERSITE=\"1\"}" \
    -c 'mcp_servers.hag4r_genesis_diagnostics.enabled=true' \
    -c 'mcp_servers.hag4r_genesis_diagnostics.required=true' \
    -c 'mcp_servers.hag4r_genesis_diagnostics.startup_timeout_sec=60' \
    -c 'mcp_servers.hag4r_genesis_diagnostics.tool_timeout_sec=3900' \
    --json -o "$DIAGGEN_JOB_QUEUE_DIR/last_message.txt" - \
    < "$DIAGGEN_JOB_QUEUE_DIR/prompt.txt" \
    > "$DIAGGEN_JOB_QUEUE_DIR/codex_events.jsonl" 2> "$DIAGGEN_JOB_QUEUE_DIR/codex_stderr.log"
codex_rc=$?
"$PYTHON" "$SUPPORT" archive
archive_rc=$?
set -e
if ((codex_rc == 0 && archive_rc == 0)); then
    state success "Genesis run completed and archived"
    finish_job success
else
    state failed "Codex exit=$codex_rc, artifact verification=$archive_rc; available artifacts archived"
    finish_job failed execution_failed
fi
