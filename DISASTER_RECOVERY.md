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
  install without startup, drill-safe start, HTTP check, document-count check,
  outbound block, and cleanup in the `restore-drill` VM.
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

The Paperless database restore test currently reports a PostgreSQL collation
version warning: the restored database records `2.36`, while the current
PostgreSQL image provides `2.41`. Treat this as a post-restore maintenance item.
Do not blindly refresh the recorded collation version until affected
collation-dependent objects have been reviewed and rebuilt.

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
