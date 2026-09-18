#!/usr/bin/env python3
"""Exercise the update transaction using fake Docker/apt/backups, never the host."""
import os
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'files/system-update.sh'
MOCK = r'''#!/usr/bin/python3
import json, os, pathlib, subprocess, sys
name = pathlib.Path(sys.argv[0]).resolve().name
args = sys.argv[1:]
root = pathlib.Path(os.environ['TEST_ROOT'])
with (root / 'calls').open('a') as f:
    f.write(name + ' ' + ' '.join(args) + '\n')
if name == 'findmnt':
    print('cifs')
elif name == 'mountpoint':
    sys.exit(1 if os.environ.get('FAIL_MOUNT') else 0)
elif name == 'runuser':
    sys.exit(subprocess.call(args[args.index('--') + 1:]))
elif name == 'apt-get':
    sys.exit(1 if os.environ.get('FAIL_APT') else 0)
elif name == 'backup-runner':
    service = args[-1].split('=')[1]
    if os.environ.get('FAIL_BACKUP') == service:
        sys.exit(1)
    p = root / 'backups' / (service + '_backups')
    p.mkdir(parents=True, exist_ok=True)
    (p / (service + '_backup_20260918T010000.tar.gz')).write_bytes(b'test archive')
elif name == 'docker':
    if args[0] == 'compose':
        project = pathlib.Path(args[args.index('--project-directory') + 1]).name
        services = {'homeassistant': ['homeassistant'], 'monitoring': ['home-dashboard'],
                    'paperless': ['paperless-ngx', 'db', 'redis']}[project]
        if '--services' in args:
            print('\n'.join(services))
        elif 'ps' in args:
            print('\n'.join(project + '--' + s for s in services))
        elif 'up' in args and os.environ.get('FAIL_START'):
            sys.exit(1)
    elif args[0] == 'inspect':
        print(json.dumps([{'Name': x, 'Image': 'sha256:abcdef',
                           'Config': {'Labels': {'com.docker.compose.service': x.split('--')[1]}},
                           'State': {'Running': True, 'Health': {'Status': 'healthy'}}}
                          for x in args[1:]]))
'''

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='update-script-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        for name in ('docker', 'mountpoint', 'findmnt', 'runuser', 'apt-get', 'backup-runner'):
            p = bin_dir / name
            p.write_text(MOCK)
            p.chmod(0o755)
        for name in ('paperless', 'homeassistant', 'monitoring'):
            p = self.root / name
            p.mkdir()
            (p / 'docker-compose.yml').write_text('services: {}\n')
        lock = self.root / '.cache/backup-locks/docker-backup-global.lock'
        lock.parent.mkdir(parents=True)
        lock.touch()
        (self.root / 'backups').mkdir()
        runner = self.root / 'ansible-playbooks/docker/run-ansible.sh'
        runner.parent.mkdir(parents=True)
        runner.symlink_to(bin_dir / 'backup-runner')
        # Rebase only host-specific paths; the transaction code is unmodified.
        source = SCRIPT.read_text().replace('/home/karsten', str(self.root))
        source = source.replace('/run/lock/raspi-system-update.lock', str(self.root / 'update.lock'))
        self.script = self.root / 'update.sh'
        self.script.write_text(source)
        self.env = {**os.environ, 'TEST_ROOT': str(self.root),
                    'PATH': str(bin_dir) + ':' + os.environ['PATH']}

    def run_update(self, *args, **flags):
        result = subprocess.run(['bash', str(self.script), *args],
                                env={**self.env, **flags}, text=True, capture_output=True)
        return result, (self.root / 'calls').read_text()

    def test_check_is_read_only(self):
        result, calls = self.run_update('--check')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertNotIn('apt-get ', calls)
        self.assertNotIn('runuser ', calls)
        self.assertNotIn(' pull\n', calls)
        self.assertNotIn(' up ', calls)

    def test_failed_backup_prevents_updates(self):
        result, calls = self.run_update(FAIL_BACKUP='paperless')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('apt-get ', calls)
        self.assertNotIn(' pull\n', calls)

    def test_missing_mount_prevents_backup_and_updates(self):
        result, calls = self.run_update(FAIL_MOUNT='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('runuser ', calls)
        self.assertNotIn('apt-get ', calls)

    def test_success_order_and_recovery(self):
        result, calls = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertLess(calls.index('service_name=monitoring'), calls.index('apt-get update'))
        self.assertLess(calls.index('image tag'), calls.index('apt-get update'))
        self.assertLess(calls.index(' upgrade -y'), calls.index(' pull\n'))
        self.assertIn('up -d --wait --wait-timeout 180', calls)
        recovery = list((self.root / 'backups').glob('update-recovery-*'))
        self.assertEqual(len(recovery), 1)
        self.assertEqual(len(list(recovery[0].glob('*.tar.gz'))), 3)
        self.assertTrue((recovery[0] / 'previous-images.json').exists())
        self.assertTrue((recovery[0] / 'success').exists())
        self.assertNotIn('jellyfin', calls)
        self.assertNotIn('convertx', calls)

    def test_successful_recovery_retention(self):
        for _ in range(3):
            result, calls = self.run_update()
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        recovery = list((self.root / 'backups').glob('update-recovery-*'))
        self.assertEqual(len(recovery), 2)
        self.assertIn('docker image rm local-recovery/paperless-', calls)
        for path in recovery:
            self.assertEqual(len(list(path.glob('*.tar.gz'))), 3)

    def test_failed_start_stops_app_without_automatic_downgrade(self):
        result, calls = self.run_update(FAIL_START='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('stop paperless-ngx', calls)
        self.assertNotIn('previous-images.json up', calls)
        self.assertFalse(list((self.root / 'backups').glob('update-recovery-*/success')))

    def test_failed_package_update_does_not_stop_existing_app(self):
        result, calls = self.run_update(FAIL_APT='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('stop paperless-ngx', calls)
        self.assertNotIn(' pull\n', calls)

if __name__ == '__main__':
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo: the production entry point requires root; all external actions are mocked.')
    unittest.main()
