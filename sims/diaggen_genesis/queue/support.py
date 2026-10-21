"""Deterministic queue bookkeeping; the Codex CLI owns the DiagGen pipeline."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

QUEUE = Path(__file__).resolve().parent
BASE = QUEUE.parent
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


def input_path():
    explicit = QUEUE / "input_path.txt"
    if explicit.exists():
        path = Path(explicit.read_text().strip()).expanduser()
    else:
        paths = [p for p in (BASE / "inputs").iterdir()
                 if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg")]
        if len(paths) != 1:
            raise ValueError("Place exactly one PNG/JPG in inputs/, or set queue/input_path.txt")
        path = paths[0]
    from PIL import Image
    with Image.open(path) as image:
        image.verify()
    print(path.resolve())


def select_gpu(gpu_csv, process_csv, minimum_mib):
    busy = {row[0].strip() for row in csv.reader(io.StringIO(process_csv)) if row}
    candidates, snapshot = [], []
    for row in csv.reader(io.StringIO(gpu_csv)):
        if not row or len(row) != 3:
            continue
        index, uuid, free = (item.strip() for item in row)
        free = int(free)
        record = {"index": int(index), "uuid": uuid, "free_mib": free,
                  "has_compute_process": uuid in busy}
        snapshot.append(record)
        if free >= minimum_mib and uuid not in busy:
            candidates.append(record)
    candidates.sort(key=lambda record: record["free_mib"], reverse=True)
    return (candidates[0] if candidates else None), snapshot


def probe():
    def query(fields, kind):
        return subprocess.run(
            ["nvidia-smi", f"--query-{kind}={fields}", "--format=csv,noheader,nounits"],
            check=True, text=True, capture_output=True, timeout=20,
        ).stdout
    # Fail closed if either query fails; never infer an idle GPU from an error.
    candidate, snapshot = select_gpu(
        query("index,uuid,memory.free", "gpu"),
        query("gpu_uuid,pid", "compute-apps"),
        int(os.environ.get("DIAGGEN_MIN_FREE_MIB", "65536")),
    )
    write_json(QUEUE / "gpu_snapshot.json", {"checked_at": now(), "gpus": snapshot})
    if not candidate:
        return 3
    print(candidate["uuid"])
    return 0


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
    elif command == "input":
        input_path()
    elif command == "probe":
        return probe()
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
