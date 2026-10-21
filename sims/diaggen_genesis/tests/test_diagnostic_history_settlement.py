"""CPU regressions for the verified native historical-settlement patch.

The patch is applied only to a temporary module. No run ledger, MCP process,
GPU, or active native source is modified. Run with the hag4r Python environment.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

WORKSPACE = Path(__file__).resolve().parents[3]
NATIVE = WORKSPACE / "tools" / "diaggen"
SUPPORT = WORKSPACE / "tools" / "diaggen_support"
sys.path.insert(0, str(NATIVE))


def load_verified_module(*, baseline=False):
    manifest = json.loads((SUPPORT / "diagnostic_history_settlement.json").read_text())
    source = (NATIVE / manifest["target"]).read_bytes()
    patch = (SUPPORT / "diagnostic_history_settlement.patch").read_bytes()
    if hashlib.sha256(patch).hexdigest() != manifest["patch_sha256"]:
        raise AssertionError("verified patch digest changed")
    digest = hashlib.sha256(source).hexdigest()
    expected = manifest["before_sha256"] if baseline else manifest["after_sha256"]
    if digest not in {manifest["before_sha256"], manifest["after_sha256"]}:
        raise AssertionError("native source does not match either verified digest")
    if digest != expected:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / manifest["target"]
            target.parent.mkdir(parents=True)
            target.write_bytes(source)
            command = ["patch", "--batch", "--fuzz=0", "-p1"]
            if baseline:
                command.append("--reverse")
            subprocess.run(command, input=patch,
                           cwd=folder, check=True, capture_output=True)
            candidate = target.read_bytes()
    else:
        candidate = source
    if hashlib.sha256(candidate).hexdigest() != expected:
        raise AssertionError("patched source digest mismatch")
    name = "hag4r.agentic.runtime_tools._diagnostic_history_" + ("baseline" if baseline else "regression")
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(candidate, str(NATIVE / manifest["target"]), "exec"), module.__dict__)
    return module


def closed_episode(module):
    """Small complete independent-part probe, closed under its original owner."""
    region = {
        "region_id": "strap", "risk_rank": 1, "name": "Flexible strap",
        "semantic_region": "flexible fastening strap",
        "selection_rationale": "The strap is a distinct functional region.",
        "physical_hypothesis": "The strap can bend under a bounded probe.",
        "desired_interaction": "Lift the strap with a bounded probe.",
        "episode_intent": "Check a distinct anchored strap.",
        "termination_condition": "Close after a complete probe and release.",
        "setup_anchor": {
            "anchor_region": "base", "anchor_type": "support_contact",
            "relationship_to_probe": "distinct",
            "relationship_rationale": "The base supports a separate strap.",
            "uncertainty": "low", "concerns": [],
        },
    }
    second_region = copy.deepcopy(region)
    second_region.update(region_id="base", risk_rank=2, name="Supporting base")
    plan = module.validate_diagnostic_session_plan({
        "schema_version": "hag4r-genesis-diagnostic-session-plan-v2",
        "session_intent": "Check one independent anchored region.",
        "candidate_region_count": 2, "regions": [region, second_region],
        "omitted_region_summary": [], "paired_comparisons": [],
    })
    owner = {"attachment_id": "owner_original", "agent_invocation_id": "child_original",
             "episode_id": "episode_0001", "region_id": "strap",
             "active_revision_id": "revision_0000"}
    session = {
        **owner, "live_session_handle": "session_original", "lifecycle_state": "closed",
        "bound_at": "2026-10-21T10:00:00+00:00",
        "closed_at": "2026-10-21T10:01:00+00:00",
    }
    state = {
        "active_revision": "revision_0000",
        "diagnostic_runtime_attachments": [{
            "attachment_id": owner["attachment_id"], "agent_invocation_id": owner["agent_invocation_id"],
            "status": "attached",
        }],
        "diagnostic_runtime_sessions": [session],
        "diagnostics": {
            "active_diagnostic_session_plan": plan,
            "diagnostic_session_plans": [copy.deepcopy(plan)],
            "session_plan_version": plan["schema_version"],
            "diagnostic_region_ledger": [{
                "region_id": "strap", "risk_rank": 1, "region": copy.deepcopy(plan["regions"][0]),
                "episode_id": "episode_0001", "qualifying_attempt_id": "attempt_0001",
                "status": "episode_defined",
            }, {"region_id": "base", "risk_rank": 2,
                "region": copy.deepcopy(plan["regions"][1]), "status": "planned"}],
            "episodes": [{"episode_id": "episode_0001"}],
            "setup_trials": [{
                **owner, "anchor_id": "strap", "trial_id": "setup_0001",
                "anchor_compile_id": "anchor_0001", "final_status": "used_for_episode",
                "reflection": {"anchor_semantic_match": "matched",
                               "tested_dof_preservation": "preserved",
                               "owner_snapshot": {**owner, "trial_id": "setup_0001"},
                               "setup_concern_dispositions": []},
            }],
            "compiled_anchor_targets": [{
                "compile_id": "anchor_0001", "anchor_id": "strap",
                "selected_part_id": 0, "active_revision_id": "revision_0000",
                "genesis_aabb_box": [0., 0., 0., 1., 1., 1.],
            }],
            "compiled_probe_targets": [{
                "compile_id": "probe_0001", "region_id": "strap",
                "selected_part_id": 1, "active_revision_id": "revision_0000",
                "simulate_episode_id": "episode_0001",
                "genesis_aabb_box": [2., 0., 0., 3., 1., 1.],
            }],
            "probe_target_reflections": [{
                **owner, "compile_id": "probe_0001", "semantic_match": "matched",
                "owner_snapshot": owner.copy(),
            }],
            "anchor_probe_separation_results": [{
                **owner, "separation_id": "separation_0001",
                "anchor_compile_id": "anchor_0001", "probe_compile_id": "probe_0001",
                "anchor_part_id": 0, "probe_part_id": 1,
                "anchor_aabb": [0., 0., 0., 1., 1., 1.],
                "probe_aabb": [2., 0., 0., 3., 1., 1.],
                "positive_intersection_volume": 0., "relationship_to_probe": "distinct",
                "derived_basis_status": "different_grounded_parts",
                "validation_outcome": "validated_distinct",
                "owner_snapshot": {**owner, "anchor_compile_id": "anchor_0001",
                                   "probe_compile_id": "probe_0001"},
            }],
            "diagnostic_probe_attempts": [{
                **owner, "attempt_id": "attempt_0001", "compile_id": "probe_0001",
                "qualifying": True, "dispatch_status": "completed",
                "tool_result_index": 0, "application_index": 0, "result_status": "ok",
                "registered_action_id": "action_0001", "grabbed_selected_part_fraction": .8,
            }],
            "tool_results": [{
                "tool_result_index": 0, "tool": "simulate", "episode_id": "episode_0001",
                "result": {"status": "ok", "result": {"steps_completed": 100}},
            }],
            "probe_target_applications": [{
                "region_id": "strap", "episode_id": "episode_0001",
                "active_revision_id": "revision_0000", "attempt_id": "attempt_0001",
                "compile_id": "probe_0001", "registered_action_id": "action_0001",
                "requested_duration_steps": 100, "result_status": "ok",
                "probe_target_validation": {"status": "ok", "compile_id": "probe_0001",
                                            "tool_result_index": 0,
                                            "grabbed_selected_part_fraction": .8},
            }],
            "probe_measurements": [{"region_id": "strap", "episode_id": "episode_0001",
                                    "compile_id": "probe_0001"}],
        },
    }
    result = module.settle_region_on_live_close(state, **close_arguments())
    if result["status"] != "coverage_complete":
        raise AssertionError("fixture must have full real verifier coverage")
    return state


def close_arguments():
    return {"attachment_id": "owner_original", "live_session_handle": "session_original",
            "episode_id": "episode_0001", "close_outcome": "clean_closed"}


class HistoricalSettlementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_verified_module()
        cls.baseline = load_verified_module(baseline=True)

    def setUp(self):
        self.state = closed_episode(self.module)

    def history(self, status="superseded"):
        self.state["diagnostic_runtime_attachments"][0]["status"] = status
        self.state["diagnostic_runtime_attachments"].append({
            "attachment_id": "owner_successor", "agent_invocation_id": "child_successor",
            "status": "attached",
        })
        return self.state

    def summary(self):
        return self.module.build_diagnostic_coverage_summary(self.state)

    def test_original_current_owner_remains_valid(self):
        self.assertEqual(self.summary()["regions"][0]["status"], "coverage_complete")

    def test_unpatched_negative_control_reproduces_the_production_error(self):
        state = closed_episode(self.baseline)
        state["diagnostic_runtime_attachments"][0]["status"] = "superseded"
        with self.assertRaisesRegex(self.baseline.GenesisVlmSchemaError, "crosses attachment ownership"):
            self.baseline.build_diagnostic_coverage_summary(state)

    def test_expired_and_superseded_history_keeps_complete_coverage(self):
        for status in ["expired", "superseded"]:
            with self.subTest(status=status):
                self.state = closed_episode(self.module)
                self.history(status)
                self.assertEqual(self.summary()["regions"][0]["status"], "coverage_complete")

    def test_old_owner_cannot_create_or_repeat_a_new_close(self):
        self.history()
        with self.assertRaises(self.module.GenesisVlmSchemaError):
            self.module.settle_region_on_live_close(self.state, **close_arguments())
        self.state["diagnostics"]["region_settlements"].clear()
        with self.assertRaises(self.module.GenesisVlmSchemaError):
            self.module.settle_region_on_live_close(self.state, **close_arguments())

    def test_successor_cannot_close_old_session(self):
        self.history()
        arguments = {**close_arguments(), "attachment_id": "owner_successor"}
        with self.assertRaises(self.module.GenesisVlmSchemaError):
            self.module.settle_region_on_live_close(self.state, **arguments)

    def test_reopened_or_rebound_session_is_rejected(self):
        for status in ["bound", "created", "failed_closing"]:
            with self.subTest(status=status):
                self.state = closed_episode(self.module)
                self.history()
                self.state["diagnostic_runtime_sessions"][0]["lifecycle_state"] = status
                with self.assertRaises(self.module.GenesisVlmSchemaError):
                    self.summary()

    def test_wrong_immutable_session_fields_are_rejected(self):
        for field in ["attachment_id", "agent_invocation_id", "episode_id", "live_session_handle",
                      "active_revision_id", "closed_at", "bound_at"]:
            with self.subTest(field=field):
                self.state = closed_episode(self.module)
                self.history()
                self.state["diagnostic_runtime_sessions"][0][field] = "wrong"
                with self.assertRaises(self.module.GenesisVlmSchemaError):
                    self.summary()

    def test_wrong_settlement_identity_or_snapshot_is_rejected(self):
        for field in ["attachment_id", "episode_id", "live_session_handle", "active_revision_id",
                      "region_id", "close_outcome"]:
            with self.subTest(field=field):
                self.state = closed_episode(self.module)
                self.history()
                self.state["diagnostics"]["region_settlements"][0][field] = "wrong"
                with self.assertRaises(self.module.GenesisVlmSchemaError):
                    self.summary()

    def test_failed_unknown_owner_is_not_historical_permission(self):
        for status in ["failed", "unknown", None]:
            with self.subTest(status=status):
                self.state = closed_episode(self.module)
                self.history(status)
                with self.assertRaises(self.module.GenesisVlmSchemaError):
                    self.summary()

    def test_forged_copy_is_not_an_existing_durable_settlement(self):
        self.history()
        row = copy.deepcopy(self.state["diagnostics"]["region_settlements"][0])
        with self.assertRaises(self.module.GenesisVlmSchemaError):
            self.module._derive_region_close_settlement(
                self.state, **close_arguments(), historical_settlement=row)

    def test_duplicate_settlement_id_is_rejected(self):
        self.history()
        rows = self.state["diagnostics"]["region_settlements"]
        rows.append(copy.deepcopy(rows[0]))
        with self.assertRaises(self.module.GenesisVlmSchemaError):
            self.summary()

    def test_frozen_ownership_snapshot_drift_is_rejected(self):
        for field in ["attachment_id", "agent_invocation_id", "episode_id", "live_session_handle",
                      "closed_at", "bound_at", "lifecycle_state"]:
            with self.subTest(field=field):
                self.state = closed_episode(self.module)
                self.history()
                snapshot = self.state["diagnostics"]["region_settlements"][0]["evidence_lineage"]["ownership"]
                snapshot[field] = "wrong"
                with self.assertRaises(self.module.GenesisVlmSchemaError):
                    self.summary()

    def test_wrong_original_owner_invocation_is_rejected(self):
        self.history()
        self.state["diagnostic_runtime_attachments"][0]["agent_invocation_id"] = "wrong"
        with self.assertRaises(self.module.GenesisVlmSchemaError):
            self.summary()

    def test_existing_probe_evidence_checks_remain_strict(self):
        self.history()
        self.state["diagnostics"]["diagnostic_probe_attempts"][0]["grabbed_selected_part_fraction"] = .49
        with self.assertRaises(self.module.GenesisVlmSchemaError):
            self.summary()


if __name__ == "__main__":
    unittest.main()
