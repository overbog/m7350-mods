#!/bin/sh
# Replace OEM Wi-Fi with ZX in RAM. Keep the three APs on separate bridges.
set -u
. "$(dirname "$0")/../lib/home-common.sh"
init=/etc/init.d/wlanManager
v=wlan0-va0
lte=wlan0-va1
# With L2 off, keep the only VAP in the first hardware slot.
[ "$VPN_L2" = 1 ] || lte=$v
usb=rndis0
usb_bridge=bridge0
oem_ko=/usr/lib/modules/3.18.20/extra/rtl8192es.ko
oem_hash=244a4fc6e96a735a25c08b6bc913db76bba739bbe5ec02aba0980efb53490148
zx_size=1320175
oem_size=908783

zx_loaded() {
    grep -q "^rtl8192es $zx_size " /proc/modules ||
        { [ -f "$RUN/zx-two-vap" ] && mod_loaded rtl8192es && ! oem_loaded; }
}
oem_loaded() { grep -q "^rtl8192es $oem_size " /proc/modules; }
held() { grep -q " $init " /proc/self/mountinfo; }

# Advertise the gateway's current bridge MAC to USB clients after the move.
announce_usb_gateway() {
    local bridge=$1 address
    address=$(ip -4 addr show dev "$bridge" scope global |
        awk '$1 == "inet" { split($2, cidr, "/"); print cidr[1]; exit }')
    if [ -z "$address" ] ||
        ! arping -q -b -U -c 3 -w 4 -I "$bridge" -s "$address" "$address"; then
        say "Could not announce the USB gateway on $bridge"
    fi
}

# WPS helpers can inherit wlanmgr's socket and leave its receive queue
# open after wlanmgr exits. key_detect sends there synchronously.
stop_oem_wps_socket_holders() {
    local inode name pid attempt
    inode=$(awk '$8 == "/tmp/ha_wm.sock" { print $7; exit }' /proc/net/unix)
    [ -n "$inode" ] || return 0
    for name in webs wscd iwcontrol; do
        for pid in $(pidof "$name" 2>/dev/null); do
            [ "$(readlink "/proc/$pid/exe")" = "/bin/$name" ] || continue
            if [ "$name" = webs ]; then
                [ "$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null)" = '/bin/webs -x ' ] || continue
            fi
            ls -l "/proc/$pid/fd" 2>/dev/null | grep -Fq "socket:[$inode]" || continue
            kill -TERM "$pid" 2>/dev/null || :
        done
    done
    for attempt in 1 2 3 4 5; do
        if ! awk -v inode="$inode" '$7 == inode { found=1 } END { exit !found }' /proc/net/unix; then
            return 0
        fi
        sleep 1
    done
    say "OEM WPS socket is still open"
    return 1
}

configure_ap_security() {
    local iface=$1 key=$2 kv
    # ZX uses PSK_WPA2=2 and the CCMP-only cipher mask 8.
    for kv in authtype=2 encmode=2 psk_enable=2 wpa_cipher=0 wpa2_cipher=8; do
        iwpriv "$iface" set_mib "$kv" >/dev/null || return 1
    done
    iwpriv "$iface" set_mib "passphrase=$key" >/dev/null
}

configure_vap() {
    local iface=$1 name=$2 mac=$3 key=$4 kv
    ifconfig "$iface" hw ether "$mac" || return 1
    for kv in "ssid=$name" opmode=16 band=11 "channel=$CHANNEL"; do
        iwpriv "$iface" set_mib "$kv" >/dev/null || return 1
    done
    configure_ap_security "$iface" "$key"
}

load_zx() {
    local mem
    mem=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
    case "$mem" in ''|*[!0-9]*) return 1 ;; esac
    [ "$mem" -ge "$MIN_MEM_KIB" ] || { say "MemAvailable ${mem} KiB below $MIN_MEM_KIB"; return 1; }
    touch "$RUN/zx-two-vap" || return 1
    ( cd "$KO" && "$BIN/load-module-fd-musl" ./rtl8192es-two-vap.ko ) || return 1
    zx_loaded || { say "ZX driver not loaded"; return 1; }
}

wait_zx_interfaces() {
    local attempt=0 iface
    while :; do
        missing=
        for iface in "$@"; do
            if ! ip link show dev "$iface" >/dev/null 2>&1; then
                missing=$iface
                break
            fi
        done
        [ -n "$missing" ] || return 0
        [ "$attempt" -lt 3 ] || return 1
        attempt=$((attempt + 1))
        sleep 1
    done
}

