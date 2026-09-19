# Raspberry Pi disaster recovery

Current operational runbook, reviewed 2026-09-19. Run commands from
`/home/karsten/ansible-playbooks` as `karsten` unless stated otherwise.
[Historical drill evidence](docs/RECOVERY_HISTORY_2026-09-18.md) is retained
separately; it is not the current service inventory.

## Recovery scope and inventory

| Stack | Containers | Data and dependencies |
| --- | --- | --- |
| `homeassistant` | Home Assistant, Mosquitto, Node-RED | Service directory with configuration, authentication, MQTT and Node-RED data; host `/etc/localtime`, `/run/dbus`; review hardware/integrations before starting |
| `paperless` | Paperless-ngx, PostgreSQL 16, Redis 7 | Private `.env`, four mounted named volumes, NAS `/mnt/paperless/consume` and `/mnt/paperless/export` |
| `monitoring` | Prometheus, Grafana, node-exporter, blackbox, FRITZ exporter, SNMP exporter, home dashboard | Two named volumes, exporter secrets, collector/config files, dashboard source and `home-dashboard/data/events.db` |

There are 13 active containers. XMLTV and the DVB-C VM are retired and must not
be recreated as part of recovery. The dashboard belongs to the parent Monitoring
Compose project; do not create a standalone dashboard project. The separate
`restore-drill` VM remains a disposable test environment.

Docker stores its data under `/mnt/usb/docker` on the USB ext4 filesystem.
The original host is a Raspberry Pi 5 running Debian 12 arm64. Prefer an arm64
replacement; image digests and device integrations may not work on another
architecture. The historical replacement drill used Debian 13 arm64.

Git contains code, Compose snapshots, systemd files and reapplication instructions
in [services/README.md](services/README.md) and [system/README.md](system/README.md).
It does not contain application data or plaintext credentials. Stack archives do
not constitute a host disk image: USB partitioning, boot configuration, network,
Docker daemon settings, host credentials and system schedules require separate
provisioning. Complete bare-metal recovery has not yet been rehearsed end to end.

## Backup locations, schedule and contents

For each `<service>` in `homeassistant`, `paperless`, `monitoring`:

| Destination | Path | Configured retention |
| --- | --- | --- |
| Local | `/home/karsten/backups/<service>_backups/` | 3 archives |
| NAS | `/mnt/backups/<service>/` | 30 archives |
| OneDrive | `onedrive:backups/<service>_backups` | 7 archives |

Archive names are `<service>_backup_YYYYMMDDTHHMMSS.tar.gz`. Retention settings
are in `docker/backup.yml`; recovery hard links and historical/manual copies can
make on-disk counts higher. Do not manually prune update-recovery directories
while investigating a failed update.

Systemd timers start Home Assistant at 01:00, Paperless at 01:20 and Monitoring at
02:00, Europe/Berlin. `system-update.timer` runs the guarded updater every Saturday
at 03:30; it first backs up all three stacks and aborts updates on any backup/replica
failure. The wrapper serializes backups, restore checks and the update phase using
a shared lock.

Each portable archive contains the complete service directory (including hidden
files and secrets), mounted named volumes, writable external bind data and
`backup-manifest.json`. External read-only host paths are requirements, not
included data. The stack is stopped for a consistent copy, then restarted with
up to 180 seconds of health/running-state waiting. Monitoring's SQLite database
is copied cold together with its application sources.

Archives are gzip-compressed tar files, **not client-side encrypted**. All three
stacks are authorized for the existing NAS and OneDrive destinations. Keep
archives and recovery credentials private; do not commit them to the public repo.

A failed NAS destination does not prevent the local archive or OneDrive attempt;
a failed cloud destination does not invalidate a successful NAS copy. Any enabled
destination failure still fails the job. Remote retention runs only after that
destination's verified upload. Paperless's NAS *source data* must still be
available for a complete backup, even if a backup destination is unavailable.

## Select and verify a recovery point

Use the wrapper rather than calling the Docker playbooks directly so production
operations share the lock. The following modes do not replace production data:

```sh
./docker/run-ansible.sh restore.yml -e service_name=paperless \
  -e restore_mode=validate -e restore_source=local
./docker/run-ansible.sh restore.yml -e service_name=paperless \
  -e restore_mode=portable_test -e restore_source=local
./docker/run-ansible.sh restore.yml -e service_name=paperless \
  -e restore_mode=test -e restore_source=local
```

Use `homeassistant` or `monitoring` for the first two commands. `test` is
Paperless-only: it starts an isolated PostgreSQL instance and runs SQL checks.
`portable_test` reconstructs files/temporary volumes without starting the complete
application. Monitoring validation also checks dashboard SQLite integrity/schema.
Validation uses temporary disk space and Docker tooling; it is not a zero-write
operation, even though production service data is untouched.

