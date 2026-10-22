"""CPU tests of the actual native segmentation wrapper in a verified patch copy.

No production run ledger, source module, SAM3 model, or GPU is modified.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

WORKSPACE = Path(__file__).resolve().parents[3]
NATIVE = WORKSPACE / "tools/diaggen"
SUPPORT = WORKSPACE / "tools/diaggen_support"
sys.path.insert(0, str(NATIVE))


def load_module(*, baseline=False):
    manifest = json.loads((SUPPORT / "segmentation_raw_prediction_guard.json").read_text())
    source = (NATIVE / manifest["target"]).read_bytes()
    proposal = (SUPPORT / "segmentation_raw_prediction_guard.patch").read_bytes()
    if hashlib.sha256(proposal).hexdigest() != manifest["patch_sha256"]:
        raise AssertionError("proposal patch digest mismatch")
    digest = hashlib.sha256(source).hexdigest()
    expected = manifest["before_sha256"] if baseline else manifest["after_sha256"]
    if digest not in {manifest["before_sha256"], manifest["after_sha256"]}:
        raise AssertionError("native source differs from verified before/after digest")
    if digest != expected:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / manifest["target"]
            target.parent.mkdir(parents=True)
            target.write_bytes(source)
            argv = ["patch", "--batch", "--fuzz=0", "-p1"]
            if baseline:
                argv.append("--reverse")
            subprocess.run(argv, input=proposal, cwd=directory, check=True,
                           capture_output=True)
            source = target.read_bytes()
    if hashlib.sha256(source).hexdigest() != expected:
        raise AssertionError("temporary patched source digest mismatch")
    name = "hag4r.agentic.runtime_tools._segmentation_test_" + str(baseline)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    sys.modules[name] = module
    exec(compile(source, str(NATIVE / manifest["target"]), "exec"), module.__dict__)
    return module


class SegmentationEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.baseline = load_module(baseline=True)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.raw_path = self.folder / "raw.npz"
        self.manifest_path = self.folder / "segmentation_manifest.json"
        self.write_raw(count=1)
        self.manifest = {
            "sam3_raw_npz_path": str(self.raw_path),
            "sam3_pre_postprocess_mask_count": 1,
            "sam3_pre_postprocess_zero_masks": False,
            "final_part_count": 1,
            "parts": [{"part_id": 0, "source": "sam3_mask",
                       "is_segmentation_evidence": True}],
            "postprocess_summary": {"final_segmentation_evidence_part_count": 1},
        }

    def write_raw(self, count=1, *, boxes_count=None, scores_count=None, nonempty=True):
        masks = np.full((count, 1, 4, 4), nonempty, dtype=bool)
        np.savez(self.raw_path, masks=masks,
                 boxes_xyxy=np.zeros((count if boxes_count is None else boxes_count, 4), dtype=np.float32),
                 scores=np.ones(count if scores_count is None else scores_count, dtype=np.float32))

    def invoke(self, *, module=None, attempt=1):
        m = module or self.module
        self.manifest_path.write_text(json.dumps(self.manifest))
        state = {"repo_root": str(self.folder), "paths": {
            "cleaned_image_path": str(self.folder / "cleaned.png"),
            "segmentation_dir": str(self.folder),
            "segmentation_manifest_path": str(self.manifest_path),
            "logs_dir": str(self.folder / "logs"),
        }}
        result = m.StageRunResult(name="sam3_omnipart_2d_segmentation",
                                  stage=m.Stage.SEGMENTATION, success=True,
                                  returncode=0, stdout_path=None, stderr_path=None,
                                  artifacts=(), metrics={}, error="")
        with patch.object(m, "_run_state_stage", side_effect=lambda _root, **kwargs: kwargs["invoke"](state)), \
             patch.object(m, "_stage_tool_attempt_index", return_value=attempt), \
             patch.object(m, "_object_description", return_value="A test object."), \
             patch.object(m, "_worker_gpu_env", return_value=None), \
             patch.object(m, "run_sam3_omnipart_2d_segmentation", return_value=result) as runner, \
             patch.object(m, "_record_segmentation_attempt") as record:
            actual = m.run_sam3_omnipart_2d_segmentation_stage(str(self.folder), "test object", max_attempts=3)
        runner.assert_called_once()
        return actual, record.call_args.kwargs["attempt"]

    def test_real_baseline_wrongly_accepts_empty_raw_fallback(self):
        self.write_raw(count=0)
        self.manifest.update(sam3_pre_postprocess_mask_count=0,
                             sam3_pre_postprocess_zero_masks=True,
                             parts=[{"part_id": 0, "source": "foreground_fill_fallback",
                                     "is_segmentation_evidence": False}],
                             postprocess_summary={"final_segmentation_evidence_part_count": 0})
        old, _ = self.invoke(module=self.baseline)
        actual, attempt = self.invoke()
        self.assertTrue(old.success)
        self.assertFalse(actual.success)
        self.assertTrue(actual.metrics["retryable"])
        self.assertEqual(attempt["status"], "retry_required")
        self.assertIn("zero raw masks", actual.error)

    def test_empty_raw_with_spoofed_positive_manifest_still_fails(self):
        self.write_raw(count=0)
        actual, _ = self.invoke()
        self.assertFalse(actual.success)

    def test_real_prediction_success_retained(self):
        actual, attempt = self.invoke()
        self.assertTrue(actual.success)
        self.assertEqual(attempt["status"], "accepted")

    def test_fill_supplements_real_evidence_without_rejecting_it(self):
        self.manifest["parts"].append({"part_id": 1, "source": "foreground_fill_fallback",
                                       "is_segmentation_evidence": False})
        self.manifest["final_part_count"] = 2
        actual, _ = self.invoke()
        self.assertTrue(actual.success)

    def test_all_real_predictions_rejected_in_postprocess_fails(self):
        self.manifest["parts"][0]["is_segmentation_evidence"] = False
        self.manifest["postprocess_summary"]["final_segmentation_evidence_part_count"] = 0
        actual, _ = self.invoke()
        self.assertFalse(actual.success)
        self.assertIn("no SAM3-derived part", actual.error)

    def test_budget_exhaustion_is_not_retryable(self):
        self.write_raw(count=0)
        actual, attempt = self.invoke(attempt=3)
        self.assertFalse(actual.success)
        self.assertFalse(actual.metrics["retryable"])
        self.assertEqual(attempt["status"], "max_attempts_exhausted")

    def test_missing_raw_fails(self):
        self.raw_path.unlink()
        actual, _ = self.invoke()
        self.assertFalse(actual.success)

    def test_mismatched_prediction_shapes_fail(self):
        self.write_raw(count=1, boxes_count=0)
        actual, _ = self.invoke()
        self.assertFalse(actual.success)
        self.assertIn("inconsistent shapes", actual.error)

    def test_zero_pixel_prediction_fails(self):
        self.write_raw(nonempty=False)
        actual, _ = self.invoke()
        self.assertFalse(actual.success)

    def test_three_dimensional_raw_masks_supported(self):
        np.savez(self.raw_path, masks=np.ones((1, 4, 4), dtype=bool),
                 boxes_xyxy=np.zeros((1, 4), dtype=np.float32),
                 scores=np.ones(1, dtype=np.float32))
        actual, _ = self.invoke()
        self.assertTrue(actual.success)

    def test_non_singleton_mask_channel_rejected(self):
        np.savez(self.raw_path, masks=np.ones((1, 2, 4, 4), dtype=bool),
                 boxes_xyxy=np.zeros((1, 4), dtype=np.float32),
                 scores=np.ones(1, dtype=np.float32))
        actual, _ = self.invoke()
        self.assertFalse(actual.success)
        self.assertIn("invalid dimensions", actual.error)

    def test_missing_or_inconsistent_manifest_counts_fail(self):
        for key, value in [("sam3_pre_postprocess_mask_count", None),
                           ("sam3_pre_postprocess_mask_count", 2),
                           ("final_part_count", 0), ("final_part_count", -1),
                           ("final_part_count", 2)]:
            with self.subTest(key=key, value=value):
                original = copy.deepcopy(self.manifest)
                self.manifest[key] = value
                actual, _ = self.invoke()
                self.assertFalse(actual.success)
                self.manifest = original

    def test_over_cap_still_retryable(self):
        self.manifest["parts"] = [copy.deepcopy(self.manifest["parts"][0]) for _ in range(7)]
        self.manifest["final_part_count"] = 7
        self.manifest["postprocess_summary"]["final_segmentation_evidence_part_count"] = 7
        actual, _ = self.invoke()
        self.assertFalse(actual.success)
        self.assertTrue(actual.metrics["retryable"])


if __name__ == "__main__":
    unittest.main()
