# Historical recovery evidence through 2026-09-18

This is an archived record, not the current operating procedure. XMLTV is retired;
archive names and counts below are historical. Use [the current recovery runbook](../DISASTER_RECOVERY.md).

# Docker Disaster Recovery

The backup files are ordinary gzip-compressed tar archives. They are not
client-side encrypted. Local and NAS copies are written with restrictive file
permissions; access to remote copies is controlled by the remote provider.
This is an intentional availability-first choice: recovery does not depend on
an additional encryption key.

## What a portable backup contains

- the complete Compose service directory, including hidden files;
- every named Docker volume mounted by the running Compose project;
- every writable bind mount outside the service directory;
- `backup-manifest.json`, describing images, mounts and host requirements.

Writable bind mounts inside the service directory are already part of the
service-directory copy. Read-only paths outside it, such as `/etc/localtime`
and `/run/dbus`, are recorded as requirements of the replacement host.

## Safe verification

Archive-only validation:

```bash
ansible-playbook -i inventory docker/restore.yml \
  -e service_name=paperless \
  -e restore_mode=validate \
  -e restore_source=auto
```

Generic reconstruction test:

```bash
ansible-playbook -i inventory docker/restore.yml \
  -e service_name=paperless \
  -e restore_mode=portable_test \
  -e restore_source=auto
```

Replace `paperless` with `homeassistant` or `xmltv` for those services. The
portable test creates only isolated temporary volumes when a service has named
volumes. It does not stop or modify production containers and removes its
temporary data.

Paperless additionally supports an application-aware PostgreSQL test:

```bash
ansible-playbook -i inventory docker/restore.yml \
  -e service_name=paperless \
  -e restore_mode=test \
  -e restore_source=auto
```

## Current recovery boundary

`validate`, `portable_test`, the Paperless database `test` mode, and empty-target
`install` are hardened. Destructive in-place restore remains intentionally
disabled. Replacing an existing installation requires a separate, explicit
cut-over operation.

As of 2026-08-04, the current local backups have been verified as follows:

- Paperless: the regular backup `paperless_backup_20260804T012002.tar.gz`
  contains `backup-manifest.json`, was copied to NAS and OneDrive, passes
  `validate`, and passes the isolated PostgreSQL `test` mode with 390 documents
  and 237 migrations.
- Paperless replacement drill: `install` on a fresh Debian 13 arm64 KVM VM with
  `restore_install_start=false` successfully restored the service directory,
  four Docker volumes, and two external bind targets. A manual Compose start
  brought up PostgreSQL, Redis, and Paperless successfully; the web endpoint
  returned HTTP 302 for the login redirect and the restored database contained
  390 documents.
- Paperless drill-safe start: the generated `docker-compose.drill.yml` starts
  Paperless on an internal Docker network, exposes the login page through a
  temporary proxy on port 8000, disables restart policies, and blocks direct
  outbound network access from the Paperless container.
- Paperless repeatable KVM drill: `docker/restore-drill.sh --service paperless
  --reset-vm-target --drill-start` successfully repeated reset, install plan,
  install without startup, drill-safe start, HTTP check, restart-policy check,
  internal-network check, outbound block, and cleanup in the `restore-drill`
  VM.
- Paperless PostgreSQL collation maintenance rehearsal: the same backup was
  restored into the `restore-drill` VM, PostgreSQL was started by itself, and
  `REINDEX DATABASE paperless;` followed by
  `ALTER DATABASE paperless REFRESH COLLATION VERSION;` changed the recorded
  database collation version from `2.36` to `2.41` in about 5 seconds. The
  post-check reported `2.41`/`2.41`, 390 documents, and 237 migrations. A
  drill-safe Paperless start after the maintenance reached HTTP 302 through
  the proxy and all containers became healthy.
- Paperless production PostgreSQL collation maintenance: after creating and
  validating `paperless_backup_20260804T210244.tar.gz`, the production
  Paperless application and Redis containers were stopped while PostgreSQL
  remained healthy. `REINDEX DATABASE paperless;` followed by
  `ALTER DATABASE paperless REFRESH COLLATION VERSION;` completed in about 6
  seconds. The post-check reported `2.41`/`2.41`, 390 documents, and 237
  migrations, and the Paperless, PostgreSQL, and Redis containers returned to
  healthy status.
