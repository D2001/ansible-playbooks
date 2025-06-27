# Docker Backup Role

This role handles the complete backup process for Docker services, including stopping containers, backing up volumes and service files, and restarting containers.

## Features

- Graceful container shutdown and restart
- Docker volume backup and restore
- Service directory backup
- Parallel volume processing for performance
- Error handling with guaranteed container restart
- Integration with backup_utils role for uploads

## Tasks

### main.yml
Complete backup workflow:
1. Pre-flight checks (directory and compose file existence)
2. Container shutdown
3. Volume discovery and backup
4. Service directory archiving
5. Upload to remote locations
6. Container restart

## Variables

**Required:**
- `service_name`: Name of the Docker service
- `service_dir`: Full path to the service directory
- `compose_file`: Path to docker-compose.yml file

**Optional (with defaults):**
- `backup_dir`: Local backup directory
- `backup_file`: Backup filename with timestamp
- `tar_compression_level`: Compression level (1-9, default: 1)
- `parallel_jobs`: Number of parallel backup jobs

## Usage

```yaml
- include_role:
    name: docker_backup
  vars:
    service_name: paperless
    service_dir: /home/karsten/paperless
```

## Dependencies

- backup_utils role (for upload and cleanup operations)
- Docker and docker-compose installed
- community.general collection for archive module
