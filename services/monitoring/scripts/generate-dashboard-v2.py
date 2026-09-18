#!/usr/bin/env python3

import json
from pathlib import Path

OUT = Path("/home/karsten/monitoring/grafana/dashboards/home-infrastructure-v2.json")

# Do not hard-code Grafana's generated datasource UID.
# "default" resolves to the configured default Prometheus datasource.
DS = {"type": "prometheus", "uid": "default"}

GREEN = "green"
YELLOW = "yellow"
RED = "red"


def target(expr, ref="A", legend=""):
    t = {
        "refId": ref,
        "expr": expr,
        "range": True,
    }
    if legend:
        t["legendFormat"] = legend
    return t


def row(pid, title, y, collapsed=False):
    return {
        "id": pid,
        "type": "row",
        "title": title,
        "collapsed": collapsed,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
        "panels": [],
    }


def stat(
    pid,
    title,
    expr,
    x,
    y,
    w,
    h=4,
    unit="none",
    decimals=0,
    mappings=None,
    thresholds=None,
    text_mode="auto",
):
    if thresholds is None:
        thresholds = [
            {"color": RED, "value": None},
            {"color": GREEN, "value": 1},
        ]

    p = {
        "id": pid,
        "type": "stat",
        "title": title,
        "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [target(expr)],
        "options": {
            "reduceOptions": {
                "values": False,
                "calcs": ["lastNotNull"],
                "fields": "",
            },
            "orientation": "auto",
            "textMode": text_mode,
            "colorMode": "background",
            "graphMode": "none",
            "justifyMode": "auto",
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "decimals": decimals,
                "thresholds": {
                    "mode": "absolute",
                    "steps": thresholds,
                },
            },
            "overrides": [],
        },
    }

    if mappings:
        p["fieldConfig"]["defaults"]["mappings"] = mappings

    return p


def health_stat(pid, title, expr, x, y, w=4, h=4):
    return stat(
        pid,
        title,
        expr,
        x,
        y,
        w,
        h,
        mappings=[
            {
                "type": "value",
                "options": {
                    "0": {"text": "PROBLEM", "color": RED},
                    "1": {"text": "HEALTHY", "color": GREEN},
                },
            }
        ],
        thresholds=[
            {"color": RED, "value": None},
            {"color": GREEN, "value": 1},
        ],
    )


def timeseries(pid, title, targets, x, y, w=12, h=7, unit="short"):
    return {
        "id": pid,
        "type": "timeseries",
        "title": title,
        "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": targets,
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "drawStyle": "line",
                    "lineInterpolation": "smooth",
                    "lineWidth": 1,
                    "fillOpacity": 10,
                    "showPoints": "never",
                    "spanNulls": False,
                },
            },
            "overrides": [],
        },
        "options": {
            "legend": {
                "displayMode": "table",
                "placement": "bottom",
                "calcs": ["lastNotNull", "mean", "max"],
            },
            "tooltip": {
                "mode": "multi",
                "sort": "desc",
            },
        },
    }


def table(pid, title, targets, x, y, w=24, h=8):
    return {
        "id": pid,
        "type": "table",
        "title": title,
        "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": targets,
        "options": {
            "showHeader": True,
            "cellHeight": "sm",
        },
        "fieldConfig": {
            "defaults": {},
            "overrides": [],
        },
    }


panels = []

# ============================================================
# OVERVIEW
# ============================================================

panels.append(row(2000, "HOME INFRASTRUCTURE · OVERVIEW", 0))

overall = """
min(
  (
    probe_success{job="paperless-external"}
  )
  or
  (
    max(probe_success{job="internet-icmp"})
  )
  or
  (
    home_ex4100_up
  )
  or
  (
    home_timesync_up
  )
)
"""

# Overall is intentionally conservative and complemented by subsystem health.
panels.append(health_stat(
    2001, "OVERALL",
    """
min(
  scalar(probe_success{job="paperless-external"})
  or vector(0),
  scalar(max(probe_success{job="internet-icmp"}))
  or vector(0)
)
""",
    0, 1, 5
))

panels.append(health_stat(
    2002, "PAPERLESS",
    'probe_success{job="paperless-external"}',
    5, 1, 5
))

panels.append(health_stat(
    2003, "NETWORK",
    'max(probe_success{job="internet-icmp"})',
    10, 1, 5
))

panels.append(health_stat(
    2004, "STORAGE",
    'home_ex4100_up * min(home_ex4100_disk_present)',
    15, 1, 4
))

