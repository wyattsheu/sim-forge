"""CPU-only queue admission regressions; never touch production job ledgers."""
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1] / "queue/batch_control.py"
SPEC = importlib.util.spec_from_file_location("shared_gpu_batch", PATH)
batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch)


class GpuSharingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.plan = {
            "schema_version": batch.PLAN_SCHEMA,
            "policy": {**batch.DEFAULT_POLICY, "max_parallel_jobs": 4, "max_jobs_per_gpu": 2},
            "jobs": [{"id": f"object_{n}", "run_id": f"run_{n}",
                      "input": f"inputs/{n}.png", "input_sha256": "a" * 64}
                     for n in range(6)],
        }
        self.flush()
        self.csv = "0,GPU-A,65536\n1,GPU-B,24993\n"
        self.queue = batch.Queue(self.base, gpu_query=lambda: self.csv)
        self.queue.init()

    def flush(self):
        (self.base / "batch_plan.json").write_text(json.dumps(self.plan))

    def state(self):
        return json.loads((self.base / "queue/batch.json").read_text())

    def test_spare_memory_allows_second_job_on_assigned_gpu(self):
        self.assertEqual(self.queue.claim("GPU-A"), "object_0")
        old = self.state()["jobs"][0]
        self.assertIn("GPU-A", self.queue.candidates())
        self.assertEqual(self.queue.claim("GPU-A"), "object_1")
        self.assertEqual(self.state()["jobs"][0], old)
        self.assertNotIn("GPU-A", self.queue.candidates())
        self.assertIsNone(self.queue.claim("GPU-A"))

    def test_busy_second_gpu_needs_headroom_for_existing_waiter(self):
        self.assertEqual(self.queue.claim("GPU-B"), "object_0")
        self.assertNotIn("GPU-B", self.queue.candidates())
        self.assertIsNone(self.queue.claim("GPU-B"))
        self.csv = "1,GPU-B,49152\n"
        self.assertIn("GPU-B", self.queue.candidates())
        self.assertEqual(self.queue.claim("GPU-B"), "object_1")

    def test_shared_admission_reprobes_exact_budget_boundary(self):
        self.queue.claim("GPU-A")
        self.assertIn("GPU-A", self.queue.candidates())
        self.csv = "0,GPU-A,49151\n"
        self.assertIsNone(self.queue.claim("GPU-A"))
        self.csv = "0,GPU-A,49152\n"
        self.assertEqual(self.queue.claim("GPU-A"), "object_1")

    def test_bound_resumed_job_cannot_move_to_other_gpu(self):
        state = self.state()
        state["jobs"][1].update(execution_mode="resume", resume_id="resume_1",
                                resume_gpu_uuid="GPU-B", resume_state_sha256="b" * 64)
        batch.atomic_json(self.base / "queue/batch.json", state)
        self.queue.claim("GPU-A")
        self.assertEqual(self.queue.claim("GPU-A"), "object_2")
        self.assertEqual(self.state()["jobs"][1]["status"], "queued")

    def test_large_job_budget_is_preserved_when_sharing(self):
        hold = self.base / "queue/HOLD"
        hold.touch()
        self.queue.set_minimum("object_0", 70000, "measured_memory_peak")
        hold.unlink()
        self.csv = "0,GPU-A,100000\n"
        self.queue.claim("GPU-A")
        self.csv = "0,GPU-A,94575\n"
        self.assertIsNone(self.queue.claim("GPU-A"))
        self.csv = "0,GPU-A,94576\n"
        self.assertEqual(self.queue.claim("GPU-A"), "object_1")

    def test_global_limit_still_applies_with_multiple_jobs_per_gpu(self):
        self.plan["policy"]["max_parallel_jobs"] = 3
        self.flush()
        self.queue.init()
        self.csv = "0,GPU-A,100000\n1,GPU-B,100000\n"
        for gpu in ["GPU-A", "GPU-A", "GPU-B"]:
            self.assertIsNotNone(self.queue.claim(gpu))
        self.assertEqual(self.queue.candidates(), [])
        self.assertIsNone(self.queue.claim("GPU-B"))

    def test_concurrent_claims_count_unbound_workers_and_never_duplicate(self):
        with ThreadPoolExecutor(max_workers=12) as pool:
            claims = list(pool.map(lambda _: self.queue.claim("GPU-A"), range(30)))
        admitted = [job for job in claims if job is not None]
        self.assertEqual(len(admitted), 2)
        self.assertEqual(len(set(admitted)), 2)
        running = [job for job in self.state()["jobs"] if job["status"] == "running"]
        self.assertEqual(len(running), 2)
        self.assertTrue(all(job["runner_pid"] is None for job in running))

    def test_finishing_one_job_releases_only_its_admission_budget(self):
        self.queue.claim("GPU-A")
        self.queue.claim("GPU-A")
        self.queue.finish("object_0", "success")
        self.assertEqual(self.queue.claim("GPU-A"), "object_2")
        self.assertEqual(self.state()["jobs"][1]["status"], "running")

    def test_hold_blocks_shared_admission(self):
        self.queue.claim("GPU-A")
        before = self.state()
        (self.base / "queue/HOLD").touch()
        self.assertEqual(self.queue.candidates(), [])
        self.assertIsNone(self.queue.claim("GPU-A"))
        self.assertEqual(self.state(), before)

    def test_default_keeps_one_job_per_gpu(self):
        self.plan["policy"].pop("max_jobs_per_gpu")
        self.flush()
        self.queue.init()
        self.queue.claim("GPU-A")
        self.assertNotIn("GPU-A", self.queue.candidates())
        self.assertIsNone(self.queue.claim("GPU-A"))

    def test_nonpositive_or_noninteger_slot_counts_are_rejected(self):
        for value in [0, -1, True, False, None, 2.0, "2"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                batch.validate_policy({"max_jobs_per_gpu": value})


if __name__ == "__main__":
    unittest.main()
