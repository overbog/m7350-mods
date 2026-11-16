# SPDX-License-Identifier: GPL-2.0-only
"""Inject startup failures, then check mode, CGI and OLED output.

Set M7350_OEM_WWW to the extracted OEM web root to also run Chromium checks.
The browser test requires Node and Playwright. NODE and CHROMIUM can point to
local executables, and M7350_SCREENSHOTS enables captures in that directory.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

PKG = Path(__file__).resolve().parents[1] / 'package' / 'm7350-l2'

IP = r'''
case "$*" in
    'route get '*)
        case "$SCENARIO" in
            boot_recovery|no_lte)
                polls=$(cat "$M7350_L2_RUN/lte-polls" 2>/dev/null || echo 0)
                printf '%s\n' "$((polls + 1))" > "$M7350_L2_RUN/lte-polls"
                [ "$SCENARIO" = boot_recovery ] && [ "$polls" -ge 125 ] || exit 0 ;;
        esac
        echo 'dev rmnet_data0 src 192.0.2.2' ;;
    '-4 route show exact '*)
        [ "$SCENARIO" = pin ] || echo '198.51.100.1 dev rmnet_data0' ;;
    'route add '*) exit 1 ;;
    'xfrm policy add '*) [ "$SCENARIO" != guard ] ;;
    'xfrm state')
        if [ "$SCENARIO" != esp ]; then
            printf 'src 198.51.100.1 dst 192.0.2.2\n proto esp spi 1\nsrc 192.0.2.2 dst 198.51.100.1\n proto esp spi 2\n'
        fi ;;
    '-4 addr show dev ppp0')
        [ -e "$M7350_VPN_RUN/up" ] &&
            echo ' inet 10.0.0.2 peer 198.51.100.1/32 scope global ppp0' ;;
    'link show dev ppp0') [ -e "$M7350_VPN_RUN/up" ] ;;
    *) exit 0 ;;
esac
'''

SWANCTL = r'''
case "$1:$SCENARIO" in
    --stats:vici) exit 1 ;;
    --load-all:load) exit 1 ;;
    --initiate:proposal)
        echo 'parsed INFORMATIONAL_V1 request 123 [ N(NO_PROP) ]'; exit 1 ;;
    --initiate:auth)
        echo 'received AUTHENTICATION_FAILED error notify' >&2; exit 1 ;;
    --initiate:identity)
        echo 'received INVALID_ID_INFORMATION error notify' >&2; exit 1 ;;
    --initiate:selectors)
        echo 'received TS_UNACCEPTABLE error notify' >&2; exit 1 ;;
    --initiate:decrypt) echo 'HASH verification failed'; exit 1 ;;
    --initiate:silent_psk|--initiate:after_auth)
        echo 'parsed ID_PROT response 0 [ SA V V V V ]'
        echo 'parsed ID_PROT response 0 [ KE No NAT-D NAT-D ]'
        echo 'generating ID_PROT request 0 [ ID HASH ]'
        echo 'received retransmit of response with ID 0, but next request already sent'
        if [ "$SCENARIO" = after_auth ]; then
            echo 'parsed ID_PROT response 0 [ ID HASH ]'
            echo 'IKE_SA m7350-l2tp[1] established'
        fi
        echo 'initiate failed: CHILD_SA not established after 18000ms'; exit 1 ;;
    --terminate:quick_mode_ke|--terminate:quick_mode_recovery)
        echo terminated >> "$M7350_L2_RUN/ike-attempts"; exit 0 ;;
    --initiate:quick_mode_ke|--initiate:quick_mode_recovery)
        echo initiate >> "$M7350_L2_RUN/ike-attempts"
        if [ "$SCENARIO" = quick_mode_recovery ] && grep -Fxq terminated "$M7350_L2_RUN/ike-attempts"; then
            echo 'CHILD_SA l2tp established'; exit 0
        fi
        echo 'IKE_SA m7350-l2tp[1] established'
        echo 'unable to apply received KE value'
        echo 'initiate failed: establishing CHILD_SA l2tp failed'; exit 1 ;;
    --initiate:unreachable|--initiate:silent_proposal)
        echo 'giving up after retransmits'; exit 1 ;;
    --initiate:ike_unknown) echo 'initiate failed'; exit 1 ;;
    --initiate:*)
        echo '[CFG] selected proposal: IKE:AES_CBC_128/HMAC_SHA1_96/PRF_HMAC_SHA1/MODP_2048'
        echo '[IKE] IKE_SA m7350-l2tp[1] established' ;;
esac
'''

XL2TPD = r'''
echo 'xl2tpd started'
echo 'password = unregistered value'
echo 'unlabelled first credential sample-pass'
echo 'unlabelled second credential sample-shared'
[ "$SCENARIO" != fifo ] || exit 1
case "$SCENARIO" in
    ppp_auth) echo 'CHAP authentication failed' > "$M7350_VPN_RUN/pppd.log" ;;
    *) echo 'PPP link established' > "$M7350_VPN_RUN/pppd.log" ;;
esac
# The connect mock can write the log as soon as the FIFO appears.
mkfifo "$M7350_VPN_RUN/l2tp-control"
'''

class FailureReportingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which('cc')
        if not cls.compiler:
            return
        cls.build = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build.cleanup)
        driver = Path(cls.build.name) / 'oled.c'
        driver.write_text(r'''
#define main menu_main
#include "m7350l2-menu.c"
#undef main
int main(int argc, char **argv)
{
    unsigned short frame[FB_W * FB_H];
    unsigned short expected[FB_W * FB_H];
    char reason[200];
    if (argc != 2) return 2;
    status_value("last_error", reason, sizeof reason);
    if (strcmp(reason, argv[1])) return 3;
    fb = frame;
    draw_switch_failure(reason);
    fb = expected;
    clear();
    text(0, 0, "Switch failed:", WHITE);
    text(0, 114, "See web page", WHITE);
    for (size_t i = 0; argv[1][i] && i < 96; ++i) {
        char glyph[] = {argv[1][i], 0};
        text((int)(i % 16) * 8, 18 + (int)(i / 16) * 16, glyph, WHITE);
    }
    return memcmp(frame, expected, sizeof frame) != 0;
}
''')
        cls.oled = Path(cls.build.name) / 'oled'
        subprocess.run([cls.compiler, '-Wall', '-Wextra', '-Werror', '-I', str(PKG / 'src'),
                        str(driver), str(PKG / 'src/wifi-qr.c'),
                        str(PKG / 'src/qrcodegen/qrcodegen.c'), '-o', str(cls.oled)], check=True)

    def make_fixture(self, directory, scenario):
        base = Path(directory) / 'data'
        shutil.copytree(PKG, base)
        run = Path(directory) / 'run'
        vpn = Path(directory) / 'vpn'
        mock = Path(directory) / 'mock'
        mock.mkdir()
        lib = base / 'lib'
        bin_dir = lib / 'bin'
        bin_dir.mkdir(exist_ok=True)
        research = lib / 'research'
        research.mkdir(exist_ok=True)
        for hook in ('ppp-ip-up', 'ppp-ip-down'):
            (research / hook).touch()

        def executable(file, body):
            file.write_text('#!/bin/sh\n' + body + '\n')
            file.chmod(0o755)

        for step in (base / 'home.d').glob('*.sh'):
            if step.name != '20-tunnel1.sh':
                step.unlink()
        if scenario in ('step_start', 'step_check', 'step_silent'):
            executable(base / 'home.d/30-radio.sh', '''
                case "$1:$SCENARIO" in
                    start:step_start|check:step_check) echo '[30-radio] Wi-Fi device missing' >&2; exit 1 ;;
                    check:step_silent) exit 9 ;;
                esac''')
        executable(mock / 'ip', IP)
        executable(mock / 'ping', '''
            printf '%s\\n' "$*" >> "$M7350_L2_RUN/ping-calls"
            [ "$SCENARIO" = silent_proposal ] &&
                [ "$*" = '-q -I rmnet_data0 -c 1 -W 2 -w 3 198.51.100.1' ]''')
        executable(mock / 'pidof', 'exit 1')
        executable(mock / 'logger', r'''
            [ "$1" = -p ] && [ "$3" = -t ] && [ "$5" = -- ] || exit 1
            stamp=$(LC_ALL=C date -u '+%b %d %H:%M:%S')
            printf '%s host %s %s: %s\n' "$stamp" "$2" "$4" "$6" >> "$M7350_L2_RUN/syslog"
        ''')
        executable(mock / 'logread', r'cat "$M7350_L2_RUN/syslog"')
        executable(mock / 'sleep', '''
            case "$SCENARIO:$1" in
                boot_recovery:1|no_lte:1) [ -d "$M7350_VPN_RUN" ] || exit 0 ;;
            esac
            # Give the background FIFO writer time to run on a loaded host.
            case "$SCENARIO:$1" in
                fifo:*|vici:*) ;;
                *:1)
                    if [ -f "$M7350_VPN_RUN/xl2tpd.conf" ] && [ ! -p "$M7350_VPN_RUN/l2tp-control" ]; then
                        exec /bin/sleep 0.2
                    fi ;;
            esac
            exec /bin/sleep 0.03
        ''')
        executable(mock / 'timeout', r'''
            case "${8:-}:$5" in
                d:*|*'d m7350'*) rm -f "$M7350_VPN_RUN/up" ;;
                *) case "$SCENARIO" in
                    connect) exit 1 ;;
                    boot_recovery|boot_reject)
                        echo connect >> "$M7350_L2_RUN/ppp-attempts"
                        if [ "$SCENARIO" = boot_recovery ] && [ -f "$M7350_VPN_RUN/pppd-first.log" ]; then
                            touch "$M7350_VPN_RUN/up"
                        else
                            echo 'CHAP authentication failed' > "$M7350_VPN_RUN/pppd.log"
                        fi ;;

                    vtep|step_start|step_check|step_silent|quick_mode_recovery) touch "$M7350_VPN_RUN/up" ;;
                esac ;;
            esac''')
        executable(mock / 'auth', 'read token; [ "$token" = test-token ]')
        for name, body in [('charon', """
                           echo 'charon started'
                           echo '05[IKE] CHILD_SA l2tp{1} established' > "$M7350_VPN_RUN/charon.log"
                           """), ('swanctl', SWANCTL),
                           ('xl2tpd', XL2TPD), ('pppd', 'exit 0'),
                           ('pause_oem_offload', 'exit 0'), ('remove_owned_module', 'exit 0')]:
            executable(bin_dir / name, body)
        (lib / 'MANIFEST.sha256').write_text(''.join(
            f'{hashlib.sha256(p.read_bytes()).hexdigest()}  bin/{p.name}\n'
            for p in bin_dir.iterdir() if p.is_file()))
        if scenario == 'integrity':
            (bin_dir / 'swanctl').write_text('tampered')
        state = base / 'state'
        state.mkdir(exist_ok=True)
        (state / 'vpn-selected').write_text('test\n')
        (state / 'vpn-test.conf').write_text(
            f'server={"invalid" if scenario == "profile" else "198.51.100.1"}\n'
            'user=test\npassword=sample-pass\npsk=sample-shared\n'
            f'auth={"mschapv2" if scenario == "unsupported_auth" else "chap"}\n'
            f'l2={int(scenario == "vtep")}\nvni=7350\nport=4789\n'
            'ike=aes128-sha1-modp2048\nesp=aes128-sha1-modp1024\nusb_network=lte\n')
        env = dict(os.environ, PATH=f'{mock}:{os.environ["PATH"]}', SCENARIO=scenario,
                   M7350_L2_BASE=str(base), M7350_L2_RUN=str(run), M7350_VPN_RUN=str(vpn),
                   M7350_L2_AUTH=str(mock / 'auth'), M7350L2_MODE=str(base / 'bin/m7350-mode'))
        return base, run, vpn, env

    def post(self, base, env, action, token='test-token', **fields):
        body = urllib.parse.urlencode({'token': token, 'action': action, **fields}).encode()
        out = subprocess.check_output(['sh', str(base / 'www/cgi-bin/m7350l2')], input=body,
            env=dict(env, CONTENT_LENGTH=str(len(body)), REQUEST_METHOD='POST'))
        return json.loads(out.partition(b'\r\n\r\n')[2])

    @unittest.skipUnless(os.environ.get('M7350_OEM_WWW'), 'requires OEM web assets and Playwright')
    def test_failure_views_in_browser(self):
        oem = Path(os.environ['M7350_OEM_WWW']).resolve()
        with tempfile.TemporaryDirectory() as directory:
            overlay = Path(directory) / 'www'
            subprocess.run([sys.executable, PKG / 'tools/build-www.py', oem, PKG, overlay], check=True)
            base, _, _, env = self.make_fixture(directory, 'ppp_auth')
            result = subprocess.run([base / 'bin/m7350-mode', 'set', 'vpn'], env=env,
                                    capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)

            class FixtureServer(SimpleHTTPRequestHandler):
                def __init__(self, *args):
                    super().__init__(*args, directory=oem)

                def translate_path(self, path):
                    original = Path(super().translate_path(path))
                    patched = overlay / original.relative_to(oem)
                    return str(patched if patched.is_file() else original)

                def do_POST(self):
                    if self.path != '/cgi-bin/m7350l2':
                        self.send_error(404)
                        return
                    length = int(self.headers['Content-Length'])
                    response = subprocess.check_output(['sh', base / 'www/cgi-bin/m7350l2'],
                        input=self.rfile.read(length),
                        env=dict(env, CONTENT_LENGTH=str(length), REQUEST_METHOD='POST'))
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(response.partition(b'\r\n\r\n')[2])

                def log_message(self, *_):
                    pass

            with ThreadingHTTPServer(('127.0.0.1', 0), FixtureServer) as server:
                worker = Thread(target=server.serve_forever)
                worker.start()
                try:
                    command = [os.environ.get('NODE', 'node'),
                               Path(__file__).with_name('vpn_failure_browser.js'),
                               f'http://127.0.0.1:{server.server_port}']
                    if os.environ.get('M7350_SCREENSHOTS'):
                        command.append(os.environ['M7350_SCREENSHOTS'])
                    subprocess.run(command, check=True, timeout=45)
                finally:
                    server.shutdown()
                    worker.join()

    def test_profile_staging_reason_survives_reset_during_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            base, run, _, env = self.make_fixture(directory, 'staging')
            run.mkdir()
            (run / 'vpn-profile.conf').mkdir()  # cannot write the runtime profile
            (base / 'state/mode').write_text('vpn\n')
            env['M7350_L2_STABLE_SECS'] = '0'
            vpn_driver = base / 'modes/vpn.sh'
            original = vpn_driver.read_text()
            vpn_driver.write_text(original.replace('stop)\n', '''stop)
    # Interrupt the switch before it can report the result of cleanup.
    kill -TERM "$PPID"
    exit 1
''', 1))
            mode = base / 'bin/m7350-mode'
            result = subprocess.run([mode, 'boot'], env=env, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, -15, result.stderr)
            reason = 'Profile: could not prepare the runtime configuration for vpn'
            self.assertEqual(self.post(base, env, 'status')['last_error'], reason)
            self.assertEqual(self.post(base, env, 'last_failure')['reason'], reason)
            shutil.rmtree(run)
            env['M7350_L2_EARLY_RESET_MAX'] = '1'
            subprocess.run([mode, 'boot'], env=env, capture_output=True, timeout=10)
            status = self.post(base, env, 'status')
            self.assertEqual(status['safe_hold'], 'on')
            self.assertEqual(status['last_error'],
                             reason + '; repeated early resets (1); safe hold')
            if self.compiler:
                subprocess.run([self.oled, status['last_error']], env=env, check=True)

    def test_quick_mode_retry_is_bounded_and_uses_same_profile(self):
        for scenario in ('quick_mode_recovery', 'quick_mode_ke', 'unreachable'):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                base, run, vpn, env = self.make_fixture(directory, scenario)
                result = subprocess.run([base / 'bin/m7350-mode', 'set', 'vpn'],
                                        env=env, capture_output=True, timeout=10)
                attempts = run / 'ike-attempts'
                if scenario == 'unreachable':
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(attempts.exists())
                    continue
                self.assertEqual(attempts.read_text().splitlines()[:3],
                                 ['initiate', 'terminated', 'initiate'])
                self.assertEqual(attempts.read_text().count('initiate'), 2)
                if scenario == 'quick_mode_recovery':
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual((run / 'active').read_text().strip(), 'vpn')
                    self.assertIn('esp_proposals = aes128-sha1-modp1024',
                                  (vpn / 'etc/swanctl/swanctl.conf').read_text())
                    self.assertIn('unable to apply received KE value',
                                  (vpn / 'swanctl-phase2-first.log').read_text())
                    subprocess.run([base / 'bin/m7350-mode', 'set', 'factory'],
                                   env=env, capture_output=True, check=True, timeout=10)
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual((run / 'active').read_text().strip(), 'factory')
                    status = self.post(base, env, 'status')
                    self.assertIn('phase 2 Diffie-Hellman public value was rejected',
                                  status['last_error'])
                    failure = run / 'last-failure' / 'swanctl-phase2-first.log'
                    self.assertIn('unable to apply received KE value', failure.read_text())

    def test_boot_waits_for_lte_and_retries_ppp_only_once(self):
        for scenario, verb, attempts, success in (
            ('boot_recovery', 'boot', 2, True),
            ('boot_reject', 'boot', 2, False),
            ('boot_reject', 'set', 1, False),
        ):
            with self.subTest(scenario=scenario, verb=verb), tempfile.TemporaryDirectory() as directory:
                base, run, _, env = self.make_fixture(directory, scenario)
                (base / 'state/mode').write_text('vpn\n')
                args = [verb] if verb == 'boot' else ['set', 'vpn']
                result = subprocess.run([base / 'bin/m7350-mode', *args], env=env,
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode == 0, success, result.stderr)
                self.assertEqual((run / 'ppp-attempts').read_text().splitlines(),
                                 ['connect'] * attempts)
                if success:
                    self.assertIn('LTE source IPv4 ready after waiting 125s', (run / 'syslog').read_text())
                    self.assertEqual((run / 'active').read_text().strip(), 'vpn')
                else:
                    failure = self.post(base, env, 'last_failure')
                    self.assertIn('rejected PAP/CHAP authentication', failure['reason'])
                    self.assertEqual('after boot retry' in failure['reason'], verb == 'boot')
                    self.assertEqual('pppd-first.log' in failure['logs'], verb == 'boot')

    def test_missing_lte_ipv4_has_a_boot_deadline_and_manual_switch_checks_once(self):
        for verb, polls, reason in (
            ('boot', 181, 'LTE: no source IPv4 address after waiting 180s'),
            ('set', 1, 'LTE: no source IPv4 address'),
        ):
            with self.subTest(verb=verb), tempfile.TemporaryDirectory() as directory:
                base, run, vpn, env = self.make_fixture(directory, 'no_lte')
                (base / 'state/mode').write_text('vpn\n')
                args = [verb] if verb == 'boot' else ['set', 'vpn']
                result = subprocess.run([base / 'bin/m7350-mode', *args], env=env,
                                        capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(int((run / 'lte-polls').read_text()), polls)
                self.assertFalse(vpn.exists())
                status = self.post(base, env, 'status')
                self.assertEqual(status['active'], 'factory')
                self.assertEqual(status['last_error'], reason + '; reverted to factory')

    def test_failure_paths(self):
        cases = {
            'profile': 'Profile: select a complete VPN profile',
            'no_lte': 'LTE: no source IPv4 address',
            'integrity': 'Setup: swanctl is missing or failed integrity verification',
            'unsupported_auth': 'PPP: unsupported authentication method',
            'pin': 'LTE: could not pin endpoint route to LTE',
            'guard': 'IPsec: could not install cleartext L2TP block',
            'vici': 'IKE: charon exited before VICI became ready',
            'load': 'IKE: strongSwan could not load the profile over VICI',
            'proposal': 'IKE: VPN server rejected the proposal (NO_PROPOSAL_CHOSEN)',
            'auth': 'IKE: VPN server rejected authentication (AUTHENTICATION_FAILED)',
            'identity': 'IKE: VPN server rejected the identity (INVALID_ID_INFORMATION)',
            'selectors': 'IKE: VPN server rejected traffic selectors (TS_UNACCEPTABLE)',
            'decrypt': 'IKE: authentication verification failed',
            'silent_psk': 'IKE: server answered the key exchange but did not confirm authentication; check the pre-shared key',
            'after_auth': 'IKE: IKE negotiation timed out after the VPN server replied',
            'silent_proposal': 'IKE: server reachable but did not answer the IKE offer; check the IKE/ESP proposals and the PSK',
            'unreachable': 'IKE: no response from VPN server',
            'ike_unknown': 'IKE: swanctl could not establish',
            'esp': 'ESP: security associations were not installed',
            'fifo': 'L2TP: xl2tpd did not open its control FIFO',
            'connect': 'L2TP: could not send the connect request',
            'ppp_auth': 'PPP: VPN server rejected PAP/CHAP authentication',
            'ppp_ip': 'PPP: ppp0 did not get a usable IPv4 address',
            'vtep': 'L2: PPP peer must differ from the public L2TP server',
            'step_start': '30-radio: Wi-Fi device missing',
            'step_check': '30-radio: Wi-Fi device missing',
            'step_silent': '30-radio: readiness check failed after startup (exit 9)',
        }
        for scenario, expected in cases.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                base, run, vpn, env = self.make_fixture(directory, scenario)
                mode = base / 'bin/m7350-mode'
                result = subprocess.run([mode, 'set', 'vpn'], env=env, capture_output=True,
                                        text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                reason = (run / 'start-error').read_text().strip()
                self.assertTrue(reason.startswith(expected), reason)
                status = self.post(base, env, 'status')
                self.assertEqual(status['active'], 'factory', status)
                self.assertTrue(status['last_error'].startswith(reason), status)
                if self.compiler:
                    subprocess.run([self.oled, status['last_error']], env=env, check=True)
                failure = self.post(base, env, 'last_failure')
                self.assertEqual(failure['reason'], reason)
                self.assertFalse(vpn.exists(), result.stderr)
                self.assertEqual((run / 'ping-calls').exists(), scenario in ('silent_proposal', 'unreachable'))
                if scenario in ('silent_psk', 'proposal'):
                    errors = self.post(base, env, 'vpn_log', level='4')['entries']
                    expected_line = ('received retransmit of response' if scenario == 'silent_psk'
                                     else 'N(NO_PROP)')
                    self.assertTrue(any(expected_line in row['message'] for row in errors))
                if scenario == 'ppp_auth':
                    logs = failure['logs']
                    self.assertIn('charon started', logs['charon.out'])
                    self.assertIn('CHILD_SA l2tp{1} established', logs['charon.log'])
                    self.assertIn('selected proposal: IKE:', logs['swanctl-initiate.log'])
                    self.assertEqual(logs['xl2tpd.log'], 'xl2tpd started')
                    self.assertIn('CHAP authentication failed', logs['pppd.log'])
                    self.assertRegex(failure['time'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
                    self.assertEqual(
                        self.post(base, env, 'last_failure', summary='1'),
                        {'result': 0, 'reason': reason, 'time': failure['time']})
                    with (run / 'syslog').open('a') as log:
                        log.write('Nov 13 12:00:00 host daemon.err unrelated: ignored\n')
                    entries = self.post(base, env, 'vpn_log', level='0')['entries']
                    levels = {entry['message']: entry['level'] for entry in entries}
                    for name, extract in logs.items():
                        for line in extract.splitlines():
                            self.assertEqual(levels[f'{name}: {line}'], 4 if name == 'pppd.log' else 1)
                    self.assertNotIn('ignored', levels)
                    errors = self.post(base, env, 'vpn_log', level='4')['entries']
                    self.assertEqual([row['message'] for row in errors],
                                     ['pppd.log: CHAP authentication failed', status['last_error']])
                    for forbidden in ('sample-pass', 'sample-shared', 'unregistered value'):
                        self.assertNotIn(forbidden, (run / 'syslog').read_text())
                    self.assertEqual(self.post(base, env, 'last_failure', 'bad-token')['result'], -3)
                    self.assertEqual((run / 'last-failure').stat().st_mode & 0o777, 0o700)
                    subprocess.run([mode, 'set', 'factory'], env=env, check=True, capture_output=True)
                    self.assertEqual(self.post(base, env, 'status')['last_error'], '')
                    self.assertEqual(self.post(base, env, 'last_failure'), failure)
                for forbidden in ('sample-pass', 'sample-shared', 'unregistered value'):
                    self.assertNotIn(forbidden, json.dumps(failure) + result.stderr)
