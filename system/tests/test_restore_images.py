import copy
import importlib.util
from pathlib import Path
import unittest

HELPER = Path(__file__).resolve().parents[2] / 'roles/docker_restore/files/pin_restore_images.py'
spec = importlib.util.spec_from_file_location('pin_restore_images', HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
REF = 'postgres@sha256:' + 'a' * 64

class ImagePinningTests(unittest.TestCase):
    def test_restore_uses_recorded_image_and_preserves_mounts(self):
        compose = {'services': {'db': {'image': 'postgres:16', 'volumes': ['data:/var/lib/postgresql/data'],
                                      'environment': {'POSTGRES_PASSWORD': '${DB_PASSWORD}'}}}}
        manifest = {'services': {'db': {'restore_image': REF, 'repo_digests': [REF]}}}
        before = copy.deepcopy(compose)
        self.assertEqual(module.pin_images(compose, manifest), ['db'])
        self.assertEqual(compose['services']['db']['image'], REF)
        for key in ('volumes', 'environment'):
            self.assertEqual(compose['services']['db'][key], before['services']['db'][key])

    def test_legacy_and_local_builds_are_unchanged(self):
        compose = {'services': {'db': {'image': 'postgres:16'}, 'app': {'build': './app'}}}
        before = copy.deepcopy(compose)
        self.assertEqual(module.pin_images(compose, {'services': {'db': {}, 'app': {'restore_image': ''}}}), [])
        self.assertEqual(compose, before)

    def test_invalid_or_unrecorded_digest_is_rejected(self):
        for ref, recorded in [('postgres:latest', ['postgres:latest']), (REF, [])]:
            with self.assertRaises(ValueError):
                module.pin_images({'services': {'db': {}}},
                                  {'services': {'db': {'restore_image': ref, 'repo_digests': recorded}}})

    def test_unknown_service_is_rejected(self):
        with self.assertRaises(ValueError):
            module.pin_images({'services': {}},
                              {'services': {'db': {'restore_image': REF, 'repo_digests': [REF]}}})

if __name__ == '__main__':
    unittest.main()
