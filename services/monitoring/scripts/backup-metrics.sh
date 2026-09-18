#!/usr/bin/env bash

set -u
set -o pipefail

OUTDIR="/home/karsten/monitoring/textfile"
OUT="${OUTDIR}/backups.prom"
TMP="${OUT}.tmp"

SERVICES=(
  homeassistant
  paperless
  monitoring
)

VPS_SERVICES=(
  traefik
  sentinel
)

LOCAL_BASE="/home/karsten/backups"
NAS_BASE="/mnt/backups"
REMOTE="onedrive:backups"

mkdir -p "$OUTDIR"

escape_label() {
    printf '%s' "$1" \
      | sed 's/\\/\\\\/g; s/"/\\"/g; s/\n/\\n/g'
}

emit_file_metrics() {
    local service="$1"
    local target="$2"
    local file="$3"

    local timestamp size filename

    if [[ -n "$file" && -f "$file" ]]; then
        timestamp=$(stat -c '%Y' "$file")
        size=$(stat -c '%s' "$file")
        filename=$(basename "$file")

        printf 'backup_present{service="%s",target="%s"} 1\n' \
            "$service" "$target"

        printf 'backup_last_timestamp_seconds{service="%s",target="%s"} %s\n' \
            "$service" "$target" "$timestamp"

        printf 'backup_last_size_bytes{service="%s",target="%s"} %s\n' \
            "$service" "$target" "$size"

        printf 'backup_last_info{service="%s",target="%s",filename="%s"} 1\n' \
            "$service" "$target" "$(escape_label "$filename")"
    else
        printf 'backup_present{service="%s",target="%s"} 0\n' \
            "$service" "$target"
    fi
}

{
    echo '# HELP backup_present Whether at least one backup exists for service and target.'
    echo '# TYPE backup_present gauge'

    echo '# HELP backup_last_timestamp_seconds Modification timestamp of newest backup.'
    echo '# TYPE backup_last_timestamp_seconds gauge'

    echo '# HELP backup_last_size_bytes Size of newest backup in bytes.'
    echo '# TYPE backup_last_size_bytes gauge'

    echo '# HELP backup_last_info Information about newest backup.'
    echo '# TYPE backup_last_info gauge'

    echo '# HELP backup_file_count Number of backup archives currently present.'
    echo '# TYPE backup_file_count gauge'

    echo '# HELP backup_local_nas_match Whether newest local and NAS backup filename and size match.'
    echo '# TYPE backup_local_nas_match gauge'

    echo '# HELP backup_nas_mount_up Whether /mnt/backups is currently a CIFS mount.'
    echo '# TYPE backup_nas_mount_up gauge'

    echo '# HELP backup_cloud_query_success Whether the latest OneDrive query completed successfully.'
    echo '# TYPE backup_cloud_query_success gauge'

    echo '# HELP backup_all_targets_match Whether newest backup filename and size match across local NAS and OneDrive.'
    echo '# TYPE backup_all_targets_match gauge'

    echo '# HELP backup_age_seconds Age of newest backup in seconds.'
    echo '# TYPE backup_age_seconds gauge'

    if findmnt -rn -T "$NAS_BASE" -t cifs >/dev/null 2>&1; then
        echo 'backup_nas_mount_up 1'
        NAS_UP=1
    else
        echo 'backup_nas_mount_up 0'
        NAS_UP=0
    fi

    for service in "${SERVICES[@]}"; do

        local_dir="${LOCAL_BASE}/${service}_backups"
        nas_dir="${NAS_BASE}/${service}"

        local_file=$(
            find "$local_dir" \
              -maxdepth 1 \
              -type f \
              -name "${service}_backup_*.tar.gz" \
              -printf '%T@ %p\n' 2>/dev/null \
            | sort -nr \
            | head -1 \
            | cut -d' ' -f2-
        )

        if [[ "$NAS_UP" -eq 1 ]]; then
            nas_file=$(
                timeout 10 find "$nas_dir" \
                  -maxdepth 1 \
                  -type f \
                  -name "${service}_backup_*.tar.gz" \
                  -printf '%T@ %p\n' 2>/dev/null \
                | sort -nr \
                | head -1 \
                | cut -d' ' -f2-
            )
        else
            nas_file=""
        fi

        emit_file_metrics "$service" "local" "$local_file"
        emit_file_metrics "$service" "nas" "$nas_file"

        local_count=$(
            find "$local_dir" \
              -maxdepth 1 \
              -type f \
              -name "${service}_backup_*.tar.gz" \
              2>/dev/null | wc -l
        )

        if [[ "$NAS_UP" -eq 1 ]]; then
            nas_count=$(
                timeout 10 find "$nas_dir" \
                  -maxdepth 1 \
                  -type f \
                  -name "${service}_backup_*.tar.gz" \
                  2>/dev/null | wc -l
            )
        else
            nas_count=0
        fi

        printf 'backup_file_count{service="%s",target="local"} %s\n' \
            "$service" "$local_count"

        printf 'backup_file_count{service="%s",target="nas"} %s\n' \
            "$service" "$nas_count"

        match=0

        if [[ -n "$local_file" && -n "$nas_file" ]]; then
            local_name=$(basename "$local_file")
            nas_name=$(basename "$nas_file")
            local_size=$(stat -c '%s' "$local_file" 2>/dev/null || echo 0)
            nas_size=$(stat -c '%s' "$nas_file" 2>/dev/null || echo -1)

            if [[ "$local_name" == "$nas_name" &&
                  "$local_size" == "$nas_size" ]]; then
                match=1
            fi
        fi

        printf 'backup_local_nas_match{service="%s"} %s\n' \
            "$service" "$match"

        cloud_tmp=$(mktemp)

        if timeout 30 rclone lsjson \
            "${REMOTE}/${service}_backups" \
            --files-only \
            --include "${service}_backup_*.tar.gz" \
            > "$cloud_tmp" 2>/dev/null; then

            printf 'backup_cloud_query_success{service="%s"} 1\n' \
                "$service"

            python3 - "$service" "$cloud_tmp" <<'PY'
import json
import sys
from datetime import datetime

service = sys.argv[1]
path = sys.argv[2]

try:
    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)
