# Docker Service Backup & Restore Playbooks

This repository provides **Ansible playbooks** to backup and restore any Dockerized service (e.g., `jellyfin`, `paperless`, etc.) on your system.  
The playbooks are fully generic: just set the `service_name` variable to match your service.

---

## Features

- **Backup**:  
  - Stops the service's Docker containers.
  - Archives the service directory.
  - Copies the backup to a local directory, an SMB/NAS share, and OneDrive (via rclone).
  - Prunes old backups locally, on NAS, and on OneDrive.
  - Restarts the Docker containers.

- **Restore**:  
  - Finds the latest backup (preferring local, then NAS, then OneDrive).
  - Optionally downloads/copies the backup to local if needed.
  - Removes the existing service directory and restores from the backup.
  - Restarts the Docker containers.

---

## Requirements

- Ansible (tested with 2.9+)
- Docker & docker-compose
- rclone (configured for OneDrive)
- SMB/NAS share mounted at `/mnt/<service_name>/backup`
- User `karsten` must have permissions for all relevant paths

---

## Usage

### 1. **Backup**

Run the backup playbook for any service (default: `temp_service`):

```bash
ansible-playbook backup.yml -e "service_name=jellyfin"
```

You can override `service_name` for any Docker service you want to back up:

```bash
ansible-playbook backup.yml -e "service_name=paperless"
```

### 2. **Restore**

**Warning:** The restore playbook will DELETE your existing service directory and replace it with the latest backup.

Run the restore playbook:

```bash
ansible-playbook restore.yml -e "service_name=jellyfin"
```

You will be prompted to confirm the restore.

---

## Customization

- **Change backup retention:**  
  Override `max_backups` (default: 7):

  ```bash
  ansible-playbook backup.yml -e "service_name=jellyfin max_backups=14"
  ```

- **Change backup locations:**  
  Edit the variables at the top of the playbooks if your paths differ.

---

## Notes

- The playbooks assume your Docker service directory is `/home/karsten/<service_name>`.
- Backups are stored locally in `/home/karsten/<service_name>_backups`, on NAS at `/mnt/<service_name>/backup`, and on OneDrive at `onedrive:<service_name>_backups`.
- The playbooks use the `karsten` user for all file operations and Docker commands.
- Ensure your rclone config and SMB mounts are working before running the playbooks.

---

## Example: Backing up and restoring "paperless"

```bash
ansible-playbook backup.yml -e "service_name=paperless"
ansible-playbook restore.yml -e "service_name=paperless"
```

---