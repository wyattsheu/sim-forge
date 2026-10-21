#!/usr/bin/env bash
# Wait for an input and an idle GPU, then launch one real Codex orchestrator.
set -euo pipefail
QUEUE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(cd "$QUEUE_DIR/.." && pwd)"
WORKSPACE="$(cd "$BASE/../.." && pwd)"
export DIAGGEN_ROOT="$WORKSPACE/tools/diaggen"
export DIAGGEN_QUEUE_RUN_ID=genesis_first_20261021
export DIAGGEN_MIN_FREE_MIB=65536
export DIAGGEN_WATCHER_PID=$$
export PYTHONNOUSERSITE=1
export PYTHONUNBUFFERED=1
export CUDA_HOME=/usr/local/cuda-12.8
export PATH="$CUDA_HOME/bin:$HOME/.local/bin:$HOME/miniforge3/bin:$PATH"
PYTHON="$DIAGGEN_ROOT/.conda/hag4r/bin/python"
SUPPORT="$QUEUE_DIR/support.py"
RUN_ROOT="$DIAGGEN_ROOT/outputs/agentic_asset_refinement/$DIAGGEN_QUEUE_RUN_ID"
exec >> "$QUEUE_DIR/watcher.log" 2>&1
exec 9> "$QUEUE_DIR/watcher.lock"
flock -n 9 || exit 1
state() { "$PYTHON" "$SUPPORT" status "$@"; }
trap 'state cancelled "Watcher received a termination signal"; trap - EXIT; exit 130' INT TERM
trap 'rc=$?; if ((rc != 0)); then state failed "Launcher exited with code $rc; see watcher.log"; fi' EXIT

if [[ -e "$QUEUE_DIR/STARTED" || -e "$RUN_ROOT/state.json" ]]; then
    state stopped "This job has already started; refusing a duplicate run"
    exit 0
fi
if [[ ! -f "$QUEUE_DIR/preflight.ok" ]]; then
    state blocked "Codex shell/imagegen/child-agent preflight has not passed"
    exit 0
fi

previous_gpu=""
while true; do
    if [[ -e "$QUEUE_DIR/STOP" ]]; then
        state cancelled "STOP file found; no pipeline was launched"
        exit 0
    fi
    if ! SOURCE_IMAGE="$("$PYTHON" "$SUPPORT" input 2> "$QUEUE_DIR/input_check.log")"; then
        state waiting_input "Place one PNG/JPG in $BASE/inputs/"
        previous_gpu=""
        sleep 60
        continue
    fi
    if ! candidate="$("$PYTHON" "$SUPPORT" probe 2> "$QUEUE_DIR/gpu_check.log")"; then
        state waiting_gpu "Need an idle GPU with at least 65536 MiB free"
        previous_gpu=""
        sleep 60
        continue
    fi
    if [[ "$candidate" != "$previous_gpu" ]]; then
        state confirming_gpu "GPU $candidate is idle; checking again in 60 seconds"
        previous_gpu="$candidate"
        sleep 60
        continue
    fi
    export CUDA_VISIBLE_DEVICES="$candidate"
    break
done

# Retain the same GPU token in the ledger, all stage workers, and diagnostics MCP.
export HAG4R_SAM3_CHECKPOINT_PATH="$HOME/.cache/huggingface/hub/models--facebook--sam3/snapshots/3c879f39826c281e95690f02c7821c4de09afae7/sam3.pt"
printf '%s\n' "$CUDA_VISIBLE_DEVICES" > "$QUEUE_DIR/selected_gpu.txt"
printf '%s\n' "$SOURCE_IMAGE" > "$QUEUE_DIR/original_input.txt"
(set -o noclobber; printf '%s\n' "$DIAGGEN_QUEUE_RUN_ID" > "$QUEUE_DIR/STARTED")
state running "Using $CUDA_VISIBLE_DEVICES with Genesis diagnostics enabled"
cd "$DIAGGEN_ROOT"
mkdir -p outputs/inputs
FROZEN_INPUT="$DIAGGEN_ROOT/outputs/inputs/${DIAGGEN_QUEUE_RUN_ID}.${SOURCE_IMAGE##*.}"
cp -- "$SOURCE_IMAGE" "$FROZEN_INPUT"
printf '%s\n' "$FROZEN_INPUT" > "$QUEUE_DIR/selected_input.txt"
"$PYTHON" -m hag4r.agentic.run_diaggen_pipeline \
    --source_image "$FROZEN_INPUT" \
    --run_id "$DIAGGEN_QUEUE_RUN_ID" \
    --output_tag "$DIAGGEN_QUEUE_RUN_ID" \
    --run_root outputs/agentic_asset_refinement \
    --config configs/config_genesis_diagnostics_enabled.yaml \
    > "$QUEUE_DIR/initializer.json"

