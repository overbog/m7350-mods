# SPDX-License-Identifier: GPL-2.0-only
"""Offline tests for package/m7350-l2 (mode switcher) with mock steps."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / 'package' / 'm7350-l2'

MOCK_STEP = '''#!/bin/sh
# Mock step: an "object" is a file in $WORLD.
name=$(basename "$0" .sh)
obj="$WORLD/$name"
case "$1" in
  start) [ -e "$WORLD/fail-start-$name" ] && exit 1; touch "$obj" ;;
  stop) [ -e "$WORLD/fail-stop-$name" ] && exit 1; rm -f "$obj" ;;
  check) [ -e "$obj" ] ;;
  absent) [ ! -e "$obj" ] ;;
esac
'''


class ModeSwitcherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / 'data'
        shutil.copytree(PKG, self.base)
        self.run_dir = self.tmp / 'run'
        self.world = self.tmp / 'world'
        self.world.mkdir()
        for mode in ('home', 'provider'):  # replace real steps with mocks
            for real in (self.base / (mode + '.d')).glob('*.sh'):
                real.unlink()
        for mode, steps in (('home', ('10-vpn', '20-vxlan')), ('provider', ('10-l2tp',))):
            for step in steps:
                path = self.base / (mode + '.d') / (step + '.sh')
                path.write_text(MOCK_STEP)
                path.chmod(0o755)
        self.env = dict(os.environ, M7350_L2_BASE=str(self.base),
                        M7350_L2_RUN=str(self.run_dir), M7350_L2_STABLE_SECS='0',
                        WORLD=str(self.world))
        commands = self.tmp / 'commands'
        commands.mkdir()
        sleep = commands / 'sleep'
        sleep.write_text('#!/bin/sh\nkill -TERM "$PPID"\n')
        sleep.chmod(0o755)
        self.interrupt_env = dict(self.env, PATH=str(commands) + os.pathsep + self.env['PATH'])

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def mode(self, *args, env=None):
        return subprocess.run(['sh', str(self.base / 'bin' / 'm7350-mode'), *args],
                              env=self.env if env is None else env,
                              capture_output=True, text=True, timeout=15)

    def reset_ram(self):
        shutil.rmtree(self.run_dir)
        for obj in self.world.iterdir():
            obj.unlink()

    def status(self):
        out = self.mode('status').stdout
        return dict(line.split('=', 1) for line in out.splitlines())

    def objects(self):
        return sorted(p.name for p in self.world.iterdir() if not p.name.startswith('fail-'))

    def test_switch_home_then_provider_then_factory(self):
        self.assertEqual(self.mode('set', 'home').returncode, 0)
        self.assertEqual(self.objects(), ['10-vpn', '20-vxlan'])
        self.assertEqual(self.status()['active'], 'home')
        self.assertEqual(self.mode('set', 'provider').returncode, 0)
        self.assertEqual(self.objects(), ['10-l2tp'])
        self.assertEqual(self.mode('set', 'factory').returncode, 0)
        self.assertEqual(self.objects(), [])
        self.assertEqual(self.status()['desired'], 'factory')

    def test_failed_start_rolls_back_to_factory(self):
        (self.world / 'fail-start-20-vxlan').touch()
        result = self.mode('set', 'home')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.objects(), [])
        status = self.status()
        self.assertEqual(status['active'], 'factory')
        self.assertIn('reverted to factory', status['last_error'])

    def test_failed_start_keeps_previous_desired_mode(self):
        self.mode('set', 'home')
        (self.world / 'fail-start-10-l2tp').touch()
        self.assertNotEqual(self.mode('set', 'provider').returncode, 0)
        status = self.status()
        self.assertEqual(status['active'], 'factory')
        self.assertEqual(status['desired'], 'home')

    def test_failed_stop_does_not_start_target(self):
        self.mode('set', 'home')
        (self.world / 'fail-stop-20-vxlan').touch()
        self.assertNotEqual(self.mode('set', 'provider').returncode, 0)
        self.assertNotIn('10-l2tp', self.objects())
        self.assertEqual(self.status()['active'], 'dirty')

    def test_oem_is_restored_on_boot_after_failed_vpn_teardown(self):
        self.assertEqual(self.mode('set', 'home').returncode, 0)
        (self.base / 'state' / 'boot_pending').write_text('home\n')
        (self.world / 'fail-stop-20-vxlan').touch()
        self.assertNotEqual(self.mode('set', 'factory').returncode, 0)
        self.assertEqual(self.status()['active'], 'dirty')
        self.assertEqual(self.status()['desired'], 'factory')
        shutil.rmtree(self.run_dir)
        for obj in self.world.iterdir():
            obj.unlink()
        self.assertEqual(self.mode('boot').returncode, 0)
        self.assertEqual(self.objects(), [])
        self.assertEqual(self.status()['active'], 'factory')
        self.assertFalse((self.base / 'state' / 'boot_pending').exists())

    def test_mode_without_steps_is_refused(self):
        for step in (self.base / 'provider.d').glob('*.sh'):
            step.unlink()
        result = self.mode('set', 'provider')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not packaged', result.stderr)
        self.assertEqual(self.status()['active'], 'factory')

    def test_invalid_mode_rejected(self):
        self.assertEqual(self.mode('set', 'rm -rf').returncode, 2)

    def test_lock_blocks_concurrent_switch(self):
        self.run_dir.mkdir(exist_ok=True)
        (self.run_dir / 'lock').mkdir()
        (self.run_dir / 'lock' / 'pid').write_text(str(os.getpid()))
        result = self.mode('set', 'home')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('busy', result.stderr)
        self.assertEqual(self.objects(), [])

    def test_stale_lock_is_reclaimed(self):
        self.run_dir.mkdir(exist_ok=True)
        (self.run_dir / 'lock').mkdir()
        (self.run_dir / 'lock' / 'pid').write_text('999999')
        self.assertEqual(self.mode('set', 'home').returncode, 0)

    def test_boot_restores_saved_mode(self):
        self.mode('set', 'home')
        self.mode('set', 'factory')
        (self.base / 'state' / 'mode').write_text('home\n')
        shutil.rmtree(self.run_dir)  # reboot clears RAM
        for obj in self.world.iterdir():
            obj.unlink()
        self.assertEqual(self.mode('boot').returncode, 0)
        self.assertEqual(self.objects(), ['10-vpn', '20-vxlan'])
        self.assertFalse((self.base / 'state' / 'boot_pending').exists())

    def test_single_early_reset_starts_home_again(self):
        state = self.base / 'state'
        state.mkdir()
        (state / 'mode').write_text('home\n')
        self.assertEqual(self.mode('boot', env=self.interrupt_env).returncode, -15)
        self.assertEqual((state / 'boot_pending').read_text(), '0\n')
        self.reset_ram()
        self.assertEqual(self.mode('boot', env=self.interrupt_env).returncode, -15)
        self.assertEqual(self.objects(), ['10-vpn', '20-vxlan'])
        self.assertEqual(self.status()['active'], 'home')
        self.assertEqual(self.status()['safe_hold'], 'off')
        self.assertEqual((state / 'boot_pending').read_text(), '1\n')
        # Re-running the hook on the same boot must not count another reset.
        self.assertEqual(self.mode('boot').returncode, 0)
        self.assertEqual((state / 'boot_pending').read_text(), '1\n')

    def test_stable_boot_clears_legacy_pending_marker(self):
        state = self.base / 'state'
        state.mkdir()
        (state / 'mode').write_text('home\n')
        (state / 'boot_pending').write_text('home\n')
        self.assertEqual(self.mode('boot').returncode, 0)
        self.assertEqual(self.status()['active'], 'home')
        self.assertFalse((state / 'boot_pending').exists())
        self.assertIn('boot: stable mark reached', (self.run_dir / 'log').read_text())

    def test_three_consecutive_early_resets_hold_factory(self):
        state = self.base / 'state'
        state.mkdir()
        (state / 'mode').write_text('home\n')
        for count in range(3):
            self.assertEqual(self.mode('boot', env=self.interrupt_env).returncode, -15)
            self.assertEqual((state / 'boot_pending').read_text(), f'{count}\n')
            self.reset_ram()
        self.assertNotEqual(self.mode('boot').returncode, 0)
        self.assertEqual(self.objects(), [])
        self.assertEqual(self.status()['safe_hold'], 'on')
        self.assertIn('repeated early resets (3); safe hold', self.status()['last_error'])
        self.reset_ram()
        self.mode('boot')
        self.assertEqual(self.objects(), [])
        self.assertEqual(self.mode('set', 'home').returncode, 0)
        self.assertEqual(self.status()['safe_hold'], 'off')

    def test_oem_boot_clears_an_early_reset_streak(self):
        state = self.base / 'state'
        state.mkdir()
        (state / 'mode').write_text('factory\n')
        (state / 'boot_pending').write_text('9\n')
        self.assertEqual(self.mode('boot').returncode, 0)
        self.assertEqual(self.status()['active'], 'factory')
        self.assertEqual(self.status()['safe_hold'], 'off')
        self.assertFalse((state / 'boot_pending').exists())
        self.assertEqual(self.objects(), [])

    def test_completed_start_failure_does_not_leave_reset_marker(self):
        state = self.base / 'state'
        state.mkdir()
        (state / 'mode').write_text('home\n')
        (self.world / 'fail-start-20-vxlan').touch()
        self.assertNotEqual(self.mode('boot').returncode, 0)
        self.assertEqual(self.status()['safe_hold'], 'off')
        self.assertFalse((state / 'boot_pending').exists())


if __name__ == '__main__':
    unittest.main()