except Exception:
    entries = []

files = [
    x for x in entries
    if not x.get("IsDir", False)
    and x.get("Name", "").endswith(".tar.gz")
]

print(
    f'backup_file_count{{service="{service}",target="onedrive"}} '
    f'{len(files)}'
)

if not files:
    print(
        f'backup_present{{service="{service}",target="onedrive"}} 0'
    )
    raise SystemExit

def timestamp(entry):
    value = entry.get("ModTime", "")
    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        return 0

latest = max(files, key=timestamp)

name = latest.get("Name", "")
size = int(latest.get("Size", 0))
ts = int(timestamp(latest))

name = name.replace("\\", "\\\\").replace('"', '\\"')

print(
    f'backup_present{{service="{service}",target="onedrive"}} 1'
)
print(
    f'backup_last_timestamp_seconds'
    f'{{service="{service}",target="onedrive"}} {ts}'
)
print(
    f'backup_last_size_bytes'
    f'{{service="{service}",target="onedrive"}} {size}'
)
print(
    f'backup_last_info'
    f'{{service="{service}",target="onedrive",filename="{name}"}} 1'
)
PY
        else
            printf 'backup_cloud_query_success{service="%s"} 0\n' \
                "$service"
        fi

        rm -f "$cloud_tmp"
    done

    # VPS services: OneDrive-only monitoring.
    for service in "${VPS_SERVICES[@]}"; do

        cloud_tmp=$(mktemp)

        if timeout 30 rclone lsjson \
            "${REMOTE}/${service}_backups" \
            --files-only \
            --include "${service}_backup_*.tar.gz" \
            > "$cloud_tmp" 2>/dev/null; then

            printf 'backup_cloud_query_success{service="%s"} 1\n' \
                "$service"

            python3 - "$service" "$cloud_tmp" <<'PYVPS'
import json
import sys
import time
from datetime import datetime

service = sys.argv[1]
path = sys.argv[2]

try:
    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)
except Exception:
    entries = []

files = [
    x for x in entries
    if not x.get("IsDir", False)
    and x.get("Name", "").endswith(".tar.gz")
]

print(
    f'backup_file_count{{service="{service}",target="onedrive"}} '
    f'{len(files)}'
)

if not files:
    print(
        f'backup_present{{service="{service}",target="onedrive"}} 0'
    )
    raise SystemExit

def timestamp(entry):
    value = entry.get("ModTime", "")
    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        return 0

latest = max(files, key=timestamp)

name = latest.get("Name", "")
size = int(latest.get("Size", 0))
ts = int(timestamp(latest))
age = max(0, int(time.time()) - ts)

name = name.replace("\\", "\\\\").replace('"', '\\"')

