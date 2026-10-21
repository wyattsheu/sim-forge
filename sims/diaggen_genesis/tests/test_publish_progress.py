"""CPU-only observer tests; all Git pushes target a temporary local bare repo."""
from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "queue/publish_progress.py"
SPEC = importlib.util.spec_from_file_location("diaggen_publish_progress", MODULE_PATH)
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l1sAAAAASUVORK5CYII=")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def run_git(directory, *arguments):
    result = subprocess.run(["git", "-C", str(directory), *arguments],
                            text=True, capture_output=True, timeout=20)
    if result.returncode:
        raise AssertionError(f"temporary Git test failed: {arguments[0]}: {result.stderr}")
    return result.stdout.strip()


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="diaggen-publisher-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.workspace = self.base / "workspace"
        self.queue = self.workspace / "sims/diaggen_genesis/queue"
        self.run_root = self.workspace / "tools/diaggen/outputs/agentic_asset_refinement/test_run"
        self.status = {
            "phase": "waiting_gpu", "run_id": "test_run",
            "updated_at": "2026-10-21T11:00:00+08:00",
            "simulator": "Genesis", "generation_and_diagnostics_model": "gpt-6-luna",
            "reasoning_effort": "max", "detail": "PRIVATE_SECRET GPU-PRIVATE",
            "watcher_pid": "PRIVATE_SECRET", "working_run_root": "/PRIVATE_SECRET",
        }
        self.state = {
            "run_id": "test_run", "status": "running", "active_revision": "r001",
            "created_at": "2026-10-21T11:00:00+08:00",
            "updated_at": "2026-10-21T11:00:00+08:00",
            "stages": {
                "image_cleanup": {
                    "ok": False, "status": "pending", "started_at": None,
                    "outputs": {"secret": "PRIVATE_SECRET"}, "error": "PRIVATE_SECRET",
                    "tool_calls": [{"tool_name": "PRIVATE_SECRET", "inputs_summary": {"owner_lease_token": "PRIVATE_SECRET"}}],
                }
            },
            "paths": {},
            "diagnostic_runtime_attachments": [{"owner_lease": {"lease_id": "PRIVATE_SECRET"}}],
            "diagnostic_runtime_sessions": [{"handle": "PRIVATE_SECRET"}],
            "diagnostics": {
                "enabled": True, "episodes": [],
                "terminal": {"status": "pending", "error": "PRIVATE_SECRET", "owner_lease_token": "PRIVATE_SECRET"},
            },
            "runtime_events": [{"secret": "PRIVATE_SECRET"}],
        }
        self.flush()

    def flush(self):
        write_json(self.queue / "status.json", self.status)
        write_json(self.run_root / "state.json", self.state)

    def snapshot(self):
        self.flush()
        return publisher.build_snapshot(self.workspace)

    def test_whitelist_removes_secrets_paths_and_raw_diagnostics(self):
        snapshot, _ = self.snapshot()
        text = json.dumps(snapshot) + publisher.render_readme(snapshot)
        for forbidden in ("PRIVATE_SECRET", str(self.workspace), "owner_lease", "tool_calls", "watcher_pid", "runtime_events"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(snapshot["simulator"], "Genesis")
        self.assertEqual(len(snapshot["stages"]), 9)

    def test_started_pending_stage_displays_running(self):
        self.state["stages"]["image_cleanup"]["started_at"] = "2026-10-21T11:03:00+08:00"
        snapshot, _ = self.snapshot()
        first = snapshot["stages"][0]
        self.assertEqual(first["ledger_status"], "pending")
        self.assertEqual(first["status"], "running")

    def test_timestamps_and_confirmation_do_not_change_signature(self):
        first, _ = self.snapshot()
        self.status.update(phase="confirming_gpu", updated_at="2026-10-21T11:05:00+08:00")
        self.state["updated_at"] = "2026-10-21T11:05:00+08:00"
        second, _ = self.snapshot()
        self.assertEqual(first["signature"], second["signature"])
        self.assertEqual(second["phase"], "waiting_gpu")

    def test_revision_change_changes_signature(self):
        first, _ = self.snapshot()
        self.state["active_revision"] = "r002"
        second, _ = self.snapshot()
        self.assertNotEqual(first["signature"], second["signature"])

    def test_preview_whitelist_and_bounds(self):
        preview = self.run_root / "image_cleanup/object.png"
        preview.parent.mkdir(parents=True)
        preview.write_bytes(PNG)
        outside = self.base / "outside.png"
        outside.write_bytes(PNG)
        self.state["paths"] = {
            "cleaned_image_path": str(preview), "albedo_path": str(outside),
            "source_image": str(preview), "not_whitelisted": str(preview),
        }
        snapshot, files = self.snapshot()
        self.assertEqual([name for name, _ in files], ["media/cleaned_image.png"])
        self.assertNotIn(str(preview), json.dumps(snapshot))
        preview.unlink()
        preview.symlink_to(outside)
        _, files = self.snapshot()
        self.assertEqual(files, [])

    def test_final_export_media_is_allowed_only_inside_outputs(self):
        export = self.workspace / "tools/diaggen/outputs/run_pipeline/test_run"
        export.mkdir(parents=True)
        video = export / "probe.mp4"
        video.write_bytes(b"\0\0\0\x18ftypisom" + b"\0" * 30)
        self.state["paths"]["final_export_dir"] = str(export)
        self.state["diagnostics"]["episodes"] = [{"video_path": str(video), "token": "PRIVATE_SECRET"}]
        _, files = self.snapshot()
        self.assertEqual([name for name, _ in files], ["media/episode_001_video.mp4"])
        self.state["paths"]["final_export_dir"] = str(self.base)
        _, files = self.snapshot()
        self.assertEqual(files, [])

    def test_media_budget_and_mislabeled_text(self):
        for key, filename in (("cleaned_image_path", "first.png"), ("albedo_path", "second.png")):
            path = self.run_root / filename
            path.write_bytes(PNG)
            self.state["paths"][key] = str(path)
        with patch.object(publisher, "MAX_MEDIA_BYTES", len(PNG)):
            _, files = self.snapshot()
            self.assertEqual(len(files), 1)
        with patch.object(publisher, "MAX_FILE_BYTES", len(PNG) - 1):
            _, files = self.snapshot()
            self.assertEqual(files, [])
        Path(self.state["paths"]["cleaned_image_path"]).write_text("PRIVATE_SECRET")
        del self.state["paths"]["albedo_path"]
        _, files = self.snapshot()
        self.assertEqual(files, [])

    def test_invalid_run_identifier_is_rejected(self):
        self.status["run_id"] = "../../outside"
        self.flush()
        with self.assertRaises(ValueError):
            publisher.build_snapshot(self.workspace)

    def test_missing_runtime_is_explicitly_not_initialized(self):
        (self.run_root / "state.json").unlink()
        snapshot, files = publisher.build_snapshot(self.workspace)
        self.assertEqual(snapshot["pipeline_status"], "not_initialized")
        self.assertIsNone(snapshot["diagnostics"]["enabled"])
        self.assertEqual(files, [])


class GitTests(SnapshotTests):
    def setUp(self):
        super().setUp()
        self.remote = self.base / "remote.git"
        self.worktree = self.base / "publishing-worktree"
        self.worktree.mkdir()
        run_git(self.base, "init", "--bare", str(self.remote))
        run_git(self.worktree, "init", f"--initial-branch={publisher.BRANCH}")
        run_git(self.worktree, "config", "user.name", "Publisher Test")
        run_git(self.worktree, "config", "user.email", "publisher-test@example.invalid")
        (self.worktree / "baseline.txt").write_text("baseline\n")
        run_git(self.worktree, "add", "--", "baseline.txt")
        run_git(self.worktree, "commit", "-m", "Test baseline")
        run_git(self.worktree, "remote", "add", "origin", str(self.remote))

    def test_real_local_push_dedupe_revision_and_no_attribution(self):
        result = publisher.sync_once(self.workspace, self.worktree)
        self.assertTrue(result["pushed"])
        first = run_git(self.worktree, "rev-parse", "HEAD")
        self.assertEqual(first, run_git(self.remote, "rev-parse", f"refs/heads/{publisher.BRANCH}"))
        self.status["updated_at"] = "2026-10-21T12:00:00+08:00"
        self.status["phase"] = "confirming_gpu"
        self.flush()
        result = publisher.sync_once(self.workspace, self.worktree)
        self.assertFalse(result["changed"])
        self.assertFalse(result["pushed"])
        self.assertEqual(first, run_git(self.worktree, "rev-parse", "HEAD"))
        self.state["active_revision"] = "r002"
        self.flush()
        publisher.sync_once(self.workspace, self.worktree)
        self.assertNotEqual(first, run_git(self.worktree, "rev-parse", "HEAD"))
        message = run_git(self.worktree, "log", "-1", "--format=%B").lower()
        self.assertNotIn("co-authored-by", message)
        self.assertNotIn("coworker", message)
        public = (self.worktree / publisher.PROGRESS / "status.json").read_text()
        self.assertNotIn("PRIVATE_SECRET", public)

    def test_failed_push_retries_unchanged_local_commit(self):
        run_git(self.worktree, "remote", "set-url", "origin", str(self.base / "missing.git"))
        with self.assertRaises(RuntimeError):
            publisher.sync_once(self.workspace, self.worktree)
        committed = run_git(self.worktree, "rev-parse", "HEAD")
        run_git(self.worktree, "remote", "set-url", "origin", str(self.remote))
        result = publisher.sync_once(self.workspace, self.worktree)
        self.assertFalse(result["changed"])
        self.assertTrue(result["pushed"])
        self.assertEqual(committed, run_git(self.worktree, "rev-parse", "HEAD"))
        self.assertEqual(committed, run_git(self.remote, "rev-parse", f"refs/heads/{publisher.BRANCH}"))

    def test_unrelated_staging_and_branch_are_rejected(self):
        (self.worktree / "unrelated.txt").write_text("do not commit\n")
        run_git(self.worktree, "add", "--", "unrelated.txt")
        with self.assertRaises(ValueError):
            publisher.sync_once(self.workspace, self.worktree)
        self.assertEqual(run_git(self.worktree, "diff", "--cached", "--name-only"), "unrelated.txt")
        run_git(self.worktree, "restore", "--staged", "--", "unrelated.txt")
        run_git(self.worktree, "checkout", "-b", "main")
        with self.assertRaises(ValueError):
            publisher.sync_once(self.workspace, self.worktree)

    def test_root_index_is_untouched_and_media_removed_explicitly(self):
        run_git(self.workspace, "init")
        (self.workspace / "user-work.txt").write_text("user staged work\n")
        run_git(self.workspace, "add", "--", "user-work.txt")
        before = run_git(self.workspace, "diff", "--cached", "--name-only")
        image = self.run_root / "object.png"
        image.write_bytes(PNG)
        self.state["paths"]["cleaned_image_path"] = str(image)
        self.flush()
        publisher.sync_once(self.workspace, self.worktree)
        self.assertTrue((self.worktree / publisher.PROGRESS / "media/cleaned_image.png").exists())
        self.state["paths"] = {}
        self.flush()
        publisher.sync_once(self.workspace, self.worktree)
        self.assertFalse((self.worktree / publisher.PROGRESS / "media/cleaned_image.png").exists())
        self.assertEqual(before, run_git(self.workspace, "diff", "--cached", "--name-only"))

    def test_dry_run_produces_snapshot_without_a_commit(self):
        before = run_git(self.worktree, "rev-parse", "HEAD")
        result = publisher.sync_once(self.workspace, self.worktree, dry_run=True)
        self.assertTrue(result["changed"])
        self.assertEqual(before, run_git(self.worktree, "rev-parse", "HEAD"))
        self.assertTrue((self.worktree / publisher.PROGRESS / "status.json").is_file())
        # Simulate recovery after files were written but never staged/committed.
        result = publisher.sync_once(self.workspace, self.worktree)
        self.assertFalse(result["changed"])
        self.assertTrue(result["pushed"])
        self.assertNotEqual(before, run_git(self.worktree, "rev-parse", "HEAD"))


if __name__ == "__main__":
    unittest.main()
