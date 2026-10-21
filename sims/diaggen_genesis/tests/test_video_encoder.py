"""Real CPU encoder round trips and inputs known to be invalid."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

MODULE = Path(__file__).resolve().parents[3] / "tools/diaggen_support/encode_simulation_video.py"
SPEC = importlib.util.spec_from_file_location("diaggen_video_encoder", MODULE)
encoder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(encoder)


class VideoEncoderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.frames = self.root / "captured frames"
        self.frames.mkdir()
        for index in range(4):
            Image.new("RGB", (65, 33), (index * 50, 80, 140)).save(self.frames / f"frame_{index:06d}.png")
        self.scene = self.root / "scene configs" / "scene.json"
        self.scene.parent.mkdir()
        self.config = {"timestep": .002, "render_png": {"capture_every_n_steps": 10}, "output_png": str(self.frames)}
        self.environment = {"HAG4R_MP4_OUTPUT_ROOT": str(self.root / "encoded videos")}
        self.save()

    def save(self):
        self.scene.write_text(json.dumps(self.config))

    def test_native_output_contract_padding_and_exact_fps(self):
        result = encoder.encode(self.scene, 10, environment=self.environment)
        self.assertEqual(Path(result["path"]), self.root / "encoded videos/scene configs/scene.mp4")
        self.assertEqual((result["width"], result["height"]), (66, 34))
        self.assertEqual(result["frame_count"], 4)
        self.assertEqual(result["fps"], 5)

    def test_missing_frame_does_not_reuse_or_replace_existing_output(self):
        result = encoder.encode(self.scene, 10, environment=self.environment)
        output = Path(result["path"])
        original = output.read_bytes()
        (self.frames / "frame_000001.png").unlink()
        with self.assertRaises(ValueError):
            encoder.encode(self.scene, 10, environment=self.environment)
        self.assertEqual(output.read_bytes(), original)

    def test_corrupt_or_different_sized_png_is_rejected(self):
        path = self.frames / "frame_000001.png"
        path.write_bytes(b"broken")
        with self.assertRaises(Exception):
            encoder.encode(self.scene, 10, environment=self.environment)
        Image.new("RGB", (5, 5)).save(path)
        with self.assertRaises(ValueError):
            encoder.encode(self.scene, 10, environment=self.environment)

    def test_invalid_metadata_is_rejected(self):
        for field, value in (("timestep", 0), ("timestep", True), ("timestep", float("nan")), ("output_png", "")):
            with self.subTest(field=field, value=value):
                old = self.config[field]
                self.config[field] = value
                self.save()
                with self.assertRaises(ValueError):
                    encoder.encode(self.scene, 10, environment=self.environment)
                self.config[field] = old
        self.config["render_png"]["capture_every_n_steps"] = True
        self.save()
        with self.assertRaises(ValueError):
            encoder.encode(self.scene, 10, environment=self.environment)

    def test_relative_source_requires_explicit_root(self):
        self.config["output_png"] = "captured frames"
        self.save()
        with self.assertRaises(ValueError):
            encoder.encode(self.scene, 10, environment=self.environment)
        result = encoder.encode(self.scene, 10, environment={**self.environment, "HAG4R_LEGACY_SIM_ROOT": str(self.root)})
        self.assertEqual(result["frame_count"], 4)

    def test_bad_multiplier_is_rejected(self):
        for value in (0, -1, float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                encoder.encode(self.scene, value, environment=self.environment)


if __name__ == "__main__":
    unittest.main()
