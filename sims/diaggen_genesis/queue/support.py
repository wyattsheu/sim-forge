"""Deterministic queue bookkeeping; the Codex CLI owns the DiagGen pipeline."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT_QUEUE = Path(__file__).resolve().parent
QUEUE = Path(os.environ.get("DIAGGEN_JOB_QUEUE_DIR", str(ROOT_QUEUE))).resolve()
BASE = ROOT_QUEUE.parent
WORKSPACE = BASE.parents[1]
DIAGGEN = WORKSPACE / "tools/diaggen"
RUN_ID = os.environ.get("DIAGGEN_QUEUE_RUN_ID", "genesis_first_20261021")
RUN_ROOT = DIAGGEN / "outputs/agentic_asset_refinement" / RUN_ID


def now():
    return datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def status(phase, detail=""):
    write_json(QUEUE / "status.json", {
        "updated_at": now(), "phase": phase, "detail": detail,
        "simulator": "Genesis", "pipeline": "DiagGen", "run_id": RUN_ID,
        "generation_and_diagnostics_model": "gpt-6-luna", "reasoning_effort": "max",
        "input_directory": str(BASE / "inputs"),
        "working_run_root": str(RUN_ROOT),
        "results_directory": str(BASE / "runs" / RUN_ID),
        "watcher_pid": os.environ.get("DIAGGEN_WATCHER_PID"),
    })
    print(f"[{now()}] {phase}: {detail}", flush=True)


def archive():
    state_path = RUN_ROOT / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    destination = BASE / "runs" / RUN_ID
    destination.mkdir(parents=True, exist_ok=True)
    mapping = {}
    if RUN_ROOT.exists():
        shutil.copytree(RUN_ROOT, destination / "trace", dirs_exist_ok=True)
        mapping[str(RUN_ROOT)] = str(destination / "trace")
    export = state.get("paths", {}).get("final_export_dir")
    if export:
        export = Path(export).resolve()
        export.relative_to((DIAGGEN / "outputs").resolve())
        if export.is_dir():
            shutil.copytree(export, destination / "asset", dirs_exist_ok=True)
            mapping[str(export)] = str(destination / "asset")
    source_file = QUEUE / "selected_input.txt"
    source = Path(source_file.read_text().strip()) if source_file.exists() else None
    if source and source.is_file():
        shutil.copy2(source, destination / ("input" + source.suffix.lower()))
    provenance = BASE / "demo_image_sources.json"
    if provenance.exists():
        shutil.copy2(provenance, destination / "input_sources.json")
    write_json(destination / "manifest.json", {
        "simulator": "Genesis", "simulator_version": "1.2.0", "pipeline": "DiagGen",
        "diagnostics_enabled": True, "run_id": RUN_ID, "archived_at": now(),
        "generation_and_diagnostics_model": "gpt-6-luna", "reasoning_effort": "max",
        "paper_generation_and_diagnostics": {"model": "gpt-5.6-luna", "reasoning_effort": "max"},
        "model_change_reason": "User requested the paper's model family, allowing a newer version.",
        "pipeline_status": state.get("status", "not_initialized"),
        "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest() if source else None,
        "original_input": (QUEUE / "original_input.txt").read_text().strip()
                          if (QUEUE / "original_input.txt").exists() else None,
        "source_to_archive": mapping,
        "note": "Archive copy; absolute paths in the original ledger still refer to the working checkout.",
    })
    if state.get("status") != "success" or not (destination / "asset/final_export_manifest.json").is_file():
        return 4
    return 0


def main():
    command = sys.argv[1]
    if command == "status":
        status(*sys.argv[2:])
    elif command == "archive":
        return archive()
    else:
        raise ValueError(command)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(2)
