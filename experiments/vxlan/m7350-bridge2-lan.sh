#!/bin/sh
# Run on M7350 after stage C and the peer LAN-side handoff. All state is in RAM.
set -eu

state=/run/m7350-bridge2-lan
bridge=bridge2
vap=wlan0-va0
vx=vxlan0
chain=M7350_BRIDGE2
vtep=${VTEP:-}
ppp_addr=${PPP_ADDR:-}
port=${PORT:-4789}
usb_bridge=${USB_BRIDGE:-bridge0}

is_member() {
    test -e "/sys/class/net/$bridge/brif/$1"
}

detach() {
    test -d "$state" || return 0
    if is_member "$vx"; then
        brctl delif "$bridge" "$vx" || return 1
    fi
    if is_member "$vx"; then
        echo "VXLAN remains attached. Retaining firewall rules." >&2
        return 1
    fi
    # Insertions are recorded only after success. Keep the journal on failure.
    for tool in iptables ip6tables; do
        for table in filter mangle; do
            if test -f "$state/$tool.$table"; then
                if "$tool" -t "$table" -C FORWARD -j "$chain" 2>/dev/null; then
                    "$tool" -t "$table" -D FORWARD -j "$chain" || return 1
                fi
                "$tool" -t "$table" -F "$chain" || return 1
                "$tool" -t "$table" -X "$chain" || return 1
                unlink "$state/$tool.$table" || return 1
            fi
        done
    done
    for hook in INPUT OUTPUT; do
        for iface in "$vap" "$vx" rndis0; do
            marker="$state/ebtables.$hook.$iface"
            if test -f "$marker"; then
                flag=-i
                if test "$hook" = OUTPUT; then flag=-o; fi
                ebtables -D "$hook" "$flag" "$iface" -j DROP || return 1
                unlink "$marker" || return 1
            fi
        done
    done
    rmdir "$state"
}

add_pair_rules() {
    tool=$1 table=$2
    "$tool" -t "$table" -N "$chain"
    : > "$state/$tool.$table"
    for incoming in $client_ports "$vx"; do
      for outgoing in $client_ports "$vx"; do
        test "$incoming" != "$outgoing" || continue
        set -- -i "$bridge" -o "$bridge" -m physdev --physdev-is-bridged \
            --physdev-in "$incoming" --physdev-out "$outgoing"
        if test "$table" = mangle && { test "$incoming" = "$vx" || test "$outgoing" = "$vx"; }; then
            mss=1270
            if test "$tool" = ip6tables; then mss=1250; fi
            "$tool" -t "$table" -A "$chain" "$@" -p tcp --tcp-flags SYN,RST SYN \
                -j TCPMSS --set-mss "$mss"
        fi
        "$tool" -t "$table" -A "$chain" "$@" -j ACCEPT
      done
    done
    "$tool" -t "$table" -I FORWARD 1 -j "$chain"
}

