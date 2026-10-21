"""Deterministic batch bookkeeping; shell runners own Codex and DiagGen execution."""
from __future__ import annotations

import csv
import fcntl
import io
import json
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
    for key in ("minimum_free_mib", "check_interval_seconds", "max_parallel_jobs"):
        if type(policy[key]) is not int or policy[key] <= 0:
            raise ValueError("GPU policy integer must be positive")
    if policy["allow_compute_sharing"] is not True:
        raise ValueError("This memory-only queue requires compute sharing")
    return policy


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
            detail = f"Waiting for at least {policy['minimum_free_mib']} MiB free GPU memory; compute sharing enabled."
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
            if len(active) >= batch["policy"]["max_parallel_jobs"] or not any(job["status"] == "queued" for job in batch["jobs"]):
                return []
            used = {job["gpu_uuid"] for job in active}
            records = parse_gpu_csv(self.gpu_query())
            return [record["uuid"] for record in records
                    if record["free_mib"] >= batch["policy"]["minimum_free_mib"] and record["uuid"] not in used]

    def claim(self, gpu_uuid):
        validate_gpu_uuid(gpu_uuid)
        with self._locked():
            # Recheck here as HOLD may appear after candidate selection.
            if (self.directory / "HOLD").exists():
                return None
            batch = self._load()
            active = [job for job in batch["jobs"] if job["status"] == "running"]
            if len(active) >= batch["policy"]["max_parallel_jobs"] or any(job["gpu_uuid"] == gpu_uuid for job in active):
                return None
            selected = next((job for job in batch["jobs"] if job["status"] == "queued"), None)
            if selected is None:
                return None
            records = parse_gpu_csv(self.gpu_query())
            if not any(record["uuid"] == gpu_uuid and record["free_mib"] >= batch["policy"]["minimum_free_mib"] for record in records):
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
        if field not in ("input", "run_id", "gpu_uuid", "status"):
            raise ValueError("Unsupported job info field")
        with self._locked():
            return self._job(self._load(), job_id).get(field)

    def policy(self, field):
        if field not in DEFAULT_POLICY:
            raise ValueError("Unsupported policy field")
        with self._locked():
            return self._load()["policy"][field]

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

    def retry(self, job_id, new_run_id, reason):
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
            previous_run_id = job["run_id"]
            used_run_ids = {entry["run_id"] for entry in batch["jobs"]}
            for entry in batch["jobs"]:
                history = entry.get("attempts_history", [])
                if not isinstance(history, list) or not all(isinstance(item, dict) for item in history):
                    raise ValueError("Invalid attempts history")
                used_run_ids.update(item.get("run_id") for item in history)
            if new_run_id in used_run_ids:
                raise ValueError("Retry requires a new unique run identifier")
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
                       started_at=None, finished_at=None, attempts_history=history)
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
    elif command == "finish" and len(rest) in (2, 3):
        queue.finish(*rest)
    elif command == "retry" and len(rest) == 3:
        print(json.dumps(queue.retry(*rest), ensure_ascii=False))
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
