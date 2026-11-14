# Bench results — 2026-11-14

Candidate `e3a3b1a` on M7350(EU) v5.2, firmware 1.0.10 Build 181220 Rel.1066n.

| Check | Outcome | Evidence and scope |
| --- | --- | --- |
| Source export | Pass | New Git history, explicit file selection, automated secret scan of the exported checkout and history, and exact-match checks against selected current device credentials. No secret values were printed. |
| Local suite | 50 passed, 1 skipped | 51 test methods completed on the host. The optional Chromium fixture was skipped. |
| Clean VM build | Pass, with external binaries | Fresh Debian 13 x86-64 QEMU guest, no network, cloned the candidate and compiled the ARM authentication and OLED helpers with Linaro 4.9.4. Generated the web overlay from separate OEM files and verified both manifests. The VPN userspace and kernel modules were checked inputs supplied as binaries. |
| Full VM test suite | Incomplete | The run reported errors in several timing-dependent SSH tests and hit the five-minute QEMU limit before producing its final report. These tests passed in the host suite. |
| Device install | Pass as an update | The router had about 2 MiB free in its persistent data partition. Applied a verified 448,641-byte update in place with a RAM backup. Verified 100 package files and 33 library artifacts, and authenticated CGI calls to status, statistics and VPN log. |
| Failed VPN startup | Pass | A temporary profile pointed at the documentation-only address 192.0.2.1. `RESULT unreachable: PASS`. The router reported that the server did not respond, removed PPP/VXLAN state and returned to factory mode. |
| Return to OEM and restore | Pass | Confirmed OEM bridge membership for USB and Wi-Fi. Unmounted the overlay, then confirmed the original web JavaScript was served using the saved OEM hash. Remounted in VPN Off. Restored the pre-test package and verified its original manifests. Boot ID stayed unchanged. |

Clean VM manifest hashes:

- `PACKAGE.sha256`: `724bd490cb5fce95bb008f0059088f3251a4360e6523270c8dec8332bbf7867e`
- `lib/MANIFEST.sha256`: `fef56bae5ed678b89c5e19d26353400210adfb31b5e8940156c0b02350f76a5d`

Fresh installation on stock firmware, reboot, and success against a real VPN peer were outside this bench run. The package build still needs a from-source path for the legacy dependencies before distribution. An isolated update and OEM return do not establish those results.
