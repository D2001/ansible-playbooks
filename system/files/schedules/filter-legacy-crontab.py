#!/usr/bin/env python3
"""Remove only schedules superseded by the host-baseline systemd timers."""

import argparse
import sys


BACKUP_RUNNER = "/home/karsten/ansible-playbooks/docker/run-ansible.sh backup.yml"
UPDATE_RUNNER = "/home/karsten/scripts/system-update.sh"


def is_managed_job(line, user):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    if user == "karsten":
        return BACKUP_RUNNER in stripped and any(
            f"service_name={service}" in stripped
            for service in ("homeassistant", "paperless", "monitoring")
        )
    if user == "root":
        if UPDATE_RUNNER in stripped:
            return True
        return (
            "/sbin/reboot" in stripped
            and "cron-reboot.log" in stripped
            and "date +\\%d" in stripped
        )
    raise ValueError("Unsupported crontab owner")


def filter_crontab(text, user):
    lines = text.splitlines()
    kept = [line for line in lines if not is_managed_job(line, user)]
    removed = len(lines) - len(kept)
    result = "\n".join(kept).rstrip() + "\n"
    return result, removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", choices=("karsten", "root"), required=True)
    args = parser.parse_args()
    result, removed = filter_crontab(sys.stdin.read(), args.user)
    sys.stdout.write(result)
    print(f"Removed {removed} legacy {args.user} schedule(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
