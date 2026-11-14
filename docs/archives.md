# Source and archive catalog

Reference hardware: TP-Link M7350(EU) v5.2. Firmware archives below are labelled EU V5 by the vendor. Build 181220 matches the reference router. The other firmware packages are archival evidence and are untested as an installation base. We checked the recorded archive sizes and hashes against the retained copies on 2026-11-14. These are checks of retained bytes; no vendor signature for the archives is claimed.

| Build | Bytes verified | Size (bytes) | SHA-256 | Official location |
| --- | --- | ---: | --- | --- |
| 181220 | `M7350(EU) 5.0_1.0.10 Build 181220 Rel.1066n_User.zip` | 49889202 | `b146038929edbf0addefb6c3e47f4c1f135db9e86099f23a2fa3488a4b31511e` | [TP-Link](https://static.tp-link.com/2019/201901/20190122/M7350(EU)_V5_181220.zip) |
| 200330 | `M7350(EU) 5.0_1.0.13 Build 200330 Rel.1073n_User.zip` | 49956861 | `fa5aa716fa7eee81b8ccbbc5a043bebf9f6f80ced3ccf93b50e230592d890a6d` | [TP-Link](https://www.tp-link.com/support/download/m7350/v5/) |
| 201019 | `M7350(EU) 5.0_1.1.2 Build 201019 Rel.1077n_User.zip` | 50293225 | `9c71db79dfb147065d7061d2586498d7060f27894566471362610ee45dfb200b` | [TP-Link](https://www.tp-link.com/support/download/m7350/v5/) |
| GPL BSP | `M7350v5_en_gpl.tar` | 1467699200 | `1da697c7fcb24427ac796f7d46a5ba4d96da94c18e812dbedad09fe53105dee2` | [TP-Link](https://static.tp-link.com/resources/gpl/M7350v5_en_gpl.tar.gz) |

The three firmware rows refer to the inner `_User.zip` files. The GPL row refers to the decompressed tar. Check the hash at the matching layer. The direct URLs for the later firmware builds are listed on the regional support page. No Internet Archive copy has been checked for complete matching payloads. Use the vendor links first. Check a mirror against the same recorded hash before using it.

The WLAN starting point is [ZX297520V3 Linux 3.4, rtl8192cd_92es at commit 80e1fec8](https://github.com/zx297520v3-mainline/linux-3.4/tree/80e1fec813691ceb16567581c3fe4d49e4bab7f3/drivers/net/wireless/rtl8192cd_92es). The vendor kernel source is in the GPL BSP above. The experimental two-VAP binary also needs our 9x07 port and exact build inputs. Complete corresponding source and patch provenance for the shipped candidate are still being assembled.

The bench toolchain is [Linaro GCC 4.9.4 archive on the Armbian mirror](https://mirrors.dotsrc.org/armbian-dl/_toolchain/gcc-linaro-4.9.4-2017.01-x86_64_arm-linux-gnueabi.tar.xz), SHA-256 `232302236c90ec136a42d44bc387d2e1199f5df010b77e97ee590216d2b5b181`. See the build procedure for the checked version.

The following userspace source archives were also checked against retained copies. They document the inputs for rebuilding the legacy programs; the bench package uses independently supplied binaries.

| Input | Size (bytes) | SHA-256 |
| --- | ---: | --- |
| [strongSwan 5.9.14](https://download.strongswan.org/strongswan-5.9.14.tar.bz2) | 4869709 | `728027ddda4cb34c67c4cec97d3ddb8c274edfbabdaeecf7e74693b54fc33678` |
| [GMP 6.3.0](https://gmplib.org/download/gmp/gmp-6.3.0.tar.xz) | 2094196 | `a3c2b80201b89e68616f4ad30bc66aee4927c3ce50e33929ca819d5c43538898` |
| [xl2tpd 1.3.18](https://codeload.github.com/xelerance/xl2tpd/tar.gz/refs/tags/v1.3.18) | 534937 | `47f52b9c56cabe77766533bca3736a8198581ff38443eb4b4c8971c885ac9329` |
| [pppd 2.4.9](https://codeload.github.com/ppp-project/ppp/tar.gz/refs/tags/ppp-2.4.9) | 719904 | `675bff4f366174649f4a3c92fd32ac476e694164ff2b0b7710019b6ead9c561e` |
| [musl 1.2.5](https://musl.libc.org/releases/musl-1.2.5.tar.gz) | 1080786 | `a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4` |

Firmware, OEM HTML, device snapshots and driver binaries are external inputs. Public mirrors will be considered after checking redistribution rights for each artifact. A hash does not confer redistribution rights.
