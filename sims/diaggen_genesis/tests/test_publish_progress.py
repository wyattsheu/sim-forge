"""CPU-only observer tests; all Git pushes target a temporary local bare repo."""
from __future__ import annotations

import base64
from copy import deepcopy
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

    def install_batch(self):
        ids = ("usb_hub", "baseball_cap", "curling_iron", "sloth", "sauce_keeper",
               "sneaker", "kitchen_tongs", "dragon", "capybara")
        self.batch = {
            "schema_version": "diaggen-batch-v1",
            "policy": {"minimum_free_mib": 24576, "allow_compute_sharing": True,
                       "check_interval_seconds": 15, "max_parallel_jobs": 2,
                       "owner_lease_token": "PRIVATE_SECRET"},
            "jobs": [{"id": name, "run_id": "test_run" if index == 0 else f"test_run_{name}",
                      "input": f"/PRIVATE_SECRET/{name}.png",
                      "status": "running" if index == 0 else "queued",
                      "gpu_uuid": "PRIVATE_SECRET", "runner_pid": 123456789,
                      "attempts": 1 if index == 0 else 0,
                      "detail": "PRIVATE_SECRET"} for index, name in enumerate(ids)],
        }
        write_json(self.queue / "batch.json", self.batch)
        return self.batch

    def write_job_state(self, index, **changes):
        job = self.batch["jobs"][index]
        state = deepcopy(self.state)
        state.update(run_id=job["run_id"], **changes)
        path = self.workspace / "tools/diaggen/outputs/agentic_asset_refinement" / job["run_id"] / "state.json"
        write_json(path, state)
        return state, path

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

    def test_batch_nonfocus_progress_pushes_and_heartbeat_deduplicates(self):
        self.install_batch()
        publisher.sync_once(self.workspace, self.worktree)
        initial = run_git(self.worktree, "rev-parse", "HEAD")
        self.status["updated_at"] = "2026-10-21T13:00:00+08:00"
        self.batch["jobs"][8]["runner_pid"] = 987654321
        self.flush()
        write_json(self.queue / "batch.json", self.batch)
        result = publisher.sync_once(self.workspace, self.worktree)
        self.assertFalse(result["changed"])
        self.assertEqual(initial, run_git(self.worktree, "rev-parse", "HEAD"))
        self.write_job_state(8, active_revision="r009")
        publisher.sync_once(self.workspace, self.worktree)
        latest = run_git(self.worktree, "rev-parse", "HEAD")
        self.assertNotEqual(initial, latest)
        self.assertEqual(latest, run_git(self.remote, "rev-parse", f"refs/heads/{publisher.BRANCH}"))


