#!/usr/bin/env python3
"""Deterministic incident admission/result bookkeeping; shell owns Codex exec.

This never executes a pipeline, decides a diagnostic verdict, or edits native
state. A separate scheduled shell worker invokes Codex only for admitted faults.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

from batch_control import Queue, atomic_json, now, validate_identifier
from monitor import object_file, pid_alive


MAX_ATTEMPTS = 2
COOLDOWN_SECONDS = 900
MONITOR_STALE_SECONDS = 240
CLASSIFICATIONS = {'scheduler', 'pipeline_runtime', 'dependency', 'external_service',
                   'native_business_halt', 'unknown', 'no_issue'}
OUTCOMES = {'repaired_and_requeued', 'recovered', 'waiting_native_cleanup',
            'needs_attention', 'healthy', 'blocked_review'}
ACTIONABLE = {'resume_ineligible', 'export_validation_failed', 'retry_limit',
              'process_inspection_unavailable', 'unbound_worker_review',
              'inspection_failed', 'preflight_failed', 'stage_failed', 'quiet'}
CONTINUABLE = {'native_revision_budget_exhausted', 'exported_unaccepted'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class RepairControl:
    def __init__(self, workspace=None, *, clock=time.time, pid_probe=pid_alive):
        self.workspace = (workspace or Path(__file__).resolve().parents[3]).resolve()
        self.base = self.workspace / 'sims/diaggen_genesis'
        self.queue = Queue(self.base)
        self.directory = self.queue.directory
        self.path = self.directory / 'repair_state.json'
        self.clock, self.pid_probe = clock, pid_probe

    @contextmanager
    def locked(self):
        with (self.directory / 'repair_state.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def state(self):
        return object_file(self.path) if self.path.exists() else {'incidents': {}, 'baseline': []}

    def batch(self):
        with self.queue._locked():
            return self.queue._load()

    def job_signature(self, job):
        path = self.workspace / 'tools/diaggen/outputs/agentic_asset_refinement' / job['run_id'] / 'state.json'
        native = object_file(path) if path.exists() else {}
        terminal = native.get('diagnostics', {}).get('terminal') or {}
        operational = terminal.get('operational_outcome') or {}
        business = terminal.get('business_outcome') or {}
        return digest({'id': job['id'], 'run_id': job['run_id'], 'resume_id': job.get('resume_id'),
                       'queue_status': job['status'], 'native_status': native.get('status'),
                       'stages': {k: v.get('status') for k, v in native.get('stages', {}).items()},
                       'terminal_status': terminal.get('status'),
                       'business_status': business.get('status'),
                       'failure_kind': operational.get('failure_kind')})

    def baseline(self):
        """Record already understood failures once, never suppress a newer run."""
        with self.locked():
            state = self.state()
            if 'baseline_at' not in state:
                state['baseline'] = [self.job_signature(j) for j in self.batch()['jobs']
                                     if j['status'] == 'failed' and j['id'] in ('capybara_plush_toy', 'kitchen_tongs')]
                state['baseline_at'] = now()
                atomic_json(self.path, state)
            return state

    def request_job(self, job_id, reason):
        """Record an explicit operator investigation without erasing prior limits."""
        validate_identifier(job_id)
        validate_identifier(reason)
        with self.locked():
            job = next((j for j in self.batch()['jobs'] if j['id'] == job_id), None)
            if job is None:
                raise ValueError('Unknown investigation job')
            state = self.state()
            request_id = uuid.uuid4().hex
            state.setdefault('requested', []).append({
                'kind': 'user_requested_investigation', 'job_id': job_id, 'run_id': job['run_id'],
                'prior_resume_id': job.get('resume_id'), 'prior_attempts': job['attempts'],
                'reason': reason, 'signature': digest({'request': request_id, 'job': job_id})})
            atomic_json(self.path, state)
            return request_id

    def incidents(self, state):
        monitor_path = self.directory / 'monitor_status.json'
        if not monitor_path.exists():
            return [{'kind': 'monitor_missing', 'signature': digest('monitor_missing')}]
        try:
            observed = object_file(monitor_path)
            stamp = datetime.fromisoformat(observed['updated_at']).timestamp()
        except (ValueError, TypeError, KeyError):
            return [{'kind': 'monitor_invalid', 'signature': digest('monitor_invalid')}]
        if self.clock() - stamp > MONITOR_STALE_SECONDS:
            return [{'kind': 'monitor_stale', 'signature': digest('monitor_stale')}]
        index = {(j.get('id'), j.get('run_id')): j for j in observed.get('jobs', [])}
        try:
            batch = self.batch()
        except (ValueError, KeyError, FileNotFoundError):
            return [{'kind': 'queue_ledger_invalid', 'signature': digest('queue_ledger_invalid')}]
        current_runs = {(j['id'], j['run_id']) for j in batch['jobs']}
        result = [item for item in state.get('requested', [])
                  if (item.get('job_id'), item.get('run_id')) in current_runs]
        inbox = observed.get('inbox', {})
        if inbox.get('outcome') == 'scan_failed' or inbox.get('runtime_errors', 0):
            result.append({'kind': 'image_intake_failed',
                           'signature': digest({'kind': 'image_intake_failed',
                                                'error_type': inbox.get('error_type')})})
        for job in batch['jobs']:
            observation = index.get((job['id'], job['run_id']), {})
            outcome = observation.get('outcome')
            continuing = bool(job.get('diagnostic_continuation')) or job.get('autonomous_native_repair') is True
            if job['status'] == 'cancelled' or (job['status'] == 'success'
                                               and not (continuing and outcome == 'exported_unaccepted')):
                continue
            identity = self.job_signature(job)
            if identity in state.get('baseline', []) and not continuing:
                continue
            if outcome == 'business_halt':
                outcome = 'new_native_halt'
            if outcome == 'waiting_cleanup':
                # Give the native watchdog time to close abnormal owners first.
                finished = job.get('finished_at')
                if finished and self.clock() - datetime.fromisoformat(finished).timestamp() > 600:
                    outcome = 'cleanup_wait_excessive'
            if (outcome in ACTIONABLE or outcome in ('cleanup_wait_excessive', 'new_native_halt')
                    or (continuing and outcome in CONTINUABLE)):
                result.append({'kind': outcome, 'job_id': job['id'], 'run_id': job['run_id'],
                               'prior_resume_id': job.get('resume_id'), 'prior_attempts': job['attempts'],
                               'signature': digest({'state': identity, 'kind': outcome})})
        return result

    def readiness(self):
        sys.path.insert(0, str(self.base / 'preflight'))
        from readiness import verify
        return verify(self.workspace, self.directory / 'runtime_preflight.json')

    def prepare(self, *, audit=False, runner_pid=None, retry_launch_fix=False):
        runner_pid = os.getpid() if runner_pid is None else runner_pid
        with self.locked():
            state = self.state()
            if any((self.directory / name).exists() for name in ('REPAIR_STOP', 'AUTOMATION_STOP', 'STOP')):
                return None
            active = state.get('active')
            if active and self.pid_probe(active.get('runner_pid')):
                return None
            if active:
                # Keep evidence of an interrupted repair; do not release its gate.
                prior = self.directory / 'repair_jobs' / active['id']
                atomic_json(prior / 'abandoned.json', {'observed_at': now(), 'reason': 'repair_worker_disappeared'})
                state.pop('active', None)
            hold = self.directory / 'HOLD'
            held = hold.read_text() if hold.is_file() and not hold.is_symlink() else None
            owned_hold = (held is not None and held.startswith('diaggen-repair:')
                          and held == state.get('owned_hold'))
            machine_hold = (held is not None and any(held.startswith(prefix) for prefix in
                            ('Runtime preflight is missing or stale;', 'SAM3 EXR preflight failed;',
                             'Private Xvfb is missing;', 'Six-view display preflight failed;')))
            # A human HOLD means work is being reviewed; do not compete with it.
            if hold.exists() and not (owned_hold or machine_hold):
                return None
            previous_launch = None
            if retry_launch_fix:
                # Explicit operator retry after a verified CLI configuration fix.
                # No model/stage budget is reset and the failed launch stays intact.
                self.readiness()
                previous = object_file(self.directory / 'repair_status.json')
                validate_identifier(previous['id'])
                prior = self.directory / 'repair_jobs' / previous['id']
                completion = object_file(prior / 'completion.json')
                events = prior / 'events.jsonl'
                if (completion.get('exit_code') != 1 or completion.get('result_valid') is not False
                        or (events.exists() and events.stat().st_size != 0)
                        or (prior / 'stderr.log').read_text().strip() !=
                        'Error loading config.toml: invalid transport\nin `mcp_servers.hag4r_genesis_diagnostics`'):
                    raise ValueError('Immediate launch retry requires a proven pre-model transport failure')
                previous_launch = object_file(prior / 'request.json')
            found = [{'kind': 'read_only_audit', 'signature': digest('read_only_audit')}]
            if not audit:
                found = ([state['owned_hold_incident']] if owned_hold and state.get('owned_hold_incident')
                         else self.incidents(state))
                found = [i for i in found if state.get('incidents', {}).get(i['signature'], {}).get('attempts', 0) < MAX_ATTEMPTS
                         and not state.get('incidents', {}).get(i['signature'], {}).get('resolved', False)
                         and (self.clock() - state.get('incidents', {}).get(i['signature'], {}).get('last_attempt', 0) >= COOLDOWN_SECONDS
                              or (previous_launch is not None and i['signature'] == previous_launch['incident']['signature']))]
                if not found:
                    atomic_json(self.path, state)
                    return None
            incident = found[0]
            job_id = datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:12]
            target = self.directory / 'repair_jobs' / job_id
            target.mkdir(parents=True, exist_ok=False)
            if not audit and not hold.exists():
                held = 'diaggen-repair:' + job_id + '\n'
                with self.queue._locked():
                    with hold.open('x') as stream:
                        stream.write(held)
                state['owned_hold'] = held
                state['owned_hold_incident'] = incident
            request = {'schema_version': 'diaggen-repair-request-v1', 'id': job_id,
                       'created_at': now(), 'read_only': audit, 'incident': incident,
                       'workspace': str(self.workspace), 'hold_present': hold.exists(),
                       'hold_sha256': hashlib.sha256(held.encode()).hexdigest() if held else None,
                       'hold_owned': not audit and held == state.get('owned_hold'),
                       'machine_hold': machine_hold, 'baseline_known_failures': state.get('baseline', [])}
            if previous_launch is not None:
                request['verified_launch_fix_retry_of'] = previous_launch['id']
            atomic_json(target / 'request.json', request)
            template = (self.directory / 'repair_prompt.md').read_text()
            (target / 'prompt.txt').write_text(template.replace('@REQUEST@', str(target / 'request.json'))
                                             .replace('@WORKSPACE@', str(self.workspace)))
            counter = state.setdefault('incidents', {}).setdefault(incident['signature'], {'attempts': 0})
            if not audit:
                counter.update(attempts=counter['attempts'] + 1, last_attempt=self.clock())
            state['active'] = {'id': job_id, 'runner_pid': runner_pid, 'read_only': audit}
            atomic_json(self.path, state)
            self.publish('running', job_id, audit=audit, incident=incident['kind'])
            return job_id

    def publish(self, status, job_id, *, audit=False, incident='unknown', classification='unknown', outcome='needs_attention'):
        atomic_json(self.directory / 'repair_status.json', {
            'schema_version': 'diaggen-repair-status-v1', 'updated_at': now(), 'enabled': True,
            'status': status, 'id': job_id, 'read_only_audit': audit, 'incident': incident,
            'classification': classification, 'outcome': outcome,
            'model': 'gpt-6-luna', 'reasoning_effort': 'max'})

    def finish(self, job_id, returncode):
        validate_identifier(job_id)
        with self.locked():
            state = self.state()
            if state.get('active', {}).get('id') != job_id:
                raise ValueError('Repair result does not own the active slot')
            target = self.directory / 'repair_jobs' / job_id
            request = object_file(target / 'request.json')
            result_path = target / 'result.json'
            result = object_file(result_path) if result_path.exists() else {}
            valid = (returncode == 0 and result.get('classification') in CLASSIFICATIONS
                     and result.get('outcome') in OUTCOMES and result.get('incident_id') == job_id
                     and isinstance(result.get('summary'), str)
                     and all(isinstance(result.get(k), list) and all(isinstance(x, str) for x in result[k])
                             for k in ('changed_files', 'checks', 'requeued_jobs')))
            classification = result['classification'] if valid else 'unknown'
            outcome = result['outcome'] if valid else 'needs_attention'
            # A model's claim of requeue is checked against actual queue state.
            if outcome == 'repaired_and_requeued':
                expected = request['incident'].get('job_id')
                current = next((j for j in self.batch()['jobs'] if j['id'] == expected), None)
                changed = (current is not None and
                           (current['run_id'] != request['incident'].get('run_id')
                            or current.get('resume_id') != request['incident'].get('prior_resume_id')
                            or current['attempts'] > request['incident'].get('prior_attempts', current['attempts'])))
                if not current or current['status'] not in ('queued', 'running') or not changed:
                    outcome = 'needs_attention'
            released = False
            verified = False
            if not request['read_only']:
                try:
                    self.readiness()
                    verified = True
                except Exception:
                    outcome = 'needs_attention'
            hold = self.directory / 'HOLD'
            if not request['read_only'] and request['hold_owned'] and hold.is_file() and not hold.is_symlink():
                if verified and hashlib.sha256(hold.read_bytes()).hexdigest() == request['hold_sha256']:
                    with self.queue._locked():
                        if hashlib.sha256(hold.read_bytes()).hexdigest() == request['hold_sha256']:
                            hold.unlink()
                            released = True
            if not request['read_only'] and hold.exists() and outcome in ('healthy', 'recovered', 'repaired_and_requeued'):
                outcome = 'needs_attention'
            evidence = {'finished_at': now(), 'exit_code': returncode, 'result_valid': valid,
                        'own_hold_released_after_verification': released,
                        'classification': classification, 'outcome': outcome}
            atomic_json(target / 'completion.json', evidence)
            state.pop('active', None)
            if (outcome in ('healthy', 'recovered', 'repaired_and_requeued')
                    or (classification == 'native_business_halt'
                        and request['incident']['kind'] not in CONTINUABLE)):
                state['incidents'][request['incident']['signature']]['resolved'] = True
            atomic_json(self.path, state)
            self.publish('finished' if valid else 'needs_attention', job_id,
                         audit=request['read_only'], incident=request['incident']['kind'],
                         classification=classification, outcome=outcome)
            return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('baseline', 'prepare', 'finish', 'request'))
    parser.add_argument('arguments', nargs='*')
    parser.add_argument('--audit', action='store_true')
    parser.add_argument('--retry-launch-fix', action='store_true')
    args = parser.parse_args()
    control = RepairControl()
    if args.command == 'baseline':
        control.baseline()
    elif args.command == 'request' and len(args.arguments) == 2:
        print(control.request_job(*args.arguments))
    elif args.command == 'prepare':
        value = control.prepare(audit=args.audit, runner_pid=int(os.environ['DIAGGEN_REPAIR_RUNNER_PID']),
                                retry_launch_fix=args.retry_launch_fix)
        if value:
            print(value)
    elif args.command == 'finish' and len(args.arguments) == 2:
        print(json.dumps(control.finish(args.arguments[0], int(args.arguments[1]))))
    else:
        parser.error('Invalid command arguments')


if __name__ == '__main__':
    main()
