#!/usr/bin/env bash
# Deterministic shell queue; each worker starts one real Codex orchestrator.
set -euo pipefail
QUEUE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$QUEUE_DIR/../../.." && pwd)"
export PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1
export PATH="$HOME/.local/bin:$HOME/miniforge3/bin:$PATH"
PYTHON="$WORKSPACE/tools/diaggen/.conda/hag4r/bin/python"
CONTROL="$QUEUE_DIR/batch_control.py"
exec >> "$QUEUE_DIR/watcher.log" 2>&1
exec 9> "$QUEUE_DIR/watcher.lock"
flock -n 9 || exit 1
batch() { "$PYTHON" "$CONTROL" "$@"; }
supervise_job() {
    local job="$1" worker_pid child_rc=0 phase
    # This guard survives an absent/broken worker script and waits for its EXIT trap.
    bash "$QUEUE_DIR/run_one.sh" "$job" &
    worker_pid=$!
    if ! batch bind "$job" "$worker_pid"; then
        printf 'Worker binding did not complete for %s; waiting for its result\n' "$job"
    fi
    if wait "$worker_pid"; then
        child_rc=0
    else
        child_rc=$?
    fi
    if phase="$(batch info "$job" status)"; then
        if [[ "$phase" == running ]]; then
            printf 'Worker for %s exited (%s) without a terminal result\n' "$job" "$child_rc"
            batch finish "$job" failed worker_exited_without_result || \
                printf 'Could not finalize failed worker %s\n' "$job"
        fi
    else
        printf 'Could not inspect completed worker %s\n' "$job"
    fi
    return 0
}
if [[ ! -f "$QUEUE_DIR/preflight.ok" ]]; then
    printf '%s\n' "Codex shell/imagegen/child-agent preflight has not passed"
    exit 1
fi
batch init
interval="$(batch policy check_interval_seconds)"
printf '%s\n' "Batch queue started; jobs share available GPU memory"
while true; do
    if [[ -e "$QUEUE_DIR/STOP" ]]; then
        batch cancel
        batch summary
        # Already running jobs finish normally; no unrelated processes are stopped.
        wait || printf '%s\n' "A worker guard exited with an error"
        exit 0
    fi
    batch summary
    if batch done; then
        wait || printf '%s\n' "A worker guard exited with an error"
        batch summary
        exit 0
    fi
    if candidates="$(batch candidates)"; then
        while IFS= read -r gpu; do
            [[ -n "$gpu" ]] || continue
            if job="$(batch claim "$gpu")"; then
                printf 'Starting batch job %s on %s\n' "$job" "$gpu"
                # Release the supervisor lock in the child before it starts Codex.
                supervise_job "$job" 9>&- &
            else
                code=$?
                if ((code != 3)); then
                    printf 'Could not claim GPU (%s); retrying next poll\n' "$code"
                fi
            fi
        done <<< "$candidates"
    else
        printf '%s\n' "GPU probe failed; no jobs launched this poll"
    fi
    sleep "$interval"
done
