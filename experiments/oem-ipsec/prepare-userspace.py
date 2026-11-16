#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Relocate PPP configuration/hooks to RAM; run once on freshly extracted sources."""
import pathlib, sys
root = pathlib.Path(sys.argv[1])
p = root / 'ppp-ppp-2.4.9/pppd/pathnames.h'
s = p.read_text()
assert '#define _ROOT_PATH\n' in s
p.write_text(s.replace('#define _ROOT_PATH\n', '#define _ROOT_PATH "/run/m7350-vpn"\n'))
p = root / 'xl2tpd-1.3.18/l2tp.h'
s = p.read_text()
assert '"/usr/sbin/pppd"' in s
p.write_text(s.replace('"/usr/sbin/pppd"', '"/run/m7350-vpn/pppd"'))
