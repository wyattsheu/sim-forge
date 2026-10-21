"""Exercise the real support installer only inside temporary native trees."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

WORKSPACE = Path(__file__).resolve().parents[3]
TOOLS = WORKSPACE / "tools"
PATCHES = ("strict_material_coverage", "diagnostic_history_settlement")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RuntimeSupportInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="diaggen installer test ")
        self.addCleanup(self.temporary.cleanup)
        self.tools = Path(self.temporary.name) / "tools"
        self.support = self.tools / "diaggen_support"
        self.native = self.tools / "diaggen"
        self.support.mkdir(parents=True)
        (self.native / "scripts").mkdir(parents=True)
        self.installer = self.tools / "setup_diaggen_runtime_support.sh"
        shutil.copyfile(TOOLS / self.installer.name, self.installer)
        shutil.copyfile(TOOLS / "diaggen_support/generate_simulation_mp4.sh",
                        self.support / "generate_simulation_mp4.sh")
        self.manifests = {}
        self.original_sources = {}
        for name in PATCHES:
            for extension in ("json", "patch"):
                shutil.copyfile(TOOLS / "diaggen_support" / f"{name}.{extension}",
                                self.support / f"{name}.{extension}")
            manifest = json.loads((self.support / f"{name}.json").read_text())
            self.manifests[name] = manifest
            source = TOOLS / "diaggen" / manifest["target"]
            target = self.native / manifest["target"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            current = digest(target)
            if current == manifest["after_sha256"]:
                subprocess.run(["patch", "--batch", "--reverse", "--fuzz=0", "-p1",
                                "--input", str(self.support / f"{name}.patch")],
                               cwd=self.native, check=True, capture_output=True)
            elif current != manifest["before_sha256"]:
                self.fail(f"Native source has an unreviewed hash: {name}")
            self.assertEqual(digest(target), manifest["before_sha256"])
            self.original_sources[name] = target.read_bytes()

    def run_installer(self):
        return subprocess.run(["bash", str(self.installer)], cwd=self.temporary.name,
                              text=True, capture_output=True, timeout=20)

    def assert_unchanged(self, expected=None):
        for name in PATCHES:
            target = self.native / self.manifests[name]["target"]
            self.assertEqual(target.read_bytes(), (expected or self.original_sources)[name])
        self.assertFalse((self.native / "scripts/generate_simulation_mp4.sh").exists())

    def test_both_verified_patches_install_and_repeat_idempotently(self):
        first = self.run_installer()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        mtimes = {}
        for name in PATCHES:
            target = self.native / self.manifests[name]["target"]
            self.assertEqual(digest(target), self.manifests[name]["after_sha256"])
            mtimes[name] = target.stat().st_mtime_ns
        encoder = self.native / "scripts/generate_simulation_mp4.sh"
        self.assertTrue(encoder.is_symlink())
        self.assertEqual(encoder.resolve(), (self.support / encoder.name).resolve())
        second = self.run_installer()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        for name in PATCHES:
            target = self.native / self.manifests[name]["target"]
            self.assertEqual(digest(target), self.manifests[name]["after_sha256"])
            self.assertEqual(target.stat().st_mtime_ns, mtimes[name])

    def test_unknown_source_in_either_patch_rejects_before_native_changes(self):
        for name in PATCHES:
            with self.subTest(patch=name):
                target = self.native / self.manifests[name]["target"]
                unknown = self.original_sources[name] + b"\n# unrelated upstream change\n"
                target.write_bytes(unknown)
                result = self.run_installer()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Native source changed", result.stderr)
                self.assert_unchanged({**self.original_sources, name: unknown})
                target.write_bytes(self.original_sources[name])

    def test_tampered_patch_in_either_manifest_rejects_before_native_changes(self):
        for name in PATCHES:
            with self.subTest(patch=name):
                patch = self.support / f"{name}.patch"
                original = patch.read_bytes()
                patch.write_bytes(original + b"\n")
                result = self.run_installer()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Verified patch hash differs", result.stderr)
                self.assert_unchanged()
                patch.write_bytes(original)

    def test_incorrect_after_hash_rejects_before_native_changes(self):
        path = self.support / "diagnostic_history_settlement.json"
        manifest = self.manifests["diagnostic_history_settlement"].copy()
        manifest["after_sha256"] = "0" * 64
        path.write_text(json.dumps(manifest))
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Native patch candidate verification failed", result.stderr)
        self.assert_unchanged()

    def test_patch_fuzz_is_rejected_even_with_a_matching_before_hash(self):
        name = PATCHES[0]
        before = "context 0\ncontext 1\ncontext 2\nold\ncontext 4\ncontext 5\ncontext 6\n"
        after = before.replace("old\n", "new\n")
        changed = before.replace("context 0\n", "different first context\n")
        manifest = self.manifests[name].copy()
        patch = "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                           fromfile="a/" + manifest["target"], tofile="b/" + manifest["target"]))
        patch_path = self.support / f"{name}.patch"
        patch_path.write_text(patch)
        target = self.native / manifest["target"]
        target.write_text(changed)
        manifest.update(before_sha256=digest(target),
                        after_sha256=hashlib.sha256(changed.replace("old\n", "new\n").encode()).hexdigest(),
                        patch_sha256=digest(patch_path))
        (self.support / f"{name}.json").write_text(json.dumps(manifest))
        # Negative control: GNU patch's default fuzz would accept this drift.
        permissive = subprocess.run(["patch", "--batch", "--dry-run", "-p1", "--input", str(patch_path)],
                                    cwd=self.native, text=True, capture_output=True)
        self.assertEqual(permissive.returncode, 0, permissive.stdout + permissive.stderr)
        self.assertIn("fuzz", permissive.stdout)
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assert_unchanged({**self.original_sources, name: changed.encode()})


if __name__ == "__main__":
    unittest.main()