print(
    f'backup_present{{service="{service}",target="onedrive"}} 1'
)
print(
    f'backup_last_timestamp_seconds'
    f'{{service="{service}",target="onedrive"}} {ts}'
)
print(
    f'backup_last_size_bytes'
    f'{{service="{service}",target="onedrive"}} {size}'
)
print(
    f'backup_last_info'
    f'{{service="{service}",target="onedrive",filename="{name}"}} 1'
)
print(
    f'backup_age_seconds'
    f'{{service="{service}",target="onedrive"}} {age}'
)
PYVPS

        else
            printf 'backup_cloud_query_success{service="%s"} 0\n' \
                "$service"
            printf 'backup_present{service="%s",target="onedrive"} 0\n' \
                "$service"
        fi

        rm -f "$cloud_tmp"
    done

    # VPS disaster-recovery backup: OneDrive-only monitoring.
    service="vps-dr"
    cloud_tmp=$(mktemp)

    if timeout 30 rclone lsjson \
        "${REMOTE}/vps-dr" \
        --files-only \
        --include "vps-dr_vps_*.tar.gz" \
        > "$cloud_tmp" 2>/dev/null; then

        printf 'backup_cloud_query_success{service="%s"} 1\n' \
            "$service"

        python3 - "$service" "$cloud_tmp" <<'PYVPSDR'
import json
import sys
import time
from datetime import datetime

service = sys.argv[1]
path = sys.argv[2]

try:
    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)
except Exception:
    entries = []

files = [
    x for x in entries
    if not x.get("IsDir", False)
    and x.get("Name", "").startswith("vps-dr_vps_")
    and x.get("Name", "").endswith(".tar.gz")
]

print(
    f'backup_file_count{{service="{service}",target="onedrive"}} '
    f'{len(files)}'
)

if not files:
    print(
        f'backup_present{{service="{service}",target="onedrive"}} 0'
    )
    raise SystemExit

def timestamp(entry):
    value = entry.get("ModTime", "")
    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        return 0

latest = max(files, key=timestamp)

name = latest.get("Name", "")
size = int(latest.get("Size", 0))
ts = int(timestamp(latest))
age = max(0, int(time.time()) - ts)

name = name.replace("\\", "\\\\").replace('"', '\\"')

print(
    f'backup_present{{service="{service}",target="onedrive"}} 1'
)
print(
    f'backup_last_timestamp_seconds'
    f'{{service="{service}",target="onedrive"}} {ts}'
)
print(
    f'backup_last_size_bytes'
    f'{{service="{service}",target="onedrive"}} {size}'
)
print(
    f'backup_last_info'
    f'{{service="{service}",target="onedrive",filename="{name}"}} 1'
)
print(
    f'backup_age_seconds'
    f'{{service="{service}",target="onedrive"}} {age}'
)
PYVPSDR

    else
        printf 'backup_cloud_query_success{service="%s"} 0\n' \
            "$service"
        printf 'backup_present{service="%s",target="onedrive"} 0\n' \
            "$service"
    fi

    rm -f "$cloud_tmp"

    # Compare newest backup across all three targets.
    for service in "${SERVICES[@]}"; do
        local_info=$(grep "^backup_last_info{service=\"${service}\",target=\"local\"" "$TMP" 2>/dev/null || true)
        nas_info=$(grep "^backup_last_info{service=\"${service}\",target=\"nas\"" "$TMP" 2>/dev/null || true)
        cloud_info=$(grep "^backup_last_info{service=\"${service}\",target=\"onedrive\"" "$TMP" 2>/dev/null || true)

        local_size=$(grep "^backup_last_size_bytes{service=\"${service}\",target=\"local\"" "$TMP" 2>/dev/null | awk '{print $2}')
        nas_size=$(grep "^backup_last_size_bytes{service=\"${service}\",target=\"nas\"" "$TMP" 2>/dev/null | awk '{print $2}')
        cloud_size=$(grep "^backup_last_size_bytes{service=\"${service}\",target=\"onedrive\"" "$TMP" 2>/dev/null | awk '{print $2}')

        local_name=$(printf '%s\n' "$local_info" | sed -n 's/.*filename="\([^"]*\)".*/\1/p')
        nas_name=$(printf '%s\n' "$nas_info" | sed -n 's/.*filename="\([^"]*\)".*/\1/p')
        cloud_name=$(printf '%s\n' "$cloud_info" | sed -n 's/.*filename="\([^"]*\)".*/\1/p')

        all_match=0

        if [[ -n "$local_name" &&
              "$local_name" == "$nas_name" &&
              "$local_name" == "$cloud_name" &&
              -n "$local_size" &&
              "$local_size" == "$nas_size" &&
              "$local_size" == "$cloud_size" ]]; then
            all_match=1
        fi

        printf 'backup_all_targets_match{service="%s"} %s\n' \
            "$service" "$all_match"
    done

    echo '# HELP backup_collector_last_success_timestamp_seconds Last successful collector run.'
    echo '# TYPE backup_collector_last_success_timestamp_seconds gauge'
    printf 'backup_collector_last_success_timestamp_seconds %s\n' "$(date +%s)"

} > "$TMP"

mv "$TMP" "$OUT"
chmod 644 "$OUT"
