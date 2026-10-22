#!/usr/bin/env python3
"""Human CLI for image submission and server-service control, not a pipeline agent."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from batch_control import Queue
from image_intake import Intake


BASE = Path(__file__).resolve().parents[1]
TIMERS = ('diaggen-genesis-monitor.timer', 'diaggen-genesis-repair.timer')
GATES = ('HOLD', 'STOP', 'AUTOMATION_STOP', 'REPAIR_STOP')


def run_service(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Service command failed')
    return result.stdout.strip()


def start_services(base):
    queue = Queue(base)
    if not queue.path.exists():
        queue.init()
    (base / 'inbox').mkdir(exist_ok=True)
    states = run_service(['systemctl', '--user', 'show', '--property=LoadState', '--value', *TIMERS])
    if 'not-found' in states.splitlines():
        run_service(['bash', str(base / 'queue/install_monitor.sh')])
    else:
        run_service(['systemctl', '--user', 'enable', '--now', *TIMERS])
        run_service(['systemctl', '--user', 'start', '--no-block', 'diaggen-genesis-monitor.service'])
    # Human stop flags are preserved, even when explicitly starting services.
    return [name for name in GATES if (queue.directory / name).exists()]


def status(base):
    queue = Queue(base)
    if not queue.path.exists():
        raise ValueError('Queue is not initialized; use ./diaggen start')
    with queue._locked():
        batch = queue._load()
    units = subprocess.run(['systemctl', '--user', 'is-active', *TIMERS],
                           capture_output=True, text=True, timeout=10)
    states = units.stdout.strip().splitlines()
    inbox_status = queue.directory / 'inbox_status.json'
    jobs = []
    for job in batch['jobs']:
        entry = {key: job.get(key) for key in ('id', 'run_id', 'status')}
        entry['completion_status'] = None
        evidence = queue.directory / 'jobs' / job['id'] / 'completion_validation.json'
        if job['status'] == 'success':
            entry['completion_status'] = 'exported_unverified'
            try:
                report = json.loads(evidence.read_text())
                if report.get('valid') is True and report.get('run_id') == job['run_id']:
                    if report.get('strict_genesis_accept') is True:
                        entry['completion_status'] = 'exported_accepted'
                    elif report.get('completion_kind') == 'native_final_revise_export':
                        entry['completion_status'] = 'exported_unaccepted'
            except (ValueError, OSError):
                pass
        jobs.append(entry)
    return {'simulator': 'Genesis', 'model': 'gpt-6-luna', 'reasoning_effort': 'max',
            'inbox': str(base / 'inbox'), 'results_directory': str(base / 'runs'),
            'services': dict(zip(TIMERS, states)),
            'gates': [name for name in GATES if (queue.directory / name).exists()],
            'jobs': jobs,
            'inbox_status': json.loads(inbox_status.read_text()) if inbox_status.exists() else None}


def main(argv=None, *, base=BASE):
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {'submit', 'start', 'status'}
    # ./diaggen /path/image.png is the short form of ./diaggen submit ...
    if argv and argv[0] not in commands and not argv[0].startswith('-'):
        argv.insert(0, 'submit')
    parser = argparse.ArgumentParser(description='提交圖片，由背景 DiagGen + Genesis 自動執行。')
    subs = parser.add_subparsers(dest='command', required=True)
    submit = subs.add_parser('submit', help='提交圖片或資料夾並啟動背景排程')
    submit.add_argument('paths', nargs='+', help='PNG/JPG/JPEG 圖片或資料夾，支援空白與中文路徑')
    submit.add_argument('--recursive', action='store_true', help='包含資料夾的子目錄')
    submit.add_argument('--dry-run', action='store_true', help='只檢查圖片與重複項目，不寫入或啟動工作')
    subs.add_parser('start', help='啟用收件資料夾與背景排程；保留人工暫停旗標')
    state = subs.add_parser('status', help='查看所有任務與背景服務狀態')
    state.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'submit':
            items = Intake(base).submit(args.paths, recursive=args.recursive, dry_run=args.dry_run)
            for item in items:
                label = '重複圖片，沿用既有任務' if item['duplicate'] else ('可提交' if args.dry_run else '已加入佇列')
                print(f"{label}：{item['id']} [{item['status']}]\n  結果：{item['results_directory']}")
            if not args.dry_run:
                try:
                    gates = start_services(base)
                except (RuntimeError, OSError, subprocess.SubprocessError) as error:
                    print(f'圖片已記帳，但服務未確認啟動：{error}\n請執行 ./diaggen start；重複提交不會另開任務。', file=sys.stderr)
                    return 1
                print('背景排程已啟用；可關閉 SSH。')
                if gates:
                    print('目前有暫停旗標：' + ', '.join(gates) + '；需處理其原因後才會接續。')
        elif args.command == 'start':
            gates = start_services(base)
            print(f'背景排程已啟用。把 PNG/JPG/JPEG 放入：\n{base / "inbox"}\n穩定檔案會在約 1–2 分鐘內加入佇列。')
            if gates:
                print('目前有暫停旗標：' + ', '.join(gates))
        else:
            value = status(base)
            if args.json:
                print(json.dumps(value, ensure_ascii=False, indent=2))
            else:
                for name, value_ in value['services'].items():
                    print(f'{name}: {value_}')
                if value['gates']:
                    print('暫停旗標：' + ', '.join(value['gates']))
                for job in value['jobs']:
                    label = job['completion_status'] or job['status']
                    print(f"{label:20} {job['id']} → {job['run_id']}")
                inbox = value['inbox_status'] or {}
                for item in inbox.get('files', []):
                    if item['outcome'] in ('settling', 'invalid_image', 'admission_failed'):
                        print(f"收件：{item['name']} [{item['outcome']}] {item.get('error_type', '')}")
                print('輸出：' + value['results_directory'])
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'無法完成：{error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
