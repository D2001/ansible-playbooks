SYSTEM (Ansible Playbook)
===============================================

This Ansible playbook automates the setup and redeployment of a Raspberry Pi
server, including Docker, WireGuard, and rclone configuration.
It is intended to be run locally and includes secure handling of 
sensitive files using Ansible Vault.

------------------------------------------------------------

Project Structure
-----------------

system/
├── deploy.yml             # Main playbook
└── files/
    ├── rclone.conf        # Encrypted rclone configuration
    └── wg0.conf           # Encrypted WireGuard configuration

------------------------------------------------------------

Features
--------

- Installs essential packages: docker.io, docker-compose, rsync, wireguard, etc.
- Ensures Docker is running and adds the user 'karsten' to the docker group.
- Installs rclone with architecture detection.
- Deploys rclone config for both the user and root securely.
- Sets up and enables WireGuard VPN with the wg0 interface.
- Enables IPv4 forwarding required for VPN functionality.

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
