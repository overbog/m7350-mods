#!/bin/sh
# Tunnel 1: L2TP/IPsec to the configured VPN server (strongSwan + xl2tpd + pppd), routed.
set -u
. "$(dirname "$0")/../lib/home-common.sh"
. "$BASE/lib/failure.sh"
vici="unix://$VPN/charon.vici"
pinned=$RUN/tunnel1-pinned-route
guard=$RUN/tunnel1-esp-guard
owned=$RUN/tunnel1-owned

start_error() {
    record_start_error "$1: $2" || :
    say "$1: $2"
    exit 1
}

initiate_ike() {
    (umask 077; "$VPN/swanctl" --initiate --child l2tp --timeout 18 --uri "$vici" > "$VPN/swanctl-initiate.log" 2>&1)
}

# Retry Quick Mode once with a fresh IKE SA if the peer's DH public value
# was rejected. Keep the configured proposals, PFS and cleartext guard.
initiate_ike_recover() {
    local termination
    rm -f "$VPN/swanctl-phase2-first.log"
    initiate_ike && return 0
    grep -q 'IKE_SA .* established' "$VPN/swanctl-initiate.log" &&
        grep -q 'unable to apply received KE value' "$VPN/swanctl-initiate.log" ||
        return 1
    (umask 077; cp "$VPN/swanctl-initiate.log" "$VPN/swanctl-phase2-first.log") || return 1
    termination=$("$VPN/swanctl" --terminate --ike m7350-l2tp --timeout 5 --uri "$vici" 2>&1) ||
        [ "$termination" = "terminate failed: no matching SAs to terminate found" ] || return 1
    logger -p daemon.notice -t m7350-vpn -- 'Retrying phase 2 key exchange with a fresh IKE SA' 2>/dev/null || :
    initiate_ike
}

