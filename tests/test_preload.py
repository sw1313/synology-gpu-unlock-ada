# SPDX-License-Identifier: GPL-2.0-only
"""Boot transaction tests against a fake filesystem; no GPU/root required."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

try:
    import fcntl
except ImportError:
    sys.modules['fcntl'] = types.SimpleNamespace(LOCK_EX=2, LOCK_UN=8, flock=lambda *a: None)

REPO = Path(__file__).resolve().parents[1]


class TestPath(type(Path())):
    # Windows forbids ':' in filenames; the production BDF remains unchanged.
    def __truediv__(self, key):
        if os.name == 'nt':
            key = str(key).replace(':', '_')
        return super().__truediv__(key)


class BootTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('preload', REPO / 'runtime/preload.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.path = lambda p: TestPath(self.base) / str(p).lstrip('/')
        self.m.ROOT = self.path('/usr/local/share/gpu-unlock-ada')
        self.m.CONF = self.path('/etc/gpu-unlock-ada/mode.json')
        self.m.RUN = self.path('/run/gpu-unlock-ada')
        self.m.log = io.StringIO()
        self.cfg = dict(mode='once', target='0000:01:00.0', kernel_release='5.10.55+',
                        kernel_version='reviewed build', vendor='0x10de', device='0x2803',
                        subsystem_vendor='0x10b0', subsystem_device='0x1903')
        self.dev = self.path('/sys/bus/pci/devices/0000:01:00.0')
        self.write('/proc/sys/kernel/random/boot_id', 'test-boot')
        for key in ('vendor', 'device', 'subsystem_vendor', 'subsystem_device'):
            self.write(str(self.dev.relative_to(self.base)) + '/' + key, self.cfg[key])
        self.write(str(self.dev.relative_to(self.base)) + '/driver_override', '(null)')
        self.write('/usr/local/share/gpu-unlock-ada/modules/gpu_unlock.ko', 'test-module')
        digest = hashlib.sha256(b'test-module').hexdigest()
        self.write('/usr/local/share/gpu-unlock-ada/manifest.json', json.dumps({'modules/gpu_unlock.ko': digest}))
        self.m.RUN.mkdir(parents=True)
        self.calls = []
        self.result = '0'
        self.flag = 'Y'
        self.loaded_target = self.cfg['target']
        self.fail_dependency = False
        self.bind_during_transaction = False
        self.addCleanup(patch.stopall)
        patch.object(self.m, 'Path', self.path).start()
        patch.object(self.m.fcntl, 'flock', lambda *a: None).start()
        patch.object(self.m, 'cmd', self.command).start()
        patch.object(self.m.subprocess, 'check_output',
                     lambda args, **kw: self.cfg['kernel_release' if args[-1] == '-r' else 'kernel_version']).start()
        patch('sys.stdout', io.StringIO()).start()

    def write(self, name, value):
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value)

    def command(self, args):
        self.calls.append(args)
        if self.fail_dependency:
            raise RuntimeError('dependency failed')
        if Path(args[1]).name == 'gpu_unlock.ko':
            prefix = '/sys/module/gpu_unlock/parameters/'
            for k, v in [('transaction_result', self.result), ('targets', self.loaded_target),
                         ('ad106_experimental', self.flag)]:
                self.write(prefix + k, v)
            if self.bind_during_transaction:
                (self.dev / 'driver').mkdir()

    def run_boot(self):
        self.m.CONF.parent.mkdir(parents=True, exist_ok=True)
        self.m.CONF.write_text(json.dumps(self.cfg))
        self.m.perform()
        state = self.m.RUN / 'state.json'
        return json.loads(state.read_text()) if state.exists() else {}

    def test_disabled_never_loads(self):
        self.cfg['mode'] = 'disabled'
        self.assertEqual(self.run_boot(), {})
        self.assertEqual(self.calls, [])

    def test_success_consumes_once_and_releases_hold(self):
        state = self.run_boot()
        self.assertEqual(state['status'], 'unlocked_verified')
        self.assertFalse(state['gpu_held'])
        self.assertEqual((self.dev / 'driver_override').read_text(), '\n')
        self.assertEqual(json.loads(self.m.CONF.read_text())['mode'], 'disabled')
        self.assertTrue((self.m.RUN / 'success').exists())
        self.assertEqual(len(self.calls), 4)
        self.m.perform()
        self.assertEqual(len(self.calls), 4)

    def test_persistent_stays_enabled(self):
        self.cfg['mode'] = 'persistent'
        self.assertEqual(self.run_boot()['status'], 'unlocked_verified')
        self.assertEqual(json.loads(self.m.CONF.read_text())['mode'], 'persistent')

    def test_kernel_change_skips_before_hold(self):
        self.m.subprocess.check_output = lambda *a, **kw: 'changed kernel'
        self.assertEqual(self.run_boot()['status'], 'precheck_failed_stock_boot')
        self.assertEqual(self.calls, [])

    def test_nonreviewed_target_rejected(self):
        self.cfg['target'] = 'all'
        self.assertEqual(self.run_boot()['status'], 'precheck_failed_stock_boot')
        self.assertEqual(self.calls, [])

    def test_pci_identity_change_rejected(self):
        (self.dev / 'device').write_text('0x0000')
        self.assertEqual(self.run_boot()['status'], 'precheck_failed_stock_boot')
        self.assertEqual(self.calls, [])

    def test_bound_driver_not_unbound(self):
        (self.dev / 'driver').mkdir()
        self.assertEqual(self.run_boot()['status'], 'too_late_stock_driver_already_bound')
        self.assertEqual(self.calls, [])

    def test_foreign_override_preserved(self):
        (self.dev / 'driver_override').write_text('vfio-pci')
        self.assertEqual(self.run_boot()['status'], 'precheck_failed_stock_boot')
        self.assertEqual((self.dev / 'driver_override').read_text(), 'vfio-pci')
        self.assertEqual(self.calls, [])

    def test_checksum_failure_does_not_load(self):
        (self.m.ROOT / 'modules/gpu_unlock.ko').write_text('changed')
        self.assertEqual(self.run_boot()['status'], 'precheck_failed_stock_boot')
        self.assertEqual(self.calls, [])

    def test_dependency_failure_has_no_hold(self):
        self.fail_dependency = True
        self.assertFalse(self.run_boot()['gpu_held'])
        self.assertEqual((self.dev / 'driver_override').read_text(), '(null)')

    def test_loaded_module_not_reused(self):
        self.path('/sys/module/gpu_unlock').mkdir(parents=True)
        self.assertEqual(self.run_boot()['status'], 'precheck_failed_stock_boot')
        self.assertFalse((self.m.RUN / 'success').exists())

    def assert_blocked(self):
        state = self.run_boot()
        self.assertEqual(state['status'], 'blocked_after_transaction')
        self.assertTrue(state['gpu_held'])
        self.assertEqual((self.dev / 'driver_override').read_text(), self.m.HOLD + '\n')
        self.assertFalse((self.m.RUN / 'success').exists())
        self.assertEqual(json.loads(self.m.CONF.read_text())['mode'], 'disabled')

    def test_insmod_success_is_not_transaction_success(self):
        self.result = '-115'
        self.assert_blocked()

    def test_wrong_optin_retains_hold(self):
        self.flag = 'N'
        self.assert_blocked()

    def test_wrong_loaded_target_retains_hold(self):
        self.loaded_target = 'all'
        self.assert_blocked()

    def test_unexpected_bind_retains_hold(self):
        self.bind_during_transaction = True
        self.assert_blocked()


if __name__ == '__main__':
    unittest.main()
