#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "files/schedules/filter-legacy-crontab.py"
SPEC = importlib.util.spec_from_file_location("filter_legacy_crontab", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ScheduleMigrationTests(unittest.TestCase):
    def test_user_backups_removed_and_unrelated_jobs_preserved(self):
        source = """# existing schedule
00 1 * * * /home/karsten/ansible-playbooks/docker/run-ansible.sh backup.yml -e "service_name=homeassistant"
20 1 * * * /home/karsten/ansible-playbooks/docker/run-ansible.sh backup.yml -e "service_name=paperless"
0 2 * * * /home/karsten/ansible-playbooks/docker/run-ansible.sh backup.yml -e "service_name=monitoring"
5 3 * * * /home/karsten/bin/unrelated
"""
        result, removed = MODULE.filter_crontab(source, "karsten")
        self.assertEqual(removed, 3)
        self.assertIn("unrelated", result)
        self.assertIn("# existing schedule", result)

    def test_root_update_and_specific_reboot_removed(self):
        source = """0 0 * * * /home/karsten/scripts/system-update.sh >> /var/log/system-update.log 2>&1
0 4 * * 1 [ "$(date +\\%d)" -le 7 ] && echo ok >> /var/log/cron-reboot.log && /sbin/reboot
15 4 * * * /sbin/reboot
"""
        result, removed = MODULE.filter_crontab(source, "root")
        self.assertEqual(removed, 2)
        self.assertIn("15 4 * * * /sbin/reboot", result)

    def test_filter_is_idempotent(self):
        source = "5 3 * * * /home/karsten/bin/unrelated\n"
        once, removed = MODULE.filter_crontab(source, "karsten")
        twice, removed_again = MODULE.filter_crontab(once, "karsten")
        self.assertEqual(removed, 0)
        self.assertEqual(removed_again, 0)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
