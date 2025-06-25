# Docker Restore Role

This role handles the complete restore process for Docker services, including finding the best available backup, preparing the environment, and restoring both service files and Docker volumes.

## Features

- Multi-source backup discovery (local, NAS, OneDrive)
- Intelligent backup selection by modification time
- Complete service directory restoration
- Docker volume restoration
- Temporary directory management
- Comprehensive error handling and cleanup

## Tasks

### main.yml
Orchestrates the complete restore process:
1. Find best available backup
2. Prepare restore environment
3. Restore data and volumes

### prepare_restore.yml
Prepares the restore environment:
- Validates backup file integrity
- Prepares service directory
- Downloads remote backups if needed

### restore_data.yml
Performs the actual data restoration:
- Extracts backup archive
- Restores Docker volumes
- Restores service files
- Sets proper permissions

## Variables

**Required:**
- `service_name`: Name of the Docker service
- `service_dir`: Full path to the service directory
- `backup_base_dir`: Base directory for backups

**Optional (with defaults):**
- `backup_dir`: Service-specific backup directory
- `compose_file`: Path to docker-compose.yml file
- `restore_timeout`: Timeout for restore operations

## Usage

```yaml
- include_role:
    name: docker_restore
  vars:
    service_name: paperless
    service_dir: /home/karsten/paperless
```

## Dependencies

- backup_utils role (for backup discovery)
- Docker installed
- Sufficient disk space for extraction
