# SPDX-License-Identifier: GPL-2.0-only
"""Offline contract tests for package/m7350-l2/home.d steps.

These do not exercise device behaviour (ip, iptables, iwpriv, insmod); they
check the verb contract, the manifest hash gate and shell syntax.
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / 'package' / 'm7350-l2'
STEPS = sorted((PKG / 'home.d').glob('[0-9][0-9]-*.sh'))


class HomeStepsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / 'data'
        shutil.copytree(PKG, self.base)
        self.env = dict(os.environ, M7350_L2_BASE=str(self.base),
                        M7350_L2_RUN=str(self.tmp / 'run'))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_expected_step_order(self):
        self.assertEqual([s.name for s in STEPS], [
            '10-ipsec-modules.sh', '20-tunnel1.sh', '25-routing.sh',
            '28-lte.sh', '30-zx-vap.sh', '40-vxlan.sh', '50-bridge2.sh', '60-supervise.sh'])

    def test_vxlan_endpoints_follow_ppp_and_reject_public_server(self):
        script = '''
            . "$M7350_L2_BASE/lib/home-common.sh"
            VPN_SERVER=198.51.100.10
            ip() { printf '    inet %s peer %s/32 scope global ppp0\n' "$LOCAL_IP" "$PEER_IP"; }
            ppp_vxlan_endpoints
        '''
        for local_ip, peer_ip in [('10.0.0.2', '10.0.0.1'), ('10.0.1.2', '10.0.1.1')]:
            result = subprocess.check_output(['sh', '-c', script], text=True,
                env=dict(self.env, LOCAL_IP=local_ip, PEER_IP=peer_ip))
            self.assertEqual(result.strip(), f'{local_ip} {peer_ip}')
        result = subprocess.run(['sh', '-c', script], capture_output=True,
            env=dict(self.env, LOCAL_IP='10.0.0.2', PEER_IP='198.51.100.10'))
        self.assertNotEqual(result.returncode, 0)

    def test_steps_parse(self):
        for step in STEPS:
            result = subprocess.run(['sh', '-n', str(step)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, step.name + result.stderr)

    def test_zx_retries_an_incomplete_sdio_probe_once(self):
        step = self.base / 'home.d/30-zx-vap.sh'
        # Exercise the readiness and retry path without touching the host radio.
        functions = step.read_text().split('\ncase "${1:-}" in\n', 1)[0]
        step.write_text(functions + r'''
loads=0; polls=0
load_zx() { loads=$((loads + 1)); echo load; }
rmmod() { echo unload; }
mod_loaded() { return 1; }
compact_zx_memory() { echo compact; }
sleep() { polls=$((polls + 1)); }
ip() {
    case "$4" in
        wlan0|wlan0-va1) return 0 ;;
        wlan0-va0)
            case "$PROBE:$loads:$polls" in
                delayed:1:2|retry:2:*) return 0 ;;
            esac ;;
    esac
    return 1
}
prepare_zx
''')
        cases = {'delayed': (0, ['load']),
                 'retry': (0, ['load', 'unload', 'compact', 'load']),
                 'missing': (1, ['load', 'unload', 'compact', 'load'])}
        for probe, (code, events) in cases.items():
            with self.subTest(probe=probe):
                result = subprocess.run(['sh', str(step)], env=dict(self.env, PROBE=probe),
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(result.stdout.splitlines(), events)
                if code:
                    self.assertIn('wlan0-va0 missing after retrying', result.stderr)

    def test_unknown_verb_exits_2(self):
        for step in STEPS:
            result = subprocess.run(['sh', str(self.base / 'home.d' / step.name), 'bogus'],
                                    env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, step.name + result.stderr)

    def verified(self, name):
        script = '. "$M7350_L2_BASE/lib/home-common.sh"; verified "%s"' % name
        return subprocess.run(['sh', '-c', script], env=self.env,
                              capture_output=True, text=True).returncode

    def test_manifest_gate(self):
        lib = self.base / 'lib'
        (lib / 'ko').mkdir(exist_ok=True)
        artifact = lib / 'ko' / 'x.ko'
        artifact.write_bytes(b'module')
        digest = hashlib.sha256(b'module').hexdigest()
        (lib / 'MANIFEST.sha256').write_text('%s  ko/x.ko\n' % digest)
        self.assertEqual(self.verified('ko/x.ko'), 0)
        artifact.write_bytes(b'tampered')
        self.assertNotEqual(self.verified('ko/x.ko'), 0)
        self.assertNotEqual(self.verified('ko/missing.ko'), 0)

    def test_no_secret_values_in_package(self):
        env = (PKG / 'etc' / 'home.env').read_text()
        for word in ('PSK', 'PASSWORD', 'SECRET'):
            self.assertNotIn(word + '=', env.upper())
        self.assertFalse((PKG / 'secrets').exists())


if __name__ == '__main__':
    unittest.main()
