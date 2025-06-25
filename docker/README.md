# Docker Service Backup & Restore System (Optimized)

A robust, universal backup and restore system for Docker services using Ansible playbooks. This system provides automated backups to multiple locations (local, NAS, OneDrive) with different retention policies and seamless restoration capabilities.

## 🚀 Recent Optimizations

### Performance Improvements
- **Parallel Operations**: Volume backups, uploads, and cleanups run in parallel
- **Smart Compression**: Uses `pigz` for parallel gzip compression when available
- **Async Tasks**: Non-blocking operations with proper status monitoring
- **Efficient Docker Integration**: Uses Ansible Docker modules instead of shell commands

### Reliability Enhancements
- **Error Handling**: Block/rescue/always pattern ensures containers restart even on failure
- **Pre-flight Checks**: Validates directories and files before starting
- **Backup Validation**: Verifies backup integrity and minimum file size
- **Better Resource Management**: Proper cleanup of temporary resources

### Code Quality
- **Modular Design**: Split into separate task files for better organization
- **Better Error Messages**: Detailed logging and failure reporting
- **Collection Dependencies**: Documented required Ansible collections
- **Validation Tools**: Separate playbook for backup integrity testing

## Features

- **Universal**: Works with any Docker service (paperless, jellyfin, convertx, etc.)
- **Complete Backups**: Backs up entire service directory including hidden files (.env, .gitignore, etc.)
- **Docker Volume Support**: Automatically detects and backs up Docker volumes
- **Multi-Location Storage**: Stores backups locally, on NAS, and on OneDrive
- **Smart Retention**: Different retention policies for each storage location
- **Easy Restoration**: Single command to restore from the latest available backup
- **Cron Compatible**: Perfect for automated scheduled backups
- **Comprehensive Logging**: Timestamped logs for all operations
- **Parallel Processing**: Multiple operations run simultaneously for better performance

## Architecture

### Optimized Backup Flow
1. **Pre-flight validation** (service directory, compose file existence)
2. **Parallel directory creation** (backup and NAS directories)
3. **Graceful container shutdown** using Docker Compose module
4. **Intelligent volume detection** using Docker API
5. **Parallel volume backups** with async task monitoring
6. **Efficient compression** with pigz/parallel gzip
7. **Parallel uploads** to SMB and OneDrive
8. **Concurrent cleanup** of old backups
9. **Guaranteed container restart** via always block

### Restore Flow
1. Find latest backup (priority: local > NAS > OneDrive)
2. Download backup if needed
3. Stop existing containers
4. Extract backup to temporary location
5. Restore Docker volumes if present
6. Copy all files (including hidden) to service directory
7. Start containers

## Files

- **`backup.yml`**: Main optimized backup playbook
- **`upload_backup.yml`**: Parallel upload operations
- **`cleanup_backups.yml`**: Concurrent cleanup tasks
- **`validate_backup.yml`**: Backup integrity validation
- **`restore.yml`**: Main restore playbook  
- **`run-ansible.sh`**: Wrapper script with logging and cron support
- **`requirements.yml`**: Required Ansible collections

## Prerequisites

### System Requirements
```bash
# Install required packages
sudo apt update
sudo apt install ansible docker.io docker-compose rclone moreutils pigz

# Install Ansible collections
ansible-galaxy collection install -r requirements.yml

# Ensure user is in docker group
sudo usermod -aG docker $USER
# Log out and back in for group changes to take effect
```

### OneDrive Setup
```bash
# Configure rclone for OneDrive
rclone config

# Test the connection
rclone lsf onedrive:
```

### NAS Mount
Ensure your NAS is mounted at `/mnt/backups/` or update the `nas_backup_dir` variable in the playbooks.

## Usage

