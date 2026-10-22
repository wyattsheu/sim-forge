"""CPU tests for copying snapshot QA images under a new export output tag."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

WORKSPACE = Path(__file__).resolve().parents[3]
NATIVE = WORKSPACE / "tools/diaggen"
SUPPORT = WORKSPACE / "tools/diaggen_support"
sys.path.insert(0, str(NATIVE))


def load_verified_module():
    manifest = json.loads((SUPPORT / "snapshot_export_inputs.json").read_text())
    source = (NATIVE / manifest["target"]).read_bytes()
    delta = (SUPPORT / "snapshot_export_inputs.patch").read_bytes()
    digest = lambda value: hashlib.sha256(value).hexdigest()
    if digest(delta) != manifest["patch_sha256"]:
        raise AssertionError("snapshot patch digest changed")
    if digest(source) not in {manifest["before_sha256"], manifest["after_sha256"]}:
        raise AssertionError("snapshot source no longer matches verified baseline")
    if digest(source) == manifest["before_sha256"]:
        with tempfile.TemporaryDirectory() as folder:
            candidate = Path(folder) / manifest["target"]
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(source)
            command = ["patch", "--batch", "--fuzz=0", "-p1"]
            subprocess.run(command + ["--dry-run"], input=delta,
                           cwd=folder, capture_output=True, check=True)
            subprocess.run(command, input=delta, cwd=folder, capture_output=True, check=True)
            source = candidate.read_bytes()
    if digest(source) != manifest["after_sha256"]:
        raise AssertionError("snapshot patched source digest mismatch")
    name = "hag4r.agentic._snapshot_export_inputs_verified"
    spec = importlib.util.spec_from_loader(name, loader=None,
                                          origin=str(NATIVE / manifest["target"]))
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(NATIVE / manifest["target"])
    sys.modules[name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


class SnapshotExportInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = load_verified_module()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / "source/params"
        self.destination = root / "new/params"
        self.source.mkdir(parents=True)
        self.suffixes = ("target_E", "target_density", "target_part", "source_part")
        self.source_bytes = {}
        for index, suffix in enumerate(self.suffixes):
            data = b"known-source-image-" + bytes([index])
            (self.source / f"old_{suffix}.png").write_bytes(data)
            self.source_bytes[suffix] = data
        self.state = {"output_tag": "old", "paths": {
            "monolithic_params_path": str(self.source / "heterogeneous_params.npz")}}
        self.paths = {"monolithic_params_path": str(self.destination / "heterogeneous_params.npz")}

    def copy(self):
        return self.native._copy_snapshot_parameter_renders(
            snapshot_state=self.state, paths=self.paths, output_tag="new")

    def test_new_tag_images_exist_byte_identically_with_source_lineage(self):
        records = self.copy()
        self.assertEqual(len(records), 4)
        for suffix in self.suffixes:
            target = self.destination / f"new_{suffix}.png"
            self.assertEqual(target.read_bytes(), self.source_bytes[suffix])
            record = records[f"diagnostics_snapshot_parameter_render_{suffix}"]
            self.assertEqual(record["path"], str(self.source / f"old_{suffix}.png"))
            self.assertEqual(record["destination_path"], str(target))
            self.assertEqual(record["sha256"], record["destination_sha256"])
            self.assertTrue(record["byte_identical"])
        self.native.validate_external_lineage({"external_lineage": records})

    def test_missing_required_image_fails_before_any_copy(self):
        (self.source / "old_source_part.png").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "missing parameter render"):
            self.copy()
        self.assertFalse(self.destination.exists())

    def test_missing_tag_fails_without_copy_or_guessing(self):
        self.state.pop("output_tag")
        with self.assertRaisesRegex(ValueError, "record output_tag"):
            self.copy()
        self.assertFalse(self.destination.exists())

    def test_wrong_source_tag_does_not_glob_an_unrelated_image(self):
        self.state["output_tag"] = "absent"
        with self.assertRaisesRegex(FileNotFoundError, "absent_target_E"):
            self.copy()
        self.assertFalse(self.destination.exists())

    def test_existing_source_images_are_unchanged(self):
        self.copy()
        for suffix in self.suffixes:
            self.assertEqual((self.source / f"old_{suffix}.png").read_bytes(), self.source_bytes[suffix])
        self.assertEqual(len(list(self.source.iterdir())), 4)

    def test_source_drift_is_rejected_by_native_lineage_validator(self):
        records = self.copy()
        (self.source / "old_target_E.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "external lineage source"):
            self.native.validate_external_lineage({"external_lineage": records})


if __name__ == "__main__":
    unittest.main()
