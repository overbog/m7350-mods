# Source and archive catalog

Reference hardware: TP-Link M7350(EU) v5.2. Firmware archives below are labelled EU V5 by the vendor. Build 181220 matches the reference router. The other firmware packages are archival evidence and are untested as an installation base. We checked the recorded archive sizes and hashes against the retained copies on 2026-11-14. These are checks of retained bytes; no vendor signature for the archives is claimed.

| Build | Bytes verified | Size (bytes) | SHA-256 | Official location |
| --- | --- | ---: | --- | --- |
| 181220 | `M7350(EU) 5.0_1.0.10 Build 181220 Rel.1066n_User.zip` | 49889202 | `b146038929edbf0addefb6c3e47f4c1f135db9e86099f23a2fa3488a4b31511e` | [TP-Link](https://static.tp-link.com/2019/201901/20190122/M7350(EU)_V5_181220.zip) |
| 200330 | `M7350(EU) 5.0_1.0.13 Build 200330 Rel.1073n_User.zip` | 49956861 | `fa5aa716fa7eee81b8ccbbc5a043bebf9f6f80ced3ccf93b50e230592d890a6d` | [TP-Link](https://www.tp-link.com/support/download/m7350/v5/) |
| 201019 | `M7350(EU) 5.0_1.1.2 Build 201019 Rel.1077n_User.zip` | 50293225 | `9c71db79dfb147065d7061d2586498d7060f27894566471362610ee45dfb200b` | [TP-Link](https://www.tp-link.com/support/download/m7350/v5/) |
| GPL BSP | `M7350v5_en_gpl.tar` | 1467699200 | `1da697c7fcb24427ac796f7d46a5ba4d96da94c18e812dbedad09fe53105dee2` | [TP-Link](https://static.tp-link.com/resources/gpl/M7350v5_en_gpl.tar.gz) |

The three firmware rows refer to the inner `_User.zip` files. The GPL row refers to the decompressed tar. Check the hash at the matching layer. The direct URLs for the later firmware builds are listed on the regional support page. No Internet Archive copy has been checked for complete matching payloads. Use the vendor links first. Check a mirror against the same recorded hash before using it.

The [source build](source-build.md) uses the following other pinned inputs. The input filenames below are the names expected by the build recipe.

| Input | Origin | SHA-256 |
| --- | --- | --- |
| `M7350v5_en_gpl.tar.gz` | [TP-Link compressed GPL BSP](https://static.tp-link.com/resources/gpl/M7350v5_en_gpl.tar.gz). Use its `kernel/` subtree. | `22255db0e09b43758c887971f2e1b789c65a79b145ed6f93b60e9d2f6b8f7b35` |
| `zx-linux-3.4.tar.gz` | [ZX297520V3 Linux 3.4 at 80e1fec8](https://codeload.github.com/zx297520v3-mainline/linux-3.4/tar.gz/80e1fec813691ceb16567581c3fe4d49e4bab7f3). Use `drivers/net/wireless/rtl8192cd_92es` and apply the checked-in exact patches. | `3791b9e28d934dc5667306331b895943874581ec02eb4f48b81c5183adda2362` |
| `gcc492.tar.gz` | [Third-party Linaro GCC 4.9.2 prerelease, pinned repository commit](https://codeload.github.com/eckucukoglu/arm-linux-gnueabihf/tar.gz/e48c9ec0dc02714cc8dda84e8a4121db36920406). Used only for kernel modules. | `bc8f5e0653023b8f7d8f026a4acd8279f33377d50471edd045172b3b713e1435` |
| `linaro-mirror.tar.xz` | [Linaro GCC 4.9.4 on the Armbian mirror](https://mirrors.dotsrc.org/armbian-dl/_toolchain/gcc-linaro-4.9.4-2017.01-x86_64_arm-linux-gnueabi.tar.xz). | `232302236c90ec136a42d44bc387d2e1199f5df010b77e97ee590216d2b5b181` |
| `dropbear_2025.89.orig.tar.bz2` | [Debian source package](https://sources.debian.org/src/dropbear/2025.89-1~deb13u1/). The recipe uses the upstream tarball, with local options. | `0d1f7ca711cfc336dc8a85e672cab9cfd8223a02fe2da0a4a7aeb58c9e113634` |

The userspace source archives below were checked against retained copies. Use `xl2tpd-v1.3.18.tar.gz` for the xl2tpd archive. The other archives use the filenames shown by their upstream links, with the pppd archive named `ppp-2.4.9.tar.gz`.

| Input | Size (bytes) | SHA-256 |
| --- | ---: | --- |
| [strongSwan 5.9.14](https://download.strongswan.org/strongswan-5.9.14.tar.bz2) | 4869709 | `728027ddda4cb34c67c4cec97d3ddb8c274edfbabdaeecf7e74693b54fc33678` |
| [GMP 6.3.0](https://gmplib.org/download/gmp/gmp-6.3.0.tar.xz) | 2094196 | `a3c2b80201b89e68616f4ad30bc66aee4927c3ce50e33929ca819d5c43538898` |
| [xl2tpd 1.3.18](https://codeload.github.com/xelerance/xl2tpd/tar.gz/refs/tags/v1.3.18) | 534937 | `47f52b9c56cabe77766533bca3736a8198581ff38443eb4b4c8971c885ac9329` |
| [pppd 2.4.9](https://codeload.github.com/ppp-project/ppp/tar.gz/refs/tags/ppp-2.4.9) | 719904 | `675bff4f366174649f4a3c92fd32ac476e694164ff2b0b7710019b6ead9c561e` |
| [musl 1.2.5](https://musl.libc.org/releases/musl-1.2.5.tar.gz) | 1080786 | `a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4` |

Firmware, OEM HTML, upstream source archives and generated binaries stay outside Git. Public mirrors will be considered after checking redistribution rights for each artifact. A hash does not confer redistribution rights.
