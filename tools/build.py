#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Assemble a local bench package from explicit, separately supplied inputs."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "package/m7350-l2"
MODULES = """aead authenc cbc cryptomgr esp4 hmac pcompress rtl8192es-two-vap
    seqiv sha1_generic sha256_generic vxlan xfrm_algo xfrm_user rtl8192es-lean""".split()
TOOLS = """charon load-module-fd-musl pause_oem_offload pppd remove_owned_module
    swanctl xl2tpd""".split()
ROUTING = ("apply-routing.sh", "dnsmasq-vpn.conf.example", "ppp-ip-down",
           "ppp-ip-up", "rollback-routing.sh")
VXLAN = ("m7350-bridge2-lan.sh", "m7350-vxlan-apply.sh", "m7350-vxlan-rollback.sh")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest(directory, output):
    rows = [f"{digest(p)}  {p.relative_to(directory)}\n"
            for p in sorted(directory.rglob("*")) if p.is_file() and p != output]
    output.write_text("".join(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("oem-www", "libauth", "runtime", "toolchain", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    cc = args.toolchain.resolve() / "bin/arm-linux-gnueabi-gcc"
    strip = cc.with_name("arm-linux-gnueabi-strip")
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".m7350-build-") as work:
        package = Path(work) / "payload"
        package.mkdir()
        for name in ("bin", "etc", "home.d", "init.d", "modes", "provider.d"):
            shutil.copytree(PACKAGE / name, package / name, ignore=shutil.ignore_patterns(".keep"))
        lib = package / "lib"
        for name in ("bin", "ko", "research"):
            (lib / name).mkdir(parents=True)
        for source in (PACKAGE / "lib").glob("*.sh"):
            shutil.copy2(source, lib / source.name)
        runtime = args.runtime.resolve()
        subprocess.run(["sha256sum", "--check", "--quiet", "SHA256SUMS"], cwd=runtime, check=True)
        pinned = {line.split()[1].removeprefix("./"): line.split()[0]
                  for line in (runtime / "SHA256SUMS").read_text().splitlines()}
        for name in (*[f"ko/{module}.ko" for module in MODULES],
                     *[f"bin/{tool}" for tool in TOOLS],
                     *(["bin/dropbearmulti"] if (runtime / "bin/dropbearmulti").exists() else [])):
            source = runtime / name
            if digest(source) != pinned.get(name):
                raise SystemExit(f"runtime artifact absent from manifest or changed: {name}")
            dest = lib / name
            shutil.copyfile(source, dest)
            dest.chmod(0o755 if name.startswith("bin/") else 0o644)
        for source_dir, names in (("experiments/oem-ipsec/vpn-client", ROUTING),
                                  ("experiments/vxlan", VXLAN)):
            for name in names:
                shutil.copy2(ROOT / source_dir / name, lib / "research" / name)

        auth_dir = Path(work) / "oem-lib"
        auth_dir.mkdir()
        shutil.copyfile(args.libauth, auth_dir / "libauth.so")
        flags = ["-Os", "-Wall", "-Wextra", "-Werror", "-march=armv7-a", "-mfloat-abi=soft"]
        src = PACKAGE / "src"
        auth = lib / "bin/m7350l2-auth"
        menu = lib / "bin/m7350l2-menu"
        subprocess.run([cc, *flags, "-o", auth, src / "m7350l2-auth.c",
                        f"-L{auth_dir}", "-lauth", "-Wl,--allow-shlib-undefined"], check=True)
        subprocess.run([cc, *flags, "-std=gnu99", "-static", f"-I{src}", "-o", menu,
                        src / "m7350l2-menu.c", src / "wifi-qr.c", src / "qrcodegen/qrcodegen.c"],
                       check=True)
        subprocess.run([strip, auth, menu], check=True)
        with (lib / "MANIFEST.sha256").open("w") as stream:
            for name in ("bin", "ko", "research"):
                for item in sorted((lib / name).iterdir()):
                    stream.write(f"{digest(item)}  {item.relative_to(lib)}\n")
        subprocess.run(["python3", PACKAGE / "tools/build-www.py", args.oem_www.resolve(),
                        PACKAGE, package / "www"], check=True)
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True)
        (package / "REVISION").write_text(revision)
        manifest(package, package / "PACKAGE.sha256")
        package.rename(output)


if __name__ == "__main__":
    main()
