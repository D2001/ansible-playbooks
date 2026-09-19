#!/usr/bin/env python3
"""Render host rules; live restore touches only INPUT and DOCKER-USER."""
import argparse

LAN_INTERFACES = ('eth1', 'br0')

def render(ipv6=False, boot=False):
    lan = 'fe80::/64' if ipv6 else '192.168.0.0/24'
    lines = ['*filter', ':INPUT DROP [0:0]', ':DOCKER-USER - [0:0]']
    if boot:
        lines += [':FORWARD DROP [0:0]', ':OUTPUT ACCEPT [0:0]']
    lines += ['-F INPUT', '-F DOCKER-USER', '-A INPUT -i lo -j ACCEPT',
              '-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT']
    # ICMPv6 is required for neighbour discovery, MTU and IPv6 operation.
    lines += [f'-A INPUT -p {"ipv6-icmp" if ipv6 else "icmp"} -j ACCEPT',
              '-A INPUT -m conntrack --ctstate INVALID -j DROP']
    if not ipv6:
        lines += ['-A INPUT -i virbr0 -p udp -m multiport --dports 53,67 -j ACCEPT',
                  '-A INPUT -i virbr0 -p tcp --dport 53 -j ACCEPT']
    # The workstation enters through eth0/br0 even though the host IP is on eth1.
    for interface in LAN_INTERFACES:
        if ipv6:
            lines += [f'-A INPUT -i {interface} -s fe80::/10 -p udp --sport 547 --dport 546 -j ACCEPT']
        else:
            lines += [f'-A INPUT -i {interface} -s 192.168.0.1 -p udp --sport 67 --dport 68 -j ACCEPT']
        lines += [f'-A INPUT -i {interface} -s {lan} -p tcp -m multiport --dports 22,1880,3000,3080,8000,8123,18555 -j ACCEPT',
                  f'-A INPUT -i {interface} -s {lan} -p udp -m multiport --dports 1900,5353 -j ACCEPT',
                  f'-A INPUT -i {interface} -s {lan} -p udp -m multiport --sports 1900,5353 -j ACCEPT']
    if not ipv6:
        lines += ['-A INPUT -i wg0 -s 10.8.0.0/24 -p tcp -m multiport --dports 22,3000,3080,8000,8123 -j ACCEPT']
    # RETURN retains Docker's own port publishing/isolation decisions.
    lines += ['-A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN']
    for bridge in ('docker0', 'br-+'):
        for interface in LAN_INTERFACES:
            lines += [f'-A DOCKER-USER -i {interface} -o {bridge} -s {lan} -p tcp -m multiport --dports 1880,8000 -j RETURN']
        if not ipv6:
            lines += [f'-A DOCKER-USER -i wg0 -o {bridge} -s 10.8.0.0/24 -p tcp --dport 8000 -j RETURN']
        # Container initiated traffic stays under Docker's own isolation rules.
        lines += [f'-A DOCKER-USER -i docker0 -o {bridge} -j RETURN',
                  f'-A DOCKER-USER -i br-+ -o {bridge} -j RETURN',
                  f'-A DOCKER-USER -o {bridge} -j DROP']
    lines += ['-A DOCKER-USER -j RETURN', 'COMMIT', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ipv6', action='store_true')
    parser.add_argument('--boot', action='store_true')
    args = parser.parse_args()
    print(render(args.ipv6, args.boot), end='')
