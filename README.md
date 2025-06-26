# Ansible Infrastructure & Backup System

A comprehensive Ansible-based system for deploying Raspberry Pi infrastructure and managing Docker service backups. This project provides both system deployment capabilities and a robust backup/restore system using a modular role-based architecture.

## 🏗️ Project Structure

```
ansible-playbooks/
├── ansible.cfg                    # Ansible configuration
├── inventory                      # Host inventory
├── system/                        # System deployment
│   ├── deploy.yml                 # Main system deployment playbook
│   ├── files/                     # Configuration files
│   │   ├── wg0.conf               # WireGuard configuration
│   │   ├── smb_credentials        # SMB mount credentials
│   │   └── rclone.conf            # rclone configuration
│   └── README.md                  # System deployment documentation
├── docker/                        # Docker backup system
│   ├── backup.yml                 # Main backup playbook
│   ├── restore.yml                # Main restore playbook
│   ├── run-ansible.sh             # Wrapper script with logging
│   ├── check-compatibility.sh     # System compatibility checker
│   └── README.md                  # Docker backup documentation
└── roles/                         # Ansible roles
    ├── docker_backup/             # Docker backup role
    │   ├── tasks/
    │   │   ├── main.yml           # Main backup workflow
    │   │   ├── upload_backup.yml  # Upload to remote locations
    │   │   └── cleanup_backups.yml # Backup retention cleanup
    │   ├── defaults/main.yml      # Default variables
    │   ├── meta/main.yml         # Role metadata
    │   └── README.md             # Role documentation
    └── docker_restore/            # Docker restore role
        ├── tasks/
        │   ├── main.yml           # Main restore orchestration
        │   ├── prepare_restore.yml # Restore preparation
        │   └── restore_data.yml   # Data restoration
        ├── defaults/main.yml      # Default variables
        ├── meta/main.yml         # Role metadata
        └── README.md             # Role documentation
```

## 🚀 Quick Start

### 1. Clone and Setup
```bash
git clone <repository-url>
cd ansible-playbooks

# Make scripts executable
chmod +x docker/run-ansible.sh
chmod +x docker/check-compatibility.sh
```

### 2. System Deployment (Optional)
```bash
# Deploy complete Raspberry Pi infrastructure
sudo ansible-playbook system/deploy.yml
```

### 3. Docker Service Backup
```bash
# Backup a Docker service
./docker/run-ansible.sh backup.yml -e "service_name=paperless"

# Restore a Docker service
./docker/run-ansible.sh restore.yml -e "service_name=paperless"
```

## 📋 Quick Reference

### Common Commands
```bash
# System deployment
sudo ansible-playbook system/deploy.yml --ask-vault-pass

# Backup operations
./docker/run-ansible.sh -e "service_name=paperless"                    # Daily backup
./docker/run-ansible.sh backup.yml -e "service_name=jellyfin"          # Explicit backup
./docker/run-ansible.sh backup.yml -e "service_name=convertx" --check  # Dry run

# Restore operations
./docker/run-ansible.sh restore.yml -e "service_name=paperless"        # Interactive restore
./docker/run-ansible.sh restore.yml -e "service_name=jellyfin" -vvv    # Verbose restore

# Monitoring
tail -f /home/karsten/backups/logs/paperless_backup.log                # Live log
ls -la /home/karsten/backups/paperless_backups/                        # Local backups
docker ps --format "table {{.Names}}\t{{.Status}}"                    # Container status
```

### Cron Setup
```bash
# Environment
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
HOME=/home/karsten
# Daily backups
0 2 * * * /home/karsten/ansible-playbooks/docker/run-ansible.sh -e "service_name=paperless"
0 3 * * 0 /home/karsten/ansible-playbooks/docker/run-ansible.sh -e "service_name=jellyfin"
```

---

## 🖥️ System Deployment

The system deployment module sets up a complete Raspberry Pi infrastructure with Docker, WireGuard VPN, and SMB mounts.

### What Gets Deployed

#### Core Services
- **Docker & Docker Compose**: Container orchestration
- **WireGuard VPN**: Secure remote access
- **SMB/CIFS Mounts**: NAS integration for backups
- **rclone**: OneDrive/cloud storage integration

#### Storage Integration
- **NAS Mounts**: Automatic SMB share mounting
  - `/mnt/paperless` - Paperless document storage
  - `/mnt/backups` - Backup storage
  - `/mnt/public` - General file sharing


