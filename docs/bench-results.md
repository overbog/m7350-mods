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

Fresh installation and reboot were outside the update run above; see the separate test below. A real VPN peer was outside the update run; see the later Home test. The package build still needs a from-source path for the legacy dependencies before distribution. An isolated update and OEM return do not establish those results.


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

## Home VPN with L2 after reboot

**2026-11-14, candidate `e3a3b1a`: manual startup passed; automatic reconnection failed.** Reinstalled the clean VM build and verified both manifests. Restored only the bench Home profile from the private backup, enabled L2 and set USB to L3 for management. The VPN peer was observed independently; no changes were made to its configuration.

| Step (UTC) | Observation |
| --- | --- |
| 16:02:40, before reboot | Home was active with negotiated PPP addresses, and the router received 4/4 ping replies from the PPP peer. `vxlan0` was up on `bridge2` with the L2 Wi-Fi interface. Both endpoints counted received and transmitted VXLAN frames. A separate Wi-Fi client joined the L2 SSID and obtained a lease from the remote LAN. The peer's independently initiated PPP ping to the router received 0/3 replies. |
| 16:03:16, reboot requested | The boot ID changed. The saved Home profile started automatically at 14.22 seconds of device uptime, without a manual mode switch. The old PPP session closed on the peer at 16:03:48. |
| 16:03:55–16:03:56, automatic negotiation | Both logs showed that IKEv1 phase 1 succeeded. In phase 2, strongSwan selected the ESP proposal with MODP1024, reported `unable to apply received KE value`, and failed to establish `CHILD_SA 'l2tp'`. The peer deleted the new IKE SA. No new PPP session or VXLAN datapath came up. |
| After failure | Runtime reverted to OEM. The saved mode remained VPN until explicitly switched off. The summary classified the error as an IKE timeout, while the detailed log located it at the Diffie–Hellman exchange for phase 2 (PFS). Why the received key exchange value could not be applied is unconfirmed. |
| Removal | Pass. Switched to VPN Off, uninstalled the package and rebooted. Verified the OEM web fingerprint and login, original bridge membership, no PPP/VXLAN or package hooks, and no temporary SSH or Telnet listeners. |

Only one boot with Home enabled was attempted. This candidate should not be described as automatically reconnecting after reboot.

### Phase 2 recovery and repeat test

