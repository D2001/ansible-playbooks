# Raspberry Pi service configuration

Versioned configuration snapshot of the running stacks under `/home/karsten`
(2026-09-18). Each subdirectory maps to the corresponding live directory.
Monitoring includes the dashboard source, collectors and Grafana provisioning;
the dashboard is part of the parent Compose project.

## Reapply on an existing host

Copy the selected files to the matching live paths, preserving executable bits
on collector scripts. Do not replace whole directories or delete untracked files.
Render the two `.j2` templates with Ansible and a privately supplied
`ex4100_snmp_community` variable, removing the `.j2` suffix at the destination.
Use mode 0600 for the rendered SNMP configuration. Never commit the rendered
files or the variable value. Existing private files can instead be retained.

The following remain private and must come from the verified backup or secret
store: Paperless `.env`, monitoring `secrets/`, Home Assistant configuration,
Node-RED data, Mosquitto configuration/data, dashboard database and Docker volumes.
Git alone is not a complete restore. Follow `../DISASTER_RECOVERY.md` for data.

Before activation, validate each stack with `docker compose config --quiet` in
its live directory. Applying Compose changes can restart containers: take a
backup first and use `docker compose up -d --build --wait` during maintenance.
Do not run Compose from this snapshot directory: that creates different projects
and uses missing private files. Existing project names and live paths must remain.

System collector unit snapshots are in `../system/files/monitoring/`; the
Paperless base unit is in `../system/files/storage/paperless.service`.
Install units under `/etc/systemd/system`, then daemon-reload and enable the
three collector timers. Storage drop-ins, updater and weekly restore verification
have separate playbooks documented in `../system/README.md`.

The active nightly backups run at 01:00 (Home Assistant), 01:20 (Paperless), and
02:00 (Monitoring); keep their existing wrapper and global lock. XMLTV and the
unused DVB-C VM were retired. Historical data deletion is deliberately not an
automatic deployment step. The former standalone dashboard Compose project must
not be recreated.
