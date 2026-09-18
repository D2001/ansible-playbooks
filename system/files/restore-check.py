#!/usr/bin/env python3
"""Run isolated restore checks and publish per-service results for Prometheus."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

BASE = Path('/home/karsten')
STATE_DIR = BASE / 'backups/restore-checks'
METRICS = BASE / 'monitoring/textfile/restore-checks.prom'
RUNNER = BASE / 'ansible-playbooks/docker/run-ansible.sh'
MODES = {'homeassistant': ('portable_test',),
         'paperless': ('portable_test', 'test'),
         'monitoring': ('portable_test',)}
SOURCES = ('local', 'nas', 'onedrive')


def atomic_write(path, text, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def metrics_text(results):
    lines = [
        '# HELP restore_check_last_attempt_timestamp_seconds Last isolated restore attempt.',
        '# TYPE restore_check_last_attempt_timestamp_seconds gauge',
        '# HELP restore_check_last_success_timestamp_seconds Last successful isolated restore.',
        '# TYPE restore_check_last_success_timestamp_seconds gauge',
        '# HELP restore_check_success Whether the latest isolated check succeeded.',
        '# TYPE restore_check_success gauge',
        '# HELP restore_check_duration_seconds Duration of latest isolated restore check.',
        '# TYPE restore_check_duration_seconds gauge',
    ]
    for key, result in sorted(results.items()):
        service, source, mode = key.split('|')
        if service not in MODES or source not in SOURCES or mode not in MODES[service]:
            raise ValueError('Unexpected restore status label')
        labels = f'service="{service}",source="{source}",mode="{mode}"'
        for metric, field in [('last_attempt_timestamp_seconds', 'last_attempt'),
                              ('last_success_timestamp_seconds', 'last_success'),
                              ('success', 'success'), ('duration_seconds', 'duration')]:
            lines.append(f'restore_check_{metric}{{{labels}}} {int(result.get(field, 0))}')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=(*SOURCES, 'rotate'), default='rotate')
    parser.add_argument('--service', choices=tuple(MODES))
    parser.add_argument('--plan', action='store_true')
    args = parser.parse_args()
    source = (SOURCES[datetime.date.today().isocalendar().week % len(SOURCES)]
              if args.source == 'rotate' else args.source)
    checks = [(service, mode) for service, modes in MODES.items()
              if args.service is None or args.service == service for mode in modes]
    if args.plan:
        print(json.dumps({'source': source, 'checks': checks, 'production_start': False}))
        return 0
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE_DIR / 'run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Restore checks already running; no second run started')
            return 0
        state_file = STATE_DIR / 'status.json'
        results = json.loads(state_file.read_text()) if state_file.exists() else {}
        failures = []
        for service, mode in checks:
            key = '|'.join((service, source, mode))
            started = int(time.time())
            previous_success = results.get(key, {}).get('last_success', 0)
            log_path = STATE_DIR / f'{service}-{source}-{mode}.log'
            print(f'Checking {service}: source={source}, mode={mode}', flush=True)
            # Mark the attempt before launch so interruption cannot leave a stale
            # success indication for a new run.
            results[key] = {'last_attempt': started, 'last_success': previous_success,
                            'success': 0, 'duration': 0, 'log': str(log_path)}
            atomic_write(state_file, json.dumps(results, indent=2) + '\n', 0o600)
            atomic_write(METRICS, metrics_text(results), 0o644)
            with log_path.open('w') as log:
                log_path.chmod(0o600)
                run = subprocess.run([str(RUNNER), 'restore.yml', '-e', f'service_name={service}',
                                      '-e', f'restore_mode={mode}', '-e', f'restore_source={source}'],
                                     stdout=log, stderr=subprocess.STDOUT)
            finished = int(time.time())
            results[key].update(success=int(run.returncode == 0), duration=finished-started,
                                last_success=finished if run.returncode == 0 else previous_success)
            atomic_write(state_file, json.dumps(results, indent=2) + '\n', 0o600)
            atomic_write(METRICS, metrics_text(results), 0o644)
            print(f'{service}/{mode}: ' + ('passed' if run.returncode == 0 else 'FAILED'), flush=True)
            if run.returncode:
                failures.append(key)
        return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