ike_failure() {
    local reason
    # VICI and charon can print either the long notify name or its short name.
    # Emit only fixed diagnostic text, never an arbitrary peer log line.
    reason=$(cat "$VPN/swanctl-initiate.log" 2>/dev/null |
        awk '
            /received|parsed/ && /NO_PROPOSAL_CHOSEN|N\(NO_PROP\)/ { notify="proposal" }
            /received|parsed/ && /AUTHENTICATION_FAILED|N\(AUTH_FAILED\)/ { notify="auth" }
            /received|parsed/ && /INVALID_ID_INFORMATION|N\(INV_ID\)/ { notify="id" }
            /received|parsed/ && /TS_UNACCEPTABLE|N\(TS_UNACCEPT\)/ { notify="selectors" }
            /invalid HASH|HASH verification failed|decryption failed/ { auth=1 }
            /parsed ID_PROT response/ && /\[ SA[[:space:]]/ { answered=1 }
            /parsed ID_PROT response/ && /\[ KE[[:space:]]/ { answered=1; key_exchange=1 }
            /parsed ID_PROT response/ && /\[ ID HASH[[:space:]]/ { authenticated=1 }
            /generating ID_PROT request/ && /\[ ID HASH[[:space:]]/ { sent_auth=1 }
            /IKE_SA .* established/ { authenticated=1 }
            /unable to apply received KE value/ && authenticated { quick_mode_ke=1 }
            /received packet: from|parsed .* response/ { answered=1 }
            /retransmit|timed out|timeout|peer not responding|no response|not established after [0-9]+ms/ { timedout=1 }
            END {
                if (notify=="proposal") print "VPN server rejected the proposal (NO_PROPOSAL_CHOSEN)"
                else if (notify=="auth") print "VPN server rejected authentication (AUTHENTICATION_FAILED)"
                else if (notify=="id") print "VPN server rejected the identity (INVALID_ID_INFORMATION)"
                else if (notify=="selectors") print "VPN server rejected traffic selectors (TS_UNACCEPTABLE)"
                else if (quick_mode_ke) print "phase 2 Diffie-Hellman public value was rejected"
                else if (auth) print "authentication verification failed; check the pre-shared key"
                else if (timedout && key_exchange && sent_auth && !authenticated)
                    print "server answered the key exchange but did not confirm authentication; check the pre-shared key"
                else if (timedout && answered) print "IKE negotiation timed out after the VPN server replied"
                else if (timedout) print "initial-timeout"
                else print "swanctl could not establish the IKE/ESP security association"
            }')
    if [ "$reason" = initial-timeout ]; then
        if ping -q -I rmnet_data0 -c 1 -W 2 -w 3 "$VPN_SERVER" >/dev/null 2>&1; then
            reason="server reachable but did not answer the IKE offer; check the IKE/ESP proposals and the PSK"
        else
            reason="no response from VPN server; check reachability"
        fi
    fi
    start_error IKE "$reason"
}

stage_runtime() {
    src=$1
    umask 077
    mkdir -p "$VPN/etc/swanctl" "$VPN/etc/ppp" || return 1
    for b in charon swanctl xl2tpd pppd pause_oem_offload remove_owned_module; do
        verified "bin/$b" || start_error Setup "$b is missing or failed integrity verification"
        ln -sf "$BIN/$b" "$VPN/$b" || start_error Setup "could not stage $b"
    done
    psk=${VPN_PSK:-}; pass=${VPN_PASS:-}; user=${VPN_USER:-}
    if [ ! -f "$RUN/vpn-profile.conf" ]; then
        psk=$(cat "$SECRETS/ipsec.psk") || start_error Setup "IPsec credential file is unavailable"
        pass=$(cat "$SECRETS/ppp.password") || start_error Setup "PPP credential file is unavailable"
        user=$(cat "$SECRETS/ppp.user") || start_error Setup "PPP account file is unavailable"
    fi
    case "$VPN_AUTH" in
        pap) refuse_pap=no; require_chap=no; refuse=refuse-chap ;;
        chap) refuse_pap=yes; require_chap=yes; refuse=refuse-pap ;;
        *) start_error PPP "unsupported authentication method; select PAP or CHAP" ;;
    esac
    cat > "$VPN/etc/strongswan.conf" <<CONF || return 1
charon {
 install_routes = no
 threads = 12
 filelog {
  router {
   path = $VPN/charon.log
   default = 1
   flush_line = yes
  }
 }
 plugins {
  vici { socket = $vici }
 }
}
swanctl { socket = $vici }
CONF
    cat > "$VPN/etc/swanctl/swanctl.conf" <<CONF || return 1
connections {
 m7350-l2tp {
  version = 1
  local_addrs = $src
  remote_addrs = $VPN_SERVER
  proposals = $VPN_IKE
  encap = yes
  dpd_delay = 30s
  local { auth = psk }
  remote { auth = psk }
  children {
   l2tp {
    mode = transport
    local_ts = dynamic[17/1701]
    remote_ts = $VPN_SERVER[17/1701]
    esp_proposals = $VPN_ESP
    life_time = 30m
    rekey_time = 25m
    start_action = none
   }
  }
 }
}
secrets {
 ike-m7350 { secret = $psk }
}
CONF
    cat > "$VPN/xl2tpd.conf" <<CONF || return 1
[global]
port = 1701
listen-addr = $src
access control = yes
[lac m7350]
lns = $VPN_SERVER
require authentication = no
refuse pap = $refuse_pap
require chap = $require_chap
pppoptfile = $VPN/ppp-options
ppp debug = no
autodial = no
redial = no
CONF
    peer_dns=
    [ -n "$VPN_DNS" ] || peer_dns=usepeerdns
    cat > "$VPN/ppp-options" <<CONF || return 1
noauth
unit 0
noipdefault
nodefaultroute
$peer_dns
noccp
nobsdcomp
nodeflate
noaccomp
nopcomp
mtu ${VPN_MTU:-1360}
mru ${VPN_MTU:-1360}
ipparam m7350-vpn
name $user
password "$pass"
$refuse
refuse-eap
logfile $VPN/pppd.log
CONF
    unset psk pass
    cp "$RESEARCH/ppp-ip-up" "$VPN/etc/ppp/ip-up" || return 1
    cp "$RESEARCH/ppp-ip-down" "$VPN/etc/ppp/ip-down" || return 1
    chmod 700 "$VPN/etc/ppp/ip-up" "$VPN/etc/ppp/ip-down"
}

case "${1:-}" in
start)
    [ -n "$VPN_SERVER" ] || start_error Setup "VPN server is not configured"
    [ ! -e "$VPN" ] || start_error Setup "another session owns the VPN runtime"
    ip link show dev ppp0 >/dev/null 2>&1 && start_error PPP "ppp0 already exists"
    src=$(lte_src)
    case "$src" in ''|*[!0-9.]*) start_error LTE "no source IPv4 address";; esac
    mkdir -p "$RUN" && touch "$owned" || start_error Setup "could not reserve the VPN runtime"
    stage_runtime "$src" || start_error Setup "could not prepare the VPN configuration and PPP hooks"
    # Pin the outer endpoint to LTE so PPP never captures its own transport.
    if ! ip -4 route show exact "$VPN_SERVER/32" | grep -q .; then
        ip route add "$VPN_SERVER/32" dev rmnet_data0 && echo "$VPN_SERVER/32 dev rmnet_data0" > "$pinned" || start_error LTE "could not pin endpoint route to LTE"
    fi
    ip xfrm policy add dir out dst "$VPN_SERVER/32" proto udp dport 1701 action block priority 2147482999 || start_error IPsec "could not install cleartext L2TP block"
    touch "$guard" || { ip xfrm policy delete dir out dst "$VPN_SERVER/32" proto udp dport 1701; start_error IPsec "could not record ownership of the L2TP block"; }
    STRONGSWAN_CONF=$VPN/etc/strongswan.conf "$VPN/charon" > "$VPN/charon.out" 2>&1 &
    echo $! > "$VPN/charon.pid"
    i=0
    until "$VPN/swanctl" --stats --uri "$vici" >/dev/null 2>&1; do
        alive_owned "$VPN/charon.pid" "$VPN/charon" || start_error IKE "charon exited before VICI became ready"
        [ "$i" -lt 20 ] || start_error IKE "charon VICI did not become ready"
        i=$((i+1))
        sleep 1
    done
    "$VPN/swanctl" --load-all --file "$VPN/etc/swanctl/swanctl.conf" --uri "$vici" >/dev/null ||
        start_error IKE "strongSwan could not load the profile over VICI"
    initiate_ike_recover || ike_failure
    esp_ready || start_error ESP "security associations were not installed in both directions"
    "$VPN/xl2tpd" -D -c "$VPN/xl2tpd.conf" -C "$VPN/l2tp-control" -p "$VPN/xl2tpd.pid" > "$VPN/xl2tpd.log" 2>&1 &
    i=0; while [ ! -p "$VPN/l2tp-control" ] && [ "$i" -lt 10 ]; do i=$((i+1)); sleep 1; done
    [ -p "$VPN/l2tp-control" ] || start_error L2TP "xl2tpd did not open its control FIFO"
    timeout -t 4 sh -c 'printf "c m7350\n" > "$1"' sh "$VPN/l2tp-control" || start_error L2TP "could not send the connect request"
    i=0; while ! ppp_up && [ "$i" -lt 20 ]; do i=$((i+1)); sleep 1; done
    if ! ppp_up; then
        if grep -Eiq '(CHAP|PAP).*fail|authentication (failed|failure|rejected)|auth.*denied' "$VPN/pppd.log" 2>/dev/null; then
            start_error PPP "VPN server rejected PAP/CHAP authentication"
        fi
        start_error PPP "ppp0 did not get a usable IPv4 address"
    fi
    if [ "$VPN_L2" = 1 ] && ! ppp_vxlan_endpoints >/dev/null; then
        start_error L2 "PPP peer must differ from the public L2TP server"
    fi
    ;;