backup_health = """
1 - max(
  (
    1 - backup_nas_mount_up
  )
  or
  (
    time() - backup_collector_last_success_timestamp_seconds > bool 2700
  )
  or
  (
    1 - backup_present{
      target="local",
      service=~"homeassistant|paperless|monitoring"
    }
  )
  or
  (
    1 - backup_present{
      target="nas",
      service=~"homeassistant|paperless|monitoring"
    }
  )
  or
  (
    1 - backup_present{
      target="onedrive",
      service=~"homeassistant|paperless|monitoring|traefik|sentinel|vps-dr"
    }
  )
  or
  (
    1 - backup_cloud_query_success{
      service=~"homeassistant|paperless|monitoring|traefik|sentinel|vps-dr"
    }
  )
  or
  (
    1 - backup_all_targets_match{
      service=~"homeassistant|paperless|monitoring"
    }
  )
  or
  (
    (
      time() -
      backup_last_timestamp_seconds{
        target="onedrive",
        service=~"homeassistant|paperless|monitoring|traefik|sentinel|vps-dr"
      }
    ) > bool 129600
  )
)
"""

panels.append(health_stat(
    2005, "BACKUPS",
    backup_health,
    19, 1, 5
))


# ============================================================
# PAPERLESS
# ============================================================

panels.append(row(2010, "PAPERLESS · END-TO-END", 5))

panels.append(health_stat(
    2011,
    "paperless.karikarstus.de",
    'probe_success{job="paperless-external"}',
    0, 6, 8
))

panels.append(stat(
    2012,
    "Antwortzeit",
    'probe_duration_seconds{job="paperless-external"} * 1000',
    8, 6, 8,
    unit="ms",
    decimals=0,
    thresholds=[
        {"color": GREEN, "value": None},
        {"color": YELLOW, "value": 500},
        {"color": RED, "value": 1000},
    ],
))

panels.append(stat(
    2013,
    "TLS Restlaufzeit",
    '(probe_ssl_earliest_cert_expiry{job="paperless-external"} - time()) / 86400',
    16, 6, 8,
    unit="d",
    decimals=0,
    thresholds=[
        {"color": RED, "value": None},
        {"color": YELLOW, "value": 14},
        {"color": GREEN, "value": 30},
    ],
))


# ============================================================
# FAILURE CHAIN
# ============================================================

panels.append(row(2020, "PAPERLESS · FEHLERKETTE", 10))

chain = [
    (2021, "INTERNET", 'max(probe_success{job="internet-icmp"})'),
    (2022, "DNS", 'probe_success{job="paperless-dns"}'),
    (2023, "HTTPS", 'probe_success{job="paperless-external"}'),
    (2024, "VPS", 'up{job="vps"}'),
    (2025, "TRAEFIK", 'up{job="vps-traefik"} or up{job="traefik"}'),
    (2026, "WIREGUARD", 'wireguard_peer_handshake_age_seconds{job="vps",peer="paperless"} < bool 180'),
    (2027, "PI", 'up{job="raspberry-pi"}'),
    (2028, "PAPERLESS", 'home_paperless_component_up{component="web"}'),
]

for i, (pid, title, expr) in enumerate(chain):
    panels.append(health_stat(
        pid, title, expr,
        i * 3, 11, 3, 4
    ))


# ============================================================
# SYSTEMS
# ============================================================

panels.append(row(2030, "SYSTEMS", 15))

panels.append(stat(
    2031,
    "Raspberry Pi · CPU",
    '100-(avg(rate(node_cpu_seconds_total{job="raspberry-pi",mode="idle"}[5m]))*100)',
    0, 16, 4,
    unit="percent",
    decimals=1,
    thresholds=[
        {"color": GREEN, "value": None},
        {"color": YELLOW, "value": 75},
        {"color": RED, "value": 90},
    ],
))

panels.append(stat(
    2032,
    "Pi · RAM",
    '(1-(node_memory_MemAvailable_bytes{job="raspberry-pi"}/node_memory_MemTotal_bytes{job="raspberry-pi"}))*100',
    4, 16, 4,
    unit="percent",
    decimals=1,
    thresholds=[
        {"color": GREEN, "value": None},
        {"color": YELLOW, "value": 80},
        {"color": RED, "value": 90},
    ],
))

panels.append(stat(
    2033,
    "Pi · Temperatur",
    'avg(node_hwmon_temp_celsius{job="raspberry-pi",chip="thermal_thermal_zone0"})',
    8, 16, 4,
    unit="celsius",
    decimals=1,
    thresholds=[
        {"color": GREEN, "value": None},
        {"color": YELLOW, "value": 70},
        {"color": RED, "value": 80},
    ],
))

