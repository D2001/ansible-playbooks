import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'files/restore-check.py'
spec = importlib.util.spec_from_file_location('restore_check', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class RestoreCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'
        self.metrics = self.root / 'textfile/results.prom'

    def run_check(self, rc, plan=False):
        argv = ['restore-check.py', '--source', 'local', '--service', 'monitoring']
        if plan:
            argv.append('--plan')
        with patch.object(module, 'STATE_DIR', self.state), patch.object(module, 'METRICS', self.metrics), \
                patch('sys.argv', argv), patch.object(module.subprocess, 'run',
                return_value=types.SimpleNamespace(returncode=rc)) as run:
            result = module.main()
            return result, run.call_args

    def test_plan_has_no_writes_or_commands(self):
        result, call = self.run_check(0, plan=True)
        self.assertEqual(result, 0)
        self.assertIsNone(call)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.metrics.exists())

    def test_success_then_failure_preserves_previous_success(self):
        result, call = self.run_check(0)
        self.assertEqual(result, 0)
        self.assertIn('restore_mode=portable_test', call.args[0])
        self.assertNotIn('restore_mode=install', call.args[0])
        state = json.loads((self.state / 'status.json').read_text())
        success = state['monitoring|local|portable_test']['last_success']
        self.assertGreater(success, 0)
        result, call = self.run_check(2)
        self.assertEqual(result, 1)
        state = json.loads((self.state / 'status.json').read_text())
        self.assertEqual(state['monitoring|local|portable_test']['last_success'], success)
        self.assertEqual(state['monitoring|local|portable_test']['success'], 0)
        self.assertIn('mode="portable_test"} 0', self.metrics.read_text())
        self.assertEqual((self.state / 'status.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.metrics.stat().st_mode & 0o777, 0o644)

    def test_unexpected_metric_labels_rejected(self):
        with self.assertRaises(ValueError):
            module.metrics_text({'bad|local|portable_test': {}})

if __name__ == '__main__':
    unittest.main()
