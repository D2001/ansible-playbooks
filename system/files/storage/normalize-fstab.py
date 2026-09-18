#!/usr/bin/env python3
"""Produce a normalized fstab without printing credentials. Does not mount anything."""
import argparse
from pathlib import Path

SHARES = {
    '/mnt/paperless': '//nas-labor.fritz.box/paperless',
    '/mnt/public': '//nas-labor.fritz.box/Public',
    '/mnt/backups': '//nas-labor.fritz.box/backups',
}
OPTIONS = ('credentials=/etc/smb_credentials,uid=1000,gid=1000,'
           'file_mode=0770,dir_mode=0770,iocharset=utf8,nounix,noserverino,rw,'
           '_netdev,nofail,x-systemd.automount,x-systemd.mount-timeout=30s')

def normalize(text):
    result = []
    usb_found = False
    for line in text.splitlines():
        if line in ('# BEGIN ANSIBLE MANAGED SMB SHARES', '# END ANSIBLE MANAGED SMB SHARES'):
            continue
        fields = line.split()
        if fields and not line.lstrip().startswith('#') and len(fields) >= 4:
            target = fields[1]
            if target in SHARES or target == '/mnt/smb/public':
                if fields[0] not in SHARES.values() or fields[2] != 'cifs':
                    raise ValueError('Refusing to replace unexpected mount at ' + target)
                continue
            if target == '/mnt/usb':
                if usb_found or fields[2] != 'ext4' or not fields[0].startswith('UUID='):
                    raise ValueError('Unexpected Docker storage mount')
                usb_found = True
                options = [o for o in fields[3].split(',')
                           if o != 'nofail' and not o.startswith('x-systemd.device-timeout=')]
                fields[3] = ','.join(options + ['nofail', 'x-systemd.device-timeout=15s'])
                line = ' '.join(fields)
        result.append(line)
    if not usb_found:
        raise ValueError('Configure the USB filesystem by UUID before hardening storage')
    result.append('# BEGIN ANSIBLE MANAGED SMB SHARES')
    result.extend(f'{src} {target} cifs {OPTIONS} 0 0' for target, src in SHARES.items())
    result.append('# END ANSIBLE MANAGED SMB SHARES')
    return '\n'.join(result) + '\n'

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination')
    args = parser.parse_args()
    result = normalize(Path(args.source).read_text())
    Path(args.destination).write_text(result)
    Path(args.destination).chmod(0o600)
    print('Prepared fstab: one USB mount and three NAS automounts; legacy entries removed')
