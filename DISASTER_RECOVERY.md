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

`validate`, `portable_test`, and the Paperless database `test` mode are
hardened. Destructive in-place restore is intentionally disabled. The next
recovery stage will install only into an empty target directory and unused
Docker volume names; replacing an existing installation will require a
separate, explicit cut-over operation.
