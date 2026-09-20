# Home dashboard

The homepage provides a compact logical network overview: Internet/WAN gateway,
LAN members (Pi on eth0, EX4100 and workstation) and the Pi-to-VPS WireGuard path.
Addresses and relationships are documented inventory, not automatic discovery or
measured physical switch ports. Device badges reuse the existing aggregate health
states; the router badge refers to its WAN link and the tunnel badge to peer/handshake
health. No per-device latency or physical link speed is invented.

System/application details are collapsible; workstation Wake-on-LAN remains
available on its network card. Backups, findings and history remain accessible.
Missing values display a dash or unknown status; failed/timed-out status requests
mark the previous display as stale. Retired XMLTV is no longer named in the summary.

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
