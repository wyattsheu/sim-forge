"""Actual native revision recovery on temporary ledgers, with refusal controls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/diaggen"))
from hag4r.agentic import runtime_state

SPEC = importlib.util.spec_from_file_location("prepare_repair_stage_runtime", ROOT / "tools/diaggen_support/prepare_repair_stage_runtime.py")
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


class RepairStageRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "outputs/agentic_asset_refinement/example"
        self.old = self.run / "revisions/revision_0000/state.json"
        self.current = self.run / "state.json"
        self.state = {
            "schema_version": runtime_state.RUNTIME_STATE_SCHEMA_VERSION,
            "run_root": str(self.run), "repo_root": str(self.root), "run_mode": "full_image",
            "status": "running", "active_revision": "revision_0001", "accepted_revision": None,
            "exported_revision": None, "completed_global_stage_sequence": ["image_cleanup", "sam3_omnipart_2d_segmentation", "omnipart_generate_parts"],
            "stages": {"image_cleanup": {"ok": True, "status": "reused"}},
            "route_state": {"active_repair_revision": {"route": "segmentation", "new_revision": "revision_0001", "base_revision": "revision_0000"}},
            "revisions": {"revision_0000": {"status": "superseded", "superseded_by": "revision_0001", "revision_root": str(self.old.parent)},
                          "revision_0001": {"status": "active", "base_revision": "revision_0000", "rerun_route": "segmentation",
                                            "created_at": "2026-10-22T09:30:00+00:00", "revision_root": str(self.run / "revisions/revision_0001")}},
            "stage_runtime": {}, "history": [], "diagnostics": {"enabled": True},
            "diagnostic_runtime_attachments": [], "diagnostic_runtime_sessions": [],
        }
        for key in ("image_cleanup", *TOOL.RERUN_KEYS["segmentation"]):
            self.state["stage_runtime"][key] = {"terminal": {"status": "pending_validation", "timestamp": "2026-10-22T09:00:00+00:00", "stage_key": key},
                                                 "diagnostic_response_summary": "Original record", "other_provenance": "preserve"}
        self.base = deepcopy(self.state)
        self.base["active_revision"] = "revision_0000"
        self.save()

    def save(self):
        self.old.parent.mkdir(parents=True, exist_ok=True)
        self.old.write_text(json.dumps(self.base))
        self.current.write_text(json.dumps(self.state))

    def prepare(self, apply=False):
        return TOOL.prepare(self.run, apply=apply, diaggen_root=self.root)

    def assert_refused_unchanged(self, message):
        before = self.current.read_bytes(), self.old.read_bytes()
        with self.assertRaisesRegex(ValueError, message):
            self.prepare(apply=True)
        self.assertEqual(before, (self.current.read_bytes(), self.old.read_bytes()))

    def test_read_only_inspection_proves_inherited_records_without_mutation(self):
        before = self.current.read_bytes()
        report = self.prepare()
        self.assertEqual(report["inherited_terminal_keys"], list(TOOL.RERUN_KEYS["segmentation"]))
        self.assertFalse(report["applied"])
        self.assertEqual(before, self.current.read_bytes())

    def test_actual_native_reset_preserves_prefix_base_and_generated_stage_records(self):
        old = self.old.read_bytes()
        report = self.prepare(apply=True)
        self.assertTrue(report["applied"])
        state = json.loads(self.current.read_text())
        self.assertEqual(state["completed_global_stage_sequence"], self.state["completed_global_stage_sequence"])
        self.assertEqual(state["stages"], self.state["stages"])
        self.assertEqual(state["stage_runtime"]["image_cleanup"], self.state["stage_runtime"]["image_cleanup"])
        for key in TOOL.RERUN_KEYS["segmentation"]:
            self.assertEqual(state["stage_runtime"][key], {"other_provenance": "preserve"})
        self.assertEqual(old, self.old.read_bytes())
        self.assertEqual(state["history"][-1]["event"], "repair_stage_runtime_terminals_reset")

    def test_already_prepared_revision_is_read_only_noop(self):
        self.prepare(apply=True)
        before = self.current.read_bytes()
        self.assertFalse(self.prepare(apply=True)["applied"])
        self.assertEqual(before, self.current.read_bytes())

    def test_new_revision_terminal_is_never_removed(self):
        self.state["stage_runtime"]["omnipart"]["terminal"]["summary"] = "Newly authored result"
        self.save()
        self.assert_refused_unchanged("current or unproven terminal")

    def test_halted_terminal_is_never_removed_even_if_present_in_base(self):
        for d in (self.state, self.base):
            d["stage_runtime"]["segmentation"]["terminal"]["status"] = "halted"
        self.save()
        self.assert_refused_unchanged("halted or newly authored")

    def test_late_timestamp_is_rejected_even_if_base_payload_matches(self):
        for d in (self.state, self.base):
            d["stage_runtime"]["segmentation"]["terminal"]["timestamp"] = "2026-10-22T09:31:00+00:00"
        self.save()
        self.assert_refused_unchanged("halted or newly authored")

    def test_accepted_exported_and_completed_states_are_rejected(self):
        for field, value in (("accepted_revision", "revision_0001"), ("exported_revision", "revision_0001"), ("status", "success")):
            original = self.state.get(field)
            self.state[field] = value
            self.save()
            with self.subTest(field=field):
                self.assert_refused_unchanged("eligible|unfinished|Accepted or exported")
            self.state[field] = original

    def test_live_diagnostic_owner_blocks_bookkeeping(self):
        self.state["diagnostic_runtime_attachments"] = [{"status": "attached"}]
        self.save()
        self.assert_refused_unchanged("ownership is active")

    def test_revision_mismatch_is_rejected(self):
        self.state["route_state"]["active_repair_revision"]["new_revision"] = "revision_0002"
        self.save()
        self.assert_refused_unchanged("Current active repair")

    def test_foreign_base_snapshot_is_rejected(self):
        self.base["run_root"] = str(self.root / "another_run")
        self.save()
        self.assert_refused_unchanged("different run or revision")

    def test_material_route_retains_segmentation_and_omnipart_terminals(self):
        self.state["route_state"]["active_repair_revision"]["route"] = "material_inference"
        self.state["revisions"]["revision_0001"]["rerun_route"] = "material_inference"
        self.save()
        self.prepare(apply=True)
        state = json.loads(self.current.read_text())
        for key in ("image_cleanup", "segmentation", "omnipart"):
            self.assertEqual(state["stage_runtime"][key], self.state["stage_runtime"][key])


if __name__ == "__main__":
    unittest.main()
