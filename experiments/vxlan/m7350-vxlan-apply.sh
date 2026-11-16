#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Run ONLY in the M7350 research shell, AFTER an explicit operator GO and after
# the peer stage-B diff has fixed the real addresses. RAM-only, fail-closed: any
# error stops and never opens LTE. Does NOT load modules by force, does NOT touch
# flash. Stage C (tunnel, no bridge) and stage D (bridge attach) are separate.
set -eu

: "${VTEP:?provide the peer IPv4 address}"
: "${PPP_ADDR:?provide the local PPP IPv4 address}"
: "${VNI:=7350}"
: "${PORT:=4789}"
: "${PPP_IF:=ppp0}"
: "${WAN_IF:=rmnet_data0}"
: "${BRIDGE:=bridge0}"
: "${VX:=vxlan0}"
: "${MTU:=1310}"
MOD=/usr/lib/modules/3.18.20/kernel/net
VXKO=${VXKO:?absolute path to the reviewed vxlan.ko staged in RAM}

snap() { d=/tmp/vxlan-snap; mkdir -p $d; lsmod>$d/lsmod; ip addr>$d/addr; ip route show table all>$d/routes; iptables-save>$d/ipt; brctl show>$d/br 2>/dev/null||true; echo "snapshot in $d"; }

stageC() {
  # Refuse stale or foreign objects before taking ownership of this trial.
  ip -4 addr show dev "$PPP_IF" | awk -v addr="$PPP_ADDR" '
    $1 == "inet" { split($2, parts, "/"); if (parts[1] == addr) found = 1 }
    END { exit !found }
  ' || { echo "stage C requires the pinned PPP address $PPP_ADDR on $PPP_IF" >&2; return 1; }
  if ip link show dev "$VX" >/dev/null 2>&1 ||
     grep -q '^vxlan ' /proc/modules ||
     iptables -S VXLAN_OUT >/dev/null 2>&1 ||
     iptables -S VXLAN_IN >/dev/null 2>&1; then
    echo "stage C objects already exist; inspect ownership before proceeding" >&2
    return 1
  fi
  existing_route=$(ip -4 route show table all exact "$VTEP/32")
  if [ "${PPP_PEER_ROUTE:-0}" = 1 ]; then
    # pppd already owns the negotiated peer's host route.
    ip -4 route get "$VTEP" | awk -v dev="$PPP_IF" '
        NR == 1 { for (i=1; i<NF; i++) if ($i == "dev" && $(i+1) == dev) ok=1 }
        END { exit !ok }' || { echo "negotiated peer is not routed through $PPP_IF" >&2; return 1; }
  elif [ -n "$existing_route" ]; then
    echo "a route for $VTEP/32 already exists; refusing to replace it" >&2
    return 1
  fi
  snap
  # modules: OEM udp_tunnel deps first, then the reviewed vxlan.ko, never forced
  lsmod | grep -q '^udp_tunnel'      || insmod $MOD/ipv4/udp_tunnel.ko
  lsmod | grep -q '^ip6_udp_tunnel'  || insmod $MOD/ipv6/ip6_udp_tunnel.ko
  lsmod | grep -q '^vxlan'           || insmod "$VXKO" udp_port=$PORT
  dmesg | tail -5
  # egress guard BEFORE the interface: outer VXLAN only to VTEP via ppp0; never on WAN
  # Stage C contract: accept outer VXLAN only out ppp0 to the VTEP, then DROP it
  # anywhere else (so a route change or reconnect can never leak UDP 4789 onto WAN/LTE).
  iptables -N VXLAN_OUT 2>/dev/null || true
  iptables -C VXLAN_OUT -p udp -s "$PPP_ADDR" -d "$VTEP" --dport $PORT -o "$PPP_IF" -j ACCEPT 2>/dev/null || iptables -A VXLAN_OUT -p udp -s "$PPP_ADDR" -d "$VTEP" --dport $PORT -o "$PPP_IF" -j ACCEPT
  iptables -C VXLAN_OUT -p udp -d "$VTEP" --dport $PORT -j DROP 2>/dev/null || iptables -A VXLAN_OUT -p udp -d "$VTEP" --dport $PORT -j DROP
  iptables -C OUTPUT -j VXLAN_OUT 2>/dev/null || iptables -I OUTPUT 1 -j VXLAN_OUT
  iptables -N VXLAN_IN 2>/dev/null || true
  iptables -C VXLAN_IN -i "$PPP_IF" -p udp --dport $PORT -s "$VTEP" -d "$PPP_ADDR" -j ACCEPT 2>/dev/null || iptables -A VXLAN_IN -i "$PPP_IF" -p udp --dport $PORT -s "$VTEP" -d "$PPP_ADDR" -j ACCEPT
  iptables -C VXLAN_IN -p udp --dport $PORT -j DROP 2>/dev/null || iptables -A VXLAN_IN -p udp --dport $PORT -j DROP
  iptables -C INPUT -j VXLAN_IN 2>/dev/null || iptables -I INPUT 1 -j VXLAN_IN
  # route: VTEP via ppp0 wins; blackhole at HIGHER metric catches it if ppp0 drops (the peer fix)
  ip route add blackhole "$VTEP/32" metric 32760
  if [ "${PPP_PEER_ROUTE:-0}" != 1 ]; then
    ip route add "$VTEP/32" dev "$PPP_IF" metric 10
  fi
  # interface, not yet bridged
  ip link add "$VX" type vxlan id "$VNI" local "$PPP_ADDR" dev "$PPP_IF" ttl 64
  # OEM ip lacks "remote". The all-zero FDB entry is the unicast flood peer.
  bridge fdb add 00:00:00:00:00:00 dev "$VX" dst "$VTEP"
  ip link set "$VX" mtu "$MTU" up
  echo "stage C up: $VX -> $VTEP via $PPP_IF (temp-IP ping + WAN leak check is the operator's go/no-go)"
}

