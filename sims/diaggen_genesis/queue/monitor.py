#!/usr/bin/env python3
"""One deterministic server watchdog tick, never a pipeline or diagnostic agent.

Shell workers retain the official Codex skill orchestration. This program only
observes processes, restores shell services, and uses existing guarded queue
resume/export bookkeeping. It never resets a stage or retries a business halt.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from batch_control import Queue, atomic_json, now


MAX_RESUMES = 2
RETRY_DELAY_SECONDS = 300
BIND_GRACE_SECONDS = 180
QUIET_SECONDS = 2700


def object_file(path):
    if path.is_symlink():
        raise ValueError("Watchdog refuses a symlink ledger")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Watchdog requires an object ledger")
    return value


def pid_alive(pid):
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # Zombies cannot execute but remain conservatively treated as live here.
    return True


def native_resource_profiler(entry, argv, run_root):
    """Recognize only the checkout's exact detached resource sampler.

    The official profiler survives retryable diagnostics for up to 24 hours.
    It samples resources and writes profiling reports, not pipeline state. Its
    locked PID, interpreter, argv and cwd must all match before excluding it.
    """
    try:
        root = run_root.parents[2]
        python = root / '.conda/hag4r/bin/python'
        arguments = [value for value in argv if value]
        if (len(arguments) != 6 or arguments[1:] !=
                [b'-m', b'hag4r.agentic.runtime_profiler', b'monitor', b'--run-root',
                 str(run_root).encode()]):
            return False
        lock = run_root / 'profiling/resource_monitor.lock'
        return (not lock.is_symlink() and lock.is_file()
                and lock.read_text().strip() == entry.name
                and Path(os.fsdecode(arguments[0])).resolve() == python.resolve()
                and (entry / 'exe').resolve(strict=True) == python.resolve(strict=True)
                and (entry / 'cwd').resolve(strict=True) == root.resolve())
    except (OSError, ValueError, IndexError):
        return False


def run_processes(run_id, run_root):
    """Conservative own-UID orphan check; never signal any process.

    Return None when a same-user process cannot be inspected. Environment and
    command bytes stay private and are never logged or included in a report.
    """
    matches = []
    markers = [f"DIAGGEN_QUEUE_RUN_ID={run_id}".encode(),
               f"HAG4R_WORKER_ID={run_id}".encode()]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            # Reaped-later zombies cannot execute. Login/PAM daemons intentionally
            # protect environ; their known login-only command titles are outside
            # this workload. Unknown protected compute processes still block us.
            status = (entry / 'status').read_text()
            if any(line.startswith('State:') and line.split()[1] == 'Z' for line in status.splitlines()):
                continue
            argv = (entry / 'cmdline').read_bytes().split(b'\0')
            if native_resource_profiler(entry, argv, run_root):
                continue
            comm = (entry / 'comm').read_text().strip()
            if ((comm == '(sd-pam)' and argv[0] == b'(sd-pam)')
                    or (comm == 'sshd' and argv[0].startswith(b'sshd: ') and b'@' in argv[0])):
                continue
            env = (entry / 'environ').read_bytes().split(b'\0')
            if any(marker in env for marker in markers) or any(str(run_root).encode() in arg for arg in argv):
                matches.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (PermissionError, OSError):
            return None
    return matches


class Monitor:
    def __init__(self, workspace=None, *, clock=time.time, process_probe=run_processes,
                 pid_probe=pid_alive):
        self.workspace = (workspace or Path(__file__).resolve().parents[3]).resolve()
        self.base = self.workspace / 'sims/diaggen_genesis'
        self.queue = Queue(self.base)
        self.directory = self.queue.directory
        self.clock, self.process_probe, self.pid_probe = clock, process_probe, pid_probe
        self.state_path = self.directory / 'automation_state.json'
        self.memory = object_file(self.state_path) if self.state_path.exists() else {'jobs': {}}
        if not isinstance(self.memory.get('jobs'), dict):
            raise ValueError('Invalid watchdog state')

    def save(self):
        atomic_json(self.state_path, self.memory)

    def ensure_session(self, name, script):
        found = subprocess.run(['tmux', 'has-session', '-t', name], capture_output=True,
                               timeout=10)
        if found.returncode == 0:
            return 'running'
        subprocess.run(['tmux', 'new-session', '-d', '-s', name, 'bash',
                        str(self.directory / script)], check=True, capture_output=True, timeout=10)
        return 'restarted'

    def readiness(self):
        import sys
        sys.path.insert(0, str(self.base / 'preflight'))
        from readiness import verify
        verify(self.workspace, self.directory / 'runtime_preflight.json')

    @contextmanager
    def recovery_hold(self):
        path = self.directory / 'HOLD'
        marker = 'diaggen-watchdog-recovery:' + uuid.uuid4().hex + '\n'
        # Queue claims and creation of this gate use the same lock.
        with self.queue._locked():
            with path.open('x') as stream:
                stream.write(marker)
                stream.flush()
                os.fsync(stream.fileno())
        try:
            yield
        finally:
            with self.queue._locked():
                if path.is_file() and not path.is_symlink() and path.read_text() == marker:
                    path.unlink()

    def native(self, job):
        root = self.workspace / 'tools/diaggen/outputs/agentic_asset_refinement' / job['run_id']
        path = root / 'state.json'
        return root, object_file(path) if path.exists() else {}

    def recent_activity(self, job, root):
        paths = [root / 'state.json'] + [self.directory / 'jobs' / job['id'] / name for name in
                                       ('codex_events.jsonl', 'launcher.log', 'status.json')]
        stamps = [p.stat().st_mtime for p in paths if p.is_file()]
        return max(stamps, default=self.clock())

    def recover_export(self, job):
        # This runs in mesh Python so the existing validator has its native deps.
        from reconcile_export import reconcile_export
        return reconcile_export(job['id'], base=self.base)

    def observe_job(self, job):
        root, native = self.native(job)
        status = job['status']
        if status == 'success':
            revision = native.get('active_revision')
            metadata = native.get('revisions', {}).get(revision, {})
            return 'exported_unaccepted' if metadata.get('status') == 'exported_unaccepted' else 'completed'
        if status in ('queued', 'cancelled'):
            return status
        # Already recorded business/stage failures need no process inspection:
        # no mutation or restart is attempted for them under any circumstances.
        terminal = native.get('diagnostics', {}).get('terminal') or {}
        business = terminal.get('business_outcome') or {}
        if status == 'failed' and native.get('status') != 'success':
            if terminal.get('status') == 'halted' or business.get('status') in ('recommendation_valid', 'business_halt'):
                return 'business_halt'
            if any(s.get('status') in ('failed', 'halted') for s in native.get('stages', {}).values()):
                return 'stage_failed'
        pid = job.get('runner_pid')
        if self.pid_probe(pid):
            return ('quiet' if self.clock() - self.recent_activity(job, root) > QUIET_SECONDS else 'running')
        # Process descendants can outlive their parent: never duplicate their work.
        owners = self.process_probe(job['run_id'], root)
        if owners is None:
            return 'process_inspection_unavailable'
        if owners:
            return 'waiting_cleanup'
        if type(pid) is not int or pid <= 0:
            return 'unbound_worker_review'
        if status == 'running':
            started = datetime.fromisoformat(job['started_at']).timestamp()
            if self.clock() - started < BIND_GRACE_SECONDS:
                return 'awaiting_worker_binding'
            with self.queue._locked():
                current = self.queue._job(self.queue._load(), job['id'])
                if current != job or self.pid_probe(pid):
                    return 'changed_during_observation'
                history = self.directory / 'automation_history' / job['id']
                history.mkdir(parents=True, exist_ok=True)
                atomic_json(history / (uuid.uuid4().hex + '.json'), job)
                batch = self.queue._load()
                current = self.queue._job(batch, job['id'])
                current.update(status='failed', finished_at=now(), reason='automation_worker_disappeared')
                self.queue._save(batch)
            job = {**job, 'status': 'failed'}
        if (self.directory / 'HOLD').exists():
            return 'hold'
        # Validated recommendations and real halts are not operational retries.
        if terminal.get('status') == 'halted' or business.get('status') in ('recommendation_valid', 'business_halt'):
            if native.get('status') != 'success':
                return 'business_halt'
        if any(s.get('status') in ('failed', 'halted') for s in native.get('stages', {}).values()):
            return 'stage_failed'
        key = job['id'] + ':' + job['run_id']
        memory = self.memory['jobs'].setdefault(key, {'attempts': 0})
        signature = hashlib.sha256(json.dumps(native, sort_keys=True).encode()).hexdigest()
        if memory.get('blocked_state') == signature:
            return memory.get('blocked_status', 'resume_ineligible')
        if memory['attempts'] >= MAX_RESUMES:
            return 'retry_limit'
        if self.clock() - memory.get('last_attempt', 0) < RETRY_DELAY_SECONDS:
            return 'retry_backoff'
        if native.get('status') != 'success':
            try:
                self.readiness()
            except Exception:
                return 'preflight_failed'
        # Persist budget before attempting a mutation, even if the process dies.
        memory.update(attempts=memory['attempts'] + 1, last_attempt=self.clock())
        self.save()
        if native.get('status') == 'success':
            try:
                self.recover_export(job)
                return 'export_recovered'
            except Exception:
                memory.update(blocked_state=signature, blocked_status='export_validation_failed')
                self.save()
                return 'export_validation_failed'
        try:
            with self.recovery_hold():
                # Existing Queue.resume rechecks PID, stage prefix, input hashes,
                # native diagnostics cleanup and immutable history under its lock.
                self.queue.resume(job['id'], 'scheduled_' + uuid.uuid4().hex,
                                  'scheduled_operational_resume')
            return 'resumed'
        except FileExistsError:
            return 'hold'
        except Exception:
            memory.update(blocked_state=signature, blocked_status='resume_ineligible')
            self.save()
            return 'resume_ineligible'

    def tick(self):
        report = {'schema_version': 'diaggen-server-monitor-v1', 'updated_at': now(),
                  'interval_seconds': 60, 'max_resumes_per_run': MAX_RESUMES,
                  'enabled': not (self.directory / 'AUTOMATION_STOP').exists(), 'jobs': []}
        if not report['enabled']:
            atomic_json(self.directory / 'monitor_status.json', report)
            return report
        with self.queue._locked():
            batch = self.queue._load()
        stopped = (self.directory / 'STOP').exists()
        report['queue_stopped'] = stopped
        for job in batch['jobs']:
            try:
                outcome = 'queue_stopped' if stopped else self.observe_job(job)
            except Exception:
                outcome = 'inspection_failed'
            report['jobs'].append({'id': job['id'], 'run_id': job['run_id'], 'outcome': outcome})
        with self.queue._locked():
            batch = self.queue._load()
        if not stopped and any(j['status'] in ('queued', 'running') for j in batch['jobs']):
            report['watcher'] = self.ensure_session('diaggen-genesis-wait', 'wait_and_run.sh')
        else:
            report['watcher'] = 'not_needed'
        report['publisher'] = self.ensure_session('diaggen-github-progress', 'publish_progress.sh')
        self.save()
        atomic_json(self.directory / 'monitor_status.json', report)
        return report


if __name__ == '__main__':
    # The shell owns the nonblocking singleton lock and log redirection.
    try:
        print(json.dumps(Monitor().tick(), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'status': 'monitor_failed', 'error_type': type(error).__name__}))
        raise SystemExit(1)
