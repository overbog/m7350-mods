#!/bin/sh
# Attach vxlan0 to bridge2: SSID 2 joins the remote LAN at L2.
# Needs the remote side (VTEP on the LAN bridge) to be in place.
set -u
. "$(dirname "$0")/../lib/home-common.sh"

if [ "$VPN_L2" = 0 ]; then
    case "${1:-}" in start|stop|check) exit 0;; esac
fi
case "${1:-}" in
start)
    usb_bridge=bridge0
    [ ! -f "$RUN/usb-bridge" ] || usb_bridge=$(cat "$RUN/usb-bridge")
    endpoints=$(ppp_vxlan_endpoints) || exit 1
    [ "$endpoints" = "$(cat "$RUN/vxlan-ppp-endpoints" 2>/dev/null)" ] || exit 1
    IPSEC_PEER=$VPN_SERVER VTEP=${endpoints#* } PORT=$VPN_PORT VNI=$VPN_VNI PPP_ADDR=${endpoints% *} USB_BRIDGE=$usb_bridge \
        sh "$RESEARCH/m7350-bridge2-lan.sh" attach >&2
    ;;
stop) sh "$RESEARCH/m7350-bridge2-lan.sh" detach >&2 ;;
check) [ -e /sys/class/net/bridge2/brif/vxlan0 ] ;;
absent) [ ! -e /run/m7350-bridge2-lan ] && [ ! -e /sys/class/net/bridge2/brif/vxlan0 ] ;;
*) exit 2 ;;
esac
