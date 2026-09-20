#!/usr/bin/env python3
"""One-time guarded migration from USB eth1/br0 to onboard eth0."""
import fcntl
import importlib.machinery
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import time
import sys

ROOT = Path('/root/network-cutover-recovery')
PENDING = ROOT / 'pending'
PROFILE = 'onboard-lan'
OLD = ['ae9ab1ed-33df-31c0-b592-45aea2104d36',
       'b33c93d7-5dd3-4092-ae17-ace685071be9',
       'cf824cba-ecea-4fe4-83db-f958ba361248',
       '23f31f2d-86e4-3553-9c36-315d213b55b4']
MAC = '00:e0:4c:00:f0:87'
TIMER = 'network-cutover-rollback'
HERE = Path(__file__).resolve().parent


def run(*args, check=True, data=None):
    r = subprocess.run(args, input=data, text=True, capture_output=True, timeout=75)
    if check and r.returncode:
        raise RuntimeError(f'{args}: {r.stderr}')
    return r.stdout.strip()


def announce():
    mac = bytes.fromhex(MAC.replace(':', ''))
    address = socket.inet_aton('192.168.0.199')
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0806)) as sock:
        sock.bind(('eth0', 0))
        for _ in range(3):
            for operation in (1, 2):
                arp = struct.pack('!HHBBH', 1, 0x0800, 6, 4, operation)
                arp += mac + address + bytes(6) + address
                sock.send(b'\xff'*6 + mac + b'\x08\x06' + arp)
            time.sleep(.1)


def verify():
    addresses = json.loads(run('ip', '-j', 'addr', 'show', 'eth0'))
    assert any(a.get('local') == '192.168.0.199' for a in addresses[0]['addr_info']), 'Expected DHCP address missing'
    route = json.loads(run('ip', '-j', 'route', 'get', '1.1.1.1'))[0]
    assert route['dev'] == 'eth0' and route.get('gateway') == '192.168.0.1', 'Unexpected default route'
    run('ping', '-I', 'eth0', '-c', '2', '-W', '2', '192.168.0.1')


def rollback(folder):
    # Remove the cloned MAC from eth0 before reactivating the USB adapter.
    run('nmcli', 'con', 'mod', PROFILE, 'connection.autoconnect', 'no', check=False)
    run('nmcli', '--wait', '15', 'con', 'down', PROFILE, check=False)
    run('ip', 'link', 'set', 'eth0', 'down')
    run('ip', 'link', 'set', 'eth0', 'address', '2c:cf:67:d8:08:0a')
    for uuid, value in json.loads((folder / 'autoconnect.json').read_text()).items():
        run('nmcli', 'con', 'mod', uuid, 'connection.autoconnect', value)
    run('nmcli', '--wait', '30', 'con', 'up', OLD[1])
    run('nmcli', '--wait', '30', 'con', 'up', OLD[2])
    run('nmcli', '--wait', '45', 'con', 'up', OLD[0])
    for binary, suffix in [('iptables', 'v4'), ('ip6tables', 'v6')]:
        run(binary+'-restore', '--wait', '10', '--noflush', data=(folder / ('rollback.'+suffix)).read_text())
    run('systemctl', 'stop', TIMER+'.timer', check=False)
    PENDING.unlink(missing_ok=True)
    print('Rolled back network cutover:', folder, flush=True)


