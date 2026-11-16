# Build the ARM runtime from source

This build targets M7350(EU) v5.2, OEM **1.0.10 Build 181220 Rel.1066n**, Linux 3.18.20. It produces 15 kernel modules and eight ARM programs, including optional Dropbear. The kernel itself stays OEM. Compile and inspect the artifacts on a Linux host. The build never connects to a router or loads a module.

## Inputs

Use an x86-64 Debian 13 VM with Python 3, GNU make, GCC, binutils, patch, bc, flex, bison, Perl, gzip, bzip2 and XZ. Install the ARM EABI cross compiler and headers (`gcc-arm-linux-gnueabi`, `libc6-dev-armel-cross`, `linux-libc-dev-armel-cross`) and the 32-bit host libraries (`libc6-i386`, `lib32stdc++6`, `lib32z1`) needed by the older GCC 4.9.2 prerelease. Install `qemu-user` for executable smoke tests. Use a fresh work directory on a Linux filesystem. The VM can be disconnected after installing build dependencies and staging the inputs.

Keep an input directory outside Git. Download the archives from the exact links in the [archive catalog](archives.md) and use the filenames and checksums in [runtime-inputs.sha256](../tools/runtime-inputs.sha256). The Linaro 4.9.4 archive supplies the old ARM glibc, while the 4.9.2 prerelease supplies the kernel compiler. Debian's ARM GCC 14 builds the musl userspace. The test packages were GCC 14.2.0-19 for the host, GCC 14.2.0-19cross1 for armel and Linux UAPI headers 6.12.38-1cross1 for armel.