panels.append(stat(
    2034,
    "VPS · CPU",
    '100-(avg(rate(node_cpu_seconds_total{job="vps",mode="idle"}[5m]))*100)',
    12, 16, 4,
    unit="percent",
    decimals=1,
    thresholds=[
        {"color": GREEN, "value": None},
        {"color": YELLOW, "value": 75},
        {"color": RED, "value": 90},
    ],
))

panels.append(stat(
    2035,
    "VPS · RAM",
    '(1-(node_memory_MemAvailable_bytes{job="vps"}/node_memory_MemTotal_bytes{job="vps"}))*100',
    16, 16, 4,
    unit="percent",
    decimals=1,
    thresholds=[
        {"color": GREEN, "value": None},
        {"color": YELLOW, "value": 80},
        {"color": RED, "value": 90},
    ],
))

panels.append(health_stat(
    2036,
    "FRITZ · WAN",
    'fritz_wan_phys_link_status{job="fritzbox"}',
    20, 16, 4
))


# ============================================================
# STORAGE
# ============================================================

panels.append(row(2040, "STORAGE · WD MY CLOUD EX4100", 20))

panels.append(health_stat(
    2041,
    "EX4100",
    'home_ex4100_up',
    0, 21, 4
))

panels.append(stat(
    2042,
    "Systemtemperatur",
    'home_ex4100_temperature_celsius',
    4, 21, 4,
    unit="celsius",
    decimals=0,
    thresholds=[
        {"color": GREEN, "value": None},
        {"color": YELLOW, "value": 50},
        {"color": RED, "value": 60},
    ],
))

panels.append(health_stat(
    2043,
    "Lüfter",
    'home_ex4100_fan_up',
    8, 21, 4
))

panels.append(stat(
    2044,
    "Volume_1",
    '''
100 *
(
  ex4100_hrStorageUsed{hrStorageDescr="/mnt/HD/HD_a2"}
/
  ex4100_hrStorageSize{hrStorageDescr="/mnt/HD/HD_a2"}
)
''',
    12, 21, 4,
    unit="percent",
    decimals=1,
    thresholds=[
        {"color": GREEN, "value": None},
        {"color": YELLOW, "value": 75},
        {"color": RED, "value": 90},
    ],
))

panels.append(stat(
    2045,
    "Disk 1",
    'home_ex4100_disk_temperature_celsius{disk="1"}',
    16, 21, 4,
    unit="celsius",
    decimals=0,
    thresholds=[
        {"color": GREEN, "value": None},
        {"color": YELLOW, "value": 45},
        {"color": RED, "value": 55},
    ],
))

panels.append(stat(
    2046,
    "Disk 2",
    'home_ex4100_disk_temperature_celsius{disk="2"}',
    20, 21, 4,
    unit="celsius",
    decimals=0,
    thresholds=[
        {"color": GREEN, "value": None},
        {"color": YELLOW, "value": 45},
        {"color": RED, "value": 55},
    ],
))


# ============================================================
# BACKUPS
# ============================================================

panels.append(row(2050, "BACKUPS", 25))

services = [
    ("Home Assistant", "homeassistant"),
    ("Paperless", "paperless"),
    ("Monitoring", "monitoring"),
]

y = 26

for idx, (display, service) in enumerate(services):
    yy = y + idx * 3

    panels.append(health_stat(
        2060 + idx * 10,
        display + " · Local",
        f'backup_present{{service="{service}",target="local"}}',
        0, yy, 4, 3
    ))

    panels.append(health_stat(
        2061 + idx * 10,
        display + " · NAS",
        f'backup_present{{service="{service}",target="nas"}}',
        4, yy, 4, 3
    ))

    panels.append(health_stat(
        2062 + idx * 10,
        display + " · Cloud",
        f'backup_present{{service="{service}",target="onedrive"}}',
        8, yy, 4, 3
    ))

    panels.append(health_stat(
        2063 + idx * 10,
        display + " · Match",
        f'backup_all_targets_match{{service="{service}"}}',
        12, yy, 4, 3
    ))

    panels.append(stat(
        2064 + idx * 10,
        display + " · Age",
        f'(time()-backup_last_timestamp_seconds{{service="{service}",target="onedrive"}})/3600',
        16, yy, 8, 3,
        unit="h",
        decimals=1,
        thresholds=[
            {"color": GREEN, "value": None},
            {"color": YELLOW, "value": 24},
            {"color": RED, "value": 36},
        ],
    ))

