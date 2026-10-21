"""Queue export recovery preserves failures and refuses incomplete evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "queue/reconcile_export.py"
SPEC = importlib.util.spec_from_file_location("reconcile_export", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReconcileExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.base = self.workspace / "sims/diaggen_genesis"
        self.queue = self.base / "queue"
        self.queue.mkdir(parents=True)
        self.run_id = "example_run"
        self.run = self.workspace / "tools/diaggen/outputs/agentic_asset_refinement" / self.run_id
        self.export = self.workspace / "tools/diaggen/outputs/run_pipeline" / self.run_id
        self.archive = self.base / "runs" / self.run_id
        self.native_state = {"status": "success", "run_root": str(self.run), "run_id": self.run_id}
        self.write_json(self.run / "state.json", self.native_state)
        self.write_json(self.export / "final_export_manifest.json", {"run_id": self.run_id})
        (self.export / "asset.dat").write_text("actual asset")
        self.job = {"id": "example", "run_id": self.run_id, "input": "inputs/example.png", "status": "failed",
                    "gpu_uuid": "GPU-test", "runner_pid": 99999999, "attempts": 2,
                    "started_at": "2026-10-21T14:55:20+08:00", "finished_at": "2026-10-21T16:11:47+08:00",
                    "reason": "execution_failed", "attempts_history": [{"run_id": "old_run", "status": "failed"}]}
        self.batch = {"schema_version": "diaggen-batch-v1", "policy": {
                          "minimum_free_mib": 24576, "allow_compute_sharing": True,
                          "check_interval_seconds": 15, "max_parallel_jobs": 2}, "jobs": [copy.deepcopy(self.job)]}
        self.write_json(self.queue / "batch.json", self.batch)
        self.write_json(self.queue / "status.json", {"phase": "failed", "original": "root failure"})
        self.write_json(self.queue / "jobs/example/status.json", {
            "phase": "failed", "detail": "artifact verification=4", "run_id": self.run_id,
        })
        self.write_json(self.archive / "manifest.json", {"pipeline_status": "running", "original_failure": True})
        self.write_json(self.archive / "trace/state.json", {"status": "running", "original_failure": True})
        self.write_json(self.archive / "trace/revisions/revision_0000/state.json", {"status": "running"})
        self.report = {"valid": True, "run_id": self.run_id, "run_root": str(self.run),
                       "accepted_revision": "revision_0000", "manifest_sha256": self.hash_file(self.export / "final_export_manifest.json"),
                       "state_sha256": self.hash_file(self.run / "state.json"),
                       "artifact_sha256": {"asset.dat": self.hash_file(self.export / "asset.dat")}}
        self.validator = mock.Mock(return_value=self.report)
        self.archive_runner = mock.Mock(side_effect=self.fake_archive)
        self.pid_probe = mock.Mock(return_value=False)

    @staticmethod
    def hash_file(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def write_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def fake_archive(self, queue, job):
        self.write_json(self.archive / "manifest.json", {"run_id": job["run_id"], "pipeline_status": "success"})
        shutil.copy2(self.run / "state.json", self.archive / "trace/state.json")
        shutil.copytree(self.export, self.archive / "asset", dirs_exist_ok=True)

    def recover(self):
        return MODULE.reconcile_export("example", base=self.base, validator=self.validator,
                                       archive_runner=self.archive_runner, pid_probe=self.pid_probe)

    def current_job(self):
        return MODULE.read_object(self.queue / "batch.json")["jobs"][0]

    def test_recovery_preserves_failure_evidence_and_attempt_history(self):
        previous_status = (self.queue / "jobs/example/status.json").read_bytes()
        previous_manifest = (self.archive / "manifest.json").read_bytes()
        previous_trace = (self.archive / "trace/state.json").read_bytes()
        native_before = (self.run / "state.json").read_bytes()
        result = self.recover()
        self.assertTrue(result["recovered"])
        job = self.current_job()
        self.assertEqual(job["status"], "success")
        for key in ("attempts", "attempts_history", "runner_pid", "gpu_uuid", "started_at", "finished_at"):
            self.assertEqual(job[key], self.job[key])
        recovery = job["completion_recovery"]
        self.assertEqual(recovery["previous_job"], self.job)
        self.assertEqual(recovery["previous_job_status"]["detail"], "artifact verification=4")
        self.assertEqual(recovery["validation_sha256"], MODULE.digest(self.report))
        history = self.queue / result["evidence_directory"]
        self.assertEqual((history / "job_status_before.json").read_bytes(), previous_status)
        self.assertEqual((history / "archive_manifest_before.json").read_bytes(), previous_manifest)
        self.assertEqual((history / "archive_trace_state_before.json").read_bytes(), previous_trace)
        self.assertEqual((self.run / "state.json").read_bytes(), native_before)
        self.assertEqual(MODULE.read_object(self.queue / "jobs/example/status.json")["phase"], "success")
        self.assertEqual(MODULE.read_object(self.queue / "status.json")["batch_counts"]["success"], 1)

    def test_active_runner_is_refused_before_validation(self):
        self.pid_probe.return_value = True
        with self.assertRaisesRegex(ValueError, "still alive"):
            self.recover()
        self.validator.assert_not_called()
        self.archive_runner.assert_not_called()
        self.assertEqual(self.current_job(), self.job)

    def test_changed_run_id_during_validation_is_refused(self):
        def change_job(*args, **kwargs):
            value = MODULE.read_object(self.queue / "batch.json")
            value["jobs"][0]["run_id"] = "different_run"
            self.write_json(self.queue / "batch.json", value)
            return self.report
        self.validator.side_effect = change_job
        with self.assertRaisesRegex(ValueError, "Job changed"):
            self.recover()
        self.archive_runner.assert_not_called()
        self.assertEqual(self.current_job()["status"], "failed")

    def test_validation_failure_is_refused_without_archive(self):
        self.validator.side_effect = ValueError("Native validation failed")
        with self.assertRaisesRegex(ValueError, "Native validation failed"):
            self.recover()
        self.archive_runner.assert_not_called()
        self.assertEqual(self.current_job(), self.job)

    def test_unsettled_native_state_is_refused(self):
        self.native_state["status"] = "running"
        self.write_json(self.run / "state.json", self.native_state)
        with self.assertRaisesRegex(ValueError, "must be settled"):
            self.recover()
        self.archive_runner.assert_not_called()

    def test_archive_failure_keeps_queue_failed_and_old_snapshots(self):
        before = (self.archive / "manifest.json").read_bytes()
        def fail_after_partial_copy(*args):
            self.write_json(self.archive / "manifest.json", {"partial": True})
            raise subprocess.CalledProcessError(4, ["support.py", "archive"])
        self.archive_runner.side_effect = fail_after_partial_copy
        with self.assertRaises(subprocess.CalledProcessError):
            self.recover()
        self.assertEqual(self.current_job(), self.job)
        snapshots = list((self.queue / "recovery_history").rglob("archive_manifest_before.json"))
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].read_bytes(), before)

    def test_archive_corruption_does_not_promote_queue(self):
        def corrupt(queue, job):
            self.fake_archive(queue, job)
            (self.archive / "asset/asset.dat").write_text("bad copied asset")
        self.archive_runner.side_effect = corrupt
        with self.assertRaisesRegex(ValueError, "differs from verified"):
            self.recover()
        self.assertEqual(self.current_job(), self.job)

    def test_changed_job_during_archive_is_not_overwritten(self):
        def change_job(queue, job):
            self.fake_archive(queue, job)
            value = MODULE.read_object(self.queue / "batch.json")
            value["jobs"][0]["run_id"] = "different_run"
            self.write_json(self.queue / "batch.json", value)
        self.archive_runner.side_effect = change_job
        with self.assertRaisesRegex(ValueError, "changed during archival"):
            self.recover()
        self.assertEqual(self.current_job()["run_id"], "different_run")
        self.assertEqual(self.current_job()["status"], "failed")

    def test_idempotence_does_not_repeat_archive_or_snapshots(self):
        first = self.recover()
        job = self.current_job()
        second = self.recover()
        self.assertTrue(second["already_recovered"])
        self.assertFalse(second["recovered"])
        self.assertEqual(second["evidence_directory"], first["evidence_directory"])
        self.assertEqual(self.current_job(), job)
        self.assertEqual(len(list((self.queue / "recovery_history").rglob("batch_job_before.json"))), 1)
        self.archive_runner.assert_called_once()

    def test_missing_previous_archive_snapshots_are_recorded_without_copy(self):
        (self.archive / "trace/revisions/revision_0000/state.json").unlink()
        result = self.recover()
        history = self.queue / result["evidence_directory"]
        inventory = MODULE.read_object(history / "snapshot_inventory.json")
        self.assertFalse(inventory["archive_revision_state_before.json"]["existed"])
        self.assertFalse((history / "archive_revision_state_before.json").exists())

    def test_archive_subprocess_gets_original_job_environment(self):
        with mock.patch.object(MODULE.subprocess, "run") as run:
            MODULE.archive_existing(MODULE.Queue(self.base), self.job)
        args, kwargs = run.call_args
        self.assertEqual(args[0][-1], "archive")
        self.assertEqual(args[0][1], str(self.queue / "support.py"))
        self.assertEqual(kwargs["env"]["DIAGGEN_QUEUE_RUN_ID"], self.run_id)
        self.assertEqual(kwargs["env"]["DIAGGEN_JOB_QUEUE_DIR"], str(self.queue / "jobs/example"))
        self.assertTrue(kwargs["check"])


if __name__ == "__main__":
    unittest.main()
