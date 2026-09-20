# Home dashboard

The homepage is built around a connected network map: Internet/WAN gateway,
LAN members (Pi on eth0, EX4100 and workstation) and the Pi-to-VPS WireGuard path.
Applications with direct links and current findings sit alongside the map.
The former domain tiles and detailed backup matrix have been removed. Backups
are a single status strip; failures still name the affected backup sets.
Addresses and relationships are documented inventory, not automatic discovery or
measured physical switch ports. Device badges reuse the existing aggregate health
states; the router badge refers to its WAN link and the tunnel badge to peer/handshake
health. Internet combines reachability and router telemetry; missing router data
must not be described as a successful overall Internet check. No per-device latency
or physical link speed is invented.

System values, dated recent events, the Paperless diagnostic path and 24-hour
latency charts share one initially collapsed detail section. Its open state persists
across polling. Workstation Wake-on-LAN remains available on its network card.
On narrow screens the LAN nodes stack with the Pi immediately above its VPN path.
Missing values display a dash or unknown status; failed/timed-out status requests
mark the previous display as stale. Unknown telemetry appears in the findings.
The frontend uses local CSS, SVG icons and vanilla JavaScript (`static/dashboard.js`),
with no external assets or new runtime dependencies. The backend API is unchanged.

Frontend checks (Node.js):

```sh
node system/tests/test_dashboard_network.cjs
```

Run the command from the repository root. An optional second argument is a saved
`/api/status` JSON response to exercise the complete renderer against real data.

The dashboard belongs to the `monitoring` Compose project. Run commands from
`/home/karsten/monitoring`:

```sh
docker compose up -d --build --wait home-dashboard
docker compose logs --tail=100 home-dashboard
```

There is deliberately no standalone Compose project in this directory. The
parent project owns the container and `./home-dashboard/data` bind mount.

The nightly monitoring backup stops the entire project before archiving it,
including the dashboard SQLite database. The archive contains the Dockerfile,
application, pinned Python requirements, templates, static files and database.
On a replacement host, Compose can build the dashboard from these sources.
Building on a fresh host requires access to the base image and Python packages.

Restore validation checks the database with SQLite `integrity_check` and verifies
that the `state` and `events` tables and dashboard build sources are present.
The standard monitoring restore workflow therefore covers the dashboard too.
