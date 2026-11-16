# SPDX-License-Identifier: GPL-2.0-only
# Sourced by the home.d steps. POSIX sh for busybox ash.
# Persistent files live in $BASE (UBIFS /data); runtime state in RAM.
# The research binaries were built with /run/m7350-vpn compiled in, so the
# VPN runtime directory keeps that path; it holds symlinks into $BASE.

BASE=${M7350_L2_BASE:-/data/m7350-l2}
RUN=${M7350_L2_RUN:-/run/m7350-l2}
VPN=${M7350_VPN_RUN:-/run/m7350-vpn}
LIB=$BASE/lib
KO=$LIB/ko
BIN=$LIB/bin
RESEARCH=$LIB/research
SECRETS=$BASE/secrets

. "$BASE/lib/vpn-profile.sh"

# Non-secret deployment settings (VPN_SERVER, VPN_DNS, VTEP, PPP_ADDR, ...).
. "$BASE/etc/home.env"
VPN_L2=1; VPN_VNI=7350; VPN_PORT=4789
VPN_USB=
VPN_AUTH=chap; VPN_MTU=1360
VPN_IKE=aes128-sha1-modp2048; VPN_ESP=aes128-sha1-modp1024
VPN_USER=; VPN_PASS=; VPN_PSK=
if [ -f "$RUN/vpn-profile.conf" ]; then
    vpn_read_file "$RUN/vpn-profile.conf" || exit 1
fi

IPSEC_MODULES="aead pcompress cryptomgr sha1_generic sha256_generic hmac cbc authenc seqiv xfrm_algo xfrm_user esp4"

say() { echo "[$(basename "$0" .sh)] $*" >&2; }

mod_loaded() { grep -q "^$1 " /proc/modules; }

# Verify a staged artifact against the package manifest before using it.
verified() {
    want=$(awk -v f="$1" '$2 == f {print $1}' "$LIB/MANIFEST.sha256")
    [ -n "$want" ] || { say "not in manifest: $1"; return 1; }
    printf '%s  %s\n' "$want" "$LIB/$1" | sha256sum -c - >/dev/null 2>&1 ||
        { say "hash mismatch: $1"; return 1; }
}

# Kill a process only if its pid file still names the expected command.
kill_owned() {  # kill_owned <pidfile> <command-substring>
    [ -f "$1" ] || return 0
    pid=$(cat "$1")
    if [ -n "$pid" ] && [ -r "/proc/$pid/cmdline" ] &&
       tr '\000' ' ' < "/proc/$pid/cmdline" | grep -qF "$2"; then
        kill -TERM "$pid"
        i=0
        while [ -d "/proc/$pid" ] && [ "$i" -lt 10 ]; do i=$((i+1)); sleep 1; done
        [ -d "/proc/$pid" ] && { say "pid $pid did not exit"; return 1; }
    fi
    rm -f "$1"
}

alive_owned() {  # alive_owned <pidfile> <command-substring>
    [ -f "$1" ] || return 1
    pid=$(cat "$1")
    [ -n "$pid" ] && [ -r "/proc/$pid/cmdline" ] &&
        tr '\000' ' ' < "/proc/$pid/cmdline" | grep -qF "$2"
}

esp_ready() {
    ip xfrm state | awk -v peer="$VPN_SERVER" '
        /^src / { direction = ($2 == peer ? "in" : ($4 == peer ? "out" : "")) }
        /^[[:space:]]*proto esp / && direction != "" { seen[direction] = 1 }
        END { exit !(seen["in"] && seen["out"]) }
    '
}

ppp_local_ipv4() {
    ip -4 addr show dev ppp0 2>/dev/null | awk -v addr="$PPP_ADDR" '
        $1=="inet" { split($2,a,"/"); if (addr=="" || a[1]==addr) { print a[1]; ok=1; exit } }
        END { exit !ok }'
}

ppp_up() { ppp_local_ipv4 >/dev/null; }

# Read both addresses from the same point-to-point address record.
ppp_vxlan_endpoints() {
    endpoints=$(ip -4 addr show dev ppp0 2>/dev/null | awk '
        $1 == "inet" && $3 == "peer" {
            split($2, local_addr, "/"); split($4, peer_addr, "/")
            print local_addr[1], peer_addr[1]; exit
        }')
    set -- $endpoints
    [ "$#" = 2 ] && vpn_ipv4 "$1" && vpn_ipv4 "$2" &&
        [ "$1" != "$2" ] && [ "$2" != "$VPN_SERVER" ] || return 1
    printf '%s %s\n' "$1" "$2"
}

ppp_tcp_mss() {
    mtu=$(cat /sys/class/net/ppp0/mtu 2>/dev/null) || return 1
    vpn_number "$mtu" 68 65535 || return 1
    limit=${VPN_MTU:-1360}
    [ "$mtu" -le "$limit" ] || mtu=$limit
    printf '%s\n' "$((mtu - 40))"
}

vpn_dns_ipv4() {
    dns_ip=$VPN_DNS
    if [ -z "$dns_ip" ]; then
        dns_ip=$(cat "$VPN/peer-dns" 2>/dev/null) || return 1
    fi
    vpn_ipv4 "$dns_ip" && [ "$dns_ip" != "$VPN_SERVER" ] || return 1
    printf '%s\n' "$dns_ip"
}

lte_src() {
    ip route get "$VPN_SERVER" | awk '/dev rmnet_data0/ {for(i=1;i<NF;i++) if($i=="src") print $(i+1)}'
}
