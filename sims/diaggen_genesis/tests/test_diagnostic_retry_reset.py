"""CPU regressions for transport-recovery execution-attempt isolation.

Load verified before/after native sources into temporary modules. Production
ledgers are read only; no attachment, live session, GPU, or state write occurs.
"""
import ast
import copy
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

WORKSPACE = Path(__file__).resolve().parents[3]
NATIVE = WORKSPACE / "tools" / "diaggen"
SUPPORT = WORKSPACE / "tools" / "diaggen_support"
BASELINE_FIXTURES = NATIVE / "outputs" / "preflight" / "diagnostic_retry_reset_baseline_20261022"
sys.path.insert(0, str(NATIVE))


def load_verified_module(*, baseline=False):
    manifest = json.loads((SUPPORT / "diagnostic_retry_reset.json").read_text())
    series = json.loads((SUPPORT / "native_patches.json").read_text())
    names = series.get("patches", [])
    if "diagnostic_retry_reset" not in names:
        raise AssertionError("retry patch is missing from the verified series")
    reset_index = names.index("diagnostic_retry_reset")
    later = []
    for name in names[reset_index + 1:]:
        later_manifest = json.loads((SUPPORT / (name + ".json")).read_text())
        if later_manifest["target"] != manifest["target"]:
            continue
        later_patch = SUPPORT / (name + ".patch")
        if hashlib.sha256(later_patch.read_bytes()).hexdigest() != later_manifest["patch_sha256"]:
            raise AssertionError("later native patch digest changed: " + name)
        later.append((name, later_manifest, later_patch))

    source = (NATIVE / manifest["target"]).read_bytes()
    current_digest = hashlib.sha256(source).hexdigest()
    expected_tip = later[-1][1]["after_sha256"] if later else manifest["after_sha256"]
    patch = SUPPORT / "diagnostic_retry_reset.patch"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest["patch_sha256"]:
        raise AssertionError("retry patch digest changed")

    if current_digest not in {manifest["before_sha256"], manifest["after_sha256"], expected_tip}:
        raise AssertionError("native source is not a verified retry patch-chain endpoint")

    with tempfile.TemporaryDirectory(prefix="diaggen-retry-test-") as folder:
        target = Path(folder) / manifest["target"]
        target.parent.mkdir(parents=True)
        target.write_bytes(source)
        if current_digest == expected_tip:
            for name, later_manifest, later_patch in reversed(later):
                if hashlib.sha256(target.read_bytes()).hexdigest() != later_manifest["after_sha256"]:
                    raise AssertionError("later native patch chain is discontinuous: " + name)
                subprocess.run(
                    ["patch", "--batch", "--fuzz=0", "-p1", "--reverse", "--input", str(later_patch)],
                    cwd=folder, check=True, capture_output=True,
                )
                if hashlib.sha256(target.read_bytes()).hexdigest() != later_manifest["before_sha256"]:
                    raise AssertionError("later native patch reversal mismatch: " + name)
        elif current_digest == manifest["before_sha256"] and not baseline:
            subprocess.run(
                ["patch", "--batch", "--fuzz=0", "-p1", "--forward", "--input", str(patch)],
                cwd=folder, check=True, capture_output=True,
            )
        if baseline and hashlib.sha256(target.read_bytes()).hexdigest() == manifest["after_sha256"]:
            subprocess.run(
                ["patch", "--batch", "--fuzz=0", "-p1", "--reverse", "--input", str(patch)],
                cwd=folder, check=True, capture_output=True,
            )
        source = target.read_bytes()

    expected = manifest["before_sha256"] if baseline else manifest["after_sha256"]
    if hashlib.sha256(source).hexdigest() != expected:
        raise AssertionError("temporary module digest mismatch")
    name = "hag4r.agentic.runtime_tools._retry_reset_" + ("before" if baseline else "after")
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(source, str(NATIVE / manifest["target"]), "exec"), module.__dict__)
    module.verified_test_source = source
    return module


