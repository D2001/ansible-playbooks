Paperless-ngx Backup & Restore (Ansible Playbooks)
==================================================

This directory contains two Ansible playbooks designed to manage reliable
backups and restoration of a self-hosted Paperless-ngx installation running in
Docker.

Backups are archived, stored locally, and uploaded to OneDrive using rclone.
Restoration pulls the latest archive from OneDrive and safely restores it.

------------------------------------------------------------

Playbooks Included
------------------

1. backup_paperless.yml
   - Stops the running Paperless-ngx Docker containers.
   - Archives the entire Paperless directory.
   - Uploads the archive to OneDrive using rclone.
   - Removes older local and remote backups (retains latest 7).
   - Restarts Paperless-ngx.

2. restore_paperless.yml
   - Prompts user for confirmation before proceeding.
   - Stops Paperless-ngx containers.
   - Downloads the latest backup from OneDrive.
   - Deletes the existing Paperless directory.
   - Extracts the backup archive into place.
   - Starts Paperless-ngx containers again.

------------------------------------------------------------

Requirements
------------

- Ansible installed on the local system.
- Docker and docker-compose installed.
- rclone installed and authenticated with OneDrive.
- Paperless-ngx directory located at: /home/karsten/paperless
- Backups stored at: /home/karsten/paperless_backups
- OneDrive remote configured as: onedrive:paperless_backups
- The user `karsten` must have Docker and file permissions.

------------------------------------------------------------

Usage
-----

To run a **backup**:

    ansible-playbook backup_paperless.yml

To run a **restore** (⚠ WARNING: this overwrites all current data):

    ansible-playbook restore_paperless.yml

You will be asked to confirm by typing `YES`.

------------------------------------------------------------

Backup Retention
----------------

- Keeps only the latest 7 local and remote backups by default.
- You can change this by editing the `max_backups` variable in the backup playbook.

------------------------------------------------------------

Safety Notes
------------

- Containers are stopped before backups/restores to ensure data consistency.
- All operations are performed locally (`hosts: localhost`).
- Restoration requires manual confirmation to avoid accidental data loss.

------------------------------------------------------------
