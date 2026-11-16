#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Explicit RAM-only experiment. Failure leaves guards in place, never opens LTE.
set -eu
base=/run/m7350-vpn
. "$base/routing.env"
test ! -e "$base/routing-started"
test -z "$(ip route show table "$TABLE")"
! ip rule | grep -q "^$DNS_RULE:"
! ip rule | grep -q "^$LAN_RULE:"
for chain in M7350_VPN4 M7350_OUT; do
 ! iptables -nL "$chain" >/dev/null 2>&1
done
test -f /lib/modules/3.18.20/extra/shortcut-fe-cm.ko
date -u > "$base/routing-started"
iptables-save > "$base/iptables-before-routing"
ip6tables-save > "$base/ip6tables-before-routing"
ip rule > "$base/rules-before-routing"
ip xfrm policy > "$base/policies-before-routing"

iptables -N M7350_VPN4
iptables -A M7350_VPN4 -i "$LAN_IF" ! -s "$LAN_NET" -j DROP
iptables -A M7350_VPN4 -i "$LAN_IF" -s "$LAN_NET" -o "$PPP_IF" -j ACCEPT
iptables -A M7350_VPN4 -i "$LAN_IF" -j DROP
iptables -A M7350_VPN4 -i "$PPP_IF" -o "$LAN_IF" -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A M7350_VPN4 -j RETURN
iptables -I FORWARD 1 -j M7350_VPN4
ip6tables -N M7350_VPN6
ip6tables -A M7350_VPN6 -i "$LAN_IF" -j DROP
ip6tables -A M7350_VPN6 -o "$LAN_IF" -j DROP
ip6tables -I FORWARD 1 -j M7350_VPN6
ip6tables -N M7350_DNS6
for proto in udp tcp; do
 ip6tables -A M7350_DNS6 -i "$LAN_IF" -p "$proto" --dport 53 -j DROP
 ip6tables -I OUTPUT 1 ! -o lo -p "$proto" --dport 53 -j DROP
done
ip6tables -I INPUT 1 -j M7350_DNS6

# Pause the connection manager so old/offloaded LTE flows cannot bypass guards.
cp /lib/modules/3.18.20/extra/shortcut-fe-cm.ko "$base/saved-shortcut-fe-cm.ko"
"$base/pause_oem_offload"
! grep -q '^shortcut_fe_cm ' /proc/modules

# Independent terminal policies: no table fall-through and no plaintext L2TP.
ip route add blackhole default metric 32760 table "$TABLE"
ip route add default dev "$PPP_IF" metric 10 table "$TABLE"
ip rule add priority "$DNS_RULE" to "$VPN_DNS/32" table "$TABLE"
ip rule add priority "$LAN_RULE" iif "$LAN_IF" table "$TABLE"
if [ "${TUNNEL_OWNS_ESP_GUARD:-0}" != 1 ]; then
    ip xfrm policy add dir out dst "$VPN_SERVER/32" proto udp dport 1701 action block priority "$BLOCK_PRIO"
fi

iptables -N M7350_OUT
iptables -A M7350_OUT -o lo -j RETURN
for proto in udp tcp; do
 iptables -A M7350_OUT ! -o "$PPP_IF" -p "$proto" --dport 53 -j DROP
done
iptables -I OUTPUT 1 -j M7350_OUT
iptables -t nat -N M7350_DNS
for proto in udp tcp; do
 iptables -t nat -A M7350_DNS -i "$LAN_IF" -s "$LAN_NET" -p "$proto" --dport 53 -j REDIRECT --to-ports 1053
done
iptables -t nat -I PREROUTING 1 -j M7350_DNS
iptables -t nat -N M7350_NAT
iptables -t nat -A M7350_NAT -s "$LAN_NET" -o "$PPP_IF" -j MASQUERADE
iptables -t nat -I POSTROUTING 1 -j M7350_NAT
iptables -t mangle -N M7350_MSS
iptables -t mangle -A M7350_MSS -i "$LAN_IF" -o "$PPP_IF" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss "${VPN_MSS:-1320}"
iptables -t mangle -A M7350_MSS -i "$PPP_IF" -o "$LAN_IF" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss "${VPN_MSS:-1320}"
iptables -t mangle -I FORWARD 1 -j M7350_MSS
ip route flush cache
date -u > "$base/routing-installed"
echo 'Routing guards installed; start the dedicated DNS proxy next.'
