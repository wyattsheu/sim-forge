"""CPU-only checks for the one-call bridge; no production run is modified."""
from contextlib import redirect_stderr, redirect_stdout
from functools import partial
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


WORKSPACE = Path(__file__).resolve().parents[3]
SCRIPT = WORKSPACE / "tools" / "diaggen_support" / "stage_tool.py"
SPEC = importlib.util.spec_from_file_location("test_diaggen_stage_tool", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)
GPU = "GPU-ef92f209-a96e-e42c-a1c9-96e2f1db7e55"
OTHER_GPU = "GPU-9ea7f276-1404-458e-ae57-a2698b66a4e7"


class StageToolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.input_path = Path(self.directory.name) / "args.json"
        self.run_root = str(Path(self.directory.name) / "initialized_run")

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = bridge.main(list(args))
        return rc, json.loads(stdout.getvalue()), stderr.getvalue()

    def write_input(self, value):
        self.input_path.write_text(json.dumps(value), encoding="utf-8")
        return str(self.input_path)

    def fake_guard(self, returncode=0):
        guard = bridge.load_guard_module()
        guard.wait_for_memory = mock.Mock(return_value=returncode)
        return guard

    def runtime(self, binding=GPU, *, missing_state=False):
        return SimpleNamespace(
            load_state=mock.Mock(return_value={} if missing_state else {"run_root": self.run_root}),
            worker_cuda_visible_devices=mock.Mock(return_value=binding),
        )

    def environment(self, **changes):
        environment = {"CUDA_VISIBLE_DEVICES": GPU, "DIAGGEN_JOB_MINIMUM_FREE_MIB": "24576"}
        environment.update(changes)
        return environment

    def test_explicit_names_exclude_all_diagnostic_and_transition_tools(self):
        self.assertEqual(len(bridge.TOOL_MODULES), 30)
        for name in ("attach_diagnostic_run", "renew_diagnostic_owner_lease",
                     "create_genesis_live_session", "close_genesis_live_session",
                     "simulation_reset", "simulate", "finalize_diagnostic_run",
                     "materialize_diagnostic_terminal_artifacts", "apply_diagnostic_recommendation",
                     "save_state", "load_state", "__dict__", "__import__"):
            with self.subTest(name=name), mock.patch.object(bridge, "import_native_module") as importer:
                with self.assertRaisesRegex(ValueError, "not allowlisted"):
                    bridge.resolve_tool(name)
                importer.assert_not_called()

    def test_workspace_and_guard_paths_derive_from_script(self):
        self.assertEqual(bridge.WORKSPACE, WORKSPACE)
        self.assertEqual(bridge.GUARD_PATH, WORKSPACE / "tools" / "wait_diaggen_gpu_memory.py")
        self.assertNotEqual(bridge.GUARD_PATH.parent, bridge.DIAGGEN_ROOT)
        guard = bridge.load_guard_module()
        self.assertEqual(Path(guard.__file__).resolve(), bridge.GUARD_PATH)

    def test_native_module_origin_rejects_another_checkout(self):
        with mock.patch.object(bridge.importlib, "import_module", return_value=SimpleNamespace(__file__="/tmp/other.py")):
            with self.assertRaisesRegex(ImportError, "must come from"):
                bridge.import_native_module(bridge.STAGE_MODULE)

    def test_missing_checkout_fails_without_import(self):
        with mock.patch.object(bridge, "DIAGGEN_ROOT", Path(self.directory.name) / "missing"), \
                mock.patch.object(bridge.importlib, "import_module") as importer:
            with self.assertRaises(FileNotFoundError):
                bridge.import_native_module(bridge.STAGE_MODULE)
            importer.assert_not_called()

    def test_missing_native_callable_is_an_import_error(self):
        with mock.patch.object(bridge, "import_native_module", return_value=SimpleNamespace()):
            with self.assertRaisesRegex(ImportError, "unavailable"):
                bridge.resolve_tool("submit_segmentation_stage")

    def test_list_imports_and_inspects_without_calling_tools(self):
        def native(run_root, summary=""):
            self.fail("--list must never invoke a native function")
        with mock.patch.object(bridge, "resolve_tool", return_value=native) as resolver:
            rc, result, _ = self.cli("--list")
        self.assertEqual(rc, 0)
        self.assertEqual(result["tools"], list(bridge.TOOL_MODULES))
        self.assertEqual(resolver.call_count, len(bridge.TOOL_MODULES))
        self.assertIn("run_root", result["signatures"]["submit_segmentation_stage"])

    def test_list_reports_import_failure_as_failure(self):
        with mock.patch.object(bridge, "resolve_tool", side_effect=ImportError("missing native dependency")):
            rc, result, stderr = self.cli("--list")
        self.assertEqual(rc, 1)
        self.assertEqual(result["error"]["type"], "ImportError")
        self.assertIn("missing native dependency", stderr)

    def test_list_rejects_invocation_arguments(self):
        with mock.patch.object(bridge, "list_tools") as listing:
            rc, result, _ = self.cli("--list", "submit_segmentation_stage")
        self.assertEqual(rc, 1)
        self.assertIn("by itself", result["error"]["message"])
        listing.assert_not_called()

    def test_native_is_called_once_and_its_result_is_preserved(self):
        calls = []
        expected = {"status": "pending_validation", "summary": "actually submitted"}
        def native(run_root, summary=""):
            calls.append((run_root, summary))
            print("native progress message")
            return expected
        path = self.write_input({"run_root": self.run_root, "summary": "observed artifacts"})
        with mock.patch.object(bridge, "resolve_tool", return_value=native), \
                mock.patch.object(bridge, "require_omnipart_memory") as guard:
            rc, result, stderr = self.cli("submit_segmentation_stage", "--input-json", path)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [(self.run_root, "observed artifacts")])
        self.assertEqual(result["result"], expected)
        self.assertIn("native progress message", stderr)
        guard.assert_not_called()

    def test_native_exception_is_preserved_and_not_retried(self):
        native = mock.Mock(side_effect=RuntimeError("actual native failure"))
        path = self.write_input({})
        with mock.patch.object(bridge, "resolve_tool", return_value=native):
            rc, result, stderr = self.cli("submit_segmentation_stage", "--input-json", path)
        self.assertEqual(rc, 1)
        self.assertEqual(result["error"], {"type": "RuntimeError", "message": "actual native failure"})
        self.assertIn("actual native failure", stderr)
        native.assert_called_once_with()

    def test_native_retryable_failure_result_is_not_rewritten(self):
        result = {"result": {"ok": False, "metrics": {"retryable": True}, "error": "too many parts"}}
        def native(run_root):
            return result
        with mock.patch.object(bridge, "resolve_tool", return_value=native):
            actual = bridge.invoke_tool("run_sam3_omnipart_2d_segmentation_stage", {"run_root": self.run_root})
        self.assertIs(actual, result)

    def test_missing_or_unexpected_native_arguments_block_call_and_guard(self):
        called = []
        def native(run_root):
            called.append(run_root)
        for arguments in ({}, {"run_root": self.run_root, "typo": True}):
            with self.subTest(arguments=arguments), mock.patch.object(bridge, "resolve_tool", return_value=native), \
                    mock.patch.object(bridge, "require_omnipart_memory") as guard:
                with self.assertRaises(TypeError):
                    bridge.invoke_tool(bridge.OMNIPART_TOOL, arguments)
                guard.assert_not_called()
        self.assertEqual(called, [])

    def test_json_array_malformed_duplicates_and_nonfinite_block_call(self):
        for text in ("[]", "{broken", '{"run_root":"a","run_root":"b"}', '{"value":NaN}'):
            self.input_path.write_text(text, encoding="utf-8")
            with self.subTest(text=text), mock.patch.object(bridge, "invoke_tool") as invoke:
                rc, result, _ = self.cli("submit_segmentation_stage", "--input-json", str(self.input_path))
                self.assertEqual(rc, 1)
                self.assertEqual(result["status"], "error")
                invoke.assert_not_called()

    def test_missing_input_file_blocks_call(self):
        with mock.patch.object(bridge, "invoke_tool") as invoke:
            rc, result, _ = self.cli("submit_segmentation_stage", "--input-json", str(self.input_path))
        self.assertEqual(rc, 1)
        self.assertEqual(result["error"]["type"], "FileNotFoundError")
        invoke.assert_not_called()

    def test_unknown_cli_tool_fails_without_native_import(self):
        with mock.patch.object(bridge, "import_native_module") as importer:
            rc, result, _ = self.cli("attach_diagnostic_run", "--input-json", self.write_input({}))
        self.assertEqual(rc, 1)
        self.assertIn("not allowlisted", result["error"]["message"])
        importer.assert_not_called()

    def test_non_omnipart_does_not_accept_a_supposed_memory_guard_override(self):
        native = mock.Mock()
        with mock.patch.object(bridge, "resolve_tool", return_value=native):
            with self.assertRaisesRegex(ValueError, "only valid"):
                bridge.invoke_tool("submit_segmentation_stage", {}, minimum_free_mib=24576)
        native.assert_not_called()

    def test_omnipart_guard_precedes_exactly_one_native_call_on_exact_uuid(self):
        events = []
        guard = self.fake_guard()
        def wait(uuid, minimum, *, emit):
            events.append(("guard", uuid, minimum))
            emit({"status": "ready", "gpu_uuid": uuid})
            return 0
        guard.wait_for_memory.side_effect = wait
        def native(run_root):
            events.append(("native", run_root))
            return {"ok": True}
        runtime = self.runtime()
        with mock.patch.object(bridge, "resolve_tool", return_value=native), \
                mock.patch.object(bridge, "load_guard_module", return_value=guard), \
                mock.patch.object(bridge, "import_native_module", return_value=runtime), \
                redirect_stderr(io.StringIO()) as stderr:
            result = bridge.invoke_tool(bridge.OMNIPART_TOOL, {"run_root": self.run_root}, environment=self.environment())
        self.assertEqual(events, [("guard", GPU, 24576), ("native", self.run_root)])
        self.assertEqual(result, {"ok": True})
        self.assertIn(GPU, stderr.getvalue())
        runtime.load_state.assert_called_once_with(str(Path(self.run_root).resolve()))

    def test_explicit_memory_threshold_works_without_environment_default(self):
        guard, runtime = self.fake_guard(), self.runtime()
        with mock.patch.object(bridge, "load_guard_module", return_value=guard), \
                mock.patch.object(bridge, "import_native_module", return_value=runtime):
            bridge.require_omnipart_memory({"run_root": self.run_root}, 49152,
                                          environment={"CUDA_VISIBLE_DEVICES": GPU})
        self.assertEqual(guard.wait_for_memory.call_args.args, (GPU, 49152))

    def test_missing_and_invalid_thresholds_never_query_gpu(self):
        for configured in (None, "", "0", "-1", "2.5", " 24576", "NaN", "１２３"):
            guard = self.fake_guard()
            with self.subTest(configured=configured), \
                    mock.patch.object(bridge, "load_guard_module", return_value=guard), \
                    mock.patch.object(bridge, "import_native_module") as importer:
                with self.assertRaises(ValueError):
                    bridge.require_omnipart_memory({"run_root": self.run_root}, environment=self.environment(DIAGGEN_JOB_MINIMUM_FREE_MIB=configured))
                guard.wait_for_memory.assert_not_called()
                importer.assert_not_called()

    def test_invalid_or_multiple_gpu_tokens_never_query_or_call_native(self):
        for token in (None, "", "0", "0,1", f"{GPU},{OTHER_GPU}", "MIG-not-a-full-gpu", f" {GPU}"):
            native, guard = mock.Mock(), self.fake_guard()
            with self.subTest(token=token), mock.patch.object(bridge, "resolve_tool", return_value=native), \
                    mock.patch.object(bridge, "load_guard_module", return_value=guard):
                with self.assertRaises(ValueError):
                    bridge.invoke_tool(bridge.OMNIPART_TOOL, {"run_root": self.run_root}, environment=self.environment(CUDA_VISIBLE_DEVICES=token))
                native.assert_not_called()
                guard.wait_for_memory.assert_not_called()

    def test_worker_gpu_mismatch_or_unbound_state_prevents_query_and_native(self):
        for binding in (OTHER_GPU, None, "0"):
            native, guard, runtime = mock.Mock(), self.fake_guard(), self.runtime(binding)
            with self.subTest(binding=binding), mock.patch.object(bridge, "resolve_tool", return_value=native), \
                    mock.patch.object(bridge, "load_guard_module", return_value=guard), \
                    mock.patch.object(bridge, "import_native_module", return_value=runtime):
                with self.assertRaises(ValueError):
                    bridge.invoke_tool(bridge.OMNIPART_TOOL, {"run_root": self.run_root}, environment=self.environment())
                native.assert_not_called()
                guard.wait_for_memory.assert_not_called()

    def test_missing_runtime_state_prevents_query_and_native(self):
        native, guard = mock.Mock(), self.fake_guard()
        with mock.patch.object(bridge, "resolve_tool", return_value=native), \
                mock.patch.object(bridge, "load_guard_module", return_value=guard), \
                mock.patch.object(bridge, "import_native_module", return_value=self.runtime(missing_state=True)):
            with self.assertRaisesRegex(ValueError, "existing initialized"):
                bridge.invoke_tool(bridge.OMNIPART_TOOL, {"run_root": self.run_root}, environment=self.environment())
        native.assert_not_called()
        guard.wait_for_memory.assert_not_called()

    def test_guard_failure_and_false_return_never_invoke_native(self):
        for guard_rc in (1, None, False):
            native, guard = mock.Mock(), self.fake_guard(guard_rc)
            with self.subTest(guard_rc=guard_rc), mock.patch.object(bridge, "resolve_tool", return_value=native), \
                    mock.patch.object(bridge, "load_guard_module", return_value=guard), \
                    mock.patch.object(bridge, "import_native_module", return_value=self.runtime()):
                with self.assertRaisesRegex(RuntimeError, "did not succeed"):
                    bridge.invoke_tool(bridge.OMNIPART_TOOL, {"run_root": self.run_root}, environment=self.environment())
                native.assert_not_called()

    def test_real_guard_wait_then_probe_failure_does_not_invoke_native(self):
        guard = bridge.load_guard_module()
        query = mock.Mock(side_effect=[f"{GPU}, 1\n", "malformed probe"])
        sleep = mock.Mock()
        guard.wait_for_memory = partial(guard.wait_for_memory, query=query, sleep=sleep)
        native = mock.Mock()
        with mock.patch.object(bridge, "resolve_tool", return_value=native), \
                mock.patch.object(bridge, "load_guard_module", return_value=guard), \
                mock.patch.object(bridge, "import_native_module", return_value=self.runtime()), \
                redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(RuntimeError):
                bridge.invoke_tool(bridge.OMNIPART_TOOL, {"run_root": self.run_root}, environment=self.environment())
        self.assertEqual(query.call_count, 2)
        sleep.assert_called_once_with(15)
        self.assertIn('"status": "waiting"', stderr.getvalue())
        self.assertIn('"status": "probe_failed"', stderr.getvalue())
        native.assert_not_called()

    def test_missing_guard_file_fails_before_native(self):
        native = mock.Mock()
        with mock.patch.object(bridge, "resolve_tool", return_value=native), \
                mock.patch.object(bridge, "GUARD_PATH", Path(self.directory.name) / "missing_guard.py"):
            with self.assertRaises(FileNotFoundError):
                bridge.invoke_tool(bridge.OMNIPART_TOOL, {"run_root": self.run_root}, environment=self.environment())
        native.assert_not_called()


class NativeListIntegrationTest(unittest.TestCase):
    def test_actual_native_functions_import_from_any_working_directory(self):
        python = WORKSPACE / "tools" / "diaggen" / ".conda" / "hag4r" / "bin" / "python"
        if not python.is_file():
            self.skipTest("Native DiagGen Python is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([str(python), str(SCRIPT), "--list"], cwd=directory,
                                    env=dict(os.environ, PYTHONNOUSERSITE="1"),
                                    capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        listing = json.loads(result.stdout)
        self.assertEqual(set(listing["tools"]), set(bridge.TOOL_MODULES))
        self.assertIn("sam3_prompt", listing["signatures"]["run_sam3_omnipart_2d_segmentation_stage"])
        self.assertEqual(listing["signatures"][bridge.OMNIPART_TOOL], "(run_root: 'str') -> 'dict[str, Any]'")


if __name__ == "__main__":
    unittest.main()
