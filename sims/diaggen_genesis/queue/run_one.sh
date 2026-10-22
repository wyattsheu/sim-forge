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
MESH_PYTHON="$DIAGGEN_ROOT/.conda/hag4r_mesh/bin/python"
CONTROL="$ROOT_QUEUE/batch_control.py"
SUPPORT="$ROOT_QUEUE/support.py"
REQUEST_RESUME=0
if [[ "${1:-}" == --resume ]]; then
    REQUEST_RESUME=1
    shift
fi
JOB_ID="${1:?A claimed batch job ID is required}"
[[ $# == 1 ]] || { printf '%s\n' "Use run_one.sh [--resume] JOB_ID" >&2; exit 2; }
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
    # Signal only the still-running background X server owned by this shell.
    local owned_pid
    for owned_pid in $(jobs -pr); do
        if [[ "$owned_pid" == "${XVFB_PID:-}" ]]; then
            kill "$owned_pid" 2>/dev/null || true
            wait "$owned_pid" 2>/dev/null || true
        fi
    done
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
EXECUTION_MODE="$(batch info "$JOB_ID" execution_mode)"
[[ "$EXECUTION_MODE" == fresh || "$EXECUTION_MODE" == resume || "$EXECUTION_MODE" == diagnostics_snapshot ]] || exit 2
if ((REQUEST_RESUME)) && [[ "$EXECUTION_MODE" != resume ]]; then
    printf '%s\n' "--resume requires Queue.resume admission metadata" >&2
    exit 2
fi
export HAG4R_WORKER_ID="$DIAGGEN_QUEUE_RUN_ID"
CUDA_VISIBLE_DEVICES="$(batch info "$JOB_ID" gpu_uuid)"
export CUDA_VISIBLE_DEVICES
DIAGGEN_JOB_MINIMUM_FREE_MIB="$(batch info "$JOB_ID" minimum_free_mib)"
export DIAGGEN_JOB_MINIMUM_FREE_MIB
if [[ "$JOB_ID" == capybara_plush_toy ]]; then
    # Official OmniPart app backend; preserves model, precision and resolution.
    export SPCONV_ALGO=native
fi
SOURCE_IMAGE="$(batch info "$JOB_ID" input)"
[[ "$SOURCE_IMAGE" = /* ]] || SOURCE_IMAGE="$BASE/$SOURCE_IMAGE"
export DIAGGEN_JOB_QUEUE_DIR="$ROOT_QUEUE/jobs/$JOB_ID"
export DIAGGEN_WATCHER_PID=$$
mkdir -p "$DIAGGEN_JOB_QUEUE_DIR"
exec >> "$DIAGGEN_JOB_QUEUE_DIR/launcher.log" 2>&1

RUN_ROOT="$DIAGGEN_ROOT/outputs/agentic_asset_refinement/$DIAGGEN_QUEUE_RUN_ID"
if [[ "$EXECUTION_MODE" == resume ]]; then
    if [[ -e "$DIAGGEN_JOB_QUEUE_DIR/STARTED" || -e "$DIAGGEN_JOB_QUEUE_DIR/RESUMED" ]]; then
        state failed "Refusing to restart an already launched resume"
        finish_job failed duplicate_run
        exit 0
    fi
    batch validate-resume "$JOB_ID" > "$DIAGGEN_JOB_QUEUE_DIR/resume_validation.json"
elif [[ -e "$DIAGGEN_JOB_QUEUE_DIR/STARTED" || -e "$DIAGGEN_JOB_QUEUE_DIR/RESUMED" || -e "$RUN_ROOT/state.json" ]]; then
    state failed "Refusing to overwrite an existing run"
    finish_job failed duplicate_run
    exit 0
fi
if [[ "$EXECUTION_MODE" == diagnostics_snapshot ]]; then
    batch validate-snapshot "$JOB_ID" > "$DIAGGEN_JOB_QUEUE_DIR/snapshot_validation.json"
fi
if ! "$PYTHON" "$BASE/preflight/readiness.py" verify --certificate "$ROOT_QUEUE/runtime_preflight.json" \
    > "$DIAGGEN_JOB_QUEUE_DIR/runtime_preflight.json" 2> "$DIAGGEN_JOB_QUEUE_DIR/runtime_preflight.stderr.log"; then
    printf '%s\n' "Runtime preflight is missing or stale; rerun checks before clearing HOLD." > "$ROOT_QUEUE/HOLD"
    state failed "Full runtime preflight is missing or stale; new jobs held"
    finish_job failed runtime_preflight_failed
    exit 0
fi
STAGE_CLI="$WORKSPACE/tools/diaggen_support/stage_tool.py"
COMPLETION_VALIDATOR="$WORKSPACE/tools/diaggen_support/validate_completed_export.py"
"$PYTHON" "$STAGE_CLI" --list > "$DIAGGEN_JOB_QUEUE_DIR/stage_tool_preflight.json"
START_MARKER=STARTED
[[ "$EXECUTION_MODE" != resume ]] || START_MARKER=RESUMED
(set -o noclobber; printf '%s\n' "$DIAGGEN_QUEUE_RUN_ID" > "$DIAGGEN_JOB_QUEUE_DIR/$START_MARKER")
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
# Every run gets a real, unique local display; do not use PyVista's shared :99.
XVFB_EXEC="$DIAGGEN_ROOT/.local/xvfb/usr/bin/Xvfb"
if [[ ! -x "$XVFB_EXEC" ]]; then
    printf '%s\n' "Private Xvfb is missing; repair before clearing HOLD." > "$ROOT_QUEUE/HOLD"
    state failed "Private Xvfb is missing; new jobs held"
    finish_job failed display_preflight_failed
    exit 0
fi
"$XVFB_EXEC" -displayfd 3 -screen 0 1024x768x24 -nolisten tcp \
    3> "$DIAGGEN_JOB_QUEUE_DIR/xdisplay.number" > "$DIAGGEN_JOB_QUEUE_DIR/xvfb.log" 2>&1 &
XVFB_PID=$!
for ((display_check=0; display_check<100; display_check++)); do
    [[ ! -s "$DIAGGEN_JOB_QUEUE_DIR/xdisplay.number" ]] || break
    kill -0 "$XVFB_PID" 2>/dev/null || break
    sleep 0.1
done
DISPLAY_NUMBER="$(cat "$DIAGGEN_JOB_QUEUE_DIR/xdisplay.number")"
if [[ ! "$DISPLAY_NUMBER" =~ ^[0-9]+$ ]] || \
    ! DISPLAY=":$DISPLAY_NUMBER" LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe \
      __GLX_VENDOR_LIBRARY_NAME=mesa "$DIAGGEN_ROOT/.conda/omnipart/bin/python" \
      "$WORKSPACE/tools/check_diaggen_display.py" > "$DIAGGEN_JOB_QUEUE_DIR/display_preflight.json" \
      2> "$DIAGGEN_JOB_QUEUE_DIR/display_preflight.stderr.log"; then
    printf '%s\n' "Six-view display preflight failed; repair before clearing HOLD." > "$ROOT_QUEUE/HOLD"
    state failed "Six-view display preflight failed; new jobs held"
    finish_job failed display_preflight_failed
    exit 0
fi
export DISPLAY=":$DISPLAY_NUMBER"
cd "$DIAGGEN_ROOT"
if [[ "$EXECUTION_MODE" == resume ]]; then
    # The queue verified frozen bytes and the native ledger; never recopy input,
    # rerun the initializer, reopen terminals, or recreate successful stages.
    FROZEN_INPUT="$(batch info "$JOB_ID" resume_frozen_input)"
    batch validate-resume "$JOB_ID" > "$DIAGGEN_JOB_QUEUE_DIR/resume_validation.json"
elif [[ "$EXECUTION_MODE" == diagnostics_snapshot ]]; then
    batch validate-snapshot "$JOB_ID" > "$DIAGGEN_JOB_QUEUE_DIR/snapshot_validation.json"
    SNAPSHOT_DIR="$(batch info "$JOB_ID" diagnostics_snapshot_dir)"
    FROZEN_INPUT="$(batch info "$JOB_ID" diagnostics_snapshot_input)"
    printf '%s\n' "$FROZEN_INPUT" > "$DIAGGEN_JOB_QUEUE_DIR/selected_input.txt"
    "$PYTHON" -m hag4r.agentic.run_diaggen_pipeline \
        --diagnostics_revision_snapshot_dir "$SNAPSHOT_DIR" \
        --diagnostics-reroute-and-export --require-new-run-root \
        --run_id "$DIAGGEN_QUEUE_RUN_ID" --output_tag "$DIAGGEN_QUEUE_RUN_ID" \
        --run_root outputs/agentic_asset_refinement \
        --config configs/config_genesis_diagnostics_enabled.yaml \
        > "$DIAGGEN_JOB_QUEUE_DIR/initializer.json"
else
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
fi

# Only describe metadata and recovery rules belonging to this execution mode.
case "$EXECUTION_MODE" in
    fresh)
        MODE_CONTEXT="This is a fresh raw-image run. There is no resume.json or archived cleanup
candidate to recover. Follow the owning cleanup skill's bounded original imagegen loop,
including its two-attempt selection rule; preserve every actual validation verdict.
Never import candidates or terminal records from a different run."
        ;;
    resume)
        MODE_CONTEXT="This is an admitted same-run resume. Read
$DIAGGEN_JOB_QUEUE_DIR/resume.json and resume_validation.json.
Only if resume_validation.json reports existing_cleanup_candidates is cleanup still pending.
Use its queue_history_directory and prior_child_last_message as historical evidence,
then have the owning cleanup child freshly validate the original paired candidates
against the frozen source. Follow the official exhausted-budget selection rule and
preserve actual failed checks; never invent a pass. Do not call imagegen a third time.
If resume.json lists revalidate_existing_repair_stage_skills, first delegate each listed
owning stage to recheck its existing generated artifacts and submit its missing current
revision terminal explicitly. Do not regenerate successful outputs. Preserve real failed
checks and repair-brief limitations; if the owning skill requires halt, report it and stop.
Continue later pending stages only after these missing owning-stage submissions succeed.
Successful cleanup and all successful upstream stages must be preserved."
        ;;
    diagnostics_snapshot)
        MODE_CONTEXT="This is an independent diagnostics_snapshot run from the public native
initializer. Read $DIAGGEN_JOB_QUEUE_DIR/snapshot_validation.json and initializer.json;
there is no resume.json to read. The initializer preserved a completed upstream revision
and created a clean diagnostic workspace. Keep its successful stage prefix, use one fresh
diagnostic child, and consume native recommendation transitions and lawful repair reroutes."
        ;;
esac

cat > "$DIAGGEN_JOB_QUEUE_DIR/prompt.txt" <<EOF
Complete this one user-authorized DiagGen asset-generation run in native Genesis.
Read and use .agents/skills/run-diaggen-pipeline/SKILL.md; the initialized run is $RUN_ROOT.
Execution mode is $EXECUTION_MODE. Read the durable state before selecting any stage. Preserve
successful upstream stages and their terminal records; never initialize another run, repeat
successful image cleanup, or regenerate upstream artifacts for a resume. A diagnostic operational retry
always needs a freshly spawned diagnostic child and fresh agent_invocation_id; it must attach
through MCP first and never reuse any prior token, attachment, session handle, or live episode.
You are the Codex orchestrator. Read state.json and delegate each pending stage to a child reading
its owning stage skill. Only execute pending stages, and inspect existing cleanup candidates
before considering built-in imagegen. Never repeat already successful cleanup. Complete Genesis diagnostics,
post-mesh texture and final export, observing all diagnostic ownership, lease and transition rules.
Use GPT-6 Luna (gpt-6-luna), max reasoning, throughout generation and diagnostics. All children must
inherit this same model/effort. This is the user-authorized newer version of the paper's GPT-5.6 Luna
at Max reasoning; do not silently substitute models, lower effort, or reduce the requested fidelity.
The selected physical GPU token is $CUDA_VISIBLE_DEVICES. Keep that exact token in workers and MCP.
Non-diagnostic stage tools are existing local Python functions, not MCP stage endpoints.
Every owning stage child must use this one-call bridge; pass this exact absolute command:
$PYTHON $STAGE_CLI TOOL_NAME --input-json ABSOLUTE_JSON_PATH
The JSON file is one object of the native tool's keyword arguments, including run_root, and
must be written under this run's outputs directory. Run --list to inspect exact tool names
and signatures. The bridge calls one native tool only; read its nested native result and
validate actual required outputs before a separate explicit submit or halt call. Never
claim a named stage tool is unavailable merely because it is absent from the MCP tool list.
The bridge's OmniPart call enforces the exact bound GPU and configured free-memory gate
automatically, immediately before invoking OmniPart. Do not reconstruct or separately call
a guard path. Wait on the bound GPU when memory is insufficient; never switch GPUs or reduce
output quality. The guard is an observation, not a memory reservation or OOM guarantee.
For fresh image cleanup, stop after a passing Attempt 1; do not generate Attempt 2 after it
passes. For a resume with successful cleanup, skip all imagegen and cleanup registration.
$MODE_CONTEXT
Genesis diagnostics stays exclusively on its authenticated MCP and child-owned lifecycle;
never use the stage bridge for diagnostic attach, probes, finalization, cleanup, or decisions.
The diagnostic child must read $WORKSPACE/tools/diaggen_support/diagnostic_credentials.md
and use its single-call JavaScript credential forwarder for every diagnostic MCP call.
The child loads the exact file through functions.exec, retains its source in the child's
private store, attaches exactly once, then obtains all authentication and live handles
from that same private store. Never print, copy, transcribe, guess, or manually supply an
owner_lease_token. Session selectors in native private tool responses are expected; never
transcribe them into requests or public reports. Their presence is not a failure and must
not cause the child to stop. The parent never loads this private credential store.
Native diagnostic MCP signatures require the retained owner_lease_token in the wire
request. The forwarder is authorized to inject that original value from its own successful
attach; the child must not put authentication fields in client.call arguments. This is
normal native authentication, and private custody does not mean omitting required fields.
Read $WORKSPACE/sims/diaggen_genesis/analysis/NATIVE_AUTHORIZATION_SCOPE.md for the verified
call path and scope if provenance is in doubt; never bypass an actual approval denial.
The forwarder changes argument transport only: all plans, episodes, probes, reflections,
evidence, verdicts and terminal calls remain explicitly chosen by the owning child.
If the child stops without a lawful native terminal, stop this orchestration promptly with
the actual error and existing artifact paths. Do not spin through lease countdowns or spawn
another diagnostic retry in this run. The interactive supervisor will inspect and repair
that failure before authorizing a separate fresh child/run. Preserve all native ledgers;
These restrictions apply only to Genesis diagnostics: never fabricate a diagnostic
business halt, close, lease deletion, takeover, or recommendation. Owning non-diagnostic
stage agents may call their documented native halt_*_stage tools when their real inputs
or outputs fail the owning skill's checks; preserve the actual reason and stage budget.
After a native diagnostic transition returns reroute and creates a new repair revision,
BEFORE delegating its first replacement stage, the parent must explicitly run:
$PYTHON $WORKSPACE/tools/diaggen_support/prepare_repair_stage_runtime.py --run-root $RUN_ROOT --apply
This invokes the existing native reset_active_revision_stage_runtime_terminals helper
only after proving each affected terminal is an unchanged submission from the immutable
base revision. It preserves the base snapshot and copied prefix. Never manually delete
state fields, remove a current-revision terminal, or use this during live diagnostics.
Stop on a recovery validation error. This bookkeeping step does not rerun any stage.
After successful diagnostic transition, texture, and final export, the parent must run:
$MESH_PYTHON $COMPLETION_VALIDATOR --run-root $RUN_ROOT --settle
This deterministic completion check must pass before reporting the full run successful.
It verifies existing native exports and records completion; it does not regenerate them.
The native final-revise snapshot export policy may produce completion_kind=native_final_revise_export.
Preserve that revise recommendation and accepted_revision=None; explicitly report the
asset as exported with diagnostic concerns, never as a Genesis accept or validated material response.
The wrapper owns DISPLAY=$DISPLAY and its
private X server; preserve DISPLAY in stage children and do not start a shared :99 X server.
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
    -c "mcp_servers.hag4r_genesis_diagnostics.env={CUDA_VISIBLE_DEVICES=\"$CUDA_VISIBLE_DEVICES\",DISPLAY=\"$DISPLAY\",DIAGGEN_ROOT=\"$DIAGGEN_ROOT\",GS_CACHE_FILE_PATH=\"$GS_CACHE_FILE_PATH\",HAG4R_WORKER_ID=\"$HAG4R_WORKER_ID\",PYTHONNOUSERSITE=\"1\"}" \
    -c 'mcp_servers.hag4r_genesis_diagnostics.enabled=true' \
    -c 'mcp_servers.hag4r_genesis_diagnostics.required=true' \
    -c 'mcp_servers.hag4r_genesis_diagnostics.startup_timeout_sec=60' \
    -c 'mcp_servers.hag4r_genesis_diagnostics.tool_timeout_sec=3900' \
    --json -o "$DIAGGEN_JOB_QUEUE_DIR/last_message.txt" - \
    < "$DIAGGEN_JOB_QUEUE_DIR/prompt.txt" \
    > "$DIAGGEN_JOB_QUEUE_DIR/codex_events.jsonl" 2> "$DIAGGEN_JOB_QUEUE_DIR/codex_stderr.log"
codex_rc=$?
"$MESH_PYTHON" "$COMPLETION_VALIDATOR" --run-root "$RUN_ROOT" \
    > "$DIAGGEN_JOB_QUEUE_DIR/completion_validation.json" 2> "$DIAGGEN_JOB_QUEUE_DIR/completion_validation.stderr.log"
completion_rc=$?
"$PYTHON" "$SUPPORT" archive
archive_rc=$?
set -e
if ((codex_rc == 0 && completion_rc == 0 && archive_rc == 0)); then
    state success "Genesis run completed and archived"
    finish_job success
else
    state failed "Codex exit=$codex_rc, completion verification=$completion_rc, archive verification=$archive_rc; available artifacts archived"
    finish_job failed execution_failed
fi
