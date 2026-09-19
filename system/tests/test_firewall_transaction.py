import importlib.machinery
from pathlib import Path
import unittest

tool = importlib.machinery.SourceFileLoader('firewall_transaction', str(Path(__file__).parents[1] / 'files/firewall-transaction.py')).load_module()


class RollbackTests(unittest.TestCase):
    def test_restores_owned_chains_and_policies_without_dynamic_rules(self):
        saved = '''*filter
:INPUT DROP [1:2]
:FORWARD ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
:DOCKER-USER - [0:0]
:DOCKER - [0:0]
-A INPUT -j LIBVIRT_INP
-A INPUT -p tcp --dport 22 -j ACCEPT
-A DOCKER-USER -j RETURN
-A DOCKER -j ACCEPT
-A FORWARD -j DOCKER-USER
COMMIT
*nat
:INPUT ACCEPT [0:0]
-A INPUT -j ACCEPT
COMMIT
'''
        result = tool.saved_input(saved)
        self.assertIn(':INPUT DROP [1:2]', result)
        self.assertIn(':FORWARD ACCEPT [0:0]', result)
        self.assertIn('-A INPUT -j LIBVIRT_INP', result)
        self.assertNotIn('-A INPUT -j ACCEPT', result)
        self.assertNotIn('-A DOCKER -j ACCEPT', result)
        self.assertNotIn('-A FORWARD', result)
        self.assertNotIn('-F FORWARD', result)


if __name__ == '__main__':
    unittest.main()
