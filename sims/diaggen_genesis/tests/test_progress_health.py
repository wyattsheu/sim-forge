"""Negative controls for the public read-only diagnostic health observer."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "queue/publish_progress.py"
SPEC = importlib.util.spec_from_file_location("health_publisher", SOURCE)
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)
NOW = datetime(2026, 10, 22, 7, 0, tzinfo=timezone.utc)


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "run"
        self.workspace = self.root / "revisions/revision_0000/sim_diagnostics"
        self.audit = self.workspace / "material_audit_authoritative/revision_0000"
        self.audit.mkdir(parents=True)
        self.state = {
            "active_revision": "revision_0000", "updated_at": "2026-10-22T06:40:00+00:00",
            "paths": {"diagnostic_workspace_dir": str(self.workspace)},
            "diagnostics": {"episodes": [], "terminal": None},
            "diagnostic_runtime_attachments": [{
                "status": "attached", "attachment_id": "PRIVATE_SECRET",
                "owner_lease": {"owner_lease_token": "PRIVATE_SECRET", "lease_id": "PRIVATE_SECRET",
                                "expires_at": "2026-10-22T07:45:00+00:00", "in_flight_count": 0}}],
        }

    def result(self, phase="running"):
        return publisher.runtime_health(self.state, self.root, phase, observed_at=NOW)

    def test_stale_is_review_signal_not_failure_or_retry(self):
        result = self.result()
        self.assertEqual(result["warnings"], ["diagnostic_idle_review"])
        self.assertEqual(result["meaning"], "observation_only_not_retry_authorization")
        self.assertNotIn("status", result)

    def test_recent_update_and_inflight_are_not_idle(self):
        self.state["updated_at"] = "2026-10-22T06:59:00+00:00"
        self.assertEqual(self.result()["warnings"], [])
        self.state["updated_at"] = "2026-10-22T06:00:00+00:00"
        self.state["diagnostic_runtime_attachments"][0]["owner_lease"]["in_flight_count"] = 1
        self.assertEqual(self.result()["warnings"], [])

    def test_expired_wait_is_distinct_from_active_wait(self):
        self.state["diagnostic_runtime_attachments"][0]["owner_lease"]["expires_at"] = "2026-10-22T07:00:00+00:00"
        self.assertEqual(self.result()["warnings"], ["diagnostic_cleanup_due"])

    def test_invalid_time_never_assumes_expired(self):
        for invalid in (None, "bad", "2026-10-22T06:00:00"):
            with self.subTest(invalid=invalid):
                self.state["updated_at"] = invalid
                self.assertEqual(self.result()["warnings"], ["diagnostic_timestamp_invalid"])

    def test_terminal_and_nonrunning_are_not_reported_idle(self):
        for phase in ("failed", "success", "waiting_gpu"):
            self.assertEqual(self.result(phase)["warnings"], [])
        self.state["diagnostics"]["terminal"] = {"status": "halted"}
        self.assertEqual(self.result()["warnings"], [])

    def test_orphan_snapshot_and_current_registration(self):
        (self.audit / "cleaned_source_image.png").write_bytes(b"unchanged evidence")
        self.assertIn("audit_snapshot_collision", self.result()["warnings"])
        self.state["diagnostics"]["source_semantic_material_artifact_registrations"] = [
            {"active_revision_id": "revision_old"}]
        self.assertIn("audit_snapshot_collision", self.result()["warnings"])
        self.state["diagnostics"]["source_semantic_material_artifact_registrations"].append(
            {"active_revision_id": "revision_0000"})
        self.assertNotIn("audit_snapshot_collision", self.result()["warnings"])

    def test_unrelated_files_do_not_trigger_collision(self):
        (self.audit / "preview.png").write_bytes(b"preview")
        self.assertNotIn("audit_snapshot_collision", self.result()["warnings"])

    def test_external_workspace_and_symlink_are_not_followed(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        self.state["paths"]["diagnostic_workspace_dir"] = str(outside)
        self.assertIn("audit_path_invalid", self.result()["warnings"])
        self.state["paths"]["diagnostic_workspace_dir"] = str(self.workspace)
        self.audit.rmdir()
        self.audit.symlink_to(outside, target_is_directory=True)
        self.assertIn("audit_path_invalid", self.result()["warnings"])

    def test_observation_does_not_mutate_state_or_files_or_publish_private_values(self):
        file = self.audit / "cleaned_source_image.png"
        file.write_bytes(b"original")
        before_state = deepcopy(self.state)
        before_hash = hashlib.sha256(file.read_bytes()).hexdigest()
        result = self.result()
        self.assertEqual(self.state, before_state)
        self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), before_hash)
        text = json.dumps(result)
        for secret in ("PRIVATE_SECRET", str(self.root), "expires_at", "owner_lease", "attachment_id"):
            self.assertNotIn(secret, text)

    def test_heartbeats_do_not_change_signature_but_new_evidence_does(self):
        first = self.result()
        self.state["updated_at"] = "2026-10-22T06:41:00+00:00"
        self.state["diagnostic_runtime_attachments"][0]["owner_lease"]["expires_at"] = "2026-10-22T07:46:00+00:00"
        self.assertEqual(publisher.semantic_signature(first), publisher.semantic_signature(self.result()))
        self.state["diagnostics"]["tool_results"] = [{"raw_secret": "PRIVATE_SECRET"}]
        self.assertNotEqual(publisher.semantic_signature(first), publisher.semantic_signature(self.result()))


if __name__ == "__main__":
    unittest.main()
