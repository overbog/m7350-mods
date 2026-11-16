# SPDX-License-Identifier: GPL-2.0-only
"""Offline tests for package/m7350-l2/www/cgi-bin/m7350l2 with a stub auth helper."""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / 'package' / 'm7350-l2'
CGI = PKG / 'www' / 'cgi-bin' / 'm7350l2'

AUTH_STUB = '#!/bin/sh\nread t\n[ "$t" = good ] && [ -n "$REMOTE_ADDR" ]\n'


class WebCgiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / 'data'
        shutil.copytree(PKG, self.base)
        for mode in ('home', 'provider'):
            for step in (self.base / (mode + '.d')).glob('*.sh'):
                step.unlink()
        auth = self.tmp / 'auth'
        auth.write_text(AUTH_STUB)
        auth.chmod(0o755)
        self.env = dict(os.environ, M7350_L2_BASE=str(self.base),
                        M7350_L2_RUN=str(self.tmp / 'run'), M7350_L2_AUTH=str(auth),
                        REMOTE_ADDR='192.168.0.100', REQUEST_METHOD='POST')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def post(self, fields, method='POST'):
        body = urllib.parse.urlencode(fields).encode()
        env = dict(self.env, CONTENT_LENGTH=str(len(body)), REQUEST_METHOD=method)
        out = subprocess.run(['sh', str(CGI)], input=body, env=env, capture_output=True).stdout
        header, _, payload = out.decode().partition('\r\n\r\n')
        self.assertIn('application/json', header)
        return json.loads(payload)

    def test_vpn_stats_off_connected_and_failed(self):
        run = Path(self.env['M7350_L2_RUN'])
        run.mkdir()
        request = {'token': 'good', 'action': 'vpn_stats'}
        self.assertEqual(self.post(request)['state'], 'off')
        self.assertEqual(self.post(dict(request, token='bad'))['result'], -3)

        state = self.base / 'state'
        state.mkdir(exist_ok=True)
        (state / 'last_error').write_text('IKE: proposal rejected; reverted to factory\n')
        snapshot = run / 'last-failure'
        snapshot.mkdir()
        (snapshot / 'reason').write_text('IKE: proposal rejected\n')
        failure = self.post(request)
        self.assertEqual((failure['state'], failure['reason']),
                         ('failed', 'IKE: proposal rejected'))

        mock_ip = self.tmp / 'ip'
        mock_ip.write_text('#!/bin/sh\necho "2: ppp0 inet 192.0.2.2 peer 192.0.2.1/32"\n')
        mock_ip.chmod(0o755)
        net, wlan, vpn = (self.tmp / name for name in ('net', 'wlan', 'vpn'))
        self.env.update(PATH=f'{self.tmp}:{os.environ["PATH"]}', M7350_STATS_NET=str(net),
                        M7350_STATS_WLAN=str(wlan), M7350_VPN_RUN=str(vpn))
        for iface in ('ppp0', 'vxlan0'):
            statistics = net / iface / 'statistics'
            statistics.mkdir(parents=True)
            (statistics / 'rx_bytes').write_text('123\n')
            (statistics / 'tx_bytes').write_text('456\n')
        (net / 'bridge2/brif/vxlan0').mkdir(parents=True)
        (wlan / 'wlan0-va0').mkdir(parents=True)
        (wlan / 'wlan0-va0/sta_info').write_text('hwaddr: private-mac\n')
        vpn.mkdir()
        (vpn / 'ppp-session').write_text('2026-11-11T10:00:00Z\n2\n')
        (run / 'active').write_text('vpn\n')
        (run / 'vpn-profile-slot').write_text('home\n')
        (run / 'vpn-profile.conf').write_text('server=198.51.100.1\nl2=1\npsk=private-key\n')
        result = self.post(request)
        self.assertEqual((result['state'], result['profile'], result['server']),
                         ('connected', 'home', '198.51.100.1'))
        self.assertEqual((result['local'], result['peer']), ('192.0.2.2', '192.0.2.1'))
        self.assertEqual((result['rx'], result['tx'], result['vxlan_rx'], result['vxlan_tx']),
                         (123, 456, 123, 456))
        self.assertEqual(result['clients'], {'lte': None, 'l3': None, 'l2': 1})
        self.assertEqual((result['l2'], result['since'], result['reconnects']),
                         (True, '2026-11-11T10:00:00Z', 2))
        self.assertNotIn('private-', json.dumps(result))

    PROFILE = dict(token='good', action='profile', server='vpn.example.net', user='astero@isp',
                   auth='chap', ipsec='0', public_mode='ipcp', public_prefix='', mtu='1400',
                   password='p&ss w=rd%', psk='')

    def test_get_rejected(self):
        self.assertEqual(self.post({'token': 'good', 'action': 'status'}, method='GET')['result'], -1)

    def test_login_exposes_only_active_operating_mode(self):
        def public_mode(query='mode'):
            response = subprocess.check_output(
                ['sh', str(CGI)], env=dict(self.env, REQUEST_METHOD='GET', QUERY_STRING=query))
            return json.loads(response.partition(b'\r\n\r\n')[2])

        self.assertEqual(public_mode(), {'mode': 'OEM'})
        run = Path(self.env['M7350_L2_RUN'])
        run.mkdir()
        (run / 'active').write_text('vpn\n')
        (run / 'vpn-profile-slot').write_text('private-profile\n')
        self.assertEqual(public_mode(), {'mode': 'VPN'})
        self.assertEqual(public_mode('switch-state'), {'mode': 'VPN', 'switching': False})
        (run / 'lock').mkdir()
        self.assertEqual(public_mode('switch-state'), {'mode': 'VPN', 'switching': True})
        (run / 'active').write_text('dirty\n')
        self.assertEqual(public_mode(), {'mode': 'Unavailable'})

    def test_bad_or_missing_token_rejected_without_changes(self):
        for token in ('', 'bad'):
            fields = dict(self.PROFILE, token=token)
            self.assertEqual(self.post(fields)['result'], -3)
        self.assertFalse((self.base / 'state' / 'provider.conf').exists())
        self.assertEqual(self.post({'token': 'good', 'action': 'status'})['result'], 0)

    def test_status_shape(self):
        r = self.post({'token': 'good', 'action': 'status'})
        self.assertEqual((r['active'], r['desired'], r['switching']), ('factory', 'factory', False))
        self.assertFalse(r['profile']['password_set'])

    def test_profile_saved_and_secret_never_returned(self):
        r = self.post(self.PROFILE)
        self.assertEqual(r['result'], 0)
        self.assertEqual(r['profile']['server'], 'vpn.example.net')
        self.assertTrue(r['profile']['password_set'])
        self.assertNotIn('p&ss', json.dumps(r))
        secret = self.base / 'secrets' / 'provider.password'
        self.assertEqual(secret.read_text(), 'p&ss w=rd%\n')
        self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.base / 'secrets').stat().st_mode), 0o700)
        # An empty password keeps the stored one.
        self.post(dict(self.PROFILE, password='', user='other'))
        self.assertEqual(secret.read_text(), 'p&ss w=rd%\n')

    def test_injection_and_invalid_values_rejected(self):
        bad = [dict(server='a;reboot'), dict(server='$(reboot)'), dict(user='u`id`'),
               dict(user='a b'), dict(password='quote"'), dict(password="it's"),
               dict(auth='none'), dict(ipsec='yes'), dict(mtu='99999'), dict(mtu='12a'),
               dict(public_mode='routed', public_prefix='10.0.0.0/33'),
               dict(public_mode='routed', public_prefix='1.2.3.4;x'),
               dict(ipsec='1', psk='')]
        for change in bad:
            r = self.post(dict(self.PROFILE, **change))
            self.assertEqual(r['result'], -1, change)
        self.assertFalse((self.base / 'state' / 'provider.conf').exists())

    def test_routed_prefix_accepted(self):
        r = self.post(dict(self.PROFILE, public_mode='routed', public_prefix='203.0.113.8/29'))
        self.assertEqual(r['profile']['public_prefix'], '203.0.113.8/29')

    def test_set_validates_mode(self):
        self.assertEqual(self.post({'token': 'good', 'action': 'set', 'mode': 'x;y'})['result'], -1)
        self.assertEqual(self.post({'token': 'good', 'action': 'set', 'mode': 'factory'})['result'], 0)

    def test_web_switch_to_home_and_back_with_simulated_driver(self):
        def install_step(mode):
            step = self.base / (mode + '.d') / '10-simulated.sh'
            step.write_text(
                f'#!/bin/sh\nmarker="$M7350_L2_RUN/{mode}-simulated"\n'
                'case "$1" in start) touch "$marker";; stop) rm -f "$marker";; '
                'check) test -e "$marker";; absent) test ! -e "$marker";; esac\n'
            )

        install_step('home')
        for mode in ('home', 'provider', 'factory'):
            self.assertTrue(self.post(dict(token='good', action='set', mode=mode))['started'])
            deadline = time.monotonic() + 4
            while True:
                status = self.post(dict(token='good', action='status'))
                if status['active'] == mode and not status['switching']:
                    break
                self.assertLess(time.monotonic(), deadline, status)
                time.sleep(0.05)
            self.assertEqual(status['desired'], mode)
            if mode == 'home':
                self.assertFalse(status['provider_available'])
                rejected = self.post(dict(token='good', action='set', mode='provider'))
                self.assertEqual(rejected['result'], -1)
                self.assertEqual(self.post(dict(token='good', action='status'))['active'], 'home')
                install_step('provider')
            if mode == 'provider':
                self.assertTrue(status['provider_available'])
            for driver in ('home', 'provider'):
                self.assertEqual((self.tmp / 'run' / (driver + '-simulated')).exists(),
                                 driver == mode)

    def test_home_credentials_and_networks(self):
        form = dict(token='good', action='home_profile', ssid='Lab Wi-Fi & VPN',
                    ssid_l3='Lab L3', ssid_lte='Lab LTE',
                    user='home-user', password='demo&pass%', psk='demo-psk',
                    wifi_password='demo wifi')
        default = self.post(dict(token='good', action='status'))['home']
        self.assertEqual([default[k] for k in ('ssid_lte', 'ssid_l3', 'ssid')],
                         ['M7350-LTE', 'M7350-L3', 'M7350-L2'])
        (self.base / 'state').mkdir(exist_ok=True)
        (self.base / 'state' / 'home.conf').write_text('Existing L2\n')
        legacy = self.post(dict(token='good', action='status'))['home']
        self.assertEqual(legacy, dict(default, ssid='Existing L2'))
        (self.base / 'state' / 'home.conf').write_text('Existing L2\nExisting L3\nExisting LTE\nl3\n')
        self.assertEqual(self.post(dict(form, ssid_lte=form['ssid']))['result'], -1)
        self.assertEqual(self.post(dict(form, wifi_password='short'))['result'], -1)
        self.assertFalse((self.base / 'secrets').exists())
        r = self.post(form)
        self.assertEqual(r['home'], dict(ssid='Lab Wi-Fi & VPN', ssid_l3='Lab L3', ssid_lte='Lab LTE',
                                        user='home-user',
                                        password_set=True, psk_set=True, wifi_set=True,
                                        wifi_lte_custom=False, wifi_l3_custom=False, wifi_l2_custom=True))
        for name, key in (('ppp.password', 'password'), ('ipsec.psk', 'psk'),
                          ('wifi.password', 'wifi_password')):
            secret = self.base / 'secrets' / name
            self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o600)
            self.assertEqual(secret.read_text(), form[key] + '\n')
            self.assertNotIn(form[key], json.dumps(r))
        self.assertEqual(self.post(dict(form, password='', psk='', wifi_password=''))['result'], 0)
        self.assertEqual((self.base / 'secrets' / 'wifi.password').read_text(), 'demo wifi\n')
        self.assertEqual((self.base / 'state/home.conf').read_text().splitlines()[3], 'l3')

    def test_vpn_profiles_selection_and_runtime_snapshot(self):
        req = dict(token='good', action='vpn_create', slot='provider', server='198.51.100.12',
                   dns='192.0.2.53', user='test-ppp', password='mock password', psk='mock-psk',
                   auth='pap', mtu='1400', l2='0', vni='7350',
                   port='4789', ike='aes128-sha1-modp2048', esp='aes128-sha1-modp1024')
        self.assertEqual(self.post(dict(req, l2='1', vni='0'))['result'], -1)
        self.assertEqual(self.post(dict(req, server='999.51.100.12'))['result'], -1)
        self.assertEqual(self.post(dict(req, ike='x{y}'))['result'], -1)
        self.assertEqual(self.post(dict(req, slot='../other'))['result'], -1)
        self.assertEqual(self.post(dict(req, usb_network='l2'))['result'], -1)
        self.assertEqual(self.post(dict(req, usb_network='bridge0'))['result'], -1)
        saved = self.post(req)
        self.assertEqual(saved['usb_network'], 'lte')
        self.assertEqual((saved['result'], saved['selected'], saved['auth']), (0, '', 'pap'))
        self.assertNotIn(req['password'], json.dumps(saved))
        self.assertNotIn(req['psk'], json.dumps(saved))
        state = self.base / 'state'
        profile = state / 'vpn-provider.conf'
        self.assertEqual(stat.S_IMODE(profile.stat().st_mode), 0o600)
        self.assertFalse((state / 'vpn-home.conf').exists())
        self.assertEqual(self.post(dict(token='good', action='vpn_select', slot='provider'))['selected'], 'provider')
        step = self.base / 'home.d' / '10-sim.sh'
        step.write_text('#!/bin/sh\n[ "$1" != start ] || grep -qx l2=0 "$M7350_L2_RUN/vpn-profile.conf"\n')
        mode = self.base / 'bin' / 'm7350-mode'
        cmd = lambda name: subprocess.run(['sh', str(mode), 'set', name], env=self.env,
                                          capture_output=True, text=True)
        (state / 'home-usb').write_text('l2\n')
        self.assertEqual(self.post(dict(token='good', action='vpn_get', slot='provider'))['usb_network'], 'lte')
        profile.write_text(profile.read_text().replace('usb_network=lte\n', ''))
        self.assertNotEqual(cmd('vpn').returncode, 0)
        self.assertEqual(self.post(dict(token='good', action='status'))['active'], 'factory')
        (state / 'home-usb').write_text('l3\n')
        self.assertEqual(cmd('vpn').returncode, 0)
        status = self.post(dict(token='good', action='status'))
        self.assertEqual((status['active'], status['active_profile']), ('vpn', 'provider'))
        snapshot = self.tmp / 'run' / 'vpn-profile.conf'
        before = snapshot.read_bytes()
        self.assertIn(b'usb_network=l3\n', before)
        self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o600)
        self.assertEqual(self.post(dict(req, action='vpn_save', mtu='1300', password='', psk='',
                                        usb_network='lte'))['result'], 0)
        self.assertEqual(snapshot.read_bytes(), before)
        self.assertIn('password=mock password\n', profile.read_text())
        self.assertEqual((state / 'mode').read_text().strip(), 'vpn')
        shutil.rmtree(snapshot.parent)
        self.assertEqual(subprocess.run(['sh', str(mode), 'boot'],
                         env=dict(self.env, M7350_L2_STABLE_SECS='0'),
                         capture_output=True).returncode, 0)
        restarted = self.post(dict(token='good', action='status'))
        self.assertEqual((restarted['active'], restarted['active_profile']), ('vpn', 'provider'))
        self.assertIn('usb_network=lte\n', snapshot.read_text())
        self.assertEqual(cmd('factory').returncode, 0)
        self.assertFalse(snapshot.exists())

    def test_last_error_is_json_escaped(self):
        state = self.base / 'state'
        state.mkdir(exist_ok=True)
        (state / 'last_error').write_text('bad "quote" \\ path\n')
        r = self.post({'token': 'good', 'action': 'status'})
        self.assertEqual(r['last_error'], 'bad "quote" \\ path')

    def test_independent_wifi_passwords(self):
        req = dict(token='good', action='wifi_profile', ssid='L2', ssid_l3='L3', ssid_lte='LTE',
                   custom_lte='1', custom_l3='0', custom_l2='1', key_lte='test-lte-key', key_l2='test-l2-key')
        result = self.post(req)
        self.assertEqual(result['result'], 0)
        self.assertNotIn(req['key_lte'], json.dumps(result))
        self.assertNotIn(req['key_l2'], json.dumps(result))
        path = self.base / 'secrets' / 'wifi-custom.conf'
        self.assertEqual(path.read_text(), 'test-lte-key\n\ntest-l2-key\n')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(self.post(dict(req, key_lte='', custom_l2='0'))['result'], 0)
        self.assertEqual(path.read_text(), 'test-lte-key\n\n\n')
        self.assertEqual(self.post(dict(req, key_l2=''))['result'], -1)

    def test_create_named_vpn_profile(self):
        req = dict(token='good', action='vpn_create', slot='office', server='198.51.100.12',
                   dns='', user='test-ppp', password='mock password', psk='mock-psk',
                   auth='pap', mtu='', l2='1', vni='7350',
                   port='4789', ike='aes128-sha1-modp2048', esp='aes128-sha1-modp1024')
        empty = self.post(dict(token='good', action='vpn_get'))
        self.assertEqual((empty['slot'], empty['selected'], empty['profiles'], empty['server']),
                         ('', '', [], ''))
        self.assertEqual(self.post(dict(token='good', action='set', mode='vpn'))['result'], -1)
        created = self.post(dict(req, usb_network='l2'))
        self.assertEqual((created['profiles'], created['dns'], created['l2']), (['office'], '', '1'))
        self.assertEqual(created['usb_network'], 'l2')
        self.assertNotIn('vtep', created)
        self.assertNotIn('vtep=', (self.base / 'state/vpn-office.conf').read_text())
        self.assertEqual(self.post(dict(req, slot='../../bad'))['result'], -1)
        self.assertEqual(self.post(dict(req, server='198.51.100.13'))['result'], -1)
        edit = dict(req, action='vpn_save')
        self.assertEqual(self.post(dict(edit, mtu='9001'))['result'], -1)
        self.assertEqual(self.post(dict(edit, mtu='9000'))['mtu'], '9000')
        self.assertEqual(self.post(edit)['mtu'], '')
        picked = self.post(dict(token='good', action='vpn_select', slot='office'))
        self.assertEqual((picked['selected'], picked['server']), ('office', '198.51.100.12'))

        delete = dict(token='good', action='vpn_delete', slot='office')
        saved = self.base / 'state/vpn-office.conf'
        for slot in ('', '../../bad', 'missing', 'home', 'provider'):
            self.assertEqual(self.post(dict(delete, slot=slot))['result'], -1, slot)
        self.assertEqual(self.post(dict(delete, token='bad'))['result'], -3)
        self.assertTrue(saved.exists())

        run = Path(self.env['M7350_L2_RUN'])
        (run / 'vpn-profile-slot').write_text('office\n')
        self.assertEqual(self.post(delete)['result'], -1)
        (run / 'vpn-profile-slot').unlink()
        (run / 'lock').mkdir()
        self.assertEqual(self.post(delete)['result'], -2)
        (run / 'lock').rmdir()
        rename = dict(delete, action='vpn_rename', new_slot='renamed-office')
        before = saved.read_bytes()
        self.assertEqual(self.post(dict(rename, new_slot='../bad'))['result'], -1)
        self.assertEqual(self.post(dict(rename, new_slot='office'))['result'], -1)
        (run / 'vpn-profile-slot').write_text('office\n')
        self.assertEqual(self.post(rename)['result'], -1)
        (run / 'vpn-profile-slot').unlink()
        (run / 'lock').mkdir()
        self.assertEqual(self.post(rename)['result'], -2)
        (run / 'lock').rmdir()
        renamed = self.post(rename)
        self.assertEqual((renamed['result'], renamed['slot'], renamed['selected'], renamed['profiles']),
                         (0, 'renamed-office', 'renamed-office', ['renamed-office']))
        self.assertFalse(saved.exists())
        saved = self.base / 'state/vpn-renamed-office.conf'
        self.assertEqual(saved.read_bytes(), before)
        self.assertEqual(stat.S_IMODE(saved.stat().st_mode), 0o600)
        delete['slot'] = 'renamed-office'
        deleted = self.post(delete)
        self.assertEqual((deleted['result'], deleted['slot'], deleted['profiles']),
                         (0, '', []))
        self.assertFalse(saved.exists())
        self.assertFalse((self.base / 'state/vpn-selected').exists())
        self.assertEqual(self.post(dict(delete, action='vpn_get'))['result'], -1)


if __name__ == '__main__':
    unittest.main()
