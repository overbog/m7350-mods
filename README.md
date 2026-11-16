# M7350 LTE VPN experiment

Reuse a TP-Link M7350(EU) v5.2 as an LTE router with routed L2TP/IPsec and optional Ethernet over VXLAN. The reference device runs TP-Link firmware **1.0.10 Build 181220 Rel.1066n**, with **Linux 3.18.20**.

> **Security limitation.** This router terminates the VPN. It sees traffic before encryption and stores VPN credentials. A compromised router can expose both. The project keeps the OEM firmware, web stack, kernel and hardware drivers. The 3.18 series was already end of life when its final kernel.org release appeared in May 2019. An available vendor download does not establish continued security maintenance. Treat this as a reuse experiment. For sensitive traffic or a network security boundary, use an actively maintained device. See the [Linux maintainer's announcement](https://lkml.rescloud.iu.edu/1905.2/00686.html).

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
