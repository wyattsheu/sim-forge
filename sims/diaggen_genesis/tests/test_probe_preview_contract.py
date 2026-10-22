"""Execute native revision/preview/reflection bookkeeping without GPU or MCP."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping
import unittest

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "tools/diaggen"
SUPPORT = ROOT / "tools/diaggen_support"


class ProbePreviewContractTests(unittest.TestCase):
    def setUp(self):
        self.state = {"active_revision": "revision_0000", "diagnostics": {
            "active_episode_index": None, "compiled_probe_targets": [
                {"compile_id": "original", "target_id": "target", "region_id": "arm"}],
            "active_compiled_probe_target_id": "original", "probe_target_edit_trials": [],
            "probe_target_preview_artifacts": [], "probe_target_reflections": [],
            "region_current_probe_compile_ids": {"arm": "original"}}}
        self.diag = self.state["diagnostics"]
        self.scope = {
            "Any": Any, "Mapping": Mapping, "GenesisVlmSchemaError": ValueError,
            "_require_bound_diagnostic_run_root": lambda root: root,
            "_require_state": lambda root: self.state,
            "_diagnostics": lambda state: state["diagnostics"],
            "_ensure_part_grounding_context": lambda state: {},
            "_compiled_probe_target_by_id": lambda diag, cid: next(x for x in diag["compiled_probe_targets"] if x["compile_id"] == cid),
            "_probe_target_intent_by_id": lambda *args: {
                "selected_part_id": 1, "region_hint": "tip", "semantic_group_part_ids": [1],
                "semantic_group_part_grounding": []},
            "_verify_probe_semantic_group_lineage": lambda *args: None,
            "validate_diagnostic_probe_target_edit": lambda value: value,
            "_validate_probe_target_edit_evidence_refs": lambda *args, **kwargs: [],
            "compile_probe_target_from_context": lambda *args, **kwargs: {"bounded_edit": True},
            "_save_diagnostics": lambda *args, **kwargs: None,
            "_compiled_probe_target_summary": lambda value: value,
            "_planned_region": lambda *args: {"episode_id": "episode_0001"},
            "_require_nonempty_runtime_text": lambda value, label: value,
            "_resolve_v2_preview_refs": lambda *args, **kwargs: (
                [{"kind": "visual_evidence", "ref": kwargs["preview_id"]}], {}),
            "_probe_targets_dir": lambda *args: Path("/temporary/nonexistent"),
            "_compact_triple_view_record": lambda value: value,
            "_append_triple_view_evidence_once": lambda *args: None,
        }
        def render(context, compiled, **kwargs):
            trial = kwargs["trial_id"]
            return {"manifest_path": trial + ".json", "views": {"top": {"path": "top.png"}},
                    "triptych_png_path": trial + ".png", "triple_view_manifest_path": trial + "_views.json",
                    "triple_view_evidence_id": trial + "_evidence", "panel_order": ["top", "ne_3q", "sw_3q"],
                    "manifest": {}, "triple_view_manifest": {}}
        self.scope["render_probe_target_preview"] = render
        path = NATIVE / "hag4r/agentic/runtime_tools/diagnostics.py"
        names = {"revise_diagnostic_probe_target", "preview_diagnostic_probe_target",
                 "_render_and_record_probe_target_preview", "_probe_target_preview_summary",
                 "record_diagnostic_probe_target_reflection"}
        nodes = [node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual(len(nodes), len(names))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), self.scope)

    def revise(self):
        return self.scope["revise_diagnostic_probe_target"]("cpu_only", "original", {"reason": "bounded overlap correction"})

    def reflect(self, result):
        return self.scope["record_diagnostic_probe_target_reflection"](
            "cpu_only", "arm", result["compile_id"], "matched",
            [{"kind": "visual_evidence", "ref": result["triple_view_evidence_id"]}], "verified current preview")

    def test_native_revision_already_records_one_preview_and_returned_ref_can_be_consumed(self):
        result = self.revise()
        self.assertEqual(len(self.diag["probe_target_preview_artifacts"]), 1)
        self.assertEqual(result["compile_id"], self.diag["active_compiled_probe_target_id"])
        self.assertEqual(result["triple_view_evidence_id"], self.diag["probe_target_preview_artifacts"][0]["triple_view_evidence_id"])
        self.assertEqual(self.reflect(result)["status"], "success")

    def test_old_extra_preview_sequence_reproduces_exact_native_reflection_rejection(self):
        result = self.revise()
        self.scope["preview_diagnostic_probe_target"]("cpu_only", result["compile_id"])
        self.assertEqual(len(self.diag["probe_target_preview_artifacts"]), 2)
        with self.assertRaisesRegex(ValueError, "exactly one current probe preview"):
            self.reflect(result)

    def test_verified_skill_patch_matches_actual_native_revision_contract(self):
        record = json.loads((SUPPORT / "probe_preview_recovery.json").read_text())
        delta = (SUPPORT / "probe_preview_recovery.patch").read_bytes()
        source = (NATIVE / record["target"]).read_bytes()
        self.assertEqual(hashlib.sha256(delta).hexdigest(), record["patch_sha256"])
        self.assertEqual(hashlib.sha256(source).hexdigest(), record["after_sha256"])
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / record["target"]
            target.parent.mkdir(parents=True)
            target.write_bytes(source)
            subprocess.run(["patch", "--reverse", "--batch", "--fuzz=0", "-p1"], cwd=temporary,
                           input=delta, capture_output=True, check=True)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), record["before_sha256"])
        self.assertIn("records exactly one new preview", source.decode())


if __name__ == "__main__":
    unittest.main()