Sources are `local`, `nas`, `onedrive`, or `auto`. `auto` selects the newest
available candidate by filename timestamp (ties prefer local, then NAS, then
OneDrive); it does not establish that this is the desired pre-incident state.
Use an explicit source and `-e restore_file=<archive-basename>` to hold the same
recovery point across validation, plan and install. A local/NAS absolute archive
path is also supported. If validation fails, inspect the error and explicitly
select a known-good copy; do not assume automatic fallback after corruption.

New manifests record actual image IDs, registry digests and architecture.
Validation pins extracted Compose image references to recorded digests before
test/install. Legacy archives may lack version pinning. Locally built dashboard
images are rebuilt from archived source and a pinned Python base; a byte-identical
build is not guaranteed. Images themselves are not saved in the tar archive:
registry/package access or an independently populated image cache is required.

## Prepare an empty replacement host

1. Fence the failed/original host so two Home Assistant or Paperless instances
   cannot run automations, consume documents or process mail simultaneously.
   Keep backup, update and recurring restore timers disabled during recovery.
2. Provision Debian arm64 and user `karsten` (UID/GID 1000), sudo access and the
   expected network/DNS/timezone. Clone this repository at the original path.
   Have the Ansible Vault password, current SMB and rclone credentials available
   independently of the failed SD card. Existing Vault files may be older than
   live credentials; verify access rather than assuming they are current.
3. Install Docker Engine with Compose v2, Ansible and the collections used by this
   repository (`community.docker`, `community.general`), Python with PyYAML,
   rclone, CIFS tools, `pigz`, `moreutils` (`ts`) and `flock`. Ensure `karsten` can
   access Docker and the required sudo operations. The older `system/deploy.yml`
   is a provisioning aid, not a tested one-command restoration of the current host.
4. Prepare/mount the intended USB filesystem at `/mnt/usb` using its actual UUID.
   Do not format an existing recovery disk. Configure `/etc/docker/daemon.json`
   with `"data-root": "/mnt/usb/docker"`, merging any other required settings,
   before restoring volumes. Never start Docker against an unmounted fallback
   directory. An existing USB Docker data directory is not an empty target.
5. Restore `/etc/smb_credentials` with mode 0600 and private rclone configuration
   for `karsten`. Restore WireGuard/network configuration if needed for access.
   Configure the NAS shares and USB fstab entry, then apply:

   ```sh
   ansible-playbook system/storage-hardening.yml
   ```

   This requires an existing ext4 USB entry by UUID. It installs Docker/Paperless
   dependencies and NAS automount definitions; it does not mount/restart existing
   services. On the empty host activate the mounts before starting Docker. Verify
   `mountpoint -q /mnt/usb`, `docker info --format '{{.DockerRootDir}}'` and
   `findmnt -rn -t cifs --mountpoint /mnt/paperless` before installing Paperless.
6. Obtain the selected archive from the chosen source and run validation/tests.
   Allow space for the archive, extracted validation copy and restored volumes;
   compressed archive size alone is insufficient. Review the manifest's host
   paths and hardware requirements before continuing.

The three NAS shares map to `//nas-labor.fritz.box/paperless`,
`//nas-labor.fritz.box/backups` and `//nas-labor.fritz.box/Public` at
`/mnt/paperless`, `/mnt/backups` and `/mnt/public`. The reboot on 2026-09-19
verified all three automount units and CIFS mounts, USB Docker storage and healthy
Paperless startup. This test used available USB/NAS storage; behavior during a
storage outage and full bare-metal recovery remain separate tests.

## Install without starting applications

The example deliberately uses a known tested archive. Select the required
recovery point first; it may be a different file or source by the time of an
incident. Run both commands only on the intended replacement host:

```sh
./docker/run-ansible.sh restore.yml -e service_name=paperless \
  -e restore_mode=install -e restore_source=local \
  -e restore_file=paperless_backup_20260918T233043.tar.gz \
  -e restore_install_plan_only=true -e restore_install_start=false \
  -e '{"restore_install_confirm":"RESTORE paperless"}'

./docker/run-ansible.sh restore.yml -e service_name=paperless \
  -e restore_mode=install -e restore_source=local \
  -e restore_file=paperless_backup_20260918T233043.tar.gz \
  -e restore_install_start=false \
  -e '{"restore_install_confirm":"RESTORE paperless"}'
```

Repeat for the other stacks with their own archive and matching `RESTORE
homeassistant` / `RESTORE monitoring` confirmation. The role's default is to
start containers: explicitly keep `restore_install_start=false` until cut-over.

Installation restores original absolute paths from the manifest. It requires
absent/empty service and external bind directories and refuses existing required
Docker volume names. The plan does not install application data, but does download/
extract/validate as needed. Destructive in-place replacement is disabled.

**If the NAS survived and consume/export already contain files, Paperless install
will refuse those nonempty targets. Do not empty the NAS merely to pass this
check.** Reconcile surviving data and prepare an isolated empty destination or an
explicit cut-over plan. Changing `restore_install_target_dir` only relocates the
service directory; it does not rewrite absolute external bind paths. The role can
create external bind directories, so independently confirm the CIFS mount to
avoid restoring NAS data onto the SD card.

