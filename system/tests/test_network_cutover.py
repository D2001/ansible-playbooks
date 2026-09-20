import importlib.machinery
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

tool = importlib.machinery.SourceFileLoader('network_cutover', str(Path(__file__).parents[1] / 'files/network-cutover.py')).load_module()


class CutoverTests(unittest.TestCase):
    def test_rollback_removes_cloned_mac_before_usb_reactivation(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'autoconnect.json').write_text(json.dumps({u: 'yes' for u in tool.OLD}))
            for suffix in ('v4', 'v6'):
                (folder / ('rollback.'+suffix)).write_text('*filter\nCOMMIT\n')
            with patch.object(tool, 'run') as run, patch.object(tool, 'PENDING', folder / 'pending'):
                tool.rollback(folder)
            calls = [call.args for call in run.call_args_list]
            stop = calls.index(('nmcli', '--wait', '15', 'con', 'down', tool.PROFILE))
            reset = calls.index(('ip', 'link', 'set', 'eth0', 'address', '2c:cf:67:d8:08:0a'))
            usb = calls.index(('nmcli', '--wait', '45', 'con', 'up', tool.OLD[0]))
            self.assertLess(stop, reset)
            self.assertLess(reset, usb)
            self.assertEqual(sum(c[0].endswith('-restore') for c in calls), 2)

    def test_wrong_dhcp_address_is_rejected(self):
        with patch.object(tool, 'run', return_value='[{"addr_info":[{"local":"192.168.0.200"}]}]'):
            with self.assertRaisesRegex(AssertionError, 'Expected DHCP address'):
                tool.verify()


if __name__ == '__main__':
    unittest.main()
