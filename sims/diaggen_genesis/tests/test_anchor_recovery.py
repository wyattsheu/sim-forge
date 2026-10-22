"""CPU proof of the native anchor edit/reset failure and verified skill repair.

No production state or source is changed. The actual native compile/revise
function bodies run against an in-memory ledger and a tiny tetrahedral mesh.
"""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

WORKSPACE = Path(__file__).resolve().parents[3]
NATIVE = WORKSPACE / "tools/diaggen"
SUPPORT = WORKSPACE / "tools/diaggen_support"
sys.path.insert(0, str(NATIVE))
import numpy as np
from hag4r.tools import probe_targeting as targeting

spec = importlib.util.spec_from_file_location("anchor_audit", SUPPORT / "audit_anchor_recovery.py")
AUDIT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AUDIT)


def verified_skill(name):
    manifest = json.loads((SUPPORT / (name + ".json")).read_text())
    source = (NATIVE / manifest["target"]).read_bytes()
    delta = (SUPPORT / (name + ".patch")).read_bytes()
    digest = lambda value: hashlib.sha256(value).hexdigest()
    assert digest(delta) == manifest["patch_sha256"]
    assert digest(source) in {manifest["before_sha256"], manifest["after_sha256"]}
    with tempfile.TemporaryDirectory() as folder:
        candidate = Path(folder) / manifest["target"]
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(source)
        if digest(source) == manifest["before_sha256"]:
            command = ["patch", "--batch", "--fuzz=0", "-p1"]
            subprocess.run(command + ["--dry-run"], input=delta, cwd=folder,
                           capture_output=True, check=True)
            subprocess.run(command, input=delta, cwd=folder, capture_output=True, check=True)
        result = candidate.read_bytes()
    assert digest(result) == manifest["after_sha256"]
    return result.decode()


class AnchorRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.context = {"parts_by_id": {"0": 0},
                        "parts": [{"part_name": "support", "part_semantics": "supporting body"}]}
        vertices = np.array([[0., 0., 0.], [.1, 0., 0.], [0., .1, 0.],
                             [0., 0., .1], [.1, .1, .1]])
        primitives = np.array([[0, 1, 2, 3], [1, 2, 3, 4]])
        self.inputs = {"mesh": SimpleNamespace(vertices=vertices, primitives=primitives),
                       "primitive_labels": np.zeros(2, dtype=int),
                       "primitive_centroids": vertices[primitives].mean(axis=1)}
        self.state = {"active_revision": "revision_0000", "diagnostics": {
            "compiled_anchor_targets": [], "anchor_target_edit_trials": [],
            "active_compiled_anchor_target_by_anchor": {}}}
        intent = {"intent_id": "anchor_intent_01", "selected_part_id": 0,
                  "region_hint": "full_part", "anchor_intent": "supporting body",
                  "physical_boundary_condition": "support body"}
        # Extract the actual production bodies; do not rewrite their logic or
        # import credential/session wrappers for this CPU-only bookkeeping test.
        source = NATIVE / "hag4r/agentic/runtime_tools/diagnostics.py"
        names = {"compile_diagnostic_anchor_target", "revise_diagnostic_anchor_target"}
        nodes = [node for node in ast.parse(source.read_text()).body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual(len(nodes), 2)
        self.scope = {
            "re": re, "Any": object, "GenesisVlmSchemaError": ValueError,
            "_require_bound_diagnostic_run_root": lambda root: root,
            "_require_state": lambda root: self.state,
            "_diagnostics": lambda state: state["diagnostics"],
            "_planned_region": lambda *args: {},
            "_ensure_part_grounding_context": lambda state: self.context,
            "_anchor_target_intent_by_anchor": lambda *args: intent,
            "compile_anchor_target_from_context": targeting.compile_anchor_target_from_context,
            "validate_diagnostic_anchor_target_edit": targeting.validate_anchor_target_edit,
            "_compiled_anchor_target_summary": lambda item: copy.deepcopy(item),
            "_compiled_anchor_target_by_id": lambda diag, cid: next(
                item for item in diag["compiled_anchor_targets"] if item["compile_id"] == cid),
            "_validate_anchor_target_edit_evidence_refs": lambda *args, **kwargs: [],
            "_save_diagnostics": lambda *args, **kwargs: None,
            "_render_and_record_anchor_target_preview": lambda **kwargs: {
                "compile_id": kwargs["compile_id"], "preview_rendered": True},
        }
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), self.scope)
        self.input_patch = patch.object(targeting, "_load_compile_inputs", return_value=self.inputs)
        self.input_patch.start()
        self.addCleanup(self.input_patch.stop)
        self.edit = {"schema_version": targeting.ANCHOR_TARGET_EDIT_SCHEMA_VERSION,
                     "face_adjust_percent": {"x_min": -25}, "translation_fraction": {},
                     "reason": "Tighten the supporting region using the current preview.",
                     "evidence_refs": ["triple_view:current"], "view_basis": ["top"],
                     "observed_mismatch": "too_large"}

    def compile(self):
        return self.scope["compile_diagnostic_anchor_target"]("cpu_only", "anchor")

    def revise(self, cid, edit=None):
        return self.scope["revise_diagnostic_anchor_target"]("cpu_only", cid, edit or self.edit)

    def test_old_recompile_sequence_discards_real_native_edit(self):
        original = self.compile()
        edited = self.revise(original["compile_id"])
        revised_record = self.state["diagnostics"]["compiled_anchor_targets"][-1]
        self.assertNotEqual(revised_record["mesh_frame_box_m"], original["mesh_frame_box_m"])
        reset = self.compile()
        self.assertEqual(reset["mesh_frame_box_m"], original["mesh_frame_box_m"])
        self.assertNotEqual(reset["compile_id"], edited["compile_id"])
        self.assertEqual(AUDIT.analyze_anchor_history(self.state)["reset_count"], 1)

    def test_consume_returned_revision_keeps_edited_active_target(self):
        original = self.compile()
        edited = self.revise(original["compile_id"])
        current = self.state["diagnostics"]["compiled_anchor_targets"][-1]
        self.assertTrue(edited["preview_rendered"])
        self.assertEqual(edited["compile_id"], current["compile_id"])
        self.assertEqual(self.state["diagnostics"]["active_compiled_anchor_target_by_anchor"]["anchor"],
                         edited["compile_id"])
        self.assertNotEqual(current["mesh_frame_box_m"], original["mesh_frame_box_m"])
        self.assertEqual(AUDIT.analyze_anchor_history(self.state)["reset_count"], 0)

    def test_second_edit_is_original_base_relative_not_incremental(self):
        original = self.compile()
        edited = self.revise(original["compile_id"])
        previous = copy.deepcopy(self.state["diagnostics"]["compiled_anchor_targets"][-1])
        self.revise(edited["compile_id"])
        current = self.state["diagnostics"]["compiled_anchor_targets"][-1]
        self.assertEqual(current["mesh_frame_box_m"], previous["mesh_frame_box_m"])
        cumulative = targeting.apply_anchor_target_edit(previous["mesh_frame_box_m"], self.edit)
        self.assertNotEqual(current["mesh_frame_box_m"], cumulative)

    def test_verified_micro_skill_preserves_gates_and_names_correct_sequence(self):
        text = verified_skill("anchor_preview_recovery")
        self.assertNotIn("`revise_diagnostic_anchor_target` -> recompile", text)
        self.assertIn("Retain the returned `compile_id`", text)
        self.assertIn("Do not call `compile_diagnostic_anchor_target` again", text)
        self.assertIn("original heuristic `base_box_m`", text)
        self.assertIn("Use at most three setup trials per anchor.", text)
        self.assertIn("A mismatch may not define an episode.", text)

    def test_verified_index_agrees_with_micro_skill(self):
        text = verified_skill("anchor_preview_index")
        self.assertNotIn("revision -> recompile -> current preview", text)
        self.assertIn("retain its returned compile ID", text)
        self.assertIn("do not submit `matched`,", text)

    def test_audit_refuses_missing_compile_evidence(self):
        self.state["diagnostics"]["setup_trials"] = [
            {"trial_id": "bad", "anchor_compile_id": "absent"}]
        with self.assertRaisesRegex(ValueError, "missing compile"):
            AUDIT.analyze_anchor_history(self.state)


if __name__ == "__main__":
    unittest.main()
