# Build input provenance and license inventory

The project's original code is licensed under GNU GPL version 2 only (`GPL-2.0-only`). The top-level [LICENSE](../LICENSE) contains the full June 1991 license text. SPDX headers identify the project's scripts, helpers, build tools, web module and tests. Upstream and vendored components retain their own licenses and notices as inventoried below.

The source build uses the pinned inputs in [the archive catalog](archives.md) and [the checksum manifest](../tools/runtime-inputs.sha256).

| Component | Evidence and license |
| --- | --- |
| TP-Link Linux 3.18.20 BSP, external crypto, XFRM, ESP4 and VXLAN modules | TP-Link's M7350 V5 GPL source archive, kernel `COPYING` and per-file headers. Linux's top-level notice specifies GPL version 2, with separate terms where marked. The runtime's modules declare GPL in ELF metadata. |
| ZX Realtek RTL8192ES driver and 9x07 patches | ZX297520V3 Linux 3.4 tree at commit `80e1fec813691ceb16567581c3fe4d49e4bab7f3`. Core files including `8192cd_osdep.c` carry Realtek's GPL version 2 notice. The subtree also contains other notices, including an all-rights-reserved header in `WlanHAL/RTL88XX/Hal88XXFirmware.c`, and precompiled radio firmware blobs under `WlanHAL/Data/8192E`. Build rules convert data into embedded C arrays. A GPL module tag establishes neither the firmware source nor redistribution permission for all embedded bytes. Complete per-file review and permission for any bundled firmware remain open. |
| strongSwan 5.9.14 | GPL-2.0-or-later per upstream `LICENSE`, with exceptions for specifically named plugin sources. The Blowfish/DES/MD4/MD5 plugins named by that exception are excluded by the selected build. [Upstream release license](https://github.com/strongswan/strongswan/blob/5.9.14/LICENSE) |
| GMP 6.3.0 | Upstream `README`, `COPYING.LESSERv3` and `COPYINGv2` identify the LGPL-3.0-or-later or GPL-2.0-or-later options for the library. The runtime links GMP statically. [Upstream licensing](https://gmplib.org/) |
| musl 1.2.5 | Upstream `COPYRIGHT` identifies MIT terms and lists component notices. [Versioned source notice](https://git.musl-libc.org/cgit/musl/tree/COPYRIGHT?h=v1.2.5) |
| pppd 2.4.9 | The upstream README identifies BSD-style source notices for pppd and separately licensed plugins. The core contains Carnegie Mellon and Paul Mackerras notices. The build omits plugins. Preserve the exact source-file notices and acknowledgments. [Versioned source README](https://github.com/ppp-project/ppp/blob/ppp-2.4.9/README) |
| xl2tpd 1.3.18 | Upstream `LICENSE` contains GPL version 2. Daemon sources refer to the bundled GPL. [Versioned source license](https://github.com/xelerance/xl2tpd/blob/v1.3.18/LICENSE) |
| Dropbear 2025.89 | Debian's source archive contains upstream sources and `LICENSE`, including MIT-style notices and the separate notices for bundled components. The build uses the upstream tarball and the repository's local options. [Upstream source license](https://github.com/mkj/dropbear/blob/DROPBEAR_2025.89/LICENSE) |
| Linaro / GNU toolchains | The Linaro archives supply GCC, GNU binutils and the associated runtime components. GCC and binutils have GPL notices and the GCC runtime exception applies where specified by the corresponding runtime file. The older kernel-toolchain archive is third-party and pinned by hash. |
| EGLIBC 2.19 | Linaro GCC 4.9.4-2017.01 supplies the static libc used by pppd, xl2tpd and the OEM offload helper. The retrieved source revision contains LGPL 2.1 in `libc/COPYING.LIB`, GPL in `libc/COPYING` and per-file notices. See the [binary release policy](#eglibc-source-for-binary-releases). |
| OEM inputs and web overlay | The matching stock archive supplies the OEM web assets, proprietary `libauth.so` link input, existing tunnel-module metadata and the original kernel image used for symbol/config extraction. The user supplies the matching OEM ZIP. The extractor checks each OEM input, and the generated overlay, original web assets and proprietary link input stay local. |
| Nayuki QR Code generator | Retains the MIT notice in the checked-in source. |

## EGLIBC source for binary releases

Every binary release that includes programs statically linked with EGLIBC must make the exact corresponding EGLIBC source and build recipe available. Ship the tarball and recipe alongside the binaries, or give recipients a release-specific link in this repository to the exact source and recipe, with version and SHA-256 pins, from which the library can be rebuilt. Include the applicable notices and the materials needed to relink the statically linked programs with a modified library. If the pinned downloads are inaccessible at release time, supply the source and recipe alongside the binaries. Generated binaries stay outside Git.

The current recipe uses EGLIBC 2.19 (`2.19-2014.08-1-git` in `libc/version.h`), branch `linaro_eglibc-2_19`, revision `ab302c9d26707876d053f17d39d8aa6ef951e3e0`. The `gcc-linaro-4.9.4-2017.01-linux-manifest.txt` file inside the pinned `arm-linux-gnueabi` toolchain names that revision and the corresponding Linaro Advanced Build Environment (ABE) revision. Use the manifest and the ABE recipe with the pinned source listed in the [archive catalog](archives.md#eglibc-corresponding-source). The downloaded archive hashes and embedded Git revisions were verified. Rebuilding EGLIBC itself from these inputs has not been tested.

## Locally extracted inputs

This repository does not redistribute either radio firmware blob or its generated C array. The build extracts the two files locally from the pinned ZX archive and checks each file before Kbuild embeds its bytes in the locally generated modules. Provenance of the exact bytes ends at the ZX archive. See the [extraction procedure](source-build.md#inputs).

| File under `WlanHAL/Data/8192E/` | Bytes | SHA-256 |
| --- | ---: | --- |
| `rtl8192Efw.bin` | 24052 | `6c2add036e87196d01f43fb2bd8cfa4b80664a7c4ede7fbc7b31405df072ab39` |
| `rtl8192EfwMP.bin` | 24632 | `1fcaf39cb56df935611a2c6e388e1c9cc791d0d2b9cf5eb74811936464e214ed` |

The complete local payload includes the embedded radio bytes and OEM-derived overlay. Before any binary release, account for the exact corresponding sources and local build scripts, any statically linked dependencies, required notices and licenses, the Realtek embedded firmware, and the OEM-derived overlay. The repository carries recipes and source diffs. Upstream archives, radio and OEM firmware, original OEM web assets and generated binary packages stay outside Git.
