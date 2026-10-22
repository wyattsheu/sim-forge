#!/usr/bin/env python3
"""Recover failed queue bookkeeping for an independently verified completed export.

No generation, simulator, GPU, native-state, or service operations occur here.
Existing failure evidence is copied before the standard archive is refreshed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from batch_control import Queue, atomic_json, now, validate_identifier


SCHEMA = "diaggen-export-queue-recovery-v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_object(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"Expected JSON object: {path}")
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def runner_alive(pid):
    require(type(pid) is int and pid > 0, "A valid prior runner PID is required")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def native_validator(run_root, *, diaggen_root):
    sys.path.insert(0, str(diaggen_root.parent / "diaggen_support"))
    from validate_completed_export import validate_completed_export
    return validate_completed_export(run_root, diaggen_root=diaggen_root)


def archive_existing(queue, job):
    workspace = queue.base.parents[1]
    environment = dict(os.environ)
    environment.update(DIAGGEN_JOB_QUEUE_DIR=str(queue.directory / "jobs" / job["id"]),
                       DIAGGEN_QUEUE_RUN_ID=job["run_id"], PYTHONNOUSERSITE="1",
                       PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([str(workspace / "tools/diaggen/.conda/hag4r/bin/python"),
                    str(queue.directory / "support.py"), "archive"],
                   env=environment, check=True, capture_output=True, text=True, timeout=1800)


def snapshot_failure(queue, job, report):
    """Copy only existing evidence; absence is explicitly recorded in inventory."""
    exported_revision = report.get("exported_revision") or report.get("accepted_revision")
    validate_identifier(exported_revision)
    recovery = queue.directory / "recovery_history" / job["id"] / job["run_id"] / uuid.uuid4().hex
    require(not recovery.exists(), "Recovery history directory already exists")
    recovery.mkdir(parents=True)
    archive = queue.base / "runs" / job["run_id"]
    locations = {
        "root_status_before.json": queue.directory / "status.json",
        "job_status_before.json": queue.directory / "jobs" / job["id"] / "status.json",
        "completion_validation_before.json": queue.directory / "jobs" / job["id"] / "completion_validation.json",
        "archive_manifest_before.json": archive / "manifest.json",
        "archive_trace_state_before.json": archive / "trace/state.json",
        "archive_revision_state_before.json": archive / "trace/revisions" / exported_revision / "state.json",
    }
    inventory = {}
    for name, source in locations.items():
        require(not source.is_symlink(), f"Unsafe evidence symlink: {source}")
        if source.exists():
            require(source.is_file(), f"Evidence is not a regular file: {source}")
            shutil.copy2(source, recovery / name)
            inventory[name] = {"source": str(source), "existed": True,
                               "sha256": hashlib.sha256((recovery / name).read_bytes()).hexdigest()}
        else:
            inventory[name] = {"source": str(source), "existed": False}
    atomic_json(recovery / "batch_job_before.json", job)
    atomic_json(recovery / "validation_report.json", report)
    atomic_json(recovery / "snapshot_inventory.json", inventory)
    return recovery


def update_job_view(queue, job, recovery, report):
    path = queue.directory / "jobs" / job["id"] / "status.json"
    view = read_object(path) if path.is_file() else {}
    view.update(phase="success", updated_at=now(), run_id=job["run_id"],
                detail="Existing native export independently verified and archived; prior failure evidence preserved",
                completion_recovery=recovery)
    atomic_json(path, view)
    atomic_json(path.parent / "completion_validation.json", report)


def reconcile_export(job_id, *, base=None, validator=None, archive_runner=None, pid_probe=None):
    validate_identifier(job_id)
    queue = Queue(base)
    validator = validator or native_validator
    archive_runner = archive_runner or archive_existing
    pid_probe = pid_probe or runner_alive
    with queue._locked():
        batch = queue._load()
        original = copy.deepcopy(queue._job(batch, job_id))
        require(original["status"] in {"failed", "success"}, "Only a failed job may be recovered")
        if original["status"] == "success":
            require(isinstance(original.get("completion_recovery"), dict), "Success was not produced by export recovery")
        require(not pid_probe(original.get("runner_pid")), "Prior runner is still alive")

    workspace = queue.base.parents[1]
    diaggen = workspace / "tools/diaggen"
    native_run = diaggen / "outputs/agentic_asset_refinement" / original["run_id"]
    report = validator(native_run, diaggen_root=diaggen)
    require(report.get("valid") is True and report.get("run_id") == original["run_id"]
            and report.get("run_root") == str(native_run), "Validated run does not match queue job")
    native_state = read_object(native_run / "state.json")
    require(native_state.get("status") == "success", "Native run must be settled successfully before queue recovery")
    require(native_state.get("run_root") == str(native_run), "Native run-root mismatch")
    require(hashlib.sha256((native_run / "state.json").read_bytes()).hexdigest() == report.get("state_sha256"),
            "Native state changed after validation")
    report_digest = digest(report)

    with queue._locked():
        batch = queue._load()
        current = queue._job(batch, job_id)
        require(current == original, "Job changed during validation; no recovery performed")
        require(not pid_probe(current.get("runner_pid")), "Prior runner became active")
        if current["status"] == "success":
            recovery = current["completion_recovery"]
            require(recovery.get("run_id") == current["run_id"]
                    and recovery.get("validation_sha256") == report_digest,
                    "Successful recovery validation no longer matches")
            # Repair derived views if a prior invocation stopped after its batch commit.
            update_job_view(queue, current, recovery, report)
            atomic_json(queue.directory / "status.json", queue._summary(batch))
            return {"schema_version": SCHEMA, "job_id": job_id, "run_id": current["run_id"],
                    "recovered": False, "already_recovered": True, "evidence_directory": recovery["evidence_directory"]}
        evidence = snapshot_failure(queue, original, report)

    # This subprocess only copies existing outputs through the established archive.
    # Failed or partial archive attempts leave queue failure state and snapshots intact.
    archive_runner(queue, original)
    destination = queue.base / "runs" / original["run_id"]
    archived_manifest = read_object(destination / "manifest.json")
    archived_state = read_object(destination / "trace/state.json")
    require(archived_manifest.get("run_id") == original["run_id"]
            and archived_manifest.get("pipeline_status") == "success"
            and archived_state.get("status") == "success"
            and archived_state.get("run_root") == str(native_run), "Refreshed archive is not a successful matching run")
    require(hashlib.sha256((destination / "trace/state.json").read_bytes()).hexdigest() == report["state_sha256"],
            "Archived state differs from verified native state")
    exported_manifest = destination / "asset/final_export_manifest.json"
    require(exported_manifest.is_file() and hashlib.sha256(exported_manifest.read_bytes()).hexdigest()
            == report["manifest_sha256"], "Archived final export manifest does not match verified source")
    require(not any(path.is_symlink() for path in (destination / "asset").rglob("*")),
            "Archived asset contains symlinks")
    inventory = {path.relative_to(destination / "asset").as_posix()
                 for path in (destination / "asset").rglob("*") if path.is_file()}
    require(inventory == set(report["artifact_sha256"]) | {"final_export_manifest.json"},
            "Archived asset inventory differs from verified source")
    for name, expected in report["artifact_sha256"].items():
        path = destination / "asset" / name
        require(path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                f"Archived asset differs from verified source: {name}")

    with queue._locked():
        batch = queue._load()
        current = queue._job(batch, job_id)
        require(current == original and current["status"] == "failed", "Job changed during archival; queue left untouched")
        require(not pid_probe(current.get("runner_pid")), "Prior runner became active")
        recovery = {
            "schema_version": SCHEMA, "run_id": original["run_id"], "recovered_at": now(),
            "previous_job": original, "validation_sha256": report_digest,
            "previous_job_status": read_object(evidence / "job_status_before.json")
                                   if (evidence / "job_status_before.json").is_file() else None,
            "manifest_sha256": report["manifest_sha256"],
            "evidence_directory": str(evidence.relative_to(queue.directory)),
        }
        current.update(status="success", reason="verified_export_recovered", completion_recovery=recovery)
        # Attempts, attempts_history, runner PID, GPU record, and original times stay unchanged.
        queue._save(batch)
        update_job_view(queue, current, recovery, report)
        return {"schema_version": SCHEMA, "job_id": job_id, "run_id": current["run_id"],
                "recovered": True, "already_recovered": False, "evidence_directory": recovery["evidence_directory"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(reconcile_export(args.job_id), ensure_ascii=False, indent=2))
    except Exception as error:
        print(json.dumps({"schema_version": SCHEMA, "recovered": False,
                          "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
