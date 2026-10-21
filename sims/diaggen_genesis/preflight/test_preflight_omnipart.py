"""Safety checks for the GPU preflight, without starting CUDA or models."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("probe_omnipart", Path(__file__).with_name("probe_omnipart.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class GpuGateTests(unittest.TestCase):
    def test_rejects_index_or_multi_gpu_tokens_without_query(self):
        with patch.object(probe.subprocess, "run") as run:
            for token in ["0", "0,1", "GPU-123,GPU-456", "all"]:
                with self.subTest(token=token), self.assertRaises(ValueError):
                    probe.query_gpu(token)
            run.assert_not_called()

    def test_exact_gpu_identity_and_free_memory(self):
        token = "GPU-ab12-cd34"
        completed = subprocess.CompletedProcess([], 0, token + ", 9000, Test GPU\n", "")
        with patch.object(probe.subprocess, "run", return_value=completed):
            result = probe.query_gpu(token)
        self.assertEqual(result["free_mib"], 9000)
        self.assertEqual(result["uuid"], token)

    def test_mismatched_or_ambiguous_gpu_response_fails_closed(self):
        token = "GPU-ab12-cd34"
        for output in ["GPU-ffff, 9000, Other\n", "GPU-ab12-cd34, 9000, A\nGPU-ffff, 9000, B\n", ""]:
            completed = subprocess.CompletedProcess([], 0, output, "")
            with patch.object(probe.subprocess, "run", return_value=completed), self.assertRaises(ValueError):
                probe.query_gpu(token)

    def test_rejects_outputs_outside_native_preflight_root(self):
        with self.assertRaises(ValueError):
            probe.run(Path("/tmp/not-a-diaggen-output"), None)


if __name__ == "__main__":
    unittest.main()
