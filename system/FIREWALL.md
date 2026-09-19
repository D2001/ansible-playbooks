# Host firewall

Applied on 2026-09-19. Source: `files/firewall-policy.py`; installer:
`firewall.yml`; guarded activation: `files/firewall-transaction.py`.

## Access policy

| Service | LAN | WireGuard | localhost |
| --- | --- | --- | --- |
| SSH 22 | yes | yes | yes |
| Home Assistant 8123 | yes | yes | yes |
| Paperless 8000 | yes | yes | yes |
| Node-RED 1880 | yes | no | yes |
| Grafana 3000 / dashboard 3080 | yes | yes | yes |
| go2rtc 18555 | yes | no | yes |
| Prometheus 9090 / exporters | no | no | yes |
| Apache 80 / retired TVHeadend / Jellyfin | no | no | Apache disabled |

LAN means `eth1` or `br0` and `192.168.0.0/24`, or IPv6 link-local `fe80::/64`.
The host address and return route are on `eth1`, but packet capture showed the
workstation's SSH packets entering via `eth0` (enslaved to `br0`). Both LAN ingress
paths must be allowed. The initial eth1-only policy broke new LAN SSH sessions;
existing sessions survived via conntrack. Do not infer ingress from the IP address
assignment or return route. The packet regression test now covers a real LAN bridge
for host access and Docker DNAT as well as the direct-interface path.
VPN means `wg0` and `10.8.0.0/24`; IPv6 VPN is not configured. No global IPv6
address was present during deployment. Review these values before replacement
hardware, interface or subnet changes. Loopback and established/related replies
are accepted. ICMP/ICMPv6 remain enabled. LAN mDNS/SSDP requests and replies,
DHCP and libvirt `virbr0` DNS/DHCP are allowed. WireGuard originates the tunnel
to the VPS with keepalives; replies use conntrack, not a fixed inbound port rule.

INPUT and FORWARD default to DROP. Docker ingress is restricted through
DOCKER-USER; allowed traffic returns to Docker's own port/isolation rules.
Container-initiated traffic retains Docker's own isolation. The implementation
uses the existing iptables-nft backend, consistent with
[Docker's packet-filtering model](https://docs.docker.com/engine/network/packet-filtering-firewalls/).
The policy assumes the current identical published/container ports 1880 and 8000.
Change rules and tests if port mappings change.

## Apply and recover

Install tools (does not activate policy):

```sh
ansible-playbook -i inventory system/firewall.yml
sudo python3 /usr/local/lib/raspi/firewall-transaction.py trial
```

The trial creates a root-only recovery directory under `/root/firewall-recovery`,
saves original rules, persistent files, Apache configuration/status and the Docker
drop-in, arms a ten-minute systemd rollback timer, changes INPUT/DOCKER-USER and
disables Apache. Other live chains/NAT are preserved. Inspect
`systemctl list-timers raspi-firewall-rollback.timer`.

Before confirming, check SSH, new LAN/VPN connections, Home Assistant, Node-RED,
public Paperless, Grafana/dashboard and Prometheus targets. A localhost request
does not establish that remote access is allowed.

```sh
sudo python3 /usr/local/lib/raspi/firewall-transaction.py confirm
# Or revert the pending trial immediately:
sudo python3 /usr/local/lib/raspi/firewall-transaction.py rollback
```

Confirm persists only the candidate policy and stops the rollback timer. Stored
rules contain no Docker/libvirt runtime networks. `netfilter-persistent` is enabled;
Docker Requires/After netfilter-persistent is installed. Both restore plugins use
NOFLUSH, and their save operations are disabled to avoid overwriting the policy
with dynamic snapshots. Reload with `sudo netfilter-persistent reload`.
Do not use `netfilter-persistent flush` or overwrite the files with iptables-save.
Dynamic obsolete rules from the old configuration remain in memory until reboot;
they are no longer present in persistent files.

For a confirmed change needing emergency recovery, use a local console, restore
`rules.v4`, `rules.v6`, `netfilter-persistent` and optional `firewall.conf` from the
chosen private recovery directory to their original paths, and daemon-reload.
`rollback.v4` and `rollback.v6` can be fed to the corresponding restore command
with `--noflush` on the same running host; they may reference live libvirt chains.
Do not blindly restore `full.v4`/`full.v6` after Docker networks have changed.
Apache can be re-enabled with `systemctl enable --now apache2` if needed.

## Verification and limits

```sh
sudo unshare --net python3 system/tests/firewall_netns.py
python3 -m unittest discover -s system/tests -p 'test_firewall*.py'
```

The packet test creates isolated client, host and container namespaces. It tests
IPv4/IPv6 allowed/blocked ports, actual DNAT forwarding, VPN restrictions and
dynamic-chain preservation across reload. Namespaces are destroyed afterwards;
the test refuses to run in PID 1's network namespace.

Production validation: rollback service successfully restored the old firewall
and Apache; subsequent trial/confirmation/reload succeeded. All 13 containers
remained running, all tested local HTTP endpoints succeeded, public Paperless
returned HTTP 302 and all Prometheus targets reported up at the final check.
No full host reboot was performed. New physical-LAN SSH access and the full boot
path require a separate check with local console access available. Home Assistant
device-specific discovery/camera functions require functional user verification.
