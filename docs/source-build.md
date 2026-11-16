# Build the ARM runtime from source

This build targets M7350(EU) v5.2, OEM **1.0.10 Build 181220 Rel.1066n**, Linux 3.18.20. It produces 15 kernel modules and eight ARM programs, including optional Dropbear. The kernel itself stays OEM. Compile and inspect the artifacts on a Linux host. The build never connects to a router or loads a module.

## Inputs

Use an x86-64 Debian 13 VM with Python 3, GNU make, GCC, binutils, patch, bc, flex, bison, Perl, gzip, bzip2 and XZ. Install the ARM EABI cross compiler and headers (`gcc-arm-linux-gnueabi`, `libc6-dev-armel-cross`, `linux-libc-dev-armel-cross`) and the 32-bit host libraries (`libc6-i386`, `lib32stdc++6`, `lib32z1`) needed by the older GCC 4.9.2 prerelease. Install `qemu-user` for executable smoke tests. Use a fresh work directory on a Linux filesystem. The VM can be disconnected after installing build dependencies and staging the inputs.

Put the archives listed in [runtime-inputs.sha256](../tools/runtime-inputs.sha256) in a directory outside Git. Use these names even when the vendor download has a different filename. The [archive catalog](archives.md) identifies each archive. The Linaro 4.9.4 archive supplies the old ARM glibc, while the Linaro 4.9.2 prerelease supplies the kernel compiler. Debian's ARM GCC 14 builds the musl userspace. The test packages were GCC 14.2.0-19 for the host, GCC 14.2.0-19cross1 for armel and Linux UAPI headers 6.12.38-1cross1 for armel.

Generate the OEM inputs directly from the verified **inner** 181220 `_User.zip`:

```sh
python3 tools/extract-oem-build-inputs.py "/path/to/181220_User.zip" "$inputs"
JOBS=2 tools/build-runtime.sh "$inputs" "$work"
python3 tools/check-runtime.py "$work/runtime" "$work/kernel/Module.symvers"
```

The extractor takes the ARM kernel from the gzip stream in the Android `boot.img`, checks its decompressed hash, and extracts the embedded `IKCFG`. It appends the single trailing blank line present in the retained OEM config capture. Both `udp_tunnel.ko` and `ip6_udp_tunnel.ko` come from the stock ZIP and match the copies used in the earlier bench. They are used only to derive exports and are absent from the output runtime. The same ZIP supplies `libauth.so` and OEM web assets.

## Build and ABI details

- The kernel code is extracted from the TP-Link GPL BSP, with the pinned reference kernel configuration. `olddefconfig modules_prepare` prepares only the build tree. The only host compiler accommodation is `HOSTCFLAGS=-fcommon` for the old device-tree compiler. The target compiler is the pinned crosstool-NG Linaro **4.9.2 prerelease**, which is the bench compiler. The manufacturer's final compiler build is unidentified.
- The OEM ELF and bootloader are unnecessary to build modules. The decompressed kernel supplies 6,278 symbol names and the two OEM tunnel modules supply six more. The table is for modpost. The stock config has `CONFIG_MODVERSIONS=n`, so the CRC fields are zero placeholders. GPL-versus-ordinary export categories were not recovered. Import closure and vermagic do not verify all C layouts or runtime behavior.
- IPsec/crypto/XFRM objects are selected with external Kbuild files and use the BSP source. VXLAN also comes from the BSP. Its one translation unit sets `CONFIG_VXLAN_MODULE=1` so the BSP header exports the correct declarations without changing the base configuration.
- Realtek starts at the [ZX297520V3 Linux 3.4 archive](https://codeload.github.com/zx297520v3-mainline/linux-3.4/tar.gz/80e1fec813691ceb16567581c3fe4d49e4bab7f3). The [9x07 port](../experiments/rtl8192es-zx/zx-9x07-port.patch) is an exact diff against the retained one-VAP source tree. It includes the external Kbuild setup, SDIO and networking adaptations, and the optional VAP initialization and teardown handling. The [two-VAP delta](../experiments/rtl8192es-zx/zx-9x07-two-vap.patch) records the exact `platform.mk` changes used in the later two-VAP bench. The build verifies the bytes of all original archive members after applying each patch. Git preserves the original mixture of LF and CRLF in the patches. Kbuild generates firmware and table arrays from data files in the source archive. The build disables legacy ZX power management, the ZTE worker-thread variant, and WPA3/SAE, and strips debug and comment sections from both output modules.
- `charon` and `swanctl` come from strongSwan 5.9.14 with only the configured monolithic plugins, statically linked against musl 1.2.5 and GMP 6.3.0. `pppd` and `xl2tpd` use Linaro GCC 4.9.4 with static glibc. The [build preparation](../experiments/oem-ipsec/prepare-userspace.py) relocates PPP configuration and hooks and gives xl2tpd the private pppd path. The slim pppd excludes plugins, MSCHAP/MPPE, EAP-TLS and IPv6. xl2tpd uses the PTY/PPP_ASYNC path. The three small runtime helpers are compiled from the checked-in C sources. Dropbear 2025.89 is dynamic against the OEM glibc, built with the checked-in key-only configuration.
- `check-runtime.py` checks ARM EABI5 ELF metadata, module imports and vermagic, Realtek's SDIO alias and VAP code markers, and the static-linkage expectation for the VPN executables. With `--bench DIR`, it also reports per-file hash equality against a retained runtime.

Assemble the package and verify both manifests:

```sh
python3 tools/build.py \
  --toolchain "$work/toolchains/gcc-linaro-4.9.4-2017.01-x86_64_arm-linux-gnueabi" \
  --oem-www "$inputs/oem-www" --libauth "$inputs/oem-lib/libauth.so" \
  --runtime "$work/runtime" --output out/payload
(cd out/payload && sha256sum -c PACKAGE.sha256 && cd lib && sha256sum -c MANIFEST.sha256)
```

The packager also accepts an existing separately verified runtime for historical bench work. Rebuilding the runtime does not require that previous payload.

See [provenance and licensing](licensing.md) and [bench results](bench-results.md).