compact_zx_memory() {
    [ ! -w /proc/sys/vm/compact_memory ] ||
        (printf '1\n' > /proc/sys/vm/compact_memory) 2>/dev/null || :
}

prepare_zx() {
    local missing
    set -- wlan0 "$lte"
    [ "$VPN_L2" = 0 ] || set -- "$@" "$v"
    load_zx || return 1
    wait_zx_interfaces "$@" && return 0
    say "$missing missing after ZX probe; retrying the driver load"
    rmmod rtl8192es || { say "could not unload the incomplete ZX driver"; return 1; }
    mod_loaded rtl8192es && { say "incomplete ZX driver still loaded"; return 1; }
    # The SDIO probe needs a contiguous 64 KiB RX buffer. A loaded
    # module alone does not mean the probe succeeded.
    compact_zx_memory
    load_zx || return 1
    wait_zx_interfaces "$@" || { say "$missing missing after retrying the ZX driver probe"; return 1; }
}

case "${1:-}" in
start)
    [ -e /sys/class/net/bridge2 ] && { say "bridge2 already exists"; exit 1; }
    held && { say "$init already bind-mounted"; exit 1; }
    [ -e "/sys/class/net/bridge0/brif/$usb" ] || { say "OEM USB port missing from bridge0"; exit 1; }
    verified ko/rtl8192es-two-vap.ko && verified bin/load-module-fd-musl || exit 1
    mkdir -p "$RUN"
    # Keep the OEM manager from restarting the radio under us.
    cat > "$RUN/hold-init" <<'HOLD'
#!/bin/sh
exit 0
HOLD
    chmod 700 "$RUN/hold-init"
    cp "$init" "$RUN/oem-init"
    mount -o bind "$RUN/hold-init" "$init" || exit 1
    sh "$RUN/oem-init" stop
    i=0; while pidof wlanmgr >/dev/null && [ "$i" -lt 5 ]; do i=$((i+1)); sleep 1; done
    pidof wlanmgr >/dev/null && { say "wlanmgr did not stop"; exit 1; }
    stop_oem_wps_socket_holders || exit 1
    mod_loaded rtl8192es && rmmod rtl8192es
    mod_loaded rtl8192es && { say "OEM driver still loaded"; exit 1; }
    prepare_zx || exit 1
    /usr/bin/wifi/script/wlan_8192c.sh wlan0 > "$RUN/zx-profile.log" 2>&1 || { say "OEM Wi-Fi profile failed"; exit 1; }
    oem_pass=$(cat /data/rtl8192c/wlan0/wpa_psk) || exit 1
    lte_pass=$(wifi_custom_password 1p) || exit 1
    l3_pass=$(wifi_custom_password 2p) || exit 1
    l2_pass=$(wifi_custom_password 3p) || exit 1
    lte_pass=${lte_pass:-$oem_pass}
    l3_pass=${l3_pass:-$oem_pass}
    l2_pass=${l2_pass:-$oem_pass}
    if [ -s "$BASE/state/home.conf" ]; then
        {
            IFS= read -r saved_l2 || :
            IFS= read -r saved_l3 || :
            IFS= read -r saved_lte || :
        } < "$BASE/state/home.conf"
        SSID2=${saved_l2:-$SSID2}
        SSID_L3=${saved_l3:-$SSID_L3}
        SSID_LTE=${saved_lte:-$SSID_LTE}
    fi
    case "${VPN_USB:-$(vpn_legacy_usb)}" in
        l3) usb_bridge=bridge0 ;;
        l2) [ "$VPN_L2" = 1 ] || exit 1; usb_bridge=bridge2 ;;
        lte) usb_bridge=bridge3 ;;
        *) exit 1 ;;
    esac
    for key in "$lte_pass" "$l3_pass" "$l2_pass"; do
        [ "${#key}" -ge 8 ] && [ "${#key}" -le 63 ] || exit 1
    done
    configure_ap_security wlan0 "$l3_pass" || exit 1
    iwpriv wlan0 set_mib "ssid=$SSID_L3" >/dev/null || exit 1
    [ "$VPN_L2" = 0 ] || configure_vap "$v" "$SSID2" "$SSID2_MAC" "$l2_pass" || exit 1
    configure_vap "$lte" "$SSID_LTE" "$SSID_LTE_MAC" "$lte_pass" || exit 1
    unset oem_pass lte_pass l3_pass l2_pass key
    [ -e /sys/class/net/bridge0/brif/wlan0 ] || brctl addif bridge0 wlan0 || exit 1
    if [ "$VPN_L2" = 1 ]; then
        brctl addbr bridge2 && brctl addif bridge2 "$v" && ip link set bridge2 up || exit 1
    fi
    brctl addif bridge3 "$lte" || exit 1
    iwpriv wlan0 set_mib "channel=$CHANNEL" >/dev/null || exit 1
    iwpriv wlan0 set_mib vap_enable=1 >/dev/null || exit 1
    ip link set wlan0 up || exit 1
    sleep 15
    [ "$VPN_L2" = 0 ] || ip link set "$v" up || exit 1
    ip link set "$lte" up || exit 1
    if [ "$usb_bridge" != bridge0 ]; then
        printf '%s\n' "$usb_bridge" > "$RUN/usb-bridge" || exit 1
        brctl delif bridge0 "$usb" && brctl addif "$usb_bridge" "$usb" || exit 1
        if [ "$usb_bridge" = bridge3 ]; then
            announce_usb_gateway bridge3
        fi
    fi
    ;;
