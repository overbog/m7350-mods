"""m7350-ssh against a fake iptables (raw + filter tables) and a fake dropbear."""
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / 'package' / 'm7350-l2'

FAKE_IPTABLES = r'''#!/usr/bin/env python3
import json, os, sys
db = os.environ['FAKE_FW']
args = sys.argv[1:]
if os.path.exists(db + '.fail') and open(db + '.fail').read().strip() in ' '.join(args):
    sys.exit(1)
st = json.load(open(db)) if os.path.exists(db) else {'raw:PREROUTING': [], 'filter:INPUT': []}
table = 'filter'
if args[:2] == ['-t', 'raw']:
    table, args = 'raw', args[2:]
op, chain, rest = args[0], args[1], args[2:]
key = table + ':' + chain
rules = st.setdefault(key, [])
if op in ('-I',) and rest and rest[0].isdigit():
    pos, rest = int(rest[0]), rest[1:]
rule = ' '.join(rest)
if op == '-C':
    sys.exit(0 if rule in rules else 1)
if op == '-I':
    rules.insert(pos - 1 if 'pos' in dir() else 0, rule)
elif op == '-D':
    if rule not in rules: sys.exit(1)
    rules.remove(rule)
elif op == '-S':
    print('-P %s DROP' % chain)
    for r in rules: print('-A %s %s' % (chain, r))
json.dump(st, open(db, 'w'))
'''

FAKE_DROPBEAR = r'''#!/bin/sh
prog=$1; shift
case "$prog" in
  dropbearkey)
    case "$1" in -y) echo "Fingerprint: SHA256:fake"; exit 0;; esac
    while [ $# -gt 0 ]; do [ "$1" = -f ] && echo key > "$2"; shift; done ;;
  dropbear)
    while [ $# -gt 0 ]; do [ "$1" = -P ] && pid=$2; shift; done
    sleep 300 </dev/null >/dev/null 2>&1 & echo $! > "$pid"; echo "dropbear started" >> "$FAKE_FW.dropbear" ;;
esac
'''

LTE = '-i rmnet+ -p tcp --dport 22 -j DROP'
ALLOW = '-p tcp --dport 22 -j ACCEPT'


class SshServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        base = self.tmp / 'base'
        shutil.copytree(PKG / 'bin', base / 'bin')
        (base / 'lib' / 'bin').mkdir(parents=True)
        db = base / 'lib' / 'bin' / 'dropbearmulti'
        db.write_text(FAKE_DROPBEAR); db.chmod(0o755)
        (base / 'ssh').mkdir()
        (base / 'ssh' / 'authorized_keys').write_text('ssh-ed25519 AAAA test\n')
        fakebin = self.tmp / 'fakebin'; fakebin.mkdir()
        ipt = fakebin / 'iptables'; ipt.write_text(FAKE_IPTABLES); ipt.chmod(0o755)
        self.fw = self.tmp / 'fw.json'
        self.env = dict(os.environ, PATH='%s:%s' % (fakebin, os.environ['PATH']),
                        FAKE_FW=str(self.fw), M7350_L2_BASE=str(base),
                        M7350_L2_RUN=str(self.tmp / 'run'), M7350_SSH_GUARD_SECS='1')
        self.ssh = str(base / 'bin' / 'm7350-ssh')

    def tearDown(self):
        subprocess.run([self.ssh, 'stop'], env=self.env, capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_ssh(self, cmd):
        return subprocess.run([self.ssh, cmd], env=self.env, capture_output=True, text=True, timeout=30)

    def state(self):
        import json
        return json.loads(self.fw.read_text())

    def wait(self, pred, secs=8):
        end = time.monotonic() + secs
        while time.monotonic() < end:
            if pred():
                return True
            time.sleep(0.1)
        return False

    def test_start_orders_rules_and_stop_removes_them(self):
        self.assertEqual(self.run_ssh('start').returncode, 0)
        st = self.state()
        self.assertEqual(st['raw:PREROUTING'], [LTE])
        self.assertEqual(st['filter:INPUT'][:2], [LTE, ALLOW])
        self.assertIn('guard: running', self.run_ssh('status').stdout)
        self.run_ssh('stop')
        st = self.state()
        self.assertEqual(st['raw:PREROUTING'], [])
        self.assertEqual(st['filter:INPUT'], [])

    def test_guard_restores_filter_after_oem_rebuild(self):
        self.run_ssh('start')
        import json
        st = self.state()
        st['filter:INPUT'] = ['-s 192.168.0.0/24 -i bridge0 ! -p icmp -j ACCEPT']  # OEM rebuild
        self.fw.write_text(json.dumps(st))
        self.assertTrue(self.wait(lambda: self.state()['filter:INPUT'][:2] == [LTE, ALLOW]))
        self.assertEqual(self.state()['raw:PREROUTING'], [LTE])
        self.assertIn('filter rules re-inserted', (self.tmp / 'run' / 'ssh.log').read_text())

    def test_guard_restores_raw_rule_too(self):
        self.run_ssh('start')
        import json
        st = self.state(); st['raw:PREROUTING'] = []
        self.fw.write_text(json.dumps(st))
        self.assertTrue(self.wait(lambda: self.state()['raw:PREROUTING'] == [LTE]))

    def test_fails_closed_without_raw_rule(self):
        (Path(str(self.fw) + '.fail')).write_text('PREROUTING')
        r = self.run_ssh('start')
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(Path(str(self.fw) + '.dropbear').exists(), 'dropbear must not start')
        self.assertEqual(self.state()['filter:INPUT'] if self.fw.exists() else [], [])

    def test_guard_stops_dropbear_when_rules_cannot_return(self):
        self.run_ssh('start')
        import json
        st = self.state(); st['raw:PREROUTING'] = []
        self.fw.write_text(json.dumps(st))
        Path(str(self.fw) + '.fail').write_text('PREROUTING')
        self.assertTrue(self.wait(lambda: 'dropbear: stopped' in self.run_ssh('status').stdout))
        self.assertIn('rule insert failed', (self.tmp / 'run' / 'ssh.log').read_text())

    def test_no_keys_no_start(self):
        (Path(self.env['M7350_L2_BASE']) / 'ssh' / 'authorized_keys').write_text('')
        self.assertNotEqual(self.run_ssh('start').returncode, 0)
        self.assertFalse(self.fw.exists())


if __name__ == '__main__':
    unittest.main()
