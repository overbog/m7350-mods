#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Explicit operator rollback only. This returns client forwarding/DNS to OEM/LTE.
# It does not terminate the VPN or remove unrelated routes/SA/modules.
set -eu
base=/run/m7350-vpn
. "$base/routing.env"
test -e "$base/routing-installed"

delete_rule() {
    tool=$1 table=$2 chain=$3
    shift 3
    if "$tool" -t "$table" -C "$chain" "$@" >/dev/null 2>&1; then
        "$tool" -t "$table" -D "$chain" "$@"
    fi
}

delete_chain() {
    tool=$1 table=$2 chain=$3
    if "$tool" -t "$table" -nL "$chain" >/dev/null 2>&1; then
        "$tool" -t "$table" -F "$chain"
        "$tool" -t "$table" -X "$chain"
    fi
}

delete_rule iptables nat PREROUTING -j M7350_DNS
delete_rule iptables nat POSTROUTING -j M7350_NAT
delete_rule iptables mangle FORWARD -j M7350_MSS
delete_rule iptables filter OUTPUT -j M7350_OUT
delete_rule ip6tables filter INPUT -j M7350_DNS6
for proto in udp tcp; do
    delete_rule ip6tables filter OUTPUT ! -o lo -p "$proto" --dport 53 -j DROP
done
if ip rule show | grep -q "^$LAN_RULE:"; then
    ip rule del priority "$LAN_RULE" iif "$LAN_IF" table "$TABLE"
fi
if ip rule show | grep -q "^$DNS_RULE:"; then
    ip rule del priority "$DNS_RULE" to "$VPN_DNS/32" table "$TABLE"
fi
ip route flush table "$TABLE"
if [ "${TUNNEL_OWNS_ESP_GUARD:-0}" != 1 ]; then
    ip xfrm policy delete dir out dst "$VPN_SERVER/32" proto udp dport 1701
fi
# Remove the forwarding guards last, after intentional routing rollback.
delete_rule iptables filter FORWARD -j M7350_VPN4
delete_rule ip6tables filter FORWARD -j M7350_VPN6
for chain in M7350_VPN4 M7350_OUT; do delete_chain iptables filter "$chain"; done
for chain in M7350_VPN6 M7350_DNS6; do delete_chain ip6tables filter "$chain"; done
for chain in M7350_DNS M7350_NAT; do delete_chain iptables nat "$chain"; done
delete_chain iptables mangle M7350_MSS
pid=$(cat "$base/owned-dnsmasq.pid")
if test -e "/proc/$pid/cmdline"; then
 test "$(tr '\000' ' ' < /proc/$pid/cmdline)" = "dnsmasq --no-daemon --conf-file=$base/dnsmasq-vpn.conf "
 kill -TERM "$pid"
fi
# Preserve the previous OEM power-managed offload state, not arbitrary modules.
if ! grep -q '^shortcut_fe_cm ' /proc/modules; then
    insmod "$base/saved-shortcut-fe-cm.ko"
fi
grep -q '^shortcut_fe_cm ' /proc/modules
rm -f "$base/routing-installed" "$base/routing-started"
ip route flush cache
echo 'Returned routing and DNS to OEM; VPN remains separately managed.'