stop)
    rc=0
    previous=
    if [ -f "$RUN/usb-bridge" ]; then
        previous=$(cat "$RUN/usb-bridge")
        case "$previous" in bridge2|bridge3) ;; *) exit 1 ;; esac
        if [ -e "/sys/class/net/$previous/brif/$usb" ]; then
            brctl delif "$previous" "$usb" || exit 1
        fi
        [ -e "/sys/class/net/bridge0/brif/$usb" ] || brctl addif bridge0 "$usb" || exit 1
        rm -f "$RUN/usb-bridge"
    fi
    if zx_loaded; then
        # Close the VAPs before their parent and detach all radio ports before unloading ZX.
        for iface in wlan0-va1 wlan0-va0 wlan0; do
            [ -e "/sys/class/net/$iface" ] || continue
            ip link set "$iface" down || exit 1
            if [ -e "/sys/class/net/$iface/brport" ]; then
                bridge=$(readlink "/sys/class/net/$iface/brport/bridge") || exit 1
                brctl delif "${bridge##*/}" "$iface" || exit 1
            fi
        done
    fi
    if [ -e /sys/class/net/bridge2 ] && { [ -f "$RUN/zx-two-vap" ] || zx_loaded; }; then
        ip link set bridge2 down
        brctl delbr bridge2 || rc=1
    fi
    zx_loaded && rmmod rtl8192es
    if zx_loaded; then say "ZX driver still loaded"; rc=1; else rm -f "$RUN/zx-two-vap"; fi
    if held; then umount "$init" || rc=1; fi
    # Return the radio to the OEM driver and manager.
    pidof wlanmgr >/dev/null || "$init" start
    if ! mod_loaded rtl8192es; then
        printf '%s  %s\n' "$oem_hash" "$oem_ko" | sha256sum -c - >/dev/null 2>&1 && insmod "$oem_ko"
    fi
    if oem_loaded; then
        if [ ! -e /sys/class/net/wlan0/brport ] || [ "$(cat /sys/class/net/wlan0/brport/state)" != 3 ]; then
            /usr/bin/wifi/script/wlan_8192c.sh wlan0 > "$RUN/oem-profile.log" 2>&1
            [ -e /sys/class/net/wlan0/brport ] || brctl addif bridge0 wlan0
            ip link set wlan0 up
        fi
    else
        say "OEM Wi-Fi driver not restored"; rc=1
    fi
    if [ "$previous" = bridge3 ]; then
        announce_usb_gateway bridge0
    fi
    exit $rc
    ;;
check)
    usb_bridge=bridge0
    [ ! -f "$RUN/usb-bridge" ] || usb_bridge=$(cat "$RUN/usb-bridge")
    zx_loaded && [ -e "/sys/class/net/$usb_bridge/brif/$usb" ] &&
        { [ "$VPN_L2" = 0 ] || [ -e /sys/class/net/bridge2/brif/$v ]; } && [ -e /sys/class/net/bridge3/brif/$lte ] &&
        [ -e /sys/class/net/bridge0/brif/wlan0 ] || exit 1
    ifaces="wlan0 $lte"
    [ "$VPN_L2" = 0 ] || ifaces="$ifaces $v"
    for iface in $ifaces; do
        flags=$(cat "/sys/class/net/$iface/flags") || exit 1
        [ "$((flags & 1))" = 1 ] || exit 1
    done
    ;;
absent)
    [ ! -e /sys/class/net/bridge2 ] && [ ! -e "$RUN/usb-bridge" ] && ! zx_loaded && ! held
    ;;
*) exit 2 ;;
esac
