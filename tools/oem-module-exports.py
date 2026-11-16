#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Generate modpost input from the pinned stock kernel and two stock tunnel modules."""

import re
import struct
import subprocess
import sys
from pathlib import Path


def main():
    inputs = Path(sys.argv[1])
    image = (inputs / "kernel-decompressed.bin").read_bytes()
    start, end, base = 0x7442DC, 0x75070C, 0xC0008000
    exports = {}
    for offset in range(start, end, 8):
        _, pointer = struct.unpack_from("<II", image, offset)
        index = pointer - base
        if not end <= index < len(image):
            raise ValueError("Invalid OEM export name pointer")
        name = image[index:image.index(0, index)].decode("ascii")
        if name in exports or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name):
            raise ValueError("Invalid or duplicate OEM export name")
        exports[name] = "vmlinux"
    for name in ("udp_tunnel", "ip6_udp_tunnel"):
        symbols = subprocess.check_output(["nm", "--defined-only", inputs / f"{name}.ko"],
                                          text=True)
        for symbol in re.findall(r"\b__ksymtab_(\w+)$", symbols, re.MULTILINE):
            if symbol in exports:
                raise ValueError(f"Duplicate export {symbol}")
            exports[symbol] = f"oem-modules/{name}"
    # MODVERSIONS=n on the reference device. CRC and GPL class are placeholders.
    for symbol, module in sorted(exports.items()):
        print(f"0x00000000\t{symbol}\t{module}\tEXPORT_SYMBOL")


if __name__ == "__main__":
    main()
