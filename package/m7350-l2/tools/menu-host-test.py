#!/usr/bin/env python3
"""Host test for m7350l2-menu: fake key_detect, fake framebuffer, stub switcher.

Waits on observable state (framebuffer changes, call logs) instead of fixed
sleeps, so it is stable under load. Saves each screen as PNG (3x).
usage: menu-host-test.py <menu-binary> <out-dir>
"""
import hashlib
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

binary, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp(prefix='m7m', dir='/tmp'))  # short path: key_detect allows 31 chars
fbfile, keysock, mysock = tmp / 'fb', str(tmp / 'kd.sock'), str(tmp / 'menu.sock')
fbfile.write_bytes(bytes(256 * 128))
state = tmp / 'active'
state.write_text('factory')
calls, oledd = tmp / 'calls', tmp / 'oledd'
mode = tmp / 'mode'
mode.write_text('#!/bin/sh\n'
                'if [ "$1" = status ]; then echo "active=$(cat %s)"; '
                'echo "last_error=start of vpn failed; reverted"; exit 0; fi\n'
                'echo "$@" >> %s\nsleep 1\n[ "$2" = vpn ] && exit 1\necho "$2" > %s\n'
                % (state, calls, state))
mode.chmod(0o755)
# oledd is modelled by a pid list: stop empties it, start fills it.
pids, held = tmp / 'oledd.pids', tmp / 'held'
start_failure = tmp / 'oledd-start-failure'
pids.write_text('4242\n')
kd = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
kd.bind(keysock)
kd.settimeout(10)
env = dict(os.environ, M7350L2_FB=str(fbfile), M7350L2_KEYSOCK=keysock, M7350L2_SOCK=mysock,
           M7350L2_MODE=str(mode), M7350L2_OLEDD_STOP='echo stop >> %s; : > %s' % (oledd, pids),
           M7350L2_OLEDD_START='echo start >> %s; test -e %s || echo 4242 > %s'
           % (oledd, start_failure, pids),
           M7350L2_OLEDD_HOLD='echo hold >> %s; touch %s' % (oledd, held),
           M7350L2_OLEDD_HELD='test -e %s' % held,
           M7350L2_OLEDD_RELEASE='echo release >> %s; rm -f %s' % (oledd, held),
           M7350L2_OLEDD_PIDS_CMD='cat %s' % pids,
           M7350L2_PANEL_ON='true', M7350L2_LOG=str(tmp / 'menu.log'))


fixtures = tmp / 'wifi'
fixtures.mkdir()
env['M7350L2_WIFI_FIXTURES'] = str(fixtures)
for iface, ssid, key in [('wlan0', b'Test OEM', b'test-oem-key'),
                         ('wlan0-va1', b'Test LTE', b'test-lte-key')]:
    for name, data in {'opmode': struct.pack('=i', 0x10),
                       'psk_enable': struct.pack('=i', 3),
                       'encmode': bytes([2]),
                       'hiddenAP': struct.pack('=i', 0),
                       'ssid': ssid,
                       'passphrase': key}.items():
        (fixtures / (iface + '.' + name)).write_bytes(data)


def digest():
    return hashlib.sha256(fbfile.read_bytes()).hexdigest()


def blank():
    return not any(fbfile.read_bytes())


def wait_for(pred, what, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            time.sleep(0.05)  # let a redraw finish
            return
        time.sleep(0.02)
    raise AssertionError('timed out waiting for ' + what)


SESSION = ['hold', 'stop', 'release', 'start']


def held_and_stopped():
    return held.exists() and pids.read_text().strip() == ''


def lines(path):
    return path.read_text().split() if path.exists() else []


def press(kind, change=True, button='wps'):
    before = digest()
    kd.sendto(('key_detect: %s %s press' % (button, kind)).encode(), mysock)
    if change:
        wait_for(lambda: digest() != before, 'screen change after %s press' % kind)


def png(name):
    raw = fbfile.read_bytes()
    rows = []
    for y in range(128):
        row = bytearray([0])
        for x in range(128):
            v = struct.unpack_from('<H', raw, y * 256 + x * 2)[0]
            row += bytes([((v >> 11) & 31) * 8, ((v >> 5) & 63) * 4, (v & 31) * 8]) * 3
        rows += [bytes(row)] * 3

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
    (out / (name + '.png')).write_bytes(
        b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 384, 384, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))