#### Prerequisites
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Ansible
sudo apt install ansible -y

# Ensure user has sudo privileges
sudo usermod -aG sudo $USER
```

### Configuration Files

Before deployment, ensure these files are configured:

#### `/system/files/wg0.conf`
```ini
[Interface]
PrivateKey = <your-private-key>
Address = 10.0.0.2/24
DNS = 1.1.1.1

[Peer]
PublicKey = <peer-public-key>
Endpoint = <vpn-server>:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
```

#### `/system/files/smb_credentials`
```ini
username=<nas-username>
password=<nas-password>
domain=<domain>
```

#### `/system/files/rclone.conf`
```ini
[onedrive]
type = onedrive
# ... OneDrive configuration
```

### Running System Deployment

```bash
# Full system deployment
sudo ansible-playbook system/deploy.yml

# Check deployment status
systemctl status docker
systemctl status wg-quick@wg0
df -h | grep /mnt
```

### Post-Deployment Verification

```bash
# Verify Docker
docker --version
docker compose version

# Verify WireGuard
sudo wg show

# Verify mounts
mount | grep cifs

# Verify rclone
rclone about onedrive:
```

---

## 🐳 Docker Backup & Restore System

A sophisticated, role-based backup system for Docker services with multi-location storage and automated retention policies.

### Architecture Overview

#### Role-Based Design
- **`docker_backup`**: Handles complete service backup including volumes and multi-location uploads
- **`docker_restore`**: Manages restoration from any backup location with intelligent source discovery

#### Backup Locations & Retention
- **Local**: 1 backup (immediate recovery)
- **OneDrive**: 7 backups (offsite protection)
- **NAS**: 30 backups (long-term retention)

### Backup Process Flow

1. **Pre-flight Checks**
   - Verify service directory exists
   - Check docker-compose.yml is present
   - Ensure backup directories are accessible

2. **Container Management**
   - Gracefully stop Docker containers
   - Wait for clean shutdown

3. **Volume Detection & Backup**
   - Auto-detect Docker volumes for the service
   - Create individual volume backups
   - Generate compressed archives

4. **Service Directory Backup**
   - Archive entire service directory
   - Include hidden files (.env, .gitignore)
   - Preserve file permissions

5. **Multi-Location Storage**
   - Store locally for immediate access
   - Upload to NAS for network backup
   - Sync to OneDrive for offsite protection

6. **Cleanup & Recovery**
   - Remove old backups per retention policy
   - Restart Docker containers
   - Verify service health

### Restore Process Flow

1. **Backup Discovery**
   - Search local backups first
   - Check NAS if no local backup
   - Download from OneDrive if needed

2. **Safety Measures**
   - Interactive confirmation prompt
   - Create emergency backup of existing data
   - Validate backup file integrity

3. **Service Restoration**
   - Stop existing containers
   - Remove old service directory (with sudo for Docker-created files)
   - Extract backup to temporary location

4. **Data Recovery**
   - Restore Docker volumes using Alpine containers
   - Copy service files with proper permissions
   - Set correct ownership (karsten:karsten)

5. **Service Restart**
   - Start containers with health checks
   - Verify container status
   - Wait for services to be ready

### Supported Docker Services

The system works with any Docker service that follows standard conventions:

#### Service Structure
```
/home/karsten/<service_name>/
├── docker-compose.yml          # Required
├── .env                       # Environment variables
├── data/                      # Application data
├── config/                    # Configuration files
└── custom-scripts/            # Custom scripts
```

#### Volume Naming
Docker volumes should follow the pattern: `<service_name>_<volume_name>`

Examples:
- `paperless_data`
- `paperless_media`
- `jellyfin_config`
- `jellyfin_cache`

### Usage Examples

#### Basic Operations
```bash
# Backup paperless service
./docker/run-ansible.sh backup.yml -e "service_name=paperless"

# Restore paperless service
./docker/run-ansible.sh restore.yml -e "service_name=paperless"

# Backup jellyfin service
./docker/run-ansible.sh backup.yml -e "service_name=jellyfin"
```

#### Advanced Operations
```bash
# Backup with custom retention
ansible-playbook docker/backup.yml -e "service_name=paperless max_local_backups=3"

# Check mode (dry run)
./docker/run-ansible.sh backup.yml -e "service_name=paperless" --check

