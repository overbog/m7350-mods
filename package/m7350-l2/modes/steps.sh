#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Ordered step runner shared by the home and provider modes.
# Each step is <mode>.d/NN-name.sh implementing: start | stop | check | absent.
#   start  bring the piece up; nonzero on failure
#   stop   tear it down; must be safe to run when the piece is already absent
#   check  zero when the piece is fully up
#   absent zero when nothing of the piece remains (used by factory check)
# usage: steps.sh <steps-dir> {start|stop|check|absent}
set -u
dir=$1
verb=$2
BASE=${M7350_L2_BASE:-/data/m7350-l2}
RUN=${M7350_L2_RUN:-/run/m7350-l2}
. "$BASE/lib/failure.sh"

list() { ls "$dir"/[0-9][0-9]-*.sh 2>/dev/null | sort; }
rlist() { list | sort -r; }
step_error() {
    record_start_error "$1: $2" || :
    message=$(cat "$RUN/start-error" 2>/dev/null || printf '%s: %s' "$1" "$2")
    printf '%s\n' "$message" >&2
    capture_start_failure || :
    # Keep the first reason even if stopping a driver resets the router.
    (umask 077; printf '%s\n' "$message" > "$BASE/state/.last_error.$$" &&
        mv -f "$BASE/state/.last_error.$$" "$BASE/state/last_error") || :
}

start_or_check() {
    step_name=$(basename "$1" .sh)
    diagnostic=$(umask 077; mktemp "$RUN/.step-error.XXXXXX") || {
        step_error "$step_name" "could not create a diagnostic file"
        return 1
    }
    if sh "$1" "$2" 2>"$diagnostic"; then
        rm -f "$diagnostic"
        return 0
    else
        step_status=$?
    fi
    # Only a message explicitly emitted by this step's say() can become UI text.
    detail=$(filter_failure_log "$diagnostic" |
        awk -v prefix="[$step_name] " 'index($0, prefix) == 1 { text=substr($0, length(prefix)+1) } END { print text }')
    rm -f "$diagnostic"
    case "$2" in
        start) fallback="could not initialize (exit $step_status)" ;;
        check) fallback="readiness check failed after startup (exit $step_status)" ;;
    esac
    case "$step_name" in
        10-ipsec-modules) label="IPsec modules" ;;
        20-tunnel1) label="L2TP/IPsec" ;;
        25-routing) label="VPN routing and DNS" ;;
        28-lte) label="LTE bridge" ;;
        30-zx-vap) label="Wi-Fi access points" ;;
        40-vxlan) label="VXLAN" ;;
        50-bridge2) label="L2 bridge" ;;
        60-supervise) label="VPN monitor" ;;
        *) label=$step_name ;;
    esac
    step_error "$label" "${detail:-$fallback}"
    return 1
}

case "$verb" in
    start)
        mkdir -p "$RUN" || exit 1
        steps=$(list)
        [ -n "$steps" ] || { step_error "$(basename "$dir" .d)" "mode not packaged (no startup steps)"; exit 1; }
        done_steps=
        for s in $steps; do
            if start_or_check "$s" start; then
                done_steps="$s $done_steps"
            else
                sh "$s" stop
                for d in $done_steps; do sh "$d" stop; done
                exit 1
            fi
        done
        for s in $steps; do
            start_or_check "$s" check || exit 1
        done
        ;;
    stop)
        rc=0
        for s in $(rlist); do sh "$s" stop || rc=1; done
        exit $rc
        ;;
    check|absent)
        for s in $(list); do sh "$s" "$verb" || exit 1; done
        ;;
    *) echo "usage: $0 DIR {start|stop|check|absent}" >&2; exit 2 ;;
esac
