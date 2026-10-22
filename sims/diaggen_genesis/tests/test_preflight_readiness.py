import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / "preflight/readiness.py"
SPEC = importlib.util.spec_from_file_location("preflight_readiness", MODULE)
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        for relative in readiness.REQUIRED_SOURCES:
            path = self.workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture source")
        support = self.workspace / "tools/diaggen_support/helper.py"
        support.parent.mkdir(parents=True)
        support.write_text("fixture support")
        jobs = []
        for index in range(9):
            path = self.workspace / readiness.BASE / f"inputs/fixture {index}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"input {index}".encode())
            jobs.append({"id": f"job_{index}", "input": f"inputs/fixture {index}.png",
                         "input_sha256": readiness.sha256(path)})
        (self.workspace / readiness.BASE / "batch_plan.json").write_text(json.dumps({"jobs": jobs}))
        self.report = self.workspace / "full-report.json"
        names = ['host/fixture', 'mesh/fixture', 'genesis/fixture', 'omnipart/fixture',
                 'namespace_unittest_suite', 'preflight_negative_controls', 'source_and_test_inventory_unchanged']
        self.report.write_text(json.dumps({'schema_version': 'diaggen-full-runtime-preflight-v1',
            'simulator': 'Genesis', 'overall_status': 'pass',
            'checks': [{'name': name, 'status': 'PASS'} for name in names],
            'counts': {'pass': len(names), 'fail': 0, 'skip': 0}}))
        self.certificate = self.workspace / "private/certificate.json"
        self.inventory = {"inventory_sha256": "fixture", "python_path": ["fixture"]}
        self.env_patch = patch.object(readiness, "environment_inventory", return_value=self.inventory)
        self.binary_patch = patch.object(readiness, "binary_inventory", return_value={"xvfb": "fixture"})
        self.environment = self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.binaries = self.binary_patch.start()
        self.addCleanup(self.binary_patch.stop)
        self.native_patch = patch.object(readiness, "native_tracked_sources", return_value=[
            readiness.NATIVE / "hag4r/tools/volumetric_meshing.py"])
        self.native_sources = self.native_patch.start()
        self.addCleanup(self.native_patch.stop)

    def certify(self):
        return readiness.certify(self.workspace, self.report, self.certificate)

    def verify(self):
        return readiness.verify(self.workspace, self.certificate)

    def test_full_pass_certifies_and_verifies_five_inventory_snapshots(self):
        self.assertEqual(self.certify()["status"], "pass")
        self.assertEqual(self.environment.call_count, 5)
        self.assertEqual(self.verify()["status"], "pass")
        certificate = json.loads(self.certificate.read_text())
        self.assertEqual(len(certificate["fingerprint"]["inputs"]), 9)

    def test_empty_failed_skipped_and_partial_reports_are_rejected(self):
        for report in ({"overall_status": "pass", "checks": []},
                       {"overall_status": "fail", "checks": [{"status": "pass"}]},
                       {"overall_status": "pass", "checks": [{"status": "skip"}]},
                       {"overall_status": "pass", "checks": [{"status": "pass"}, {}]}):
            with self.subTest(report=report):
                self.report.write_text(json.dumps(report))
                with self.assertRaises(ValueError):
                    self.certify()
        self.assertFalse(self.certificate.exists())

    def test_missing_report_and_certificate_fail_closed(self):
        with self.assertRaises(FileNotFoundError):
            self.verify()
        self.report.unlink()
        with self.assertRaises(FileNotFoundError):
            self.certify()

    def test_cpu_only_report_cannot_certify_or_replace_full_runtime_gate(self):
        value = json.loads(self.report.read_text())
        value['schema_version'] = 'diaggen-orchestration-preflight-v1'
        self.report.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'full runtime'):
            self.certify()
        self.assertFalse(self.certificate.exists())

    def test_full_summary_must_cover_all_runtime_families_and_cpu_checks(self):
        original = json.loads(self.report.read_text())
        for missing in ('genesis/fixture', 'namespace_unittest_suite'):
            value = json.loads(json.dumps(original))
            value['checks'] = [x for x in value['checks'] if x['name'] != missing]
            value['counts']['pass'] = len(value['checks'])
            self.report.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'missing required'):
                self.certify()

    def test_full_summary_rejects_duplicate_names_and_incorrect_totals(self):
        value = json.loads(self.report.read_text())
        value['counts']['pass'] += 1
        self.report.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'counts'):
            self.certify()
        value['counts']['pass'] -= 1
        value['checks'][1]['name'] = value['checks'][0]['name']
        self.report.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'distinct'):
            self.certify()

    def test_changed_report_fails_verification(self):
        self.certify()
        self.report.write_text(self.report.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "report changed"):
            self.verify()

    def test_changed_and_missing_source_fail_verification(self):
        source = self.workspace / readiness.BASE / "queue/run_one.sh"
        self.certify()
        source.write_text("changed after test")
        with self.assertRaisesRegex(ValueError, "Runtime changed"):
            self.verify()
        source.unlink()
        with self.assertRaisesRegex(ValueError, "Required file is absent"):
            self.verify()

    def test_added_helper_and_changed_inventory_fail_verification(self):
        self.certify()
        self.environment.return_value = {"inventory_sha256": "changed"}
        with self.assertRaisesRegex(ValueError, "Runtime changed"):
            self.verify()
        self.environment.return_value = self.inventory
        (self.workspace / "tools/diaggen_support/new.patch").write_text("new patch")
        with self.assertRaisesRegex(ValueError, "Runtime changed"):
            self.verify()

    def test_changed_input_rejected_against_plan(self):
        self.certify()
        (self.workspace / readiness.BASE / "inputs/fixture 1.png").write_bytes(b"replacement")
        with self.assertRaisesRegex(ValueError, "input hash mismatch"):
            self.verify()

    def test_new_native_cuda_source_invalidates_certificate(self):
        self.certify()
        relative = readiness.NATIVE / "test_kernel.cu"
        (self.workspace / relative).write_text("new native CUDA implementation")
        self.native_sources.return_value = self.native_sources.return_value + [relative]
        with self.assertRaisesRegex(ValueError, "Runtime changed"):
            self.verify()

    def test_changed_certificate_status_rejected(self):
        self.certify()
        payload = json.loads(self.certificate.read_text())
        payload["overall_status"] = "skip"
        self.certificate.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "Invalid certificate"):
            self.verify()

    def test_missing_environment_and_changed_binary_fail_closed(self):
        self.certify()
        self.environment.side_effect = FileNotFoundError("missing isolated Python")
        with self.assertRaises(FileNotFoundError):
            self.verify()
        self.environment.side_effect = None
        self.binaries.return_value = {"xvfb": "changed after test"}
        with self.assertRaisesRegex(ValueError, "Runtime changed"):
            self.verify()

    def test_nonobject_report_and_certificate_are_rejected(self):
        self.report.write_text("[]")
        with self.assertRaisesRegex(ValueError, "report must be an object"):
            self.certify()
        self.certificate.parent.mkdir(parents=True)
        self.certificate.write_text("[]")
        with self.assertRaisesRegex(ValueError, "Invalid certificate"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
