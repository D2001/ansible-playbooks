from flask import Flask, render_template, jsonify
import requests
import time
import socket
import threading
import sqlite3
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

PROMETHEUS = "http://127.0.0.1:9090"
session = requests.Session()

WORKSTATION_MAC = "fc:9d:05:76:e7:79"
WORKSTATION_BROADCAST = "192.168.0.255"
WORKSTATION_WOL_PORT = 9
WORKSTATION_IP = "192.168.0.195"

EVENT_DB = "/data/events.db"

workstation_lock = threading.Lock()
workstation_start_requested = 0


def send_magic_packet():
    mac = WORKSTATION_MAC.replace(":", "").replace("-", "")

    if len(mac) != 12:
        raise ValueError("Invalid workstation MAC")

    packet = bytes.fromhex("FF" * 6 + mac * 16)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(
            packet,
            (WORKSTATION_BROADCAST, WORKSTATION_WOL_PORT)
        )
    finally:
        sock.close()





# ============================================================
# Workstation AI + event helpers
# ============================================================

def ai_status():

    result = {
        "ollama": False,
        "openwebui": False,
        "models": [],
    }

    try:
        r = session.get(
            f"http://{WORKSTATION_IP}:11434/api/ps",
            timeout=1.5,
        )

        if r.ok:
            result["ollama"] = True

            result["models"] = [
                m.get("name") or m.get("model")
                for m in r.json().get("models", [])
                if m.get("name") or m.get("model")
            ]

    except Exception:
        pass


    try:
        r = session.get(
            f"http://{WORKSTATION_IP}:3000/",
            timeout=1.5,
        )

        result["openwebui"] = (
            r.status_code < 500
        )

    except Exception:
        pass


    return result



def event_db():

    db = sqlite3.connect(
        EVENT_DB,
        timeout=3,
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            level TEXT NOT NULL,
            text TEXT NOT NULL
        )
        """
    )

    return db



def add_event(level, text):

    try:

        with event_db() as db:

            last = db.execute(
                """
                SELECT ts,text
                FROM events
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

            now = int(time.time())

            if (
                not last
                or last[1] != text
                or now - last[0] > 30
            ):

                db.execute(
                    """
                    INSERT INTO events(
                        ts,
                        level,
                        text
                    )
                    VALUES(?,?,?)
                    """,
                    (
                        now,
                        level,
                        text,
                    ),
                )

                db.execute(
                    """
                    DELETE FROM events
                    WHERE id NOT IN (
                        SELECT id
                        FROM events
                        ORDER BY id DESC
                        LIMIT 100
                    )
                    """
                )

    except Exception:
        pass



def track_state(
    key,
    value,
    online_text,
    offline_text,
    warning_text=None,
):

    try:

        with event_db() as db:

            row = db.execute(
                """
                SELECT value
                FROM state
                WHERE key=?
                """,
                (key,),
            ).fetchone()

            previous = (
                row[0]
                if row
                else None
            )

            db.execute(
                """
                INSERT INTO state(key,value)
                VALUES(?,?)
                ON CONFLICT(key)
                DO UPDATE SET
                    value=excluded.value
                """,
                (
                    key,
                    value,
                ),
            )


        # First observation establishes baseline.
        # It is deliberately not logged as an event.
        if (
            previous is None
            or previous == value
        ):
            return


        if value == "ok":

            add_event(
                "ok",
                online_text,
            )


        elif (
            value == "warning"
            and warning_text
        ):

            add_event(
                "warning",
                warning_text,
            )


        elif value in (
            "error",
            "off",
        ):

            add_event(
                (
                    "error"
                    if value == "error"
                    else "info"
                ),
                offline_text,
            )

    except Exception:
        pass



