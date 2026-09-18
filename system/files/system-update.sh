#!/usr/bin/env bash
# Cron entry point. --check is read-only; default performs backed-up updates.
set -Eeuo pipefail

BASE_DIR=/home/karsten
BACKUP_RUNNER="$BASE_DIR/ansible-playbooks/docker/run-ansible.sh"
BACKUP_SERVICES=(homeassistant paperless monitoring)
# Preserve the existing update scope: only Paperless images are auto-updated.
UPDATE_PROJECT=paperless
CHECK_ONLY=false
RECOVERY_DIR=
CONTAINERS_CHANGED=false

log() { printf '[%(%F %T)T] %s\n' -1 "$*"; }
fail() { log "ERROR: $*" >&2; exit 1; }

case "${1:-}" in
    --check) CHECK_ONLY=true ;;
    '') ;;
    *) fail "Usage: $0 [--check]" ;;
esac
[[ $# -le 1 ]] || fail "Too many arguments"

preflight() {
    for cmd in docker mountpoint findmnt flock runuser python3 apt-get; do
        command -v "$cmd" >/dev/null || fail "Required command missing: $cmd"
    done
    [[ -x "$BACKUP_RUNNER" ]] || fail "Backup runner missing"
    mountpoint -q /mnt/usb || fail "Docker storage /mnt/usb is not mounted"
    findmnt -rn -t cifs --mountpoint /mnt/paperless >/dev/null ||
        fail "Paperless source /mnt/paperless is not mounted as CIFS"
    for service in "${BACKUP_SERVICES[@]}"; do
        [[ -f "$BASE_DIR/$service/docker-compose.yml" ]] ||
            fail "Compose configuration missing for $service"
        docker compose --project-directory "$BASE_DIR/$service" config --quiet
    done
    python3 - <<'PY'
import json, subprocess
for project in ('homeassistant', 'paperless', 'monitoring'):
    ids = subprocess.check_output(['docker', 'compose', '--project-directory',
                                  '/home/karsten/' + project, 'ps', '-a', '-q'], text=True).split()
    declared = subprocess.check_output(['docker', 'compose', '--project-directory',
                                       '/home/karsten/' + project, 'config', '--services'], text=True).split()
    containers = json.loads(subprocess.check_output(['docker', 'inspect', *ids])) if ids else []
    actual = {c['Config']['Labels']['com.docker.compose.service'] for c in containers}
    if not set(declared).issubset(actual):
        raise SystemExit('Missing containers in ' + project)
    for c in containers:
        state = c['State']
        if not state['Running'] or state.get('Health', {}).get('Status', 'healthy') != 'healthy':
            raise SystemExit('Unhealthy container: ' + c['Name'])
print('All declared services are running; configured health checks passed')
PY
}

on_failure() {
    local rc=$?
    trap - ERR
    log "ERROR: Update failed (exit $rc). Recovery metadata: ${RECOVERY_DIR:-not created}"
    if [[ "$CONTAINERS_CHANGED" == true ]]; then
        # A new application may have migrated its DB: do not auto-downgrade images.
        docker compose --project-directory "$BASE_DIR/$UPDATE_PROJECT" stop paperless-ngx || true
        log "Paperless application stopped after failed update; inspect logs and restore the matching pre-update data before an image downgrade."
    fi
    exit "$rc"
}
trap on_failure ERR

preflight
if [[ "$CHECK_ONLY" == true ]]; then
    log "Read-only check passed. Update scope: OS packages and Paperless images. Backups: ${BACKUP_SERVICES[*]}."
    exit 0
fi
[[ $EUID -eq 0 ]] || fail "Run updates as root; --check may run as the Docker user"

exec 8>/run/lock/raspi-system-update.lock
flock -n 8 || fail "Another system update is already running"

# The wrapper owns the global backup lock during each backup. Do not hold that
# same lock here until all backup wrappers have returned, otherwise they deadlock.
for service in "${BACKUP_SERVICES[@]}"; do
    log "Creating and replicating pre-update backup: $service"
    runuser -u karsten -- "$BACKUP_RUNNER" backup.yml -e "service_name=$service"
done

# Exclude scheduled backups/restores throughout package updates and recreation.
exec 9<>"$BASE_DIR/.cache/backup-locks/docker-backup-global.lock"
flock -w 3600 9 || fail "Timed out waiting for backup/update lock"
preflight

RECOVERY_DIR=$(mktemp -d "$BASE_DIR/backups/update-recovery-$(date +%Y%m%dT%H%M%S)-XXXXXXXX")
chmod 0700 "$RECOVERY_DIR"
python3 - "$RECOVERY_DIR" <<'PY'
import json, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
ids = subprocess.check_output(['docker', 'compose', '--project-directory',
                              '/home/karsten/paperless', 'ps', '-a', '-q'], text=True).split()
containers = json.loads(subprocess.check_output(['docker', 'inspect', *ids]))
services = {}
for c in containers:
    service = c['Config']['Labels']['com.docker.compose.service']
    tag = 'local-recovery/paperless-' + service + ':' + root.name.lower()
    subprocess.run(['docker', 'image', 'tag', c['Image'], tag], check=True)
    services[service] = {'image': tag, 'pull_policy': 'never'}
(root / 'previous-images.json').write_text(json.dumps({'services': services}, indent=2) + '\n')
backups = {}
for service in ('homeassistant', 'paperless', 'monitoring'):
    paths = sorted((pathlib.Path('/home/karsten/backups') / (service + '_backups')).glob(service + '_backup_*.tar.gz'))
    if not paths:
        raise SystemExit('Missing pre-update archive: ' + service)
    # Preserve the chosen archive beyond regular local backup retention.
    src = paths[-1]
    dest = root / src.name
    dest.hardlink_to(src)
    backups[service] = str(dest)
(root / 'backups.json').write_text(json.dumps(backups, indent=2) + '\n')
PY
log "Pre-update images and archives retained in $RECOVERY_DIR"

log "Updating OS package index and installed packages"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade -y

log "Pulling Paperless images"
docker compose --project-directory "$BASE_DIR/$UPDATE_PROJECT" pull
CONTAINERS_CHANGED=true
docker compose --project-directory "$BASE_DIR/$UPDATE_PROJECT" up -d --wait --wait-timeout 180
preflight
CONTAINERS_CHANGED=false
# Keep two successful recovery points. Failed runs remain for investigation.
python3 - "$RECOVERY_DIR" <<'PYRECOVERY'
import json, pathlib, shutil, subprocess, sys
current = pathlib.Path(sys.argv[1])
(current / 'success').touch()
completed = sorted((p for p in current.parent.glob('update-recovery-*')
                    if p.is_dir() and not p.is_symlink() and (p / 'success').is_file()),
                   key=lambda p: (p / 'success').stat().st_mtime_ns)
for old in completed[:-2]:
    images = json.loads((old / 'previous-images.json').read_text())
    for service in images['services'].values():
        tag = service['image']
        if not tag.startswith('local-recovery/paperless-'):
            raise SystemExit('Refusing unexpected recovery image reference')
        # Remove only our recovery tag, never force-delete an in-use image.
        subprocess.run(['docker', 'image', 'rm', tag], check=True)
    shutil.rmtree(old)
PYRECOVERY
log "System and Paperless update completed; health checks passed. No automatic reboot."