# Verbose output for debugging
./docker/run-ansible.sh backup.yml -e "service_name=paperless" -vvv
```

### The run-ansible.sh Wrapper

The `run-ansible.sh` script provides crucial functionality for reliable operation:

#### Features
- **Cron Compatibility**: Sets environment variables and working directory
- **Intelligent Path Handling**: Resolves playbook paths (relative/absolute)
- **Service Name Detection**: Extracts service name from command arguments
- **Timestamped Logging**: Every log line includes timestamp
- **Log Rotation**: Automatically keeps last 1000 lines per log file
- **Error Handling**: Captures and logs exit codes

#### Usage Patterns
```bash
# Simple backup (defaults to backup.yml)
./run-ansible.sh -e "service_name=paperless"

# Explicit playbook
./run-ansible.sh backup.yml -e "service_name=paperless"

# From any directory (absolute path)
/home/karsten/ansible-playbooks/docker/run-ansible.sh restore.yml -e "service_name=jellyfin"

# With additional ansible arguments
./run-ansible.sh backup.yml -e "service_name=paperless" --check -vvv
```

### Automated Backups (Cron)

#### Setup Cron Jobs
```bash
# Edit crontab
crontab -e

# Daily paperless backup at 2 AM
0 2 * * * /home/karsten/ansible-playbooks/docker/run-ansible.sh -e "service_name=paperless"

# Weekly jellyfin backup at 3 AM on Sundays
0 3 * * 0 /home/karsten/ansible-playbooks/docker/run-ansible.sh -e "service_name=jellyfin"

# Monthly convertx backup at 4 AM on 1st day of month
0 4 1 * * /home/karsten/ansible-playbooks/docker/run-ansible.sh -e "service_name=convertx"
```

#### Cron Troubleshooting
The `run-ansible.sh` script is specifically designed for cron compatibility:
- Sets proper environment variables
- Uses absolute paths
- Changes to correct working directory
- Provides comprehensive logging

### Logging & Monitoring

#### Log Locations
```
/home/karsten/backups/logs/
├── paperless_backup.log        # Paperless backup operations

```

#### Log Features
- **Timestamped entries**: Every line includes timestamp
- **Automatic rotation**: Keeps last 1000 lines per log
- **Structured output**: Clear operation status and errors
- **Debug information**: Environment variables for cron debugging

#### Monitoring Commands
```bash
# Watch live backup operation
tail -f /home/karsten/backups/logs/paperless_backup.log

# Check recent backup status
grep "completed with exit code" /home/karsten/backups/logs/*_backup.log

# View all backup files
ls -la /home/karsten/backups/*/
```

### Configuration & Customization

#### Variables (defaults/main.yml)
```yaml
# Storage locations
base_dir: "/home/karsten"
backup_base_dir: "{{ base_dir }}/backups"
nas_backup_dir: "/mnt/backups/{{ service_name }}"
rclone_remote: "onedrive:backups/{{ service_name }}_backups"

# Retention policies
max_local_backups: 1
max_onedrive_backups: 7
max_nas_backups: 30

# Performance settings
tar_compression_level: 1
parallel_jobs: "{{ ansible_processor_vcpus | default(2) }}"

# Timeout settings
backup_timeout: 1800
restore_timeout: 300
health_check_retries: 30
```

#### Custom Service Configuration
```bash
# Override service directory
ansible-playbook docker/backup.yml -e "service_name=custom service_dir=/opt/custom"

# Custom backup location
ansible-playbook docker/backup.yml -e "service_name=test backup_dir=/tmp/test_backups"

# Custom retention policy
ansible-playbook docker/backup.yml -e "service_name=important max_local_backups=5"
```

### Error Handling & Recovery

#### Backup Failures
- **Automatic container restart**: Containers are restarted even if backup fails
- **Partial backup protection**: Creates backup only if all components succeed
- **Detailed error logging**: Full error context in logs

#### Restore Failures
- **Emergency backup**: Creates emergency backup before restore
- **Automatic fallback**: Falls back to emergency backup on failure
- **Safe directory handling**: Uses sudo for Docker-created files

#### Common Issues & Solutions

**Permission Denied (Docker files)**
```bash
# The system automatically handles this with sudo commands
# No manual intervention required
```

**rclone Configuration Missing**
```bash
# Configure OneDrive
rclone config

# Test connection
rclone ls onedrive:
```

**NAS Mount Failed**
```bash
# Check SMB credentials
sudo cat /etc/smb_credentials

# Remount manually
sudo mount -a

