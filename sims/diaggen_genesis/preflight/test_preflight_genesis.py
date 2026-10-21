"""Negative controls for artifact validation; CPU only."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image


spec = importlib.util.spec_from_file_location("probe_genesis", Path(__file__).with_name("probe_genesis.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ArtifactValidationTests(unittest.TestCase):
    def test_geometry_rejects_missing_nonfinite_and_collapsed_readback(self):
        valid = {"vertex_count": 5, "element_count": 2, "representation": "volumetric",
                 "bbox_min": [0., 0., 0.], "bbox_max": [1., 1., 1.]}
        probe.validate_geometry(valid)
        for change in ({"element_count": 0}, {"bbox_max": [1., float("nan"), 1.]},
                       {"bbox_max": [0., 1., 1.]}):
            with self.assertRaises(ValueError):
                probe.validate_geometry(valid | change)

    def test_render_rejects_blank_missing_wrong_hash_and_escaped_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            blank = output / "blank.png"
            Image.new("RGB", (80, 80)).save(blank)
            with self.assertRaisesRegex(ValueError, "blank"):
                probe.validate_render({"image": {"path": str(blank)}}, output)
            with self.assertRaisesRegex(ValueError, "missing"):
                probe.validate_render({"image": {"path": str(output / "missing.png")}}, output)
            pixels = np.zeros((80, 80, 3), dtype=np.uint8)
            pixels[20:60, 20:60] = [50, 180, 90]
            image = output / "visible.png"
            Image.fromarray(pixels).save(image)
            self.assertEqual(probe.validate_render({"image": {"path": str(image)}}, output), [image])
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                probe.validate_render({"image": {"path": str(image), "sha256": "wrong"}}, output)
            with self.assertRaisesRegex(ValueError, "outside"):
                probe.validate_render({"image": {"path": str(image)}}, output / "narrow")


if __name__ == "__main__":
    unittest.main()