stageD() {
  : "${PHONE4:?current phone IPv4}" "${PHONE6:?current phone link-local IPv6}"
  : "${PHONE_NS:?phone solicited-node multicast}" "${PHONE_MAC:?current phone MAC}"
  : "${MAC4:?dedicated Mac IPv4}" "${MAC6:?dedicated Mac link-local IPv6}"
  : "${MAC_NS:?Mac solicited-node multicast}" "${MAC_MAC:?dedicated Mac MAC}"
  if ip -4 addr show dev "$VX" | grep -q 'inet '; then
    echo "remove the C test IP before attaching VXLAN to the LAN" >&2
    return 1
  fi
  for name in VXLAN_D4 VXLAN_D6; do
    if iptables -S "$name" >/dev/null 2>&1 || ip6tables -S "$name" >/dev/null 2>&1; then
      echo "D chain already exists: $name" >&2
      return 1
    fi
  done
  if iptables -t mangle -S VXLAN_DM >/dev/null 2>&1 ||
     ebtables -L VXLAN_DE >/dev/null 2>&1; then
    echo "D mangle or Ethernet chain already exists" >&2
    return 1
  fi

  ebtables -N VXLAN_DE
  # Block DHCP even when it comes from an allowed endpoint.
  ebtables -A VXLAN_DE -p IPv4 --ip-proto udp --ip-sport 67:68 --ip-dport 67:68 -j DROP
  # The forwarding path permits only the two endpoint MACs and bridge ports.
  ebtables -A VXLAN_DE -i "$VX" -o wlan0 -s "$MAC_MAC" -j RETURN
  ebtables -A VXLAN_DE -i wlan0 -o "$VX" -s "$PHONE_MAC" -j RETURN
  ebtables -A VXLAN_DE -j DROP
  ebtables -I FORWARD 1 -i "$VX" -j VXLAN_DE
  ebtables -I FORWARD 1 -o "$VX" -j VXLAN_DE
  ebtables -I INPUT 1 -i "$VX" -j DROP
  # The trial only forwards between the phone and Mac. Block locally
  # generated frames, including offers from the OEM DHCP server.
  ebtables -I OUTPUT 1 -o "$VX" -j DROP

  iptables -N VXLAN_D4
  ip6tables -N VXLAN_D6
  iptables -t mangle -N VXLAN_DM
  vxlan_direction "$VX" wlan0 "$MAC4" "$PHONE4" "$MAC6" "$PHONE6" "$PHONE_NS"
  vxlan_direction wlan0 "$VX" "$PHONE4" "$MAC4" "$PHONE6" "$MAC6" "$MAC_NS"
  iptables -I FORWARD 1 -j VXLAN_D4
  ip6tables -I FORWARD 1 -j VXLAN_D6
  iptables -t mangle -I FORWARD 1 -j VXLAN_DM

  brctl addif "$BRIDGE" "$VX"
  echo "stage D attached: verify ARP, ND, mDNS and the existing VPN"
}

vxlan_direction() {
  in=$1 out=$2 src4=$3 dst4=$4 src6=$5 dst6=$6 ns6=$7
  set -- -i "$BRIDGE" -o "$BRIDGE" -m physdev --physdev-is-bridged --physdev-in "$in" --physdev-out "$out"
  iptables -A VXLAN_D4 "$@" -s "$src4/32" -d "$dst4/32" -j ACCEPT
  iptables -A VXLAN_D4 "$@" -s "$src4/32" -d 224.0.0.251/32 -p udp --sport 5353 --dport 5353 -j ACCEPT
  # Clamp only the trial pair and bypass the OEM blanket TTL increment.
  iptables -t mangle -A VXLAN_DM "$@" -s "$src4/32" -d "$dst4/32" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1270
  iptables -t mangle -A VXLAN_DM "$@" -s "$src4/32" -d "$dst4/32" -j ACCEPT
  iptables -t mangle -A VXLAN_DM "$@" -s "$src4/32" -d 224.0.0.251/32 -p udp --sport 5353 --dport 5353 -j ACCEPT
  ip6tables -A VXLAN_D6 "$@" -s "$src6/128" -d "$dst6/128" -j ACCEPT
  ip6tables -A VXLAN_D6 "$@" -s "$src6/128" -d "$ns6/128" -p ipv6-icmp --icmpv6-type 135 -j ACCEPT
  ip6tables -A VXLAN_D6 "$@" -s "$src6/128" -d ff02::fb/128 -p udp --sport 5353 --dport 5353 -j ACCEPT
}

case "${1:-}" in
  C) stageC ;;
  D) stageD ;;
  *) echo "usage: VTEP=.. PPP_ADDR=.. VXKO=.. $0 {C|D}"; exit 2 ;;
esac
