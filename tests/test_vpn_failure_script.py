# SPDX-License-Identifier: GPL-2.0-only
"""Host test of tools/vpn-failure-test.sh against a fake m7350-mode."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'package' / 'm7350-l2' / 'tools' / 'vpn-failure-test.sh'

# Fake switcher: reads the selected profile and fails with a reason chosen by
# the test (REASON file), or the generic message when REASON is empty.
FAKE_MODE = r'''#!/bin/sh
ST=$M7350_L2_BASE/state
case "$1" in
status) echo "active=$(cat $ST/active)"; echo "last_error=$(cat $ST/last_error 2>/dev/null)";;
set)
    echo "set $2 slot=$(cat $ST/vpn-selected)" >> $ST/calls
    if [ "$2" = vpn ]; then
        cp "$ST/vpn-$(cat $ST/vpn-selected).conf" "$ST/seen.conf"
        [ -f $ST/succeed ] && { echo vpn > $ST/active; exit 0; }
        r=$(cat $ST/reason); echo "${r:-start of vpn failed; reverted to factory}" > $ST/last_error
        echo "error: $r psk=$(sed -n 's/^psk=//p' $ST/seen.conf)" >&2
        exit 1
    fi
    echo factory > $ST/active;;
esac
'''


class VpnFailureScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.st = self.tmp / 'state'
        self.st.mkdir()
        (self.tmp / 'run').mkdir()
        (self.st / 'active').write_text('factory\n')
        (self.st / 'vpn-selected').write_text('home\n')
        (self.st / 'vpn-home.conf').write_text(
            'server=192.0.2.1\nuser=u\npassword=realpass\npsk=realpsk\nauth=chap\nl2=0\nike=aes128-sha1-modp2048\n')
        (self.st / 'reason').write_text('')
        mode = self.tmp / 'm7350-mode'
        mode.write_text(FAKE_MODE)
        mode.chmod(0o755)
        bindir = self.tmp / 'bin'
        bindir.mkdir()
        for name, body in {'logger': 'exit 0', 'logread': 'exit 0', 'pidof': 'exit 1', 'ip': 'exit 1'}.items():
            p = bindir / name
            p.write_text('#!/bin/sh\n' + body + '\n')
            p.chmod(0o755)
        self.env = dict(os.environ, M7350_L2_BASE=str(self.tmp), M7350_L2_RUN=str(self.tmp / 'run'),
                        M7350_MODE=str(mode), M7350_FTEST_NO_LTE_CHECK='1',
                        PATH=f'{bindir}:{os.environ["PATH"]}')

    def tearDown(self):
        subprocess.run(['rm', '-rf', str(self.tmp)])

    def run_scenario(self, scenario, reason=''):
        (self.st / 'reason').write_text(reason)
        return subprocess.run(['sh', str(SCRIPT)], env=dict(self.env, SCENARIO=scenario),
                              capture_output=True, text=True, timeout=30)

    def assert_restored(self):
        self.assertEqual((self.st / 'vpn-selected').read_text(), 'home\n')
        self.assertFalse((self.st / 'vpn-ftest.conf').exists())
        self.assertEqual((self.st / 'active').read_text().strip(), 'factory')
        self.assertIn('realpsk', (self.st / 'vpn-home.conf').read_text())

    def test_specific_reason_passes_and_profile_restored(self):
        r = self.run_scenario('psk', 'IKE: server answered the key exchange but did not confirm authentication; check the pre-shared key')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('RESULT psk: PASS', r.stdout)
        seen = (self.st / 'seen.conf').read_text()
        self.assertNotIn('psk=realpsk', seen)        # the PSK really was changed
        self.assertIn('password=realpass', seen)     # nothing else was
        self.assertNotIn('realpsk', r.stdout)        # and no secret is printed
        self.assertNotIn(seen.split('psk=')[1].split()[0], r.stdout)
        self.assert_restored()

    def test_silent_proposal_passes_only_with_proposal_diagnostic(self):
        reason = 'IKE: server reachable but did not answer the IKE offer; check the IKE/ESP proposals and the PSK'
        r = self.run_scenario('proposal', reason)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('RESULT proposal: PASS', r.stdout)
        self.assertIn('ike=aes256-sha512-modp8192\n', (self.st / 'seen.conf').read_text())
        self.assert_restored()

    def test_initial_timeout_does_not_pass_as_psk_or_proposal(self):
        for scenario in ('psk', 'proposal'):
            with self.subTest(scenario=scenario):
                r = self.run_scenario(scenario, 'IKE: no response from VPN server; check reachability')
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn(f'RESULT {scenario}: FAIL', r.stdout)
                self.assert_restored()

    def test_generic_reason_fails(self):
        r = self.run_scenario('unreachable')
        self.assertEqual(r.returncode, 1)
        self.assertIn('FAIL last_error names a specific reason', r.stdout)
        self.assert_restored()

    def test_new_generic_reasons_fail(self):
        for reason in ('Startup: could not start vpn',
                       'IKE: swanctl could not establish the IKE/ESP security association'):
            r = self.run_scenario('unreachable', reason)
            self.assertEqual(r.returncode, 1, reason)
            self.assertIn('FAIL last_error names a specific reason', r.stdout)
            self.assert_restored()

    def test_unexpected_success_fails_and_returns_to_factory(self):
        (self.st / 'succeed').touch()
        r = self.run_scenario('proposal')
        self.assertEqual(r.returncode, 1)
        self.assertIn('FAIL switch reported failure', r.stdout)
        self.assertIn('set factory', (self.st / 'calls').read_text())
        self.assert_restored()

    def test_l2vtep_sets_l2_vni_port(self):
        r = self.run_scenario('l2vtep', 'L2 needs a negotiated PPP peer address distinct from the public L2TP server.')
        self.assertEqual(r.returncode, 0, r.stdout)
        seen = (self.st / 'seen.conf').read_text()
        for kv in ('l2=1', 'vni=7350', 'port=4789'):
            self.assertIn(kv + '\n', seen)
        self.assert_restored()

    def test_refuses_when_not_factory(self):
        (self.st / 'active').write_text('vpn\n')
        r = self.run_scenario('psk')
        self.assertEqual(r.returncode, 2)
        self.assertIn('ABORT', r.stdout)
        self.assertFalse((self.st / 'calls').exists())
        self.assertEqual((self.st / 'vpn-selected').read_text(), 'home\n')


if __name__ == '__main__':
    unittest.main()