vps_y = y + len(services) * 3

for idx, (display, service) in enumerate([
    ("Traefik", "traefik"),
    ("Sentinel", "sentinel"),
    ("VPS-DR", "vps-dr"),
]):
    yy = vps_y + idx * 3

    panels.append(health_stat(
        2110 + idx * 10,
        display + " · Cloud",
        f'backup_present{{service="{service}",target="onedrive"}}',
        0, yy, 8, 3
    ))

    panels.append(health_stat(
        2111 + idx * 10,
        display + " · OneDrive API",
        f'backup_cloud_query_success{{service="{service}"}}',
        8, yy, 8, 3
    ))

    panels.append(stat(
        2112 + idx * 10,
        display + " · Age",
        f'(time()-backup_last_timestamp_seconds{{service="{service}",target="onedrive"}})/3600',
        16, yy, 8, 3,
        unit="h",
        decimals=1,
        thresholds=[
            {"color": GREEN, "value": None},
            {"color": YELLOW, "value": 24},
            {"color": RED, "value": 36},
        ],
    ))


# ============================================================
# 24 HOURS
# ============================================================

trend_y = vps_y + 9

panels.append(row(2200, "LAST 24 HOURS · TRENDS", trend_y))

panels.append(timeseries(
    2201,
    "Paperless Response Time",
    [
        target(
            'probe_duration_seconds{job="paperless-external"} * 1000',
            "A",
            "External"
        ),
        target(
            'probe_duration_seconds{job="http-services",service="Paperless"} * 1000',
            "B",
            "Internal"
        ),
    ],
    0, trend_y + 1, 12, 7, "ms"
))

panels.append(timeseries(
    2202,
    "Internet Latency",
    [
        target(
            'probe_duration_seconds{job="internet-icmp"} * 1000',
            "A",
            "{{service}}"
        )
    ],
    12, trend_y + 1, 12, 7, "ms"
))

panels.append(timeseries(
    2203,
    "WAN Traffic",
    [
        target(
            'fritz_wan_datarate_bytes{job="fritzbox",direction="rx"} * 8',
            "A",
            "Download"
        ),
        target(
            'fritz_wan_datarate_bytes{job="fritzbox",direction="tx"} * 8',
            "B",
            "Upload"
        ),
    ],
    0, trend_y + 8, 12, 7, "bps"
))

panels.append(timeseries(
    2204,
    "System Load",
    [
        target(
            '100-(avg(rate(node_cpu_seconds_total{job="raspberry-pi",mode="idle"}[5m]))*100)',
            "A",
            "Pi CPU"
        ),
        target(
            '100-(avg(rate(node_cpu_seconds_total{job="vps",mode="idle"}[5m]))*100)',
            "B",
            "VPS CPU"
        ),
    ],
    12, trend_y + 8, 12, 7, "percent"
))


# ============================================================
# DETAILS
# ============================================================

details_y = trend_y + 15

panels.append(row(
    2300,
    "DETAILS · CONTAINERS / COMPONENTS / MOUNTS",
    details_y,
    collapsed=False
))

panels.append(table(
    2301,
    "Container Running",
    [
        target(
            'home_container_running',
            "A",
            "{{container}}"
        )
    ],
    0, details_y + 1, 8, 8
))

panels.append(table(
    2302,
    "Container Restarts",
    [
        target(
            'home_container_restarts',
            "A",
            "{{container}}"
        )
    ],
    8, details_y + 1, 8, 8
))

panels.append(table(
    2303,
    "Mounts",
    [
        target(
            'home_mount_available',
            "A",
            "{{mount}}"
        )
    ],
    16, details_y + 1, 8, 8
))


dashboard = {
    "id": None,
    "uid": "home-infrastructure-v2",
    "title": "Home Infrastructure V2",
    "tags": [
        "home",
        "infrastructure",
        "operations"
    ],
    "timezone": "browser",
    "schemaVersion": 42,
    "version": 1,
    "refresh": "30s",
    "editable": True,
    "graphTooltip": 1,
    "time": {
        "from": "now-24h",
        "to": "now"
    },
    "timepicker": {},
    "templating": {
        "list": []
    },
    "annotations": {
        "list": []
    },
    "links": [],
    "panels": panels,
}

OUT.write_text(
    json.dumps(
        dashboard,
        indent=2,
        ensure_ascii=False
    ) + "\n"
)

print("Created:", OUT)
print("Panels:", len(panels))
print("UID:", dashboard["uid"])
