#!/bin/sh
# Factory mode owns nothing. "check" means: no object of any other mode remains.
set -u
here=$(dirname "$0")
base=$(dirname "$here")
case "${1:-}" in
    start|stop) exit 0 ;;
    check)
        for m in home provider; do
            sh "$here/steps.sh" "$base/$m.d" absent || { echo "leftover objects from mode $m" >&2; exit 1; }
        done
        ;;
    *) echo "usage: $0 {start|stop|check}" >&2; exit 2 ;;
esac
