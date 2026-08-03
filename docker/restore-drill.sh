#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &&
    pwd
)"
REPO_DIR="$(
    cd -- "$SCRIPT_DIR/.." &&
    pwd
)"

SERVICE_NAME=""
VM_NAME="restore-drill"
VM_HOST="192.168.122.18"
VM_USER="karsten"
BASE_DIR="/home/karsten"
REMOTE_REPO="/home/karsten/ansible-playbooks-restore-hardening"
BACKUP_FILE=""
RESET_VM_TARGET=0
DRILL_START=0
SKIP_VM_START=0

usage() {
    cat <<'EOF'
Usage:
  docker/restore-drill.sh --service SERVICE [options]

Options:
  --service NAME        Service to restore in the drill VM.
  --backup-file PATH    Explicit local backup archive. Defaults to latest portable local backup.
  --vm-name NAME        libvirt VM name. Default: restore-drill.
  --vm-host HOST        SSH host or IP. Default: 192.168.122.18.
  --vm-user USER        SSH user. Default: karsten.
  --remote-repo PATH    Repo checkout path inside the VM.
  --reset-vm-target     Remove prior drill containers, service dir, bind data and volumes in the VM.
  --drill-start         After install, start Paperless with docker-compose.drill.yml and verify it.
  --skip-vm-start       Do not call virsh start; only wait for SSH.
  -h, --help            Show this help.

The script never restores in place on the host. It syncs the current checkout and
one portable backup archive into the configured VM, then runs the hardened
install flow there with restore_install_start=false.
EOF
}

log() {
    printf '[restore-drill] %s\n' "$*" >&2
}

die() {
    printf '[restore-drill] ERROR: %s\n' "$*" >&2
    exit 1
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --service)
            SERVICE_NAME="${2:-}"
            shift 2
            ;;
        --backup-file)
            BACKUP_FILE="${2:-}"
            shift 2
            ;;
        --vm-name)
            VM_NAME="${2:-}"
            shift 2
            ;;
        --vm-host)
            VM_HOST="${2:-}"
            shift 2
            ;;
        --vm-user)
            VM_USER="${2:-}"
            shift 2
            ;;
        --remote-repo)
            REMOTE_REPO="${2:-}"
            shift 2
            ;;
        --reset-vm-target)
            RESET_VM_TARGET=1
            shift
            ;;
        --drill-start)
            DRILL_START=1
            shift
            ;;
        --skip-vm-start)
            SKIP_VM_START=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
done

