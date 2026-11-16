#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# SSID 1 / bridge0 clients routed through tunnel 1, with DNS proxy and
# fail-closed guards. Uses the research apply/rollback scripts unchanged.
set -u
. "$(dirname "$0")/../lib/home-common.sh"

start_dns() {
    sed "s/@VPN_DNS_IPV4@/$1/" "$RESEARCH/dnsmasq-vpn.conf.example" > "$VPN/dnsmasq-vpn.conf" || return 1
    dnsmasq --no-daemon --conf-file="$VPN/dnsmasq-vpn.conf" > "$VPN/dnsmasq-vpn.out" 2>&1 &
    echo $! > "$VPN/owned-dnsmasq.pid"
    sleep 1
    alive_owned "$VPN/owned-dnsmasq.pid" "dnsmasq-vpn.conf"
}

case "${1:-}" in
start)
    [ -d "$VPN" ] || { say "tunnel 1 runtime missing"; exit 1; }
    tries=0
    until dns_ip=$(vpn_dns_ipv4); do
        if [ "$tries" -ge 5 ]; then
            logger -p daemon.err -t m7350-vpn -- "PPP did not supply usable DNS. Set a DNS override." 2>/dev/null || :
            exit 1
        fi
        tries=$((tries+1))
        sleep 1
    done
    mss=$(ppp_tcp_mss) || exit 1
    cat > "$VPN/routing.env" <<CONF
VPN_SERVER=$VPN_SERVER
VPN_DNS=$dns_ip
LAN_NET=192.168.0.0/24
LAN_ADDR=192.168.0.1
LAN_IF=bridge0
PPP_IF=ppp0
TABLE=735
DNS_RULE=10734
LAN_RULE=10735
BLOCK_PRIO=2147483000
TUNNEL_OWNS_ESP_GUARD=1
VPN_MSS=$mss
CONF
    sh "$RESEARCH/apply-routing.sh" >&2 || { say "apply-routing failed (guards stay closed)"; exit 1; }
    printf '%s\n' "$mss" > "$VPN/active-mss" || exit 1
    start_dns "$dns_ip" || { say "DNS proxy did not start"; exit 1; }
    ;;
refresh)
    [ -e "$VPN/routing-installed" ] || exit 1
    if mss=$(ppp_tcp_mss) && [ "$mss" != "$(cat "$VPN/active-mss" 2>/dev/null)" ]; then
        iptables -t mangle -R M7350_MSS 1 -i bridge0 -o ppp0 -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss "$mss" &&
            iptables -t mangle -R M7350_MSS 2 -i ppp0 -o bridge0 -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss "$mss" &&
            printf '%s\n' "$mss" > "$VPN/active-mss" || return_code=1
    fi
    old_dns=$(vpn_value "$VPN/routing.env" VPN_DNS)
    vpn_ipv4 "$old_dns" || exit 1
    if ! dns_ip=$(vpn_dns_ipv4); then
        kill_owned "$VPN/owned-dnsmasq.pid" "dnsmasq-vpn.conf"
        exit $?
    fi
    if [ "$dns_ip" != "$old_dns" ]; then
        sed "s/^VPN_DNS=.*/VPN_DNS=$dns_ip/" "$VPN/routing.env" > "$VPN/routing.env.new" || exit 1
        ip rule add priority 10734 to "$dns_ip/32" table 735 || exit 1
        if ! mv -f "$VPN/routing.env.new" "$VPN/routing.env"; then
            ip rule del priority 10734 to "$dns_ip/32" table 735
            exit 1
        fi
        ip rule del priority 10734 to "$old_dns/32" table 735 || say "could not remove old DNS rule"
        ip route flush cache
    fi
    if ! grep -Fxq "server=$dns_ip" "$VPN/dnsmasq-vpn.conf" ||
        ! alive_owned "$VPN/owned-dnsmasq.pid" "dnsmasq-vpn.conf"; then
        kill_owned "$VPN/owned-dnsmasq.pid" "dnsmasq-vpn.conf" &&
            start_dns "$dns_ip" || exit 1
    fi
    exit "${return_code:-0}"
    ;;
stop)
    [ -e "$VPN/routing-started" ] || { kill_owned "$VPN/owned-dnsmasq.pid" "dnsmasq-vpn.conf"; exit 0; }
    sh "$RESEARCH/rollback-routing.sh" >&2 || exit 1
    ;;
check)
    [ -e "$VPN/routing-installed" ] && alive_owned "$VPN/owned-dnsmasq.pid" "dnsmasq-vpn.conf"
    ;;
absent)
    ! iptables -nL M7350_VPN4 >/dev/null 2>&1 && ! ip rule | grep -q '^10735:'
    ;;
*) exit 2 ;;
esac
