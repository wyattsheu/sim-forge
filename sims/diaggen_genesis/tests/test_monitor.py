"""Watchdog recovery policy tests: no models, GPUs or real tmux sessions."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

QUEUE = Path(__file__).resolve().parents[1] / 'queue'
sys.path.insert(0, str(QUEUE))
SPEC = importlib.util.spec_from_file_location('diaggen_server_monitor', QUEUE / 'monitor.py')
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


class MonitorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.directory = self.workspace / 'sims/diaggen_genesis/queue'
        self.directory.mkdir(parents=True)
        self.job = {'id': 'example', 'run_id': 'example_run', 'input': 'inputs/example.png',
                    'status': 'failed', 'gpu_uuid': 'GPU-test', 'runner_pid': 99999999,
                    'attempts': 1, 'started_at': '2000-01-01T00:00:00+00:00',
                    'finished_at': '2000-01-01T01:00:00+00:00'}
        self.batch = {'schema_version': 'diaggen-batch-v1', 'policy': {}, 'jobs': [self.job]}
        monitor.atomic_json(self.directory / 'batch.json', self.batch)
        self.run = self.workspace / 'tools/diaggen/outputs/agentic_asset_refinement/example_run'
        self.native = {'status': 'seeded', 'stages': {'image_cleanup': {'status': 'success'}},
                       'diagnostics': {'terminal': None}}
        monitor.atomic_json(self.run / 'state.json', self.native)
        self.proc = Mock(return_value=[])
        self.pid = Mock(return_value=False)
        self.m = monitor.Monitor(self.workspace, clock=lambda: 2000000000,
                                 process_probe=self.proc, pid_probe=self.pid)
        self.m.readiness = Mock()
        self.m.ensure_session = Mock(return_value='running')
        self.m.queue.resume = Mock()
        self.m.recover_export = Mock()

    def test_resume_calls_existing_admission_under_own_hold_preserving_native(self):
        before = (self.run / 'state.json').read_bytes()
        def resume(job, resume_id, reason):
            self.assertEqual(job, 'example')
            self.assertTrue(resume_id.startswith('scheduled_'))
            self.assertEqual(reason, 'scheduled_operational_resume')
            self.assertTrue((self.directory / 'HOLD').exists())
        self.m.queue.resume.side_effect = resume
        self.assertEqual(self.m.observe_job(self.job), 'resumed')
        self.assertFalse((self.directory / 'HOLD').exists())
        self.assertEqual(before, (self.run / 'state.json').read_bytes())
        self.assertEqual(json.loads((self.directory / 'automation_state.json').read_text())['jobs']['example:example_run']['attempts'], 1)

    def test_business_recommendation_and_halt_never_resume(self):
        for terminal in ({'status': 'halted'}, {'business_outcome': {'status': 'recommendation_valid'}},
                         {'business_outcome': {'status': 'business_halt'}}):
            with self.subTest(terminal=terminal):
                self.native['diagnostics']['terminal'] = terminal
                monitor.atomic_json(self.run / 'state.json', self.native)
                self.assertEqual(self.m.observe_job(self.job), 'business_halt')
        self.m.queue.resume.assert_not_called()
        self.m.recover_export.assert_not_called()

    def test_failed_native_stage_is_not_reopened(self):
        self.proc.return_value = None
        self.native['stages']['image_cleanup']['status'] = 'failed'
        monitor.atomic_json(self.run / 'state.json', self.native)
        self.assertEqual(self.m.observe_job(self.job), 'stage_failed')
        self.m.queue.resume.assert_not_called()
        self.proc.assert_not_called()

    def test_live_runner_or_descendant_blocks_recovery(self):
        self.pid.return_value = True
        self.assertEqual(self.m.observe_job(self.job), 'quiet')
        self.proc.assert_not_called()
        self.pid.return_value = False
        for owners, result in (([1234], 'waiting_cleanup'), (None, 'process_inspection_unavailable')):
            self.proc.return_value = owners
            self.assertEqual(self.m.observe_job(self.job), result)
        self.m.queue.resume.assert_not_called()

    def test_unknown_runner_requires_review(self):
        self.job['runner_pid'] = None
        self.assertEqual(self.m.observe_job(self.job), 'unbound_worker_review')
        self.m.queue.resume.assert_not_called()

    def test_manual_hold_is_preserved(self):
        (self.directory / 'HOLD').write_text('manual repair')
        self.assertEqual(self.m.observe_job(self.job), 'hold')
        self.assertEqual((self.directory / 'HOLD').read_text(), 'manual repair')
        self.m.queue.resume.assert_not_called()

    def test_hold_replaced_during_recovery_is_not_removed(self):
        def resume(*args):
            (self.directory / 'HOLD').write_text('new manual hold')
        self.m.queue.resume.side_effect = resume
        self.assertEqual(self.m.observe_job(self.job), 'resumed')
        self.assertEqual((self.directory / 'HOLD').read_text(), 'new manual hold')

    def test_admission_rejection_is_cached_without_leaking_exception(self):
        self.m.queue.resume.side_effect = ValueError('native admission rejected PRIVATE')
        self.assertEqual(self.m.observe_job(self.job), 'resume_ineligible')
        self.assertFalse((self.directory / 'HOLD').exists())
        self.assertEqual(self.m.observe_job(self.job), 'resume_ineligible')
        self.m.queue.resume.assert_called_once()
        self.assertNotIn('PRIVATE', (self.directory / 'automation_state.json').read_text())

    def test_preflight_failure_does_not_consume_budget_or_launch(self):
        self.m.readiness.side_effect = ValueError('stale')
        for _ in range(3):
            self.assertEqual(self.m.observe_job(self.job), 'preflight_failed')
        self.assertEqual(self.m.memory['jobs']['example:example_run']['attempts'], 0)
        self.m.queue.resume.assert_not_called()

    def test_budget_and_backoff_survive_new_monitor_process(self):
        self.assertEqual(self.m.observe_job(self.job), 'resumed')
        again = monitor.Monitor(self.workspace, clock=lambda: 2000000001,
                                process_probe=self.proc, pid_probe=self.pid)
        again.readiness = Mock()
        again.queue.resume = Mock()
        self.assertEqual(again.observe_job(self.job), 'retry_backoff')
        again.clock = lambda: 2000000301
        self.assertEqual(again.observe_job(self.job), 'resumed')
        again.clock = lambda: 2000000900
        self.assertEqual(again.observe_job(self.job), 'retry_limit')
        again.queue.resume.assert_called_once()

    def test_native_success_uses_validated_export_recovery(self):
        self.native['status'] = 'success'
        monitor.atomic_json(self.run / 'state.json', self.native)
        self.assertEqual(self.m.observe_job(self.job), 'export_recovered')
        self.m.recover_export.assert_called_once_with(self.job)
        self.m.queue.resume.assert_not_called()

    def test_invalid_export_is_not_reported_completed(self):
        self.native['status'] = 'success'
        monitor.atomic_json(self.run / 'state.json', self.native)
        self.m.recover_export.side_effect = ValueError('invalid')
        self.assertEqual(self.m.observe_job(self.job), 'export_validation_failed')
        self.assertEqual(self.m.observe_job(self.job), 'export_validation_failed')
        self.m.recover_export.assert_called_once()

    def test_dead_worker_preserves_prior_queue_job_and_native(self):
        self.job.update(status='running', finished_at=None)
        monitor.atomic_json(self.directory / 'batch.json', self.batch)
        before = (self.run / 'state.json').read_bytes()
        self.m.queue.resume.side_effect = ValueError('not admissible')
        self.assertEqual(self.m.observe_job(self.job), 'resume_ineligible')
        current = json.loads((self.directory / 'batch.json').read_text())['jobs'][0]
        self.assertEqual(current['status'], 'failed')
        self.assertEqual(current['reason'], 'automation_worker_disappeared')
        evidence = list((self.directory / 'automation_history/example').glob('*.json'))
        self.assertEqual(len(evidence), 1)
        self.assertEqual(json.loads(evidence[0].read_text()), self.job)
        self.assertEqual(before, (self.run / 'state.json').read_bytes())

    def test_stop_controls_disable_recovery(self):
        (self.directory / 'STOP').touch()
        self.assertEqual(self.m.tick()['jobs'][0]['outcome'], 'queue_stopped')
        self.m.queue.resume.assert_not_called()
        self.m.ensure_session.assert_called_once_with('diaggen-github-progress', 'publish_progress.sh')
        self.m.ensure_session.reset_mock()
        (self.directory / 'AUTOMATION_STOP').touch()
        self.assertFalse(self.m.tick()['enabled'])
        self.m.ensure_session.assert_not_called()

    def test_tick_restores_queue_and_publisher(self):
        self.job['status'] = 'queued'
        monitor.atomic_json(self.directory / 'batch.json', self.batch)
        result = self.m.tick()
        self.assertEqual(result['jobs'][0]['outcome'], 'queued')
        self.m.ensure_session.assert_any_call('diaggen-genesis-wait', 'wait_and_run.sh')
        self.m.ensure_session.assert_any_call('diaggen-github-progress', 'publish_progress.sh')
        self.m.queue.resume.assert_not_called()

    def test_ensure_session_restarts_only_named_service(self):
        with patch.object(monitor.subprocess, 'run') as run:
            run.return_value.returncode = 1
            self.assertEqual(monitor.Monitor.ensure_session(self.m, 'diaggen-genesis-wait', 'wait_and_run.sh'), 'restarted')
        self.assertEqual(run.call_args_list[1].args[0], ['tmux', 'new-session', '-d', '-s', 'diaggen-genesis-wait', 'bash', str(self.directory / 'wait_and_run.sh')])

    def test_real_queue_admission_archives_history_and_keeps_gpu_and_native(self):
        native_root = self.workspace / 'tools/diaggen'
        frozen = native_root / 'outputs/inputs/example_run.png'
        frozen.parent.mkdir(parents=True)
        frozen.write_bytes(b'original input')
        source = self.workspace / 'sims/diaggen_genesis/inputs/example.png'
        source.parent.mkdir(parents=True)
        source.write_bytes(frozen.read_bytes())
        gpu = 'GPU-ef92f209-a96e-e42c-a1c9-96e2f1db7e55'
        self.job.update(gpu_uuid=gpu, input_sha256=hashlib.sha256(frozen.read_bytes()).hexdigest())
        monitor.atomic_json(self.directory / 'batch.json', self.batch)
        job_dir = self.directory / 'jobs/example'
        job_dir.mkdir(parents=True)
        for name, value in {'selected_input.txt': str(frozen), 'original_input.txt': str(source),
                            'selected_gpu.txt': gpu, 'launcher.log': 'old failed attempt'}.items():
            (job_dir / name).write_text(value)
        stages = ['image_cleanup', 'sam3_omnipart_2d_segmentation', 'omnipart_generate_parts',
                  'hag4r_gpt_staged_material_inference', 'hag4r_assign_params_to_prims',
                  'hag4r_combined_to_monolithic', 'genesis_live_diagnostic_loop',
                  'hag4r_post_mesh_texture', 'hag4r_final_export_bundle']
        artifact = self.run / 'revisions/revision_0000/cleanup.png'
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b'completed upstream output')
        self.native.update(schema_version='2026-07-skill-suite-runtime-state-v2',
                           run_id=self.job['run_id'], run_root=str(self.run), repo_root=str(native_root),
                           run_mode='full_image', runtime_kind='codex_skill',
                           inputs={'source_image': str(frozen)}, paths={'source_image': str(frozen)},
                           planned_global_stage_sequence=stages, completed_global_stage_sequence=stages[:1],
                           stage_runtime={}, diagnostics={'enabled': True},
                           worker_isolation={'gpu_binding': {'effective_cuda_visible_devices': gpu}})
        self.native['stages'] = {s: {'status': 'pending', 'ok': False} for s in stages}
        self.native['stages']['image_cleanup'] = {'status': 'success', 'ok': True,
            'artifacts': {'expected': [{'path': str(artifact), 'required': True}]}}
        monitor.atomic_json(self.run / 'state.json', self.native)
        before = (self.run / 'state.json').read_bytes()
        # Exercise the actual existing guarded queue method, not a replacement.
        self.m.queue.resume = monitor.Queue.resume.__get__(self.m.queue)
        self.assertEqual(self.m.observe_job(self.job), 'resumed')
        current = json.loads((self.directory / 'batch.json').read_text())['jobs'][0]
        self.assertEqual(current['status'], 'queued')
        self.assertEqual(current['resume_gpu_uuid'], gpu)
        self.assertEqual(current['run_id'], self.job['run_id'])
        self.assertEqual(len(current['attempts_history']), 1)
        self.assertEqual(before, (self.run / 'state.json').read_bytes())
        self.assertFalse((self.directory / 'HOLD').exists())
        histories = list((self.directory / 'job_history/example').glob('*/launcher.log'))
        self.assertEqual(histories[0].read_text(), 'old failed attempt')


class MonitorPrivacyTests(unittest.TestCase):
    def test_profiler_exclusion_requires_exact_module_pid_interpreter_and_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'diaggen'
            run = root / 'outputs/agentic_asset_refinement/test_run'
            lock = run / 'profiling/resource_monitor.lock'
            lock.parent.mkdir(parents=True)
            lock.write_text('1234\n')
            python = root / '.conda/hag4r/bin/python'
            python.parent.mkdir(parents=True)
            python.symlink_to(sys.executable)
            entry = Path(directory) / 'proc/1234'
            entry.mkdir(parents=True)
            (entry / 'exe').symlink_to(sys.executable)
            (entry / 'cwd').symlink_to(root)
            args = [str(python).encode(), b'-m', b'hag4r.agentic.runtime_profiler',
                    b'monitor', b'--run-root', str(run).encode(), b'']
            self.assertTrue(monitor.native_resource_profiler(entry, args, run))
            self.assertFalse(monitor.native_resource_profiler(entry, args[:-1] + [b'--other-work'], run))
            self.assertFalse(monitor.native_resource_profiler(entry, args[:2] + [b'hag4r.agentic.diagnostic_mcp_server'] + args[3:], run))
            lock.write_text('5678\n')
            self.assertFalse(monitor.native_resource_profiler(entry, args, run))
            lock.write_text('1234\n')
            (entry / 'cwd').unlink()
            (entry / 'cwd').symlink_to(Path(directory))
            self.assertFalse(monitor.native_resource_profiler(entry, args, run))
            (entry / 'cwd').unlink()
            (entry / 'cwd').symlink_to(root)
            (entry / 'exe').unlink()
            (entry / 'exe').symlink_to('/bin/false')
            self.assertFalse(monitor.native_resource_profiler(entry, args, run))

    def test_real_orphan_scan_finds_only_its_owned_test_process(self):
        run_id = 'watchdog_test_' + str(os.getpid())
        environment = dict(os.environ, DIAGGEN_QUEUE_RUN_ID=run_id)
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], env=environment)
        try:
            self.assertIn(child.pid, monitor.run_processes(run_id, Path('/nonexistent') / run_id))
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_public_monitor_ignores_secrets_unmatched_runs_and_heartbeat_changes(self):
        spec = importlib.util.spec_from_file_location('monitor_publisher_tests', QUEUE / 'publish_progress.py')
        publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publisher)
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory)
            report = {'schema_version': 'diaggen-server-monitor-v1', 'enabled': True,
                      'updated_at': '2026-10-22T19:00:00+08:00', 'PRIVATE': 'PRIVATE',
                      'jobs': [{'id': 'example', 'run_id': 'current', 'outcome': 'business_halt', 'token': 'PRIVATE'},
                               {'id': 'example', 'run_id': 'old', 'outcome': 'PRIVATE'}]}
            monitor.atomic_json(queue / 'monitor_status.json', report)
            first = publisher.monitor_snapshot(queue, [{'id': 'example', 'run_id': 'current'}])
            self.assertNotIn('PRIVATE', json.dumps(first))
            self.assertEqual(len(first['jobs']), 1)
            self.assertEqual(first['jobs'][0]['outcome'], 'business_halt')
            report['updated_at'] = '2026-10-22T19:01:00+08:00'
            monitor.atomic_json(queue / 'monitor_status.json', report)
            second = publisher.monitor_snapshot(queue, [{'id': 'example', 'run_id': 'current'}])
            self.assertEqual(publisher.semantic_signature(first), publisher.semantic_signature(second))


if __name__ == '__main__':
    unittest.main()
