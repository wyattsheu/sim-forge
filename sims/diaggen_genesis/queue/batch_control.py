"""Deterministic batch bookkeeping; shell runners own Codex and DiagGen execution."""
from __future__ import annotations

import csv
import fcntl
import io
import json
import hashlib
import shutil
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo


PLAN_SCHEMA = "diaggen-batch-plan-v1"
BATCH_SCHEMA = "diaggen-batch-v1"
STATUSES = ("queued", "running", "success", "failed", "cancelled")
TERMINAL = frozenset(("success", "failed", "cancelled"))
DEFAULT_POLICY = {
    "minimum_free_mib": 24576,
    "allow_compute_sharing": True,
    "check_interval_seconds": 15,
    "max_parallel_jobs": 2,
    "max_jobs_per_gpu": 1,
}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
GPU_UUID = re.compile(r"GPU-[A-Za-z0-9-]+\Z")
REASON = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


def now():
    return datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value) or ".." in value:
        raise ValueError("Invalid job or run identifier")
    return value


def validate_gpu_uuid(value):
    if not isinstance(value, str) or not GPU_UUID.fullmatch(value):
        raise ValueError("Invalid GPU UUID")
    return value


def validate_policy(value):
    if not isinstance(value, dict):
        raise ValueError("GPU policy must be an object")
    policy = dict(DEFAULT_POLICY)
    policy.update(value)
    for key in ("minimum_free_mib", "check_interval_seconds", "max_parallel_jobs", "max_jobs_per_gpu"):
        if type(policy[key]) is not int or policy[key] <= 0:
            raise ValueError("GPU policy integer must be positive")
    if policy["allow_compute_sharing"] is not True:
        raise ValueError("This memory-only queue requires compute sharing")
    return policy


def job_accepts_gpu(job, gpu_uuid):
    """Resumed native states retain their original exact worker GPU token."""
    return job.get("resume_gpu_uuid") in (None, gpu_uuid)


def effective_minimum_free_mib(policy, job):
    return max(policy["minimum_free_mib"], job.get("minimum_free_mib", 0))


def gpu_accepts_job(policy, active, job, gpu):
    """Budget unallocated demand before allowing another job on a busy GPU.

    Existing memory use is already reflected by NVIDIA. Counting each admitted
    job's gate again deliberately leaves headroom for agents that have not yet
    loaded their models. This is admission bookkeeping, not a CUDA reservation.
    """
    assigned = [entry for entry in active if entry["gpu_uuid"] == gpu["uuid"]]
    if len(assigned) >= policy["max_jobs_per_gpu"] or not job_accepts_gpu(job, gpu["uuid"]):
        return False
    budget = effective_minimum_free_mib(policy, job)
    if policy["max_jobs_per_gpu"] > 1:
        budget += sum(effective_minimum_free_mib(policy, entry) for entry in assigned)
    return gpu["free_mib"] >= budget