stop)
    [ -f "$owned" ] || exit 0
    rc=0
    if [ -p "$VPN/l2tp-control" ] && ppp_up; then
        timeout -t 4 sh -c "printf 'd m7350\n' > $VPN/l2tp-control"
        i=0; while ppp_up && [ "$i" -lt 10 ]; do i=$((i+1)); sleep 1; done
    fi
    if [ -S "$VPN/charon.vici" ]; then
        "$VPN/swanctl" --terminate --ike m7350-l2tp --timeout 10 --uri "$vici" >/dev/null 2>&1
    fi
    kill_owned "$VPN/xl2tpd.pid" "$VPN/xl2tpd.conf" || rc=1
    kill_owned "$VPN/charon.pid" "$VPN/charon" || rc=1
    ip link show dev ppp0 >/dev/null 2>&1 && { say "ppp0 still up"; rc=1; }
    if [ "$rc" = 0 ] && [ -f "$guard" ]; then
        ip xfrm policy delete dir out dst "$VPN_SERVER/32" proto udp dport 1701 || rc=1
        [ "$rc" != 0 ] || rm -f "$guard"
    fi
    if [ -f "$pinned" ]; then
        ip route del $(cat "$pinned") 2>/dev/null
        rm -f "$pinned"
    fi
    # Routing (25) is stopped before this step; nothing else may remain.
    if [ "$rc" = 0 ] && [ ! -e "$VPN/routing-started" ]; then
        rm -rf "$VPN" && rm -f "$owned" || rc=1
    fi
    exit $rc
    ;;