def recent_events(limit=8):

    try:

        with event_db() as db:

            rows = db.execute(
                """
                SELECT
                    ts,
                    level,
                    text
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()


        return [
            {
                "timestamp": ts,
                "level": level,
                "text": text,
            }
            for ts, level, text in rows
        ]

    except Exception:

        return []



# ============================================================
# Prometheus helpers
# ============================================================

def prom(query):
    try:
        r = session.get(
            f"{PROMETHEUS}/api/v1/query",
            params={"query": query},
            timeout=4,
        )
        r.raise_for_status()

        result = r.json().get("data", {}).get("result", [])

        if not result:
            return None

        return float(result[0]["value"][1])

    except Exception:
        return None


def prom_range(query, hours=24, step=300):
    """Return Prometheus range data as [[timestamp, value], ...]."""
    try:
        end = int(time.time())
        start = end - (hours * 3600)

        r = session.get(
            f"{PROMETHEUS}/api/v1/query_range",
            params={
                "query": query,
                "start": start,
                "end": end,
                "step": step,
            },
            timeout=6,
        )
        r.raise_for_status()

        result = r.json().get("data", {}).get("result", [])

        if not result:
            return []

        points = []

        for ts, value in result[0].get("values", []):
            try:
                points.append([int(float(ts)), float(value)])
            except (TypeError, ValueError):
                pass

        return points

    except Exception:
        return []


def query_all(queries):
    result = {}

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {
            key: pool.submit(prom, query)
            for key, query in queries.items()
        }

        for key, future in futures.items():
            try:
                result[key] = future.result()
            except Exception:
                result[key] = None

    return result


def state(value, warning=False):
    if value is None:
        return "unknown"
    if warning:
        return "warning"
    return "ok" if value >= 1 else "error"


def rounded(value, digits=1):
    if value is None:
        return None
    return round(value, digits)


def worst(*states):
    order = {
        "ok": 0,
        "unknown": 1,
        "warning": 2,
        "error": 3,
    }

    return max(states, key=lambda x: order.get(x, 1))


# ============================================================
# Backup helper
# ============================================================

def backup_state(values, service, full=True):
    prefix = f"backup_{service}"

    local = values.get(prefix + "_local") if full else None
    nas = values.get(prefix + "_nas") if full else None
    cloud = values.get(prefix + "_cloud")
    match = values.get(prefix + "_match") if full else None
    cloud_query = values.get(prefix + "_cloud_query")
    age = values.get(prefix + "_age")

    if age is None:
        age_state = "unknown"
    elif age > 36:
        age_state = "error"
    elif age > 24:
        age_state = "warning"
    else:
        age_state = "ok"

    parts = [
        state(cloud),
        state(cloud_query),
        age_state,
    ]

    if full:
        parts.extend([
            state(local),
            state(nas),
            state(match),
        ])

    return {
        "local": state(local) if full else "na",
        "nas": state(nas) if full else "na",
        "cloud": state(cloud),
        "match": state(match) if full else "na",
        "cloud_query": state(cloud_query),
        "age": rounded(age, 1),
        "age_state": age_state,
        "state": worst(*parts),
    }


# ============================================================
# Main data model
# ============================================================

def build_status():

    queries = {

        # Internet
        "internet":
            'max(probe_success{job="internet-icmp"})',

        "internet_latency":
            'avg(probe_duration_seconds{job="internet-icmp"}) * 1000',

        "internet_loss":
            '100 * (1 - avg_over_time('
            'probe_success{job="internet-icmp"}[5m]))',

        "fritz":
            'fritz_wan_phys_link_status{job="fritzbox"}',

        "wan_rx":
            'fritz_wan_datarate_bytes'
            '{job="fritzbox",direction="rx"} * 8',

        "wan_tx":
            'fritz_wan_datarate_bytes'
            '{job="fritzbox",direction="tx"} * 8',

        "wan_rx_max":
            'fritz_wan_max_bitrate_bps'
            '{job="fritzbox",direction="rx"}',

        "wan_tx_max":
            'fritz_wan_max_bitrate_bps'
            '{job="fritzbox",direction="tx"}',


        # Services
        "ha":
            'probe_success{job="http-services",service="Home Assistant"}',

        "ha_ms":
            'probe_duration_seconds'
            '{job="http-services",service="Home Assistant"} * 1000',

        "paperless":
            'probe_success{job="http-services",service="Paperless"}',

        "paperless_ms":
            'probe_duration_seconds'
            '{job="http-services",service="Paperless"} * 1000',

        "paperless_external":
            'probe_success{job="paperless-external"}',

        "paperless_external_ms":
            'probe_duration_seconds{job="paperless-external"} * 1000',

        "paperless_dns":
            'probe_success{job="paperless-dns"}',

        "paperless_web":
            'home_paperless_component_up{component="web"}',

        "paperless_db":
            'home_paperless_component_up{component="postgres"}',

        "paperless_redis":
            'home_paperless_component_up{component="redis"}',

        "nodered":
            'probe_success{job="http-services",service="Node-RED"}',

        "nodered_ms":
            'probe_duration_seconds'
            '{job="http-services",service="Node-RED"} * 1000',



        # Workstation
        "workstation":
            'up{job="windows-workstation"}',

        "workstation_cpu":
            '100 - (avg(rate(windows_cpu_time_total'
            '{job="windows-workstation",mode="idle"}[5m])) * 100)',

        "workstation_ram":
            '(1 - windows_memory_available_bytes'
            '{job="windows-workstation"} / '
            'windows_memory_physical_total_bytes'
            '{job="windows-workstation"}) * 100',

        "workstation_c":
            '100 * (1 - windows_logical_disk_free_bytes'
            '{job="windows-workstation",volume="C:"} / '
            'windows_logical_disk_size_bytes'
            '{job="windows-workstation",volume="C:"})',


        "workstation_gpu":
            '100 * max(sum by (luid,eng,engtype) ('
            'rate(windows_gpu_engine_time_seconds'
            '{job="windows-workstation",'
            'device_id=~".*VEN_10DE.*"}[1m])))',

        "workstation_vram_used":
            'sum(windows_gpu_adapter_memory_dedicated_bytes'
            '{job="windows-workstation",'
            'device_id=~".*VEN_10DE.*"})',

        "workstation_vram_total":
            'sum(windows_gpu_dedicated_video_memory_size_bytes'
            '{job="windows-workstation",'
            'device_id=~".*VEN_10DE.*"})',


        # Systems
        "pi":
            'up{job="raspberry-pi"}',

        "pi_cpu":
            '100 - (avg(rate(node_cpu_seconds_total'
            '{job="raspberry-pi",mode="idle"}[5m])) * 100)',

        "pi_ram":
            '(1 - node_memory_MemAvailable_bytes{job="raspberry-pi"} / '
            'node_memory_MemTotal_bytes{job="raspberry-pi"}) * 100',

        "pi_temp":
            'avg(node_hwmon_temp_celsius'
            '{job="raspberry-pi",chip="thermal_thermal_zone0"})',

        "timesync":
            'home_timesync_up',

        "vps":
            'up{job="vps"}',

        "vps_cpu":
            '100 - (avg(rate(node_cpu_seconds_total'
            '{job="vps",mode="idle"}[5m])) * 100)',

        "vps_ram":
            '(1 - node_memory_MemAvailable_bytes{job="vps"} / '
            'node_memory_MemTotal_bytes{job="vps"}) * 100',

        "vps_disk":
            '100 * (1 - node_filesystem_avail_bytes'
            '{job="vps",mountpoint="/",fstype!="rootfs"} / '
            'node_filesystem_size_bytes'
            '{job="vps",mountpoint="/",fstype!="rootfs"})',

        "traefik":
            'up{job="vps-traefik"}',

        "wg_peer":
            'wireguard_peer_up{job="vps",peer="paperless"}',

        "wg_age":
            'wireguard_peer_handshake_age_seconds'
            '{job="vps",peer="paperless"}',


        # NAS
        "nas":
            'home_ex4100_up',

        "nas_temp":
            'home_ex4100_temperature_celsius',

        "nas_fan":
            'home_ex4100_fan_up',

        "disk1":
            'home_ex4100_disk_present{disk="1"}',

        "disk2":
            'home_ex4100_disk_present{disk="2"}',

        "disk1_temp":
            'home_ex4100_disk_temperature_celsius{disk="1"}',

        "disk2_temp":
            'home_ex4100_disk_temperature_celsius{disk="2"}',

        "nas_used":
            '100 * '
            'ex4100_hrStorageUsed{storage="/mnt/HD/HD_a2"} / '
            'ex4100_hrStorageSize{storage="/mnt/HD/HD_a2"}',


        "nas_used_bytes":
            'ex4100_hrStorageUsed'
            '{storage="/mnt/HD/HD_a2"} * '
            'ex4100_hrStorageAllocationUnits'
            '{storage="/mnt/HD/HD_a2"}',

        "nas_total_bytes":
            'ex4100_hrStorageSize'
            '{storage="/mnt/HD/HD_a2"} * '
            'ex4100_hrStorageAllocationUnits'
            '{storage="/mnt/HD/HD_a2"}',


        # Backup collector
        "backup_collector_age":
            '(time()-backup_collector_last_success_timestamp_seconds)/60',

        "backup_nas_mount":
            'backup_nas_mount_up',
    }


    # --------------------------------------------------------
    # Backup queries
    # --------------------------------------------------------

    full_backups = [
        "homeassistant",
        "paperless",
        "monitoring",
    ]

    cloud_backups = [
        "traefik",
        "sentinel",
        "vps-dr",
    ]

    for service in full_backups:

        p = f"backup_{service}"

        queries[p + "_local"] = (
            f'backup_present{{service="{service}",target="local"}}'
        )

        queries[p + "_nas"] = (
            f'backup_present{{service="{service}",target="nas"}}'
        )

        queries[p + "_cloud"] = (
            f'backup_present{{service="{service}",target="onedrive"}}'
        )

        queries[p + "_match"] = (
            f'backup_all_targets_match{{service="{service}"}}'
        )

        queries[p + "_cloud_query"] = (
            f'backup_cloud_query_success{{service="{service}"}}'
        )

        queries[p + "_age"] = (
            f'(time()-backup_last_timestamp_seconds'
            f'{{service="{service}",target="onedrive"}})/3600'
        )


    for service in cloud_backups:

        p = f"backup_{service}"

        queries[p + "_cloud"] = (
            f'backup_present{{service="{service}",target="onedrive"}}'
        )

        queries[p + "_cloud_query"] = (
            f'backup_cloud_query_success{{service="{service}"}}'
        )

        queries[p + "_age"] = (
            f'(time()-backup_last_timestamp_seconds'
            f'{{service="{service}",target="onedrive"}})/3600'
        )


    v = query_all(queries)


    # ========================================================
    # 24 hour summary
    # ========================================================

    history_queries = {
        "paperless_availability":
            'avg_over_time(probe_success{job="paperless-external"}[24h]) * 100',

        "paperless_avg":
            'avg_over_time(probe_duration_seconds{job="paperless-external"}[24h]) * 1000',

        "paperless_peak":
            'max_over_time(probe_duration_seconds{job="paperless-external"}[24h]) * 1000',

        "internet_loss_24h":
            '100 * (1 - avg_over_time(probe_success{job="internet-icmp"}[24h]))',

        "internet_avg":
            'avg_over_time(probe_duration_seconds{job="internet-icmp"}[24h]) * 1000',

        "pi_cpu_avg":
            'avg_over_time((100 - (avg(rate(node_cpu_seconds_total{job="raspberry-pi",mode="idle"}[5m])) * 100))[24h:5m])',

        "pi_cpu_peak":
            'max_over_time((100 - (avg(rate(node_cpu_seconds_total{job="raspberry-pi",mode="idle"}[5m])) * 100))[24h:5m])',

        "pi_temp_peak":
            'max_over_time(node_hwmon_temp_celsius{job="raspberry-pi",chip="thermal_thermal_zone0"}[24h])',
    }

    history_values = query_all(history_queries)

    paperless_spark = prom_range(
        'avg(probe_duration_seconds{job="paperless-external"}) * 1000',
        24,
        300,
    )

    internet_spark = prom_range(
        'avg(probe_duration_seconds{job="internet-icmp"}) * 1000',
        24,
        300,
    )


    # ========================================================
    # Individual states
    # ========================================================

    internet_state = worst(
        state(v["internet"]),
        state(v["fritz"]),
    )


    # WireGuard:
    # peer must be up AND recent handshake
    if v["wg_peer"] is None or v["wg_age"] is None:
        wg_state = "unknown"
    elif v["wg_peer"] < 1:
        wg_state = "error"
    elif v["wg_age"] > 180:
        wg_state = "error"
    elif v["wg_age"] > 150:
        wg_state = "warning"
    else:
        wg_state = "ok"


    # Workstation
    global workstation_start_requested

    workstation_online = (
        v["workstation"] is not None
        and v["workstation"] >= 1
    )

    with workstation_lock:
        start_age = (
            time.time() - workstation_start_requested
            if workstation_start_requested
            else None
        )

        if workstation_online:
            workstation_start_requested = 0
            workstation_state = "ok"
            workstation_mode = "online"

        elif start_age is not None and start_age < 120:
            workstation_state = "starting"
            workstation_mode = "starting"

        else:
            workstation_start_requested = 0
            workstation_state = "off"
            workstation_mode = "off"


    ai = (
        ai_status()
        if workstation_online
        else {
            "ollama": False,
            "openwebui": False,
            "models": [],
        }
    )


    # AI is optional while the workstation is off.
    # When the workstation is online, however, both
    # services are expected to be available.
    if (
        workstation_online
        and (
            not ai["ollama"]
            or not ai["openwebui"]
        )
    ):
        workstation_state = "warning"


    # Pi temperature
    if v["pi_temp"] is None:
        pi_temp_state = "unknown"
    elif v["pi_temp"] >= 80:
        pi_temp_state = "error"
    elif v["pi_temp"] >= 70:
        pi_temp_state = "warning"
    else:
        pi_temp_state = "ok"


    pi_state = worst(
        state(v["pi"]),
        pi_temp_state,
        state(v["timesync"]),
    )


    # VPS disk
    if v["vps_disk"] is None:
        vps_disk_state = "unknown"
    elif v["vps_disk"] >= 90:
        vps_disk_state = "error"
    elif v["vps_disk"] >= 80:
        vps_disk_state = "warning"
    else:
        vps_disk_state = "ok"


    vps_state = worst(
        state(v["vps"]),
        vps_disk_state,
    )


    # NAS
    if v["nas_temp"] is None:
        nas_temp_state = "unknown"
    elif v["nas_temp"] >= 55:
        nas_temp_state = "error"
    elif v["nas_temp"] >= 48:
        nas_temp_state = "warning"
    else:
        nas_temp_state = "ok"


    if v["nas_used"] is None:
        nas_space_state = "unknown"
    elif v["nas_used"] >= 95:
        nas_space_state = "error"
    elif v["nas_used"] >= 85:
        nas_space_state = "warning"
    else:
        nas_space_state = "ok"


    nas_state = worst(
        state(v["nas"]),
        state(v["nas_fan"]),
        state(v["disk1"]),
        state(v["disk2"]),
        nas_temp_state,
        nas_space_state,
    )


    # Services
    ha_state = state(v["ha"])

    paperless_state = worst(
        state(v["paperless"]),
        state(v["paperless_web"]),
        state(v["paperless_db"]),
        state(v["paperless_redis"]),
        state(v["paperless_external"]),
    )

    nodered_state = state(v["nodered"])


    services_state = worst(
        ha_state,
        paperless_state,
        nodered_state,
    )


    systems_state = worst(
        pi_state,
        vps_state,
        nas_state,
        state(v["fritz"]),
    )


    # ========================================================
    # Backups
    # ========================================================

    backups = {
        "Home Assistant":
            backup_state(v, "homeassistant"),

        "Paperless":
            backup_state(v, "paperless"),


        "Monitoring":
            backup_state(v, "monitoring"),

        "Traefik":
            backup_state(v, "traefik", False),

        "Sentinel":
            backup_state(v, "sentinel", False),

        "VPS-DR":
            backup_state(v, "vps-dr", False),
    }


    backup_states = [
        b["state"]
        for b in backups.values()
    ]


    if v["backup_collector_age"] is None:
        collector_state = "unknown"
    elif v["backup_collector_age"] > 45:
        collector_state = "error"
    elif v["backup_collector_age"] > 30:
        collector_state = "warning"
    else:
        collector_state = "ok"


    backups_state = worst(
        collector_state,
        state(v["backup_nas_mount"]),
        *backup_states,
    )


    # ========================================================
    # Findings / anomalies
    # ========================================================

    findings = []


    def finding(level, title, detail):
        findings.append({
            "level": level,
            "title": title,
            "detail": detail,
        })


    if v["internet"] is not None and v["internet"] < 1:
        finding(
            "error",
            "Internet nicht erreichbar",
            "Beide externen ICMP-Prüfungen sind fehlgeschlagen."
        )


    if v["fritz"] is not None and v["fritz"] < 1:
        finding(
            "error",
            "FRITZ!Box meldet WAN offline",
            "Der physische WAN-Link ist nicht aktiv."
        )


    if wg_state == "error":
        finding(
            "error",
            "WireGuard-Verbindung auffällig",
            (
                f"Letzter Handshake vor "
                f"{rounded(v['wg_age'], 0)} Sekunden."
                if v["wg_age"] is not None
                else "Handshake-Metrik nicht verfügbar."
            )
        )

    elif wg_state == "warning":
        finding(
            "warning",
            "WireGuard-Handshake wird alt",
            f"Letzter Handshake vor {rounded(v['wg_age'], 0)} Sekunden."
        )


    if v["paperless_external"] is not None and v["paperless_external"] < 1:
        finding(
            "error",
            "Paperless extern nicht erreichbar",
            "Der externe HTTPS-Probe ist fehlgeschlagen."
        )


    if v["paperless_db"] is not None and v["paperless_db"] < 1:
        finding(
            "error",
            "Paperless PostgreSQL nicht verfügbar",
            "Die Datenbank-Komponente meldet einen Fehler."
        )


    if v["paperless_redis"] is not None and v["paperless_redis"] < 1:
        finding(
            "error",
            "Paperless Redis nicht verfügbar",
            "Die Redis-Komponente meldet einen Fehler."
        )


    if (
        workstation_online
        and not ai["ollama"]
    ):
        finding(
            "warning",
            "Ollama nicht erreichbar",
            "Workstation ist online, aber die Ollama API antwortet nicht."
        )


    if (
        workstation_online
        and not ai["openwebui"]
    ):
        finding(
            "warning",
            "Open WebUI nicht erreichbar",
            "Workstation ist online, aber Open WebUI antwortet nicht."
        )


    if pi_temp_state in ("warning", "error"):
        finding(
            pi_temp_state,
            "Raspberry Pi Temperatur erhöht",
            f"Aktuell {rounded(v['pi_temp'], 1)} °C."
        )


    if vps_disk_state in ("warning", "error"):
        finding(
            vps_disk_state,
            "VPS Speicherplatz wird knapp",
            f"Root-Dateisystem ist zu {rounded(v['vps_disk'], 1)} % belegt."
        )


    if nas_space_state in ("warning", "error"):
        finding(
            nas_space_state,
            "NAS Speicherplatz wird knapp",
            f"Volume ist zu {rounded(v['nas_used'], 1)} % belegt."
        )


    if nas_temp_state in ("warning", "error"):
        finding(
            nas_temp_state,
            "NAS Temperatur erhöht",
            f"Systemtemperatur aktuell {rounded(v['nas_temp'], 0)} °C."
        )


    if v["nas_fan"] is not None and v["nas_fan"] < 1:
        finding(
            "error",
            "NAS Lüfterproblem",
            "Der EX4100 meldet den Lüfter nicht als laufend."
        )


    if collector_state in ("warning", "error"):
        finding(
            collector_state,
            "Backup-Monitoring veraltet",
            (
                f"Letzte erfolgreiche Prüfung vor "
                f"{rounded(v['backup_collector_age'], 0)} Minuten."
            )
        )


    for name, backup in backups.items():
        if backup["state"] in ("warning", "error"):
            finding(
                backup["state"],
                f"{name} Backup prüfen",
                (
                    f"Letztes Cloud-Backup vor "
                    f"{backup['age']} Stunden."
                    if backup["age"] is not None
                    else "Backup-Zeitpunkt unbekannt."
                )
            )


    # ========================================================
    # Activity log
    # ========================================================

    track_state(
        "workstation",
        (
            "ok"
            if workstation_online
            else "off"
        ),
        "MSI Workstation online",
        "MSI Workstation ausgeschaltet",
    )

    track_state(
        "internet",
        internet_state,
        "Internet wieder erreichbar",
        "Internet nicht erreichbar",
        "Internet auffällig",
    )

    track_state(
        "paperless",
        paperless_state,
        "Paperless wieder erreichbar",
        "Paperless nicht erreichbar",
        "Paperless auffällig",
    )

    track_state(
        "wireguard",
        wg_state,
        "WireGuard wieder stabil",
        "WireGuard-Verbindung unterbrochen",
        "WireGuard-Handshake auffällig",
    )

    track_state(
        "backups",
        backups_state,
        "Backups wieder vollständig",
        "Backup-Problem erkannt",
        "Backups benötigen Aufmerksamkeit",
    )


    # ========================================================
    # Overall
    # ========================================================

    overall_state = worst(
        internet_state,
        systems_state,
        services_state,
        nas_state,
        backups_state,
    )


    # ========================================================
    # Paperless diagnostic path
    # ========================================================

    paperless_path = [
        {
            "name": "Internet",
            "state": state(v["internet"]),
        },
        {
            "name": "DNS",
            "state": state(v["paperless_dns"]),
        },
        {
            "name": "VPS",
            "state": state(v["vps"]),
        },
        {
            "name": "Traefik",
            "state": state(v["traefik"]),
        },
        {
            "name": "WireGuard",
            "state": wg_state,
        },
        {
            "name": "Pi",
            "state": state(v["pi"]),
        },
        {
            "name": "Paperless",
            "state": state(v["paperless"]),
        },
    ]


    # ========================================================
    # Response
    # ========================================================

    return {

        "timestamp": int(time.time()),

        "overall": overall_state,

        "domains": {
            "internet": internet_state,
            "systems": systems_state,
            "services": services_state,
            "storage": nas_state,
            "backups": backups_state,
        },

        "internet": {
            "state": internet_state,
            "latency": rounded(v["internet_latency"], 1),
            "loss": rounded(v["internet_loss"], 1),
            "wan_rx": rounded(v["wan_rx"], 0),
            "wan_tx": rounded(v["wan_tx"], 0),
            "wan_rx_max": rounded(v["wan_rx_max"], 0),
            "wan_tx_max": rounded(v["wan_tx_max"], 0),
        },

        "systems": [
            {
                "name": "MSI Workstation",
                "state": workstation_state,
                "mode": workstation_mode,
                "action": "wake",
                "primary": (
                    f"CPU {rounded(v['workstation_cpu'],1)}% · "
                    f"GPU {rounded(v['workstation_gpu'],1)}%"
                    if workstation_online
                    else (
                        "Startet…"
                        if workstation_mode == "starting"
                        else "Ausgeschaltet"
                    )
                ),
                "secondary": (
                    (
                        f"RAM {rounded(v['workstation_ram'],1)}% · "
                        f"VRAM "
                        f"{rounded((v['workstation_vram_used'] or 0)/1073741824,1)}/"
                        f"{rounded((v['workstation_vram_total'] or 0)/1073741824,1)} GB · "
                        +
                        (
                            "Modell " + ", ".join(ai["models"])
                            if ai["models"]
                            else "KI bereit"
                        )
                    )
                    if workstation_online
                    else (
                        f"WoL gesendet · {rounded(start_age,0)} s"
                        if workstation_mode == "starting"
                        and start_age is not None
                        else "Wake-on-LAN verfügbar"
                    )
                ),
                "ai": (
                    ai
                    if workstation_online
                    else None
                ),
            },
            {
                "name": "Raspberry Pi",
                "state": pi_state,
                "primary": f"CPU {rounded(v['pi_cpu'],1)}%",
                "secondary": (
                    f"RAM {rounded(v['pi_ram'],1)}% · "
                    f"{rounded(v['pi_temp'],1)}°C"
                ),
            },
            {
                "name": "VPS",
                "state": vps_state,
                "primary": f"CPU {rounded(v['vps_cpu'],1)}%",
                "secondary": (
                    f"RAM {rounded(v['vps_ram'],1)}% · "
                    f"Disk {rounded(v['vps_disk'],1)}%"
                ),
            },
            {
                "name": "EX4100",
                "state": nas_state,
                "primary": (
                    (
                        f"{rounded(v['nas_used_bytes']/1000000000000,1)} / "
                        f"{rounded(v['nas_total_bytes']/1000000000000,1)} TB"
                    )
                    if (
                        v["nas_used_bytes"] is not None
                        and v["nas_total_bytes"] is not None
                    )
                    else "Volume unbekannt"
                ),
                "secondary": (
                    f"{rounded(v['nas_temp'],0)}°C · "
                    f"HDD {rounded(v['disk1_temp'],0)}° / "
                    f"{rounded(v['disk2_temp'],0)}°"
                ),
            },
            {
                "name": "FRITZ!Box",
                "state": state(v["fritz"]),
                "primary": (
                    "WAN online"
                    if v["fritz"] is not None and v["fritz"] >= 1
                    else "WAN prüfen"
                ),
                "secondary": (
                    f"↓ {rounded((v['wan_rx'] or 0)/1000000,1)} · "
                    f"↑ {rounded((v['wan_tx'] or 0)/1000000,1)} Mbit/s"
                ),
            },
        ],

        "services": [
            {
                "name": "Home Assistant",
                "state": ha_state,
                "response": rounded(v["ha_ms"], 1),
                "scope": "lokal",
            },
            {
                "name": "Paperless",
                "state": paperless_state,
                "response": rounded(v["paperless_external_ms"], 0),
                "scope": "extern",
            },
            {
                "name": "Node-RED",
                "state": nodered_state,
                "response": rounded(v["nodered_ms"], 1),
                "scope": "lokal",
            },
        ],

        "storage": {
            "state": nas_state,
            "used": rounded(v["nas_used"], 1),
            "temp": rounded(v["nas_temp"], 0),
            "disk1_temp": rounded(v["disk1_temp"], 0),
            "disk2_temp": rounded(v["disk2_temp"], 0),
            "fan": state(v["nas_fan"]),
            "used_tb": (
                rounded(
                    v["nas_used_bytes"] / 1000000000000,
                    1,
                )
                if v["nas_used_bytes"] is not None
                else None
            ),
            "total_tb": (
                rounded(
                    v["nas_total_bytes"] / 1000000000000,
                    1,
                )
                if v["nas_total_bytes"] is not None
                else None
            ),
        },

        "backups": backups,

        "backup_collector_age":
            rounded(v["backup_collector_age"], 1),

        "findings": findings,

        "activity": recent_events(),

        "paperless_path": paperless_path,

        "paperless_external_state":
            state(v["paperless_external"]),

        "paperless_external_ms":
            rounded(v["paperless_external_ms"], 0),

        "paperless_internal_ms":
            rounded(v["paperless_ms"], 1),

        "wireguard_age":
            rounded(v["wg_age"], 0),

        "history24": {
            "paperless_availability":
                rounded(history_values["paperless_availability"], 2),

            "paperless_avg":
                rounded(history_values["paperless_avg"], 0),

            "paperless_peak":
                rounded(history_values["paperless_peak"], 0),

            "internet_loss":
                rounded(history_values["internet_loss_24h"], 2),

            "internet_avg":
                rounded(history_values["internet_avg"], 1),

            "pi_cpu_avg":
                rounded(history_values["pi_cpu_avg"], 1),

            "pi_cpu_peak":
                rounded(history_values["pi_cpu_peak"], 1),

            "pi_temp_peak":
                rounded(history_values["pi_temp_peak"], 1),

            "paperless_spark":
                paperless_spark,

            "internet_spark":
                internet_spark,
        },
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify(build_status())


@app.route("/api/workstation/wake", methods=["POST"])
def wake_workstation():
    global workstation_start_requested

    current = prom(
        'up{job="windows-workstation"}'
    )

    if current is not None and current >= 1:
        return jsonify({
            "status": "already-online"
        })

    try:
        # Send several packets. Cheap and improves WoL reliability.
        for _ in range(3):
            send_magic_packet()
            time.sleep(0.15)

        with workstation_lock:
            workstation_start_requested = time.time()

        return jsonify({
            "status": "sent",
            "mac": WORKSTATION_MAC
        })

    except Exception as exc:
        return jsonify({
            "status": "error",
            "message": str(exc)
        }), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=3080,
        threaded=True,
    )