def sample_plan(module):
    regions = []
    for rank, label in enumerate(("flexible_strap", "supporting_body"), start=1):
        regions.append({
            "region_id": label, "risk_rank": rank, "name": label.replace("_", " "),
            "semantic_region": label.replace("_", " "),
            "physical_hypothesis": "Check bounded response of this independent region.",
            "desired_interaction": "Lift with a bounded probe.",
            "episode_intent": "Check one independently supported region.",
            "termination_condition": "Stop after a complete probe and release.",
            "selection_rationale": "A distinct functional region warrants a check.",
            "setup_anchor": {
                "anchor_type": "support_contact", "anchor_region": "distinct rear base",
                "uncertainty": "low", "relationship_to_probe": "distinct",
                "relationship_rationale": "Separate support and probed region.", "concerns": [],
            },
        })
    return module.validate_diagnostic_session_plan({
        "schema_version": "hag4r-genesis-diagnostic-session-plan-v2",
        "session_intent": "Independently check two risky regions.",
        "candidate_region_count": 2, "regions": regions,
        "omitted_region_summary": [], "paired_comparisons": [],
    })


def minimal_state(module):
    state = {"active_revision": "revision_0000", "diagnostics": {"enabled": True}}
    module._diagnostics(state)
    return state


def read_only_measurement_state(module):
    state = minimal_state(module)
    measurement = {"measurement_index": 0, "source": "compute_part_grounding_context",
                   "part_grounding_context": {"parts": []}}
    state["diagnostics"]["part_grounding_context_measurements"] = [measurement]
    state["diagnostics"]["runtime_owned_events"] = [{
        "event_id": 1, "event": "diagnostic_part_grounding_context_computed",
        "note": "computed runtime-owned diagnostic part grounding context",
        "provenance": "runtime_event",
        "detail": module._runtime_event_detail_preview({
            "part_grounding_context": module._part_grounding_measurement_preview(measurement),
        }),
    }]
    return state


def transport_failure_state(module):
    """Credential-free closed-owner fixture for stable security regressions."""
    state = minimal_state(module)
    plan = sample_plan(module)
    state["diagnostic_runtime_attachments"] = [{
        "attachment_id": "fixture_owner", "agent_invocation_id": "fixture_child",
        "status": "failed", "history": [{
            "event": "diagnostic_transport_recovery_ready",
            "failure_kind": "mcp_server_shutdown", "recovery_event_id": "fixture_recovery",
        }],
    }]
    state["diagnostic_runtime_sessions"] = [{
        "attachment_id": "fixture_owner", "agent_invocation_id": "fixture_child",
        "lifecycle_state": "closed", "live_session_handle": "fixture_session",
    }]
    state["diagnostics"].update({
        "active_diagnostic_session_plan": plan, "diagnostic_session_plans": [copy.deepcopy(plan)],
        "session_plan_version": plan["schema_version"],
        "diagnostic_region_ledger": [{"region_id": "flexible_strap", "episode_id": "old_episode"}],
        "region_episode_ids": {"flexible_strap": "old_episode"},
        "episodes": [{"episode_id": "old_episode"}],
        "part_grounding_context": {"parts": []},
        "part_grounding_context_measurements": [{
            "measurement_index": index, "source": "compute_part_grounding_context",
            "part_grounding_context": {"parts": []},
        } for index in range(3)],
        "terminal": {
            "validated": False,
            "business_outcome": {"status": "not_authored", "recommendation": None},
            "operational_outcome": {"status": "cleanup_retryable", "retryable": True,
                                    "failure_kind": "mcp_server_shutdown"},
        },
    })
    recovery = {"cause": "mcp_server_shutdown", "event_id": "fixture_recovery",
                "source_attachment_id": "fixture_owner", "source_agent_invocation_id": "fixture_child"}
    return state, recovery


class DiagnosticRetryResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_verified_module()
        cls.baseline = load_verified_module(baseline=True)
        # Static metadata validation only: this constructs no MCP runtime and
        # calls no lifecycle/authenticated diagnostic API.
        from hag4r.agentic.diagnostic_mcp_server import DiagnosticMcpRuntime
        cls.recovery_metadata = staticmethod(DiagnosticMcpRuntime._terminal_transport_recovery_metadata)

    def record_plan_in_memory(self, state, plan):
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(self.module, "_require_bound_diagnostic_run_root", return_value="fixture"))
            stack.enter_context(mock.patch.object(self.module, "_require_state", return_value=state))
            stack.enter_context(mock.patch.object(self.module, "_save_diagnostics"))
            return self.module.record_diagnostic_session_plan("fixture", plan)

    def production_state(self, run_id):
        label = {"genesis_sneaker_20261021": "sneaker", "genesis_sloth_20261021": "sloth"}[run_id]
        path = BASELINE_FIXTURES / (label + ".json")
        self.assertTrue(path.is_file(), "required local audit fixture is missing: " + str(path))
        manifest = json.loads((BASELINE_FIXTURES / "manifest.json").read_text())
        before = path.read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(), manifest["fixtures"][label]["sha256"],
                         "immutable production baseline digest changed")
        state = json.loads(before)
        attachment = state["diagnostic_runtime_attachments"][-1]
        recovery = self.recovery_metadata(state, attachment["attachment_id"])
        self.assertIsNotNone(recovery, "baseline lacks typed transport recovery provenance")
        self.addCleanup(lambda: self.assertEqual(path.read_bytes(), before,
                                                "CPU regression changed an immutable production baseline"))
        return state, recovery

    def test_actual_sneaker_and_sloth_before_after_reset(self):
        for run_id in ("genesis_sneaker_20261021", "genesis_sloth_20261021"):
            with self.subTest(run_id=run_id):
                original, recovery = self.production_state(run_id)
                self.assertGreater(len(original["diagnostics"]["part_grounding_context_measurements"]), 1)
                failed = copy.deepcopy(original)
                self.baseline.archive_and_reset_diagnostic_execution_attempt(failed, recovery=recovery)
                with self.assertRaisesRegex(self.baseline.GenesisVlmSchemaError, "non-fresh state"):
                    self.baseline.require_v2_session_state(failed, allow_fresh_unplanned=True)
                state = copy.deepcopy(original)
                attachments = copy.deepcopy(state["diagnostic_runtime_attachments"])
                sessions = copy.deepcopy(state["diagnostic_runtime_sessions"])
                context = copy.deepcopy(state["diagnostics"]["part_grounding_context"])
                archive = self.module.archive_and_reset_diagnostic_execution_attempt(state, recovery=recovery)
                snapshot = archive["execution_snapshot"]
                for key in ("part_grounding_context_measurements", "geometry_context_measurements", "runtime_owned_events"):
                    self.assertEqual(snapshot[key], original["diagnostics"][key])
                    self.assertEqual(state["diagnostics"][key], [])
                self.assertEqual(state["diagnostics"]["part_grounding_context"], context)
                self.assertEqual(state["diagnostic_runtime_attachments"], attachments)
                self.assertEqual(state["diagnostic_runtime_sessions"], sessions)
                self.assertIsNone(self.module.require_v2_session_state(state, allow_fresh_unplanned=True))
                self.assertEqual(state["diagnostics"]["diagnostic_region_ledger"], [])
                self.assertEqual(state["diagnostics"]["region_episode_ids"], {})
                self.assertEqual(state["diagnostics"]["episodes"], [])
                self.assertEqual(archive["source_agent_invocation_id"], recovery["source_agent_invocation_id"])
                self.assertEqual(archive["recovery_event_id"], recovery["event_id"])
                self.assertEqual(self.module.archive_and_reset_diagnostic_execution_attempt(state, recovery=recovery), archive)

    def test_actual_successor_new_plan_has_no_old_episode_ownership(self):
        original, recovery = self.production_state("genesis_sloth_20261021")
        state = copy.deepcopy(original)
        self.module.archive_and_reset_diagnostic_execution_attempt(state, recovery=recovery)
        plan = sample_plan(self.module)
        self.assertEqual(self.record_plan_in_memory(state, plan)["status"], "success")
        self.assertTrue(all(row["episode_id"] is None for row in state["diagnostics"]["diagnostic_region_ledger"]))
        self.assertEqual(state["diagnostics"]["region_episode_ids"], {})
        self.assertEqual(state["diagnostics"]["episodes"], [])
        self.assertEqual(len(state["diagnostics"]["diagnostic_attempt_archives"]), 1)

    def test_geometry_histories_also_archive_and_clear(self):
        state, recovery = transport_failure_state(self.module)
        measurements = [{"measurement_index": index, "geometry_context": {"fixture": index}} for index in range(3)]
        state["diagnostics"]["geometry_context_measurements"] = copy.deepcopy(measurements)
        archive = self.module.archive_and_reset_diagnostic_execution_attempt(state, recovery=recovery)
        self.assertEqual(archive["execution_snapshot"]["geometry_context_measurements"], measurements)
        self.assertEqual(state["diagnostics"]["geometry_context_measurements"], [])
        self.assertIsNone(self.module.require_v2_session_state(state, allow_fresh_unplanned=True))

    def test_first_attempt_readonly_measurement_contract_unchanged(self):
        for module in (self.baseline, self.module):
            state = read_only_measurement_state(module)
            self.assertIsNone(module.require_v2_session_state(state, allow_fresh_unplanned=True))

    def test_multiple_unarchived_measurements_are_not_fresh(self):
        state = read_only_measurement_state(self.module)
        second = copy.deepcopy(state["diagnostics"]["part_grounding_context_measurements"][0])
        second["measurement_index"] = 1
        state["diagnostics"]["part_grounding_context_measurements"].append(second)
        self.assertFalse(self.module.is_fresh_unplanned_diagnostics_state(state))

    def test_malformed_or_forged_active_measurements_are_rejected(self):
        changes = ({"source": "invented"}, {"measurement_index": True},
                   {"measurement_index": 1}, {"part_grounding_context": []}, {"extra": "forged"})
        for changeset in changes:
            with self.subTest(fields=list(changeset)):
                state = read_only_measurement_state(self.module)
                state["diagnostics"]["part_grounding_context_measurements"][0].update(changeset)
                self.assertFalse(self.module.is_fresh_unplanned_diagnostics_state(state))
        state = read_only_measurement_state(self.module)
        state["diagnostics"]["part_grounding_context_measurements"] = [None]
        self.assertFalse(self.module.is_fresh_unplanned_diagnostics_state(state))

    def test_unowned_or_forged_measurement_events_are_rejected(self):
        for field, value in (("event_id", 2), ("event", "invented"), ("provenance", "agent"),
                             ("detail", {}), ("note", "forged")):
            with self.subTest(field=field):
                state = read_only_measurement_state(self.module)
                state["diagnostics"]["runtime_owned_events"][0][field] = value
                self.assertFalse(self.module.is_fresh_unplanned_diagnostics_state(state))
        state = read_only_measurement_state(self.module)
        state["diagnostics"]["runtime_owned_events"] = []
        self.assertFalse(self.module.is_fresh_unplanned_diagnostics_state(state))

    def test_forged_successor_namespace_does_not_bypass_fresh_gate(self):
        state = read_only_measurement_state(self.module)
        state["diagnostics"]["active_diagnostic_attempt_id"] = "diagnostic_attempt_0002"
        state["diagnostics"]["runtime_owned_events"] = []
        self.assertFalse(self.module.is_fresh_unplanned_diagnostics_state(state))

    def test_successor_cannot_reuse_old_episode_or_active_execution_fields(self):
        original, recovery = transport_failure_state(self.module)
        for key, value in (("episodes", [{"episode_id": "old_episode"}]),
                           ("diagnostic_region_ledger", [{"region_id": "old", "episode_id": "old_episode"}]),
                           ("region_episode_ids", {"old": "old_episode"}),
                           ("active_episode_index", 0)):
            with self.subTest(key=key):
                state = copy.deepcopy(original)
                self.module.archive_and_reset_diagnostic_execution_attempt(state, recovery=recovery)
                state["diagnostics"][key] = value
                self.assertFalse(self.module.is_fresh_unplanned_diagnostics_state(state))

    def test_open_or_foreign_session_blocks_fresh_successor(self):
        original, recovery = transport_failure_state(self.module)
        state = copy.deepcopy(original)
        self.module.archive_and_reset_diagnostic_execution_attempt(state, recovery=recovery)
        state["diagnostic_runtime_sessions"][0]["lifecycle_state"] = "bound"
        self.assertFalse(self.module.is_fresh_unplanned_diagnostics_state(state))
        state = minimal_state(self.module)
        state["diagnostic_runtime_sessions"] = [{"lifecycle_state": "closed"}]
        self.assertFalse(self.module.is_fresh_unplanned_diagnostics_state(state))

    def test_unknown_execution_field_and_malformed_recovery_fail_without_mutation(self):
        original, recovery = transport_failure_state(self.module)
        state = copy.deepcopy(original)
        state["diagnostics"]["unknown_execution_evidence"] = {"forged": True}
        before = copy.deepcopy(state)
        with self.assertRaisesRegex(ValueError, "unclassified"):
            self.module.archive_and_reset_diagnostic_execution_attempt(state, recovery=recovery)
        self.assertEqual(state, before)
        state = copy.deepcopy(original)
        with self.assertRaisesRegex(ValueError, "malformed"):
            self.module.archive_and_reset_diagnostic_execution_attempt(state, recovery={**recovery, "extra": "forged"})
        self.assertEqual(state, original)

    def test_no_transport_recovery_for_wrong_owner_or_forged_provenance(self):
        original, _ = transport_failure_state(self.module)
        attachment_id = original["diagnostic_runtime_attachments"][-1]["attachment_id"]
        self.assertIsNone(self.recovery_metadata(original, "nonexistent_owner"))
        for field, value in (("failure_kind", "owner_lease_expired"), ("retryable", False)):
            state = copy.deepcopy(original)
            state["diagnostics"]["terminal"]["operational_outcome"][field] = value
            self.assertIsNone(self.recovery_metadata(state, attachment_id))
        state = copy.deepcopy(original)
        state["diagnostic_runtime_attachments"][-1]["history"] = []
        self.assertIsNone(self.recovery_metadata(state, attachment_id))
        state = copy.deepcopy(original)
        state["diagnostics"]["terminal"]["business_outcome"] = {"status": "accepted", "recommendation": "accept"}
        self.assertIsNone(self.recovery_metadata(state, attachment_id))

    def test_immutable_plan_rewrite_still_rejected(self):
        state = minimal_state(self.module)
        plan = sample_plan(self.module)
        self.record_plan_in_memory(state, plan)
        changed = copy.deepcopy(plan)
        changed["session_intent"] = "Rewrite the old intent."
        with self.assertRaisesRegex(self.module.GenesisVlmSchemaError, "immutable"):
            self.record_plan_in_memory(state, changed)

    def test_tampered_plan_lineage_still_rejected(self):
        state = minimal_state(self.module)
        self.record_plan_in_memory(state, sample_plan(self.module))
        state["diagnostics"]["diagnostic_session_plans"] = []
        with self.assertRaisesRegex(self.module.GenesisVlmSchemaError, "lineage"):
            self.module.require_v2_session_state(state)

    def test_one_region_one_episode_gate_still_rejects_reuse(self):
        state = minimal_state(self.module)
        plan = sample_plan(self.module)
        self.record_plan_in_memory(state, plan)
        region = state["diagnostics"]["diagnostic_region_ledger"][0]
        region["episode_id"] = "old_episode"
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(self.module, "_require_bound_diagnostic_run_root", return_value="fixture"))
            stack.enter_context(mock.patch.object(self.module, "_require_state", return_value=state))
            stack.enter_context(mock.patch.object(self.module, "_active_session_anchor", return_value=plan["regions"][0]))
            stack.enter_context(mock.patch.object(self.module, "_select_setup_trial_for_episode", return_value={}))
            stack.enter_context(mock.patch.object(self.module, "_setup_quality_from_trial", return_value={}))
            stack.enter_context(mock.patch.object(self.module, "_pinning_from_setup_trial", return_value={}))
            stack.enter_context(mock.patch.object(self.module, "create_diagnostic_episode_suite", return_value={"episode": {}}))
            with self.assertRaisesRegex(self.module.GenesisVlmSchemaError, "exactly one episode"):
                self.module.create_diagnostic_episode_from_anchor("fixture", region["region_id"], "fixture")

    def test_patch_preserves_historical_settlement_fix_and_fresh_validator_source(self):
        # Neither the security gate nor the existing historical-settlement
        # verifier is changed by the classification-only retry patch.
        before_functions = {node.name: ast.dump(node, include_attributes=False)
                            for node in ast.parse(self.baseline.verified_test_source).body
                            if isinstance(node, ast.FunctionDef)}
        after_functions = {node.name: ast.dump(node, include_attributes=False)
                           for node in ast.parse(self.module.verified_test_source).body
                           if isinstance(node, ast.FunctionDef)}
        for name in ("require_v2_session_state", "is_fresh_unplanned_diagnostics_state",
                     "_fresh_preplan_readonly_measurements_are_valid", "_derive_region_close_settlement"):
            self.assertEqual(before_functions[name], after_functions[name], name)


if __name__ == "__main__":
    unittest.main()