proc = subprocess.Popen([str(binary)], env=env)
try:
    reg = kd.recv(64)
    assert len(reg) == 40 and reg[0] == 0x2a and reg[1] == 0, reg
    assert reg[2:2 + len(mysock)].decode() == mysock

    # Idle: a short press must not take the screen.
    press('short', change=False)
    press('short', change=False, button='power')
    time.sleep(0.5)
    assert not oledd.exists() and blank(), 'short press while idle must do nothing'

    # Session 1: OEM -> VPN, the stub fails.
    press('long')
    # key_detect may report the same hold twice: the duplicate must be ignored.
    kd.sendto(b'key_detect: wps long press', mysock)
    time.sleep(0.5)
    png('1-menu-open')
    assert lines(oledd) == ['hold', 'stop'], 'a duplicate long press closed the menu'
    assert held_and_stopped(), 'oledd must be stopped and its start script held'
    press('short'); png('2-next')
    press('long', change=False)
    time.sleep(0.2)
    assert not lines(calls), 'MENU hold must not confirm the selected mode'
    press('short', button='power'); png('3-switching')
    wait_for(lambda: lines(calls) == ['set', 'vpn'], 'switch call')
    before = digest()
    wait_for(lambda: digest() != before, 'result screen'); png('4-result')
    wait_for(lambda: lines(oledd) == SESSION, 'oledd back after session 1')
    assert blank() and not held.exists()

    # Session 2: VPN -> OEM, succeeds.
    state.write_text('vpn')
    press('long'); time.sleep(0.4)
    for _ in range(3):
        press('short')
    png('4b-select-factory')
    press('short', button='power')
    wait_for(lambda: state.read_text().strip() == 'factory', 'factory switch')
    before = digest()
    wait_for(lambda: digest() != before, 'active screen'); png('4c-active')
    wait_for(lambda: lines(oledd) == SESSION * 2, 'oledd restart after session 2')

    # Session 3: Exit leaves without switching (cursor starts on factory).
    press('long'); time.sleep(0.4)
    for _ in range(3):
        press('short')
    png('5a-on-exit')
    press('short', button='power')
    wait_for(lambda: lines(oledd) == SESSION * 3 and blank(), 'exit')
    png('5-exit')

    # Session 4: 15 s without keys leaves without switching.
    press('long')
    wait_for(lambda: lines(oledd) == SESSION * 4 and blank(), 'idle timeout', timeout=20)
    png('6-idle-timeout')

    # Session 5: an oledd appears anyway while the menu is open. The menu
    # must abort without acting, release the hold and not start a second one.
    press('long'); time.sleep(0.4)
    press('short')
    pids.write_text('5151\n')
    wait_for(lambda: 'aborted without action' in (tmp / 'menu.log').read_text(), 'abort', timeout=5)
    wait_for(lambda: lines(oledd) == SESSION * 4 + ['hold', 'stop', 'release'], 'release after abort')
    time.sleep(0.3)
    assert lines(oledd) == SESSION * 4 + ['hold', 'stop', 'release'], 'abort must not start a second oledd'
    assert not held.exists()

    # Session 6: an OEM QR is shown on explicit confirmation and expires.
    pids.write_text('4242\n')
    press('long')
    press('short')
    press('short')
    press('short', button='power')
    start = time.monotonic()
    # Inverted code for the OLED: the finder pattern's corner is lit, the
    # screen corner stays dark. Version 3 at scale 3 starts at (20, 20).
    wait_for(lambda: fbfile.read_bytes()[20 * 256 + 40:20 * 256 + 42] == b'\xff\xff', 'QR drawn')
    raw = fbfile.read_bytes()
    assert raw[:2] == b'\x00\x00', 'QR screen must have a dark background'
    assert any(raw[i] for i in range(0, 256 * 14)), 'QR needs a hint line on top'
    assert any(raw[i] for i in range(256 * 114, 256 * 128)), 'QR needs the SSID line'
    png('7-oem-qr')
    wait_for(blank, 'QR timeout', timeout=32)
    assert 28 <= time.monotonic() - start <= 32, 'QR did not expire after 30 s'

    # Session 7: LTE and L3 are available in VPN, while the absent L2 is skipped.
    state.write_text('vpn')
    press('long')
    press('short')
    press('short', button='power')
    time.sleep(0.3)
    lte = digest()
    png('8-lte-qr')
    press('short')
    wait_for(lambda: digest() != lte and not blank(), 'MENU shows the next QR')
    png('8b-l3-qr')
    start_failure.touch()
    press('short', button='power')
    wait_for(lambda: 'oledd unavailable; drew VPN status' in (tmp / 'menu.log').read_text(),
             'VPN status after OEM display startup fails')
    assert not blank() and not held.exists() and not lines(pids)
    png('9-vpn-status')

    assert lines(calls) == ['set', 'vpn', 'set', 'factory'], lines(calls)
    print('host test passed; screens in', out)
finally:
    proc.terminate()
    proc.wait(timeout=5)
    kd.close()
    shutil.rmtree(tmp, ignore_errors=True)