attach() {
    : "${IPSEC_PEER:?set the verified remote IPsec endpoint}"
    test ! -e "$state"
    client_ports=$vap
    expected_l2=$vap
    expected_l3=wlan0
    expected_active_l2=$(printf '%s\n' "$vx" "$vap")
    case "$usb_bridge" in
        bridge0) expected_l3=$(printf 'rndis0\nwlan0') ;;
        bridge2)
            client_ports="rndis0 $vap"
            expected_l2=$(printf 'rndis0\n%s' "$vap")
            expected_active_l2=$(printf 'rndis0\n%s\n%s' "$vx" "$vap")
            ;;
        bridge3) test -e /sys/class/net/bridge3/brif/rndis0 ;;
        *) return 1 ;;
    esac
    test "$(ls "/sys/class/net/$bridge/brif")" = "$expected_l2" || {
        echo "Unexpected ports on bridge2 before VXLAN attach." >&2
        return 1
    }
    # OEM can also keep the ECM USB function in bridge0 without a host.
    # Both USB functions belong on the same bridge when USB is set to L3.
    l3_ports=$(ls /sys/class/net/bridge0/brif)
    if test "$usb_bridge" = bridge0; then
        l3_ports=$(printf '%s\n' "$l3_ports" | sed '/^ecm0$/d')
    fi
    test "$l3_ports" = "$expected_l3" || {
        echo "Unexpected ports on bridge0 before VXLAN attach: $(printf '%s' "$l3_ports" | tr '\n' ' ')." >&2
        return 1
    }
    test ! -e "/sys/class/net/$vx/master"
    test -z "$(ip -o addr show dev "$bridge" scope global)"
    test -z "$(ip -o addr show dev "$vx" scope global)"
    test "$(cat "/sys/class/net/$vx/mtu")" = 1310
    test "$(cat "/sys/class/net/$vap/brport/state")" = 3 || {
        echo "The L2 Wi-Fi port is not forwarding." >&2
        return 1
    }
    if grep -q '^shortcut_fe_cm ' /proc/modules; then
        echo "Pause the OEM shortcut manager before attaching VXLAN." >&2
        return 1
    fi
    ip -4 addr show dev ppp0 | grep -F "inet $ppp_addr "
    ip -4 route get "$vtep" | grep -F 'dev ppp0'
    ip -4 route show table all exact "$vtep/32" | grep -F 'blackhole '
    ip xfrm state | awk -v peer="$IPSEC_PEER" '
        /^src / { direction = ($2 == peer ? "in" : ($4 == peer ? "out" : "")) }
        /^[[:space:]]*proto esp / && direction != "" { seen[direction] = 1 }
        END { exit !(seen["in"] && seen["out"]) }
    '
    ip xfrm policy | awk -v peer="$IPSEC_PEER/32" '
        /^src / { fallback = ($2 == "0.0.0.0/0" && $4 == peer &&
                             $5 == "proto" && $6 == "udp" &&
                             $7 == "dport" && $8 == "1701") }
        /^[[:space:]]*dir out action block / && fallback { found = 1 }
        END { exit !found }
    '
    iptables -C OUTPUT -j VXLAN_OUT
    iptables -C INPUT -j VXLAN_IN
    iptables -C VXLAN_OUT -p udp -s "$ppp_addr" -d "$vtep" --dport "$port" -o ppp0 -j ACCEPT
    iptables -C VXLAN_OUT -p udp -d "$vtep" --dport "$port" -j DROP
    iptables -C VXLAN_IN -i ppp0 -p udp --dport "$port" -s "$vtep" -d "$ppp_addr" -j ACCEPT
    iptables -C VXLAN_IN -p udp --dport "$port" -j DROP

    umask 077
    mkdir "$state"
    trap 'detach' EXIT
    trap 'exit 130' HUP INT TERM
    # Block local router traffic on these ports. Bridged DHCP can still cross.
    for hook in INPUT OUTPUT; do
        for iface in $client_ports "$vx"; do
            flag=-i
            if test "$hook" = OUTPUT; then flag=-o; fi
            ebtables -I "$hook" 1 "$flag" "$iface" -j DROP
            : > "$state/ebtables.$hook.$iface"
        done
    done
    for tool in iptables ip6tables; do
        add_pair_rules "$tool" filter
        add_pair_rules "$tool" mangle
    done
    brctl addif "$bridge" "$vx"
    test "$(ls "/sys/class/net/$bridge/brif")" = "$expected_active_l2"
    trap - EXIT HUP INT TERM
    brctl show
}

case "${1:-}" in
    attach) : "${vtep:?provide the peer IPv4 address}" "${ppp_addr:?provide the local PPP IPv4 address}"; attach ;;
    detach) detach ;;
    *) echo "Usage: IPSEC_PEER=<peer-address> $0 {attach|detach}" >&2; exit 2 ;;
esac
