# Trusted package defaults and data-only VPN profile reader.
vpn_value() {
    [ -f "$1" ] && awk -v key="$2" 'index($0,key "=")==1 { print substr($0,length(key)+2); exit }' "$1"
}

vpn_ipv4() {
    printf '%s\n' "$1" | awk -F. 'NF==4 { for(i=1;i<=4;i++) if($i !~ /^(0|[1-9][0-9]*)$/ || $i>255) exit 1; ok=1 } END { if(!ok) exit 1 }'
}

vpn_number() {
    case "$1" in ''|*[!0-9]*) return 1;; esac
    [ "${#1}" -le 8 ] && [ "$1" -ge "$2" ] && [ "$1" -le "$3" ]
}

vpn_slot_ok() {
    case "$1" in ''|[!a-z]*|*[!a-z0-9-]*) return 1;; esac
    [ "${#1}" -le 24 ]
}

vpn_slot_exists() {
    vpn_slot_ok "$1" || return 1
    [ -f "$BASE/state/vpn-$1.conf" ]
}

wifi_custom_password() {
    if [ -f "$SECRETS/wifi-custom.conf" ]; then
        sed -n "$1" "$SECRETS/wifi-custom.conf"
    elif [ "$1" = 3p ]; then
        cat "$SECRETS/wifi.password" 2>/dev/null || :
    fi
}

vpn_selected() {
    slot=$(cat "$BASE/state/vpn-selected" 2>/dev/null)
    if vpn_slot_exists "$slot"; then printf '%s\n' "$slot"; fi
}

vpn_edit_slot() {
    selected=$(vpn_selected)
    if [ -n "$selected" ]; then printf '%s\n' "$selected"; return; fi
    for file in "$BASE"/state/vpn-*.conf; do
        item=${file##*/vpn-}; item=${item%.conf}
        if vpn_slot_exists "$item"; then printf '%s\n' "$item"; return; fi
    done
}

vpn_read() {
    vpn_slot_exists "$1" && vpn_read_file "$BASE/state/vpn-$1.conf"
}

vpn_legacy_usb() {
    legacy_usb=$(cat "$BASE/state/home-usb" 2>/dev/null ||
        sed -n '4p' "$BASE/state/home.conf" 2>/dev/null)
    case "$legacy_usb" in
        lte|l3|l2) printf '%s\n' "$legacy_usb" ;;
        *) printf '%s\n' lte ;;
    esac
}

vpn_usb_valid() {
    case "$VPN_USB" in
        lte|l3) return 0 ;;
        l2) [ "$VPN_L2" = 1 ] ;;
        *) return 1 ;;
    esac
}

vpn_read_file() {
    profile_file=$1
    [ -f "$profile_file" ] || return 1
    vpn_get() { vpn_value "$profile_file" "$1"; }
    VPN_SERVER=$(vpn_get server); VPN_DNS=$(vpn_get dns)
    PPP_ADDR=; VTEP=$(vpn_get vtep) # legacy teardown only
    VPN_USER=$(vpn_get user); VPN_PASS=$(vpn_get password); VPN_PSK=$(vpn_get psk)
    VPN_AUTH=$(vpn_get auth); VPN_MTU=$(vpn_get mtu)
    VPN_L2=$(vpn_get l2); VPN_VNI=$(vpn_get vni); VPN_PORT=$(vpn_get port)
    VPN_IKE=$(vpn_get ike); VPN_ESP=$(vpn_get esp)
    VPN_USB=$(vpn_get usb_network)
    [ -n "$VPN_USB" ] || VPN_USB=$(vpn_legacy_usb)
}

vpn_validate() {
    vpn_usb_valid || return 1
    vpn_ipv4 "$VPN_SERVER" || return 1
    [ -z "$VPN_DNS" ] || { vpn_ipv4 "$VPN_DNS" && [ "$VPN_SERVER" != "$VPN_DNS" ]; } || return 1
    case "$VPN_AUTH" in chap|pap|mschapv2) ;; *) return 1;; esac
    case "$VPN_USER" in ''|*[!A-Za-z0-9@._+-]*) return 1;; esac
    case "$VPN_PASS" in ''|*[!\ -~]*|*[\"\'\\]*) return 1;; esac
    case "$VPN_PSK" in ''|*[!A-Za-z0-9._+@%-]*) return 1;; esac
    [ "${#VPN_USER}" -le 64 ] && [ "${#VPN_PASS}" -le 64 ] &&
        [ "${#VPN_PSK}" -le 128 ] || return 1
    case "$VPN_MTU" in
        '') ;;
        0*) return 1 ;;
        *) vpn_number "$VPN_MTU" 576 9000 || return 1 ;;
    esac
    for proposal in "$VPN_IKE" "$VPN_ESP"; do
        case "$proposal" in ''|*[!a-z0-9,-]*) return 1;; esac
        [ "${#proposal}" -le 96 ] || return 1
    done
    case "$VPN_L2" in
        0) ;;
        1) vpn_number "$VPN_VNI" 1 16777215 && vpn_number "$VPN_PORT" 1 65535 || return 1 ;;
        *) return 1 ;;
    esac
}

vpn_dump() {
    printf '%s\n' "server=$VPN_SERVER" "dns=$VPN_DNS" \
        "user=$VPN_USER" "password=$VPN_PASS" "psk=$VPN_PSK" "auth=$VPN_AUTH" \
        "mtu=$VPN_MTU" "l2=$VPN_L2" "vni=$VPN_VNI" "port=$VPN_PORT" "ike=$VPN_IKE" "esp=$VPN_ESP" \
        "usb_network=$VPN_USB"
}
