# Onboard LAN configuration

Current topology: `eth0` is the sole active physical LAN interface; DHCP provides
192.168.0.199/24, gateway and DNS 192.168.0.1. The retired USB adapter is eth1.
The former br0/eth0 bridge is unrelated to the restore VM: restore-drill uses
libvirt's default NAT network and virbr0, which remain in place.

The onboard interface uses cloned MAC `00:E0:4C:00:F0:87` and explicit DHCP client
ID `01:00:e0:4c:00:f0:87`, preserving the USB adapter's previous DHCP identity.
The hardware MAC is `2c:cf:67:d8:08:0a`. NetworkManager supports the explicit
[cloned MAC and DHCP client ID settings](https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/nm-settings-nmcli.html).
Do not reactivate the USB adapter with its original identity while onboard-lan
is active. Remove the retired adapter after successful cutover verification.
To return to the permanent hardware MAC later, coordinate the FRITZ!Box DHCP
reservation and repeat a guarded connectivity test; do not simply remove the clone.

## Recovery

`files/network/onboard-lan.nmconnection` is the non-secret active-profile snapshot.
On a replacement host with the original host fenced off, review interface names
and DHCP identity, install the profile as root:root 0600 under
`/etc/NetworkManager/system-connections/`, run `nmcli connection reload`, then
activate `onboard-lan` from a console. Configure firewall LAN ingress for eth0.
No duplicate profile/MAC may be active on another device. Do not import all
historical bridge profiles when restoring this host.

## One-time migration tool

`files/network-cutover.py` documents and implements this host's original migration.
It is deliberately tied to the original profile UUIDs and is not a general-purpose
network deployment script. Install it beside the two firewall tools in
`/usr/local/lib/raspi/` and launch `switch` through systemd-run. It:

1. Saves original NetworkManager files, autoconnect flags and firewall chains
   root-only under `/root/network-cutover-recovery/`.
2. Creates an initially inactive DHCP profile (or reuses the verified inactive
   profile from an earlier attempt) and arms a fifteen-minute rollback.
3. Temporarily allows old and new LAN interfaces through the firewall.
4. Disables autoconnect on USB, bridge, bridge slave and the competing eth0 profile.
5. Stops the bridge and USB connection and lowers eth1 before assigning its MAC to eth0.
6. Activates onboard-lan, broadcasts ARP announcements, verifies the expected IP,
   default route and gateway; immediate failure triggers rollback.
7. Waits for independent validation and `confirm`; otherwise systemd invokes rollback.

Commands for a pending migration:

```sh
sudo python3 /usr/local/lib/raspi/network-cutover.py confirm
sudo python3 /usr/local/lib/raspi/network-cutover.py rollback
```

Rollback first removes the cloned MAC from eth0 before restarting USB and the old
bridge. Retired profiles remain disabled for recovery rather than being deleted.
After confirmation, apply the final eth0-only firewall through its guarded workflow.
The switch action refuses an active or unexpected onboard-lan profile. It can
reuse its own inactive profile after a timed rollback.

## Validation on 2026-09-20

The first attempt at 17:00 switched successfully in 1.8 seconds but automatically
rolled back at 17:05 because the user was away. This exercised the actual timed
rollback successfully. The second attempt at 19:49 again completed IP/gateway
validation in 1.8 seconds. Existing SSH sessions survived and the user confirmed
new SSH logins before the cutover was confirmed at 19:50.

Address, default route and DNS are on eth0; eth1 is down and br0 absent. The four
legacy profiles have autoconnect disabled. All 13 containers remained running,
all 14 Prometheus targets were up, and public Paperless returned HTTP 302.
The eth0-only firewall was tested in isolated namespaces, persisted and reloaded.
The network profile is persistent, but a new boot with the USB network adapter
physically removed has not yet been tested. Keep the USB storage drive attached.
