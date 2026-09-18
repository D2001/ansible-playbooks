# Home dashboard

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
