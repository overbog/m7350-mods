#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# One VPN failure scenario on the device, and what the user gets to see.
# Runs ON the M7350 (busybox sh), as root, in factory mode, with LTE up.
# Run only against a server you are authorized to test.
#
# usage: SCENARIO=<name> sh vpn-failure-test.sh
#    or: ssh root@192.168.0.1 'SCENARIO=<name> sh -s' < vpn-failure-test.sh
#   psk          wrong IPsec PSK (random)
#   proposal     IKE proposal the VPN server should not accept (BAD_IKE overrides)
#   unreachable  server 192.0.2.1 (TEST-NET-1, reserved documentation address)
#   pppauth      wrong PPP password (IPsec succeeds, PPP auth fails)
#   l2vtep       L2 on, against a lab server without a usable VXLAN peer
# Env: BASE_SLOT (profile copied, default: the selected one),
#      EXPECT (extended regex the reason must match, case-insensitive).
#
# The test profile is a copy of the base profile with one field changed,
# stored 0600 as slot "ftest" and removed afterwards; the previous selection
# is restored. Secrets are never printed. The base profile is not modified.
set -u
BASE=${M7350_L2_BASE:-/data/m7350-l2}
RUN=${M7350_L2_RUN:-/run/m7350-l2}
MODE=${M7350_MODE:-$BASE/bin/m7350-mode}
ST=$BASE/state
SLOT=ftest
TEST=$ST/vpn-$SLOT.conf
SCENARIO=${SCENARIO:-}

say() { printf '%s\n' "$*"; }
die() { say "ABORT: $*"; exit 2; }
hide() { sed -E 's/((psk|password|secret|passphrase|PSK|Password)[=: "]+)[^ ",;]*/\1***/g'; }
status_value() { "$MODE" status 2>/dev/null | sed -n "s/^$1=//p"; }

rand() { head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n'; }

case "$SCENARIO" in
    psk)         field=psk;      value=$(rand);   expect='pre-shared|authentication' ;;
    proposal)    field=ike;      value=${BAD_IKE:-aes256-sha512-modp8192}; expect='proposal' ;;
    unreachable) field=server;   value=192.0.2.1; expect='no answer|no response|timeout|unreachable|did not answer' ;;
    pppauth)     field=password; value=x$(rand);  expect='ppp|chap|pap|password|user' ;;
    l2vtep)      field=l2;       value=1;         expect='l2|vtep|peer' ;;
    *) say "usage: SCENARIO={psk|proposal|unreachable|pppauth|l2vtep} sh $0"; exit 2 ;;
esac
expect=${EXPECT:-$expect}

# Preconditions: nothing running, factory, a base profile, LTE up.
[ -x "$MODE" ] || die "$MODE missing"
[ "$(status_value active)" = factory ] || die "active mode is not factory"
[ ! -d "$RUN/lock" ] || die "a mode switch is running"
prev=$(cat "$ST/vpn-selected" 2>/dev/null)
src=${BASE_SLOT:-$prev}
[ -n "$src" ] && [ -f "$ST/vpn-$src.conf" ] || die "no base profile (BASE_SLOT)"
[ "$src" != "$SLOT" ] || die "base profile is the test slot"
[ ! -e "$TEST" ] || die "$TEST exists from an earlier run; check and remove it"
if [ -z "${M7350_FTEST_NO_LTE_CHECK:-}" ]; then
    ip -4 addr show rmnet_data0 2>/dev/null | grep -q 'inet ' || die "LTE has no IPv4"
fi

restore() {
    [ "$(status_value active)" = factory ] || "$MODE" set factory >/dev/null 2>&1
    if [ -n "$prev" ]; then
        printf '%s\n' "$prev" > "$ST/vpn-selected.tmp" && mv -f "$ST/vpn-selected.tmp" "$ST/vpn-selected"
    else
        rm -f "$ST/vpn-selected"
    fi
    rm -f "$TEST" "$TEST.tmp"
}
trap restore EXIT
trap 'exit 3' INT TERM

# Test profile: the base profile with one field replaced (added if missing).
umask 077
awk -v k="$field" -v v="$value" '
    index($0, k "=") == 1 { print k "=" v; done = 1; next }
    { print }
    END { if (!done) print k "=" v }' "$ST/vpn-$src.conf" > "$TEST.tmp" || die "could not write the test profile"
if [ "$SCENARIO" = l2vtep ]; then
    for kv in vni=7350 port=4789; do
        k=${kv%%=*}
        grep -q "^$k=[0-9]" "$TEST.tmp" || { grep -v "^$k=" "$TEST.tmp" > "$TEST.tmp2"; echo "$kv" >> "$TEST.tmp2"; mv -f "$TEST.tmp2" "$TEST.tmp"; }
    done
fi
mv -f "$TEST.tmp" "$TEST"
printf '%s\n' "$SLOT" > "$ST/vpn-selected.tmp" && mv -f "$ST/vpn-selected.tmp" "$ST/vpn-selected"

marker="ftest-$SCENARIO-$$"
logger -t m7350-ftest -- "BEGIN $marker" 2>/dev/null || :
t0=$(cut -d' ' -f1 /proc/uptime)
"$MODE" set vpn > "$RUN/ftest.out" 2>&1
rc=$?
t1=$(cut -d' ' -f1 /proc/uptime)
active=$(status_value active)
reason=$(status_value last_error)

say "== scenario $SCENARIO (field $field changed; base profile $src)"
say "set vpn: rc=$rc in $(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.1f", b - a }') s; active=$active"
say "last_error: $reason" | hide
say "-- m7350-mode output"
hide < "$RUN/ftest.out"; rm -f "$RUN/ftest.out"
say "-- syslog since start"
logread 2>/dev/null | awk -v m="BEGIN $marker" 'index($0, m) { on = 1; next } on' |
    grep -E 'm7350|charon|xl2tpd|pppd' | hide | tail -40
if [ -d "$RUN/last-failure" ]; then
    say "-- $RUN/last-failure"
    for f in "$RUN"/last-failure/*; do [ -f "$f" ] && { say "# ${f##*/}"; hide < "$f" | tail -15; }; done
fi
left=$(pidof charon xl2tpd pppd 2>/dev/null)
ip link show ppp0 >/dev/null 2>&1 && left="$left ppp0"
ip link show vxlan0 >/dev/null 2>&1 && left="$left vxlan0"

# Verdict: what the user would see.
fail=0
check() { if [ "$2" = 0 ]; then say "PASS $1"; else say "FAIL $1"; fail=1; fi; }
[ "$rc" != 0 ]; check "switch reported failure (rc=$rc)" $?
[ "$active" = factory ]; check "back in factory (active=$active)" $?
# Generic messages that do not tell the user what to fix.
generic='^start of [a-z]* failed|^Startup: could not start|could not establish the IKE/ESP security association'
[ -n "$reason" ] && ! printf '%s\n' "$reason" | grep -Eq "$generic"; check "last_error names a specific reason" $?
printf '%s\n' "$reason" | grep -Eqi "$expect"; check "reason matches /$expect/" $?
[ -z "$left" ]; check "nothing left running${left:+ ($left)}" $?
say "RESULT $SCENARIO: $([ "$fail" = 0 ] && echo PASS || echo FAIL)"
exit "$fail"