Supply your own copy of the matching OEM image. Unpack the [official TP-Link 181220 outer ZIP](https://static.tp-link.com/2019/201901/20190122/M7350(EU)_V5_181220.zip) and pass the inner `M7350(EU) 5.0_1.0.10 Build 181220 Rel.1066n_User.zip`, SHA-256 `b146038929edbf0addefb6c3e47f4c1f135db9e86099f23a2fa3488a4b31511e`. The OEM extractor accepts that inner archive, verifies its checksum and every extracted file against [oem-extracted.sha256](../tools/oem-extracted.sha256), and refuses to overwrite existing outputs.

| OEM archive path | Local build input |
| --- | --- |
| `boot.img` | Decompressed stock kernel and its embedded `IKCFG`, with the trailing LF required to match the bench config |
| `system/usr/lib/modules/3.18.20/kernel/net/ipv4/udp_tunnel.ko` and `ipv6/ip6_udp_tunnel.ko` under the same `net/` directory | Tunnel-module metadata for symbol extraction |
| `system/usr/lib/libauth.so` | `oem-lib/libauth.so`, the private authentication link input |
| `system/WEBSERVER/www/` | `oem-www/`, the original assets used to generate the local web overlay |

The exact Realtek firmware used in both bench variants comes from the [pinned ZX297520V3 archive](https://codeload.github.com/zx297520v3-mainline/linux-3.4/tar.gz/80e1fec813691ceb16567581c3fe4d49e4bab7f3), saved as `zx-linux-3.4.tar.gz` with SHA-256 `3791b9e28d934dc5667306331b895943874581ec02eb4f48b81c5183adda2362`. The archive member prefix is `linux-3.4-80e1fec813691ceb16567581c3fe4d49e4bab7f3/drivers/net/wireless/rtl8192cd_92es/WlanHAL/Data/8192E/`.

| Archive member below that prefix | SHA-256 |
| --- | --- |
| `rtl8192Efw.bin` | `6c2add036e87196d01f43fb2bd8cfa4b80664a7c4ede7fbc7b31405df072ab39` |
| `rtl8192EfwMP.bin` | `1fcaf39cb56df935611a2c6e388e1c9cc791d0d2b9cf5eb74811936464e214ed` |

The runtime build calls `python3 tools/extract-realtek-firmware.py "$inputs/zx-linux-3.4.tar.gz" "$work/realtek-firmware"` automatically. You can run the extractor on its own with a fresh output directory. It verifies the archive and both regular members before writing any firmware. The runtime build excludes those two members from the generic driver extraction, copies in the individually verified bytes, and runs Kbuild's array generation locally. A missing archive or member, wrong version or digest mismatch stops the build. The ZX archive is the verified source for these exact two blobs. An equivalent extraction from the TP-Link image has not been established.

From the clean checkout, with `inputs` pointing to the downloaded archives and `work` pointing to a fresh build directory:

```sh
python3 tools/extract-oem-build-inputs.py "/path/to/181220_User.zip" "$inputs"
JOBS=2 tools/build-runtime.sh "$inputs" "$work"
python3 tools/check-runtime.py "$work/runtime" "$work/kernel/Module.symvers"
```

## Build and ABI details

- The kernel code is extracted from the TP-Link GPL BSP, with the pinned reference kernel configuration. `olddefconfig modules_prepare` prepares only the build tree. The only host compiler accommodation is `HOSTCFLAGS=-fcommon` for the old device-tree compiler. The target compiler is the pinned crosstool-NG Linaro **4.9.2 prerelease**, which is the bench compiler. The manufacturer's final compiler build is unidentified.
- The OEM ELF and bootloader are unnecessary to build modules. The decompressed kernel supplies 6,278 symbol names and the two OEM tunnel modules supply six more. The table is for modpost. The stock config has `CONFIG_MODVERSIONS=n`, so the CRC fields are zero placeholders. GPL-versus-ordinary export categories were not recovered. Import closure and vermagic do not verify all C layouts or runtime behavior.
- IPsec/crypto/XFRM objects are selected with external Kbuild files and use the BSP source. VXLAN also comes from the BSP. Its one translation unit sets `CONFIG_VXLAN_MODULE=1` so the BSP header exports the correct declarations without changing the base configuration.
- Realtek starts at the [ZX297520V3 Linux 3.4 archive](https://codeload.github.com/zx297520v3-mainline/linux-3.4/tar.gz/80e1fec813691ceb16567581c3fe4d49e4bab7f3). The [9x07 port](../experiments/rtl8192es-zx/zx-9x07-port.patch) is an exact diff against the retained one-VAP source tree. It includes the external Kbuild setup, SDIO and networking adaptations, and the optional VAP initialization and teardown handling. The [two-VAP delta](../experiments/rtl8192es-zx/zx-9x07-two-vap.patch) records the exact `platform.mk` changes used in the later two-VAP bench. The build verifies the bytes of all original archive members after applying each patch. Git preserves the original mixture of LF and CRLF in the patches. Kbuild generates firmware and table arrays from local inputs, including the two verified firmware files. The build disables legacy ZX power management, the ZTE worker-thread variant, and WPA3/SAE, and strips debug and comment sections from both output modules.
- `charon` and `swanctl` come from strongSwan 5.9.14 with only the configured monolithic plugins, statically linked against musl 1.2.5 and GMP 6.3.0. `pppd` and `xl2tpd` use Linaro GCC 4.9.4 with static glibc. The [build preparation](../experiments/oem-ipsec/prepare-userspace.py) relocates PPP configuration and hooks and gives xl2tpd the private pppd path. The slim pppd excludes plugins, MSCHAP/MPPE, EAP-TLS and IPv6. xl2tpd uses the PTY/PPP_ASYNC path. The three small runtime helpers are compiled from the checked-in C sources. Dropbear 2025.89 is dynamic against the OEM glibc, built with the checked-in key-only configuration.
- `check-runtime.py` checks ARM EABI5 ELF metadata, module imports and vermagic, Realtek's SDIO alias and VAP code markers, and the static-linkage expectation for the VPN executables. With `--bench DIR`, it also reports per-file hash equality against a retained runtime.

Recheck the extracted OEM inputs, assemble the package and verify both manifests:

```sh
repo=$(pwd)
(cd "$inputs" && sha256sum -c "$repo/tools/oem-extracted.sha256")
python3 tools/build.py \
  --toolchain "$work/toolchains/gcc-linaro-4.9.4-2017.01-x86_64_arm-linux-gnueabi" \
  --oem-www "$inputs/oem-www" --libauth "$inputs/oem-lib/libauth.so" \
  --runtime "$work/runtime" --output out/payload
(cd out/payload && sha256sum -c PACKAGE.sha256 && cd lib && sha256sum -c MANIFEST.sha256)
```

Keep the downloaded archives, extracted inputs, generated C arrays and complete payload local. The overlay incorporates OEM assets and the modules embed the firmware. The packager also accepts an existing separately verified runtime for historical bench work. Rebuilding the runtime does not require that previous payload.

See [provenance and licensing](licensing.md) and [bench results](bench-results.md).
