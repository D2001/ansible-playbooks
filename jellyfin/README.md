Jellyfin Backup & Restore (Ansible Playbooks)
=============================================

This repository contains two Ansible playbooks for automating the backup and
restoration of a Jellyfin media server running in Docker.

Both playbooks are designed to be run locally on the Jellyfin host system and
include integration with OneDrive using rclone for offsite backups.

------------------------------------------------------------

Included Playbooks
------------------

1. backup_jellyfin.yml
   - Stops the Jellyfin container.
   - Archives the entire Jellyfin directory.
   - Uploads the backup archive to OneDrive via rclone.
   - Cleans up old local and remote backups (keeps the latest 7).
   - Restarts the Jellyfin container.

2. restore_jellyfin.yml
   - Prompts user confirmation before proceeding.
   - Stops the Jellyfin container.
   - Downloads the latest backup archive from OneDrive.
   - Deletes the existing Jellyfin directory.
   - Extracts the backup archive to recreate the Jellyfin directory.
   - Restarts the Jellyfin container.

------------------------------------------------------------

Requirements
------------

- Ansible installed on the local system.
- Docker and docker-compose installed and configured for Jellyfin.
- rclone installed and authenticated with OneDrive.
- Jellyfin data located in: /home/karsten/jellyfin
- Backups stored locally at: /home/karsten/jellyfin_backups
- OneDrive remote named: onedrive:jellyfin_backups
- User: karsten must have permission to manage Docker and files.

------------------------------------------------------------

Usage
-----

To run a **backup**:

    ansible-playbook backup_jellyfin.yml

To run a **restore** (WARNING: This will overwrite existing Jellyfin data):

    ansible-playbook restore_jellyfin.yml

You will be prompted to confirm the restore operation by typing `YES`.

------------------------------------------------------------

Backup Retention
----------------

Both local and OneDrive backups are automatically pruned to keep only
the most recent 7 backups. You can adjust this by changing the `max_backups`
variable in `backup_jellyfin.yml`.

------------------------------------------------------------

Security & Data Integrity
-------------------------

- Backup archives are stored with timestamps in the filename.
- File permissions are controlled and container services are stopped during
  backup/restore to ensure consistency and prevent corruption.
- The restore process validates the presence of a backup before proceeding.

------------------------------------------------------------