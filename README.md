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
# Check system compatibility first
./system/check-compatibility.sh

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

### System Requirements

#### Hardware
- Raspberry Pi 4 (4GB+ recommended) **OR** Ubuntu/Debian x86_64 system
- MicroSD card (32GB+ Class 10) for Raspberry Pi
- Stable internet connection
- Network access to NAS/file server (optional)

#### Supported Operating Systems
- **Ubuntu**: 18.04, 20.04, 22.04, 24.04 LTS
- **Debian**: 10 (Buster), 11 (Bullseye), 12 (Bookworm)
- **Raspberry Pi OS**: Based on Debian 11/12

#### Architecture Support
- **x86_64** (Intel/AMD 64-bit)
- **aarch64** (ARM 64-bit)
- **armv7l/armv6l** (ARM 32-bit)

#### Prerequisites
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Ansible
sudo apt install ansible -y

# Check system compatibility
./system/check-compatibility.sh

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

### Deployment Troubleshooting

#### Common Issues

**1. Package Not Found Error**
```bash
# Error: No package matching 'docker-compose-plugin' is available
# Solution: The playbook automatically handles this by falling back to pip installation
```

**2. Architecture Detection Issues**
```bash
# If you get "Unsupported architecture" error:
uname -m  # Check your architecture
# The playbook now supports x86_64, aarch64, armv7l, and armv6l
```

**3. WireGuard Configuration Issues**
```bash
# Check if config file exists and has correct format
sudo cat /etc/wireguard/wg0.conf
sudo systemctl status wg-quick@wg0
```

**4. SMB Mount Failures**
```bash
# Test SMB credentials manually
sudo mount -t cifs //nas-labor.fritz.box/backups /mnt/test -o credentials=/etc/smb_credentials

# Check network connectivity to NAS
ping nas-labor.fritz.box
```

**5. Docker Compose Version Issues**
```bash
# Check which version was installed
docker compose version  # V2 plugin
docker-compose --version  # V1 standalone

# Both versions are supported by the backup system
```

## Docker Service Configuration

### Hardware Acceleration Support

The Docker services (particularly Jellyfin) support flexible hardware acceleration using Docker Compose profiles. This allows you to run services with or without GPU support based on your hardware capabilities.

#### Jellyfin Hardware Acceleration

The Jellyfin service includes a GPU profile for hardware transcoding:

```bash
# Standard deployment (no GPU)
cd /home/karsten/jellyfin
docker compose up -d

# With GPU hardware acceleration
cd /home/karsten/jellyfin
docker compose --profile gpu up -d
```

#### Using the Jellyfin Management Script

A convenience script is provided for easier management:

```bash
cd /home/karsten/jellyfin

# Start without GPU
./jellyfin.sh start

# Start with GPU support
./jellyfin.sh start --gpu

# Other commands
./jellyfin.sh stop
./jellyfin.sh restart --gpu
./jellyfin.sh logs
./jellyfin.sh update --gpu
./jellyfin.sh status
```

#### GPU Prerequisites

Before using GPU acceleration, ensure:

1. **GPU drivers are installed**:
   ```bash
   # For Intel integrated graphics
   sudo apt install intel-media-va-driver
   
   # For AMD graphics
   sudo apt install mesa-va-drivers
   
   # For NVIDIA (requires NVIDIA Container Toolkit)
   # See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
   ```

2. **User is in video group**:
   ```bash
   sudo usermod -a -G video $USER
   # Log out and back in for changes to take effect
   ```

3. **GPU devices are accessible**:
   ```bash
   ls -la /dev/dri/
   # Should show render and card devices
   ```

#### Testing GPU Access

```bash
# Test GPU device access
docker run --rm --device /dev/dri:/dev/dri ubuntu:latest ls -la /dev/dri/

# Test with video group
VIDEO_GID=$(getent group video | cut -d: -f3)
docker run --rm --device /dev/dri:/dev/dri --group-add $VIDEO_GID ubuntu:latest id
```

### Backup Integration with Profiles

The Ansible backup system automatically handles Docker Compose profiles:

```bash
# Backup services (detects and preserves profile usage)
cd /home/karsten/ansible-playbooks/docker
./run-ansible.sh backup.yml

# Restore services (maintains original profile configuration)
cd /home/karsten/ansible-playbooks/docker
./run-ansible.sh restore.yml
```

The backup system preserves the Docker Compose configuration and will restore services with the same profile settings they had when backed up.

### Adding New Services

When adding new Docker services:

1. **Create service directory** under `/home/karsten/`
2. **Add to backup configuration** in `roles/docker_backup/vars/main.yml`
3. **Use profiles** for optional features (GPU, development, etc.)
4. **Follow naming conventions** for consistency

Example service structure:
```
/home/karsten/new-service/
├── docker-compose.yml          # Main service definition
├── README.md                   # Service documentation
├── .env.example               # Environment variables example
└── manage.sh                  # Optional management script
```

### Troubleshooting Docker Services

#### GPU Profile Issues

1. **"no such device" errors**:
   ```bash
   # Check if GPU devices exist
   ls -la /dev/dri/
   
   # If missing, install GPU drivers
   sudo apt update && sudo apt install intel-media-va-driver
   ```

2. **Permission denied accessing GPU**:
   ```bash
   # Check video group membership
   groups $USER | grep video
   
   # Add user to video group if missing
   sudo usermod -a -G video $USER
   ```

3. **Profile not found**:
   ```bash
   # List available profiles
   docker compose config --profiles
   
   # Check compose file syntax
   docker compose config
   ```

#### Service Communication Issues

1. **Services can't communicate**:
   - Check if services are on the same Docker network
   - Verify service names in docker-compose.yml
   - Test connectivity: `docker exec -it service1 ping service2`

2. **Port conflicts**:
   ```bash
   # Check what's using a port
   sudo netstat -tulpn | grep :8096
   
   # Kill conflicting processes if needed
   sudo kill -9 <PID>
   ```

3. **Volume mount issues**:
   ```bash
   # Check volume permissions
   ls -la /path/to/volume
   
   # Fix ownership if needed
   sudo chown -R 1000:1000 /path/to/volume
   ```