cat > "$QUEUE_DIR/prompt.txt" <<EOF
Run the user-authorized DiagGen asset-generation job to completion in its native Genesis simulator.
Use and read .agents/skills/run-diaggen-pipeline/SKILL.md. The initialized run is $RUN_ROOT.
Read state.json and continue all pending stages. You are the Codex orchestrator: delegate each stage
to a Codex child reading that stage's skill. Use built-in imagegen for image cleanup as required.
The paper uses GPT-5.6 Luna at Max reasoning for generation and diagnostics. The user authorized a
newer version: this job uses GPT-6 Luna (gpt-6-luna) at max reasoning. All stage children must inherit
that same model and reasoning effort; do not silently substitute another model or lower the effort.
Genesis diagnostics are enabled; follow all ownership, lease, child-only and terminal-transition boundaries.
The selected physical GPU token is $CUDA_VISIBLE_DEVICES; retain that exact single CUDA_VISIBLE_DEVICES
value in workers and the MCP server. Do not initialize a second run or change the GPU binding.
Complete post-mesh texture and final export after validated diagnostic acceptance. Never fabricate
evidence, recommendations, successful stage records, or images. If a required capability or dependency
fails, stop with a clear error and preserve artifacts. Do not edit project code, install packages,
touch other users' jobs, kill unrelated processes, or start Isaac Sim. Existing cached model loading
and necessary public model downloads are allowed. Generated working artifacts must remain inside
this checkout's outputs/. A wrapper will copy the completed results into $BASE/runs/ and label Genesis.
If sandbox execution fails with bwrap/Operation not permitted, request escalation for the exact
necessary command and let automatic approval review decide; never bypass sandbox or approval policy.
End with a concise Traditional Chinese report of actual status and the paths to meshes, images and videos.
EOF

# Supply a complete MCP definition: project config may be ignored in an untrusted checkout.
set +e
codex exec --approve-for-me --cd "$DIAGGEN_ROOT" --enable multi_agent_v2 \
    --model gpt-6-luna \
    -c 'model_reasoning_effort="max"' \
    -c 'agents.max_depth=2' \
    -c 'agents.default_subagent_model="gpt-6-luna"' \
    -c 'agents.default_subagent_reasoning_effort="max"' \
    -c 'shell_environment_policy.inherit="all"' \
    -c "mcp_servers.hag4r_genesis_diagnostics.command=\"$PYTHON\"" \
    -c 'mcp_servers.hag4r_genesis_diagnostics.args=["-B","-m","hag4r.agentic.diagnostic_mcp_server","--owner-lease-timeout-s","3900"]' \
    -c "mcp_servers.hag4r_genesis_diagnostics.cwd=\"$DIAGGEN_ROOT\"" \
    -c "mcp_servers.hag4r_genesis_diagnostics.env={CUDA_VISIBLE_DEVICES=\"$CUDA_VISIBLE_DEVICES\",DIAGGEN_ROOT=\"$DIAGGEN_ROOT\",PYTHONNOUSERSITE=\"1\"}" \
    -c 'mcp_servers.hag4r_genesis_diagnostics.enabled=true' \
    -c 'mcp_servers.hag4r_genesis_diagnostics.required=true' \
    -c 'mcp_servers.hag4r_genesis_diagnostics.startup_timeout_sec=60' \
    -c 'mcp_servers.hag4r_genesis_diagnostics.tool_timeout_sec=3900' \
    --json -o "$QUEUE_DIR/last_message.txt" - \
    < "$QUEUE_DIR/prompt.txt" > "$QUEUE_DIR/codex_events.jsonl" 2> "$QUEUE_DIR/codex_stderr.log"
codex_rc=$?
"$PYTHON" "$SUPPORT" archive
archive_rc=$?
set -e
if ((codex_rc == 0 && archive_rc == 0)); then
    state success "Genesis run completed; results copied to $BASE/runs/$DIAGGEN_QUEUE_RUN_ID"
else
    state failed "Codex exit=$codex_rc, artifact verification=$archive_rc; partial results archived when available"
fi
