#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Extract the two pinned RTL8192ES firmware blobs from a local ZX archive."""

import argparse
import hashlib
from pathlib import Path
import tarfile

ZX_ROOT = "linux-3.4-80e1fec813691ceb16567581c3fe4d49e4bab7f3"
DRIVER = f"{ZX_ROOT}/drivers/net/wireless/rtl8192cd_92es"
FIRMWARE_PATH = "WlanHAL/Data/8192E"
FIRMWARE = {
    "rtl8192Efw.bin": "6c2add036e87196d01f43fb2bd8cfa4b80664a7c4ede7fbc7b31405df072ab39",
    "rtl8192EfwMP.bin": "1fcaf39cb56df935611a2c6e388e1c9cc791d0d2b9cf5eb74811936464e214ed",
}


def read_firmware(source):
    manifest = Path(__file__).with_name("runtime-inputs.sha256").read_text()
    expected = next(line.split()[0] for line in manifest.splitlines()
                    if line.endswith("  zx-linux-3.4.tar.gz"))
    with source.open("rb") as compressed:
        if hashlib.file_digest(compressed, "sha256").hexdigest() != expected:
            raise ValueError("ZX archive SHA-256 mismatch")
        compressed.seek(0)
        blobs = {}
        with tarfile.open(fileobj=compressed, mode="r|gz") as archive:
            members = {f"{DRIVER}/{FIRMWARE_PATH}/{name}": name for name in FIRMWARE}
            for entry in archive:
                if entry.name not in members:
                    continue
                name = members[entry.name]
                if not entry.isfile() or name in blobs:
                    raise ValueError(f"{entry.name}: expected one regular archive member")
                data = archive.extractfile(entry).read()
                if hashlib.sha256(data).hexdigest() != FIRMWARE[name]:
                    raise ValueError(f"{name}: extracted firmware SHA-256 mismatch")
                blobs[name] = data
        missing = FIRMWARE.keys() - blobs.keys()
        if missing:
            raise ValueError(f"{DRIVER}/{FIRMWARE_PATH}: missing {', '.join(sorted(missing))}")
        return blobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Local pinned zx-linux-3.4.tar.gz")
    parser.add_argument("output", type=Path, help="New local directory for verified firmware")
    args = parser.parse_args()
    try:
        blobs = read_firmware(args.archive)
        args.output.mkdir()
        for name, data in blobs.items():
            (args.output / name).write_bytes(data)
            print(f"Verified {name} {FIRMWARE[name]}")
    except FileNotFoundError as error:
        parser.error(f"Required local file or directory is missing: {error.filename}. See docs/source-build.md.")
    except (OSError, ValueError, tarfile.TarError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
