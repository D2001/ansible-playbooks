SYSTEM (Ansible Playbook)
===============================================

This Ansible playbook automates the setup and redeployment of a Raspberry Pi
server, including Docker, WireGuard, rclone configuration, and SMB shares.
It also installs required Ansible collections for the backup system.
It is intended to be run locally and includes secure handling of 
sensitive files using Ansible Vault.

------------------------------------------------------------

Project Structure
-----------------

system/
├── deploy.yml             # Main playbook
└── files/
    ├── rclone.conf        # Encrypted rclone configuration
    ├── wg0.conf           # Encrypted WireGuard configuration
    └── smb_credentials    # Encrypted SMB credentials

------------------------------------------------------------

Features
--------

- **Package Installation**: Docker, WireGuard, rclone, backup tools (pigz, moreutils)
- **Docker Setup**: Ensures Docker is running and adds user to docker group
- **Ansible Collections**: Installs required collections for backup system (community.general, community.docker)
- **rclone Configuration**: Installs and configures rclone with architecture detection
- **WireGuard VPN**: Sets up and enables WireGuard with IPv4 forwarding
- **SMB Shares**: Configures and mounts NAS shares for paperless, backups, and public data
- **Security**: Uses Ansible Vault for sensitive configuration files

------------------------------------------------------------

Usage
-----

1. Ensure you have Ansible installed on the Raspberry Pi.
2. Place your encrypted `rclone.conf` and `wg0.conf` files in the `files/` directory.
3. Run the playbook with Vault password prompt:

    ansible-playbook deploy.yml --ask-vault-pass

------------------------------------------------------------

Ansible Vault
-------------

The `rclone.conf` and `wg0.conf` files are encrypted using Ansible Vault
for secure storage of credentials and keys.

To edit these files:

    ansible-vault edit files/rclone.conf
    ansible-vault edit files/wg0.conf

------------------------------------------------------------

Notes
-----

- This playbook is designed for local execution (`hosts: localhost`).
- File permissions are tightly controlled (0600 for sensitive configs).
- IPv4 forwarding is enabled for WireGuard operation.

------------------------------------------------------------
