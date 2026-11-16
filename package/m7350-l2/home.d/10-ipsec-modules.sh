#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Research IPsec modules (audited external build) for tunnel 1.
set -u
. "$(dirname "$0")/../lib/home-common.sh"
owned=$RUN/owned-modules

case "${1:-}" in
start)
    mkdir -p "$RUN"
    : > "$owned"
    for m in $IPSEC_MODULES; do
        if mod_loaded "$m"; then
            say "$m already loaded by someone else; refusing"
            exit 1
        fi
        verified "ko/$m.ko" || exit 1
        insmod "$KO/$m.ko" || { say "insmod $m failed"; exit 1; }
        echo "$m" >> "$owned"
    done
    ;;
stop)
    [ -f "$owned" ] || exit 0
    rc=0
    for m in $(awk '{a[NR]=$0} END {for (i = NR; i > 0; i--) print a[i]}' "$owned"); do
        mod_loaded "$m" || continue
        "$BIN/remove_owned_module" "$m" >/dev/null || rc=1
        mod_loaded "$m" && { say "$m still loaded"; rc=1; }
    done
    [ "$rc" = 0 ] && rm -f "$owned"
    exit $rc
    ;;
check)
    for m in $IPSEC_MODULES; do mod_loaded "$m" || exit 1; done
    ;;
absent)
    for m in $IPSEC_MODULES; do mod_loaded "$m" && exit 1; done
    exit 0
    ;;
*) exit 2 ;;
esac