- Home Assistant: the regular backup
  `homeassistant_backup_20260804T010003.tar.gz` contains
  `backup-manifest.json`, was copied to NAS and OneDrive, passes `validate`,
  and passes `portable_test`.
- Home Assistant replacement drill: `docker/restore-drill.sh --service
  homeassistant --reset-vm-target` successfully repeated reset, install plan,
  and install without startup in the `restore-drill` VM for
  `homeassistant_backup_20260804T010003.tar.gz`. The restored Compose services
  are `homeassistant`, `mosquitto`, and `nodered`; `/etc/localtime` and
  `/run/dbus` replacement-host runtime requirements were present; no containers
  were started.
- XMLTV: the regular backup `xmltv_backup_20260804T014002.tar.gz` contains
  `backup-manifest.json`, was copied to NAS and OneDrive, passes `validate`,
  and passes `portable_test`.

The newer Home Assistant cron backup
`homeassistant_backup_20260803T010005.tar.gz` did not contain
`backup-manifest.json`, so it was skipped by the repeatable KVM drill. The
production checkout has since been fast-forwarded to the hardened backup code,
and the regular backup `homeassistant_backup_20260804T010003.tar.gz` contains
the portable manifest.

The Paperless database restore test initially reported a PostgreSQL collation
version warning: the restored database recorded `2.36`, while the current
PostgreSQL image provided `2.41`. This was rehearsed successfully in the
restore VM and completed in production on 2026-08-04.

PostgreSQL documents the safe order as rebuilding affected objects, for
example with `REINDEX`, then refreshing the recorded collation version with
`ALTER DATABASE ... REFRESH COLLATION VERSION`. The refresh step only updates
the catalog metadata; it does not prove that dependent objects were rebuilt.
Reference:
<https://www.postgresql.org/docs/current/sql-altercollation.html>

Use this production maintenance sequence for Paperless:

1. Confirm a fresh Paperless backup has completed and passes `validate` plus
   the Paperless database `test` mode.
2. Optionally repeat the KVM rehearsal:
   `./docker/restore-drill.sh --service paperless --reset-vm-target --drill-start`.
3. Schedule a short Paperless maintenance window.
4. Stop Paperless application writes while keeping PostgreSQL available:

   ```bash
   cd /home/karsten/paperless
   docker compose stop paperless-ngx redis
   docker compose up -d db
   ```

5. Verify the mismatch before changing it:

   ```bash
   docker compose exec -T db psql -U paperless -d paperless -X -A -F '|' \
     -c "select datcollversion, pg_database_collation_actual_version(oid) as actual from pg_database where datname=current_database();"
   ```

6. Rebuild indexes, then refresh the recorded database collation version:

   ```bash
   docker compose exec -T db psql -U paperless -d paperless -v ON_ERROR_STOP=1 \
     -c "REINDEX DATABASE paperless;" \
     -c "ALTER DATABASE paperless REFRESH COLLATION VERSION;"
   ```

7. Re-run the version and count checks:

   ```bash
   docker compose exec -T db psql -U paperless -d paperless -X -A -F '|' \
     -c "select datcollversion, pg_database_collation_actual_version(oid) as actual from pg_database where datname=current_database(); select count(*) as documents from documents_document; select count(*) as migrations from django_migrations;"
   ```

8. Start Paperless again and confirm health:

   ```bash
   docker compose up -d
   docker compose ps
   ```

## Install on a replacement client

The install mode restores to the original absolute service path recorded in a
new backup manifest. For older portable manifests without that field it falls
back to the configured `service_dir`, currently `/home/karsten/<service>`.
External writable bind mounts are restored to their original paths as well.

Always run the read-only installation plan first:

```bash
ansible-playbook -i inventory docker/restore.yml \
  -e service_name=paperless \
  -e restore_mode=install \
  -e restore_source=auto \
  -e restore_install_plan_only=true \
  -e '{"restore_install_confirm":"RESTORE paperless"}'
```

The plan and installation refuse to continue if the service directory, an
external bind target, or any required Docker volume name is already occupied.
They also verify required read-only host paths before writing data.

This refusal is expected on the existing production host for Paperless because
the production Docker volumes already exist. Use a genuinely empty replacement
host for the full Paperless plan and install test.

