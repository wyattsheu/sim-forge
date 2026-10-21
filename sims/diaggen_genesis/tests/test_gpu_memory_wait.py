import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch


MODULE_PATH = Path(__file__).resolve().parents[3] / "tools/wait_diaggen_gpu_memory.py"
SPEC = importlib.util.spec_from_file_location("wait_diaggen_gpu_memory", MODULE_PATH)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
GPU = "GPU-ef92f209-a96e-e42c-a1c9-96e2f1db7e55"
OTHER_GPU = "GPU-9ea7f276-1404-458e-ae57-a2698b66a4e7"


class GpuMemoryWaitTests(unittest.TestCase):
    def run_guard(self, responses, *, minimum=24576, poll=15):
        query = Mock(side_effect=responses)
        sleep = Mock()
        observations = []
        result = guard.wait_for_memory(GPU, minimum, poll, query=query,
                                       sleep=sleep, emit=observations.append)
        return result, query, sleep, observations

    def test_threshold_boundary_passes_without_sleep(self):
        result, query, sleep, observations = self.run_guard([f"{GPU}, 24576\n"])
        self.assertEqual(result, 0)
        query.assert_called_once_with(GPU)
        sleep.assert_not_called()
        self.assertEqual(observations[0]["status"], "ready")
        self.assertFalse(observations[0]["memory_reserved"])

    def test_waits_repeatedly_until_measured_threshold(self):
        result, query, sleep, observations = self.run_guard(
            [f"{GPU}, 24575\n", f"{GPU}, 0\n", f"{GPU}, 49152\n"],
            minimum=49152, poll=3,
        )
        self.assertEqual(result, 0)
        self.assertEqual(query.call_count, 3)
        self.assertEqual([call.args for call in sleep.call_args_list], [(3,), (3,)])
        self.assertEqual([item["status"] for item in observations],
                         ["waiting", "waiting", "ready"])

    def test_wrong_uuid_fails_closed(self):
        result, _, sleep, observations = self.run_guard([f"{OTHER_GPU}, 99999\n"])
        self.assertEqual(result, 1)
        self.assertEqual(observations[0]["status"], "probe_failed")
        sleep.assert_not_called()

    def test_unavailable_or_malformed_memory_fails_closed(self):
        for response in (f"{GPU}, N/A\n", f"{GPU}, -1\n", f"{GPU}, 24576 MiB\n",
                         f"{GPU}, 1.5\n", "", f"{GPU}, 99999\n{OTHER_GPU}, 99999\n",
                         f"{GPU}, 99999, unexpected\n", f"{GPU}, 99999\n\n"):
            with self.subTest(response=response):
                result, _, sleep, observations = self.run_guard([response])
                self.assertEqual(result, 1)
                self.assertEqual(observations[0]["status"], "probe_failed")
                sleep.assert_not_called()

    def test_query_failure_cannot_be_read_as_available_memory(self):
        for error in (subprocess.CalledProcessError(1, ["nvidia-smi"]),
                      subprocess.TimeoutExpired(["nvidia-smi"], 10),
                      FileNotFoundError("nvidia-smi")):
            with self.subTest(error=error):
                result, query, sleep, observations = self.run_guard([error])
                self.assertEqual(result, 1)
                query.assert_called_once_with(GPU)
                sleep.assert_not_called()
                self.assertEqual(observations[0]["status"], "probe_failed")

    def test_unsafe_or_ambiguous_uuid_is_rejected_before_query(self):
        for value in (None, "", "0", "GPU-A", f"{GPU},{OTHER_GPU}",
                      f"{GPU}; echo bad", f" {GPU}", f"{GPU}\n"):
            with self.subTest(value=value):
                query = Mock()
                with self.assertRaises(ValueError):
                    guard.wait_for_memory(value, 24576, query=query)
                query.assert_not_called()

    def test_invalid_threshold_or_poll_is_rejected_before_query(self):
        for minimum, poll in ((0, 15), (-1, 15), (True, 15), (1.5, 15),
                              (24576, 0), (24576, 16), (24576, float("nan")),
                              (24576, float("inf")), (24576, True)):
            with self.subTest(minimum=minimum, poll=poll):
                query = Mock()
                with self.assertRaises(ValueError):
                    guard.wait_for_memory(GPU, minimum, poll, query=query)
                query.assert_not_called()

    def test_query_uses_exact_bound_uuid_without_shell_or_compute_query(self):
        response = subprocess.CompletedProcess([], 0, stdout=f"{GPU}, 49152\n")
        with patch.object(guard.subprocess, "run", return_value=response) as run:
            self.assertEqual(guard.query_gpu_csv(GPU), response.stdout)
        self.assertEqual(run.call_args.args[0],
                         ["nvidia-smi", "--id", GPU, "--query-gpu=uuid,memory.free",
                          "--format=csv,noheader,nounits"])
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertLessEqual(run.call_args.kwargs["timeout"], 15)

    def test_cli_uses_single_uuid_from_environment(self):
        with patch.dict(os.environ, {"CUDA_VISIBLE_DEVICES": GPU}), \
                patch.object(guard, "wait_for_memory", return_value=0) as wait:
            self.assertEqual(guard.main(["--minimum-free-mib", "49152"]), 0)
        wait.assert_called_once_with(GPU, 49152, 15)

    def test_json_observations_are_flushed(self):
        output = Mock(spec=io.StringIO)
        with patch("sys.stdout", output):
            guard.emit_json({"status": "waiting", "free_mib": 1})
        output.flush.assert_called_once_with()
        text = "".join(call.args[0] for call in output.write.call_args_list)
        self.assertEqual(json.loads(text), {"status": "waiting", "free_mib": 1})


if __name__ == "__main__":
    unittest.main()
