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

Fresh installation and reboot were outside the update run above; see the separate test below. Success against a real VPN peer was not tested with this candidate. The package build still needs a from-source path for the legacy dependencies before distribution. An isolated update and OEM return do not establish those results.


## Clean install, reboot and removal

Physical M7350(EU) v5.2 with OEM 1.0.10 Build 181220 Rel.1066n and the same clean VM candidate, `e3a3b1a`. No firmware was flashed. Before removing the old research package, an off-device, access-restricted backup captured all of `/data/config`, the previous package and profiles, and the old boot hook and links. The archive was read back and verified; it is not in this repository.

| Check | Result |
| --- | --- |
| Stock baseline | Pass. Removed the prior package and its boot hook and booted into OEM. The original OEM web JavaScript was served and the package, overlay and tunnel interfaces were absent. |
| Clean install | Pass. Installed the whole VM-built payload in an empty package directory with no imported profiles, keys or secrets. Verified 98 package file hashes and 33 runtime artifacts. The web overlay and authenticated CGI responded, and the OLED helper started. Free space on `/data` after installation was 2,652 KiB. |
| Reboot with the package installed | Pass. New boot ID; management returned after about 29 seconds. The boot hook brought back the OLED helper and web overlay, both manifests passed again, and all three test SSID settings saved through the authenticated CGI were still present. VPN stayed Off. |
| Uninstall and reboot | Pass. Returned to VPN Off, removed the hook, links, overlay, package and test settings, then verified the original OEM web files and OEM processes both before and after a new boot. USB and OEM Wi-Fi returned to `bridge0`; no PPP or VXLAN interfaces remained. |
| OEM settings and access | Pass. Ten of eleven selected OEM configuration files were byte-identical to the backup. The only changes in the eleventh file, `netmanager`, were its `hw_time` and `sys_time` fields. Removed the temporary USB management hook, files and firewall rules. From the USB host, TCP 22, 23 and 2222 no longer accepted connections and the stock admin login still worked. |

Served OEM `settings.min.js` SHA-256: `3632d8302159b5913c4cbd01c3a6a626905c1fe7daff3cd0f6cc14f7a832d374`. The candidate served `1d225254b99e36919957c7e3e137195b0b9d3a6c93c853babf8b5826a412fe6d` both before and after reboot. The router was left in OEM with the research package removed. Wi-Fi association by a separate client and automatic VPN connection to a real peer were out of scope for this run.
