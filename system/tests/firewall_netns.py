#!/usr/bin/env python3
"""Run with sudo unshare --net python3 ...; real packets, no host rule changes."""
import importlib.machinery
import os
from pathlib import Path
import socket
import subprocess
import time

policy = importlib.machinery.SourceFileLoader('policy', str(Path(__file__).parents[1] / 'files/firewall-policy.py')).load_module()


def run(*args, data=None):
    return subprocess.run(args, input=data, text=True, capture_output=True, check=True).stdout


def main():
    assert os.readlink('/proc/self/ns/net') != os.readlink('/proc/1/ns/net'), 'Must run in an isolated network namespace'
    children = []
    sockets = []
    try:
        for _ in range(2):
            child = subprocess.Popen(['unshare', '--net', 'sleep', '180'])
            children.append(child)
            for attempt in range(100):
                if os.readlink(f'/proc/{child.pid}/ns/net') != os.readlink('/proc/self/ns/net'):
                    break
                time.sleep(.02)
            else:
                raise RuntimeError('Child namespace not ready')
        client, container = [str(child.pid) for child in children]

        def ns(pid, *args):
            return run('nsenter', '-t', pid, '-n', *args)

        run('ip', 'link', 'set', 'lo', 'up')
        for host, peer, pid, hostip, peerip in [
            ('eth1', 'client', client, '192.168.0.199/24', '192.168.0.2/24'),
            ('br-test', 'container', container, '172.30.0.1/24', '172.30.0.2/24'),
        ]:
            run('ip', 'link', 'add', host, 'type', 'veth', 'peer', 'name', peer)
            run('ip', 'link', 'set', peer, 'netns', pid)
            run('ip', 'addr', 'add', hostip, 'dev', host)
            run('ip', 'link', 'set', host, 'up')
            ns(pid, 'ip', 'addr', 'add', peerip, 'dev', peer)
            ns(pid, 'ip', 'link', 'set', peer, 'up')
            ns(pid, 'ip', 'link', 'set', 'lo', 'up')
        ns(container, 'ip', 'route', 'add', 'default', 'via', '172.30.0.1')
        run('ip', '-6', 'addr', 'add', 'fe80::1/64', 'dev', 'eth1', 'nodad')
        ns(client, 'ip', '-6', 'addr', 'add', 'fe80::2/64', 'dev', 'client', 'nodad')
        Path('/proc/sys/net/ipv4/ip_forward').write_text('1')
        for family in (socket.AF_INET, socket.AF_INET6):
            for port in (22, 1880, 3000, 3080, 8000, 8123, 18555, 80, 9090, 9100, 9115, 9981):
                sock = socket.socket(family)
                if family == socket.AF_INET6:
                    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                sock.bind(('::' if family == socket.AF_INET6 else '0.0.0.0', port))
                sock.listen(64)
                sockets.append(sock)
        server = subprocess.Popen(['nsenter', '-t', container, '-n', 'python3', '-c',
            'import socket,time; sockets=[]\nfor p in (8000,1880):\n s=socket.socket();s.bind(("0.0.0.0",p));s.listen(64);sockets.append(s)\ntime.sleep(180)'])
        children.append(server)
        for binary, ipv6 in [('iptables', False), ('ip6tables', True)]:
            run(binary + '-restore', data=policy.render(ipv6, boot=True))
            # Simulate Docker's own dynamic forwarding rules.
            run(binary, '-A', 'FORWARD', '-j', 'DOCKER-USER')
            run(binary, '-A', 'FORWARD', '-j', 'ACCEPT')
            run(binary + '-restore', '--noflush', data=policy.render(ipv6, boot=True))
            assert '-A FORWARD -j DOCKER-USER' in run(binary, '-S', 'FORWARD')
        time.sleep(.2)

        def probe(address, port, expected, ipv6=False):
            code = 'import socket; s=socket.socket(socket.AF_INET6 if ' + repr(ipv6) + ' else socket.AF_INET); s.settimeout(.4); result=s.connect_ex(' + repr((address, port, 0, 2) if ipv6 else (address, port)) + '); print(int(result==0))'
            # Resolve scope in the client namespace instead of assuming ifindex.
            if ipv6:
                code = code.replace(repr((address, port, 0, 2)), f'({address!r},{port},0,socket.if_nametoindex("client"))')
            actual = ns(client, 'python3', '-c', code).strip() == '1'
            assert actual == expected, (address, port, actual, expected)
            print(address, port, 'allowed' if actual else 'blocked', flush=True)

        for ipv6, address in [(False, '192.168.0.199'), (True, 'fe80::1')]:
            for port in (22,1880,3000,3080,8000,8123,18555):
                probe(address, port, True, ipv6)
            for port in (80,9090,9100,9115,9981):
                probe(address, port, False, ipv6)
        for port in (8000,1880):
            run('iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp', '--dport', str(port), '-j', 'DNAT', '--to-destination', f'172.30.0.2:{port}')
            probe('192.168.0.199', port, True)
        # Regression: LAN packets can enter a bridge instead of the address's
        # original physical interface. Exercise real bridged host and DNAT paths.
        run('ip', 'link', 'add', 'br0', 'type', 'bridge')
        run('ip', 'link', 'set', 'eth1', 'master', 'br0')
        run('ip', 'addr', 'del', '192.168.0.199/24', 'dev', 'eth1')
        run('ip', 'addr', 'add', '192.168.0.199/24', 'dev', 'br0')
        run('ip', 'link', 'set', 'br0', 'up')
        for port in (22,1880,3000,3080,8000,8123,18555):
            probe('192.168.0.199', port, True)
        for port in (80,9090,9100):
            probe('192.168.0.199', port, False)
        # br0 is a LAN bridge, not a trusted Docker br-<id> interface.
        run('ip', 'addr', 'add', '198.18.0.1/24', 'dev', 'br0')
        ns(client, 'ip', 'addr', 'add', '198.18.0.2/24', 'dev', 'client')
        for port in (22,1880,8000):
            probe('198.18.0.1', port, False)
        run('ip', 'link', 'set', 'br0', 'name', 'wg0')
        run('ip', 'addr', 'add', '10.8.0.2/24', 'dev', 'wg0')
        ns(client, 'ip', 'addr', 'add', '10.8.0.3/24', 'dev', 'client')
        for port in (22,3000,3080,8000,8123):
            probe('10.8.0.2', port, True)
        for port in (1880,9090,80):
            probe('10.8.0.2', port, False)
        run('ip', 'link', 'set', 'wg0', 'name', 'untrusted')
        for port in (22,3000,8000,1880):
            probe('10.8.0.2', port, False)
        print('PASS: IPv4/IPv6 host filtering, Docker DNAT, VPN restrictions, dynamic-chain preservation')
    finally:
        for child in reversed(children):
            child.terminate()
            child.wait()
        for sock in sockets:
            sock.close()


if __name__ == '__main__':
    main()