## Cut-over and restore host automation

Inspect restored Compose files, secrets, ownership, mounts, image digests and
hardware dependencies. Start one stack at a time from its original directory:

```sh
cd /home/karsten/paperless
docker compose config --quiet
docker compose up -d --wait --wait-timeout 180
docker compose ps
```

Repeat from `/home/karsten/homeassistant` and `/home/karsten/monitoring`; use
`docker compose up -d --build --wait --wait-timeout 180` for Monitoring when its
local dashboard image needs building. Keep pinned restore versions during
acceptance rather than immediately updating tags.

Check Paperless login (HTTP 302 redirect can be normal), document access and DB
counts against the selected backup; check Home Assistant integrations, MQTT and
Node-RED; check Grafana, Prometheus targets and dashboard `/health` (port 3080).
A running container without a health check is not proof of application recovery.

The stack archives do not install host systemd units or cron. After acceptance:

- Reapply host firewall policy using [system/FIREWALL.md](system/FIREWALL.md).
  First verify LAN interface/subnet, IPv6 addressing and VPN routes on the replacement.
  Install `iptables-persistent` and use a guarded trial with local console access.
  Do not restore old Docker NAT/bridge snapshots. Keep Apache disabled.

- Install the Paperless base unit from `system/files/storage/paperless.service`
  together with its storage drop-in. Install the three collector service/timer
  pairs from `system/files/monitoring/` into `/etc/systemd/system`, daemon-reload,
  and enable the Paperless service and collector timers. Restore executable bits
  on collector scripts. Do not start collectors before their scripts/data exist.
- Install the schedule units with `system/schedules.yml`. On a replacement host,
  enable the four timers only after the service directories, mounts and scripts
  are ready using `-e host_enable_schedules=true`. The additional
  `host_migrate_schedules` option is intended only for an existing host with the
  known legacy entries; it is unnecessary when the replacement has empty crontabs.
- Apply `system/restore-checks.yml` to install/enable recurring verification.
  Its persistent timer may catch up immediately.
- Apply `system/update-maintenance.yml` only after successful recovery checks and
  a fresh backup. Run `sudo /home/karsten/scripts/system-update.sh --check` before
  enabling its weekly systemd timer.
- Take fresh backups and confirm all three destinations. Reboot in a maintenance
  window to verify USB dependency, NAS automounts and service/timer startup.

The updater retains matching pre-update archives and `previous-images.json` in
private `backups/update-recovery-*` directories. It updates OS packages and
Paperless images, not Home Assistant/Monitoring images. On failed application
startup it stops Paperless and retains evidence. It does not automatically undo
database migrations, image changes or OS packages: use the matching archive and
an explicit cut-over. All current containers have bounded `local` stdout/stderr
logs (3 × 10 MB); application files inside volumes are outside those limits.

## Recurring verification and latest evidence

`restore-check.timer`: Sundays at 04:30 Europe/Berlin, random delay up to ten
minutes, persistent catch-up. Sources rotate by ISO week across local, NAS and
OneDrive; every run checks all three stacks with `portable_test` and Paperless
with `test`. A given destination is therefore exercised approximately every three
weeks. These checks are not a complete application or bare-metal drill.

```sh
/home/karsten/scripts/restore-check.py --plan
/home/karsten/scripts/restore-check.py --source local
systemctl status restore-check.timer
journalctl -u restore-check.service --no-pager -n 60
```

Results/logs: `/home/karsten/backups/restore-checks/`. Metrics:
`/home/karsten/monitoring/textfile/restore-checks.prom`. Grafana dashboard:
`Restore Verification` (`/d/restore-verification`). A failure retains the prior
success timestamp but publishes failure and returns a nonzero service exit code.

All four local checks passed on 2026-09-18 using:

| Stack | Tested archive |
| --- | --- |
| Home Assistant | `homeassistant_backup_20260918T232957.tar.gz` |
| Paperless | `paperless_backup_20260918T233043.tar.gz` |
| Monitoring | `monitoring_backup_20260918T233349.tar.gz` |

The isolated Paperless SQL check reported 404 documents and 242 migrations
for this recovery point; these are historical acceptance values, not a live count.
These archives were replicated to NAS and OneDrive. An earlier expanded Monitoring
archive also passed full replica SHA-256 readback and an isolated dashboard startup
check. The earlier Paperless KVM drill exercised application startup; Home
Assistant's replacement drill installed without starting integrations. The current
Monitoring stack has not undergone a complete replacement-host install/start drill.
See the historical record for the exact scope and PostgreSQL collation rehearsal.

Cleanup on 2026-09-19 removed retired XMLTV data, obsolete editor binaries,
Monitoring `.bak` copies and old temporary caches, freeing about 3.4 GiB.
Active configuration, service data and backup archives were retained; these
removed artifacts are not recovery prerequisites. The private removal log is
`/home/karsten/backups/cleanup-20260919.json`.