The peer requires ESP PFS with MODP1024. The old SA briefly coexisted with the new IKE exchange, but the two had different SPIs and there is no evidence that the old SA caused the error. In strongSwan 5.9.14, [Quick Mode](https://github.com/strongswan/strongswan/blob/5.9.14/src/libcharon/sa/ikev1/tasks/quick_mode.c) emits the error when its DH backend rejects the received public value. The [GMP backend](https://github.com/strongswan/strongswan/blob/5.9.14/src/libstrongswan/plugins/gmp/gmp_diffie_hellman.c) checks the encoded length and the value's range. The original retained logs do not establish which check failed. Accepting malformed key material, turning off PFS, or changing the shared peer policy was not part of the fix.

Client commit `6c87aa4` permits one retry with a fresh IKE SA after that specific Quick Mode error. It keeps the configured proposals and the cleartext L2TP block. The first attempt's filtered diagnostics are retained if startup fails. Host tests injected recovery on the second attempt and a repeated KE failure, checking the retry limit, the original PFS proposal, and the error presented to the user.

- **2026-11-14, 16:23:42 UTC:** rebooted the M7350 while Home with L2 was active. The boot ID changed and the saved profile started without a manual switch.
- **16:24:19 / 16:24:24 UTC:** the peer operator confirmed a new IKE/ESP SA and then a new PPP session. The router received 4/4 PPP ping replies.
- **16:24:55 UTC:** the device reported Home active with VXLAN on `bridge2`. The peer independently measured +19 RX and +1,471 TX VXLAN frames, with no increase in drops. A client joining the L2 SSID again received DHCP from the remote LAN.

**Automatic reconnection passed on this reboot.** Phase 2 succeeded on the first negotiation, so the live run did not exercise the new retry. The original intermittent fault was not reproduced, and its precise cause remains open.

After the repeat test, switched to VPN Off, removed the package and its boot hook, and rebooted into stock. Verified the OEM HTTP fingerprint and login over USB, OEM bridge membership, no PPP or VXLAN, and no SSH or Telnet listeners after temporary management was removed.

### Repeat reboot series

The same client code was reinstalled for another coordinated series with the peer operator. The Home profile and PFS proposal were unchanged. Each counted automatic attempt started from Home with PPP and VXLAN active. No peer-side configuration was changed.

| Reboot (UTC) | Result |
| --- | --- |
| 16:29:17 | LTE was not ready: Home started at 13.94 seconds of uptime and returned to OEM at 21.25 seconds with no LTE source IPv4. No IKE exchange took place in this boot attempt. The later IKE exchange at 16:30:12 was from a manual reactivation once LTE had an address. |
| 16:30:46 | Invalid trial: the bench runner rebooted before the stability marker cleared. The boot safety check held OEM, so there was no IKE attempt. Corrected the runner's precondition and left the router's safety check in place. |
| 16:32:12 | Phase 2 passed and L2TP reached the peer. The peer rejected the new PPP login because the previous session was still marked active. The device returned to OEM, so VXLAN did not return. |
| 16:38:19 | Phase 2 and PPP returned. The peer confirmed PPP from 16:38:59 to 16:39:13. The device then rolled back because the OEM Wi-Fi manager did not stop. End-to-end L2 recovery was not established. |
| 16:44:26 | Pass. The peer saw phase 2 and new PPP at 16:45:08. Home and VXLAN were active at 16:45:39, without manual intervention. PPP ping was 4/4, local VXLAN counters showed 172 RX and 7 TX, and a client on the L2 SSID obtained DHCP from the remote LAN. The peer independently measured +13 RX and +852 TX after its initial post-connect sample, with drops unchanged. |

There were four valid automatic startup attempts and one invalid trial. No valid attempt reproduced the original Diffie–Hellman public value rejection. No retry marker or saved first-attempt KE log was found. Automatic reconnection passed once in this series; recovery **using the KE retry** remains verified only by injected host tests. The separate LTE, PPP and Wi-Fi startup failures are not covered by that retry.

The package and temporary management access were removed. After another boot, the original web fingerprint and OEM login were verified over USB; no PPP or VXLAN remained and TCP 22, 23 and 2222 did not accept connections.

### LTE readiness, stale PPP and Wi-Fi manager shutdown

The boot hook now waits up to 60 seconds for a usable IPv4 source on the LTE interface before setting up IKE. Normal mode switches still report a missing IPv4 source immediately. This avoids starting IKE against a route through the wrong interface.

The peer allows one PPP session per account. The previous trace showed the old session survived for 51 seconds after reboot. The peer rejected the new login 12 seconds before the old session closed. The client received a generic PAP/CHAP rejection. After an initial rejection at boot, the router closes its failed L2TP call, waits 20 seconds and dials once more with the same profile and IPsec association. A second failure still aborts startup. The peer configuration was unchanged.

The OEM init script sends SIGTERM through BusyBox start-stop-daemon and returns without waiting for the daemon to finish. The service monitor normally starts it through the same init script, which is held during the driver switch. The updated shutdown waits 12 seconds, records PID, thread state and kernel wait channel at five seconds, and allows five more seconds after SIGKILL if the original OEM process is still present outside uninterruptible sleep. If the manager persists, startup aborts before the driver unload.

The peer operator confirmed a new phase 2 exchange and PPP session on all three initial reboots. Local checks distinguished full Home startup from a tunnel that briefly forwarded traffic before rollback.

| Reboot requested (UTC) | Local result and peer observation |
| --- | --- |
| 17:10:11 | Pass on `79524b1`. The peer rejected the login at 17:10:46 because the old session was still active. The old session closed at 17:10:56 and the automatic retry reconnected at 17:11:08. Home reported active at 17:11:43. PPP ping was 4/4, VXLAN recorded 173 RX and 7 TX, and a Wi-Fi client obtained DHCP from the remote LAN. |
| 17:17:49 | Pass on `bb706a4`. The peer rejected the first login at 17:18:29, released the old session at 17:18:30 and accepted the retry at 17:18:50. The USB host lost the device and reported failed enumeration. Wi-Fi management confirmed the new boot ID and active Home. A separate L2 association obtained DHCP from the remote LAN. |
| 17:24:24 | Wi-Fi manager shutdown passed on `bb706a4`: the same PID still existed after five seconds, with threads in R and S, and exited in the next second without SIGKILL. PPP connected on the first try at 17:25:02. The peer saw VXLAN frames, but local Home reverted to OEM at the L2 bridge check. The OEM gadget exposed `ecm0` in `bridge0` alongside `rndis0`. This violates the original exact membership check for USB L3. |

Commit `15b514b` allows the OEM ECM function alongside RNDIS only when USB is assigned to L3. The topology check still requires the intended bridge2 ports. A manual switch with `ecm0` present verified `bridge0` containing `ecm0`, `rndis0` and `wlan0`, and `bridge2` containing `wlan0-va0` and `vxlan0`.

The final reboot on `15b514b` was requested at **17:31:37 UTC**, with the gadget reporting USB disconnected. The peer confirmed stale PPP cleanup at 17:32:14 and the new IPsec and PPP session at 17:32:19 on the first attempt. Home became active at 56.65 seconds of device uptime. PPP ping passed 4/4. Local VXLAN counters showed 172 RX and 7 TX, and the peer measured +5 RX and +195 TX with drops unchanged. A client joined the L2 SSID and obtained DHCP from the remote LAN. SSH over the L3 SSID confirmed both bridge memberships and the new boot ID.

The host suite ran 53 tests, with 52 passes and the optional browser test skipped. It exercised an IPv4 route appearing during the wait, successful recovery from a boot-only PPP refusal, a repeated refusal, and immediate failure on a manual refusal. There was no live LTE wait or Quick Mode DH rejection in this series. The observed Wi-Fi shutdown delay accounts for one instance that would have exceeded the previous deadline. The SIGKILL fallback was not needed on the device.

After the final reboot test, removed the package, web overlay and boot hook. After another reboot, confirmed the original OEM web fingerprint and authenticated login over Wi-Fi, OEM Wi-Fi and RNDIS on `bridge0`, and no PPP or VXLAN devices. Removed temporary SSH recovery, its boot hook and its firewall rules. TCP ports 22, 23 and 2222 did not accept connections. The USB host still could not enumerate the router at the end of the run.

### OEM USB cable reconnect

**2026-11-14, 17:56 UTC.** After reconnecting the USB cable, the host logged an attempt to power-cycle the port at 17:56:19 UTC and `unable to enumerate USB device` at 17:56:21 UTC. Repeated checks found no TP-Link USB device and no bound RNDIS network interface. The staging VM had no USB network interface, so the OEM web interface could not be tested over USB. The OEM SSID was visible in a fresh Wi-Fi scan. No router configuration was changed. The cause of the enumeration failure remains undetermined.

**2026-11-14, 19:34 UTC, after a router restart.** The same USB port failed enumeration again at 19:34:33 UTC. The host still saw no TP-Link USB device or RNDIS interface, and the staging VM had no USB network interface. The OEM SSID reappeared in a fresh Wi-Fi scan. The web interface remained unverified over USB.

**2026-11-14, after battery removal and reinsertion.** The OEM SSID was briefly unavailable during the test. Once it reappeared, the bench host associated over Wi-Fi and reached the router directly at `192.168.0.1`. The login page returned HTTP 200, `settings.min.js` matched the stock SHA-256, and the VPN CGI returned HTTP 404. The temporary Wi-Fi client profile was removed after the check. This probe verified the web page and its OEM fingerprint without opening an admin session.

The USB host log shows the router last enumerating as `2357:0005` at 17:18:12 UTC, followed by a hub disable event and disconnect at 17:18:47 UTC. The host tried cycling port power and reported enumeration failure again at 19:52:05 UTC, around the battery reseat. The port was administratively enabled, its overcurrent count was zero, and the device was absent from the host USB inventory. The failure is at host USB enumeration, before RNDIS binding or VM passthrough can occur. The Linux hub message `disabled by hub (EMI?)` comes from a port-enable change and does not identify its cause. A cross-test with a known-good data cable and a different physical port or host is still needed to distinguish the cable, the host port, and the router-side USB connection. [Linux USB hub code](https://github.com/torvalds/linux/blob/master/drivers/usb/core/hub.c)

**2026-11-14, 19:54–19:55 UTC, second Linux host.** After the operator moved the router, it enumerated on the second host as `2357:000a` and then `2357:0005`. The host bound `rndis_host` and obtained `192.168.0.104/24` by DHCP. An HTTP request bound to the USB network interface returned 200 from the OEM login page at `192.168.0.1`. The settings bundle matched the OEM SHA-256 and the VPN CGI returned 404. The test confirms that USB data and RNDIS work on the second host in OEM mode. Cable reuse was not confirmed, so the test does not isolate the original failure to the first host, its port, or the cable.

**2026-11-14, 19:56 UTC, back on the first host.** The original physical port was assigned by path to the running staging VM. At 19:56:07 UTC the host reported `unable to enumerate USB device` after attempting a port power cycle. The host had no device at that path, and the guest had neither the TP-Link USB ID nor its RNDIS interface. The web probe over USB was blocked. These observations locate the failure at host enumeration with passthrough configured. A test with the VM assignment released is still outstanding.
