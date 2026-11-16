#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Keeps home mode up across PPP/IPsec drops: detach L2, resume PPP with the
# research resume script, restage VXLAN and reattach. Never runs during a
# mode switch: it takes the switcher's lock for each repair.
set -u
here=$(cd "$(dirname "$0")" && pwd)
. "$here/../lib/home-common.sh"
pidf=$RUN/supervise.pid
INTERVAL=${M7350_L2_SUPERVISE_SECS:-10}

repair() {
    sh "$here/50-bridge2.sh" stop
    sh "$here/40-vxlan.sh" stop || return 1
    sh "$here/20-tunnel1.sh" resume >&2 || return 1
    sh "$here/40-vxlan.sh" start || return 1
    sh "$here/50-bridge2.sh" start
}

loop() {
    while :; do
        sleep "$INTERVAL"
        if mkdir "$RUN/lock" 2>/dev/null; then
            echo $$ > "$RUN/lock/pid"
            sh "$here/25-routing.sh" refresh
            rm -rf "$RUN/lock"
        fi
        ppp_up && esp_ready && { [ "$VPN_L2" = 0 ] || { [ -e /sys/class/net/bridge2/brif/vxlan0 ] && sh "$here/40-vxlan.sh" check; }; } && continue
        mkdir "$RUN/lock" 2>/dev/null || continue
        echo $$ > "$RUN/lock/pid"
        if repair; then say "repaired"; else say "repair failed; retrying"; fi
        rm -rf "$RUN/lock"
    done
}

case "${1:-}" in
start)
    mkdir -p "$RUN"
    sh "$0" loop > "$RUN/supervise.log" 2>&1 &
    echo $! > "$pidf"
    ;;
loop) loop ;;
stop) kill_owned "$pidf" "60-supervise.sh loop" ;;
check) alive_owned "$pidf" "60-supervise.sh loop" ;;
absent) ! alive_owned "$pidf" "60-supervise.sh loop" ;;
*) exit 2 ;;
esac