# Check mounts
df -h | grep /mnt
```

**Docker Volume Not Found**
```bash
# List volumes for service
docker volume ls | grep service_name

# Check volume naming convention
# Should be: service_name_volume_name
```

### Security Considerations

#### File Permissions
- All backups created with `karsten:karsten` ownership
- Backup directories have `755` permissions
- SMB credentials secured with `600` permissions

#### Network Security
- rclone uses OAuth2 for OneDrive authentication
- SMB connections use credential files
- WireGuard provides VPN tunnel for remote access

#### Backup Encryption
Consider encrypting sensitive backups:
```bash
# Encrypt backup before upload
gpg --symmetric --cipher-algo AES256 backup.tar.gz

# Decrypt on restore
gpg --decrypt backup.tar.gz.gpg > backup.tar.gz
```

### Testing & Validation

#### Backup Testing
```bash
# Create test service
mkdir -p /home/karsten/test_service
echo "version: '3'" > /home/karsten/test_service/docker-compose.yml
echo "TEST=value" > /home/karsten/test_service/.env

# Run backup
./docker/run-ansible.sh backup.yml -e "service_name=test_service"

# Verify backup
ls -la /home/karsten/backups/test_service_backups/
```

#### Restore Testing
```bash
# Remove test service
rm -rf /home/karsten/test_service

# Run restore
./docker/run-ansible.sh restore.yml -e "service_name=test_service"

# Verify restoration
ls -la /home/karsten/test_service/
cat /home/karsten/test_service/.env
```

#### Integration Testing
```bash
# Check system compatibility
./docker/check-compatibility.sh

# Verify all components
docker --version
rclone version
ansible --version
```

### Performance Optimization

#### Backup Speed
- **Fast compression**: Uses compression level 1 for speed
- **Parallel operations**: Uploads to multiple destinations simultaneously
- **Incremental approaches**: Only backs up when changes detected

#### Storage Efficiency
- **Smart retention**: Different policies for different storage tiers
- **Compression**: All backups are gzipped
- **Cleanup automation**: Automatic removal of old backups

### Migration & Updates

#### Updating the System
```bash
# Update system components
sudo ansible-playbook system/deploy.yml

# Update backup system
git pull origin main
```

#### Migrating Services
```bash
# Backup on old system
./docker/run-ansible.sh backup.yml -e "service_name=paperless"

# Copy backup to new system or rely on OneDrive sync

# Restore on new system
./docker/run-ansible.sh restore.yml -e "service_name=paperless"
```

---

## 🔧 Maintenance & Operations

### Regular Maintenance Tasks

#### Weekly
- Check backup logs for failures
- Verify OneDrive sync status
- Monitor disk space usage

#### Monthly
- Test restore process on non-critical service
- Review and update retention policies
- Check system updates

#### Quarterly
- Full disaster recovery test
- Review and update documentation
- Security audit of credentials

### Monitoring Commands

```bash
# Check backup status
find /home/karsten/backups -name "*.tar.gz" -mtime -7 | wc -l

# Disk space monitoring
df -h | grep -E "(backups|mnt)"

# Service health
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Log analysis
grep -i error /home/karsten/backups/logs/*.log
```

### Troubleshooting Guide

#### Common Error Patterns
- `Permission denied`: Docker file ownership issues (handled automatically)
- `Role not found`: Working directory or roles_path configuration
- `Connection failed`: Network/mount issues
- `Volume not found`: Docker volume naming convention

#### Debug Mode
```bash
# Enable maximum verbosity
./docker/run-ansible.sh backup.yml -e "service_name=test" -vvv

# Check environment variables
cat /home/karsten/backups/logs/cron_env.log

# Validate configuration
ansible-config dump
```

---

## 📚 Documentation

- **System Deployment**: See `system/README.md` for detailed deployment instructions
- **Docker Backup**: See `docker/README.md` for backup system specifics
- **Role Documentation**: Each role contains its own `README.md` with detailed usage

---

## 🤝 Contributing

1. **Test Changes**: Always test with non-critical services first
2. **Documentation**: Update relevant README files
3. **Validation**: Run `ansible-playbook --syntax-check` before committing
4. **Testing**: Use `--check` mode for dry runs

---

## 📄 License

This project is provided as-is for personal and commercial use. No warranty is provided for data loss or system issues.

---

**Project Maintainer**: Karsten  
**Last Updated**: June 2025  
**Version**: 2.0.0 (Role-based Architecture)