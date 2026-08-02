#!/usr/bin/env python3
"""Build a portable description of a running Docker Compose service."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def run(*argv):
    result = subprocess.run(argv, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "command failed: " + " ".join(argv))
    return result.stdout


def is_below(path, root):
    try:
        Path(path).resolve().relative_to(root)
        return True
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-name", required=True)
    parser.add_argument("--service-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    service_dir = Path(args.service_dir).resolve()
    compose = json.loads(
        run(
            "docker", "compose", "--project-directory", str(service_dir),
            "config", "--format", "json",
        )
    )

    container_ids = run(
        "docker", "compose", "--project-directory", str(service_dir),
        "ps", "--all", "--quiet",
    ).split()
    containers = []
    if container_ids:
        containers = json.loads(run("docker", "inspect", *container_ids))

    actual_mounts = []
    for container in containers:
        labels = (container.get("Config") or {}).get("Labels") or {}
        compose_service = labels.get("com.docker.compose.service", "")
        for mount in container.get("Mounts") or []:
            if mount.get("Type") not in {"bind", "volume"}:
                continue
            actual_mounts.append({
                "compose_service": compose_service,
                "type": mount.get("Type"),
                "source": mount.get("Source"),
                "name": mount.get("Name", ""),
                "target": mount.get("Destination"),
                "read_only": not bool(mount.get("RW", True)),
            })

    portable_binds = []
    runtime_binds = []
    external_binds = []
    named_volumes = []
    for mount in actual_mounts:
        if mount["type"] == "volume":
            named_volumes.append(mount)
            continue
        source = mount["source"]
        if is_below(source, service_dir):
            item = dict(mount)
            item["relative_source"] = os.path.relpath(source, service_dir)
            portable_binds.append(item)
        elif mount["read_only"]:
            runtime_binds.append(mount)
        else:
            item = dict(mount)
            identity = (
                item["compose_service"] + "\0" + item["target"]
            ).encode()
            item["archive_id"] = hashlib.sha256(identity).hexdigest()[:16]
            item["archive_path"] = "binds/" + item["archive_id"]
            external_binds.append(item)

    services = {}
    for name, service in (compose.get("services") or {}).items():
        services[name] = {
            "image": service.get("image", ""),
            "platform": service.get("platform", ""),
            "network_mode": service.get("network_mode", ""),
            "privileged": bool(service.get("privileged", False)),
        }

    manifest = {
        "format": "portable-compose-backup/v1",
        "service_name": args.service_name,
        "compose_project": compose.get("name", args.service_name),
        "services": services,
        "named_volumes": sorted(
            named_volumes,
            key=lambda item: (item["compose_service"], item["target"]),
        ),
        "portable_bind_mounts": sorted(
            portable_binds,
            key=lambda item: (item["compose_service"], item["target"]),
        ),
        "external_bind_mounts": sorted(
            external_binds,
            key=lambda item: (item["compose_service"], item["target"]),
        ),
        "runtime_bind_mounts": sorted(
            runtime_binds,
            key=lambda item: (item["compose_service"], item["target"]),
        ),
    }
    output = Path(args.output)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    output.chmod(0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
