"""Exercise real native successor admission against immutable local audit states."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

WORKSPACE = Path(__file__).resolve().parents[3]
NATIVE = WORKSPACE / "tools/diaggen"
HELPER = WORKSPACE / "tools/diaggen_support/check_diagnostic_retry.py"
FIXTURES = NATIVE / "outputs/preflight/diagnostic_retry_reset_baseline_20261022"
SPEC = importlib.util.spec_from_file_location("recovery_preflight", HELPER)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecoveryPreflightTests(unittest.TestCase):
    def fixture(self, name="sneaker"):
        path = FIXTURES / (name + ".json")
        before = path.read_bytes()
        self.addCleanup(lambda: self.assertEqual(path.read_bytes(), before))
        return json.loads(before)

    def test_real_native_successor_validation_is_read_only_for_both_failed_runs(self):
        for name, count in (("sneaker", 3), ("sloth", 10)):
            with self.subTest(name=name):
                state = self.fixture(name)
                before = copy.deepcopy(state)
                report = MODULE.validate_retry_state(state, diaggen_root=NATIVE)
                self.assertTrue(report["fresh_unplanned"])
                self.assertEqual(report["archived_grounding_measurement_count"], count)
                self.assertEqual(state, before)
                # Credentials and attachment/session identities never leave
                # the deterministic validator in its public report.
                for field in ("attachment_id", "owner_lease_token", "live_session_handle"):
                    self.assertNotIn(field, json.dumps(report))

    def test_helper_does_not_construct_mcp_or_save_native_state(self):
        sys.path.insert(0, str(NATIVE))
        from hag4r.agentic.diagnostic_mcp_server import DiagnosticMcpRuntime
        from hag4r.agentic import runtime_state
        with mock.patch.object(DiagnosticMcpRuntime, "__init__", side_effect=AssertionError("MCP creation forbidden")), \
                mock.patch.object(runtime_state, "save_state", side_effect=AssertionError("native state write forbidden")):
            self.assertTrue(MODULE.validate_retry_state(self.fixture(), diaggen_root=NATIVE)["valid"])

    def test_untyped_lease_expiry_cannot_be_used_as_transport_recovery(self):
        state = self.fixture()
        state["diagnostics"]["terminal"]["operational_outcome"]["failure_kind"] = "owner_lease_expired"
        with self.assertRaisesRegex(ValueError, "transport recovery provenance"):
            MODULE.validate_retry_state(state, diaggen_root=NATIVE)

    def test_still_open_session_cannot_be_accepted_as_fresh(self):
        state = self.fixture()
        state["diagnostic_runtime_sessions"][-1]["lifecycle_state"] = "bound"
        with self.assertRaisesRegex(ValueError, "non-fresh state"):
            MODULE.validate_retry_state(state, diaggen_root=NATIVE)

    def test_missing_owner_and_unknown_execution_evidence_fail(self):
        state = self.fixture()
        state["diagnostic_runtime_attachments"] = []
        with self.assertRaisesRegex(ValueError, "durable terminal owner"):
            MODULE.validate_retry_state(state, diaggen_root=NATIVE)
        state = self.fixture()
        state["diagnostics"]["unclassified_execution_evidence"] = {"forged": True}
        with self.assertRaisesRegex(ValueError, "unclassified"):
            MODULE.validate_retry_state(state, diaggen_root=NATIVE)

    def test_snapshot_helper_calls_native_preflight_with_appearance_enabled(self):
        sys.path.insert(0, str(NATIVE))
        from hag4r.agentic import runtime_state
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder)
            (snapshot / "state.json").write_text("{}")
            with mock.patch.object(runtime_state, "_preflight_diagnostics_snapshot_before_run_root_reservation") as check:
                report = MODULE.validate_snapshot(snapshot, diaggen_root=NATIVE)
            check.assert_called_once_with(diagnostics_revision_snapshot_dir=snapshot.resolve(),
                                          repo_root=NATIVE.resolve(), diagnostics_stage_only=False)
        self.assertTrue(report["appearance_preflight"])


if __name__ == "__main__":
    unittest.main()