class BatchTests(unittest.TestCase):
    flush = SnapshotTests.flush
    install_batch = SnapshotTests.install_batch
    write_job_state = SnapshotTests.write_job_state

    def setUp(self):
        SnapshotTests.setUp(self)
        self.install_batch()

    def test_per_job_memory_override_is_public_bounded_and_uses_global_floor(self):
        self.batch["jobs"][0]["minimum_free_mib"] = 49152
        self.batch["jobs"][1]["minimum_free_mib"] = 1024
        self.batch["jobs"][2]["minimum_free_mib"] = True
        self.batch["jobs"][3]["minimum_free_mib"] = "PRIVATE_SECRET"
        write_json(self.queue / "batch.json", self.batch)
        snapshot, _ = publisher.build_snapshot(self.workspace)
        self.assertEqual(snapshot["jobs"][0]["minimum_free_mib"], 49152)
        self.assertEqual([job["minimum_free_mib"] for job in snapshot["jobs"][1:4]],
                         [24576, 24576, 24576])
        report = publisher.render_readme(snapshot)
        self.assertIn("49152 MiB", report)
        self.assertNotIn("PRIVATE_SECRET", json.dumps(snapshot) + report)

    def test_all_nine_jobs_counts_policy_and_no_private_fields(self):
        snapshot, _ = publisher.build_snapshot(self.workspace)
        self.assertEqual(len(snapshot["jobs"]), 9)
        self.assertEqual(snapshot["counts"]["total"], 9)
        self.assertEqual(snapshot["counts"]["running"], 1)
        self.assertEqual(snapshot["counts"]["queued"], 8)
        self.assertEqual(snapshot["policy"], {"minimum_free_mib": 24576, "allow_compute_sharing": True,
                                             "check_interval_seconds": 15, "max_parallel_jobs": 2})
        self.assertTrue(all(len(job["stages"]) == 9 for job in snapshot["jobs"]))
        text = json.dumps(snapshot) + publisher.render_readme(snapshot)
        for forbidden in ("PRIVATE_SECRET", "gpu_uuid", "runner_pid", "owner_lease", str(self.workspace), "123456789"):
            self.assertNotIn(forbidden, text)
        self.assertIn("capybara", text)
        self.assertIn("24576 MiB", text)

    def test_nonfocus_revision_and_stage_change_update_signature(self):
        first, _ = publisher.build_snapshot(self.workspace)
        state, path = self.write_job_state(8, active_revision="r002")
        second, _ = publisher.build_snapshot(self.workspace)
        self.assertNotEqual(first["signature"], second["signature"])
        self.assertEqual(second["jobs"][0]["active_revision"], first["jobs"][0]["active_revision"])
        state["stages"]["image_cleanup"]["started_at"] = "2026-10-21T13:00:00+08:00"
        write_json(path, state)
        third, _ = publisher.build_snapshot(self.workspace)
        self.assertNotEqual(second["signature"], third["signature"])
        self.assertEqual(third["jobs"][8]["stages"][0]["status"], "running")

    def test_job_status_transitions_are_not_hidden_by_focus(self):
        first, _ = publisher.build_snapshot(self.workspace)
        self.batch["jobs"][8]["status"] = "failed"
        write_json(self.queue / "batch.json", self.batch)
        second, _ = publisher.build_snapshot(self.workspace)
        self.assertNotEqual(first["signature"], second["signature"])
        self.assertEqual(second["counts"]["failed"], 1)
        self.assertEqual(second["jobs"][8]["phase"], "failed")

    def test_job_heartbeat_private_fields_and_confirming_gpu_do_not_change_signature(self):
        first, _ = publisher.build_snapshot(self.workspace)
        self.batch["updated_at"] = "2026-10-21T14:00:00+08:00"
        self.batch["jobs"][8].update(runner_pid=123, gpu_uuid="NEW_PRIVATE_GPU")
        write_json(self.queue / "batch.json", self.batch)
        write_json(self.queue / "jobs/capybara/status.json", {
            "run_id": "test_run_capybara", "phase": "confirming_gpu",
            "updated_at": "2026-10-21T14:00:00+08:00", "owner_lease_token": "PRIVATE_SECRET",
        })
        second, _ = publisher.build_snapshot(self.workspace)
        self.assertEqual(first["signature"], second["signature"])

    def test_all_jobs_share_one_media_budget_and_safe_prefixes(self):
        for index in range(3):
            state, path = self.write_job_state(index)
            image = path.parent / "preview.png"
            image.write_bytes(PNG)
            state["paths"] = {"cleaned_image_path": str(image)}
            write_json(path, state)
        with patch.object(publisher, "MAX_MEDIA_BYTES", len(PNG) * 2):
            snapshot, media = publisher.build_snapshot(self.workspace)
        self.assertEqual(len(media), 2)
        self.assertEqual(sum(len(data) for _, data in media), len(PNG) * 2)
        self.assertEqual([name for name, _ in media], ["media/usb_hub_cleaned_image.png", "media/baseball_cap_cleaned_image.png"])
        self.assertEqual(len(snapshot["media"]), 2)
        self.assertTrue(all(publisher.allowed_output(str(publisher.PROGRESS / name)) for name, _ in media))

    def test_per_job_status_is_observed_but_sensitive_detail_is_not_published(self):
        write_json(self.queue / "jobs/usb_hub/status.json", {
            "run_id": "test_run", "phase": "blocked", "detail": "PRIVATE_SECRET",
            "generation_and_diagnostics_model": "gpt-6-luna", "reasoning_effort": "max",
        })
        snapshot, _ = publisher.build_snapshot(self.workspace)
        self.assertEqual(snapshot["jobs"][0]["phase"], "blocked")
        self.assertNotIn("PRIVATE_SECRET", json.dumps(snapshot))

    def test_batch_identifier_collisions_and_schema_mismatch_fail_closed(self):
        self.batch["jobs"][8]["id"] = "usb_hub"
        write_json(self.queue / "batch.json", self.batch)
        with self.assertRaises(ValueError):
            publisher.build_snapshot(self.workspace)
        self.install_batch()
        self.batch["schema_version"] = "unknown"
        write_json(self.queue / "batch.json", self.batch)
        with self.assertRaises(ValueError):
            publisher.build_snapshot(self.workspace)


if __name__ == "__main__":
    unittest.main()
