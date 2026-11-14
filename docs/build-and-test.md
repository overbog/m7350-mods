# Build and bench procedure

Use x86-64 Debian with Python 3.11 or later, Git, GNU coreutils, a native C compiler with libc headers for tests, and a verified Linaro 4.9.4 ARM cross compiler. This checkout builds the web patch and the ARM authentication and OLED helpers. Assembly still requires locally supplied ARM modules and VPN programs. It does not yet reproduce those components from source.

Prepare these inputs outside the repository:

- The OEM `/WEBSERVER/www` from the exact reference firmware and OEM `usr/lib/libauth.so`. Obtain them from firmware or a local reference device. Do not use a boot or filesystem archive as an input to the packager.
- The unpacked compiler from the [archive catalog](archives.md).
- A reviewed runtime directory containing `bin/`, `ko/`, and a `SHA256SUMS` manifest pinned to those exact files. See `MODULES` and `TOOLS` in [the build script](../tools/build.py). Optional key-only Dropbear is a separately obtained dependency. The build does not install or set up SSH access.

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

Verify VPN Off with `/data/m7350-l2/bin/m7350-mode set factory` and `sh /data/m7350-l2/modes/factory.sh check`. Verify that there are no PPP or VXLAN interfaces left and that the original Wi-Fi and USB network are usable. To verify the unmodified OEM web UI, call the installed init hook with `www-umount`, check the OEM hash and load the page. Remount using the existing hook's normal startup procedure, or leave the overlay off if retiring the package. A clean first installation and removal still need a separately validated procedure.
