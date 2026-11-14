# M7350 LTE VPN experiment

Reuse a TP-Link M7350(EU) v5.2 as an LTE router with routed L2TP/IPsec and optional Ethernet over VXLAN. The reference device runs TP-Link firmware **1.0.10 Build 181220 Rel.1066n**, with **Linux 3.18.20**.

> **Security limitation.** This router terminates the VPN. It sees traffic before encryption and stores VPN credentials. A compromised router can expose both. The project keeps the OEM firmware, web stack, kernel and hardware drivers. The 3.18 series was already end of life when its final kernel.org release appeared in May 2019. An available vendor download does not establish continued security maintenance. Treat this as a reuse experiment. For sensitive traffic or a network security boundary, use an actively maintained device. See the [Linux maintainer's announcement](https://lkml.rescloud.iu.edu/1905.2/00686.html).

- [Development journal](docs/development.md)
- [Source and archive catalog](docs/archives.md)
- [Build and bench procedure](docs/build-and-test.md)

The archive catalog describes inputs obtained separately. This checkout is a local release candidate. Project licensing and redistribution status of third-party components are pending review.
