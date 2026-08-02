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

Replace `paperless` with `homeassistant` to test Home Assistant, Mosquitto and
Node-RED data. The portable test creates only isolated temporary volumes. It
does not stop or modify production containers and removes its temporary data.

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