[[ -n "$SERVICE_NAME" ]] || die "--service is required"
[[ "$SERVICE_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || die "Unsafe service name: $SERVICE_NAME"
[[ "$VM_HOST" != "127.0.0.1" && "$VM_HOST" != "localhost" ]] || die "Refusing to use localhost as drill VM"
[[ "$REMOTE_REPO" == /home/* ]] || die "Refusing remote repo outside /home: $REMOTE_REPO"

require_cmd ssh
require_cmd rsync
require_cmd tar

if [[ -z "$BACKUP_FILE" ]]; then
    backup_dir="$BASE_DIR/backups/${SERVICE_NAME}_backups"
    [[ -d "$backup_dir" ]] || die "Backup directory not found: $backup_dir"
    while IFS= read -r candidate; do
        if tar -tzf "$candidate" backup-manifest.json >/dev/null 2>&1; then
            BACKUP_FILE="$candidate"
            break
        fi
        log "Skipping non-portable backup without manifest: $(basename "$candidate")"
    done < <(
        find "$backup_dir" -maxdepth 1 -type f -name "${SERVICE_NAME}_backup_*.tar.gz" \
          -printf '%T@ %p\n' | sort -nr | awk '{ $1=""; sub(/^ /, ""); print }'
    )
fi

[[ -n "$BACKUP_FILE" ]] || die "No portable manifest backup found for $SERVICE_NAME"
[[ -f "$BACKUP_FILE" ]] || die "Backup archive not found: $BACKUP_FILE"
tar -tzf "$BACKUP_FILE" backup-manifest.json >/dev/null || die "Backup has no backup-manifest.json: $BACKUP_FILE"

REMOTE="${VM_USER}@${VM_HOST}"
REMOTE_BACKUP_DIR="$BASE_DIR/backups/${SERVICE_NAME}_backups"
REMOTE_BACKUP_FILE="$REMOTE_BACKUP_DIR/$(basename "$BACKUP_FILE")"

ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10)

remote() {
    ssh "${ssh_opts[@]}" "$REMOTE" "$@"
}

remote_bash() {
    ssh "${ssh_opts[@]}" "$REMOTE" \
      "SERVICE_NAME=$(printf '%q' "$SERVICE_NAME") REMOTE_REPO=$(printf '%q' "$REMOTE_REPO") REMOTE_BACKUP_FILE=$(printf '%q' "$REMOTE_BACKUP_FILE") bash -s"
}

start_vm() {
    if [[ "$SKIP_VM_START" -eq 0 ]] && command -v virsh >/dev/null 2>&1; then
        if virsh -c qemu:///system dominfo "$VM_NAME" >/dev/null 2>&1; then
            state="$(virsh -c qemu:///system domstate "$VM_NAME" | tr -d '\r')"
            if [[ "$state" != "running" ]]; then
                log "Starting VM $VM_NAME"
                virsh -c qemu:///system start "$VM_NAME" >/dev/null
            fi
        else
            log "VM $VM_NAME not known to libvirt; relying on SSH host $VM_HOST"
        fi
    fi

    log "Waiting for SSH on $REMOTE"
    for _ in {1..60}; do
        if remote 'true' >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    die "SSH did not become available on $REMOTE"
}

sync_inputs() {
    log "Syncing repository to $REMOTE:$REMOTE_REPO"
    remote "mkdir -p $(printf '%q' "$REMOTE_REPO") $(printf '%q' "$REMOTE_BACKUP_DIR")"
    rsync -a --delete \
      --exclude '.git/' \
      "$REPO_DIR/" \
      "$REMOTE:$REMOTE_REPO/"

    log "Syncing backup $(basename "$BACKUP_FILE")"
    rsync -a "$BACKUP_FILE" "$REMOTE:$REMOTE_BACKUP_FILE"
}

reset_vm_target() {
    [[ "$RESET_VM_TARGET" -eq 1 ]] || return 0
    log "Resetting prior drill target in VM from backup manifest"
    remote_bash <<'REMOTE'
set -Eeuo pipefail

manifest_lines="$(
python3 - "$REMOTE_BACKUP_FILE" <<'PY'
import json
import sys
import tarfile

archive = sys.argv[1]
with tarfile.open(archive, "r:gz") as tf:
    manifest = json.load(tf.extractfile("backup-manifest.json"))

portable = manifest.get("portable_manifest") or manifest
service_dir = portable.get("service_dir") or f"/home/karsten/{manifest.get('service_name', '')}"
print(f"SERVICE_DIR\t{service_dir}")
for volume in portable.get("named_volumes") or []:
    name = volume.get("name")
    if name:
        print(f"VOLUME\t{name}")
for bind in portable.get("external_bind_mounts") or []:
    source = bind.get("source")
    if source:
        print(f"BIND\t{source}")
PY
)"

service_dir=""
while IFS=$'\t' read -r kind value; do
    [[ -n "${value:-}" ]] || continue
    if [[ "$kind" == "SERVICE_DIR" ]]; then
        service_dir="$value"
        break
    fi
done <<< "$manifest_lines"

if [[ -n "$service_dir" && -d "$service_dir" ]]; then
    (
        cd "$service_dir"
        if [[ -f docker-compose.yml && -f docker-compose.drill.yml ]]; then
            docker compose -f docker-compose.yml -f docker-compose.drill.yml down --remove-orphans || true
        elif [[ -f docker-compose.yml ]]; then
            docker compose down --remove-orphans || true
        fi
    )
fi

while IFS=$'\t' read -r kind value; do
    [[ -n "${value:-}" ]] || continue
    case "$kind" in
        SERVICE_DIR)
            [[ "$value" == /home/*/* ]] || {
                echo "Refusing unsafe service dir: $value" >&2
                exit 1
            }
            rm -rf -- "$value"
            ;;
        BIND)
            [[ "$value" == /mnt/*/* || "$value" == /home/*/*/* ]] || {
                echo "Refusing unsafe bind target: $value" >&2
                exit 1
            }
            mkdir -p -- "$value"
            find "$value" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
            ;;
        VOLUME)
            [[ "$value" == "${SERVICE_NAME}_"* || "$value" == *"_${SERVICE_NAME}_"* ]] || {
                echo "Refusing unexpected volume name for $SERVICE_NAME: $value" >&2
                exit 1
            }
            docker volume rm "$value" >/dev/null 2>&1 || true
            ;;
    esac
done <<< "$manifest_lines"
REMOTE
}

run_install() {
    log "Running install plan in VM"
    remote_bash <<'REMOTE'
set -Eeuo pipefail
cd "$REMOTE_REPO"
confirm_json="$(python3 -c 'import json, os; print(json.dumps({"restore_install_confirm": "RESTORE " + os.environ["SERVICE_NAME"]}))')"
ansible-playbook -i inventory docker/restore.yml \
  -e "service_name=$SERVICE_NAME" \
  -e restore_mode=install \
  -e restore_source=local \
  -e "restore_file=$REMOTE_BACKUP_FILE" \
  -e restore_install_plan_only=true \
  -e "$confirm_json"
REMOTE

    log "Installing restored data in VM without starting containers"
    remote_bash <<'REMOTE'
set -Eeuo pipefail
cd "$REMOTE_REPO"
confirm_json="$(python3 -c 'import json, os; print(json.dumps({"restore_install_confirm": "RESTORE " + os.environ["SERVICE_NAME"]}))')"
ansible-playbook -i inventory docker/restore.yml \
  -e "service_name=$SERVICE_NAME" \
  -e restore_mode=install \
  -e restore_source=local \
  -e "restore_file=$REMOTE_BACKUP_FILE" \
  -e restore_install_start=false \
  -e "$confirm_json"
REMOTE
}

run_paperless_drill_start() {
    [[ "$DRILL_START" -eq 1 ]] || return 0
    [[ "$SERVICE_NAME" == "paperless" ]] || die "--drill-start currently supports only paperless"

    log "Starting Paperless through docker-compose.drill.yml"
    remote_bash <<'REMOTE'
set -Eeuo pipefail
service_dir="$(python3 - "$REMOTE_BACKUP_FILE" <<'PY'
import json
import sys
import tarfile

with tarfile.open(sys.argv[1], "r:gz") as tf:
    manifest = json.load(tf.extractfile("backup-manifest.json"))
portable = manifest.get("portable_manifest") or manifest
print(portable.get("service_dir") or "/home/karsten/paperless")
PY
)"
cd "$service_dir"
compose() {
    docker compose -f docker-compose.yml -f docker-compose.drill.yml "$@"
}

cleanup() {
    compose stop || true
}
trap cleanup EXIT

compose up -d

healthy=0
code="000"
for _ in {1..18}; do
    compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
    code="$(curl -sS -o /tmp/paperless-drill-http.out -w "%{http_code}" http://127.0.0.1:8000/ || true)"
    echo "http_status=$code"
    if compose ps --format "{{.Name}} {{.Status}}" |
       grep -q "paperless-ngx.*healthy" && [[ "$code" != "000" && "$code" != "502" ]]; then
        healthy=1
        break
    fi
    sleep 10
done

if [[ "$healthy" -ne 1 ]]; then
    echo "Paperless did not become healthy; last http_status=$code" >&2
    exit 1
fi

echo "--- drill assertions ---"
docker inspect --format "{{.Name}} restart={{.HostConfig.RestartPolicy.Name}}" \
  paperless-db paperless-redis paperless-ngx paperless-drill-proxy
docker network inspect paperless_paperless --format "paperless_internal={{.Internal}}"
docker network inspect paperless_drill_access --format "drill_access_internal={{.Internal}}"

if compose exec -T paperless-ngx \
  python3 -c 'import socket; socket.setdefaulttimeout(3); s=socket.socket(); s.connect(("1.1.1.1", 443))'; then
    echo "outbound=unexpected-ok" >&2
    exit 1
else
    echo "outbound=blocked"
fi

set +e
document_count_output="$(compose exec -T db \
  psql -U paperless -d paperless -tAc 'select count(*) from documents_document;' 2>&1)"
document_count_rc=$?
set -e
if [[ "$document_count_rc" -ne 0 ]]; then
    echo "$document_count_output" >&2
    echo "document_count=failed" >&2
    exit "$document_count_rc"
fi
document_count="$(
    printf '%s\n' "$document_count_output" |
      awk 'NF { value=$0 } END { gsub(/^[ \t]+|[ \t]+$/, "", value); print value }'
)"
echo "document_count=$document_count"
REMOTE
}

start_vm
sync_inputs
reset_vm_target
run_install
run_paperless_drill_start

log "Drill completed for $SERVICE_NAME using $(basename "$BACKUP_FILE")"
