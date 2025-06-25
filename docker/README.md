# Docker Service Backup & Restore System (Role-Based Architecture)

A robust, modular backup and restore system for Docker services using Ansible roles. This system provides automated backups to multiple locations (local, NAS, OneDrive) with different retention policies and seamless restoration capabilities.

## 🏗️ Architecture

### Role-Based Design
This system is now organized into reusable Ansible roles for better maintainability and modularity:

- **docker_backup**: Complete Docker service backup workflow
- **docker_restore**: Complete Docker service restore workflow  
- **backup_utils**: Shared utilities (find backups, upload, cleanup)

### Key Improvements
- **Modular**: Reusable roles that can be composed
- **Maintainable**: Clear separation of concerns
- **Testable**: Individual roles can be tested independently
- **Scalable**: Easy to extend with new functionality
- **Consistent**: Standardized variable naming and structure

## 📁 Directory Structure

```
ansible-playbooks/
├── docker/
│   ├── backup.yml          # Main backup playbook (uses roles)
│   ├── restore.yml         # Main restore playbook (uses roles)
│   ├── validate_backup.yml # Backup validation utilities
│   └── requirements.yml    # Ansible collection requirements
└── roles/
    ├── docker_backup/      # Docker backup role
    │   ├── tasks/main.yml
    │   ├── defaults/main.yml
    │   ├── meta/main.yml
    │   └── README.md
    ├── docker_restore/     # Docker restore role
    │   ├── tasks/
    │   │   ├── main.yml
    │   │   ├── prepare_restore.yml
    │   │   └── restore_data.yml
    │   ├── defaults/main.yml
    │   ├── meta/main.yml
    │   └── README.md
    └── backup_utils/       # Shared backup utilities
        ├── tasks/
        │   ├── main.yml
        │   ├── find_backup.yml
        │   ├── upload_backup.yml
        │   └── cleanup_backups.yml
        ├── defaults/main.yml
        ├── meta/main.yml
        └── README.md
```

## 🚀 Features

- **Universal**: Works with any Docker service (paperless, jellyfin, convertx, etc.)
- **Complete Backups**: Backs up entire service directory including hidden files (.env, .gitignore, etc.)
- **Docker Volume Support**: Automatically detects and backs up Docker volumes
- **Multi-Location Storage**: Stores backups locally, on NAS, and on OneDrive
- **Smart Retention**: Different retention policies for each storage location
- **Easy Restoration**: Single command to restore from the latest available backup
- **Intelligent Source Selection**: Automatically finds best available backup (local > NAS > OneDrive)
- **Comprehensive Error Handling**: Block/rescue/always patterns ensure reliability
- **Modular Design**: Role-based architecture for maintainability

## 📖 Usage

### Backup a Service

```bash
# Basic backup (uses temp_service by default)
ansible-playbook -i inventory backup.yml

# Backup specific service
ansible-playbook -i inventory backup.yml -e "service_name=paperless"

# Backup with custom retention
ansible-playbook -i inventory backup.yml -e "service_name=jellyfin max_local_backups=3"
```

### Restore a Service

```bash
# Interactive restore with confirmation
ansible-playbook -i inventory restore.yml -e "service_name=paperless"

# The restore will:
# 1. Prompt for confirmation (type YES to proceed)
# 2. Find the best available backup automatically
# 3. Stop the service gracefully
# 4. Restore all data and volumes
# 5. Start the service with health checks
```

### Validate Backups

```bash
# Check backup integrity
ansible-playbook -i inventory validate_backup.yml -e "service_name=paperless"
```

## 🔧 Configuration

### Main Variables

Configure these in your playbook or inventory:

```yaml
# Service settings
service_name: "paperless"              # Service to backup/restore
base_dir: "/home/karsten"              # Base directory for services
backup_base_dir: "/home/karsten/backups"  # Base backup directory

# Retention policies
max_local_backups: 1                   # Local backups to keep
max_onedrive_backups: 7                # OneDrive backups to keep  
max_nas_backups: 30                    # NAS backups to keep

# Performance settings
tar_compression_level: 1               # Compression level (1-9)
parallel_jobs: 2                       # Parallel operations
```

### Per-Service Customization

Each service automatically gets:
- Service directory: `{{ base_dir }}/{{ service_name }}`
- Backup directory: `{{ backup_base_dir }}/{{ service_name }}_backups`
- NAS directory: `/mnt/backups/{{ service_name }}`
- OneDrive remote: `onedrive:backups/{{ service_name }}_backups`

## 🎯 Role Details

### docker_backup Role
Handles complete backup workflow:
- Pre-flight checks
- Container shutdown
- Volume discovery and backup
- Service directory archiving
- Upload to remote locations
- Container restart

### docker_restore Role  
Handles complete restore workflow:
- Multi-source backup discovery
- Backup integrity validation
- Service directory restoration
- Docker volume restoration
- Proper cleanup

### backup_utils Role
Provides shared utilities:
- `find_backup`: Intelligent backup source selection
- `upload_backup`: Multi-destination uploads
- `cleanup_backups`: Retention policy enforcement

## 📝 Requirements

### System Requirements
- Docker and docker-compose
- rclone (configured for OneDrive)
- SMB mount capabilities
- Sufficient disk space for temporary extraction

### Ansible Requirements
Install required collections:
```bash
ansible-galaxy install -r requirements.yml
```

## 🔄 Migration from Old Structure

The system maintains backward compatibility. To migrate:

1. **Old files preserved**: Original task files are backed up as `*_old.yml`
2. **New structure active**: Main playbooks now use roles
3. **Same interface**: Commands and variables remain the same
4. **Enhanced functionality**: Better error handling and modularity

## 🐛 Troubleshooting

### Common Issues

1. **Service not found**: Ensure `service_name` matches your directory name
2. **No backups found**: Check that backup directories exist and contain files
3. **Restore fails**: Verify disk space and docker service status
4. **Upload errors**: Check rclone configuration and SMB mounts

### Logs and Debugging

- Backup logs: `{{ backup_base_dir }}/logs/{{ service_name }}_backup.log`
- Verbose output: Add `-v` or `-vvv` to ansible-playbook commands
- Container logs: `docker compose logs -f` in service directory

## 🏃‍♂️ Quick Start

1. **Configure services**: Ensure your Docker services are in `{{ base_dir }}/SERVICE_NAME/`
2. **Setup rclone**: Configure OneDrive remote as "onedrive"
3. **Mount NAS**: Ensure `/mnt/backups` is accessible
4. **Test backup**: `ansible-playbook -i inventory backup.yml -e "service_name=YOUR_SERVICE"`
5. **Test restore**: `ansible-playbook -i inventory restore.yml -e "service_name=YOUR_SERVICE"`

## 📚 Additional Documentation

- See individual role README files for detailed information
- Check `defaults/main.yml` in each role for all configurable options
- Review `meta/main.yml` for role dependencies and metadata