On a genuinely empty replacement client, remove the plan-only option:

```bash
ansible-playbook -i inventory docker/restore.yml \
  -e service_name=paperless \
  -e restore_mode=install \
  -e restore_source=auto \
  -e '{"restore_install_confirm":"RESTORE paperless"}'
```

Use `homeassistant` and `RESTORE homeassistant` for the Home Assistant stack.
Set `restore_install_start=false` to install the files and volumes without
starting containers. An alternative target is possible through
`restore_install_target_dir`, but Compose files containing absolute bind paths
must then be adjusted explicitly before startup.

For a replacement-client rehearsal, use this order:

1. Run `validate` with the intended `restore_source`.
2. Run `portable_test`.
3. Run `install` with `restore_install_plan_only=true`.
4. Run `install` with `restore_install_start=false`.
5. Inspect the restored Compose files and host bind requirements.
6. Start the service only after confirming paths, permissions, and network
   expectations.

For Paperless drills, the install workflow writes
`docker-compose.drill.yml`. It is not loaded automatically. Use it for a
controlled test start:

```bash
cd /home/karsten/paperless
docker compose -f docker-compose.yml -f docker-compose.drill.yml up -d
docker compose -f docker-compose.yml -f docker-compose.drill.yml stop
```

The drill override makes the Paperless Compose network internal, adds a
temporary proxy for browser access on port 8000, and disables container restart
policies. This limits outbound network side effects while still letting the
restored stack start for health and login-page checks.

Do not leave a restored Paperless drill instance running unless external
integrations have been reviewed. The normal application startup schedules
background jobs, including mail-account processing.

## Repeatable KVM drill

Use `docker/restore-drill.sh` to repeat the replacement-client drill against
the dedicated KVM VM. The script starts the VM when needed, syncs this checkout
and the selected portable backup into the VM, runs the install plan, runs the
actual install with `restore_install_start=false`, and can run the Paperless
drill-safe start.

Paperless end-to-end drill on the disposable VM:

```bash
./docker/restore-drill.sh \
  --service paperless \
  --reset-vm-target \
  --drill-start
```

`--reset-vm-target` is intentionally explicit. It removes the previous drill
containers, restored service directory, external bind contents, and Docker
volumes inside the configured VM based on the backup manifest. It must not be
used against a production host.

Without `--reset-vm-target`, the script is non-destructive and should fail if
the VM still contains restored service data:

```bash
./docker/restore-drill.sh --service paperless --drill-start
```


## Backup destination isolation and monitoring dashboard (2026-09-18)

A local archive is created and the service restarted before remote destinations
are checked. An unavailable NAS backup mount is recorded as a NAS failure;
OneDrive is still attempted. A OneDrive failure likewise does not invalidate a
successful NAS copy. The job returns failure when any enabled destination fails,
so partial success is never reported as complete success. Remote retention runs
independently, only after that destination's upload was verified. A missing NAS
mount is checked before creating its service directory and again before copying.

This isolates the **backup destination**. Services that read application data
from a NAS (such as Paperless consume/export) still require those source data to
be available for a complete backup.

The home dashboard now belongs to the main monitoring Compose project. It is
stopped together with monitoring before backup, so its SQLite database is cold
when copied. Its build context and database are required archive entries.
Restoring monitoring also restores and starts/builds the dashboard through the
same Compose file. New monitoring archives additionally undergo SQLite integrity
and schema checks during restore validation; older manifests without the dashboard
remain supported but do not recover it. A fresh build needs registry/package access.

Example isolated reconstruction check:

```sh
./docker/run-ansible.sh restore.yml -e service_name=monitoring \
  -e restore_mode=portable_test -e restore_source=local
```

XMLTV and the DVB-C VM were retired on 2026-09-18. Earlier XMLTV drill notes above
are historical; XMLTV is no longer in the active backup schedule.

### Verification performed on 2026-09-18

- Isolated fixture with missing NAS mount: local archive and OneDrive upload
  succeeded; overall backup correctly failed for NAS only; service restarted;
  no directory was created below the unmounted destination.
- Isolated fixture with invalid OneDrive remote: local archive and NAS upload
  succeeded; overall backup correctly failed for OneDrive only; service restarted.
