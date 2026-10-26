# SPDX-License-Identifier: GPL-2.0-only
"""Exercise installation against an isolated Linux filesystem, never /etc."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'posix', 'installation requires Linux filesystem semantics')
class InstallTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('installer', REPO / 'scripts/install.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.fake = lambda p: self.base / str(p).lstrip('/')
        self.m.__file__ = '/repo/scripts/install.py'
        for file in ('runtime/read_sm_rates.py', 'runtime/preload.py', 'runtime/gpu-unlock-ada',
                     'systemd/20-gpu-unlock-ada.conf'):
            dest = self.fake('/repo/' + file)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / file, dest)
        self.write('/etc.defaults/synoinfo.conf', 'unique="synology_epyc7002_sa6400"')
        self.dev = self.fake('/sys/bus/pci/devices/0000:01:00.0')
        for key, value in dict(vendor='0x10de', device='0x2803', subsystem_vendor='0x10b0',
                               subsystem_device='0x1903', boot_vga='0').items():
            self.write('/sys/bus/pci/devices/0000:01:00.0/' + key, value)
        for name in ('fbdev.ko', 'fb.ko', 'gpu_unlock.ko'):
            self.write('/stage/modules/' + name, 'test-module')
        for name in self.m.FIRMWARE:
            self.write('/stage/firmware/' + name, 'test-firmware')
        self.write('/lib/modules/libsha256.ko', 'test-dependency')
        self.vermagic = '5.10.55+ SMP mod_unload'
        self.commands = []
        self.addCleanup(patch.stopall)
        patch.object(self.m, 'Path', self.fake).start()
        patch.object(self.m.os, 'geteuid', lambda: 0).start()
        patch.object(self.m.shutil, 'which', lambda _: '/usr/sbin/modinfo').start()
        patch.object(self.m, 'output', self.output).start()
        patch.object(self.m.subprocess, 'run', lambda args, **kw: self.commands.append(args)).start()
        patch('sys.argv', ['install.py', '--stage', '/stage', '--sha-module', '/lib/modules/libsha256.ko']).start()

    def write(self, name, value):
        dest = self.fake(name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(value)

    def output(self, args):
        if args[0] == 'nvidia-smi':
            return 'GPU-test-only, 00000000:01:00.0'
        if args[0] == '/bin/uname':
            return '5.10.55+' if args[-1] == '-r' else 'test kernel build'
        return self.vermagic

    def test_install_defaults_disabled_without_gpu_commands(self):
        self.m.main()
        cfg = json.loads(self.fake('/etc/gpu-unlock-ada/mode.json').read_text())
        self.assertEqual(cfg['mode'], 'disabled')
        self.assertEqual(cfg['expected_uuid'], 'GPU-test-only')
        root = self.fake('/usr/local/share/gpu-unlock-ada')
        manifest = json.loads((root / 'manifest.json').read_text())
        self.assertEqual(len(manifest), len(self.m.FIRMWARE) + 4)
        self.assertEqual(self.fake('/lib/firmware/gpu-unlock/610.43.03').resolve(), root / 'firmware')
        self.assertEqual(self.commands, [['systemctl', 'daemon-reload']])
        self.assertEqual(self.fake('/etc/gpu-unlock-ada').stat().st_mode & 0o777, 0o700)

    def test_existing_install_not_overwritten(self):
        self.m.main()
        cfg = self.fake('/etc/gpu-unlock-ada/mode.json')
        before = cfg.read_bytes()
        with self.assertRaises(SystemExit):
            self.m.main()
        self.assertEqual(before, cfg.read_bytes())

    def test_wrong_device_rejected_before_writes(self):
        (self.dev / 'device').write_text('0x0000')
        with self.assertRaises(SystemExit):
            self.m.main()
        self.assertFalse(self.fake('/usr/local/share/gpu-unlock-ada').exists())
        self.assertEqual(self.commands, [])

    def test_boot_vga_rejected_before_writes(self):
        (self.dev / 'boot_vga').write_text('1')
        with self.assertRaises(SystemExit):
            self.m.main()
        self.assertFalse(self.fake('/etc/gpu-unlock-ada').exists())

    def test_wrong_vermagic_rejected_before_writes(self):
        self.vermagic = '4.4.0 incompatible'
        with self.assertRaises(SystemExit):
            self.m.main()
        self.assertFalse(self.fake('/etc/gpu-unlock-ada').exists())


if __name__ == '__main__':
    unittest.main()
