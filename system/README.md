SYSTEM (Ansible Playbook)
===============================================

This Ansible playbook automates the setup and redeployment of a Raspberry Pi
server, including Docker, WireGuard, rclone configuration, and SMB shares.
It also installs required Ansible collections for the backup system.
It is intended to be run locally and includes secure handling of 
sensitive files using Ansible Vault.

------------------------------------------------------------

Project Structure
-----------------

system/
├── deploy.yml             # Main playbook
└── files/
    ├── rclone.conf        # Encrypted rclone configuration
    ├── wg0.conf           # Encrypted WireGuard configuration
    └── smb_credentials    # Encrypted SMB credentials

------------------------------------------------------------

Features
--------

- **Package Installation**: Docker, WireGuard, rclone, backup tools (pigz, moreutils)
- **Docker Setup**: Ensures Docker is running and adds user to docker group
- **Ansible Collections**: Installs required collections for backup system (community.general, community.docker)
- **rclone Configuration**: Installs and configures rclone with architecture detection
- **WireGuard VPN**: Sets up and enables WireGuard with IPv4 forwarding
- **SMB Shares**: Configures and mounts NAS shares for paperless, backups, and public data
- **Security**: Uses Ansible Vault for sensitive configuration files

------------------------------------------------------------

Usage
-----

1. Ensure you have Ansible installed on the Raspberry Pi.
2. Place your encrypted `rclone.conf` and `wg0.conf` files in the `files/` directory.
3. Run the playbook with Vault password prompt:

    ansible-playbook deploy.yml --ask-vault-pass

------------------------------------------------------------

Ansible Vault
-------------

The `rclone.conf` and `wg0.conf` files are encrypted using Ansible Vault
for secure storage of credentials and keys.

To edit these files:

    ansible-vault edit files/rclone.conf
    ansible-vault edit files/wg0.conf

------------------------------------------------------------

Notes
-----

- This playbook is designed for local execution (`hosts: localhost`).
- File permissions are tightly controlled (0600 for sensitive configs).
- IPv4 forwarding is enabled for WireGuard operation.

------------------------------------------------------------

Current Raspberry Pi maintenance (2026-09-18)
------------------------------------------

`storage-hardening.yml` normalizes existing fstab entries, removes the obsolete
`/mnt/smb/public` entry and duplicate Paperless entry, and uses the private SMB
credentials file exclusively. It requires an existing USB ext4 entry by UUID.
It adds NAS automounts, permits host boot without USB/NAS, requires USB storage for
Docker, and installs the Paperless autofs trigger before Docker starts containers.
Paperless itself requires its CIFS source mount. It also waits for healthy Compose
startup. Run after provisioning the basic host and its USB filesystem:

    ansible-playbook system/storage-hardening.yml

The playbook reloads definitions without unmounting active shares. Newly introduced
automounts take effect at boot or through a controlled stop/unmount/start operation.
On 2026-09-18 the Paperless automount was activated through such a controlled switch.
Backup and Public mounts remain mounted; their automount configuration is for the
next boot. Do not restart Docker merely to apply these dependencies.

Paperless's NAS bind mounts use `create_host_path: false`, preventing Compose from
creating missing source directories. The original fstab is retained only under
`/root/storage-hardening-recovery/` with restrictive permissions.

`files/system-update.sh` is the source of `/home/karsten/scripts/system-update.sh`.
The existing root cron job calls it at midnight. `--check` is read-only. The update
workflow backs up all three active stacks through the regular backup runner first;
a backup or replica failure aborts updates. It then holds the same global lock as
backups/restores, pins old Paperless images with local recovery tags, and retains
hard links to matching pre-update archives. OS packages and Paperless images are
updated; Home Assistant and Monitoring images are not auto-updated.

Compose startup waits for health, followed by a check of every active stack.
On an application startup/health failure after recreation, the Paperless application
is stopped and recovery evidence retained. There is no automatic image downgrade:
a new application might have migrated its database. Inspect the failed service and
use the matching backup plus `previous-images.json` through the existing isolated
restore/cut-over procedure. Package upgrades themselves are not automatically undone.

Two successful recovery directories are retained. Failed runs remain available for
investigation. Old recovery image tags are removed without force; ordinary Docker
images and production volumes are not pruned. No immediate upgrade or reboot was
performed during installation of this workflow.

Tests with mocked external commands (no host package/container changes):

    sudo python3 system/tests/test_system_update.py -v

For installing the script on a replacement host, `update-maintenance.yml` also
creates its root cron job only if no existing entry calls the script, preserving
the current schedule without introducing a duplicate.

Recurring restore checks
-----------------------

Install/reapply with `ansible-playbook system/restore-checks.yml`. The weekly
`restore-check.timer` uses only isolated restore modes, rotates backup sources,
and publishes timestamp/result/duration metrics. See DISASTER_RECOVERY.md for
commands and the Grafana Restore Verification dashboard.

Versioned restores and log limits
--------------------------------

All three active Compose configurations define bounded `local` logging (3 x 10m
per container, excluding application files inside bind mounts/volumes). New backup
manifests record actual image IDs and registry digests. The restore role rewrites
only extracted Compose image references to immutable digests; production tags are
unchanged. Registry availability is still needed when the image is not cached.
Local dashboard builds retain archived sources, a pinned base image and recorded
image ID; a byte-identical rebuild is not promised.

### Versioned live service configuration

See [services/README.md](../services/README.md) for the configuration snapshots,
dashboard sources, monitoring collectors and safe reapplication instructions.
Private credentials and runtime data are intentionally recovered from backups,
not from Git; SNMP credentials use parameterized templates.
