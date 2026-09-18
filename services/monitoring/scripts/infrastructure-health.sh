#!/usr/bin/env bash

set -u
set -o pipefail

OUT="/home/karsten/monitoring/textfile/infrastructure-health.prom"
TMP="${OUT}.tmp"

mkdir -p "$(dirname "$OUT")"
: > "$TMP"

metric_label() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

# ------------------------------------------------------------
# Collector metadata
# ------------------------------------------------------------

NOW=$(date +%s)

echo "# HELP home_infrastructure_collector_timestamp_seconds Last successful infrastructure collector run." >> "$TMP"
echo "# TYPE home_infrastructure_collector_timestamp_seconds gauge" >> "$TMP"
echo "home_infrastructure_collector_timestamp_seconds $NOW" >> "$TMP"


# ------------------------------------------------------------
# Docker
# ------------------------------------------------------------

echo "# HELP home_container_running Whether a Docker container is running." >> "$TMP"
echo "# TYPE home_container_running gauge" >> "$TMP"

echo "# HELP home_container_healthy Docker health state. 1=healthy, 0=unhealthy, -1=no healthcheck." >> "$TMP"
echo "# TYPE home_container_healthy gauge" >> "$TMP"

echo "# HELP home_container_restarts Docker container restart count." >> "$TMP"
echo "# TYPE home_container_restarts gauge" >> "$TMP"

CONTAINERS=(
    monitoring-prometheus
    monitoring-node-exporter
    monitoring-snmp-exporter
    monitoring-grafana
    monitoring-fritz-exporter
    monitoring-blackbox
    paperless-ngx
    paperless-db
    paperless-redis
    nodered
    homeassistant
    mqtt
)

for NAME in "${CONTAINERS[@]}"; do

    if ! docker inspect "$NAME" >/dev/null 2>&1; then
        echo "home_container_running{container=\"$NAME\"} 0" >> "$TMP"
        echo "home_container_healthy{container=\"$NAME\"} -1" >> "$TMP"
        echo "home_container_restarts{container=\"$NAME\"} 0" >> "$TMP"
        continue
    fi

    RUNNING=$(docker inspect \
        --format '{{if .State.Running}}1{{else}}0{{end}}' \
        "$NAME" 2>/dev/null || echo 0)

    RESTARTS=$(docker inspect \
        --format '{{.RestartCount}}' \
        "$NAME" 2>/dev/null || echo 0)

    HEALTH=$(docker inspect \
        --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
        "$NAME" 2>/dev/null || echo none)

    case "$HEALTH" in
        healthy)
            HEALTH_VALUE=1
            ;;
        unhealthy|starting)
            HEALTH_VALUE=0
            ;;
        *)
            HEALTH_VALUE=-1
            ;;
    esac

    echo "home_container_running{container=\"$NAME\"} $RUNNING" >> "$TMP"
    echo "home_container_healthy{container=\"$NAME\"} $HEALTH_VALUE" >> "$TMP"
    echo "home_container_restarts{container=\"$NAME\"} $RESTARTS" >> "$TMP"

done


# ------------------------------------------------------------
# Important mounts
# ------------------------------------------------------------

echo "# HELP home_mount_available Whether an expected mount is mounted." >> "$TMP"
echo "# TYPE home_mount_available gauge" >> "$TMP"

echo "# HELP home_mount_writable Whether an expected mount accepts a temporary write." >> "$TMP"
echo "# TYPE home_mount_writable gauge" >> "$TMP"

MOUNTS=(
    /mnt/backups
    /mnt/paperless
    /mnt/public
    /mnt/usb
)

for MOUNT in "${MOUNTS[@]}"; do

    LABEL=$(metric_label "$MOUNT")

    if mountpoint -q "$MOUNT"; then
        AVAILABLE=1
    else
        AVAILABLE=0
    fi

    WRITABLE=0

    if [ "$AVAILABLE" -eq 1 ]; then
        TESTFILE="${MOUNT}/.monitoring-write-test-$$"

        if timeout 5 touch "$TESTFILE" 2>/dev/null; then
            rm -f "$TESTFILE" 2>/dev/null || true
            WRITABLE=1
        fi
    fi

    echo "home_mount_available{mount=\"$LABEL\"} $AVAILABLE" >> "$TMP"
    echo "home_mount_writable{mount=\"$LABEL\"} $WRITABLE" >> "$TMP"

done


# ------------------------------------------------------------
# Time synchronization
# ------------------------------------------------------------

echo "# HELP home_timesync_up Whether systemd reports the clock synchronized." >> "$TMP"
echo "# TYPE home_timesync_up gauge" >> "$TMP"

SYNC=$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo no)

if [ "$SYNC" = "yes" ]; then
    echo "home_timesync_up 1" >> "$TMP"
else
    echo "home_timesync_up 0" >> "$TMP"
fi


# ------------------------------------------------------------
# Paperless application stack
# ------------------------------------------------------------

echo "# HELP home_paperless_component_up Paperless component health." >> "$TMP"
echo "# TYPE home_paperless_component_up gauge" >> "$TMP"

component_health() {

    NAME="$1"
    COMPONENT="$2"

    VALUE=$(docker inspect "$NAME" \
        --format '{{if .State.Health}}{{if eq .State.Health.Status "healthy"}}1{{else}}0{{end}}{{else}}{{if .State.Running}}1{{else}}0{{end}}{{end}}' \
        2>/dev/null || echo 0)

    echo "home_paperless_component_up{component=\"$COMPONENT\"} $VALUE" >> "$TMP"
}

component_health paperless-ngx web
component_health paperless-db postgres
component_health paperless-redis redis


# ------------------------------------------------------------
# Atomic publish
# ------------------------------------------------------------

mv "$TMP" "$OUT"