### Basic Backup
```bash
# Backup a service (e.g., paperless)
./run-ansible.sh backup.yml -e "service_name=paperless"

# Or use ansible-playbook directly
ansible-playbook backup.yml -e "service_name=paperless"
```
### Basic Restore
```bash
# Restore a service (you'll be prompted to confirm)
./run-ansible.sh restore.yml -e "service_name=paperless"

# The system will automatically find the latest backup from:
# 1. Local backups (fastest)
# 2. NAS backups (if no local backup)
# 3. OneDrive backups (if no local or NAS backup)
```

### Automated Backups (Cron)
```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /home/karsten/ansible-playbooks/docker/run-ansible.sh backup.yml -e "service_name=paperless"

# Add weekly backup for jellyfin at 3 AM on Sundays
0 3 * * 0 /home/karsten/ansible-playbooks/docker/run-ansible.sh backup.yml -e "service_name=jellyfin"
```

## Configuration

### Service Structure
Your Docker services should be organized as:
```
/home/user/
├── service_1/
│   ├── docker-compose.yml
│   ├── .env
│   └── data/
├── service_2/
│   ├── docker-compose.yml
│   └── config/
└── service_3/
    ├── docker-compose.yml
    └── data/
```

### Retention Policies
The system uses different retention policies for each storage location:

- **Local**: 1 backup (immediate recovery)
- **OneDrive**: 7 backups (weekly rotation, offsite protection) 
- **NAS**: 30 backups (monthly rotation, long-term retention)

To modify these, edit the variables in `backup.yml`:
```yaml
max_local_backups: 1
max_onedrive_backups: 7
max_nas_backups: 30
```

### Storage Locations
Default storage locations (customizable in playbooks):

- **Local**: `/home/user/backups/{service_name}_backups/`
- **NAS**: `/mnt/backups/{service_name}/`
- **OneDrive**: `onedrive:{service_name}_backups/`

## What Gets Backed Up

### Complete Service Directory
- All files including hidden files (`.env`, `.gitignore`, etc.)
- Configuration files
- Data directories
- Docker Compose files
- Custom scripts

### Docker Volumes
The system automatically detects Docker volumes associated with your service and backs them up separately, then combines everything into a single archive.

### Example Backup Contents
```
paperless_backup_20250624T202002.tar.gz
├── paperless/                    # Complete service directory
│   ├── docker-compose.yml
│   ├── .env                     # Hidden files included
│   ├── data/
│   └── config/
├── paperless_db.tar.gz          # Docker volume backup
└── paperless_media.tar.gz       # Docker volume backup
```

## Logging

All operations are logged with timestamps to:
```
/home/karsten/backups/logs/{service_name}_{operation}.log
```

### Log Examples
- `paperless_backup.log` - Backup operations for paperless
- `jellyfin_restore.log` - Restore operations for jellyfin

### Viewing Logs
```bash
# View latest backup log
tail -f /home/karsten/backups/logs/paperless_backup.log

# View all logs
ls -la /home/karsten/backups/logs/
```

## Troubleshooting

### Common Issues

**1. Permission Denied**
```bash
# Ensure user is in docker group
sudo usermod -aG docker $USER
# Log out and back in

# Check docker permissions
docker ps
```

**2. rclone Not Configured**
```bash
# Configure OneDrive
rclone config

# Test connection
rclone lsf onedrive:
```

**3. NAS Mount Issues**
```bash
# Check if NAS is mounted
df -h | grep /mnt

# Mount NAS manually
sudo mount -t cifs //nas-ip/backups /mnt/backups -o credentials=/path/to/credentials
```

**4. Docker Volumes Not Found**
```bash
# List all volumes
docker volume ls

# Check if volumes are properly named
docker volume ls | grep service_name
```

### Debug Mode
Run with verbose output for troubleshooting:
```bash
./run-ansible.sh backup.yml -e "service_name=paperless" -vvv
```

## Recovery Scenarios

### Local System Failure
1. Restore from NAS: `./run-ansible.sh restore.yml -e "service_name=paperless"`
2. System will automatically detect and use NAS backup

