#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Install the reviewed SA6400/2803 reference profile, initially disabled.

Run on the target NAS after building and reviewing work/stage. Never resets or
unbinds a running GPU. Refuses existing installations instead of overwriting.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

FIRMWARE = (
    'booter_load_ga102.bin', 'gsp_ga10x.bin', 'gsp_boot_ga102.bin',
    'gsp_boot_desc_ga102.bin', 'v67-ga102-610.43.03.bin',
    'booter_load_ad102.bin', 'gsp_boot_ad102.bin', 'gsp_boot_desc_ad102.bin',
    'v67-ad102-610.43.03-four-plm.bin', 'NVIDIA-LICENSE',
)
TARGET = '0000:01:00.0'


def output(args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, type=Path)
    parser.add_argument('--sha-module', required=True, type=Path,
                        help='existing matching DSM libsha256.ko')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run on the NAS as root.')
    repo = Path(__file__).resolve().parents[1]
    root = Path('/usr/local/share/gpu-unlock-ada')
    libexec = Path('/usr/local/libexec/gpu-unlock-ada')
    conf = Path('/etc/gpu-unlock-ada')
    cli = Path('/usr/local/bin/gpu-unlock-ada')
    hook = Path('/etc/systemd/system/systemd-udev-trigger.service.d/20-gpu-unlock-ada.conf')
    firmware_link = Path('/lib/firmware/gpu-unlock/610.43.03')
    for dest in (root, libexec, conf, cli, hook, firmware_link):
        if dest.exists() or dest.is_symlink():
            parser.error('Refusing existing path: ' + str(dest))
    if 'synology_epyc7002_sa6400' not in Path('/etc.defaults/synoinfo.conf').read_text():
        parser.error('Only the reviewed SA6400 / epyc7002 profile is admitted.')
    if output(['/bin/uname', '-r']) != '5.10.55+':
        parser.error('Only the reviewed Linux 5.10.55+ release is admitted.')
    modinfo = shutil.which('modinfo')
    if not modinfo:
        parser.error('modinfo is required to check module vermagic.')
    dev = Path('/sys/bus/pci/devices') / TARGET
    identities = dict(vendor='0x10de', device='0x2803',
                      subsystem_vendor='0x10b0', subsystem_device='0x1903')
    for key, expected in identities.items():
        if (dev / key).read_text().strip() != expected:
            parser.error('PCI identity outside the tested profile: ' + key)
    if (dev / 'boot_vga').read_text().strip() != '0':
        parser.error('The target must not be the boot VGA device.')
    rows = output(['nvidia-smi', '--query-gpu=uuid,pci.bus_id', '--format=csv,noheader']).splitlines()
    if len(rows) != 1:
        parser.error('This integration requires exactly one NVIDIA GPU.')
    uuid, bdf = (x.strip() for x in rows[0].split(','))
    if bdf.lower() not in ('00000000:01:00.0', TARGET):
        parser.error('NVIDIA UUID does not refer to the reviewed PCI target.')
    sources = {'modules/libsha256.ko': args.sha_module.resolve()}
    for name in ('fbdev.ko', 'fb.ko', 'gpu_unlock.ko'):
        sources['modules/' + name] = args.stage / 'modules' / name
    for name in FIRMWARE:
        sources['firmware/' + name] = args.stage / 'firmware' / name
    for relative, source in sources.items():
        if not source.is_file() or source.is_symlink():
            parser.error('Missing/nonregular stage file: ' + str(source))
        if relative.startswith('modules/'):
            if output([modinfo, '-F', 'vermagic', str(source)]).split()[0] != '5.10.55+':
                parser.error('Module vermagic mismatch: ' + relative)
    # All preflight checks precede changes. The mode is disabled, and the
    # systemd hook is installed last. A partial install cannot arm a transaction.
    manifest = {name: hashlib.sha256(src.read_bytes()).hexdigest()
                for name, src in sources.items()}
    for folder in (root, libexec, conf):
        folder.mkdir(parents=True, mode=0o700)
        folder.chmod(0o700)
    for relative, source in sources.items():
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        dest.chmod(0o600)
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copyfile(repo / 'runtime/read_sm_rates.py', root / 'read_sm_rates.py')
    shutil.copyfile(repo / 'runtime/preload.py', libexec / 'preload.py')
    cli.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(repo / 'runtime/gpu-unlock-ada', cli)
    cli.chmod(0o700)
    config = dict(identities, target=TARGET, expected_uuid=uuid, mode='disabled',
                  kernel_release=output(['/bin/uname', '-r']),
                  kernel_version=output(['/bin/uname', '-v']))
    (conf / 'mode.json').write_text(json.dumps(config, indent=2) + '\n')
    (conf / 'mode.json').chmod(0o600)
    firmware_link.parent.mkdir(parents=True, exist_ok=True)
    firmware_link.symlink_to(root / 'firmware', target_is_directory=True)
    hook.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(repo / 'systemd/20-gpu-unlock-ada.conf', hook)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    print('Installed DISABLED. Review systemctl cat systemd-udev-trigger.service.')
    print('Then use gpu-unlock-ada arm-once for one future boot attempt.')


if __name__ == '__main__':
    main()