resume)
    ip xfrm policy | awk -v peer="$VPN_SERVER/32" '
        /^src / { match_peer=($4==peer && $8==1701) }
        /dir out action block priority 2147482999/ && match_peer { ok=1 }
        END { exit !ok }' || exit 1
    [ -f "$guard" ] && [ -S "$VPN/charon.vici" ] && [ -p "$VPN/l2tp-control" ] || exit 1
    src=$(lte_src)
    case "$src" in ''|*[!0-9.]*) exit 1;; esac
    export STRONGSWAN_CONF="$VPN/etc/strongswan.conf"
    cfg=$VPN/etc/swanctl/swanctl.conf
    if ! grep -Fxq "  local_addrs = $src" "$cfg"; then
        umask 077
        sed "s/^[[:space:]]*local_addrs[[:space:]]*=.*/  local_addrs = $src/" "$cfg" > "$cfg.refresh" || exit 1
        "$VPN/swanctl" --load-conns --file "$cfg.refresh" --uri "$vici" || exit 1
        mv "$cfg.refresh" "$cfg" || exit 1
    fi
    esp_ready || initiate_ike_recover || exit 1
    esp_ready || exit 1
    if ! ppp_up; then
        ip link show dev ppp0 >/dev/null 2>&1 && exit 1
        timeout -t 4 sh -c "printf 'c m7350\n' > $VPN/l2tp-control" || exit 1
    fi
    i=0; while ! ppp_up && [ "$i" -lt 20 ]; do i=$((i+1)); sleep 1; done
    ppp_up || exit 1
    if [ -f "$VPN/routing-installed" ]; then
        ip route replace default dev ppp0 metric 10 table 735 || exit 1
    fi
    ;;
check)
    ppp_up && esp_ready
    ;;
absent)
    ! ip link show dev ppp0 >/dev/null 2>&1 && [ ! -e "$guard" ] && [ ! -e "$owned" ] && [ ! -e "$VPN" ] && ! pidof charon >/dev/null && ! pidof xl2tpd >/dev/null
    ;;
*) exit 2 ;;
esac