### NAS Failure  
1. Restore from OneDrive: `./run-ansible.sh restore.yml -e "service_name=paperless"`
2. System will automatically download from OneDrive

### Complete Data Loss
1. Reinstall system and prerequisites
2. Configure rclone for OneDrive
3. Run restore playbook
4. System will download latest backup from OneDrive and restore everything

## Advanced Usage

### Manual Backup Location Override
```bash
# Force backup to specific location
ansible-playbook backup.yml -e "service_name=paperless backup_dir=/custom/path"
```

### Restore from Specific Backup
```bash
# List available backups
ls -la /home/karsten/backups/paperless_backups/
rclone ls onedrive:paperless_backups/

# The restore script always uses the latest, but you can manually place
# a specific backup in the local backup directory for restoration
```

### Service Directory Customization
```bash
# Override service directory location
ansible-playbook backup.yml -e "service_name=paperless service_dir=/custom/paperless/path"
```

## Security Considerations

- **Backup Encryption**: Consider encrypting sensitive backups before uploading to OneDrive
- **Access Control**: Ensure proper file permissions on backup directories
- **Network Security**: Use secure connections for NAS and OneDrive transfers
- **Secret Management**: Store sensitive credentials securely (e.g., in Ansible Vault)

## run-ansible.sh Wrapper Script

The `run-ansible.sh` script provides enhanced functionality:

### Features
- **Timestamped Logging**: Every line of output is timestamped
- **Cron Compatibility**: Works perfectly in cron jobs
- **Smart Defaults**: Defaults to backup.yml if no playbook specified
- **Service Detection**: Automatically detects service name from arguments
- **Error Handling**: Proper exit codes and error reporting

### Advanced Usage
```bash
# Default to backup.yml (useful for cron)
./run-ansible.sh -e "service_name=paperless"

# Specify custom playbook
./run-ansible.sh restore.yml -e "service_name=paperless"

# Multiple variables
./run-ansible.sh backup.yml -e "service_name=paperless backup_dir=/custom/path"

- **Change backup locations:**  
  Edit the variables at the top of the playbooks if your paths differ.

---

## Notes

- The playbooks assume your Docker service directory is `~/<service_name>`.
- Backups are stored locally in `~/<service_name>_backups`, on NAS at `/mnt/<service_name>/backup`, and on OneDrive at `onedrive:<service_name>_backups`.
- The playbooks use the `karsten` user for all file operations and Docker commands.
- Ensure your rclone config and SMB mounts are working before running the playbooks.

---

## Testing

### Test Backup
```bash
# Create a test service
mkdir -p /home/karsten/test_service
echo "version: '3'" > /home/karsten/test_service/docker-compose.yml
echo "TEST_VAR=test_value" > /home/karsten/test_service/.env

# Run backup
./run-ansible.sh backup.yml -e "service_name=test_service"

# Verify backup created
ls -la /home/karsten/backups/test_service_backups/
```

### Test Restore
```bash
# Remove test service
rm -rf /home/karsten/test_service

# Run restore
./run-ansible.sh restore.yml -e "service_name=test_service"

# Verify restoration
ls -la /home/karsten/test_service/
cat /home/karsten/test_service/.env
```

## Example: Backing up and restoring "paperless"

```bash
# Full backup with logging
./run-ansible.sh backup.yml -e "service_name=paperless"

# Full restore with confirmation
./run-ansible.sh restore.yml -e "service_name=paperless"
```

## Contributing

When modifying the playbooks:

1. **Test thoroughly** with a test service before using on production services
2. **Validate backup contents** by extracting and inspecting archives
3. **Test restoration** to ensure all files and volumes are properly restored
4. **Update documentation** for any configuration changes

## License

This project is provided as-is for personal and commercial use. No warranty is provided for data loss or system issues.

---

**Created by:** Karsten  
**Last Updated:** June 2025  
**Version:** 1.0.0