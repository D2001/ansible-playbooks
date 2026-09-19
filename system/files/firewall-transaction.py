#!/usr/bin/env python3
"""Timed firewall trial. Confirm only after independent reachability tests."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from importlib.machinery import SourceFileLoader

POLICY = SourceFileLoader('policy', str(Path(__file__).with_name('firewall-policy.py'))).load_module()
ROOT = Path('/root/firewall-recovery')
PENDING = ROOT / 'pending'
TIMER = 'raspi-firewall-rollback'
FILES = ['/etc/iptables/rules.v4', '/etc/iptables/rules.v6',
         '/etc/default/netfilter-persistent', '/etc/systemd/system/docker.service.d/firewall.conf']


def run(*args, data=None, check=True):
    return subprocess.run(args, input=data, text=True, capture_output=True, check=check)


def saved_input(saved):
    saved = saved.split('*filter\n', 1)[1].split('\nCOMMIT', 1)[0]
    lines = ['*filter']
    for line in saved.splitlines():
        if line.startswith((':INPUT ', ':FORWARD ', ':DOCKER-USER ')):
            lines.append(line)
    lines += ['-F INPUT', '-F DOCKER-USER']
    lines += [line for line in saved.splitlines()
              if line.startswith(('-A INPUT ', '-A DOCKER-USER '))]
    return '\n'.join(lines + ['COMMIT', ''])


def rollback(folder):
    for binary, suffix in [('iptables', 'v4'), ('ip6tables', 'v6')]:
        run(binary + '-restore', '--wait', '10', '--noflush',
            data=(folder / ('rollback.' + suffix)).read_text())
    metadata = json.loads((folder / 'metadata.json').read_text())
    for path in FILES:
        target = Path(path)
        source = folder / target.name
        if source.exists():
            shutil.copy2(source, target)
        else:
            target.unlink(missing_ok=True)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable' if metadata['apache_enabled'] else 'disable', 'apache2')
    run('systemctl', 'start' if metadata['apache_active'] else 'stop', 'apache2')
    run('systemctl', 'stop', TIMER + '.timer', check=False)
    PENDING.unlink(missing_ok=True)
    print('Restored firewall files, live INPUT/DOCKER-USER chains and Apache:', folder)


def main(action):
    if os.geteuid() != 0:
        raise SystemExit('Run as root')
    ROOT.mkdir(mode=0o700, exist_ok=True)
    os.chmod(ROOT, 0o700)
    with (ROOT / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action in ('rollback', 'confirm'):
            if not PENDING.exists():
                raise SystemExit('No pending trial')
            folder = Path(PENDING.read_text())
            if action == 'rollback':
                rollback(folder)
                return
            # Commit only the already tested policy, never a snapshot of Docker NAT.
            try:
                for suffix in ('v4', 'v6'):
                    Path('/etc/iptables/rules.' + suffix).write_text((folder / ('candidate.' + suffix)).read_text())
                    os.chmod('/etc/iptables/rules.' + suffix, 0o640)
                defaults = Path('/etc/default/netfilter-persistent')
                text = defaults.read_text() if defaults.exists() else ''
                text += '\n# Managed firewall: preserve dynamic Docker/libvirt chains.\nIPTABLES_RESTORE_NOFLUSH=yes\nIP6TABLES_RESTORE_NOFLUSH=yes\nIPTABLES_SKIP_SAVE=yes\nIP6TABLES_SKIP_SAVE=yes\n'
                defaults.write_text(text)
                dropin = Path(FILES[-1])
                dropin.parent.mkdir(exist_ok=True)
                dropin.write_text('[Unit]\nRequires=netfilter-persistent.service\nAfter=netfilter-persistent.service\n')
                run('systemctl', 'daemon-reload')
                run('systemctl', 'enable', 'netfilter-persistent')
                run('systemctl', 'stop', TIMER + '.timer')
                PENDING.unlink()
                (folder / 'confirmed').touch()
                print('Confirmed and persisted:', folder)
            except Exception:
                rollback(folder)
                raise
            return
        if PENDING.exists():
            raise SystemExit('Another trial is pending; confirm or rollback first')
        folder = ROOT / time.strftime('%Y%m%dT%H%M%S')
        folder.mkdir(mode=0o700)
        for path in FILES:
            if Path(path).exists():
                shutil.copy2(path, folder / Path(path).name)
        shutil.copytree('/etc/apache2', folder / 'apache2')
        (folder / 'metadata.json').write_text(json.dumps({
            'apache_enabled': run('systemctl', 'is-enabled', 'apache2', check=False).returncode == 0,
            'apache_active': run('systemctl', 'is-active', 'apache2', check=False).returncode == 0,
        }))
        for binary, suffix in [('iptables', 'v4'), ('ip6tables', 'v6')]:
            saved = run(binary + '-save').stdout
            (folder / ('full.' + suffix)).write_text(saved)
            (folder / ('rollback.' + suffix)).write_text(saved_input(saved))
            (folder / ('candidate.' + suffix)).write_text(POLICY.render(suffix == 'v6', boot=True))
            run(binary + '-restore', '--test', '--noflush', data=POLICY.render(suffix == 'v6'))
        PENDING.write_text(str(folder))
        try:
            run('systemd-run', '--collect', '--unit=' + TIMER, '--on-active=10min',
                '/usr/bin/python3', str(Path(__file__).resolve()), 'rollback')
            for binary, ipv6 in [('iptables', False), ('ip6tables', True)]:
                run(binary + '-restore', '--wait', '10', '--noflush', data=POLICY.render(ipv6))
            run('systemctl', 'disable', '--now', 'apache2')
            print('Trial active; automatic rollback in ten minutes:', folder)
        except Exception:
            rollback(folder)
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['trial', 'confirm', 'rollback'])
    main(parser.parse_args().action)