- Production local monitoring backup `monitoring_backup_20260918T230206.tar.gz`
  completed, with the dashboard stopped together with the project.
- SHA-256: `f7129a37832b00bae167310ef65e827d8f84e3603a53b94fa400e2f7f6f2eaaa`.
- `portable_test` passed, including dashboard SQLite integrity/schema checks and
  reconstruction into isolated Docker volumes; production volumes were untouched.
- Dashboard built from archived sources and started against the copied database
  with `--network none`, no published ports and no restart policy: HTTP health
  returned 200 and SQLite integrity passed. The test container was removed.
- Production dashboard health and status API returned HTTP 200 after backup.


### Replica verification and host maintenance follow-up

The user explicitly approved exporting the expanded monitoring archive, including
dashboard data and existing monitoring credentials, to the existing NAS and
OneDrive destinations for this and future scheduled backups. The archive
`monitoring_backup_20260918T230206.tar.gz` was copied successfully to both targets.
A full readback of each target matched its local SHA-256 checksum recorded above.
The existing nightly backup schedule remains in force without a cloud exclusion.

Storage and update hardening are now described in `system/README.md` and can be
reapplied using `system/storage-hardening.yml` and `system/update-maintenance.yml`.
These targeted playbooks supplement the older host deployment; they do not by
themselves constitute a complete tested bare-metal recovery procedure.


### Runtime image versions and recurring verification

New manifests record the actual running container image ID, available repository
digests, OS and architecture. Archive validation pins the **extracted** Compose
file to those digests before any application test or installation. Production
Compose files keep their existing update policy. Legacy archives remain supported
without retroactively claiming image pinning. Local builds without registry digests
are reconstructed from archived sources; their image ID is recorded for comparison.
The dashboard Dockerfile now pins the Python base image by digest, but rebuilding
local images is not guaranteed to be bit-for-bit identical.

All active Compose services use the Docker `local` logging driver with `max-size`
10m and `max-file` 3. These limits apply to container stdout/stderr logs, not to
application log files written into volumes. Backup restart now waits up to 180
seconds for configured container health checks (or running state if none exists).

`restore-check.timer` runs Sundays at 04:30 with up to ten minutes of jitter and
persistent catch-up. Each week selects one source, rotating local/NAS/OneDrive.
It runs portable reconstruction for all three stacks and additionally the isolated
Paperless PostgreSQL test. These modes do not start the production application or
modify its volumes. The standard backup wrapper provides serialization with
backups and updates. Manual checks:

```sh
/home/karsten/scripts/restore-check.py --plan
/home/karsten/scripts/restore-check.py --source local
```

Latest per-source/mode logs and status are under `backups/restore-checks/`.
Prometheus reads `monitoring/textfile/restore-checks.prom`; Grafana provisions the
`Restore Verification` dashboard. A failed check preserves its previous success
timestamp, publishes failure and gives the systemd service a nonzero exit status.
The scheduler can be reinstalled with `system/restore-checks.yml`.

The user has explicitly approved transferring **all backup archives** to the
existing backup destinations. This includes Home Assistant, Paperless and Monitoring,
and applies to subsequent runs; the earlier scope restriction is resolved.


### Verification of the next hardening stage (2026-09-18)

- All 13 running service containers were inspected after their backup restart:
  logging driver `local`, `max-size=10m`, `max-file=3` were active.
- New Home Assistant and Paperless archives each record three immutable runtime
  image references. The new Monitoring archive records registry digests for its
  six external images and the local dashboard image ID.
- Fresh archives for all three stacks completed and were replicated successfully
  to the existing NAS and OneDrive targets after explicit approval of all archives.
- Four restore-image helper tests and three restore-check scheduler/state tests
  passed, including legacy compatibility, invalid-reference refusal and preservation
  of the previous success timestamp on failure.
- The scheduled first weekly check is 2026-09-20 around 04:30 CEST (random jitter).

- The first complete local restore sweep passed all four checks: Home Assistant
  portable reconstruction, Paperless portable reconstruction, Paperless isolated
  PostgreSQL startup/SQL validation, and Monitoring portable reconstruction with
  dashboard SQLite integrity. All checks used the newly versioned archives.
- The Grafana dashboard was verified in the active `resource` storage table
  (the legacy `dashboard` table is no longer authoritative on this installation).
