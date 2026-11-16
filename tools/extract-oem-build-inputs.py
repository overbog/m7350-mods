#!/usr/bin/env python3
"""Extract only the offline build inputs from the pinned 181220 inner OEM ZIP."""

import argparse
import hashlib
from pathlib import Path
import re
import struct
import zipfile
import zlib

ZIP_SHA256 = "b146038929edbf0addefb6c3e47f4c1f135db9e86099f23a2fa3488a4b31511e"
KERNEL_SHA256 = "a72bcf950d640d9909bc9094bec69cdd84443883dc54739c51416a999f77476d"
WWW = "system/WEBSERVER/www/"
MODULES = "system/usr/lib/modules/3.18.20/kernel/net/"


def kernel_image(boot):
    if boot[:8] != b"ANDROID!":
        raise ValueError("Invalid Android boot image header")
    size = struct.unpack_from("<I", boot, 8)[0]
    page = struct.unpack_from("<I", boot, 36)[0]
    compressed = boot[page:page + size]
    for marker in re.finditer(b"\x1f\x8b\x08", compressed):
        try:
            candidate = zlib.decompress(compressed[marker.start():], 31)
        except zlib.error:
            continue
        if hashlib.sha256(candidate).hexdigest() == KERNEL_SHA256:
            return candidate
    raise ValueError("The expected stock kernel image was not recovered")


def read_oem_inputs(source):
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != ZIP_SHA256:
            raise ValueError("OEM archive SHA-256 does not match the reference inner ZIP")
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            image = kernel_image(archive.read("boot.img"))
            start = image.index(b"IKCFG_ST") + len(b"IKCFG_ST")
            end = image.index(b"IKCFG_ED", start)
            # The bench's /proc/config.gz capture had an extra trailing LF.
            config = zlib.decompress(image[start:end], 31) + b"\n"
            files = {
                "kernel-decompressed.bin": image,
                "kernel.config": config,
                "udp_tunnel.ko": archive.read(MODULES + "ipv4/udp_tunnel.ko"),
                "ip6_udp_tunnel.ko": archive.read(MODULES + "ipv6/ip6_udp_tunnel.ko"),
                "oem-lib/libauth.so": archive.read("system/usr/lib/libauth.so"),
            }
            for item in archive.infolist():
                if item.filename.startswith(WWW) and not item.is_dir():
                    files["oem-www/" + item.filename.removeprefix(WWW)] = archive.read(item)
    return files


def verify_oem_inputs(files):
    manifest = Path(__file__).with_name("oem-extracted.sha256").read_text()
    expected = {name: digest for digest, name in
                (line.split("  ", 1) for line in manifest.splitlines())}
    if files.keys() != expected.keys():
        raise ValueError("Extracted OEM file list differs from oem-extracted.sha256")
    for name, data in files.items():
        if hashlib.sha256(data).hexdigest() != expected[name]:
            raise ValueError(f"{name}: extracted OEM file SHA-256 mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Inner 181220 _User.zip")
    parser.add_argument("output", type=Path, help="New or existing local build-input directory")
    args = parser.parse_args()
    try:
        files = read_oem_inputs(args.archive)
        verify_oem_inputs(files)
        for name, data in files.items():
            path = args.output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)
    except FileNotFoundError as error:
        parser.error(f"Required local file is missing: {error.filename}. See docs/source-build.md.")
    except (OSError, ValueError, KeyError, struct.error, zipfile.BadZipFile, zlib.error) as error:
        parser.error(str(error))
    print(f"Extracted and verified {len(files)} build inputs from the stock archive")


if __name__ == "__main__":
    main()
