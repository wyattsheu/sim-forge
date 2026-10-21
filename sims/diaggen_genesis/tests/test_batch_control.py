import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "queue/batch_control.py"
SPEC = importlib.util.spec_from_file_location("batch_control", MODULE_PATH)
batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch)

GPU_CSV = "0, GPU-A, 32768\n1, GPU-B, 24576\n2, GPU-C, 24000\n"


class BatchControlTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name) / "sims" / "diaggen_genesis"
        self.base.mkdir(parents=True)
        self.plan = {
            "schema_version": batch.PLAN_SCHEMA,
            "policy": dict(batch.DEFAULT_POLICY),
            "jobs": [self.job(index) for index in range(4)],
        }
        self.write_plan()
        self.queue = batch.Queue(self.base, gpu_query=lambda: GPU_CSV)
        self.queue.init()

    @staticmethod
    def job(index):
        return {"id": f"object_{index}", "run_id": f"genesis_object_{index}",
                "input": f"inputs/demo_gallery/object {index}.png", "input_sha256": "a" * 64}

    def write_plan(self):
        (self.base / "batch_plan.json").write_text(json.dumps(self.plan))

    def state(self):
        return json.loads((self.base / "queue/batch.json").read_text())

    def test_memory_only_probe_allows_busy_cards_and_uses_no_process_query(self):
        # No process query is made: an existing training process does not exclude a card.
        response = subprocess.CompletedProcess([], 0, stdout=GPU_CSV)
        with patch.object(batch.subprocess, "run", return_value=response) as query:
            queue = batch.Queue(self.base)
            self.assertEqual(queue.candidates(), ["GPU-A", "GPU-B"])
            self.assertEqual(query.call_count, 1)
            command = query.call_args.args[0]
            self.assertIn("--query-gpu=index,uuid,memory.free", command)
            self.assertFalse(any("compute-apps" in value for value in command))

    def test_policy_reads_initialized_values(self):
        self.assertEqual(self.queue.policy("check_interval_seconds"), 15)
        self.assertTrue(self.queue.policy("allow_compute_sharing"))
        with self.assertRaises(ValueError):
            self.queue.policy("invalid")

    def prepare_shell_sandbox(self):
        queue_dir = self.base / "queue"
        shutil.copy2(MODULE_PATH, queue_dir / "batch_control.py")
        for filename in ("wait_and_run.sh", "run_one.sh"):
            shutil.copy2(MODULE_PATH.parent / filename, queue_dir / filename)
        python = self.base.parents[1] / "tools/diaggen/.conda/hag4r/bin/python"
        python.parent.mkdir(parents=True)
        python.write_text("#!/usr/bin/env bash\nexec " + shlex.quote(sys.executable) + ' "$@"\n')
        python.chmod(0o755)
        fake_bin = self.base.parents[1] / "fake-bin"
        fake_bin.mkdir()
        nvidia = fake_bin / "nvidia-smi"
        nvidia.write_text("#!/usr/bin/env bash\nprintf '%s\\n' '0,GPU-A,32768' '1,GPU-B,24576'\n")
        nvidia.chmod(0o755)
        environment = dict(os.environ)
        environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
        return queue_dir, python, environment

    def test_supervisor_finalizes_early_worker_exits_and_continues(self):
        queue_dir, _, environment = self.prepare_shell_sandbox()
        self.plan["policy"]["check_interval_seconds"] = 1
        self.write_plan()
        (queue_dir / "preflight.ok").touch()
        # Exercise zero and nonzero early exits without starting Codex or a GPU.
        (queue_dir / "run_one.sh").write_text(
            '#!/usr/bin/env bash\nif [[ "$1" == object_0 ]]; then exit 0; fi\nexit 17\n')
        result = subprocess.run(["bash", str(queue_dir / "wait_and_run.sh")],
                                env=environment, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.queue.done())
        for job in self.state()["jobs"]:
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["reason"], "worker_exited_without_result")
            self.assertIsInstance(job["runner_pid"], int)

    def test_worker_trap_covers_first_queue_lookup_failure(self):
        queue_dir, python, environment = self.prepare_shell_sandbox()
        self.assertEqual(self.queue.claim("GPU-A"), "object_0")
        python.write_text(
            '#!/usr/bin/env bash\n'
            'if [[ "$2" == info && "$4" == run_id ]]; then exit 23; fi\n'
            'exec ' + shlex.quote(sys.executable) + ' "$@"\n')
        result = subprocess.run(["bash", str(queue_dir / "run_one.sh"), "object_0"],
                                env=environment, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 23)
        job = self.state()["jobs"][0]
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["reason"], "launcher_error")
        self.assertIsInstance(job["runner_pid"], int)
        self.assertFalse((queue_dir / "jobs").exists())

    def test_supervisor_finalizes_when_worker_script_is_missing(self):
        queue_dir, _, environment = self.prepare_shell_sandbox()
        self.plan["policy"]["check_interval_seconds"] = 1
        self.write_plan()
        (queue_dir / "preflight.ok").touch()
        (queue_dir / "run_one.sh").unlink()
        result = subprocess.run(["bash", str(queue_dir / "wait_and_run.sh")],
                                env=environment, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.queue.done())
        self.assertTrue(all(job["status"] == "failed" for job in self.state()["jobs"]))
        self.assertTrue(all(job["reason"] == "worker_exited_without_result" for job in self.state()["jobs"]))

    def test_claim_rechecks_free_memory_and_respects_24_gib(self):
        self.assertEqual(self.queue.candidates(), ["GPU-A", "GPU-B"])
        self.assertIsNone(self.queue.claim("GPU-C"))
        self.assertIsNone(self.queue.claim("GPU-MISSING"))
        self.queue.gpu_query = lambda: "0,GPU-A,24575\n"
        self.assertIsNone(self.queue.claim("GPU-A"))
        self.assertTrue(all(job["status"] == "queued" for job in self.state()["jobs"]))

    def test_two_parallel_jobs_one_per_card_then_next_job(self):
        self.assertEqual(self.queue.claim("GPU-A"), "object_0")
        self.assertIsNone(self.queue.claim("GPU-A"))
        self.assertEqual(self.queue.candidates(), ["GPU-B"])
        self.assertEqual(self.queue.claim("GPU-B"), "object_1")
        self.queue.gpu_query = lambda: GPU_CSV + "3,GPU-D,60000\n"
        self.assertIsNone(self.queue.claim("GPU-D"))
        self.assertEqual(self.queue.candidates(), [])
        self.queue.finish("object_0", "success")
        self.assertEqual(self.queue.claim("GPU-A"), "object_2")
        self.assertEqual([job["attempts"] for job in self.state()["jobs"]], [1, 1, 1, 0])

    def test_init_preserves_running_success_and_adds_jobs_updates_policy(self):
        self.queue.claim("GPU-A")
        self.queue.bind("object_0", 123)
        self.queue.claim("GPU-B")
        self.queue.finish("object_1", "success")
        before = self.state()["jobs"][:2]
        self.plan["policy"]["minimum_free_mib"] = 30000
        self.plan["jobs"].append(self.job(4))
        # The static plan is not allowed to overwrite a previously initialized job.
        self.plan["jobs"][0]["input"] = "inputs/new.png"
        self.write_plan()
        self.queue.init()
        after = self.state()
        self.assertEqual(after["jobs"][:2], before)
        self.assertEqual(len(after["jobs"]), 5)
        self.assertEqual(after["policy"]["minimum_free_mib"], 30000)
        self.assertEqual(after["jobs"][4]["status"], "queued")

    def test_concurrent_claims_do_not_duplicate_jobs_or_gpu(self):
        def claim(index):
            queue = batch.Queue(self.base, gpu_query=lambda: GPU_CSV)
            return queue.claim("GPU-A" if index % 2 == 0 else "GPU-B")
        with ThreadPoolExecutor(max_workers=8) as workers:
            result = list(workers.map(claim, range(16)))
        claimed = [value for value in result if value is not None]
        self.assertCountEqual(claimed, ["object_0", "object_1"])
        running = [job for job in self.state()["jobs"] if job["status"] == "running"]
        self.assertEqual(len({job["gpu_uuid"] for job in running}), 2)
        self.assertEqual(sum(job["attempts"] for job in self.state()["jobs"]), 2)

    def test_spaces_in_input_are_preserved_without_shell_interpolation(self):
        self.plan["jobs"][0] = {**self.job(0), "input": "inputs/demo_gallery/Capybara plush toy.jpg"}
        # Start a new queue so the plan supplies the initial value.
        (self.base / "queue/batch.json").unlink()
        self.write_plan()
        self.queue.init()
        self.assertEqual(self.queue.info("object_0", "input"), "inputs/demo_gallery/Capybara plush toy.jpg")

    def test_bad_or_unavailable_gpu_probe_fails_closed(self):
        for value in ("", "No devices were found", "0,GPU-A,N/A", "0,GPU-A,40000\ninvalid", "0,GPU-A,40000\n1,GPU-A,40000"):
            with self.subTest(value=value):
                self.queue.gpu_query = lambda value=value: value
                with self.assertRaises((ValueError, batch.csv.Error)):
                    self.queue.claim("GPU-A")
                self.assertTrue(all(job["status"] == "queued" for job in self.state()["jobs"]))
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("nvidia-smi", 10),
                      subprocess.CalledProcessError(1, "nvidia-smi", stderr="secret")):
            with self.subTest(error=type(error).__name__):
                def fail():
                    raise error
                self.queue.gpu_query = fail
                with self.assertRaises(type(error)):
                    self.queue.claim("GPU-A")
                self.assertTrue(all(job["status"] == "queued" for job in self.state()["jobs"]))

    def test_cancel_only_queued_and_summary_tracks_terminal_counts(self):
        self.assertFalse(self.queue.done())
        self.queue.claim("GPU-A")
        self.queue.cancel()
        self.assertEqual(self.queue.summary()["phase"], "running")
        self.assertEqual(self.state()["jobs"][0]["status"], "running")
        self.queue.finish("object_0", "failed", "codex_failed")
        self.assertTrue(self.queue.done())
        summary = self.queue.summary()
        self.assertEqual(summary["phase"], "failed")
        self.assertEqual(summary["batch_counts"], {
            "total": 4, "queued": 0, "running": 0, "success": 0, "failed": 1, "cancelled": 3})
        self.assertEqual(summary["simulator"], "Genesis")
        self.assertEqual(summary["generation_and_diagnostics_model"], "gpt-6-luna")
        self.assertEqual(summary["reasoning_effort"], "max")
        self.assertFalse((self.base / "queue/jobs").exists())

    def test_all_success_summary_and_idempotent_finish(self):
        for index in range(4):
            self.assertEqual(self.queue.claim("GPU-A"), f"object_{index}")
            self.queue.finish(f"object_{index}", "success")
            self.queue.finish(f"object_{index}", "success")
        self.assertTrue(self.queue.done())
        self.assertEqual(self.queue.summary()["phase"], "success")

    def test_rejects_unsafe_ids_paths_nonimages_and_reasons(self):
        cases = [("id", "../escape"), ("run_id", "../escape"),
                 ("input", "/tmp/object.png"), ("input", "inputs/../object.png"),
                 ("input", "other/object.png"), ("input", "inputs/demo_gallery/README.txt")]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.plan["jobs"][0] = {**self.job(0), field: value}
                self.write_plan()
                with self.assertRaises(ValueError):
                    self.queue.init()
        self.queue.claim("GPU-A")
        with self.assertRaises(ValueError):
            self.queue.finish("object_0", "failed", "credential: secret")
        with self.assertRaises(ValueError):
            self.queue.bind("object_0", -1)
        self.queue.bind("object_0", 123)
        with self.assertRaises(ValueError):
            self.queue.bind("object_0", 456)

    def test_symlink_input_escape_is_rejected(self):
        target = Path(self.temporary.name) / "outside"
        target.mkdir()
        inputs = self.base / "inputs"
        inputs.mkdir()
        (inputs / "linked").symlink_to(target, target_is_directory=True)
        self.plan["jobs"][0]["input"] = "inputs/linked/object.png"
        self.write_plan()
        with self.assertRaises(ValueError):
            self.queue.init()


if __name__ == "__main__":
    unittest.main()
