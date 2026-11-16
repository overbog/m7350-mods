# SPDX-License-Identifier: GPL-2.0-only
"""Host build of the OLED menu driven by fake key events and a fake framebuffer."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / 'package' / 'm7350-l2'


@unittest.skipUnless(shutil.which('cc'), 'needs a host C compiler')
class OledMenuHostTest(unittest.TestCase):
    def test_menu_flow(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            binary = tmp / 'menu'
            subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(PKG / 'src'),
                            '-o', str(binary), str(PKG / 'src' / 'm7350l2-menu.c'),
                            str(PKG / 'src' / 'wifi-qr.c'),
                            str(PKG / 'src' / 'qrcodegen' / 'qrcodegen.c')], check=True)
            result = subprocess.run(['python3', str(PKG / 'tools' / 'menu-host-test.py'),
                                     str(binary), str(tmp / 'screens')],
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        finally:
            shutil.rmtree(tmp)


if __name__ == '__main__':
    unittest.main()
