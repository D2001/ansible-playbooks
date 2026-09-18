#!/usr/bin/env python3
"""Pin only an extracted restore Compose file to recorded running image digests."""
import argparse
import json
import re
from pathlib import Path
import yaml

DIGEST = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}$')

def pin_images(compose, manifest):
    pinned = []
    services = compose.get('services', {})
    for name, recorded in manifest.get('services', {}).items():
        ref = recorded.get('restore_image', '')
        if not ref:
            continue  # Legacy manifests and locally built images retain sources.
        if name not in services or not isinstance(services[name], dict):
            raise ValueError('Manifest service is missing from Compose: ' + name)
        if not isinstance(ref, str) or not DIGEST.fullmatch(ref):
            raise ValueError('Invalid immutable image reference for ' + name)
        if ref not in recorded.get('repo_digests', []):
            raise ValueError('Image reference is not among the recorded digests')
        services[name]['image'] = ref
        pinned.append(name)
    return pinned

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('compose')
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    path = Path(args.compose)
    if path.is_symlink():
        raise SystemExit('Refusing symlink Compose file')
    compose = yaml.safe_load(path.read_text())
    pinned = pin_images(compose, manifest)
    if pinned:
        path.write_text(yaml.safe_dump(compose, sort_keys=False))
    print(json.dumps({'pinned_services': pinned}))
