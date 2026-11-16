#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -u
here=$(dirname "$0")
BASE=${M7350_L2_BASE:-/data/m7350-l2}
RUN=${M7350_L2_RUN:-/run/m7350-l2}
. "$here/../lib/vpn-profile.sh"
umask 077
prepare() {
    [ ! -d "$RUN/vpn-profile-write" ] || return 1
    chosen=$(vpn_selected)
    vpn_read "$chosen" && vpn_validate
}
case "${1:-}" in
validate) prepare ;;
start)
    prepare || exit 1
    vpn_dump > "$RUN/vpn-profile.conf" || exit 1
    printf '%s\n' "$chosen" > "$RUN/vpn-profile-slot" || exit 1
    exec sh "$here/home.sh" start
    ;;
stop)
    sh "$here/home.sh" stop || exit 1
    rm -f "$RUN/vpn-profile.conf" "$RUN/vpn-profile-slot"
    ;;
check) sh "$here/home.sh" check ;;
*) exit 2 ;;
esac
