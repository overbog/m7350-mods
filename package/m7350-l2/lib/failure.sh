# SPDX-License-Identifier: GPL-2.0-only
# Sourced by the mode switcher and startup steps. BASE and RUN are set by caller.
record_start_error() {
    (
        umask 077
        mkdir -p "$RUN" &&
            { [ -s "$RUN/start-error" ] ||
              (set -C; printf '%s\n' "$1" > "$RUN/start-error"); }
    )
}

# Suppress whole lines containing credentials. Read literal values from files,
# never through awk -v (which interprets escapes) or a process argument.
filter_failure_log() {
    (
        export LC_ALL=C
        for name in ppp.password ipsec.psk provider.password provider.psk wifi.password wifi-custom.conf; do
            [ ! -r "$BASE/secrets/$name" ] || cat "$BASE/secrets/$name"
            printf '\n'
        done
        [ ! -r /data/rtl8192c/wlan0/wpa_psk ] || cat /data/rtl8192c/wlan0/wpa_psk
        printf '\n'
        for profile in "$RUN/vpn-profile.conf" "$BASE"/state/vpn-*.conf; do
            [ ! -r "$profile" ] || sed -n -e 's/^password=//p' -e 's/^psk=//p' "$profile"
        done
    ) | LC_ALL=C awk '
        FILENAME == "-" { if (length($0)) secret[++n] = $0; next }
        {
            line = tolower($0)
            if (line ~ /password|passphrase|shared.?secret|(^|[^a-z])psk([^a-z]|$)|(^|[^a-z])secret([^a-z]|$)/ ||
                line ~ /authreq|challenge|\[(enc|ike|cfg)\].*(dump|key material)|^[[:space:]]*[[:xdigit:]][[:xdigit:]][[:xdigit:]][[:xdigit:]][[:xdigit:]]*:/ ||
                line ~ /[^[:print:]\t]/) next
            for (i = 1; i <= n; i++) if (index($0, secret[i])) next
            print substr($0, 1, 240)
        }' - "$1"
}

capture_start_failure() (
    umask 077
    work=$(mktemp -d "$RUN/.last-failure.XXXXXX") || exit 1
    trap 'rm -rf "$work"' EXIT
    cat "$RUN/start-error" > "$work/reason" || exit 1
    date -u '+%Y-%m-%dT%H:%M:%SZ' > "$work/time"
    # A conflicting VPN directory belongs to another session.
    if [ "${1:-}" != reason-only ] && [ -f "$RUN/tunnel1-owned" ]; then
        vpn_dir=${M7350_VPN_RUN:-/run/m7350-vpn}
        for name in charon.out charon.log swanctl-initiate.log swanctl-phase2-first.log xl2tpd.log pppd-first.log pppd.log; do
            [ -f "$vpn_dir/$name" ] || continue
            filter_failure_log "$vpn_dir/$name" | tail -n 24 > "$work/$name"
        done
    fi
    snapshot=$RUN/last-failure
    rm -rf "$snapshot" && mv "$work" "$snapshot" || exit 1
    for name in charon.out charon.log swanctl-initiate.log swanctl-phase2-first.log xl2tpd.log pppd-first.log pppd.log; do
        [ -s "$snapshot/$name" ] || continue
        LC_ALL=C awk '
            {
                line = tolower($0)
                level = "info"
                if (line ~ /retransmit|timed out|timeout|no response|not responding/ ||
                    line ~ /no suitable proposal|no_proposal_chosen|n\(no_prop\)/ ||
                    line ~ /unable to apply received ke value|invalid dh public value size/ ||
                    line ~ /authentication.failed|authentication rejected|auth(entication)? failure|(^|[^a-z])failed([^a-z]|$)/)
                    level = "err"
                print level, $0
            }' "$snapshot/$name" |
        while IFS=' ' read -r level line; do
            logger -p "daemon.$level" -t m7350-vpn -- "$name: $line" 2>/dev/null || :
        done
    done
)
