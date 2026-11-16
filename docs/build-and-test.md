# Build and bench procedure

Use x86-64 Debian with Python 3.11 or later, Git, GNU coreutils, a native C compiler with libc headers for tests, and a verified Linaro 4.9.4 ARM cross compiler. This checkout builds the web patch and the ARM authentication and OLED helpers. Use the [ARM runtime source build](source-build.md) to produce the modules and VPN programs supplied to the package assembler.

Prepare these inputs outside the repository:

- The OEM `/WEBSERVER/www` from the exact reference firmware and OEM `usr/lib/libauth.so`. Obtain them from firmware or a local reference device. Do not use a boot or filesystem archive as an input to the packager.
- The unpacked compiler from the [archive catalog](archives.md).
- The output of the source build, or a retained and separately reviewed runtime, containing `bin/`, `ko/`, and a `SHA256SUMS` manifest pinned to those exact files. See `MODULES` and `TOOLS` in [the build script](../tools/build.py). Optional key-only Dropbear is a separately obtained dependency. The build does not install or set up SSH access.

```sh
python3 -m unittest discover -s tests
python3 tools/build.py --toolchain /path/to/compiler \
  --oem-www /path/to/oem-www --libauth /path/to/libauth.so \
  --runtime /path/to/runtime --output out/payload
(cd out/payload && sha256sum -c PACKAGE.sha256 && cd lib && sha256sum -c MANIFEST.sha256)
```

The output includes an overlay generated from local OEM files. Keep the package local while redistribution review is pending. The manifest checks integrity and is not a signature.

## Router bench

Reference platform only: M7350(EU) v5.2, firmware 1.0.10 Build 181220 Rel.1066n and kernel 3.18.20. Use USB management and an existing authorized shell. Record the boot ID, free space, active mode and current OEM web fingerprint. Start from VPN Off. Turn off VPN before unmounting an overlay or replacing any files. Never flash an OTA to make the build match this procedure.

For a bench router that already has the overlay installed, test an update as a verified delta. Stage in RAM, compare hashes, and back up the affected files before replacing them. Keep profile, key and state directories out of the update. Unmount the old overlay using the existing init hook, apply the reviewed files and verify both manifests, then bind-mount the new overlay. The OEM web fingerprint must match before mounting. Verify that the web assets served by the router match the build. Use only an isolated test profile for a failed connection probe.

Verify VPN Off with `/data/m7350-l2/bin/m7350-mode set factory` and `sh /data/m7350-l2/modes/factory.sh check`. Verify that there are no PPP or VXLAN interfaces left and that the original Wi-Fi and USB network are usable. To verify the unmodified OEM web UI, call the installed init hook with `www-umount`, check the OEM hash and load the page. Remount using the existing hook's normal startup procedure, or leave the overlay off if retiring the package.


## Clean installation and removal on the reference device

See the [physical bench results](bench-results.md#clean-install-reboot-and-removal). This procedure assumes a trusted administrative shell reachable over USB, independent of the package. Establish and verify that access before removing or installing anything. For the reference OEM firmware, see [temporary root shell over USB](oem-usb-shell.md). Keep access restricted to the bench, and remove temporary recovery services when finished. This procedure neither flashes firmware nor resets OEM settings.

1. Back up `/data/config` off the router, including the Wi-Fi and admin settings. For a previously used bench unit also back up the old package, its profiles and its init files. Treat the archive as a secret and keep it outside Git. Verify that the archive is readable and contains the expected files before making changes.
2. Start with the OEM web tree live, `/data/m7350-l2` absent and no package init hook or runlevel links. Confirm that the original web JavaScript hash matches `www.oem-settings.sha256`. Check free space on `/data`. Make the tar on the build host and preserve its permissions, including executable bits for shell scripts, binaries and CGI programs.
3. Create `/data/m7350-l2` as root and unpack the contents of the payload tar into it. Verify `PACKAGE.sha256` in the package directory and `lib/MANIFEST.sha256` from the `lib` directory. Do this before registering the init hook.
4. Copy `init.d/m7350-l2` from the package to `/etc/init.d/m7350-l2`, preserving its executable bit. On the reference SysV firmware, register `S99m7350-l2` in `rc2.d` through `rc5.d` and `K99m7350-l2` in `rc0.d`, `rc1.d` and `rc6.d`, pointing to `../init.d/m7350-l2`. Invoke the hook with `start`. Without an installed profile the router stays on VPN Off. Verify that the custom web UI and authenticated CGI respond and the OLED helper is running. Reboot, verify that the boot ID changes, and repeat those checks.
5. To remove the package, back up any settings you intend to keep. Run `bin/m7350-mode set factory` and `sh modes/factory.sh check` from the package directory. Check that no PPP or VXLAN interface or Wi-Fi overlay remains. Use the hook's `www-umount` action and check that all paths listed in `www.mounts` are unmounted and that the original JavaScript hash is served. Stop the package OLED helper and, if enabled, stop the package SSH service from a separate administrative connection. Remove the registered links, hook, package directory and its runtime directory. This removes the package's saved VPN profiles and settings.
6. Reboot again. Verify the OEM web login and that USB and OEM Wi-Fi are on `bridge0`. Verify the absence of the VPN boot hook, overlay and tunnel devices. Remove any temporary bench access and check from the USB host that OEM HTTP still works and the temporary listener is closed.

The bench test used a fresh package on a configured stock system with a temporary USB-only management path. The stock-to-shell procedure and the live VPN reboot trials are documented separately.
