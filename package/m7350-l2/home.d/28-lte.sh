#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Direct LTE for bridge3. Keep the VPN bridge's routes and DNS separate.
set -u
. "$(dirname "$0")/../lib/home-common.sh"
bridge=bridge3
network=192.168.4.0/24
gateway=192.168.4.1
wan=rmnet_data0
owned=$RUN/lte-bridge
conf=$RUN/dnsmasq-lte.conf
pid=$RUN/owned-lte-dhcp.pid

remove_chain() {
    command=$1 table=$2 hook=$3 chain=$4
    "$command" -t "$table" -nL "$chain" >/dev/null 2>&1 || return 0
    "$command" -t "$table" -D "$hook" -j "$chain" 2>/dev/null || :
    "$command" -t "$table" -F "$chain" && "$command" -t "$table" -X "$chain"
}

case "${1:-}" in
start)
    set -e
    [ ! -e "$owned" ] && [ ! -e "/sys/class/net/$bridge" ] || exit 1
    [ -z "$(ip -4 route show exact "$network")" ] || exit 1
    ! iptables -nL M7350_LTE >/dev/null 2>&1 || exit 1
    ! iptables -nL M7350_LTE_IN >/dev/null 2>&1 || exit 1
    ! iptables -t nat -nL M7350_LTE_NAT >/dev/null 2>&1 || exit 1
    ! ip6tables -nL M7350_LTE6 >/dev/null 2>&1 || exit 1
    mkdir -p "$RUN"
    touch "$owned"
    brctl addbr "$bridge"
    ip addr add "$gateway/24" dev "$bridge"
    iptables -N M7350_LTE
    iptables -A M7350_LTE -i "$bridge" -s "$network" -o "$wan" -j ACCEPT
    iptables -A M7350_LTE -i "$wan" -o "$bridge" -d "$network" -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -A M7350_LTE -i "$bridge" -j DROP
    iptables -A M7350_LTE -o "$bridge" -j DROP
    iptables -I FORWARD 1 -j M7350_LTE
    iptables -N M7350_LTE_IN
    iptables -A M7350_LTE_IN -i "$bridge" -p udp --sport 68 --dport 67 -j ACCEPT
    iptables -A M7350_LTE_IN -i "$bridge" -s "$network" -d "$gateway" -p tcp --dport 80 -j ACCEPT
    iptables -I INPUT 1 -j M7350_LTE_IN
    iptables -t nat -N M7350_LTE_NAT
    iptables -t nat -A M7350_LTE_NAT -s "$network" -o "$wan" -j MASQUERADE
    iptables -t nat -I POSTROUTING 1 -j M7350_LTE_NAT
    ip6tables -N M7350_LTE6
    ip6tables -A M7350_LTE6 -i "$bridge" -j DROP
    ip6tables -A M7350_LTE6 -o "$bridge" -j DROP
    ip6tables -I FORWARD 1 -j M7350_LTE6
    ip link set "$bridge" up
    cat > "$conf" <<CONF
port=0
interface=$bridge
bind-interfaces
dhcp-range=192.168.4.50,192.168.4.199,255.255.255.0,1h
dhcp-option=option:dns-server,1.1.1.1,9.9.9.9
dhcp-leasefile=$RUN/lte.leases
CONF
    dnsmasq --no-daemon --conf-file="$conf" > "$RUN/dnsmasq-lte.log" 2>&1 &
    echo $! > "$pid"
    sleep 1
    alive_owned "$pid" "$conf"
    ;;
stop)
    [ -e "$owned" ] || exit 0
    rc=0
    kill_owned "$pid" "$conf" || rc=1
    if [ -e "/sys/class/net/$bridge" ]; then
        ip link set "$bridge" down && brctl delbr "$bridge" || exit 1
    fi
    remove_chain iptables filter FORWARD M7350_LTE || rc=1
    remove_chain iptables filter INPUT M7350_LTE_IN || rc=1
    remove_chain iptables nat POSTROUTING M7350_LTE_NAT || rc=1
    remove_chain ip6tables filter FORWARD M7350_LTE6 || rc=1
    [ "$rc" -ne 0 ] || rm -f "$owned" "$conf" "$RUN/lte.leases"
    exit "$rc"
    ;;
check)
    [ -e "$owned" ] && [ -e "/sys/class/net/$bridge" ] && alive_owned "$pid" "$conf"
    ;;
absent) [ ! -e "$owned" ] ;;
*) exit 2 ;;
esac
