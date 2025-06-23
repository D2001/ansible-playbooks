Home Server Ansible Playbooks
=============================

This repository contains a collection of Ansible playbooks for managing a 
self-hosted Raspberry Pi server environment. It includes setup scripts, 
backup routines, and restore operations for:

1. Jellyfin (media server)
2. Paperless-ngx (document management)
3. System-level bootstrap (Docker, WireGuard, rclone)

Each section is designed for local execution on the Pi using Ansible 
(`hosts: localhost`). Most tasks run as the user `karsten`.

------------------------------------------------------------
Repository Structure
--------------------

ansible-playbooks/
├── system/
│   ├── deploy.yml
│   └── files/
│       ├── rclone.conf       ← Ansible Vault encrypted
│       └── wg0.conf          ← Ansible Vault encrypted
├── jellyfin/
│   ├── backup_jellyfin.yml
│   └── restore_jellyfin.yml
├── paperless/
│   ├── backup_paperless.yml
│   └── restore_paperless.yml
└── README.txt

------------------------------------------------------------
1. System Bootstrap (system/deploy.yml)
---------------------------------------

This playbook prepares a fresh Raspberry Pi with the following:

- Installs packages: docker.io, docker-compose, rsync, unzip, git,
  wireguard, iptables-persistent, rclone.
- Adds `karsten` to the docker group.
- Downloads rclone (CPU arch-aware).
- Installs WireGuard config (from Vault-encrypted `wg0.conf`).
- Enables IPv4 forwarding and WireGuard VPN interface.
- Uses Vault-encrypted `rclone.conf` for remote storage.

Run with:

    cd system
    ansible-playbook deploy.yml --ask-vault-pass

(Or use --vault-password-file for automation)

------------------------------------------------------------
2. Jellyfin Backup & Restore
----------------------------

Backs up and restores the Jellyfin Docker stack.

Backup:
- Stops Docker containers
- Archives ~/jellyfin into ~/jellyfin_backups/*.tar.gz
- Uploads to OneDrive (rclone)
- Keeps the latest 7 local + remote backups
- Restarts Jellyfin

Restore:
- Requires confirmation ("YES")
- Downloads latest backup from OneDrive
- Deletes existing ~/jellyfin
- Restores archive and restarts service

Usage:

    cd jellyfin
    ansible-playbook backup_jellyfin.yml
    ansible-playbook restore_jellyfin.yml

------------------------------------------------------------
3. Paperless-ngx Backup & Restore
---------------------------------

Same structure and logic as Jellyfin, using:

- /home/karsten/paperless as data dir
- ~/paperless_backups/ for archives
- onedrive:paperless_backups for remote storage

Usage:

    cd paperless
    ansible-playbook backup_paperless.yml
    ansible-playbook restore_paperless.yml

------------------------------------------------------------
Requirements
------------

- Ansible installed
- Docker and docker-compose
- rclone configured and authenticated with OneDrive
- User `karsten` must exist with sudo rights
- Ansible Vault password for decrypting system config files

------------------------------------------------------------
Backup Retention
----------------

- `max_backups` is set to 7 by default (editable in the backup playbooks).
- Applies to both local and remote (OneDrive) backups.
- Old backups are automatically pruned after each run.

------------------------------------------------------------
Security Notes
--------------

- rclone.conf and wg0.conf are encrypted with Ansible Vault.
- System Playbook will require `--ask-vault-pass`.
- Docker services are always stopped before backup/restore.
- Restore playbooks prompt for explicit confirmation to prevent data loss.

------------------------------------------------------------

Personal use only. Feel free to adapt or fork for your own homelab.
