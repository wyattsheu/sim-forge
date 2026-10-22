"""Regression controls for immutable material-audit snapshots across retries."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "tools/diaggen"
sys.path.insert(0, str(NATIVE))

from hag4r.agentic.runtime_tools import diagnostics as native


class MaterialAuditRetryNamespaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="diaggen-material-audit-retry-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.run_root = self.root / "run"
        self.run_root.mkdir()
        self.workspace = self.root / "sim_diagnostics"
        self.workspace.mkdir()
        self.source_dir = self.repo / "sources"
        self.source_dir.mkdir()
        self.sources = {
            "raw_source_image": ("source_image", "raw.png", b"raw input"),
            "cleaned_source_image": ("cleaned_image_path", "cleaned.png", b"cleaned input"),
            "object_description": ("object_description_path", "description.json", b"{\"object\":\"fixture\"}"),
            "material_inference_payload": ("inferred_params_path", "material.json", b"{\"material\":1}"),
        }
        paths = {}
        for artifact_id, (key, filename, contents) in self.sources.items():
            path = self.source_dir / filename
            path.write_bytes(contents)
            paths[key] = str(path)
        context = {"parts": [{"part_id": "fixture_part", "part_name": "fixture"}]}
        self.context_path = self.workspace / "part_grounding_context.json"
        self.context_path.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n")
        paths.update({
            "diagnostic_workspace_dir": str(self.workspace),
            "diagnostic_workspace_index_path": str(self.workspace / "index.json"),
            "diagnostic_workspace_markdown_index_path": str(self.workspace / "index.md"),
            "diagnostic_log_path": str(self.workspace / "diagnostic.log"),
            "diagnostic_observations_digest_path": str(self.workspace / "observations_digest.json"),
        })
        self.state = {
            "run_root": str(self.run_root),
            "repo_root": str(self.repo),
            "active_revision": "revision_0000",
            "paths": paths,
            "diagnostics": {
                "part_grounding_context": context,
                "diagnostic_attempt_archives": [self.valid_archive()],
                "active_diagnostic_attempt_id": "diagnostic_attempt_0002",
            },
        }
        self.runtime_paths = {"workspace_dir": self.workspace, "part_grounding_context": self.context_path}
        self.canonical = self.workspace / "material_audit_authoritative" / "revision_0000"

    @staticmethod
    def valid_archive():
        return {
            "schema_version": "hag4r-diagnostic-attempt-archive-v1",
            "archive_id": "diagnostic_attempt_archive_0001",
            "archived_at": "2026-10-22T00:00:00+00:00",
            "recovery_cause": "mcp_server_shutdown",
            "recovery_event_id": "fixture_recovery_event",
            "source_attachment_id": "fixture_attachment",
            "source_agent_invocation_id": "fixture_child",
            "source_session_handles": ["fixture_session"],
            "source_attempt_id": "diagnostic_attempt_0001",
            "execution_snapshot": {},
            "removed_route_projection": {},
        }

    def seed_canonical_snapshots(self):
        self.canonical.mkdir(parents=True)
        originals = {}
        names = {
            "raw_source_image": "raw_source_image.png",
            "cleaned_source_image": "cleaned_source_image.png",
            "object_description": "object_description.json",
            "material_inference_payload": "material_inference_payload.json",
        }
        for artifact_id, filename in names.items():
            path = self.canonical / filename
            path.write_bytes(("prior:" + artifact_id).encode())
            originals[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        return originals

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_retry_uses_attempt_namespace_and_preserves_prior_snapshots(self):
        originals = self.seed_canonical_snapshots()
        state = copy.deepcopy(self.state)
        registration = native.initialize_source_semantic_material_artifact_registration(
            state, runtime_paths=self.runtime_paths
        )
        self.assertTrue(registration["complete"])
        self.assertEqual(len(registration["artifacts"]), 5)
        attempt_root = self.canonical / "diagnostic_attempt_0002"
        by_id = {item["artifact_id"]: item for item in registration["artifacts"]}
        for artifact_id, (_, filename, contents) in self.sources.items():
            entry = by_id[artifact_id]
            snapshot = self.workspace / entry["workspace_path"]
            self.assertEqual(entry["workspace_path"], f"material_audit_authoritative/revision_0000/diagnostic_attempt_0002/{artifact_id}{Path(filename).suffix}")
            self.assertEqual(snapshot.parent, attempt_root)
            self.assertEqual(snapshot.read_bytes(), contents)
            self.assertEqual(self.digest(snapshot), entry["source_sha256"])
        for path, before in originals.items():
            self.assertEqual(self.digest(path), before)

        registered = native.initialize_source_semantic_material_artifact_registration(
            state, runtime_paths=self.runtime_paths
        )
        self.assertEqual(registered, registration)
        native._verify_all_material_audit_authoritative_artifacts(
            state, {item["artifact_id"]: item for item in registration["artifacts"]}
        )
        for path, before in originals.items():
            self.assertEqual(self.digest(path), before)

    def test_invalid_attempt_lineage_is_rejected_before_snapshot_writes(self):
        cases = []
        no_active_id = copy.deepcopy(self.state)
        no_active_id["diagnostics"]["active_diagnostic_attempt_id"] = None
        cases.append(("archived attempt without active namespace", no_active_id))
        bad_archive = copy.deepcopy(self.state)
        bad_archive["diagnostics"]["diagnostic_attempt_archives"][0]["archive_id"] = "wrong"
        cases.append(("malformed archive lineage", bad_archive))
        unsafe_id = copy.deepcopy(self.state)
        unsafe_id["diagnostics"]["active_diagnostic_attempt_id"] = "../escape"
        cases.append(("unsafe attempt id", unsafe_id))

        for label, state in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(native.GenesisVlmSchemaError, "invalid diagnostic attempt namespace"):
                    native.initialize_source_semantic_material_artifact_registration(
                        state, runtime_paths=self.runtime_paths
                    )
                self.assertFalse(self.canonical.exists())

    def test_first_attempt_keeps_existing_immutable_collision_guard(self):
        originals = self.seed_canonical_snapshots()
        state = copy.deepcopy(self.state)
        state["diagnostics"]["diagnostic_attempt_archives"] = []
        state["diagnostics"]["active_diagnostic_attempt_id"] = None
        with self.assertRaisesRegex(
            native.GenesisVlmSchemaError,
            "material audit registration snapshot path already exists: cleaned_source_image",
        ):
            native.initialize_source_semantic_material_artifact_registration(
                state, runtime_paths=self.runtime_paths
            )
        self.assertFalse((self.canonical / "diagnostic_attempt_0002").exists())
        for path, before in originals.items():
            self.assertEqual(self.digest(path), before)


if __name__ == "__main__":
    unittest.main()
