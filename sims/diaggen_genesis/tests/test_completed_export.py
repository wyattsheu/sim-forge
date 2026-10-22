"""Completion settlement accepts real artifact evidence and rejects broken ledgers."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


WORKSPACE = Path(__file__).resolve().parents[3]
SCRIPT = Path(os.environ.get("DIAGGEN_COMPLETION_VALIDATOR_UNDER_TEST", WORKSPACE / "tools/diaggen_support/validate_completed_export.py"))
SPEC = importlib.util.spec_from_file_location("validate_completed_export", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
MODULE.NATIVE_CODE_ROOT = WORKSPACE / "tools/diaggen"


class CompletedExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run = self.root / "outputs/agentic_asset_refinement/example"
        self.revision = self.run / "revisions/revision_0000"
        self.export = self.root / "outputs/run_pipeline/example"
        self.state_path = self.run / "state.json"
        self.manifest_path = self.export / "final_export_manifest.json"
        self.native = mock.patch.object(MODULE, "_native_checks", return_value={
            "native_tet_valid": True, "native_appearance_valid": True,
        }).start()
        self.addCleanup(mock.patch.stopall)
        self.paths = {}
        self.sources = {}
        self.records = {}
        for name, key in MODULE.PHYSICAL.items():
            source = self.revision / "physical" / name
            target = self.export / name
            self.write_bytes(source, name.encode())
            self.write_bytes(target, name.encode())
            self.paths[key] = str(source)
            self.sources[name] = self.record(source)
            self.records[name] = self.record(target)
        self.appearance = self.revision / "post_mesh_texture"
        self.paths["post_mesh_texture_dir"] = str(self.appearance)
        for name in ("visual_mesh.glb", "albedo.png", "visual_to_physics.npz", "visual_manifest.json",
                     "post_mesh_texture_request.json", "qa/observed_coverage.png", "qa/fill_provenance.png",
                     "qa/confidence.png", "qa/rest_pose_render.png", "qa/report.json"):
            source, target = self.appearance / name, self.export / "appearance" / name
            self.write_bytes(source, name.encode())
            self.write_bytes(target, name.encode())
            self.records["appearance/" + name] = self.record(target)
        ownership = self.revision / "sim_diagnostics/runtime_ownership.json"
        self.write_bytes(ownership, b"{}")
        self.sources["diagnostic_runtime_ownership"] = str(ownership)
        self.manifest = {
            "run_id": "example", "accepted_revision": "revision_0000", "export_revision": "revision_0000",
            "canonical_files": [*self.records, "final_export_manifest.json"],
            "exported_artifacts": self.records, "source_artifacts": self.sources,
            "asset_refinement_source_dir": str(self.revision),
            "source_directories": {"asset_refinement": str(self.revision),
                                   "sim_diagnostics": str(self.revision / "sim_diagnostics")},
            "auxiliary_source_artifacts": {},
        }
        self.paths.update(final_export_dir=str(self.export), final_export_manifest_path=str(self.manifest_path))
        auxiliary = {
            "cleaned_image.png": self.revision / "image_cleanup/cleaned.png",
            "image_cleanup.json": self.revision / "image_cleanup/report.json",
            "heterogeneous_youngs_modulus.png": self.revision / "physical/example_target_E.png",
            "heterogeneous_density.png": self.revision / "physical/example_target_density.png",
            "heterogeneous_part_ids.png": self.revision / "physical/example_target_part.png",
            "source_part_ids.png": self.revision / "physical/example_source_part.png",
        }
        for name, path in auxiliary.items():
            self.write_bytes(path, name.encode())
            self.manifest["auxiliary_source_artifacts"][name] = self.record(path)
        self.paths.update(cleaned_image_path=str(auxiliary["cleaned_image.png"]),
                          cleanup_report_path=str(auxiliary["image_cleanup.json"]))
        recommendation = {"recommendation": "accept", "ready": True, "route": "accept", "reason": "Observed evidence"}
        self.state = {
            "schema_version": "2026-07-skill-suite-runtime-state-v2",
            "run_root": str(self.run), "runtime_kind": "codex_skill", "run_mode": "full_image",
            "status": "running", "output_tag": "example", "paths": self.paths,
            "planned_global_stage_sequence": list(MODULE.STAGES), "completed_global_stage_sequence": list(MODULE.STAGES),
            "stages": {name: {"ok": True, "status": "success", "error": ""} for name in MODULE.STAGES},
            "stage_runtime": {"final_export": {"terminal": {"tool_name": "submit_final_export_stage",
                                                            "status": "pending_validation", "error": ""}}},
            "active_revision": "revision_0000", "accepted_revision": "revision_0000", "exported_revision": "revision_0000",
            "revisions": {"revision_0000": {"status": "accepted", "revision_root": str(self.revision)}},
            "final_export": {"dir": str(self.export)},
            "diagnostics": {"enabled": True, "terminal": {
                "status": "success", "validated": True, "recommendation": recommendation,
                "business_outcome": {"status": "recommendation_valid", "recommendation": copy.deepcopy(recommendation)},
                "operational_outcome": {"status": "complete", "cleanup_status": "complete", "retryable": False,
                                        "error": "", "failure_kind": "", "artifact_status": {
                                            "media": {"status": "complete"}, "reports": {"status": "complete"}}}}},
            "route_state": {"orchestrator_diagnostic_decision": {
                "status": "success", "diagnostic_verdict": "accept", "child_recommendation": "accept",
                "source_revision": "revision_0000", "transition_action": "post_mesh_texture",
                "diagnostic_verdict_reason": "Reviewed strict accept", "failure_kind": "", "halt_reason": ""}},
            "history": [],
        }
        self.save()

    def write_bytes(self, path, contents):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)

    def record(self, path):
        return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": MODULE.sha256(path)}

    def save(self):
        self.state_path.write_text(json.dumps(self.state))
        self.manifest_path.write_text(json.dumps(self.manifest))

    def validate(self):
        return MODULE.validate_completed_export(self.run, diaggen_root=self.root)

    def test_complete_fixture_is_read_only_and_runs_native_checks(self):
        before = self.state_path.read_bytes()
        report = self.validate()
        self.assertTrue(report["valid"])
        self.assertEqual(report["artifact_count"], 16)
        self.assertEqual(self.state_path.read_bytes(), before)
        self.native.assert_called_once_with(self.root, self.export)

    def test_complete_reroute_and_export_snapshot_is_eligible(self):
        self.state.update(run_mode="post_mesh_processing_diagnostics",
                          diagnostics_reroute_and_export=True, diagnostics_stage_only=False)
        self.save()
        self.assertTrue(self.validate()["valid"])

    def make_native_final_revise_export(self):
        sys.path.insert(0, str(WORKSPACE / "tools/diaggen"))
        from hag4r.agentic import runtime_state
        old_revision = self.revision
        self.revision = self.run / "revisions/revision_0001"
        old_revision.rename(self.revision)
        self.state = json.loads(json.dumps(self.state).replace(str(old_revision), str(self.revision)))
        self.manifest = json.loads(json.dumps(self.manifest).replace(str(old_revision), str(self.revision)))
        self.state.update(run_mode="post_mesh_processing_diagnostics", diagnostics_reroute_and_export=True,
                          diagnostics_stage_only=False, active_revision="revision_0001", accepted_revision=None,
                          exported_revision="revision_0001", status="success")
        self.state["revisions"] = {"revision_0000": {"status": "superseded"},
                                   "revision_0001": {"status": "exported_unaccepted", "revision_root": str(self.revision)}}
        recommendation = {"schema_version": "hag4r-genesis-vlm-recommendation-v3", "recommendation": "revise",
                          "route": "segmentation", "diagnostic_cues": ["The strap remains merged with the upper."]}
        diagnostic = self.state["diagnostics"]["terminal"]
        diagnostic.update(tool_name="submit_diagnostic_recommendation", recommendation=recommendation,
                          route="segmentation", ready=False)
        diagnostic["business_outcome"]["recommendation"] = copy.deepcopy(recommendation)
        diagnostic["operational_outcome"]["artifact_status"]["media"]["status"] = "not_required"
        self.state["diagnostics"].update(max_runs=2, episodes=[])
        decision = {"status": "success", "diagnostic_verdict": "revise", "child_recommendation": "revise",
                    "transition_action": "post_mesh_texture", "diagnostic_export_policy": runtime_state.DIAGNOSTIC_EXPORT_POLICY,
                    "recommendation_route": "segmentation", "resulting_run_status": "running", "source_revision": "revision_0001",
                    "diagnostic_cues": recommendation["diagnostic_cues"], "diagnostic_repair_brief": {}, "diagnostic_revision_count": 1,
                    "selected_reentry_stage_skill_paths": [runtime_state.STAGE_SKILL_PATHS["post_mesh_texture"], runtime_state.STAGE_SKILL_PATHS["final_export"]]}
        self.state["route_state"] = {"orchestrator_diagnostic_decision": decision, "diagnostic_revision_count": 1,
                                     "force_rerun_stage_skill_paths": [], "first_rerouted_stage_skill_path": "", "diagnostic_repair_brief": {}}
        self.manifest.update(accepted_revision=None, export_revision="revision_0001")
        self.save()

    def test_actual_native_final_revise_export_preserves_unaccepted_outcome(self):
        self.make_native_final_revise_export()
        before = self.state_path.read_bytes()
        report = self.validate()
        self.assertTrue(report["valid"])
        self.assertFalse(report["strict_genesis_accept"])
        self.assertEqual(report["completion_kind"], "native_final_revise_export")
        self.assertIsNone(report["accepted_revision"])
        self.assertEqual(report["exported_revision"], "revision_0001")
        self.assertEqual(report["diagnostic_recommendation"], "revise")
        self.assertEqual(before, self.state_path.read_bytes())

    def test_already_exported_revise_settlement_does_not_promote_accept(self):
        self.make_native_final_revise_export()
        before = self.state_path.read_bytes()
        report = MODULE.settle_completed_export(self.run, diaggen_root=self.root)
        self.assertTrue(report["already_successful"])
        self.assertFalse(report["settled"])
        self.assertFalse(report["strict_genesis_accept"])
        self.assertEqual(before, self.state_path.read_bytes())

    def test_final_revise_policy_flag_alone_cannot_bypass_native_budget_or_cues(self):
        self.make_native_final_revise_export()
        original = copy.deepcopy(self.state)
        for mode in ("budget_not_exhausted", "missing_cues", "wrong_parent_route", "missing_terminal_tool"):
            self.state = copy.deepcopy(original)
            if mode == "budget_not_exhausted":
                self.state["diagnostics"]["max_runs"] = 3
            elif mode == "missing_cues":
                self.state["diagnostics"]["terminal"]["recommendation"]["diagnostic_cues"] = []
            elif mode == "wrong_parent_route":
                self.state["route_state"]["orchestrator_diagnostic_decision"]["recommendation_route"] = "material_inference"
            else:
                del self.state["diagnostics"]["terminal"]["tool_name"]
            self.save()
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.validate()

    def test_final_revise_never_allows_full_image_or_stage_only_mode(self):
        self.make_native_final_revise_export()
        for mode, stage_only in (("full_image", False), ("post_mesh_processing_diagnostics", True)):
            self.state.update(run_mode=mode, diagnostics_stage_only=stage_only)
            self.save()
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.validate()

    def test_final_revise_requires_explicit_unaccepted_manifest_and_revision_status(self):
        self.make_native_final_revise_export()
        del self.manifest["accepted_revision"]
        self.save()
        with self.assertRaisesRegex(ValueError, "Manifest revision"):
            self.validate()
        self.manifest["accepted_revision"] = None
        self.state["revisions"]["revision_0001"]["status"] = "accepted"
        self.save()
        with self.assertRaisesRegex(ValueError, "exported-unaccepted"):
            self.validate()

    def test_final_revise_does_not_excuse_missing_episode_media(self):
        self.make_native_final_revise_export()
        self.state["diagnostics"]["episodes"] = [{"episode_id": "episode_0001"}]
        self.save()
        with self.assertRaisesRegex(ValueError, "media completion"):
            self.validate()

    def test_stage_only_or_implicit_snapshot_mode_is_not_eligible(self):
        for reroute, stage_only in ((False, False), (True, True), (True, None), (None, False)):
            self.state.update(run_mode="post_mesh_processing_diagnostics",
                              diagnostics_reroute_and_export=reroute, diagnostics_stage_only=stage_only)
            self.save()
            with self.subTest(reroute=reroute, stage_only=stage_only), self.assertRaisesRegex(ValueError, "snapshot skill runs"):
                self.validate()

    def test_snapshot_still_requires_all_nine_completed_stages(self):
        self.state.update(run_mode="post_mesh_processing_diagnostics",
                          diagnostics_reroute_and_export=True, diagnostics_stage_only=False)
        self.state["completed_global_stage_sequence"] = list(MODULE.STAGES[6:])
        self.save()
        with self.assertRaisesRegex(ValueError, "incomplete or unordered"):
            self.validate()

    def test_missing_export_file_is_rejected(self):
        (self.export / "final_mesh.mesh").unlink()
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.validate()
        self.native.assert_not_called()

    def test_same_size_corruption_is_rejected_by_hash(self):
        path = self.export / "final_mesh.mesh"
        path.write_bytes(b"x" * path.stat().st_size)
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.validate()

    def test_missing_stage_is_rejected(self):
        del self.state["stages"][MODULE.STAGES[2]]
        self.save()
        with self.assertRaisesRegex(ValueError, "Required native stage"):
            self.validate()

    def test_completed_sequence_must_be_complete_and_ordered(self):
        self.state["completed_global_stage_sequence"].reverse()
        self.save()
        with self.assertRaisesRegex(ValueError, "incomplete or unordered"):
            self.validate()

    def test_revisions_must_match(self):
        self.state["exported_revision"] = "revision_0001"
        self.save()
        with self.assertRaisesRegex(ValueError, "revisions differ"):
            self.validate()

    def test_manifest_revision_must_match(self):
        self.manifest["accepted_revision"] = "revision_0001"
        self.save()
        with self.assertRaisesRegex(ValueError, "Manifest revision"):
            self.validate()

    def test_diagnostic_revise_cannot_be_promoted(self):
        self.state["diagnostics"]["terminal"]["recommendation"]["recommendation"] = "revise"
        self.save()
        with self.assertRaisesRegex(ValueError, "strict accept"):
            self.validate()

    def test_diagnostic_business_record_must_match(self):
        self.state["diagnostics"]["terminal"]["business_outcome"]["recommendation"]["reason"] = "Other record"
        self.save()
        with self.assertRaisesRegex(ValueError, "business recommendation mismatch"):
            self.validate()

    def test_retryable_cleanup_is_rejected(self):
        self.state["diagnostics"]["terminal"]["operational_outcome"]["cleanup_status"] = "cleanup_retryable"
        self.save()
        with self.assertRaisesRegex(ValueError, "operational completion"):
            self.validate()

    def test_parent_accept_is_required(self):
        self.state["route_state"]["orchestrator_diagnostic_decision"]["diagnostic_verdict"] = "revise"
        self.save()
        with self.assertRaisesRegex(ValueError, "Parent diagnostic accept"):
            self.validate()

    def test_extra_export_file_is_rejected(self):
        (self.export / "stale.txt").write_text("unrelated")
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.validate()

    def test_omitted_cleanup_provenance_is_rejected(self):
        del self.manifest["auxiliary_source_artifacts"]["cleaned_image.png"]
        self.save()
        with self.assertRaisesRegex(ValueError, "provenance records are incomplete"):
            self.validate()

    def test_updated_export_record_cannot_hide_source_mismatch(self):
        path = self.export / "final_mesh.mesh"
        path.write_text("changed")
        self.manifest["exported_artifacts"]["final_mesh.mesh"] = self.record(path)
        self.save()
        with self.assertRaisesRegex(ValueError, "differs from source"):
            self.validate()

    def test_symlink_export_is_rejected(self):
        path = self.export / "final_mesh.mesh"
        path.unlink()
        path.symlink_to(self.paths["monolithic_mesh_path"])
        with self.assertRaisesRegex(ValueError, "symlinks"):
            self.validate()

    def test_native_validation_failure_cannot_be_settled(self):
        self.native.side_effect = ValueError("Native GLB binding invalid")
        before = self.state_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Native GLB"):
            MODULE.settle_completed_export(self.run, diaggen_root=self.root)
        self.assertEqual(before, self.state_path.read_bytes())

    def test_opt_in_settlement_preserves_terminals_and_is_idempotent(self):
        native_state = types.ModuleType("hag4r.agentic.runtime_state")
        native_state.load_state = mock.Mock(side_effect=lambda run: MODULE.read_object(self.state_path))

        def update(run, **patch):
            state = MODULE.read_object(self.state_path)
            state.update(patch)
            self.state_path.write_text(json.dumps(state))

        def history(run, agent, note, **kwargs):
            state = MODULE.read_object(self.state_path)
            state["history"].append({"agent": agent, "note": note, **kwargs})
            self.state_path.write_text(json.dumps(state))

        native_state.update_state = mock.Mock(side_effect=update)
        native_state.append_history = mock.Mock(side_effect=history)
        before_terminal = copy.deepcopy(self.state["stage_runtime"])
        with mock.patch.dict(sys.modules, {"hag4r.agentic.runtime_state": native_state}):
            first = MODULE.settle_completed_export(self.run, diaggen_root=self.root)
            self.assertTrue(first["settled"])
            state = MODULE.read_object(self.state_path)
            self.assertEqual(state["status"], "success")
            self.assertTrue(state["completion_validation"]["valid"])
            self.assertEqual(state["stage_runtime"], before_terminal)
            before = self.state_path.read_bytes()
            second = MODULE.settle_completed_export(self.run, diaggen_root=self.root)
            self.assertTrue(second["already_successful"])
            self.assertFalse(second["settled"])
            self.assertEqual(before, self.state_path.read_bytes())
            native_state.update_state.assert_called_once()
            native_state.append_history.assert_called_once()


if __name__ == "__main__":
    unittest.main()
