"""Real image admission/queue transitions; no models, services or GPUs launched."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

QUEUE = Path(__file__).resolve().parents[1] / 'queue'
sys.path.insert(0, str(QUEUE))
import batch_control
import client
import image_intake
import monitor


class IntakeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.base = self.workspace / 'sims/diaggen_genesis'
        self.base.mkdir(parents=True)
        (self.base / 'batch_plan.json').write_text(json.dumps({
            'schema_version': 'diaggen-batch-plan-v1', 'policy': {}, 'jobs': []}))
        self.queue = batch_control.Queue(self.base, gpu_query=lambda: '0,GPU-fixture,90000\n')
        self.queue.init()
        self.source = self.workspace / '一般圖片 with spaces.png'
        Image.new('RGB', (24, 16), 'blue').save(self.source)
        self.intake = image_intake.Intake(self.base)

    def jobs(self):
        return json.loads(self.queue.path.read_text())['jobs']

    def test_submit_copies_exact_bytes_and_claims_in_existing_queue(self):
        result = self.intake.submit([self.source])[0]
        self.assertFalse(result['duplicate'])
        job = self.jobs()[0]
        frozen = self.base / job['input']
        self.assertEqual(frozen.read_bytes(), self.source.read_bytes())
        self.assertEqual(frozen.stat().st_mode & 0o222, 0)
        self.assertEqual(job['submission']['width'], 24)
        self.assertEqual(self.queue.claim('GPU-fixture'), result['id'])
        self.assertTrue(result['results_directory'].startswith(str(self.base / 'runs')))

    def test_changed_original_never_changes_admitted_image(self):
        self.intake.submit([self.source])
        admitted = (self.base / self.jobs()[0]['input']).read_bytes()
        Image.new('RGB', (9, 9), 'red').save(self.source)
        self.assertEqual((self.base / self.jobs()[0]['input']).read_bytes(), admitted)
        self.intake.submit([self.source])
        self.assertEqual(len(self.jobs()), 2)

    def test_identical_bytes_deduplicate_names_and_repeated_calls(self):
        other = self.workspace / 'another name.png'
        shutil.copyfile(self.source, other)
        results = self.intake.submit([self.source, other])
        self.assertEqual([r['duplicate'] for r in results], [False, True])
        self.assertTrue(self.intake.submit([other])[0]['duplicate'])
        self.assertEqual(len(self.jobs()), 1)

    def test_failed_duplicate_preserves_native_history_and_attempts(self):
        result = self.intake.submit([self.source])[0]
        self.queue.claim('GPU-fixture')
        self.queue.finish(result['id'], 'failed', 'test_failure')
        before = self.jobs()
        self.assertEqual(self.intake.submit([self.source])[0]['status'], 'failed')
        self.assertEqual(self.jobs(), before)

    def test_concurrent_submissions_admit_only_one_job(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(lambda _: self.intake.submit([self.source])[0], range(4)))
        self.assertEqual(sum(not item['duplicate'] for item in values), 1)
        self.assertEqual(len(self.jobs()), 1)

    def test_invalid_second_image_admits_nothing(self):
        bad = self.workspace / 'broken.jpg'
        bad.write_bytes(b'not an image')
        before = self.queue.path.read_bytes()
        with self.assertRaises(OSError):
            self.intake.submit([self.source, bad])
        self.assertEqual(self.queue.path.read_bytes(), before)
        self.assertFalse((self.base / 'inputs/submissions').exists())

    def test_truncated_jpeg_rejected(self):
        path = self.workspace / 'broken.jpg'
        Image.new('RGB', (120, 120)).save(path)
        path.write_bytes(path.read_bytes()[:100])
        with self.assertRaises(OSError):
            self.intake.submit([path])
        self.assertEqual(self.jobs(), [])

    def test_symlink_and_non_images_rejected(self):
        link = self.workspace / 'link.png'
        link.symlink_to(self.source)
        with self.assertRaises(OSError):
            self.intake.submit([link])
        with self.assertRaises(ValueError):
            self.intake.submit([self.workspace / 'README.txt'])
        self.assertEqual(self.jobs(), [])

    def test_non_regular_file_does_not_block_on_read(self):
        fifo = self.workspace / 'pipe.png'
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            self.intake.submit([fifo])

    def test_animated_image_rejected(self):
        path = self.workspace / 'animated.png'
        Image.new('RGB', (20, 20), 'red').save(path, save_all=True,
            append_images=[Image.new('RGB', (20, 20), 'blue')])
        with self.assertRaises(ValueError):
            self.intake.submit([path])

    def test_suffix_is_canonicalized_without_reencoding(self):
        path = self.workspace / 'actually_jpeg.png'
        Image.new('RGB', (8, 8)).save(path, format='JPEG')
        self.intake.submit([path])
        self.assertTrue(self.jobs()[0]['input'].endswith('.jpg'))
        self.assertEqual((self.base / self.jobs()[0]['input']).read_bytes(), path.read_bytes())

    def test_dry_run_does_not_write_queue_or_inputs(self):
        before = self.queue.path.read_bytes()
        self.assertFalse(self.intake.submit([self.source], dry_run=True)[0]['duplicate'])
        self.assertEqual(self.queue.path.read_bytes(), before)
        self.assertFalse((self.base / 'inputs').exists())

    def test_native_version_budget_can_be_selected_without_changing_duplicate_jobs(self):
        self.intake.submit([self.source], diagnostic_runs=6)
        self.assertEqual(self.jobs()[0]['sim_diagnostics_max_runs'], 6)
        self.intake.submit([self.source], diagnostic_runs=10)
        self.assertEqual(self.jobs()[0]['sim_diagnostics_max_runs'], 6)
        with self.assertRaises(ValueError):
            self.intake.submit([self.source], diagnostic_runs=0)

    def test_batch_limit_rejects_whole_invocation(self):
        with patch.object(image_intake, 'MAX_JOBS', 0):
            with self.assertRaisesRegex(ValueError, 'limit'):
                self.intake.submit([self.source])
        self.assertEqual(self.jobs(), [])

    def test_directory_and_recursive_collection(self):
        directory = self.workspace / 'folder'
        (directory / 'nested').mkdir(parents=True)
        shutil.copyfile(self.source, directory / 'one.PNG')
        Image.new('RGB', (5, 5), 'red').save(directory / 'nested/two.jpg')
        (directory / 'README.txt').write_text('ignored')
        self.assertEqual(len(self.intake.submit([directory], dry_run=True)), 1)
        self.assertEqual(len(self.intake.submit([directory], recursive=True)), 2)

    def test_upload_change_between_check_and_copy_admits_nothing(self):
        inspect = image_intake.inspect_image
        calls = []
        def changing(path):
            calls.append(path)
            if len(calls) == 2:
                Image.new('RGB', (7, 7), 'red').save(path)
            return inspect(path)
        with patch.object(image_intake, 'inspect_image', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'changed'):
                self.intake.submit([self.source])
        self.assertEqual(self.jobs(), [])

    def test_frozen_input_tamper_prevents_native_initialization(self):
        result = self.intake.submit([self.source])[0]
        self.queue.claim('GPU-fixture')
        admitted = self.base / self.jobs()[0]['input']
        admitted.chmod(0o644)
        Image.new('RGB', (9, 9), 'red').save(admitted)
        destination = self.workspace / 'tools/diaggen/outputs/inputs' / (result['run_id'] + '.png')
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            self.intake.freeze(result['id'], destination)
        self.assertFalse(destination.exists())

    def test_freeze_requires_claim_and_exact_native_destination(self):
        result = self.intake.submit([self.source])[0]
        destination = self.workspace / 'tools/diaggen/outputs/inputs' / (result['run_id'] + '.png')
        with self.assertRaisesRegex(ValueError, 'claimed'):
            self.intake.freeze(result['id'], destination)
        self.queue.claim('GPU-fixture')
        with self.assertRaisesRegex(ValueError, 'destination'):
            self.intake.freeze(result['id'], self.workspace / 'elsewhere.png')
        self.intake.freeze(result['id'], destination)
        self.assertEqual(destination.read_bytes(), self.source.read_bytes())
        self.intake.freeze(result['id'], destination)  # Same bytes are idempotent.
        destination.chmod(0o644)
        destination.write_bytes(b'other')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.intake.freeze(result['id'], destination)

    def test_inbox_waits_for_two_stable_scans_and_keeps_original(self):
        inbox = self.base / 'inbox'
        inbox.mkdir()
        path = inbox / self.source.name
        shutil.copyfile(self.source, path)
        clock = [1000]
        intake = image_intake.Intake(self.base, clock=lambda: clock[0])
        self.assertEqual(intake.scan_inbox()['files'][0]['outcome'], 'settling')
        clock[0] += 60
        self.assertEqual(intake.scan_inbox()['submitted'], 1)
        self.assertTrue(path.exists())
        self.assertEqual(intake.scan_inbox()['submitted'], 0)
        self.assertEqual(len(self.jobs()), 1)

    def test_changing_upload_restarts_settle_window(self):
        inbox = self.base / 'inbox'
        inbox.mkdir()
        path = inbox / 'upload.png'
        shutil.copyfile(self.source, path)
        clock = [1000]
        intake = image_intake.Intake(self.base, clock=lambda: clock[0])
        intake.scan_inbox()
        Image.new('RGB', (33, 33)).save(path)
        clock[0] += 60
        self.assertEqual(intake.scan_inbox()['files'][0]['outcome'], 'settling')
        self.assertEqual(self.jobs(), [])
        clock[0] += 60
        self.assertEqual(intake.scan_inbox()['submitted'], 1)

    def test_bad_inbox_image_does_not_block_good_image(self):
        inbox = self.base / 'inbox'
        inbox.mkdir()
        shutil.copyfile(self.source, inbox / 'good.png')
        (inbox / 'bad.png').write_bytes(b'incomplete')
        (inbox / 'in_progress.part').write_bytes(b'incomplete')
        clock = [1000]
        intake = image_intake.Intake(self.base, clock=lambda: clock[0])
        intake.scan_inbox()
        clock[0] += 60
        result = intake.scan_inbox()
        self.assertEqual(result['submitted'], 1)
        self.assertEqual(result['errors'], 1)
        self.assertEqual(result['runtime_errors'], 0)

    def test_inbox_runtime_bug_is_reported_for_fault_supervision(self):
        inbox = self.base / 'inbox'
        inbox.mkdir()
        shutil.copyfile(self.source, inbox / 'good.png')
        clock = [1000]
        intake = image_intake.Intake(self.base, clock=lambda: clock[0])
        intake.scan_inbox()
        clock[0] += 60
        with patch.object(intake, 'submit', side_effect=RuntimeError('fixture runtime defect')):
            result = intake.scan_inbox()
        self.assertEqual(result['runtime_errors'], 1)
        self.assertEqual(result['files'][0]['outcome'], 'admission_failed')

    def test_cli_short_form_and_service_failure_keeps_admitted_job(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output), \
                patch.object(client, 'start_services', side_effect=RuntimeError('fixture offline')):
            self.assertEqual(client.main([str(self.source)], base=self.base), 1)
        self.assertIn('圖片已記帳', output.getvalue())
        self.assertEqual(len(self.jobs()), 1)

    def test_cli_dry_run_never_starts_services(self):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(client, 'start_services') as start:
            self.assertEqual(client.main(['submit', str(self.source), '--dry-run'], base=self.base), 0)
        start.assert_not_called()
        self.assertEqual(self.jobs(), [])

    def test_start_preserves_human_gates_and_does_not_reset_baseline(self):
        for flag in client.GATES:
            (self.queue.directory / flag).write_text('human pause')
        with patch.object(client, 'run_service', return_value='loaded\nloaded') as service:
            gates = client.start_services(self.base)
        self.assertEqual(gates, list(client.GATES))
        self.assertFalse(any('install_monitor.sh' in ' '.join(call.args[0]) for call in service.call_args_list))
        for flag in client.GATES:
            self.assertEqual((self.queue.directory / flag).read_text(), 'human pause')

    def test_status_distinguishes_export_from_physical_acceptance(self):
        result = self.intake.submit([self.source])[0]
        self.queue.claim('GPU-fixture')
        self.queue.finish(result['id'], 'success', 'fixture_export')
        evidence = self.queue.directory / 'jobs' / result['id'] / 'completion_validation.json'
        evidence.parent.mkdir(parents=True)
        evidence.write_text(json.dumps({'valid': True, 'run_id': result['run_id'],
            'strict_genesis_accept': False, 'completion_kind': 'native_final_revise_export'}))
        with patch.object(client.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'active\nactive\n')):
            self.assertEqual(client.status(self.base)['jobs'][0]['completion_status'], 'exported_unaccepted')
            data = json.loads(evidence.read_text())
            data['strict_genesis_accept'] = True
            evidence.write_text(json.dumps(data))
            self.assertEqual(client.status(self.base)['jobs'][0]['completion_status'], 'exported_accepted')
            data['run_id'] = 'another_run'
            evidence.write_text(json.dumps(data))
            self.assertEqual(client.status(self.base)['jobs'][0]['completion_status'], 'exported_unverified')

    def test_monitor_tick_admits_inbox_then_restores_queue_watcher(self):
        inbox = self.base / 'inbox'
        inbox.mkdir()
        shutil.copyfile(self.source, inbox / 'good.png')
        clock = [1000]
        watcher = monitor.Monitor(self.workspace, clock=lambda: clock[0])
        watcher.ensure_session = lambda *_: 'fixture_running'
        watcher.tick()
        clock[0] += 60
        report = watcher.tick()
        self.assertEqual(report['inbox']['submitted'], 1)
        self.assertEqual(report['watcher'], 'fixture_running')
        self.assertEqual(len(self.jobs()), 1)

    def test_stop_and_automation_stop_prevent_inbox_admission(self):
        inbox = self.base / 'inbox'
        inbox.mkdir()
        shutil.copyfile(self.source, inbox / 'good.png')
        for flag in ('STOP', 'AUTOMATION_STOP'):
            path = self.queue.directory / flag
            path.touch()
            watcher = monitor.Monitor(self.workspace)
            watcher.ensure_session = lambda *_: 'fixture_running'
            watcher.tick()
            path.unlink()
        self.assertEqual(self.jobs(), [])
