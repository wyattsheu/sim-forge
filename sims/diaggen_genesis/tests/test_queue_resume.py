"""Apply the reviewed resume patch to temporary copies; never edit production."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


WORKSPACE = Path(__file__).resolve().parents[3]
PATCH_PATH = WORKSPACE / "tools/diaggen_support/resume_queue.patch"
MANIFEST_PATH = PATCH_PATH.with_suffix(".json")
BATCH_RELATIVE = "sims/diaggen_genesis/queue/batch_control.py"
SHELL_RELATIVE = "sims/diaggen_genesis/queue/run_one.sh"
GPU = "GPU-ef92f209-a96e-e42c-a1c9-96e2f1db7e55"
OTHER_GPU = "GPU-9ea7f276-1404-458e-ae57-a2698b66a4e7"
GPU_CSV = f"0,{GPU},50000\n1,{OTHER_GPU},70000\n"
STAGES = ["image_cleanup", "sam3_omnipart_2d_segmentation", "omnipart_generate_parts",
          "hag4r_gpt_staged_material_inference", "hag4r_assign_params_to_prims",
          "hag4r_combined_to_monolithic", "genesis_live_diagnostic_loop",
          "hag4r_post_mesh_texture", "hag4r_final_export_bundle"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def temporary_patched_sources(destination):
    manifest = json.loads(MANIFEST_PATH.read_text())
    before_files = []
    for relative, record in manifest["files"].items():
        source = WORKSPACE / relative
        actual = digest(source)
        if actual not in (record["before_sha256"], record["after_sha256"]):
            raise AssertionError(f"Resume patch baseline changed; review/rebase required: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if actual == record["before_sha256"]:
            before_files.append(relative)
    if before_files:
        # Avoid applying already-installed hunks when testing after deployment.
        text = PATCH_PATH.read_text()
        sections = ["--- a/" + item for item in text.split("--- a/")[1:]]
        selected = "".join(item for item in sections if item.splitlines()[0][6:] in before_files)
        result = subprocess.run(["patch", "--batch", "--forward", "-p1"], input=selected,
                                cwd=destination, capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
    for relative, record in manifest["files"].items():
        if digest(destination / relative) != record["after_sha256"]:
            raise AssertionError(f"Patched source digest differs: {relative}")


class SameRunResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patched = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.patched.cleanup)
        cls.patched_root = Path(cls.patched.name)
        cls.production_digests = {name: digest(WORKSPACE / name) for name in (BATCH_RELATIVE, SHELL_RELATIVE)}
        temporary_patched_sources(cls.patched_root)
        spec = importlib.util.spec_from_file_location("temporary_diaggen_resume_batch", cls.patched_root / BATCH_RELATIVE)
        cls.batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.batch)

    @classmethod
    def tearDownClass(cls):
        for name, expected in cls.production_digests.items():
            if digest(WORKSPACE / name) != expected:
                raise AssertionError(f"Production source changed during temporary tests: {name}")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.base = self.workspace / "sims/diaggen_genesis"
        self.base.mkdir(parents=True)
        self.native = self.workspace / "tools/diaggen"
        self.run_id = "genesis_object_0"
        self.run_root = self.native / "outputs/agentic_asset_refinement" / self.run_id
        self.frozen = self.native / "outputs/inputs" / f"{self.run_id}.png"
        self.frozen.parent.mkdir(parents=True)
        self.frozen.write_bytes(b"original frozen user input")
        self.source = self.base / "inputs/demo_gallery/object.png"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(self.frozen.read_bytes())
        self.plan = {"schema_version": self.batch.PLAN_SCHEMA, "policy": dict(self.batch.DEFAULT_POLICY),
                     "jobs": [{"id": "object_0", "run_id": self.run_id,
                               "input": "inputs/demo_gallery/object.png", "input_sha256": digest(self.frozen)}]}
        (self.base / "batch_plan.json").write_text(json.dumps(self.plan))
        self.queue = self.batch.Queue(self.base, gpu_query=lambda: GPU_CSV)
        self.queue.init()
        self.assertEqual(self.queue.claim(GPU), "object_0")
        self.queue.bind("object_0", 99999999)
        self.queue.finish("object_0", "failed", "execution_failed")
        self.job_directory = self.base / "queue/jobs/object_0"
        self.job_directory.mkdir(parents=True)
        for name, value in {"STARTED": self.run_id, "launcher.log": "original failed launcher\n",
                            "codex_events.jsonl": "original failed events\n", "selected_input.txt": str(self.frozen),
                            "original_input.txt": str(self.source), "selected_gpu.txt": GPU}.items():
            (self.job_directory / name).write_text(value)
        self.hold = self.base / "queue/HOLD"
        self.hold.touch()
        self.state = self.native_state(2)
        self.save_native()

    def native_state(self, prefix, *, diagnostic_retry=False):
        self.run_root.mkdir(parents=True, exist_ok=True)
        revision = self.run_root / "revisions/revision_0000"
        revision.mkdir(parents=True, exist_ok=True)
        paths = {"source_image": str(self.frozen), "sim_diagnostics_dir": str(revision / "sim_diagnostics")}
        stages = {name: {"status": "pending", "ok": False, "artifacts": {"expected": []}} for name in STAGES}
        for index, name in enumerate(STAGES[:prefix]):
            artifact = revision / f"evidence_{index}.json"
            artifact.write_text('{"actual_artifact":true}\n')
            stages[name] = {"status": "success", "ok": True,
                            "artifacts": {"expected": [{"path": str(artifact), "required": True}]}}
        if prefix >= 2:
            for key, name, value in (("segmentation_manifest_path", "manifest.json", {"sam3_pre_postprocess_mask_count": 2}),
                                     ("sam3_raw_metadata_path", "raw.json", {"mask_count": 2})):
                path = revision / name
                path.write_text(json.dumps(value))
                paths[key] = str(path)
        state = {"schema_version": "2026-07-skill-suite-runtime-state-v2", "run_id": self.run_id,
                 "run_root": str(self.run_root), "repo_root": str(self.native), "run_mode": "full_image",
                 "runtime_kind": "codex_skill", "status": "seeded", "inputs": {"source_image": str(self.frozen)},
                 "paths": paths, "planned_global_stage_sequence": list(STAGES), "stages": stages,
                 "completed_global_stage_sequence": STAGES[:prefix], "stage_runtime": {},
                 "worker_isolation": {"gpu_binding": {"effective_cuda_visible_devices": GPU}},
                 "diagnostics": {"enabled": True}}
        if diagnostic_retry:
            stages["genesis_live_diagnostic_loop"]["status"] = "pending_retry"
            state["diagnostics"]["terminal"] = {"status": "retryable",
                "business_outcome": {"status": "not_authored", "recommendation": None},
                "operational_outcome": {"status": "cleanup_retryable", "retryable": True,
                    "cleanup_status": "complete", "failure_kind": "mcp_server_shutdown"}}
            state["diagnostic_runtime_attachments"] = [{"status": "superseded"}, {"status": "failed"}]
            state["diagnostic_runtime_sessions"] = [{"lifecycle_state": "closed"}, {"lifecycle_state": "closed_failed"}]
            ownership = Path(paths["sim_diagnostics_dir"]) / "runtime_ownership.json"
            ownership.parent.mkdir(parents=True)
            ownership.write_text(json.dumps({key: state[key] for key in ("diagnostic_runtime_attachments", "diagnostic_runtime_sessions")}))
        return state

    def save_native(self):
        (self.run_root / "state.json").write_text(json.dumps(self.state))

    def queue_state(self):
        return json.loads(self.queue.path.read_text())

    def resume(self, identifier="resume_01"):
        with patch.object(self.batch.os, "kill", side_effect=ProcessLookupError):
            return self.queue.resume("object_0", identifier, "stage_tool_protocol_repaired")

    def test_resume_preserves_native_bytes_and_original_logs_without_input_recopy(self):
        state_bytes = (self.run_root / "state.json").read_bytes()
        frozen_bytes = self.frozen.read_bytes()
        self.source.write_bytes(b"user changed original after job started")
        archive = self.base / "runs" / self.run_id
        archive.mkdir(parents=True)
        (archive / "old_failure.json").write_text("preserved previous archive")
        mapping = self.resume()
        self.assertEqual((self.run_root / "state.json").read_bytes(), state_bytes)
        self.assertEqual(self.frozen.read_bytes(), frozen_bytes)
        job = self.queue_state()["jobs"][0]
        self.assertEqual((job["status"], job["attempts"], job["run_id"]), ("queued", 1, self.run_id))
        self.assertEqual(job["resume_gpu_uuid"], GPU)
        self.assertEqual(job["execution_mode"], "resume")
        self.assertEqual(len(job["attempts_history"]), 1)
        old = self.base / "queue" / mapping["queue_history_directory"]
        self.assertEqual((old / "launcher.log").read_text(), "original failed launcher\n")
        self.assertTrue((old / "STARTED").is_file())
        self.assertFalse((self.job_directory / "STARTED").exists())
        self.assertFalse((self.job_directory / "launcher.log").exists())
        self.assertEqual((self.job_directory / "selected_input.txt").read_text(), str(self.frozen))
        history_archive = self.base / "runs/resume_history" / self.run_id / "resume_01"
        self.assertEqual((history_archive / "old_failure.json").read_text(), "preserved previous archive")
        self.assertFalse(archive.exists())
        self.assertEqual(mapping["completed_stage_prefix"], STAGES[:2])

    def test_resume_is_scheduled_only_on_original_gpu_and_threshold_is_rechecked(self):
        self.resume()
        self.hold.unlink()
        self.assertEqual(self.queue.candidates(), [GPU])
        self.assertIsNone(self.queue.claim(OTHER_GPU))
        self.queue.gpu_query = lambda: f"0,{GPU},24575\n1,{OTHER_GPU},70000\n"
        self.assertEqual(self.queue.candidates(), [])
        self.assertIsNone(self.queue.claim(GPU))
        self.queue.gpu_query = lambda: GPU_CSV
        self.assertEqual(self.queue.claim(GPU), "object_0")
        job = self.queue_state()["jobs"][0]
        self.assertEqual(job["attempts"], 2)
        self.assertEqual(job["gpu_uuid"], GPU)
        self.assertEqual(self.queue.info("object_0", "execution_mode"), "resume")
        self.assertEqual(self.queue.validate_resume("object_0")["completed_stage_prefix"], STAGES[:2])

    def test_hold_and_failed_stopped_job_are_required(self):
        before = self.queue.path.read_bytes()
        self.hold.unlink()
        with self.assertRaisesRegex(ValueError, "HOLD"):
            self.resume()
        self.assertEqual(self.queue.path.read_bytes(), before)
        self.hold.touch()
        for status in ("queued", "running", "success", "cancelled"):
            batch = self.queue_state()
            batch["jobs"][0]["status"] = status
            self.batch.atomic_json(self.queue.path, batch)
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "failed stopped"):
                self.resume()
        self.assertTrue((self.job_directory / "STARTED").exists())

    def test_alive_or_unverifiable_pid_blocks_resume(self):
        for outcome in (None, PermissionError):
            with self.subTest(outcome=outcome), patch.object(self.batch.os, "kill", side_effect=outcome), \
                    self.assertRaisesRegex(ValueError, "alive"):
                self.queue.resume("object_0", "resume_01", "repaired")
        self.assertEqual(self.queue_state()["jobs"][0]["status"], "failed")
        self.assertFalse((self.base / "queue/job_history").exists())

    def test_changed_missing_or_escaping_frozen_input_is_rejected(self):
        original = self.frozen.read_bytes()
        for mode in ("changed", "missing", "wrong_selected_path", "wrong_declared_path"):
            with self.subTest(mode=mode):
                self.frozen.write_bytes(original)
                (self.job_directory / "selected_input.txt").write_text(str(self.frozen))
                self.state["inputs"]["source_image"] = str(self.frozen)
                if mode == "changed": self.frozen.write_bytes(b"changed frozen bytes")
                if mode == "missing": self.frozen.unlink()
                if mode == "wrong_selected_path": (self.job_directory / "selected_input.txt").write_text(str(self.source))
                if mode == "wrong_declared_path": self.state["inputs"]["source_image"] = str(self.source)
                self.save_native()
                with self.assertRaisesRegex(ValueError, "Frozen native input"):
                    self.resume()
        self.assertEqual(self.queue_state()["jobs"][0]["status"], "failed")

    def test_wrong_gpu_binding_and_unsupported_native_state_are_rejected(self):
        self.state["worker_isolation"]["gpu_binding"]["effective_cuda_visible_devices"] = OTHER_GPU
        self.save_native()
        with self.assertRaisesRegex(ValueError, "persisted worker GPU"):
            self.resume()
        self.state["worker_isolation"]["gpu_binding"]["effective_cuda_visible_devices"] = GPU
        for key, value in (("status", "success"), ("runtime_kind", "python_orchestrator"), ("run_id", "another_run")):
            original = self.state[key]
            self.state[key] = value
            self.save_native()
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "incompatible"):
                self.resume()
            self.state[key] = original

    def test_failed_native_stage_halted_terminal_or_missing_artifact_blocks_resume(self):
        baseline = json.loads(json.dumps(self.state))
        self.state["stages"]["omnipart_generate_parts"]["status"] = "failed"
        self.save_native()
        with self.assertRaisesRegex(ValueError, "cannot reopen"):
            self.resume()
        self.state = json.loads(json.dumps(baseline))
        self.state["stage_runtime"] = {"omnipart": {"terminal": {"status": "halted"}}}
        self.save_native()
        with self.assertRaisesRegex(ValueError, "halted stage terminal"):
            self.resume()
        self.state = baseline
        missing = Path(self.state["stages"]["image_cleanup"]["artifacts"]["expected"][0]["path"])
        missing.unlink()
        self.save_native()
        with self.assertRaisesRegex(ValueError, "required upstream artifact"):
            self.resume()

    def test_empty_raw_sam3_is_not_an_acceptable_preserved_prefix(self):
        Path(self.state["paths"]["sam3_raw_metadata_path"]).write_text('{"mask_count":0}')
        with self.assertRaisesRegex(ValueError, "empty raw SAM3"):
            self.resume()

    def test_diagnostic_cleanup_retry_accepts_closed_failed_sessions(self):
        self.state = self.native_state(6, diagnostic_retry=True)
        self.save_native()
        mapping = self.resume()
        self.assertTrue(mapping["diagnostic_operational_retry"])
        self.assertEqual(mapping["completed_stage_prefix"], STAGES[:6])
        self.assertEqual(self.queue_state()["jobs"][0]["run_id"], self.run_id)

    def test_diagnostic_retry_rejects_business_decisions_or_incomplete_cleanup(self):
        self.state = self.native_state(6, diagnostic_retry=True)
        baseline = json.loads(json.dumps(self.state))
        for business in ("accept", "revise", "halt", "recommendation_valid", "business_halt"):
            self.state = json.loads(json.dumps(baseline))
            self.state["diagnostics"]["terminal"]["business_outcome"]["status"] = business
            self.save_native()
            with self.subTest(business=business), self.assertRaisesRegex(ValueError, "without a business recommendation"):
                self.resume()
        self.state = baseline
        self.state["diagnostics"]["terminal"]["operational_outcome"]["cleanup_status"] = "failed"
        self.save_native()
        with self.assertRaisesRegex(ValueError, "without a business recommendation"):
            self.resume()

    def test_diagnostic_retry_rejects_active_state_or_external_session(self):
        self.state = self.native_state(6, diagnostic_retry=True)
        self.state["diagnostic_runtime_sessions"][0]["lifecycle_state"] = "connected"
        self.save_native()
        with self.assertRaisesRegex(ValueError, "ownership is still active"):
            self.resume()
        self.state["diagnostic_runtime_sessions"][0]["lifecycle_state"] = "closed"
        self.save_native()
        ownership = Path(self.state["paths"]["sim_diagnostics_dir"]) / "runtime_ownership.json"
        ownership.write_text('{"diagnostic_runtime_sessions":[{"lifecycle_state":"created"}]}')
        with self.assertRaisesRegex(ValueError, "ownership is still active"):
            self.resume()

    def test_state_drift_after_queueing_blocks_launch_validation(self):
        self.resume()
        self.state["status"] = "running"
        self.save_native()
        with self.assertRaisesRegex(ValueError, "changed after resume"):
            self.queue.validate_resume("object_0")
        self.assertEqual(self.queue_state()["jobs"][0]["status"], "queued")

    def test_queue_save_failure_restores_job_logs_and_previous_archive(self):
        archive = self.base / "runs" / self.run_id
        archive.mkdir(parents=True)
        (archive / "marker").write_text("original archive")
        before = self.queue.path.read_bytes()
        original_write = self.batch.atomic_json
        def fail_at_commit(path, value):
            if Path(path) == self.queue.path:
                raise OSError("synthetic commit failure")
            return original_write(path, value)
        with patch.object(self.batch, "atomic_json", side_effect=fail_at_commit):
            with self.assertRaisesRegex(OSError, "synthetic commit failure"):
                self.resume()
        self.assertEqual(self.queue.path.read_bytes(), before)
        self.assertEqual((self.job_directory / "launcher.log").read_text(), "original failed launcher\n")
        self.assertEqual((archive / "marker").read_text(), "original archive")
        self.assertFalse((self.job_directory / "resume.json").exists())

    def test_multiple_resumes_use_unique_history_and_preserve_attempt_count(self):
        first = self.resume("resume_01")
        self.hold.unlink()
        self.queue.claim(GPU)
        self.queue.bind("object_0", 99999999)
        self.queue.finish("object_0", "failed", "execution_failed")
        self.hold.touch()
        second = self.resume("resume_02")
        self.assertNotEqual(first["queue_history_directory"], second["queue_history_directory"])
        job = self.queue_state()["jobs"][0]
        self.assertEqual(job["attempts"], 2)
        self.assertEqual(len(job["attempts_history"]), 2)
        self.assertEqual(job["resume_id"], "resume_02")

    def test_fresh_retry_after_a_failed_resume_clears_all_resume_metadata(self):
        self.resume()
        self.hold.unlink()
        self.queue.claim(GPU)
        self.queue.bind("object_0", 99999999)
        self.queue.finish("object_0", "failed", "execution_failed")
        self.hold.touch()
        with patch.object(self.batch.os, "kill", side_effect=ProcessLookupError):
            self.queue.retry("object_0", "genesis_object_0_fresh_retry", "new_native_run")
        job = self.queue_state()["jobs"][0]
        self.assertEqual(job["execution_mode"], "fresh")
        self.assertFalse(any(key.startswith("resume_") for key in job))
        self.assertEqual(job["attempts_history"][-1]["execution_mode"], "resume")
        self.hold.unlink()
        self.assertEqual(self.queue.candidates(), [OTHER_GPU, GPU])
        self.assertEqual(self.queue.claim(OTHER_GPU), "object_0")

    def test_shell_is_valid_and_resume_branch_does_not_initialize_or_copy_input(self):
        result = subprocess.run(["bash", "-n", str(self.patched_root / SHELL_RELATIVE)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.patched_root / SHELL_RELATIVE).read_text()
        self.assertIn('MESH_PYTHON="$DIAGGEN_ROOT/.conda/hag4r_mesh/bin/python"', text)
        self.assertIn('batch validate-resume "$JOB_ID"', text)
        branch = text.split('if [[ "$EXECUTION_MODE" == resume ]]; then\n    # The queue verified', 1)[1].split("\nelse\n", 1)[0]
        self.assertNotIn("cp --", branch)
        self.assertNotIn("run_diaggen_pipeline", branch)
        self.assertIn("stage_tool.py", text)
        self.assertIn("completion_rc == 0", text)

    def run_stubbed_resume_shell(self, *, completion_failure=False):
        """Execute the real patched shell using fake external engines, never Codex/GPU."""
        self.resume()
        self.hold.unlink()
        self.assertEqual(self.queue.claim(GPU), "object_0")
        queue_directory = self.base / "queue"
        shutil.copy2(self.patched_root / BATCH_RELATIVE, queue_directory / "batch_control.py")
        shutil.copy2(self.patched_root / SHELL_RELATIVE, queue_directory / "run_one.sh")
        shutil.copy2(WORKSPACE / "sims/diaggen_genesis/queue/support.py", queue_directory / "support.py")
        shim = '''#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  *readiness.py|*check_diaggen_exr.py|*check_diaggen_display.py|*stage_tool.py)
    printf '%s\\n' '{"synthetic_preflight":true}'
    exit 0;;
  *validate_completed_export.py)
    printf '%s\\n' '{"synthetic_completion_check":true}'
    exit "${DIAGGEN_TEST_COMPLETION_RC:-0}";;
  *support.py)
    if [[ "$2" == archive ]]; then
      printf '%s\\n' "archive" >> "$DIAGGEN_TEST_CALLS"
      exit 0
    fi;;
  -m)
    printf '%s\\n' "forbidden_native_initializer" >> "$DIAGGEN_TEST_CALLS"
    exit 77;;
esac
exec PYTHON "$@"
'''.replace("exec PYTHON", "exec " + shlex.quote(sys.executable))
        for environment_name in ("hag4r", "hag4r_mesh", "hag4r_segmentation", "omnipart"):
            path = self.native / ".conda" / environment_name / "bin/python"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(shim)
            path.chmod(0o755)
        xvfb = self.native / ".local/xvfb/usr/bin/Xvfb"
        xvfb.parent.mkdir(parents=True)
        xvfb.write_text("#!/usr/bin/env bash\nprintf '%s\\n' 7 >&3\nexec sleep 30\n")
        xvfb.chmod(0o755)
        environment = dict(os.environ)
        calls = self.workspace / "external_calls.txt"
        environment.update(DIAGGEN_TEST_CALLS=str(calls),
                           DIAGGEN_TEST_COMPLETION_RC="1" if completion_failure else "0")
        # An exported Bash function takes precedence over all executable search
        # paths that the production shell prepends. The real Codex cannot start.
        environment["BASH_FUNC_codex%%"] = '''() { cat > "$DIAGGEN_JOB_QUEUE_DIR/synthetic_codex_prompt.txt"; printf '%s\\n' '{"synthetic_codex":true}'; }'''
        state_before = (self.run_root / "state.json").read_bytes()
        frozen_before = self.frozen.read_bytes()
        result = subprocess.run(["bash", str(queue_directory / "run_one.sh"), "--resume", "object_0"],
                                env=environment, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.run_root / "state.json").read_bytes(), state_before)
        self.assertEqual(self.frozen.read_bytes(), frozen_before)
        self.assertEqual(calls.read_text().splitlines(), ["archive"])
        self.assertFalse((self.job_directory / "initializer.json").exists())
        self.assertFalse((self.job_directory / "STARTED").exists())
        self.assertTrue((self.job_directory / "RESUMED").is_file())
        prompt = (self.job_directory / "synthetic_codex_prompt.txt").read_text()
        self.assertIn("Execution mode is resume", prompt)
        self.assertIn("stage_tool.py TOOL_NAME --input-json", prompt)
        self.assertIn("hag4r_mesh/bin/python", prompt)
        return self.queue_state()["jobs"][0]

    def test_real_resume_shell_reaches_stubbed_codex_without_initializer_or_input_copy(self):
        job = self.run_stubbed_resume_shell()
        self.assertEqual(job["status"], "success")
        self.assertEqual(job["run_id"], self.run_id)

    def test_real_resume_shell_rejects_completion_failure_despite_codex_and_archive_zero(self):
        job = self.run_stubbed_resume_shell(completion_failure=True)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["reason"], "execution_failed")


if __name__ == "__main__":
    unittest.main()
