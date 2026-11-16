#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Tunnel 2: VXLAN over tunnel 1 (stage C). Research scripts unchanged.
set -u
. "$(dirname "$0")/../lib/home-common.sh"

if [ "$VPN_L2" = 0 ]; then
    case "${1:-}" in start|stop|check) exit 0;; esac
fi
case "${1:-}" in
start)
    verified ko/vxlan.ko || exit 1
    endpoints=$(ppp_vxlan_endpoints) || { say "ppp0 has no usable negotiated IPv4 pair"; exit 1; }
    printf '%s\n' "$endpoints" > "$RUN/vxlan-ppp-endpoints" || exit 1
    PPP_PEER_ROUTE=1 VTEP=${endpoints#* } PORT=$VPN_PORT VNI=$VPN_VNI PPP_ADDR=${endpoints% *} \
        VXKO=$KO/vxlan.ko sh "$RESEARCH/m7350-vxlan-apply.sh" C >&2
    ;;
stop)
    # The rollback uses this non-forcing helper when present (OEM rmmod can
    # report false success).
    mkdir -p /run/m7350-vxlan
    ln -sf "$BIN/remove_owned_module" /run/m7350-vxlan/remove_owned_module
    peer_route=0
    if [ -s "$RUN/vxlan-ppp-endpoints" ]; then
        read -r local_ip VTEP < "$RUN/vxlan-ppp-endpoints" || exit 1
        vpn_ipv4 "$VTEP" || exit 1
        peer_route=1
    fi
    PPP_PEER_ROUTE=$peer_route VTEP=$VTEP PORT=$VPN_PORT VNI=$VPN_VNI \
        sh "$RESEARCH/m7350-vxlan-rollback.sh" >&2; rc=$?
    rm -rf /run/m7350-vxlan
    [ "$rc" != 0 ] || rm -f "$RUN/vxlan-ppp-endpoints" "$RUN/vxlan-ppp-ipv4" || rc=1
    exit $rc
    ;;
check)
    endpoints=$(ppp_vxlan_endpoints) || exit 1
    [ "$endpoints" = "$(cat "$RUN/vxlan-ppp-endpoints" 2>/dev/null)" ] &&
        [ -e /sys/class/net/vxlan0 ] && iptables -C OUTPUT -j VXLAN_OUT 2>/dev/null
    ;;
absent)
    [ ! -e /sys/class/net/vxlan0 ] && ! mod_loaded vxlan && ! iptables -S VXLAN_OUT >/dev/null 2>&1
    ;;
*) exit 2 ;;
esac
