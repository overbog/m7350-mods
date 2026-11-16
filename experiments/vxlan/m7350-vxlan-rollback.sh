#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# M7350 research shell. Reverses apply in order. Safe to run after any stage,
# including after a partial failure. RAM-only; a reboot clears everything anyway.
set -u
VX=${VX:-vxlan0}; BRIDGE=${BRIDGE:-bridge0}; PPP_IF=${PPP_IF:-ppp0}; WAN_IF=${WAN_IF:-rmnet_data0}; PORT=${PORT:-4789}; VTEP=${VTEP:-}
ip link set "$VX" nomaster 2>/dev/null || true
brctl delif "$BRIDGE" "$VX" 2>/dev/null || true
iptables -t mangle -D FORWARD -o "$VX" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1270 2>/dev/null || true
iptables -D FORWARD -m physdev --physdev-in wlan0 --physdev-out "$VX" -s 192.168.0.0/24 -j ACCEPT 2>/dev/null || true
iptables -D INPUT -i "$VX" -s 198.51.100.2/32 -d 198.51.100.1/32 -p icmp --icmp-type echo-request -j ACCEPT 2>/dev/null || true
ip link set "$VX" down 2>/dev/null || true
ip link del "$VX" 2>/dev/null || true
if ip link show dev "$VX" >/dev/null 2>&1; then
  echo "VXLAN interface still present; retaining route and firewall protection" >&2
  exit 1
fi
iptables -D FORWARD -j VXLAN_D4 2>/dev/null || true
iptables -F VXLAN_D4 2>/dev/null || true
iptables -X VXLAN_D4 2>/dev/null || true
ip6tables -D FORWARD -j VXLAN_D6 2>/dev/null || true
ip6tables -F VXLAN_D6 2>/dev/null || true
ip6tables -X VXLAN_D6 2>/dev/null || true
iptables -t mangle -D FORWARD -j VXLAN_DM 2>/dev/null || true
iptables -t mangle -F VXLAN_DM 2>/dev/null || true
iptables -t mangle -X VXLAN_DM 2>/dev/null || true
ebtables -D OUTPUT -o "$VX" -j DROP 2>/dev/null || true
ebtables -D INPUT -i "$VX" -j DROP 2>/dev/null || true
ebtables -D FORWARD -i "$VX" -j VXLAN_DE 2>/dev/null || true
ebtables -D FORWARD -o "$VX" -j VXLAN_DE 2>/dev/null || true
ebtables -F VXLAN_DE 2>/dev/null || true
ebtables -X VXLAN_DE 2>/dev/null || true
remove_module() {
  if [ -x /run/m7350-vxlan/remove_owned_module ]; then
    /run/m7350-vxlan/remove_owned_module "$1"
  else
    rmmod "$1"
  fi
}
if grep -q '^vxlan ' /proc/modules; then
  remove_module vxlan || true
fi
# prove the probe module is gone (Stage C review: the echo alone did not prove removal)
if lsmod | grep -q '^vxlan'; then
  VX_MOD="STILL LOADED"; ref=$(sed -n 's/^vxlan \([0-9]*\) \([0-9]*\).*/\2/p' /proc/modules 2>/dev/null)
  echo "WARN: vxlan still loaded (refcount=${ref:-?}); interface/bridge ref must drop before rmmod succeeds"
  exit 1
else
  VX_MOD="removed"
fi
if [ -s /tmp/vxlan-snap/lsmod ]; then
  for module in ip6_udp_tunnel udp_tunnel; do
    if ! grep -q "^$module " /tmp/vxlan-snap/lsmod &&
       grep -q "^$module " /proc/modules; then
      remove_module "$module" || exit 1
      if grep -q "^$module " /proc/modules; then
        echo "$module still loaded; retaining route and firewall protection" >&2
        exit 1
      fi
    fi
  done
fi
if [ -n "$VTEP" ]; then
  ip route del blackhole "$VTEP/32" metric 32760 2>/dev/null || true
  if [ "${PPP_PEER_ROUTE:-0}" != 1 ]; then
    ip route del "$VTEP/32" dev "$PPP_IF" metric 10 2>/dev/null || true
  fi
fi
iptables -D OUTPUT -j VXLAN_OUT 2>/dev/null || true
iptables -F VXLAN_OUT 2>/dev/null || true; iptables -X VXLAN_OUT 2>/dev/null || true
iptables -D INPUT -j VXLAN_IN 2>/dev/null || true
iptables -F VXLAN_IN 2>/dev/null || true; iptables -X VXLAN_IN 2>/dev/null || true
echo "rollback done; vxlan module: $VX_MOD"
echo "verify: bridge0 MTU 1500, HTTP 200, TCP23 refused, PPP session active"
echo "NOTE: this script cannot close the OEM port-trigger shell; operator must close it and confirm TCP23 refused"
