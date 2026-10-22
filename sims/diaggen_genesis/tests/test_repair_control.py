"""Incident-triggered investigator bookkeeping, never model/pipeline execution."""
import importlib.util
import json
import subprocess
import shlex
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
from datetime import datetime, timezone

QUEUE = Path(__file__).resolve().parents[1] / 'queue'
sys.path.insert(0, str(QUEUE))
SPEC = importlib.util.spec_from_file_location('diaggen_repair_tests', QUEUE / 'repair_control.py')
repair = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repair)


class RepairTests(unittest.TestCase):
    def test_real_cli_parses_the_complete_disabled_diagnostic_transport(self):
        workspace = QUEUE.parents[2]
        python = workspace / 'tools/diaggen/.conda/hag4r/bin/python'
        # No model/service call: validate config using the installed CLI parser.
        configs = []
        for line in (QUEUE / 'run_repair.sh').read_text().splitlines():
            if '-c ' in line and not line.lstrip().startswith('#'):
                tokens = shlex.split(line.rstrip().removesuffix('\\'))
                for index, token in enumerate(tokens):
                    if token == '-c':
                        configs += ['-c', tokens[index + 1].replace('$PYTHON', str(python))]
        result = subprocess.run(['codex', 'mcp', 'list', '--json', *configs],
            check=True, capture_output=True, text=True, timeout=15)
        entry = next(item for item in json.loads(result.stdout) if item['name'] == 'hag4r_genesis_diagnostics')
        self.assertFalse(entry['enabled'])

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.workspace = Path(tmp.name)
        self.q = self.workspace / 'sims/diaggen_genesis/queue'
        self.q.mkdir(parents=True)
        (self.q / 'repair_prompt.md').write_text('Request @REQUEST@ in @WORKSPACE@')
        self.job = {'id': 'dragon', 'run_id': 'dragon_run', 'input': 'inputs/dragon.png',
                    'status': 'failed', 'gpu_uuid': 'GPU-test', 'runner_pid': 99999999,
                    'attempts': 1, 'started_at': '2026-10-22T10:00:00+00:00',
                    'finished_at': '2026-10-22T10:10:00+00:00'}
        self.batch = {'schema_version': 'diaggen-batch-v1', 'policy': {}, 'jobs': [self.job]}
        repair.atomic_json(self.q / 'batch.json', self.batch)
        self.native_path = self.workspace / 'tools/diaggen/outputs/agentic_asset_refinement/dragon_run/state.json'
        self.native = {'status': 'seeded', 'stages': {'genesis_live_diagnostic_loop': {'status': 'pending_retry'}},
                       'diagnostics': {'terminal': {'status': 'retryable'}}}
        repair.atomic_json(self.native_path, self.native)
        self.seconds = 1800000000
        self.observed = {'schema_version': 'diaggen-server-monitor-v1', 'jobs': [
            {'id': 'dragon', 'run_id': 'dragon_run', 'outcome': 'resume_ineligible'}]}
        self.refresh()
        self.control = repair.RepairControl(self.workspace, clock=lambda: self.seconds,
                                            pid_probe=Mock(return_value=False))
        self.control.readiness = Mock(return_value={'status': 'pass'})

    def refresh(self):
        self.observed['updated_at'] = datetime.fromtimestamp(self.seconds, timezone.utc).isoformat()
        repair.atomic_json(self.q / 'monitor_status.json', self.observed)

    def result(self, job_id, **values):
        result = dict(incident_id=job_id, classification='scheduler', outcome='needs_attention',
                      summary='PRIVATE investigation', changed_files=[], checks=['actual check'], requeued_jobs=[])
        result.update(values)
        repair.atomic_json(self.q / 'repair_jobs' / job_id / 'result.json', result)

    def prepare(self, **kwargs):
        return self.control.prepare(runner_pid=99999999, **kwargs)

    def test_healthy_tick_does_not_launch_model_or_hold(self):
        self.job['status'] = 'running'
        repair.atomic_json(self.q / 'batch.json', self.batch)
        self.observed['jobs'][0]['outcome'] = 'running'
        self.refresh()
        self.assertIsNone(self.prepare())
        self.assertFalse((self.q / 'HOLD').exists())
        self.assertFalse((self.q / 'repair_jobs').exists())

    def test_inbox_runtime_failure_triggers_existing_bounded_investigator(self):
        self.observed['jobs'][0]['outcome'] = 'running'
        for inbox in ({'outcome': 'scan_failed', 'error_type': 'TypeError'}, {'runtime_errors': 1}):
            with self.subTest(inbox=inbox):
                self.observed['inbox'] = inbox
                self.refresh()
                self.assertEqual(self.control.incidents({})[0]['kind'], 'image_intake_failed')

    def test_invalid_inbox_image_does_not_launch_repair_model(self):
        self.observed['jobs'][0]['outcome'] = 'running'
        self.observed['inbox'] = {'errors': 1, 'runtime_errors': 0,
                                  'files': [{'outcome': 'invalid_image'}]}
        self.refresh()
        self.assertIsNone(self.prepare())

    def test_new_failure_records_evidence_and_reserves_own_gate(self):
        job_id = self.prepare()
        request = repair.object_file(self.q / 'repair_jobs' / job_id / 'request.json')
        self.assertTrue(request['hold_owned'])
        self.assertEqual(request['incident']['kind'], 'resume_ineligible')
        self.assertIn(job_id, (self.q / 'HOLD').read_text())
        self.assertIn(str(self.workspace), (self.q / 'repair_jobs' / job_id / 'prompt.txt').read_text())

    def test_audit_has_no_gate_or_retry_cost(self):
        job_id = self.prepare(audit=True)
        self.assertFalse((self.q / 'HOLD').exists())
        state = self.control.state()
        self.assertEqual(state['incidents'][repair.digest('read_only_audit')]['attempts'], 0)
        self.result(job_id, classification='no_issue', outcome='healthy')
        self.assertTrue(self.control.finish(job_id, 0)['result_valid'])
        self.control.readiness.assert_not_called()

    def test_manual_hold_and_stop_controls_are_respected(self):
        for name in ('REPAIR_STOP', 'AUTOMATION_STOP', 'STOP', 'HOLD'):
            with self.subTest(name=name):
                path = self.q / name
                path.write_text('human work')
                self.assertIsNone(self.prepare())
                self.assertEqual(path.read_text(), 'human work')
                path.unlink()

    def test_live_repair_prevents_overlap(self):
        self.prepare()
        self.control.pid_probe.return_value = True
        self.assertIsNone(self.prepare())

    def test_own_gate_only_clears_after_certificate_verifies(self):
        job_id = self.prepare()
        self.result(job_id)
        self.control.readiness.side_effect = ValueError('changed source')
        result = self.control.finish(job_id, 0)
        self.assertFalse(result['own_hold_released_after_verification'])
        self.assertTrue((self.q / 'HOLD').exists())
        self.assertEqual(result['outcome'], 'needs_attention')

    def test_replaced_gate_is_never_removed(self):
        job_id = self.prepare()
        (self.q / 'HOLD').write_text('new human gate')
        self.result(job_id, outcome='recovered')
        result = self.control.finish(job_id, 0)
        self.assertEqual((self.q / 'HOLD').read_text(), 'new human gate')
        self.assertEqual(result['outcome'], 'needs_attention')

    def test_successful_verification_releases_owned_gate(self):
        job_id = self.prepare()
        self.result(job_id, outcome='recovered')
        result = self.control.finish(job_id, 0)
        self.assertTrue(result['own_hold_released_after_verification'])
        self.assertFalse((self.q / 'HOLD').exists())
        self.assertIsNone(self.prepare())

    def test_claimed_requeue_requires_observed_queue_change(self):
        job_id = self.prepare()
        self.result(job_id, outcome='repaired_and_requeued', requeued_jobs=['dragon'])
        self.assertEqual(self.control.finish(job_id, 0)['outcome'], 'needs_attention')

    def test_claimed_requeue_requires_a_new_attempt_not_just_running_status(self):
        self.job['status'] = 'running'
        repair.atomic_json(self.q / 'batch.json', self.batch)
        self.observed['jobs'][0]['outcome'] = 'quiet'
        self.refresh()
        job_id = self.prepare()
        self.result(job_id, outcome='repaired_and_requeued', requeued_jobs=['dragon'])
        self.assertEqual(self.control.finish(job_id, 0)['outcome'], 'needs_attention')

    def test_genuine_new_queued_resume_is_verified(self):
        job_id = self.prepare()
        self.job.update(status='queued', resume_id='new_resume')
        repair.atomic_json(self.q / 'batch.json', self.batch)
        self.result(job_id, outcome='repaired_and_requeued', requeued_jobs=['dragon'])
        self.assertEqual(self.control.finish(job_id, 0)['outcome'], 'repaired_and_requeued')

    def test_certificate_is_checked_even_if_worker_removed_its_gate(self):
        job_id = self.prepare()
        (self.q / 'HOLD').unlink()
        self.result(job_id, outcome='recovered')
        self.control.readiness.side_effect = ValueError('stale')
        self.assertEqual(self.control.finish(job_id, 0)['outcome'], 'needs_attention')

    def test_missing_or_invalid_result_records_failure_without_false_success(self):
        job_id = self.prepare()
        result = self.control.finish(job_id, 124)
        self.assertFalse(result['result_valid'])
        self.assertEqual(result['outcome'], 'needs_attention')
        self.assertTrue((self.q / 'repair_jobs' / job_id / 'completion.json').exists())

    def test_results_must_match_current_incident(self):
        job_id = self.prepare()
        self.result(job_id, incident_id='wrong')
        self.assertFalse(self.control.finish(job_id, 0)['result_valid'])
        with self.assertRaises(ValueError):
            self.control.finish(job_id, 0)

    def test_attempt_limit_and_backoff_survive_restart(self):
        job_id = self.prepare()
        self.control.finish(job_id, 1)
        self.assertIsNone(self.prepare())
        self.seconds += 901
        self.refresh()
        again = repair.RepairControl(self.workspace, clock=lambda: self.seconds,
                                     pid_probe=Mock(return_value=False))
        again.readiness = self.control.readiness
        job_id = again.prepare(runner_pid=99999999)
        self.assertIsNotNone(job_id)
        again.finish(job_id, 1)
        self.seconds += 901
        self.refresh()
        self.assertIsNone(again.prepare(runner_pid=99999999))

    def test_verified_pre_model_launch_retry_keeps_failure_and_consumes_next_slot(self):
        first = self.prepare()
        directory = self.q / 'repair_jobs' / first
        (directory / 'events.jsonl').write_text('')
        (directory / 'stderr.log').write_text('Error loading config.toml: invalid transport\nin `mcp_servers.hag4r_genesis_diagnostics`\n\n')
        self.control.finish(first, 1)
        self.assertIsNone(self.prepare())
        second = self.prepare(retry_launch_fix=True)
        request = repair.object_file(self.q / 'repair_jobs' / second / 'request.json')
        self.assertEqual(request['verified_launch_fix_retry_of'], first)
        self.assertTrue((directory / 'completion.json').exists())
        self.assertEqual(self.control.state()['incidents'][request['incident']['signature']]['attempts'], 2)

    def test_launch_retry_cannot_override_a_started_model_or_stale_certificate(self):
        first = self.prepare()
        directory = self.q / 'repair_jobs' / first
        (directory / 'events.jsonl').write_text('{"type":"thread.started"}\n')
        (directory / 'stderr.log').write_text('Error loading config.toml: invalid transport\nin `mcp_servers.hag4r_genesis_diagnostics`\n')
        self.control.finish(first, 1)
        with self.assertRaises(ValueError):
            self.prepare(retry_launch_fix=True)
        (directory / 'events.jsonl').write_text('')
        self.control.readiness.side_effect = ValueError('stale certificate')
        with self.assertRaisesRegex(ValueError, 'stale certificate'):
            self.prepare(retry_launch_fix=True)

    def test_abandoned_repair_retains_evidence_and_same_attempt_budget(self):
        first = self.prepare()
        self.seconds += 901
        self.refresh()
        second = self.prepare()
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second)
        self.assertTrue((self.q / 'repair_jobs' / first / 'abandoned.json').exists())
        request = repair.object_file(self.q / 'repair_jobs' / second / 'request.json')
        self.assertTrue(request['hold_owned'])
        state = self.control.state()
        self.assertEqual(state['incidents'][request['incident']['signature']]['attempts'], 2)

    def test_new_native_halt_is_investigated_for_possible_runtime_defect(self):
        self.observed['jobs'][0]['outcome'] = 'business_halt'
        self.refresh()
        job_id = self.prepare()
        request = repair.object_file(self.q / 'repair_jobs' / job_id / 'request.json')
        self.assertEqual(request['incident']['kind'], 'new_native_halt')
        self.result(job_id, classification='native_business_halt', outcome='needs_attention')
        self.control.finish(job_id, 0)
        self.seconds += 901
        self.refresh()
        self.assertIsNone(self.prepare())

    def test_known_baseline_is_not_retried_but_new_run_is_investigated(self):
        self.job['id'] = 'capybara_plush_toy'
        self.observed['jobs'][0].update(id=self.job['id'], outcome='stage_failed')
        repair.atomic_json(self.q / 'batch.json', self.batch)
        self.refresh()
        original = self.control.baseline()['baseline']
        self.assertIsNone(self.prepare())
        self.job['run_id'] = 'new_run'
        self.observed['jobs'][0]['run_id'] = 'new_run'
        repair.atomic_json(self.q / 'batch.json', self.batch)
        self.refresh()
        self.assertEqual(self.control.baseline()['baseline'], original)
        self.assertIsNotNone(self.prepare())

    def test_missing_stale_invalid_monitor_and_invalid_batch_create_incidents(self):
        path = self.q / 'monitor_status.json'
        path.unlink()
        self.assertEqual(self.control.incidents({})[0]['kind'], 'monitor_missing')
        path.write_text('invalid JSON')
        self.assertEqual(self.control.incidents({})[0]['kind'], 'monitor_invalid')
        self.refresh()
        self.seconds += 241
        self.assertEqual(self.control.incidents({})[0]['kind'], 'monitor_stale')
        self.refresh()
        (self.q / 'batch.json').write_text('invalid JSON')
        self.assertEqual(self.control.incidents({})[0]['kind'], 'queue_ledger_invalid')

    def test_public_status_has_only_enums_and_no_private_summary(self):
        job_id = self.prepare()
        self.result(job_id)
        self.control.finish(job_id, 0)
        public = (self.q / 'repair_status.json').read_text()
        self.assertNotIn('PRIVATE', public)
        self.assertNotIn(str(self.workspace), public)

    def test_publisher_filters_private_payload_and_ignores_heartbeat_changes(self):
        spec = importlib.util.spec_from_file_location('repair_publisher_tests', QUEUE / 'publish_progress.py')
        publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publisher)
        value = {'schema_version': 'diaggen-repair-status-v1', 'enabled': True,
                 'updated_at': '2026-10-22T20:00:00+08:00', 'status': 'running',
                 'incident': 'new_native_halt', 'classification': 'pipeline_runtime',
                 'outcome': 'needs_attention', 'summary': 'PRIVATE credentials', 'path': str(self.workspace)}
        repair.atomic_json(self.q / 'repair_status.json', value)
        first = publisher.repair_snapshot(self.q)
        self.assertNotIn('PRIVATE', json.dumps(first))
        self.assertNotIn(str(self.workspace), json.dumps(first))
        self.assertEqual(first['incident'], 'new_native_halt')
        value.update(updated_at='2026-10-22T20:01:00+08:00')
        repair.atomic_json(self.q / 'repair_status.json', value)
        self.assertEqual(publisher.semantic_signature(first), publisher.semantic_signature(publisher.repair_snapshot(self.q)))


if __name__ == '__main__':
    unittest.main()
