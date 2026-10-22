"""Run the real verified patch-chain installer only inside temporary native trees."""
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
EXPECTED_PATCHES = (
    "strict_material_coverage",
    "diagnostic_history_settlement",
    "diagnostic_retry_reset",
    "segmentation_raw_prediction_guard",
    "anchor_preview_recovery",
    "anchor_preview_index",
    "snapshot_export_inputs",
    "probe_preview_recovery",
)


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
        for relative in ("generate_simulation_mp4.sh", "native_patches.json"):
            shutil.copyfile(TOOLS / "diaggen_support" / relative, self.support / relative)
        series = json.loads((self.support / "native_patches.json").read_text())
        self.assertEqual(series["schema_version"], "diaggen-native-patch-series-v1")
        self.assertEqual(tuple(series["patches"]), EXPECTED_PATCHES)
        self.manifests = {}
        self.chains = {}
        for name in series["patches"]:
            for extension in ("json", "patch"):
                shutil.copyfile(TOOLS / "diaggen_support" / f"{name}.{extension}",
                                self.support / f"{name}.{extension}")
            manifest = json.loads((self.support / f"{name}.json").read_text())
            self.assertEqual(manifest["schema_version"], "diaggen-verified-native-patch-v1")
            self.assertEqual(digest(self.support / f"{name}.patch"), manifest["patch_sha256"])
            self.manifests[name] = manifest
            chain = self.chains.setdefault(manifest["target"], [])
            if chain:
                self.assertEqual(self.manifests[chain[-1]]["after_sha256"], manifest["before_sha256"])
            chain.append(name)

        # Roll each target backwards from its actual known state. Reversing
        # patches independently would corrupt a shared-target chain fixture.
        self.original_sources = {}
        for relative, chain in self.chains.items():
            target = self.native / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((TOOLS / "diaggen" / relative).read_bytes())
            known = [self.manifests[chain[0]]["before_sha256"],
                     *[self.manifests[name]["after_sha256"] for name in chain]]
            self.assertEqual(len(known), len(set(known)))
            self.assertIn(digest(target), known, f"unreviewed native source: {relative}")
            position = known.index(digest(target))
            for name in reversed(chain[:position]):
                self.apply_fixture_patch(name, reverse=True)
            self.assertEqual(digest(target), known[0])
            self.original_sources[relative] = target.read_bytes()

    def apply_fixture_patch(self, name, *, reverse=False):
        result = subprocess.run([
            "patch", "--batch", "--fuzz=0", "-p1",
            "--reverse" if reverse else "--forward",
            "--input", str(self.support / f"{name}.patch"),
        ], cwd=self.native, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest = self.manifests[name]
        expected = manifest["before_sha256"] if reverse else manifest["after_sha256"]
        self.assertEqual(digest(self.native / manifest["target"]), expected)

    def run_installer(self):
        return subprocess.run(["bash", str(self.installer)], cwd=self.temporary.name,
                              text=True, capture_output=True, timeout=30)

    def native_snapshot(self):
        """Capture contents and mtimes, including unexpected files and symlinks."""
        result = {}
        for path in self.native.rglob("*"):
            relative = str(path.relative_to(self.native))
            if path.is_symlink():
                result[relative] = ("symlink", path.readlink(), path.lstat().st_mtime_ns)
            elif path.is_file():
                result[relative] = ("file", path.read_bytes(), path.stat().st_mtime_ns)
        return result

    def assert_final(self):
        for relative, chain in self.chains.items():
            self.assertEqual(digest(self.native / relative), self.manifests[chain[-1]]["after_sha256"])
        encoder = self.native / "scripts/generate_simulation_mp4.sh"
        self.assertTrue(encoder.is_symlink())
        self.assertEqual(encoder.resolve(), (self.support / encoder.name).resolve())

    def assert_install_and_repeat(self):
        first = self.run_installer()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assert_final()
        installed = self.native_snapshot()
        second = self.run_installer()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assert_final()
        self.assertEqual(self.native_snapshot(), installed, "repeat changed native contents or mtimes")

    def assert_rejected_without_mutation(self, expected_message=None):
        before = self.native_snapshot()
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        if expected_message:
            self.assertIn(expected_message, result.stderr)
        self.assertEqual(self.native_snapshot(), before,
                         "installer modified a native fixture before rejecting the full series")

    def test_complete_series_installs_from_pristine_and_repeats_without_mtime_changes(self):
        self.assert_install_and_repeat()

    def test_install_from_each_shared_target_intermediate(self):
        intermediates = [(relative, chain, position)
                         for relative, chain in self.chains.items()
                         for position in range(1, len(chain))]
        self.assertTrue(intermediates, "series must exercise at least one shared-target chain")
        for relative, chain, position in intermediates:
            with self.subTest(target=relative, position=position):
                for source, content in self.original_sources.items():
                    (self.native / source).write_bytes(content)
                encoder = self.native / "scripts/generate_simulation_mp4.sh"
                if encoder.is_symlink():
                    encoder.unlink()
                for name in chain[:position]:
                    self.apply_fixture_patch(name)
                self.assert_install_and_repeat()

    def test_already_final_sources_keep_mtimes_on_first_and_repeated_install(self):
        for chain in self.chains.values():
            for name in chain:
                self.apply_fixture_patch(name)
        mtimes = {relative: (self.native / relative).stat().st_mtime_ns for relative in self.chains}
        self.assert_install_and_repeat()
        self.assertEqual({relative: (self.native / relative).stat().st_mtime_ns for relative in self.chains}, mtimes)

    def test_unknown_source_in_each_target_rejects_before_any_native_changes(self):
        for relative, original in self.original_sources.items():
            with self.subTest(target=relative):
                target = self.native / relative
                target.write_bytes(original + b"\n# unrelated upstream change\n")
                self.assert_rejected_without_mutation("Native source changed")
                target.write_bytes(original)

    def test_tampered_patch_anywhere_in_series_rejects_before_native_changes(self):
        for name in EXPECTED_PATCHES:
            with self.subTest(patch=name):
                path = self.support / f"{name}.patch"
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                self.assert_rejected_without_mutation("Verified patch hash differs")
                path.write_bytes(original)

    def test_discontinuous_shared_target_chain_rejects_before_native_changes(self):
        chain = next(chain for chain in self.chains.values() if len(chain) > 1)
        name = chain[1]
        path = self.support / f"{name}.json"
        manifest = self.manifests[name].copy()
        manifest["before_sha256"] = "0" * 64
        path.write_text(json.dumps(manifest))
        self.assert_rejected_without_mutation("Verified patch chain is discontinuous")

    def test_incorrect_final_after_hash_rejects_before_native_changes(self):
        # The last candidate fails after earlier candidates pass: no earlier
        # native file may have been installed in the meantime.
        name = list(self.chains.values())[-1][-1]
        path = self.support / f"{name}.json"
        manifest = self.manifests[name].copy()
        manifest["after_sha256"] = "0" * 64
        path.write_text(json.dumps(manifest))
        self.assert_rejected_without_mutation("Native patch candidate verification failed")

    def test_patch_fuzz_rejected_even_with_matching_manifest_hashes(self):
        relative, chain = next((relative, chain) for relative, chain in self.chains.items()
                               if len(chain) == 1)
        name = chain[0]
        before = "context 0\ncontext 1\ncontext 2\nold\ncontext 4\ncontext 5\ncontext 6\n"
        after = before.replace("old\n", "new\n")
        changed = before.replace("context 0\n", "different first context\n")
        proposal = "".join(difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile="a/" + relative, tofile="b/" + relative))
        patch_path = self.support / f"{name}.patch"
        patch_path.write_text(proposal)
        target = self.native / relative
        target.write_text(changed)
        manifest = self.manifests[name].copy()
        manifest.update(before_sha256=digest(target),
                        after_sha256=hashlib.sha256(changed.replace("old\n", "new\n").encode()).hexdigest(),
                        patch_sha256=digest(patch_path))
        (self.support / f"{name}.json").write_text(json.dumps(manifest))
        # Negative control: default GNU patch would silently accept this drift.
        permissive = subprocess.run(["patch", "--batch", "--dry-run", "-p1", "--input", str(patch_path)],
                                    cwd=self.native, text=True, capture_output=True, timeout=20)
        self.assertEqual(permissive.returncode, 0, permissive.stdout + permissive.stderr)
        self.assertIn("fuzz", permissive.stdout)
        self.assert_rejected_without_mutation()

    def test_duplicate_series_entry_rejects_before_native_changes(self):
        path = self.support / "native_patches.json"
        series = json.loads(path.read_text())
        series["patches"].append(series["patches"][0])
        path.write_text(json.dumps(series))
        self.assert_rejected_without_mutation("Invalid verified native patch series")

    def test_conflicting_encoder_rejects_before_native_changes(self):
        (self.native / "scripts/generate_simulation_mp4.sh").write_text("preserve upstream encoder\n")
        self.assert_rejected_without_mutation("Existing upstream encoder differs")


if __name__ == "__main__":
    unittest.main()
