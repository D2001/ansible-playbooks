#!/usr/bin/env python3
from pathlib import Path
import unittest

import yaml


PLAYBOOK = Path(__file__).parents[1] / "host-audit.yml"


class HostAuditTests(unittest.TestCase):
    def test_audit_contains_only_read_only_modules(self):
        plays = yaml.safe_load(PLAYBOOK.read_text())
        self.assertEqual(len(plays), 1)
        play = plays[0]
        self.assertEqual(play["hosts"], "localhost")
        allowed = {
            "ansible.builtin.assert",
            "ansible.builtin.command",
            "ansible.builtin.debug",
            "ansible.builtin.stat",
        }
        metadata = {
            "name", "register", "changed_when", "failed_when", "loop",
            "loop_control", "no_log", "check_mode", "when", "vars",
        }
        for task in play["tasks"]:
            modules = set(task) - metadata
            self.assertEqual(len(modules), 1, task.get("name"))
            module = modules.pop()
            self.assertIn(module, allowed, task.get("name"))
            if module == "ansible.builtin.command":
                self.assertIs(task.get("changed_when"), False, task.get("name"))


if __name__ == "__main__":
    unittest.main()