def query_gpu_csv():
    # A failed or unavailable query is an error, never evidence of free memory.
    return subprocess.run(
        ["nvidia-smi", "--query-gpu=index,uuid,memory.free", "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout


def parse_gpu_csv(value):
    if not isinstance(value, str):
        raise ValueError("Invalid GPU query response")
    records, indices, uuids = [], set(), set()
    for row in csv.reader(io.StringIO(value), strict=True):
        if not row:
            continue
        if len(row) != 3:
            raise ValueError("Invalid GPU query columns")
        index, uuid, free = (column.strip() for column in row)
        if not index.isdecimal() or not free.isdecimal():
            raise ValueError("Invalid GPU memory or index")
        validate_gpu_uuid(uuid)
        index, free = int(index), int(free)
        if index in indices or uuid in uuids:
            raise ValueError("Duplicate GPU query record")
        indices.add(index)
        uuids.add(uuid)
        records.append({"index": index, "uuid": uuid, "free_mib": free})
    if not records:
        raise ValueError("Empty GPU query response")
    return sorted(records, key=lambda record: (-record["free_mib"], record["index"]))


def native_recovery_preflight(root, *, state_path=None, snapshot_dir=None):
    """Use native dependencies in their own process; all checks are read only."""
    command = [str(root / ".conda/hag4r/bin/python"),
               str(root.parent / "diaggen_support/check_diagnostic_retry.py"),
               "--diaggen-root", str(root)]
    command += ["--state-json", str(state_path)] if state_path is not None else ["--snapshot-dir", str(snapshot_dir)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError("Native recovery preflight failed: " + result.stderr.strip()[:1200])
    report = json.loads(result.stdout)
    if not isinstance(report, dict) or report.get("valid") is not True:
        raise ValueError("Native recovery preflight did not establish validity")
    return report


def verified_repair_prefix(state):
    """Recognize only native copied prefixes with matching repair provenance."""
    repair = state.get("route_state", {}).get("active_repair_revision")
    if repair is None:
        return None
    prefixes = {
        "segmentation": ["image_cleanup"],
        "material_inference": ["image_cleanup", "sam3_omnipart_2d_segmentation", "omnipart_generate_parts"],
        "mesh_processing": ["image_cleanup", "sam3_omnipart_2d_segmentation", "omnipart_generate_parts", "hag4r_gpt_staged_material_inference"],
    }
    if not isinstance(repair, dict) or repair.get("route") not in prefixes:
        raise ValueError("Unsupported native repair-prefix metadata")
    active, base = state.get("active_revision"), repair.get("base_revision")
    metadata = state.get("revisions", {}).get(active, {})
    expected = prefixes[repair["route"]]
    if (not isinstance(base, str) or not re.fullmatch(r"revision_[0-9]{4}", base)
            or active != f"revision_{int(base.removeprefix('revision_')) + 1:04d}"
            or repair.get("new_revision") != active or repair.get("copied_stage_prefix") != expected
            or metadata.get("status") != "active" or metadata.get("base_revision") != base
            or metadata.get("rerun_route") != repair["route"] or metadata.get("copied_stage_prefix") != expected
            or state.get("revisions", {}).get(base, {}).get("status") != "superseded"
            or state["revisions"][base].get("superseded_by") != active):
        raise ValueError("Native repair-prefix provenance mismatch")
    return {"base_revision": base, "revision": active, "copied_stage_prefix": expected}


class Queue:
    def __init__(self, base=None, *, gpu_query=None):
        self.base = Path(base).resolve() if base is not None else Path(__file__).resolve().parent.parent
        self.directory = self.base / "queue"
        self.path = self.directory / "batch.json"
        self.plan_path = self.base / "batch_plan.json"
        self.gpu_query = gpu_query or query_gpu_csv

    @contextmanager
    def _locked(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / "batch.lock").open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _validate_job(self, job):
        if not isinstance(job, dict):
            raise ValueError("Job must be an object")
        validate_identifier(job.get("id"))
        validate_identifier(job.get("run_id"))
        value = job.get("input")
        if not isinstance(value, str):
            raise ValueError("Job input must be a relative image path")
        path = Path(value)
        if path.is_absolute() or not path.parts or path.parts[0] != "inputs" or ".." in path.parts:
            raise ValueError("Job input must be inside inputs")
        try:
            (self.base / path).resolve().relative_to((self.base / "inputs").resolve())
        except ValueError:
            raise ValueError("Job input escapes inputs") from None
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            raise ValueError("Only PNG and JPG image inputs are supported")
        digest = job.get("input_sha256")
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
            raise ValueError("Invalid input SHA256")
        if "minimum_free_mib" in job and (type(job["minimum_free_mib"]) is not int or job["minimum_free_mib"] <= 0):
            raise ValueError("Job minimum free memory must be a positive integer")
        if "scheduling_note" in job and (not isinstance(job["scheduling_note"], str) or not REASON.fullmatch(job["scheduling_note"])):
            raise ValueError("Scheduling note must be a short lowercase enum")

        if "execution_mode" in job and job["execution_mode"] not in ("fresh", "resume", "diagnostics_snapshot"):
            raise ValueError("Invalid job execution mode")
        if job.get("execution_mode") == "resume":
            validate_identifier(job.get("resume_id"))
            validate_gpu_uuid(job.get("resume_gpu_uuid"))
            if not isinstance(job.get("resume_state_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", job["resume_state_sha256"]):
                raise ValueError("Invalid resume state digest")
        if job.get("execution_mode") == "diagnostics_snapshot":
            validate_identifier(job.get("snapshot_source_run_id"))
            for key in ("snapshot_state_sha256", "snapshot_source_state_sha256"):
                if not isinstance(job.get(key), str) or not re.fullmatch(r"[a-f0-9]{64}", job[key]):
                    raise ValueError("Invalid diagnostic snapshot digest")

    def _validate_jobs(self, jobs, *, dynamic=False):
        if not isinstance(jobs, list):
            raise ValueError("Jobs must be a list")
        ids, run_ids = set(), set()
        for job in jobs:
            self._validate_job(job)
            if job["id"] in ids or job["run_id"] in run_ids:
                raise ValueError("Duplicate job or run identifier")
            ids.add(job["id"])
            run_ids.add(job["run_id"])
            if dynamic:
                if job.get("status") not in STATUSES:
                    raise ValueError("Invalid job status")
                if type(job.get("attempts")) is not int or job["attempts"] < 0:
                    raise ValueError("Invalid job attempts")
                if job.get("gpu_uuid") is not None:
                    validate_gpu_uuid(job["gpu_uuid"])
                if job["status"] == "running" and job.get("gpu_uuid") is None:
                    raise ValueError("Running job must have a GPU UUID")

    def _load(self):
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != BATCH_SCHEMA:
            raise ValueError("Invalid batch schema")
        value["policy"] = validate_policy(value.get("policy"))
        self._validate_jobs(value.get("jobs"), dynamic=True)
        return value

    def _summary(self, batch):
        jobs, policy = batch["jobs"], batch["policy"]
        counts = {status: sum(job["status"] == status for job in jobs) for status in STATUSES}
        counts["total"] = len(jobs)
        selected = next((job for job in jobs if job["status"] == "running"), None)
        if selected is None:
            selected = next((job for job in jobs if job["status"] == "queued"), None)
        if selected is None and jobs:
            selected = jobs[-1]
        if counts["running"]:
            phase = "running"
            detail = f"Running {counts['running']} Genesis jobs; {counts['queued']} waiting."
        elif counts["queued"]:
            phase = "waiting_gpu"
            minimum = min(effective_minimum_free_mib(policy, job) for job in jobs if job["status"] == "queued")
            detail = f"Waiting for at least {minimum} MiB free GPU memory; compute sharing enabled."
        elif counts["failed"]:
            phase, detail = "failed", f"Batch finished with {counts['failed']} failed jobs."
        elif counts["cancelled"]:
            phase, detail = "cancelled", f"Batch finished with {counts['cancelled']} cancelled jobs."
        else:
            phase, detail = "success", f"All {counts['success']} Genesis jobs completed."
        run_id = selected["run_id"] if selected else None
        workspace = self.base.parents[1]
        return {
            "updated_at": now(), "phase": phase, "detail": detail,
            "simulator": "Genesis", "pipeline": "DiagGen", "run_id": run_id,
            "generation_and_diagnostics_model": "gpt-6-luna", "reasoning_effort": "max",
            "input_directory": str(self.base / "inputs"),
            "working_run_root": str(workspace / "tools/diaggen/outputs/agentic_asset_refinement" / run_id) if run_id else None,
            "results_directory": str(self.base / "runs" / run_id) if run_id else None,
            "watcher_pid": os.environ.get("DIAGGEN_WATCHER_PID"),
            "gpu_uuid": selected.get("gpu_uuid") if selected else None,
            "batch_counts": counts, "policy": policy,
        }

    def _save(self, batch):
        batch["updated_at"] = now()
        atomic_json(self.path, batch)
        atomic_json(self.directory / "status.json", self._summary(batch))

    def init(self):
        with self._locked():
            plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
            if not isinstance(plan, dict) or plan.get("schema_version") != PLAN_SCHEMA:
                raise ValueError("Invalid batch plan schema")
            policy = validate_policy(plan.get("policy"))
            self._validate_jobs(plan.get("jobs"))
            if self.path.exists():
                batch = self._load()
            else:
                batch = {"schema_version": BATCH_SCHEMA, "created_at": now(), "policy": policy, "jobs": []}
            existing = {job["id"] for job in batch["jobs"]}
            for job in plan["jobs"]:
                if job["id"] not in existing:
                    entry = dict(job)
                    entry.update(status="queued", gpu_uuid=None, runner_pid=None, attempts=0,
                                 started_at=None, finished_at=None)
                    batch["jobs"].append(entry)
            batch["policy"] = policy
            self._validate_jobs(batch["jobs"], dynamic=True)
            self._save(batch)
            return batch

    def candidates(self):
        with self._locked():
            # HOLD only pauses new launches; existing runners keep their state.
            if (self.directory / "HOLD").exists():
                return []
            batch = self._load()
            active = [job for job in batch["jobs"] if job["status"] == "running"]
            queued = [job for job in batch["jobs"] if job["status"] == "queued"]
            if len(active) >= batch["policy"]["max_parallel_jobs"] or not queued:
                return []
            records = parse_gpu_csv(self.gpu_query())
            return [record["uuid"] for record in records
                    if any(
                        gpu_accepts_job(batch["policy"], active, job, record)
                        for job in queued)]

    def claim(self, gpu_uuid):
        validate_gpu_uuid(gpu_uuid)
        with self._locked():
            # Recheck here as HOLD may appear after candidate selection.
            if (self.directory / "HOLD").exists():
                return None
            batch = self._load()
            active = [job for job in batch["jobs"] if job["status"] == "running"]
            if len(active) >= batch["policy"]["max_parallel_jobs"]:
                return None
            queued = [job for job in batch["jobs"] if job["status"] == "queued"]
            if not queued:
                return None
            records = parse_gpu_csv(self.gpu_query())
            gpu = next((record for record in records if record["uuid"] == gpu_uuid), None)
            if gpu is None:
                return None
            selected = next((job for job in queued if gpu_accepts_job(batch["policy"], active, job, gpu)), None)
            if selected is None:
                return None
            selected.update(status="running", gpu_uuid=gpu_uuid, runner_pid=None,
                            attempts=selected["attempts"] + 1, started_at=now(), finished_at=None)
            selected.pop("reason", None)
            self._save(batch)
            return selected["id"]

    @staticmethod
    def _job(batch, job_id):
        validate_identifier(job_id)
        selected = next((job for job in batch["jobs"] if job["id"] == job_id), None)
        if selected is None:
            raise ValueError("Unknown job identifier")
        return selected

    def bind(self, job_id, pid):
        if type(pid) is not int or pid <= 0:
            raise ValueError("Runner PID must be a positive integer")
        with self._locked():
            batch = self._load()
            job = self._job(batch, job_id)
            if job["status"] != "running" or job.get("runner_pid") not in (None, pid):
                raise ValueError("Job cannot be bound to this runner")
            job["runner_pid"] = pid
            self._save(batch)

    def info(self, job_id, field):
        if field not in ("input", "run_id", "gpu_uuid", "status", "minimum_free_mib", "execution_mode", "resume_id", "resume_frozen_input", "diagnostics_snapshot_dir", "diagnostics_snapshot_input"):
            raise ValueError("Unsupported job info field")
        with self._locked():
            batch = self._load()
            job = self._job(batch, job_id)
            if field == "execution_mode":
                return job.get(field, "fresh")
            if field == "minimum_free_mib":
                return effective_minimum_free_mib(batch["policy"], job)
            return job.get(field)

    def policy(self, field):
        if field not in DEFAULT_POLICY:
            raise ValueError("Unsupported policy field")
        with self._locked():
            return self._load()["policy"][field]

    def set_minimum(self, job_id, minimum_free_mib, reason):
        """Adjust a stopped job's memory gate while launches are held."""
        if type(minimum_free_mib) is not int or minimum_free_mib <= 0:
            raise ValueError("Job minimum free memory must be a positive integer")
        if not isinstance(reason, str) or not REASON.fullmatch(reason):
            raise ValueError("Scheduling note must be a short lowercase enum")
        with self._locked():
            if not (self.directory / "HOLD").exists():
                raise ValueError("Changing job memory requires queue/HOLD")
            batch = self._load()
            job = self._job(batch, job_id)
            if job["status"] == "running":
                raise ValueError("Running job memory cannot be changed")
            job.update(minimum_free_mib=minimum_free_mib, scheduling_note=reason)
            self._save(batch)
            return {
                "job_id": job_id, "minimum_free_mib": minimum_free_mib,
                "effective_minimum_free_mib": effective_minimum_free_mib(batch["policy"], job),
                "scheduling_note": reason,
            }

    def finish(self, job_id, status, reason=None):
        if status not in TERMINAL:
            raise ValueError("Invalid terminal job status")
        if reason is not None and (not isinstance(reason, str) or not REASON.fullmatch(reason)):
            raise ValueError("Reason must be a short lowercase enum")
        with self._locked():
            batch = self._load()
            job = self._job(batch, job_id)
            if job["status"] == status:
                return
            if job["status"] != "running":
                raise ValueError("Only a running job can finish")
            job.update(status=status, finished_at=now())
            if reason is not None:
                job["reason"] = reason
            self._save(batch)

    def retry(self, job_id, new_run_id, reason, *, diagnostics_snapshot=False, reuse_snapshot_origin=False):
        """Archive failed launcher logs and explicitly queue a fresh native run."""
        validate_identifier(new_run_id)
        if not isinstance(reason, str) or not REASON.fullmatch(reason):
            raise ValueError("Retry reason must be a short lowercase enum")
        with self._locked():
            if not (self.directory / "HOLD").exists():
                raise ValueError("Retry requires queue/HOLD until repair is reviewed")
            batch = self._load()
            job = self._job(batch, job_id)
            if job["status"] != "failed":
                raise ValueError("Only a failed job can be retried")
            snapshot_job = job
            if reuse_snapshot_origin:
                if not diagnostics_snapshot or job.get("execution_mode") != "diagnostics_snapshot":
                    raise ValueError("Origin retry requires a previously admitted diagnostics snapshot")
                source_id = validate_identifier(job.get("snapshot_source_run_id"))
                native = self.base.parents[1] / "tools/diaggen/outputs/agentic_asset_refinement"
                current_root = native / job["run_id"]
                current_path = current_root / "state.json"
                if current_root.is_symlink() or current_path.is_symlink() or not current_path.is_file():
                    raise ValueError("Current failed snapshot state is missing or unsafe")
                current_state = json.loads(current_path.read_text())
                if current_state.get("run_root") != str(current_root):
                    raise ValueError("Current snapshot state root differs")
                if current_state.get("status") == "success" or current_state.get("accepted_revision") is not None:
                    raise ValueError("Accepted snapshot must be reconciled, not restarted from its origin")
                self._assert_snapshot_ownership_closed(current_state, current_root)
                source_path = native / source_id / "state.json"
                if (not source_path.is_file() or source_path.is_symlink()
                        or hashlib.sha256(source_path.read_bytes()).hexdigest() != job.get("snapshot_source_state_sha256")):
                    raise ValueError("Previously admitted snapshot origin changed")
                snapshot_job = {**job, "run_id": source_id}
            snapshot_details = self._snapshot_details(snapshot_job) if diagnostics_snapshot else None
            previous_run_id = job["run_id"]
            used_run_ids = {entry["run_id"] for entry in batch["jobs"]}
            for entry in batch["jobs"]:
                history = entry.get("attempts_history", [])
                if not isinstance(history, list) or not all(isinstance(item, dict) for item in history):
                    raise ValueError("Invalid attempts history")
                used_run_ids.update(item.get("run_id") for item in history)
            if new_run_id in used_run_ids:
                raise ValueError("Retry requires a new unique run identifier")
            if (self.base.parents[1] / "tools/diaggen/outputs/agentic_asset_refinement" / new_run_id).exists():
                raise ValueError("Retry requires an unused native run root")
            runner_pid = job.get("runner_pid")
            if runner_pid is not None:
                if type(runner_pid) is not int or runner_pid <= 0:
                    raise ValueError("Invalid prior runner PID")
                try:
                    os.kill(runner_pid, 0)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    raise ValueError("Prior runner may still be alive") from None
                else:
                    raise ValueError("Prior runner is still alive")
            source = self.directory / "jobs" / job_id
            destination = self.directory / "job_history" / job_id / previous_run_id
            for path in (source, destination):
                try:
                    path.resolve().relative_to(self.directory.resolve())
                except ValueError:
                    raise ValueError("Job log path escapes queue") from None
            if source.is_symlink() or not source.is_dir():
                raise ValueError("Completed job log directory is missing or unsafe")
            if destination.exists() or destination.is_symlink():
                raise ValueError("Prior job history directory already exists")
            destination.parent.mkdir(parents=True, exist_ok=True)
            mapping = {
                "job_id": job_id, "previous_run_id": previous_run_id,
                "run_id": new_run_id, "retry_reason": reason,
                "queue_logs_from": str(source.relative_to(self.directory)),
                "queue_logs_to": str(destination.relative_to(self.directory)),
            }
            previous = dict(job)
            history = list(previous.pop("attempts_history", []))
            previous.update(retry_reason=reason, requeued_at=now(),
                            queue_history_directory=mapping["queue_logs_to"])
            history.append(previous)
            job.update(run_id=new_run_id, status="queued", gpu_uuid=None, runner_pid=None,
                       started_at=None, finished_at=None, attempts_history=history, execution_mode="fresh")
            for field in ("resume_id", "resume_gpu_uuid", "resume_state_sha256", "resume_frozen_input", "resume_reason"):
                job.pop(field, None)
            for field in ("diagnostics_snapshot_dir", "diagnostics_snapshot_input", "snapshot_state_sha256", "snapshot_source_state_sha256", "snapshot_source_run_id"):
                job.pop(field, None)
            if snapshot_details is not None:
                job.update(execution_mode="diagnostics_snapshot", **snapshot_details)
                mapping.update(snapshot_details)
            job.pop("reason", None)
            # All queue operations honor batch.lock, so this rename cannot collide
            # with another retry. Native output and its completed archive stay put.
            source.rename(destination)
            try:
                batch["updated_at"] = now()
                atomic_json(self.path, batch)
            except BaseException:
                destination.rename(source)
                raise
            # The batch file is the commit point; this derived view can be rebuilt.
            atomic_json(self.directory / "status.json", self._summary(batch))
            return mapping

    @staticmethod
    def _assert_snapshot_ownership_closed(state, source_root):
        ownership = [state]
        ownership_path = Path(str(state.get("paths", {}).get("sim_diagnostics_dir", ""))) / "runtime_ownership.json"
        if ownership_path.is_file():
            if ownership_path.is_symlink() or not ownership_path.resolve().is_relative_to(source_root.resolve()):
                raise ValueError("Snapshot diagnostic ownership record is unsafe")
            ownership.append(json.loads(ownership_path.read_text()))
        for ledger in ownership:
            for key, field, closed in (
                ("diagnostic_runtime_attachments", "status", ("completed", "failed", "expired", "superseded", "halted")),
                ("diagnostic_runtime_sessions", "lifecycle_state", ("closed", "closed_failed")),
            ):
                records = ledger.get(key, [])
                if not isinstance(records, list) or any(not isinstance(record, dict) or record.get(field) not in closed for record in records):
                    raise ValueError("Snapshot source diagnostic ownership is still active or malformed")

    def _snapshot_details(self, job, *, check_digest=False):
        root = self.base.parents[1] / "tools" / "diaggen"
        source_id = job["snapshot_source_run_id"] if check_digest else job["run_id"]
        source_root = root / "outputs/agentic_asset_refinement" / source_id
        source_state = source_root / "state.json"
        if source_root.is_symlink() or source_state.is_symlink() or not source_state.is_file():
            raise ValueError("Snapshot recovery needs a safe failed source state")
        raw = source_state.read_bytes()
        state = json.loads(raw)
        if (state.get("status") != "failed" or state.get("run_root") != str(source_root)
                or state.get("diagnostics", {}).get("terminal", {}).get("business_outcome", {}).get("status") != "business_halt"):
            raise ValueError("Snapshot recovery requires a preserved diagnostic business halt")
        self._assert_snapshot_ownership_closed(state, source_root)
        revision = state.get("active_revision")
        if not isinstance(revision, str) or not IDENTIFIER.fullmatch(revision):
            raise ValueError("Snapshot source has no valid active revision")
        snapshot = source_root / "revisions" / revision
        if snapshot.is_symlink() or not snapshot.is_dir() or not snapshot.resolve().is_relative_to(source_root.resolve()):
            raise ValueError("Snapshot revision directory is missing or unsafe")
        frozen = Path(str(state.get("inputs", {}).get("source_image", "")))
        if (not frozen.is_absolute() or frozen.is_symlink() or not frozen.is_file()
                or not frozen.resolve().is_relative_to((root / "outputs/inputs").resolve())
                or hashlib.sha256(frozen.read_bytes()).hexdigest() != job.get("input_sha256")):
            raise ValueError("Snapshot source frozen input is missing or changed")
        report = native_recovery_preflight(root, snapshot_dir=snapshot)
        details = {"snapshot_source_run_id": source_id, "diagnostics_snapshot_dir": str(snapshot),
                   "diagnostics_snapshot_input": str(frozen),
                   "snapshot_source_state_sha256": hashlib.sha256(raw).hexdigest(),
                   "snapshot_state_sha256": report["snapshot_state_sha256"]}
        if check_digest and any(job.get(key) != value for key, value in details.items()):
            raise ValueError("Diagnostic snapshot changed after admission")
        return details

    def diagnostics_snapshot(self, job_id, new_run_id, reason):
        return self.retry(job_id, new_run_id, reason, diagnostics_snapshot=True)

    def diagnostics_snapshot_origin(self, job_id, new_run_id, reason):
        return self.retry(job_id, new_run_id, reason, diagnostics_snapshot=True, reuse_snapshot_origin=True)

    def validate_snapshot(self, job_id):
        with self._locked():
            job = self._job(self._load(), job_id)
            if job.get("execution_mode") != "diagnostics_snapshot" or job.get("status") not in ("queued", "running"):
                raise ValueError("Job is not an admitted diagnostics snapshot recovery")
            return self._snapshot_details(job, check_digest=True)


    @staticmethod
    def _require_dead_runner(job):
        pid = job.get("runner_pid")
        if type(pid) is not int or pid <= 0:
            raise ValueError("Resume requires a recorded prior runner PID")
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            raise ValueError("Prior runner may still be alive") from None
        raise ValueError("Prior runner is still alive")

    def _resume_details(self, job, *, check_digest=False):
        """Read-only admission for a quiescent native run; never repair its ledgers."""
        root = self.base.parents[1] / "tools" / "diaggen"
        run_root = root / "outputs" / "agentic_asset_refinement" / job["run_id"]
        state_path = run_root / "state.json"
        if state_path.is_symlink() or not state_path.is_file() or not state_path.resolve().is_relative_to(run_root.resolve()):
            raise ValueError("Resume requires a safe existing native state")
        state_bytes = state_path.read_bytes()
        digest = hashlib.sha256(state_bytes).hexdigest()
        if check_digest and digest != job.get("resume_state_sha256"):
            raise ValueError("Native state changed after resume admission")
        state = json.loads(state_bytes)
        repair_prefix = verified_repair_prefix(state) if isinstance(state, dict) else None
        export_repair_snapshot = (isinstance(state, dict) and state.get("run_mode") == "post_mesh_processing_diagnostics"
                                 and state.get("diagnostics_reroute_and_export") is True
                                 and state.get("diagnostics_stage_only") is False and repair_prefix is not None)
        if (not isinstance(state, dict) or state.get("schema_version") != "2026-07-skill-suite-runtime-state-v2"
                or state.get("run_id") != job["run_id"] or state.get("run_root") != str(run_root)
                or state.get("repo_root") != str(root) or not (state.get("run_mode") == "full_image" or export_repair_snapshot)
                or state.get("runtime_kind") != "codex_skill" or state.get("status") not in ("seeded", "running", "failed")
                or state.get("diagnostics", {}).get("enabled") is not True):
            raise ValueError("Native state is incompatible with same-run Genesis resume")
        gpu = state.get("worker_isolation", {}).get("gpu_binding", {}).get("effective_cuda_visible_devices")
        if (not isinstance(gpu, str) or not re.fullmatch(r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", gpu)
                or gpu != job.get("gpu_uuid") or (check_digest and gpu != job.get("resume_gpu_uuid"))):
            raise ValueError("Resume must preserve the exact persisted worker GPU UUID")
        selected_file = self.directory / "jobs" / job["id"] / "selected_input.txt"
        if selected_file.is_symlink() or not selected_file.is_file():
            raise ValueError("Frozen input record is missing or unsafe")
        frozen = Path(selected_file.read_text(encoding="utf-8").strip())
        declared = state.get("inputs", {}).get("source_image")
        if (not frozen.is_absolute() or frozen.is_symlink() or not frozen.is_file()
                or not frozen.resolve().is_relative_to((root / "outputs" / "inputs").resolve())
                or str(frozen) != declared or str(frozen) != state.get("paths", {}).get("source_image")
                or hashlib.sha256(frozen.read_bytes()).hexdigest() != job.get("input_sha256")):
            raise ValueError("Frozen native input is missing, changed, or disagrees with the run")
        planned, stages = state.get("planned_global_stage_sequence"), state.get("stages")
        if (not isinstance(planned, list) or not planned or len(planned) != len(set(planned))
                or not all(isinstance(name, str) for name in planned) or not isinstance(stages, dict)
                or set(planned) != set(stages)):
            raise ValueError("Invalid native stage inventory")
        completed, unfinished = [], []
        for name in planned:
            stage = stages[name]
            if not isinstance(stage, dict):
                raise ValueError("Invalid native stage record")
            if stage.get("status") in ("success", "reused") and stage.get("ok") is True:
                if stage.get("status") == "reused":
                    if (repair_prefix is None or name not in repair_prefix["copied_stage_prefix"]
                            or stage.get("stats", {}).get("reused_from_revision") != repair_prefix["base_revision"]
                            or stage.get("outputs", {}).get("reused_from_revision") != repair_prefix["base_revision"]):
                        raise ValueError("Reused stage lacks verified native repair-prefix provenance")
                if unfinished:
                    raise ValueError("Successful native stages must form a prefix")
                expected = stage.get("artifacts", {}).get("expected")
                if not isinstance(expected, list) or not expected:
                    raise ValueError("Successful upstream stage has no artifact inventory")
                for artifact in expected:
                    if artifact.get("required", True):
                        path = Path(str(artifact.get("path", "")))
                        if (not path.is_absolute() or path.is_symlink() or not path.is_file() or path.stat().st_size <= 0
                                or not path.resolve().is_relative_to(run_root.resolve())):
                            raise ValueError("A required upstream artifact is missing or unsafe")
                        if (stage.get("status") == "reused" and not path.is_relative_to(
                                run_root / "revisions" / repair_prefix["revision"])):
                            raise ValueError("Reused artifact is not scoped to its active repair revision")
                completed.append(name)
            else:
                if stage.get("ok") is not False or stage.get("status") not in ("pending", "pending_retry"):
                    raise ValueError("Resume cannot reopen a failed, halted, or running native stage")
                if stage.get("status") == "pending_retry" and (unfinished or name != "genesis_live_diagnostic_loop"):
                    raise ValueError("Only the next diagnostic stage may be pending_retry")
                unfinished.append(name)
        cleanup_candidates = []
        if not completed and unfinished and unfinished[0] == "image_cleanup":
            # A stopped cleanup child may leave two bounded, unregistered images.
            # Their visual validation must be redone by a fresh owning child.
            revision = state.get("active_revision")
            if not isinstance(revision, str) or not IDENTIFIER.fullmatch(revision):
                raise ValueError("Pending cleanup recovery needs a valid revision")
            for index in (1, 2):
                candidate = run_root / "revisions" / revision / "image_cleanup" / f"attempt_{index:02d}.png"
                if (candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size <= 0
                        or not candidate.resolve().is_relative_to(run_root.resolve())):
                    raise ValueError("Pending cleanup recovery requires two existing bounded candidates")
                cleanup_candidates.append(str(candidate))
        if ((completed and completed[0] != "image_cleanup") or (not completed and not cleanup_candidates) or not unfinished
                or state.get("completed_global_stage_sequence") != completed):
            raise ValueError("Resume requires an intact successful cleanup prefix and unfinished stages")
        runtime = state.get("stage_runtime", {})
        if not isinstance(runtime, dict) or any(isinstance(record, dict) and record.get("terminal", {}).get("status") == "halted" for record in runtime.values()):
            raise ValueError("Resume cannot erase a halted stage terminal")
        if cleanup_candidates and any(isinstance(record, dict) and record.get("terminal") is not None for record in runtime.values()):
            raise ValueError("Pending cleanup recovery must have no existing stage terminal")
        if "sam3_omnipart_2d_segmentation" in completed:
            paths = state.get("paths", {})
            for key, count_key in (("segmentation_manifest_path", "sam3_pre_postprocess_mask_count"), ("sam3_raw_metadata_path", "mask_count")):
                record_path = Path(str(paths.get(key, "")))
                if not record_path.is_file() or not record_path.resolve().is_relative_to(run_root.resolve()):
                    raise ValueError("Validated raw SAM3 evidence is missing")
                count = json.loads(record_path.read_text(encoding="utf-8")).get(count_key)
                if type(count) is not int or count <= 0:
                    raise ValueError("Resume rejects an empty raw SAM3 prediction")
        diagnostics = state["diagnostics"]
        terminal = diagnostics.get("terminal")
        ownership = [state]
        ownership_path = Path(str(state.get("paths", {}).get("sim_diagnostics_dir", ""))) / "runtime_ownership.json"
        if ownership_path.is_file():
            if ownership_path.is_symlink() or not ownership_path.resolve().is_relative_to(run_root.resolve()):
                raise ValueError("Diagnostic ownership record is unsafe")
            ownership.append(json.loads(ownership_path.read_text(encoding="utf-8")))
        if stages[unfinished[0]].get("status") == "pending_retry":
            if not isinstance(terminal, dict) or len(ownership) != 2:
                raise ValueError("Diagnostic retry needs durable terminal and closed ownership")
            business, operational = terminal.get("business_outcome", {}), terminal.get("operational_outcome", {})
            if (terminal.get("status") != "retryable" or business.get("status") not in ("not_authored", "pending")
                    or business.get("recommendation") is not None or operational.get("retryable") is not True
                    or operational.get("status") not in ("cleanup_retryable", "lease_expired_retryable")
                    or operational.get("cleanup_status") != "complete"):
                raise ValueError("Diagnostics has no clean operational retry without a business recommendation")
        elif terminal is not None:
            raise ValueError("Ordinary pending resume must not contain a diagnostic terminal")
        for ledger in ownership:
            for key, field, closed in (
                ("diagnostic_runtime_attachments", "status", ("completed", "failed", "expired", "superseded")),
                ("diagnostic_runtime_sessions", "lifecycle_state", ("closed", "closed_failed")),
            ):
                records = ledger.get(key, [])
                if not isinstance(records, list) or any(not isinstance(record, dict) or record.get(field) not in closed for record in records):
                    raise ValueError("Diagnostic ownership is still active or malformed")
        if stages[unfinished[0]].get("status") == "pending_retry":
            native_recovery_preflight(root, state_path=state_path)
        return {"run_root": str(run_root), "run_id": job["run_id"], "gpu_uuid": gpu,
                "frozen_input": str(frozen), "input_sha256": job["input_sha256"],
                "state_sha256": digest, "completed_stage_prefix": completed,
                "diagnostic_operational_retry": stages[unfinished[0]].get("status") == "pending_retry",
                "existing_cleanup_candidates": cleanup_candidates}

    def validate_resume(self, job_id):
        with self._locked():
            job = self._job(self._load(), job_id)
            if job.get("execution_mode") != "resume" or job.get("status") not in ("queued", "running"):
                raise ValueError("Job is not an admitted same-run resume")
            return self._resume_details(job, check_digest=True)

    def resume(self, job_id, resume_id, reason):
        """Queue a reviewed same-run continuation without altering native outputs."""
        validate_identifier(resume_id)
        if len(resume_id) > 64 or not isinstance(reason, str) or not REASON.fullmatch(reason):
            raise ValueError("Invalid resume identifier or reason")
        with self._locked():
            if not (self.directory / "HOLD").exists():
                raise ValueError("Resume requires queue/HOLD until repair is reviewed")
            batch = self._load()
            job = self._job(batch, job_id)
            if job.get("status") != "failed":
                raise ValueError("Only a failed stopped job may resume")
            self._require_dead_runner(job)
            details = self._resume_details(job)
            source = self.directory / "jobs" / job_id
            destination = self.directory / "job_history" / job_id / (job["run_id"] + "__resume_" + resume_id)
            archive = self.base / "runs" / job["run_id"]
            archive_history = self.base / "runs" / "resume_history" / job["run_id"] / resume_id
            for path, boundary in ((source, self.directory), (destination, self.directory), (archive, self.base / "runs"), (archive_history, self.base / "runs")):
                if path.is_symlink() or not path.resolve().is_relative_to(boundary.resolve()):
                    raise ValueError("Resume history path is unsafe")
            if not source.is_dir() or destination.exists() or archive_history.exists() or (archive.exists() and not archive.is_dir()):
                raise ValueError("Resume history is missing or already exists")
            original_input = source / "original_input.txt"
            if original_input.is_symlink() or not original_input.is_file():
                raise ValueError("Original input provenance record is missing")
            mapping = {"job_id": job_id, "run_id": job["run_id"], "resume_id": resume_id, "resume_reason": reason,
                       "queue_history_directory": str(destination.relative_to(self.directory)), **details}
            mapping["prior_child_last_message"] = str(destination / "last_message.txt")
            previous = dict(job)
            history = list(previous.pop("attempts_history", []))
            previous.update(requeued_at=now(), resume_reason=reason, queue_history_directory=mapping["queue_history_directory"])
            history.append(previous)
            job.update(status="queued", runner_pid=None, started_at=None, finished_at=None, attempts_history=history,
                       execution_mode="resume", resume_id=resume_id, resume_reason=reason, resume_gpu_uuid=details["gpu_uuid"],
                       resume_state_sha256=details["state_sha256"], resume_frozen_input=details["frozen_input"])
            job.pop("reason", None)
            destination.parent.mkdir(parents=True, exist_ok=True)
            moved_archive = False
            source.rename(destination)
            try:
                source.mkdir()
                for filename in ("selected_input.txt", "original_input.txt", "selected_gpu.txt"):
                    prior = destination / filename
                    if prior.is_symlink() or not prior.is_file():
                        raise ValueError("Prior input or GPU provenance is missing or unsafe")
                    shutil.copy2(prior, source / filename)
                atomic_json(source / "resume.json", mapping)
                if archive.exists():
                    archive_history.parent.mkdir(parents=True, exist_ok=True)
                    archive.rename(archive_history)
                    moved_archive = True
                batch["updated_at"] = now()
                atomic_json(self.path, batch)
            except BaseException:
                if moved_archive:
                    archive_history.rename(archive)
                if source.exists():
                    shutil.rmtree(source)
                destination.rename(source)
                raise
            atomic_json(self.directory / "status.json", self._summary(batch))
            return mapping

    def summary(self):
        with self._locked():
            summary = self._summary(self._load())
            atomic_json(self.directory / "status.json", summary)
            return summary

    def done(self):
        with self._locked():
            return all(job["status"] in TERMINAL for job in self._load()["jobs"])

    def cancel(self):
        with self._locked():
            batch = self._load()
            for job in batch["jobs"]:
                if job["status"] == "queued":
                    job.update(status="cancelled", finished_at=now(), reason="queue_cancelled")
            self._save(batch)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise ValueError("A batch command is required")
    queue, command, rest = Queue(), args[0], args[1:]
    if command == "init" and not rest:
        queue.init()
    elif command == "candidates" and not rest:
        for gpu_uuid in queue.candidates():
            print(gpu_uuid)
    elif command == "claim" and len(rest) == 1:
        job_id = queue.claim(rest[0])
        if job_id is None:
            return 3
        print(job_id)
    elif command == "bind" and len(rest) == 2:
        queue.bind(rest[0], int(rest[1]))
    elif command == "info" and len(rest) == 2:
        value = queue.info(*rest)
        if value is not None:
            print(value)
    elif command == "policy" and len(rest) == 1:
        value = queue.policy(rest[0])
        print(str(value).lower() if isinstance(value, bool) else value)
    elif command == "set-minimum" and len(rest) == 3:
        print(json.dumps(queue.set_minimum(rest[0], int(rest[1]), rest[2]), ensure_ascii=False))
    elif command == "finish" and len(rest) in (2, 3):
        queue.finish(*rest)
    elif command == "retry" and len(rest) == 3:
        print(json.dumps(queue.retry(*rest), ensure_ascii=False))
    elif command == "resume" and len(rest) == 3:
        print(json.dumps(queue.resume(*rest), ensure_ascii=False))
    elif command == "validate-resume" and len(rest) == 1:
        print(json.dumps(queue.validate_resume(*rest), ensure_ascii=False))
    elif command == "diagnostics-snapshot" and len(rest) == 3:
        print(json.dumps(queue.diagnostics_snapshot(*rest), ensure_ascii=False))
    elif command == "diagnostics-snapshot-origin" and len(rest) == 3:
        print(json.dumps(queue.diagnostics_snapshot_origin(*rest), ensure_ascii=False))
    elif command == "validate-snapshot" and len(rest) == 1:
        print(json.dumps(queue.validate_snapshot(*rest), ensure_ascii=False))
    elif command == "summary" and not rest:
        print(json.dumps(queue.summary(), ensure_ascii=False))
    elif command == "done" and not rest:
        return 0 if queue.done() else 1
    elif command == "cancel" and not rest:
        queue.cancel()
    else:
        raise ValueError("Invalid batch command or arguments")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        # NVIDIA stderr and arbitrary exception text are intentionally excluded.
        print(f"batch_control: {type(error).__name__}; command failed safely", file=sys.stderr)
        sys.exit(2)
