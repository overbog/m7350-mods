# M7350 LTE VPN experiment

Reuse a TP-Link M7350(EU) v5.2 as an LTE router with routed L2TP/IPsec and optional Ethernet over VXLAN. The reference device runs TP-Link firmware **1.0.10 Build 181220 Rel.1066n**, with **Linux 3.18.20**.

> **Security limitation — read before using.** This is a reuse experiment, not a secure product, and it does **no hardening**. It deliberately keeps the OEM firmware, web stack, vendor drivers and the **Linux 3.18.20** kernel — software that has been end of life since 2019 and carries many public, unpatched, well-documented vulnerabilities. Nothing in this project reduces that attack surface, and an available vendor download does not establish continued security maintenance.
>
> Assume the device can be taken over. Because it terminates the VPN, it sees traffic before encryption and stores VPN credentials, so a compromise exposes both. Treat the router — and any network segment it sits on — as untrusted:
>
> - **Do not place it on a network alongside devices you cannot trust:** smart/IoT devices from unknown or no-longer-supported vendors, old or unsupported IP cameras, other end-of-life or never-supported routers, or computers running software you cannot audit. A network is only as trustworthy as its least trustworthy device, and this device is not trustworthy.
> - **Do not place it on a network carrying devices or data you need to keep safe.** Keep it on an isolated, disposable segment, separate from anything that matters.
>
> The risks of keeping a device with many well-documented vulnerabilities exposed are too high for any use that matters. For sensitive traffic, or as a network security boundary, use an actively maintained device. See the [Linux maintainer's announcement](https://lkml.rescloud.iu.edu/1905.2/00686.html).

- [Development journal](docs/development.md)
- [Source and archive catalog](docs/archives.md)
- [ARM runtime source build](docs/source-build.md)
- [Provenance and licenses](docs/licensing.md)
- [Build and bench procedure](docs/build-and-test.md)
- [Bench results](docs/bench-results.md)
- [MikroTik server configuration](docs/vpn-mikrotik-server.md)

The archive catalog describes inputs obtained separately. This checkout is a local release candidate. Project licensing and redistribution status of third-party components are pending review.

## AI usage

Much of this project — code, tests, documentation and configuration — was produced with the help of AI coding assistants (Anthropic's Claude and OpenAI's Codex) acting as directed agents under human supervision. A human operator set the goals, made the design and security decisions, ran the on-device trials, and reviewed the work before it was committed. Commits are recorded under a single project identity ("M7350 Project") rather than per individual author.

AI assistants can be wrong, sometimes confidently. Combined with the security limitation above, treat everything here as a reuse experiment: review anything you depend on and verify its behaviour on your own device.
