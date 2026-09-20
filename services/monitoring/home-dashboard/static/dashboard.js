"use strict";

const $ = id => document.getElementById(id);
const labels = {ok: "OK", warning: "Prüfen", error: "Störung", unknown: "Unbekannt", off: "Nicht aktiv", starting: "Startet"};
const safeState = state => Object.hasOwn(labels, state) ? state : "unknown";
const esc = value => String(value ?? "—").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
const fmt = (value, suffix = "") => value === null || value === undefined ? "—" : `${value}${suffix}`;
const badge = (state, text) => `<span class="badge ${safeState(state)}"><i class="dot" aria-hidden="true"></i>${esc(text ?? labels[safeState(state)])}</span>`;
const icon = name => `<svg class="node-icon" aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
let refreshing = false;
let waking = false;

function bitrate(value) {
    if (!Number.isFinite(value)) return "—";
    if (value >= 1e9) return `${(value / 1e9).toFixed(2)} Gbit/s`;
    if (value >= 1e6) return `${(value / 1e6).toFixed(1)} Mbit/s`;
    if (value >= 1e3) return `${(value / 1e3).toFixed(0)} kbit/s`;
    return `${value} bit/s`;
}

function renderNetwork(data) {
    const system = name => (data.systems || []).find(s => s.name === name) || {};
    const pi = system("Raspberry Pi"), nas = system("EX4100"), pc = system("MSI Workstation");
    const router = system("FRITZ!Box"), vps = system("VPS");
    const wg = (data.paperless_path || []).find(p => p.name === "WireGuard") || {};
    const internet = data.internet || {}, storage = data.storage || {};
    const node = (className, symbol, name, address, state, role, bottom = "") => `
        <article class="node ${className}"><div class="node-heading">${icon(symbol)}${badge(state)}</div>
        <h3>${esc(name)}</h3><div class="address">${esc(address)}</div><p class="role">${esc(role)}</p>
        ${bottom ? `<div class="node-bottom">${bottom}</div>` : ""}</article>`;
    const wake = pc.mode === "off" && pc.action === "wake"
        ? `<button class="wol-button" onclick="wakeWorkstation(this)" ${waking ? "disabled" : ""}>PC einschalten</button>` : "";
    const pcNote = pc.mode === "off" ? "Keine aktive Telemetrie" : pc.mode === "starting" ? "Wird gestartet…" : "Arbeitsplatz";
    // Internet state includes ICMP AND router telemetry; don't label it ICMP-only.
    $("network-topology").innerHTML = `
        <div class="uplink">
            ${node("internet", "globe", "Internet", "WAN / externe Ziele", internet.state, "Internet & Router-Telemetrie", esc(`${fmt(internet.latency, " ms")} · ${fmt(internet.loss, "%")} Verlust`))}
            ${node("router", "router", "FRITZ!Box", "192.168.0.1", router.state, "Gateway · WAN-Link")}
            <div class="traffic"><p>WAN-Datenrate</p><span>↓ ${esc(bitrate(internet.wan_rx))}</span><span>↑ ${esc(bitrate(internet.wan_tx))}</span><small>Aktueller Durchsatz</small></div>
        </div>
        <div class="lan-bus"><span>LAN · FRITZ!Box</span></div>
        <div class="lan-devices">
            ${node("nas", "server", "NAS · EX4100", "192.168.0.7", nas.state, "Dateien & Sicherungen", esc(`${fmt(storage.used_tb)} / ${fmt(storage.total_tb)} TB`))}
            ${node("pi", "server", "Raspberry Pi 5", "192.168.0.199 · eth0", pi.state, "Services & Monitoring")}
            ${node("workstation", "desktop", "MSI Workstation", "192.168.0.195", pc.state, pcNote, wake)}
        </div>
        <div class="vpn-connection"><div><div class="tunnel">${badge(wg.state, `WireGuard · ${labels[safeState(wg.state)]}`)}<small>Pi ↔ VPS · Handshake ${esc(fmt(data.wireguard_age, " s"))}</small></div></div></div>
        <div class="vpn-row">${node("vps", "cloud", "VPS", "10.8.0.1", vps.state, "Traefik · Paperless-Zugang", "Pi-Endpunkt: 10.8.0.2")}</div>`;
}

function renderServices(data) {
    const services = data.services || [];
    const urls = {"Home Assistant":"http://192.168.0.199:8123", "Paperless":"https://paperless.karikarstus.de", "Node-RED":"http://192.168.0.199:1880"};
    $("services-count").textContent = `${services.filter(s => s.state === "ok").length} / ${services.length} OK`;
    $("services").innerHTML = services.map(s => {
        const tag = Object.hasOwn(urls, s.name) ? "a" : "div";
        const attrs = tag === "a" ? ` href="${urls[s.name]}" target="_blank" rel="noopener noreferrer"` : "";
        return `<${tag} class="service"${attrs}><div><strong>${esc(s.name)} ${tag === "a" ? "↗" : ""}</strong><small>${esc(s.scope === "extern" ? "Öffentlicher Zugang" : s.scope === "lokal" ? "Im Heimnetz" : s.scope)}</small></div><div>${badge(s.state)}<small>${esc(fmt(s.response, " ms"))}</small></div></${tag}>`;
    }).join("") || '<p class="muted">Keine Anwendungsdaten verfügbar.</p>';
}

function renderFindings(data) {
    const findings = [...(data.findings || [])];
    if ([data.overall, ...Object.values(data.domains || {})].includes("unknown")) {
        findings.push({level:"unknown", title:"Messwerte unvollständig", detail:"Mindestens eine Quelle liefert keinen vollständigen Status. Unbekannte Werte sind in der Karte markiert."});
    }
    $("findings").innerHTML = findings.length ? findings.map(f => `<div class="finding ${safeState(f.level)}"><strong>${esc(f.title)}</strong><p>${esc(f.detail)}</p></div>`).join("")
        : data.overall === "ok" ? '<p class="all-clear"><strong>Alles im grünen Bereich.</strong>Keine aktuellen Auffälligkeiten.</p>'
        : '<p class="all-clear">Status prüfen: Nicht alle überwachten Bereiche melden OK.</p>';
}

function renderBackups(data) {
    const backups = Object.entries(data.backups || {});
    const issues = backups.filter(([, b]) => b.state !== "ok");
    const state = backups.length ? safeState(data.domains?.backups) : "unknown";
    const text = state === "ok" && !issues.length ? `${backups.length} Sicherungen aktuell`
        : issues.length ? `Prüfen: ${issues.map(([name]) => name).join(", ")}` : "Status unvollständig";
    $("backup-summary").innerHTML = `${icon("shield")}<strong>Backups</strong>${badge(state, text)}<span class="backup-note">${state === "ok" ? "Keine Aktion erforderlich" : "Details im Backup-Monitoring"}</span>`;
}

function sparkline(id, points) {
    const valid = (points || []).filter(p => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]));
    if (valid.length < 2) { $(id).innerHTML = '<text x="0" y="45">Keine Historie verfügbar</text>'; return; }
    const values = valid.map(p => p[1]);
    const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
    const start = valid[0][0], duration = valid[valid.length - 1][0] - start || 1;
    const line = valid.map(p => `${((p[0] - start) / duration * 600).toFixed(2)},${(72 - (p[1] - min) / span * 64).toFixed(2)}`).join(" ");
    $(id).innerHTML = `<polyline points="${line}" fill="none" stroke="currentColor" stroke-width="1.6" vector-effect="non-scaling-stroke"/>`;
}

function renderDetails(data) {
    $("systems").innerHTML = (data.systems || []).map(s => `<div class="system-row"><div>${badge(s.state, s.name)}</div><div>${esc(s.primary)}<small>${esc(s.secondary)}</small></div></div>`).join("");
    $("activity").innerHTML = (data.activity || []).slice(0, 6).map(e => {
        const date = new Date(e.timestamp * 1000);
        const time = date.toLocaleString("de-DE", {day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit"});
        return `<div class="activity-row"><time>${esc(time)}</time><span>${esc(e.text)}</span></div>`;
    }).join("") || '<p class="muted">Noch keine Zustandsänderungen aufgezeichnet.</p>';
    $("paperless-times").textContent = `Extern ${fmt(data.paperless_external_ms, " ms")} · intern ${fmt(data.paperless_internal_ms, " ms")}`;
    $("paperless-path").innerHTML = (data.paperless_path || []).map(p => badge(p.state, p.name)).join('<span class="path-arrow" aria-hidden="true">→</span>');
    const history = data.history24 || {};
    for (const name of ["internet", "paperless"]) {
        sparkline(`${name}-spark`, history[`${name}_spark`]);
        $(`${name}-spark-value`).textContent = `Ø ${fmt(history[`${name}_avg`], " ms")}`;
    }
}

function render(data) {
    const overall = {ok:"Alles in Ordnung", warning:"Aufmerksamkeit nötig", error:"Störung erkannt", unknown:"Status unvollständig"};
    $("overall").className = "badge " + safeState(data.overall);
    $("overall").innerHTML = badge(data.overall, overall[safeState(data.overall)]);
    renderNetwork(data);
    renderServices(data);
    renderFindings(data);
    renderBackups(data);
    renderDetails(data);
    $("updated").textContent = `Stand ${new Date(data.timestamp * 1000).toLocaleTimeString("de-DE")}`;
}

async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
        const response = await fetch("/api/status", {cache:"no-store", signal:AbortSignal.timeout(12000)});
        if (!response.ok) throw new Error("Status nicht verfügbar");
        const data = await response.json();
        if (!Number.isFinite(data.timestamp) || Math.abs(Date.now() / 1000 - data.timestamp) > 60) throw new Error("Veralteter Status");
        render(data);
        $("network-stale").classList.add("hidden");
        document.body.classList.remove("data-stale");
    } catch (error) {
        $("network-stale").classList.remove("hidden");
        document.body.classList.add("data-stale");
        $("overall").className = "badge error";
        $("overall").innerHTML = badge("error", "Daten nicht verfügbar");
    } finally { refreshing = false; }
}

async function wakeWorkstation(button) {
    if (waking) return;
    waking = true;
    if (button) button.disabled = true;
    try {
        const response = await fetch("/api/workstation/wake", {method:"POST", cache:"no-store", signal:AbortSignal.timeout(12000)});
        const result = await response.json();
        if (!response.ok) throw new Error(result.message || "WoL fehlgeschlagen");
        await refresh();
    } catch (error) {
        alert("Workstation konnte nicht gestartet werden: " + error.message);
    } finally {
        waking = false;
        document.querySelectorAll(".wol-button").forEach(b => { b.disabled = false; });
    }
}

// Start polling only after the deferred script has the complete document.
refresh();
setInterval(refresh, 15000);
