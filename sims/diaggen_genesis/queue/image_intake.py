#!/usr/bin/env python3
"""Deterministic image admission and immutable copying, never a stage agent."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import warnings

from PIL import Image

from batch_control import Queue, atomic_json, now


EXTENSIONS = {'.png', '.jpg', '.jpeg'}
MAX_BYTES = 64 * 1024 * 1024
MAX_JOBS = 100  # Same bound as the existing progress publisher, including history.
SETTLE_SECONDS = 15


def stamp(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns]


def inspect_image(value):
    path = Path(value).expanduser().absolute()
    if path.suffix.lower() not in EXTENSIONS:
        raise ValueError(f'Only PNG/JPG/JPEG images are supported: {path.name}')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
            raise ValueError(f'Image must be a regular file of at most 64 MiB: {path.name}')
        data = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    if (len(data) != before.st_size or stamp(before) != stamp(after)
            or stamp(after) != stamp(path.stat(follow_symlinks=False))):
        raise ValueError(f'Image changed while reading; finish uploading and retry: {path.name}')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ('PNG', 'JPEG') or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('A single static PNG or JPEG image is required')
            metadata = {'format': image.format, 'width': image.width, 'height': image.height}
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()  # Reject truncated data as well as invalid headers.
    return {'path': path, 'data': data, 'stamp': stamp(after),
            'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data), **metadata}


def collect_images(paths, recursive=False):
    found = []
    for value in paths:
        path = Path(value).expanduser().absolute()
        if path.is_dir() and not path.is_symlink():
            entries = path.rglob('*') if recursive else path.iterdir()
            selected = sorted(p for p in entries if p.suffix.lower() in EXTENSIONS
                              and not p.is_symlink() and p.is_file())
            if not selected:
                raise ValueError(f'No PNG/JPG/JPEG images found in {path}')
            found.extend(selected)
        else:
            found.append(path)
    return list(dict.fromkeys(found))


def immutable_copy(path, data):
    """Publish a fully written file without replacing any existing bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Refusing a symlink image destination')
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Previously frozen image changed; refusing to overwrite it')
        return
    fd, temporary = tempfile.mkstemp(prefix='.intake-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), 0o444)
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != data:
                raise ValueError('Conflicting frozen input') from None
    finally:
        os.unlink(temporary)


class Intake:
    def __init__(self, base=None, *, clock=time.time):
        self.queue = Queue(base)
        self.base = self.queue.base
        self.clock = clock

    def submit(self, paths, *, recursive=False, dry_run=False):
        paths = collect_images(paths, recursive)
        # Validate every input before admitting any job from this invocation.
        records = []
        for path in paths:
            record = inspect_image(path)
            del record['data']  # Large folders must not keep all image bytes in RAM.
            records.append(record)
        if not self.queue.path.exists():
            if dry_run:
                raise ValueError('Queue is not initialized; run ./diaggen start first')
            self.queue.init()
        with self.queue._locked():
            batch = self.queue._load()
            by_hash = {job.get('input_sha256'): job for job in batch['jobs']}
            results = []
            for record in records:
                digest = record['sha256']
                duplicate = digest in by_hash
                if duplicate:
                    job = by_hash[digest]
                else:
                    if len(batch['jobs']) >= MAX_JOBS:
                        raise ValueError('Queue has reached its 100-job history limit; no new jobs were admitted')
                    slug = re.sub(r'[^a-z0-9]+', '_', record['path'].stem.lower()).strip('_')[:28] or 'asset'
                    job_id = f'image_{slug}_{digest[:16]}'
                    suffix = '.png' if record['format'] == 'PNG' else '.jpg'
                    job = {'id': job_id, 'run_id': f'genesis_{job_id}',
                           'input': f'inputs/submissions/{digest}{suffix}',
                           'input_sha256': digest, 'status': 'queued', 'gpu_uuid': None,
                           'runner_pid': None, 'attempts': 0, 'started_at': None, 'finished_at': None,
                           'execution_mode': 'fresh', 'submitted_at': now(),
                           'submission': {key: record[key] for key in
                                          ('format', 'width', 'height', 'size_bytes')}}
                    batch['jobs'].append(job)
                    by_hash[digest] = job
                results.append({'id': job['id'], 'run_id': job['run_id'], 'status': job['status'],
                                'duplicate': duplicate, 'source': str(record['path']),
                                'results_directory': str(self.base / 'runs' / job['run_id'])})
            self.queue._validate_jobs(batch['jobs'], dynamic=True)
            if not dry_run:
                directory = self.base / 'inputs/submissions'
                if directory.is_symlink() or not directory.resolve().is_relative_to((self.base / 'inputs').resolve()):
                    raise ValueError('Unsafe submissions directory')
                for record, result in zip(records, results):
                    if not result['duplicate']:
                        current = inspect_image(record['path'])
                        if current['sha256'] != record['sha256'] or current['stamp'] != record['stamp']:
                            raise ValueError('Input changed between validation and admission; retry after uploading')
                        immutable_copy(self.base / by_hash[record['sha256']]['input'], current['data'])
                self.queue._save(batch)
        return results

    def scan_inbox(self):
        """One stable-file scan per minute; keep source files, deduplicate by bytes."""
        inbox = self.base / 'inbox'
        result = {'schema_version': 'diaggen-inbox-status-v1', 'updated_at': now(),
                  'files': [], 'submitted': 0, 'errors': 0, 'runtime_errors': 0}
        if not inbox.exists():
            return result
        if inbox.is_symlink():
            raise ValueError('Inbox must be a real directory')
        state_path = self.queue.directory / 'inbox_state.json'
        previous = json.loads(state_path.read_text()) if state_path.exists() and not state_path.is_symlink() else {}
        state = {}
        for path in sorted(inbox.iterdir()):
            if path.suffix.lower() not in EXTENSIONS or path.is_symlink() or not path.is_file():
                continue
            try:
                current = stamp(path.stat())
                old = previous.get(path.name, {})
                first = old.get('first_seen', self.clock()) if old.get('stamp') == current else self.clock()
                entry = {'stamp': current, 'first_seen': first}
                if old.get('stamp') == current and old.get('outcome') in ('submitted', 'duplicate'):
                    entry.update(outcome=old['outcome'], id=old['id'])
                elif old.get('stamp') != current or self.clock() - first < SETTLE_SECONDS:
                    entry['outcome'] = 'settling'
                else:
                    item = self.submit([path])[0]
                    entry.update(outcome='duplicate' if item['duplicate'] else 'submitted', id=item['id'])
                    result['submitted'] += not item['duplicate']
            except Exception as error:
                runtime_error = not isinstance(error, (ValueError, OSError))
                entry = {'stamp': stamp(path.stat()) if path.exists() else None,
                         'first_seen': self.clock(),
                         'outcome': 'admission_failed' if runtime_error else 'invalid_image',
                         'error_type': type(error).__name__}
                result['errors'] += 1
                result['runtime_errors'] += runtime_error
            state[path.name] = entry
            result['files'].append({'name': path.name, **entry})
        atomic_json(state_path, state)
        atomic_json(self.queue.directory / 'inbox_status.json', result)
        return result

    def freeze(self, job_id, destination):
        with self.queue._locked():
            batch = self.queue._load()
            job = next(job for job in batch['jobs'] if job['id'] == job_id)
            if job['status'] != 'running' or job.get('execution_mode', 'fresh') != 'fresh':
                raise ValueError('Only a claimed fresh job can freeze its source')
            record = inspect_image(self.base / job['input'])
            if record['sha256'] != job.get('input_sha256'):
                raise ValueError('Input hash changed after admission')
            workspace = self.base.parents[1]
            expected = workspace / 'tools/diaggen/outputs/inputs' / (job['run_id'] + Path(job['input']).suffix)
            if Path(destination).absolute() != expected or expected.parent.is_symlink():
                raise ValueError('Unexpected native frozen input destination')
            immutable_copy(expected, record['data'])


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] != 'freeze':
        raise SystemExit('Internal use: image_intake.py freeze JOB_ID DESTINATION')
    Intake().freeze(sys.argv[2], sys.argv[3])