def main(action):
    assert os.geteuid() == 0, 'Run as root'
    ROOT.mkdir(mode=0o700, exist_ok=True)
    os.chmod(ROOT, 0o700)
    with (ROOT / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action in ('rollback', 'confirm'):
            assert PENDING.exists(), 'No pending cutover'
            folder = Path(PENDING.read_text())
            if action == 'rollback':
                rollback(folder)
            else:
                verify()
                run('systemctl', 'stop', TIMER+'.timer')
                (folder / 'confirmed').touch()
                PENDING.unlink()
                print('Confirmed network cutover:', folder, flush=True)
            return
        assert action == 'switch'
        assert not PENDING.exists(), 'Another cutover is pending'
        assert not Path('/root/firewall-recovery/pending').exists(), 'Firewall trial pending'
        assert run('nmcli', '-g', 'GENERAL.CONNECTION', 'dev', 'show', 'eth1') == 'Wired connection 2'
        assert '192.168.0.199/24' in run('nmcli', '-g', 'IP4.ADDRESS', 'dev', 'show', 'eth1')
        assert 'eth0' in run('bridge', 'link')
        reuse = PROFILE in run('nmcli', '-g', 'NAME', 'con', 'show').splitlines()
        if reuse:
            assert PROFILE not in run('nmcli', '-g', 'NAME', 'con', 'show', '--active').splitlines(), 'Target is already active'
            assert run('nmcli', '-g', 'connection.uuid', 'con', 'show', PROFILE) == 'f67755e8-472d-4d8f-a954-5e93757b3313', 'Unexpected target profile'
        folder = ROOT / time.strftime('%Y%m%dT%H%M%S')
        folder.mkdir(mode=0o700)
        shutil.copytree('/etc/NetworkManager/system-connections', folder / 'system-connections')
        metadata = {uuid: run('nmcli', '-g', 'connection.autoconnect', 'con', 'show', uuid) for uuid in OLD}
        (folder / 'autoconnect.json').write_text(json.dumps(metadata))
        helper = importlib.machinery.SourceFileLoader('fw_transaction', str(HERE / 'firewall-transaction.py')).load_module()
        helper.POLICY.LAN_INTERFACES = ('eth0', 'eth1', 'br0')
        for binary, suffix in [('iptables', 'v4'), ('ip6tables', 'v6')]:
            saved = run(binary+'-save')
            (folder / ('full.'+suffix)).write_text(saved)
            (folder / ('rollback.'+suffix)).write_text(helper.saved_input(saved))
            run(binary+'-restore', '--test', '--noflush', data=helper.POLICY.render(suffix == 'v6'))
        setup = ('nmcli', 'con', 'mod', PROFILE) if reuse else (
            'nmcli', 'con', 'add', 'type', 'ethernet', 'con-name', PROFILE,
            'connection.uuid', 'f67755e8-472d-4d8f-a954-5e93757b3313')
        run(*setup, 'connection.interface-name', 'eth0', 'connection.autoconnect', 'no',
            '802-3-ethernet.cloned-mac-address', MAC,
            'ipv4.method', 'auto', 'ipv4.dhcp-client-id', '01:'+MAC,
            'ipv4.dhcp-timeout', '25', 'ipv4.may-fail', 'no',
            'ipv4.route-metric', '100', 'ipv6.method', 'auto')
        PENDING.write_text(str(folder))
        try:
            run('systemd-run', '--collect', '--unit='+TIMER, '--on-active=15min',
                '/usr/bin/python3', str(Path(__file__).resolve()), 'rollback')
            for binary, ipv6 in [('iptables', False), ('ip6tables', True)]:
                run(binary+'-restore', '--wait', '10', '--noflush', data=helper.POLICY.render(ipv6))
            for uuid in OLD:
                run('nmcli', 'con', 'mod', uuid, 'connection.autoconnect', 'no')
            run('nmcli', 'con', 'mod', PROFILE, 'connection.autoconnect', 'yes')
            started = time.monotonic()
            run('nmcli', '--wait', '15', 'con', 'down', OLD[2])
            run('nmcli', '--wait', '15', 'con', 'down', OLD[1])
            run('nmcli', '--wait', '15', 'con', 'down', OLD[0])
            run('ip', 'link', 'set', 'eth1', 'down')
            run('nmcli', '--wait', '40', 'con', 'up', PROFILE)
            announce()
            verify()
            print(f'Cutover validated after {time.monotonic()-started:.1f}s; awaiting confirm, rollback in fifteen minutes. Snapshot: {folder}', flush=True)
        except Exception:
            rollback(folder)
            raise


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ('switch', 'confirm', 'rollback'):
        raise SystemExit('Usage: network-cutover.py switch|confirm|rollback')
    main(sys.argv[1])
